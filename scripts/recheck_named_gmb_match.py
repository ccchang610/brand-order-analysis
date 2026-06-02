from __future__ import annotations

import argparse
import asyncio
import importlib
import json
import os
import random
import re
import sys
from datetime import date
from pathlib import Path
from urllib.parse import quote_plus


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from playwright.async_api import TimeoutError as PlaywrightTimeoutError  # noqa: E402
from playwright.async_api import async_playwright  # noqa: E402

from human_gmb_order_recheck import human_settle, inspect_order_flow  # noqa: E402
from strict_gmb_blue_button_audit import apply_result, clear_gmb_claims  # noqa: E402


ORDER_GAP_STATUSES = {
    "no_gmb_order_button",
    "button_confirmed_provider_pending",
    "unavailable_or_blocked",
    "needs_manual_review",
    "not_found",
    "no_gmb_profile_match",
}

ADDRESS_ONLY_MARKERS = ("新增遺漏的地點", "加入你的商家", "位於這個地點的專區")


def clean_text(value: str) -> str:
    value = (value or "").replace("臺", "台")
    value = re.sub(r"[❄️★☆()（）\[\]【】｜|:：,，.。/\\-]", "", value)
    return re.sub(r"\s+", "", value).lower()


def branch_tokens(store_name: str, brand_aliases: list[str]) -> list[str]:
    value = re.sub(r"[❄️★☆]", "", store_name or "")
    for alias in brand_aliases:
        value = re.sub(re.escape(alias), "", value, flags=re.I)
    value = re.sub(r"^(CHAGE|Milksha|Plus)\s*", "", value, flags=re.I)
    parts = [value.strip(), store_name.strip()]
    return [part for part in parts if part]


def store_name_terms(store: dict, brand_aliases: list[str]) -> list[str]:
    terms = []
    for token in branch_tokens(store.get("storeName") or "", brand_aliases):
        terms.append(token)
        for alias in brand_aliases:
            terms.append(f"{alias} {token}")
            terms.append(f"{alias}{token}")
    return [term.strip() for term in terms if term and term.strip()]


def district_from_address(address: str) -> str:
    match = re.search(r"([\u4e00-\u9fff]{1,5}[區鄉鎮市])", address or "")
    return match.group(1) if match else ""


def query_for(store: dict, brand_query: str) -> str:
    address = re.sub(r"^\s*\d{3,5}\s*", "", store.get("address") or "").strip()
    return f"{brand_query} {store.get('storeName') or ''} {address}".strip()


def body_has_name_match(text: str, store: dict, brand_aliases: list[str]) -> bool:
    compact = clean_text(text)
    aliases = [clean_text(alias) for alias in brand_aliases if alias.strip()]
    has_brand = any(alias and alias in compact for alias in aliases)
    terms = [clean_text(term) for term in store_name_terms(store, brand_aliases)]
    if any(term and term in compact for term in terms):
        return True
    branch = clean_text(branch_tokens(store.get("storeName") or "", brand_aliases)[0] if branch_tokens(store.get("storeName") or "", brand_aliases) else "")
    district = clean_text(district_from_address(store.get("address") or ""))
    return bool(has_brand and ((branch and branch in compact) or (district and district in compact)))


async def body_text(page) -> str:
    try:
        return await page.locator("body").inner_text(timeout=9000)
    except Exception:
        return ""


