from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from playwright.async_api import async_playwright


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = ROOT / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

from build_teamagichand_analysis import build_summary, write_outputs  # noqa: E402
from recheck_named_gmb_match import audit_store_by_name  # noqa: E402


BRAND_ROOT = ROOT / "teamagichand"
DATA = BRAND_ROOT / "data"
STORES_PATH = DATA / "stores.json"
SUMMARY_PATH = DATA / "summary.json"
AUDIT_PATH = DATA / "gmb_named_audit.json"
NOW = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
NON_ORDERING_GMB_STATUSES = {
    "needs_manual_review",
    "not_found",
    "no_gmb_profile_match",
    "unavailable_or_blocked",
    "duplicate_or_ambiguous",
    "no_gmb_order_button",
}
BLOCKED_RESOURCE_TYPES = {"image", "font", "media"}
BLOCKED_URL_PARTS = (
    "doubleclick.net",
    "google-analytics.com",
    "googletagmanager.com",
    "googlesyndication.com",
    "adservice.google.",
)


def load_payload() -> dict:
    return json.loads(STORES_PATH.read_text(encoding="utf-8-sig"))


def load_summary() -> dict:
    return json.loads(SUMMARY_PATH.read_text(encoding="utf-8-sig"))


def stores_from_payload(payload: dict) -> list[dict]:
    return payload["stores"] if isinstance(payload, dict) and "stores" in payload else payload


def normalize_gmb_evidence(store: dict) -> None:
    status = store.get("gmbOrderingStatus")
    if status in NON_ORDERING_GMB_STATUSES:
        store["hasGmbOrderingSystem"] = False
        store["gmbPickupProviders"] = []
        store["gmbDeliveryProviders"] = []
        store["gmbOrderPanelUrl"] = ""
        store["orderingSystems"] = [
            claim for claim in store.get("orderingSystems", []) if claim.get("sourceType") != "gmb"
        ]
        store["gmbOrderLinks"] = [
            link for link in store.get("gmbOrderLinks", []) if link.get("sourceType") != "gmb_order_panel"
        ]
    elif status == "button_confirmed_provider_pending":
        store["hasGmbOrderingSystem"] = True
        store["gmbPickupProviders"] = []
        store["gmbDeliveryProviders"] = []
        store["orderingSystems"] = [
            claim for claim in store.get("orderingSystems", []) if claim.get("sourceType") != "gmb"
        ]
        store["gmbOrderLinks"] = [
            link for link in store.get("gmbOrderLinks", []) if link.get("sourceType") != "gmb_order_panel"
        ]


def gmb_links_from_claims(store: dict) -> None:
    normalize_gmb_evidence(store)
    links = [link for link in store.get("gmbOrderLinks", []) if link.get("sourceType") != "gmb_order_panel"]
    for claim in store.get("orderingSystems", []):
        if claim.get("sourceType") != "gmb":
            continue
        modes = claim.get("orderMode") or ["unknown"]
        links.append(
            {
                "platform": claim.get("system") or "Unknown",
                "kind": "provider_row",
                "sourceType": "gmb_order_panel",
                "orderMode": modes,
                "label": claim.get("label") or claim.get("system") or "Google Order provider",
                "href": claim.get("evidenceUrl") or store.get("gmbOrderPanelUrl") or store.get("gmbUrl") or "",
                "panelUrl": claim.get("evidenceUrl") or store.get("gmbOrderPanelUrl") or "",
                "observedAt": NOW,
                "confidence": claim.get("confidence") or "confirmed",
            }
        )
    seen: set[tuple] = set()
    deduped: list[dict] = []
    for link in links:
        key = (link.get("platform"), tuple(link.get("orderMode") or []), link.get("href"), link.get("panelUrl"))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(link)
    store["gmbOrderLinks"] = deduped


