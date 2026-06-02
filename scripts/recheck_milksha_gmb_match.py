from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import re
import sys
from datetime import date
from pathlib import Path
from urllib.parse import quote_plus


os.environ.setdefault(
    "BRAND_ANALYSIS_REPORT_ROOT",
    str(Path(__file__).resolve().parents[1] / "milksha"),
)

sys.path.insert(0, str(Path(__file__).resolve().parent))

from playwright.async_api import TimeoutError as PlaywrightTimeoutError  # noqa: E402
from playwright.async_api import async_playwright  # noqa: E402

from build_milksha_analysis import DATA, build_summary, write_csv  # noqa: E402
from human_gmb_order_recheck import human_settle, inspect_order_flow  # noqa: E402
from strict_gmb_blue_button_audit import apply_result, clear_gmb_claims  # noqa: E402


STORES_PATH = DATA / "stores.json"
SUMMARY_PATH = DATA / "summary.json"

ADDRESS_PAGE_RE = re.compile(r"google\.(?:com|com\.tw)/maps/place/(?:\d{3,5}|[^/@]*%E|[^/@]*號)", re.I)
ORDER_TEXTS = ("線上點餐", "點餐外帶", "點餐外送", "Order online")


def clean_text(value: str) -> str:
    return re.sub(r"\s+", "", re.sub(r"[❄️★☆()（）\[\]【】]", "", value or "")).lower()


def store_name_terms(store: dict) -> list[str]:
    raw = store.get("storeName") or ""
    cleaned = re.sub(r"[❄️★☆]", "", raw)
    cleaned = re.sub(r"^迷客夏\s*", "", cleaned)
    cleaned = re.sub(r"^Milksha\s*", "", cleaned, flags=re.I)
    terms = [cleaned, raw, f"迷客夏Milksha {cleaned}", f"迷客夏 {cleaned}", f"Milksha {cleaned}"]
    return [term.strip() for term in terms if term.strip()]


def district_from_address(address: str) -> str:
    match = re.search(r"([\u4e00-\u9fff]{1,4}[區鄉鎮市])", address or "")
    return match.group(1) if match else ""


def query_for(store: dict) -> str:
    name = re.sub(r"[❄️★☆]", "", store.get("storeName") or "").strip()
    address = re.sub(r"^\s*\d{3,5}\s*", "", store.get("address") or "").strip()
    return f"迷客夏 Milksha {name} {address}".strip()


def body_has_name_match(text: str, store: dict) -> bool:
    compact = clean_text(text)
    district = clean_text(district_from_address(store.get("address") or ""))
    for term in store_name_terms(store):
        term_compact = clean_text(term)
        if term_compact and term_compact in compact:
            return True
    branch = clean_text(re.sub(r"[❄️★☆]", "", store.get("storeName") or ""))
    branch = branch.replace("迷客夏", "").replace("milksha", "")
    if branch and branch in compact and ("迷客夏" in text or "Milksha" in text):
        return True
    return bool(district and district in compact and ("迷客夏" in text or "Milksha" in text))


async def body_text(page) -> str:
    try:
        return await page.locator("body").inner_text(timeout=9000)
    except Exception:
        return ""