async def click_matching_place_card(page, store: dict, brand_aliases: list[str]) -> bool:
    terms = store_name_terms(store, brand_aliases)
    clicked = await page.evaluate(
        r"""
        ({ terms, brandAliases }) => {
            const normalize = value => (value || '').replace(/\s+/g, '').replace(/臺/g, '台').trim().toLowerCase();
            const clean = value => normalize(value).replace(/[❄️★☆()（）\[\]【】｜|:：,，.。/\\-]/g, '');
            const wanted = terms.map(clean).filter(Boolean);
            const brands = brandAliases.map(clean).filter(Boolean);
            const isVisible = el => {
                const rect = el.getBoundingClientRect();
                const style = getComputedStyle(el);
                return rect.width > 24
                    && rect.height > 16
                    && rect.bottom > 0
                    && rect.top < innerHeight
                    && rect.right > 0
                    && rect.left < innerWidth
                    && style.display !== 'none'
                    && style.visibility !== 'hidden'
                    && Number(style.opacity || 1) > 0.2;
            };
            const nodes = [...document.querySelectorAll('a, button, [role="button"], [role="link"], [jsaction], [tabindex]')]
                .filter(isVisible)
                .map(el => ({ el, text: clean(`${el.innerText || el.textContent || ''} ${el.getAttribute('aria-label') || ''}`) }))
                .filter(item => brands.some(brand => item.text.includes(brand)) || wanted.some(term => item.text.includes(term)))
                .filter(item => wanted.some(term => item.text.includes(term)))
                .sort((a, b) => {
                    const ar = a.el.getBoundingClientRect();
                    const br = b.el.getBoundingClientRect();
                    return (ar.top - br.top) || (ar.left - br.left);
                });
            if (!nodes.length) return false;
            nodes[0].el.click();
            return true;
        }
        """,
        {"terms": terms, "brandAliases": brand_aliases},
    )
    if clicked:
        await page.wait_for_timeout(2500)
        await human_settle(page)
    return bool(clicked)


async def resolve_named_gmb(page, store: dict, brand_aliases: list[str]) -> tuple[bool, str]:
    text = await body_text(page)
    is_address_like = any(marker in text for marker in ADDRESS_ONLY_MARKERS) and not body_has_name_match(text, store, brand_aliases)
    if is_address_like:
        clicked = await click_matching_place_card(page, store, brand_aliases)
        if clicked:
            text = await body_text(page)
    if not body_has_name_match(text, store, brand_aliases):
        return False, "No highly similar named GMB profile was visible; address-only or wrong-name pages are not counted."
    if any(marker in text for marker in ("新增遺漏的地點", "加入你的商家")) and not any(marker in text for marker in ("Google 評論", "評論", "點餐", "網站", "致電")):
        return False, "Google page still looks like an address-only place, not a named store profile."
    return True, ""


def no_named_gmb_result(store: dict, reason: str, history: list[dict]) -> dict:
    clear_gmb_claims(store)
    coverage = store.setdefault("sourceCoverage", {})
    coverage["gmbFound"] = False
    coverage["googleFound"] = bool(coverage.get("googleFound"))
    store["gmbStatus"] = "not_found"
    store["gmbOrderingStatus"] = "no_gmb_profile_match"
    store["manualReviewReason"] = reason
    store["gmbSignals"] = {
        "buttonDetected": False,
        "providersParsed": False,
        "panelUrl": "",
        "checkedAt": date.today().isoformat(),
        "checkMethod": "named_gmb_match_recheck",
        "attemptHistory": history,
        "matchQuality": "missing_named_gmb",
        "notes": reason,
    }
    return store


def update_match_signals(store: dict, result: dict, profile_url: str, history: list[dict]) -> dict:
    store["gmbUrl"] = profile_url or store.get("gmbUrl") or ""
    signals = store.get("gmbSignals") or {}
    store["gmbSignals"] = {
        **signals,
        "matchQuality": "named_gmb_profile",
        "matchedGmbUrl": store["gmbUrl"],
        "addressOnlyPageRejected": True,
        "attemptHistory": history or signals.get("attemptHistory", []),
    }
    if result.get("status") == "no_gmb_order_button":
        store["manualReviewReason"] = (
            "Named GMB profile was verified after rejecting address-only or embedded Maps leads, "
            "but no blue Google Order entry was visible during the re-check."
        )
    return store