def preserve_user_confirmed_gmb_evidence(original: dict, updated: dict) -> dict:
    original_gmb_claims = [
        claim
        for claim in original.get("orderingSystems", [])
        if claim.get("sourceType") == "gmb" and claim.get("confidence") == "confirmed"
    ]
    updated_gmb_claims = [
        claim
        for claim in updated.get("orderingSystems", [])
        if claim.get("sourceType") == "gmb" and claim.get("confidence") == "confirmed"
    ]
    if original_gmb_claims and not updated_gmb_claims:
        updated["orderingSystems"] = [
            claim for claim in updated.get("orderingSystems", []) if claim.get("sourceType") != "gmb"
        ] + original_gmb_claims
        updated["gmbPickupProviders"] = sorted(
            {
                claim.get("system")
                for claim in original_gmb_claims
                if "pickup" in (claim.get("orderMode") or []) and claim.get("system")
            }
        )
        updated["gmbDeliveryProviders"] = sorted(
            {
                claim.get("system")
                for claim in original_gmb_claims
                if "delivery" in (claim.get("orderMode") or []) and claim.get("system")
            }
        )
        updated["gmbOrderPanelUrl"] = original.get("gmbOrderPanelUrl") or updated.get("gmbOrderPanelUrl") or ""
        updated["hasGmbOrderingSystem"] = True
        updated["gmbOrderingStatus"] = "confirmed"
        updated["manualReviewReason"] = (
            "Latest re-check did not reproduce prior confirmed Google Order provider evidence; "
            "preserved prior confirmed provider claims instead of downgrading to a weaker no-button result."
        )
        signals = updated.setdefault("gmbSignals", {})
        signals["preservedPriorConfirmedEvidence"] = True
        signals["notes"] = updated["manualReviewReason"]

    if (
        original.get("gmbOrderingStatus") == "button_confirmed_provider_pending"
        and not updated_gmb_claims
        and updated.get("gmbOrderingStatus") in {"unavailable_or_blocked", "no_gmb_order_button"}
    ):
        updated["hasGmbOrderingSystem"] = True
        updated["gmbOrderingStatus"] = "button_confirmed_provider_pending"
        updated["gmbPickupProviders"] = []
        updated["gmbDeliveryProviders"] = []
        updated["manualReviewReason"] = (
            "Latest re-check did not parse providers and returned a weaker blocked/no-button result; "
            "preserved prior Google Order entry coverage as provider-pending."
        )
        signals = updated.setdefault("gmbSignals", {})
        signals["buttonDetected"] = True
        signals["providersParsed"] = False
        signals["preservedPriorPendingEntry"] = True
        signals["notes"] = updated["manualReviewReason"]

    original_signals = original.get("gmbSignals") or {}
    if not original_signals.get("userScreenshotEvidence"):
        return updated

    updated_keys = {
        (claim.get("system"), tuple(claim.get("orderMode") or []))
        for claim in updated.get("orderingSystems", [])
        if claim.get("sourceType") == "gmb"
    }
    preserved_claims = [
        claim
        for claim in original.get("orderingSystems", [])
        if claim.get("sourceType") == "gmb"
        and (claim.get("system"), tuple(claim.get("orderMode") or [])) not in updated_keys
        and (
            "User-provided screenshot" in (claim.get("evidenceNote") or "")
            or "User-provided screenshot" in (claim.get("label") or "")
        )
    ]
    if not preserved_claims:
        return updated

    updated.setdefault("orderingSystems", []).extend(preserved_claims)
    pickup = set(updated.get("gmbPickupProviders") or [])
    delivery = set(updated.get("gmbDeliveryProviders") or [])
    for claim in preserved_claims:
        if "pickup" in (claim.get("orderMode") or []):
            pickup.add(claim.get("system"))
        if "delivery" in (claim.get("orderMode") or []):
            delivery.add(claim.get("system"))
    updated["gmbPickupProviders"] = sorted(provider for provider in pickup if provider)
    updated["gmbDeliveryProviders"] = sorted(provider for provider in delivery if provider)
    updated["hasGmbOrderingSystem"] = True
    updated["gmbOrderingStatus"] = "confirmed"
    signals = updated.setdefault("gmbSignals", {})
    signals["userScreenshotEvidence"] = original_signals.get("userScreenshotEvidence")
    signals["preservedUserScreenshotEvidence"] = True
    signals["notes"] = (
        (signals.get("notes") or "").rstrip()
        + " Preserved user-screenshot-confirmed GMB provider evidence when automated re-check did not reproduce it."
    ).strip()
    return updated


