from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import sys
from datetime import datetime, timezone
from pathlib import Path

from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = ROOT / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

from build_coco_analysis import build_summary, write_outputs  # noqa: E402
from recheck_named_gmb_match import audit_store_by_name  # noqa: E402


BRAND_ROOT = ROOT / "coco"
DATA = BRAND_ROOT / "data"
STORES_PATH = DATA / "stores.json"
SUMMARY_PATH = DATA / "summary.json"
AUDIT_PATH = DATA / "gmb_named_audit.json"
NOW = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_payload() -> dict:
    return json.loads(STORES_PATH.read_text(encoding="utf-8-sig"))


def load_summary() -> dict:
    return json.loads(SUMMARY_PATH.read_text(encoding="utf-8-sig"))


def stores_from_payload(payload: dict) -> list[dict]:
    return payload["stores"] if isinstance(payload, dict) and "stores" in payload else payload


def build_preserving_platform_audit(stores: list[dict], previous_summary: dict) -> dict:
    platform = previous_summary.get("platformDirectAudit") or {}
    summary = build_summary(
        stores,
        int((platform.get("Nidin") or {}).get("platformStoreCount") or len(stores)),
        platform.get("QuickClick") or {},
        {
            "Uber Eats": platform.get("Uber Eats") or {},
            "foodpanda": platform.get("foodpanda") or {},
        },
    )
    if platform.get("LINE"):
        summary.setdefault("platformDirectAudit", {})["LINE"] = platform["LINE"]
    return summary


def save_audit_rows(stores: list[dict]) -> None:
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
    summary = build_preserving_platform_audit(stores, previous_summary)
    write_outputs(stores, summary)
    save_audit_rows(stores)
    return summary


def select_targets(stores: list[dict], args: argparse.Namespace) -> list[dict]:
    if args.ids:
        wanted = set(args.ids)
        return [store for store in stores if store.get("storeId") in wanted]
    candidates = stores
    if getattr(args, "status", ""):
        statuses = {item.strip() for item in args.status.split(",") if item.strip()}
        candidates = [store for store in candidates if store.get("gmbOrderingStatus") in statuses]
    if args.only_pending:
        candidates = [
            store
            for store in stores
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
    if args.start:
        candidates = candidates[args.start :]
    if args.limit:
        candidates = candidates[: args.limit]
    return candidates


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
    args = parser.parse_args()

    payload = load_payload()
    previous_summary = load_summary()
    stores = stores_from_payload(payload)
    targets = select_targets(stores, args)
    updated_by_id: dict[str, dict] = {}

    os.environ["BRAND_ANALYSIS_REPORT_ROOT"] = str(BRAND_ROOT)
    profile_dir = DATA / (".gmb-coco-mobile-profile" if args.mobile else ".gmb-coco-profile")
    profile_dir.mkdir(exist_ok=True)
    if args.mobile:
        viewport = {"width": 430, "height": 932}
        user_agent = (
            "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 "
            "Mobile/15E148 Safari/604.1"
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
        try:
            for index, store in enumerate(targets, start=1):
                print(f"{index}/{len(targets)} checking {store.get('storeId')} {store.get('storeName')}", flush=True)
                try:
                    checked = await asyncio.wait_for(
                        audit_store_by_name(
                            context,
                            dict(store),
                            "CoCo都可",
                            ["CoCo都可", "CoCo", "都可"],
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
                        "checkMethod": "coco_named_gmb_match_recheck",
                        "matchQuality": "timed_out",
                        "notes": checked["manualReviewReason"],
                    }
                if (
                    args.single_search_target
                    and store.get("gmbOrderingStatus") == "unavailable_or_blocked"
                    and checked.get("gmbOrderingStatus")
                    in {"no_gmb_order_button", "no_gmb_profile_match", "not_found"}
                ):
                    checked["gmbOrderingStatus"] = "unavailable_or_blocked"
                    checked["hasGmbOrderingSystem"] = False
                    checked["gmbPickupProviders"] = []
                    checked["gmbDeliveryProviders"] = []
                    checked["manualReviewReason"] = (
                        "Single-target Google Search fallback did not confirm Google Order providers; "
                        "kept as a coverage gap instead of treating it as no-button or no-GMB evidence."
                    )
                    checked["gmbSignals"] = {
                        **(checked.get("gmbSignals") or {}),
                        "checkedAt": NOW,
                        "checkMethod": "coco_single_search_target_fallback",
                        "fallbackDowngradedToCoverageGap": True,
                        "notes": checked["manualReviewReason"],
                    }
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
                await asyncio.sleep(random.uniform(1.8, 4.5))
        finally:
            await context.close()
            if browser:
                await browser.close()

    payload["stores"] = [updated_by_id.get(store["storeId"], store) for store in stores]
    summary = write_current_outputs(payload, previous_summary)
    print(
        json.dumps(
            {
                "officialStoreCount": summary.get("officialStoreCount"),
                "gmbFoundCount": summary.get("gmbFoundCount"),
                "gmbOrderingSystemCount": summary.get("gmbOrderingSystemCount"),
                "gmbCoverageGapCount": summary.get("gmbCoverageGapCount"),
                "gmbSystemCounts": summary.get("gmbSystemCounts"),
                "gmbOrderingStatusCounts": summary.get("gmbOrderingStatusCounts"),
            },
            ensure_ascii=False,
            indent=2,
        ),
        flush=True,
    )


if __name__ == "__main__":
    asyncio.run(main())