async def audit_store_by_name(context, store: dict, brand_query: str, brand_aliases: list[str], attempts: int) -> dict:
    page = await context.new_page()
    history: list[dict] = []
    targets = [
        ("googleSearch", f"https://www.google.com/search?q={quote_plus(query_for(store, brand_query))}&hl=zh-TW"),
        ("mapsSearch", f"https://www.google.com/maps/search/?api=1&query={quote_plus(query_for(store, brand_query))}"),
    ]
    if store.get("gmbUrl"):
        targets.append(("storedGmbUrl", store["gmbUrl"]))
    best = None
    best_url = ""
    named_profile_seen = False
    mismatch_reasons = []
    try:
        for target_label, target_url in targets:
            for attempt in range(1, max(1, attempts) + 1):
                try:
                    await page.goto(target_url, wait_until="domcontentloaded", timeout=45000)
                    await page.wait_for_timeout(2200)
                    await human_settle(page)
                    matched, mismatch = await resolve_named_gmb(page, store, brand_aliases)
                    if not matched:
                        mismatch_reasons.append(mismatch)
                        history.append(
                            {
                                "target": target_label,
                                "attempt": attempt,
                                "status": "name_mismatch",
                                "buttonDetected": False,
                                "providersParsed": False,
                            }
                        )
                        continue
                    named_profile_seen = True
                    profile_url = page.url
                    result = await inspect_order_flow(page)
                except PlaywrightTimeoutError:
                    result = {
                        "status": "unavailable_or_blocked",
                        "panelUrl": target_url,
                        "pickupProviders": [],
                        "deliveryProviders": [],
                        "buttonDetected": False,
                        "notes": "Timed out during named GMB match re-check.",
                    }
                    profile_url = page.url
                except Exception as exc:
                    result = {
                        "status": "unavailable_or_blocked",
                        "panelUrl": target_url,
                        "pickupProviders": [],
                        "deliveryProviders": [],
                        "buttonDetected": False,
                        "notes": f"Named GMB match re-check failed: {type(exc).__name__}.",
                    }
                    profile_url = page.url
                result["checkMethod"] = "named_gmb_match_recheck"
                result["attemptCount"] = len(history) + 1
                result["maxAttempts"] = attempts
                result["targetUrl"] = target_url
                history.append(
                    {
                        "target": target_label,
                        "attempt": attempt,
                        "status": result.get("status"),
                        "buttonDetected": bool(result.get("buttonDetected")),
                        "providersParsed": bool(result.get("pickupProviders") or result.get("deliveryProviders")),
                    }
                )
                rank = {"confirmed": 4, "button_confirmed_provider_pending": 3, "unavailable_or_blocked": 2, "no_gmb_order_button": 1}
                if best is None or rank.get(result.get("status"), 0) > rank.get(best.get("status"), 0):
                    best = result
                    best_url = profile_url
                if result.get("status") == "confirmed":
                    result["attemptHistory"] = history
                    clear_gmb_claims(store)
                    updated = apply_result(store, result)
                    return update_match_signals(updated, result, best_url, history)
                await asyncio.sleep(random.uniform(1.4, 3.6))
        if not named_profile_seen:
            reason = mismatch_reasons[-1] if mismatch_reasons else "No highly similar named GMB profile was found."
            return no_named_gmb_result(store, reason, history)
        if best:
            best["attemptHistory"] = history
            best["attemptCount"] = len(history)
            best["maxAttempts"] = attempts
            clear_gmb_claims(store)
            updated = apply_result(store, best)
            return update_match_signals(updated, best, best_url, history)
        return store
    finally:
        await page.close()


def load_payload(brand_root: Path) -> dict:
    return json.loads((brand_root / "data" / "stores.json").read_text(encoding="utf-8"))


def stores_from_payload(payload: dict) -> list[dict]:
    return payload["stores"] if isinstance(payload, dict) and "stores" in payload else payload