def write_audit_rows(stores: list[dict]) -> None:
    rows = []
    for store in stores:
        signals = store.get("gmbSignals") or {}
        if signals.get("checkMethod") in {"not_yet_audited", ""}:
            continue
        rows.append(
            {
                "storeId": store.get("storeId"),
                "storeName": store.get("storeName"),
                "address": store.get("address"),
                "gmbStatus": store.get("gmbStatus"),
                "gmbOrderingStatus": store.get("gmbOrderingStatus"),
                "hasGmbOrderingSystem": store.get("hasGmbOrderingSystem"),
                "gmbPickupProviders": store.get("gmbPickupProviders") or [],
                "gmbDeliveryProviders": store.get("gmbDeliveryProviders") or [],
                "gmbUrl": store.get("gmbUrl") or "",
                "gmbOrderPanelUrl": store.get("gmbOrderPanelUrl") or "",
                "manualReviewReason": store.get("manualReviewReason") or "",
                "gmbSignals": signals,
            }
        )
    AUDIT_PATH.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_current_outputs(payload: dict, previous_summary: dict) -> dict:
    stores = stores_from_payload(payload)
    for store in stores:
        normalize_gmb_evidence(store)
        gmb_links_from_claims(store)
        store["hasAnyOrderingSystem"] = bool(store.get("orderingSystems"))
    summary = build_summary(stores, previous_summary.get("platformDirectAudit") or {})
    write_outputs(stores, summary)
    write_audit_rows(stores)
    return summary


def select_targets(stores: list[dict], args: argparse.Namespace) -> list[dict]:
    candidates = stores
    if args.ids:
        wanted = set(args.ids)
        candidates = [store for store in stores if store.get("storeId") in wanted]
    if args.only_pending:
        candidates = [
            store
            for store in candidates
            if store.get("gmbOrderingStatus")
            in {
                "needs_manual_review",
                "unavailable_or_blocked",
                "button_confirmed_provider_pending",
                "no_gmb_order_button",
                "not_found",
                "no_gmb_profile_match",
            }
            or not store.get("sourceCoverage", {}).get("gmbFound")
        ]
    if args.status:
        statuses = {item.strip() for item in args.status.split(",") if item.strip()}
        candidates = [store for store in candidates if store.get("gmbOrderingStatus") in statuses]
    if args.start:
        candidates = candidates[args.start :]
    if args.limit:
        candidates = candidates[: args.limit]
    return candidates