async def click_matching_place_card(page, store: dict) -> bool:
    terms = store_name_terms(store)
    clicked = await page.evaluate(
        r"""
        ({ terms }) => {
            const normalize = value => (value || '').replace(/\s+/g, '').trim().toLowerCase();
            const clean = value => normalize(value).replace(/[❄️★☆()（）\\[\\]【】]/g, '');
            const wanted = terms.map(clean).filter(Boolean);
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
                .filter(item => item.text.includes('迷客夏') || item.text.includes('milksha'))
                .filter(item => wanted.some(term => item.text.includes(term) || term.includes(item.text.slice(0, Math.min(item.text.length, 18)))))
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
        {"terms": terms},
    )
    if clicked:
        await page.wait_for_timeout(2500)
        await human_settle(page)
    return bool(clicked)


async def resolve_named_gmb(page, store: dict) -> tuple[bool, str]:
    text = await body_text(page)
    is_address_page = bool(ADDRESS_PAGE_RE.search(page.url)) or (
        not body_has_name_match(text, store) and "新增遺漏的地點" in text
    )
    if is_address_page:
        clicked = await click_matching_place_card(page, store)
        if clicked:
            text = await body_text(page)
    has_name = body_has_name_match(text, store)
    if not has_name:
        return False, "No highly similar store-name GMB profile was visible; address-only page is not counted."
    if "新增遺漏的地點" in text and not any(marker in text for marker in ("Google 評論", "評論", "點餐", "網站", "致電")):
        return False, "Google page still looks like an address-only place, not a named store profile."
    return True, ""


def no_named_gmb_result(store: dict, reason: str, history: list[dict]) -> dict:
    clear_gmb_claims(store)
    store["sourceCoverage"] = {
        **(store.get("sourceCoverage") or {}),
        "googleFound": bool((store.get("sourceCoverage") or {}).get("googleFound")),
        "gmbFound": False,
    }
    store["gmbStatus"] = "not_found"
    store["gmbOrderingStatus"] = "no_gmb_profile_match"
    store["manualReviewReason"] = reason
    store["gmbSignals"] = {
        "buttonDetected": False,
        "providersParsed": False,
        "panelUrl": "",
        "checkedAt": date.today().isoformat(),
        "checkMethod": "milksha_named_gmb_match_recheck",
        "attemptHistory": history,
        "notes": reason,
        "matchQuality": "missing_named_gmb",
    }
    return store


def update_match_signals(store: dict, result: dict, profile_url: str, history: list[dict]) -> dict:
    previous = store.get("gmbSignals") or {}
    store["gmbUrl"] = profile_url
    store["gmbSignals"] = {
        **previous,
        **(store.get("gmbSignals") or {}),
        "matchQuality": "named_gmb_profile",
        "matchedGmbUrl": profile_url,
        "addressOnlyPageRejected": True,
        "attemptHistory": history or (store.get("gmbSignals") or {}).get("attemptHistory", []),
    }
    if result.get("status") == "no_gmb_order_button":
        store["manualReviewReason"] = (
            "Named GMB profile was verified after rejecting an address-only Maps page, "
            "but no blue Google Order entry was visible during the re-check."
        )
    return store


async def audit_store_by_name(context, store: dict, attempts: int) -> dict:
    page = await context.new_page()
    history: list[dict] = []
    targets = [
        ("googleSearch", f"https://www.google.com/search?q={quote_plus(query_for(store))}&hl=zh-TW"),
        ("mapsSearch", f"https://www.google.com/maps/search/?api=1&query={quote_plus(query_for(store))}"),
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
                result = None
                profile_url = ""
                try:
                    await page.goto(target_url, wait_until="domcontentloaded", timeout=45000)
                    await page.wait_for_timeout(2200)
                    await human_settle(page)
                    matched, mismatch = await resolve_named_gmb(page, store)
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
                except Exception as exc:
                    result = {
                        "status": "unavailable_or_blocked",
                        "panelUrl": target_url,
                        "pickupProviders": [],
                        "deliveryProviders": [],
                        "buttonDetected": False,
                        "notes": f"Named GMB match re-check failed: {type(exc).__name__}.",
                    }
                if result is None:
                    continue
                result["checkMethod"] = "milksha_named_gmb_match_recheck"
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
                    best_url = profile_url or page.url
                if result.get("status") == "confirmed":
                    result["attemptHistory"] = history
                    clear_gmb_claims(store)
                    updated = apply_result(store, result)
                    return update_match_signals(updated, result, best_url or profile_url, history)
                await asyncio.sleep(random.uniform(1.4, 3.6))
        if not named_profile_seen:
            reason = mismatch_reasons[-1] if mismatch_reasons else "No highly similar store-name GMB profile was found."
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


def write_outputs(payload: dict) -> dict:
    previous = json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))
    source = previous.get("source") or {}
    summary = build_summary(
        payload["stores"],
        int(source.get("nidinApiStoreCount") or 0),
        int(source.get("nidinMatchedOfficialStoreCount") or 0),
    )
    STORES_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    SUMMARY_PATH.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_csv(payload["stores"])
    return summary


def target_stores(stores: list[dict], args: argparse.Namespace) -> list[dict]:
    if args.ids:
        ids = set(args.ids)
        return [store for store in stores if store.get("storeId") in ids]
    if args.address_place_only:
        return [
            store
            for store in stores
            if store.get("gmbOrderingStatus") in {"no_gmb_order_button", "no_gmb_profile_match"}
            and ADDRESS_PAGE_RE.search(store.get("gmbUrl") or "")
        ]
    statuses = {item.strip() for item in args.status.split(",") if item.strip()}
    return [store for store in stores if store.get("gmbOrderingStatus") in statuses]


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ids", nargs="*", default=[])
    parser.add_argument("--status", default="no_gmb_order_button")
    parser.add_argument("--address-place-only", action="store_true")
    parser.add_argument("--attempts", type=int, default=2)
    parser.add_argument("--per-store-timeout", type=int, default=180)
    parser.add_argument("--headed", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    payload = json.loads(STORES_PATH.read_text(encoding="utf-8"))
    stores = payload["stores"]
    targets = target_stores(stores, args)
    if args.limit:
        targets = targets[: args.limit]

    profile_dir = DATA / ".gmb-milksha-name-profile"
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
                        audit_store_by_name(context, dict(store), args.attempts),
                        timeout=args.per_store_timeout,
                    )
                except asyncio.TimeoutError:
                    updated = dict(store)
                    updated["gmbOrderingStatus"] = "unavailable_or_blocked"
                    if ADDRESS_PAGE_RE.search(updated.get("gmbUrl") or ""):
                        updated["gmbStatus"] = "not_found"
                        updated["sourceCoverage"] = {
                            **(updated.get("sourceCoverage") or {}),
                            "gmbFound": False,
                        }
                    updated["manualReviewReason"] = (
                        f"Named GMB match re-check timed out after {args.per_store_timeout}s; "
                        "kept reviewable instead of counting an address-only page."
                    )
                updated_by_id[updated["storeId"]] = updated
                payload["stores"] = [updated_by_id.get(item["storeId"], item) for item in stores]
                summary = write_outputs(payload)
                print(
                    json.dumps(
                        {
                            "storeId": updated.get("storeId"),
                            "status": updated.get("gmbOrderingStatus"),
                            "gmbStatus": updated.get("gmbStatus"),
                            "hasGmb": updated.get("hasGmbOrderingSystem"),
                            "pickup": updated.get("gmbPickupProviders"),
                            "delivery": updated.get("gmbDeliveryProviders"),
                            "gmbUrl": updated.get("gmbUrl"),
                            "statusCounts": summary["gmbOrderingStatusCounts"],
                        },
                        ensure_ascii=False,
                    ),
                    flush=True,
                )
                await asyncio.sleep(random.uniform(1.8, 4.5))
        finally:
            await context.close()

    payload["stores"] = [updated_by_id.get(store["storeId"], store) for store in stores]
    summary = write_outputs(payload)
    print(
        json.dumps(
            {
                "officialStoreCount": summary["officialStoreCount"],
                "gmbOrderingSystemCount": summary["gmbOrderingSystemCount"],
                "gmbCoverageGapCount": summary["gmbCoverageGapCount"],
                "gmbSystemCounts": summary["gmbSystemCounts"],
                "gmbOrderingStatusCounts": summary["gmbOrderingStatusCounts"],
            },
            ensure_ascii=False,
            indent=2,
        ),
        flush=True,
    )


if __name__ == "__main__":
    asyncio.run(main())