def write_brand_outputs(brand_slug: str, brand_root: Path, payload: dict) -> dict:
    stores = stores_from_payload(payload)
    if brand_slug == "daming":
        module = importlib.import_module("build_daming_analysis")
        summary = module.make_summary(stores)
        module.write_data(stores, summary)
        return summary
    if brand_slug == "chage":
        module = importlib.import_module("build_chage_analysis")
        summary = module.build_summary(stores)
        module.write_outputs(stores, summary)
        return summary
    if brand_slug == "milksha":
        module = importlib.import_module("build_milksha_analysis")
        previous = json.loads((brand_root / "data" / "summary.json").read_text(encoding="utf-8"))
        source = previous.get("source") or {}
        summary = module.build_summary(
            stores,
            int(source.get("nidinApiStoreCount") or 0),
            int(source.get("nidinMatchedOfficialStoreCount") or 0),
        )
        (brand_root / "data" / "stores.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (brand_root / "data" / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        module.write_csv(stores)
        return summary
    previous = json.loads((brand_root / "data" / "summary.json").read_text(encoding="utf-8"))
    (brand_root / "data" / "stores.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return previous


def select_targets(stores: list[dict], args: argparse.Namespace) -> list[dict]:
    if args.ids:
        ids = set(args.ids)
        return [store for store in stores if store.get("storeId") in ids]
    statuses = {item.strip() for item in args.status.split(",") if item.strip()}
    targets = [
        store
        for store in stores
        if store.get("gmbOrderingStatus") in statuses
        or not (store.get("sourceCoverage") or {}).get("gmbFound")
        or store.get("gmbStatus") in {"not_found", "duplicate_or_ambiguous"}
    ]
    return targets


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--brand-root", required=True)
    parser.add_argument("--brand-slug", default="")
    parser.add_argument("--brand-query", required=True)
    parser.add_argument("--brand-alias", action="append", default=[])
    parser.add_argument("--ids", nargs="*", default=[])
    parser.add_argument("--status", default=",".join(sorted(ORDER_GAP_STATUSES)))
    parser.add_argument("--attempts", type=int, default=2)
    parser.add_argument("--per-store-timeout", type=int, default=180)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--headed", action="store_true")
    args = parser.parse_args()

    brand_root = (REPO_ROOT / args.brand_root).resolve()
    brand_slug = args.brand_slug or brand_root.name
    os.environ["BRAND_ANALYSIS_REPORT_ROOT"] = str(brand_root)
    brand_aliases = args.brand_alias or [args.brand_query]

    payload = load_payload(brand_root)
    stores = stores_from_payload(payload)
    targets = select_targets(stores, args)
    if args.limit:
        targets = targets[: args.limit]

    profile_dir = brand_root / "data" / ".gmb-named-profile"
    profile_dir.mkdir(exist_ok=True)
    context_options = {
        "locale": "zh-TW",
        "timezone_id": "Asia/Taipei",
        "viewport": {"width": 1365, "height": 920},
        "user_agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
        ),
    }
    launch_options = {
        "headless": not args.headed,
        "args": ["--disable-blink-features=AutomationControlled", "--lang=zh-TW"],
    }

    async with async_playwright() as playwright:
        context = await playwright.chromium.launch_persistent_context(
            str(profile_dir),
            **launch_options,
            **context_options,
        )
        try:
            updated_by_id = {}
            for index, store in enumerate(targets, start=1):
                print(f"{index}/{len(targets)} matching {store.get('storeId')} {store.get('storeName')}", flush=True)
                try:
                    updated = await asyncio.wait_for(
                        audit_store_by_name(context, dict(store), args.brand_query, brand_aliases, args.attempts),
                        timeout=args.per_store_timeout,
                    )
                except asyncio.TimeoutError:
                    updated = dict(store)
                    updated["gmbOrderingStatus"] = "unavailable_or_blocked"
                    updated["manualReviewReason"] = (
                        f"Named GMB match re-check timed out after {args.per_store_timeout}s; "
                        "kept reviewable instead of counting an address-only or wrong-name page."
                    )
                    updated["gmbSignals"] = {
                        **(updated.get("gmbSignals") or {}),
                        "checkedAt": date.today().isoformat(),
                        "checkMethod": "named_gmb_match_recheck",
                        "matchQuality": (updated.get("gmbSignals") or {}).get("matchQuality") or "timed_out",
                        "notes": updated["manualReviewReason"],
                    }
                updated_by_id[updated["storeId"]] = updated
                payload["stores"] = [updated_by_id.get(item["storeId"], item) for item in stores]
                summary = write_brand_outputs(brand_slug, brand_root, payload)
                print(
                    json.dumps(
                        {
                            "storeId": updated.get("storeId"),
                            "status": updated.get("gmbOrderingStatus"),
                            "gmbStatus": updated.get("gmbStatus"),
                            "hasGmb": updated.get("hasGmbOrderingSystem"),
                            "pickup": updated.get("gmbPickupProviders"),
                            "delivery": updated.get("gmbDeliveryProviders"),
                            "statusCounts": summary.get("gmbOrderingStatusCounts"),
                        },
                        ensure_ascii=False,
                    ),
                    flush=True,
                )
                await asyncio.sleep(random.uniform(1.8, 4.5))
        finally:
            await context.close()

    payload["stores"] = [updated_by_id.get(store["storeId"], store) for store in stores]
    summary = write_brand_outputs(brand_slug, brand_root, payload)
    print(
        json.dumps(
            {
                "officialStoreCount": summary.get("officialStoreCount"),
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