async def install_low_resource_routes(context) -> None:
    async def route_handler(route) -> None:
        request = route.request
        url = request.url.lower()
        if request.resource_type in BLOCKED_RESOURCE_TYPES or any(part in url for part in BLOCKED_URL_PARTS):
            await route.abort()
            return
        await route.continue_()

    await context.route("**/*", route_handler)


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--ids", nargs="*", default=[])
    parser.add_argument("--attempts", type=int, default=1)
    parser.add_argument("--per-store-timeout", type=int, default=120)
    parser.add_argument("--headed", action="store_true")
    parser.add_argument("--fresh-profile", action="store_true")
    parser.add_argument("--mobile", action="store_true")
    parser.add_argument("--single-search-target", action="store_true")
    parser.add_argument("--prefer-stored-gmb", action="store_true")
    parser.add_argument("--maps-first", action="store_true")
    parser.add_argument("--status", default="")
    parser.add_argument("--only-pending", action="store_true")
    parser.add_argument("--rewrite-only", action="store_true")
    parser.add_argument("--allow-heavy-resources", action="store_true")
    args = parser.parse_args()

    payload = load_payload()
    previous_summary = load_summary()
    stores = stores_from_payload(payload)
    if args.rewrite_only:
        summary = write_current_outputs(payload, previous_summary)
        print(
            json.dumps(
                {
                    "officialStoreCount": summary["officialStoreCount"],
                    "gmbOrderingSystemCount": summary["gmbOrderingSystemCount"],
                    "gmbCoverageGapCount": summary["gmbCoverageGapCount"],
                    "gmbSystemCounts": summary["gmbSystemCounts"],
                    "gmbPickupSystemCounts": summary["gmbPickupSystemCounts"],
                    "gmbDeliverySystemCounts": summary["gmbDeliverySystemCounts"],
                    "gmbOrderingStatusCounts": summary["gmbOrderingStatusCounts"],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return
    targets = select_targets(stores, args)
    updated_by_id: dict[str, dict] = {}

    os.environ["BRAND_ANALYSIS_REPORT_ROOT"] = str(BRAND_ROOT)
    temp_profile = tempfile.TemporaryDirectory(prefix="codex-brand-analysis-teamagichand-", ignore_cleanup_errors=True)
    profile_dir = Path(temp_profile.name) / ("gmb-mobile-profile" if args.mobile else "gmb-profile")
    profile_dir.mkdir(parents=True, exist_ok=True)
    if args.mobile:
        viewport = {"width": 430, "height": 932}
        user_agent = (
            "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1"
        )
    else:
        viewport = {"width": 1365, "height": 920}
        user_agent = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
        )
    context_options = {
        "locale": "zh-TW",
        "timezone_id": "Asia/Taipei",
        "viewport": viewport,
        "user_agent": user_agent,
        "is_mobile": args.mobile,
        "has_touch": args.mobile,
    }
    launch_options = {
        "headless": not args.headed,
        "args": ["--disable-blink-features=AutomationControlled", "--lang=zh-TW"],
    }

    async with async_playwright() as playwright:
        browser = None
        if args.fresh_profile:
            browser = await playwright.chromium.launch(**launch_options)
            context = await browser.new_context(**context_options)
        else:
            context = await playwright.chromium.launch_persistent_context(
                str(profile_dir),
                **launch_options,
                **context_options,
            )
        if not args.allow_heavy_resources:
            await install_low_resource_routes(context)
        try:
            for index, store in enumerate(targets, start=1):
                print(f"{index}/{len(targets)} checking {store.get('storeId')} {store.get('storeName')}", flush=True)
                try:
                    checked = await asyncio.wait_for(
                        audit_store_by_name(
                            context,
                            dict(store),
                            "茶之魔手",
                            ["茶之魔手", "茶的魔手", "茶の魔手", "茶魔", "Tea Magic Hand"],
                            args.attempts,
                            args.single_search_target,
                            args.prefer_stored_gmb,
                            args.maps_first,
                        ),
                        timeout=args.per_store_timeout,
                    )
                except asyncio.TimeoutError:
                    checked = dict(store)
                    checked["gmbOrderingStatus"] = "unavailable_or_blocked"
                    checked["manualReviewReason"] = (
                        f"Named GMB and Google Order audit timed out after {args.per_store_timeout}s; "
                        "kept as a coverage gap, not as no-ordering evidence."
                    )
                    checked["gmbSignals"] = {
                        **(checked.get("gmbSignals") or {}),
                        "checkedAt": NOW,
                        "checkMethod": "teamagichand_named_gmb_match_recheck",
                        "matchQuality": "timed_out",
                        "notes": checked["manualReviewReason"],
                    }
                checked = preserve_user_confirmed_gmb_evidence(store, checked)
                gmb_links_from_claims(checked)
                updated_by_id[checked["storeId"]] = checked
                payload["stores"] = [updated_by_id.get(item["storeId"], item) for item in stores]
                summary = write_current_outputs(payload, previous_summary)
                print(
                    json.dumps(
                        {
                            "storeId": checked.get("storeId"),
                            "status": checked.get("gmbOrderingStatus"),
                            "gmbStatus": checked.get("gmbStatus"),
                            "hasGmb": checked.get("hasGmbOrderingSystem"),
                            "pickup": checked.get("gmbPickupProviders"),
                            "delivery": checked.get("gmbDeliveryProviders"),
                            "statusCounts": summary.get("gmbOrderingStatusCounts"),
                        },
                        ensure_ascii=False,
                    ),
                    flush=True,
                )
                await asyncio.sleep(random.uniform(1.5, 3.5))
        finally:
            await context.close()
            if browser:
                await browser.close()
            temp_profile.cleanup()

    payload["stores"] = [updated_by_id.get(store["storeId"], store) for store in stores]
    summary = write_current_outputs(payload, previous_summary)
    print(
        json.dumps(
            {
                "officialStoreCount": summary["officialStoreCount"],
                "gmbOrderingSystemCount": summary["gmbOrderingSystemCount"],
                "gmbCoverageGapCount": summary["gmbCoverageGapCount"],
                "gmbSystemCounts": summary["gmbSystemCounts"],
                "gmbPickupSystemCounts": summary["gmbPickupSystemCounts"],
                "gmbDeliverySystemCounts": summary["gmbDeliverySystemCounts"],
                "gmbOrderingStatusCounts": summary["gmbOrderingStatusCounts"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
