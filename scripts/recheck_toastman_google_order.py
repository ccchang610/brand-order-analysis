from __future__ import annotations

import asyncio
import json
import re
from datetime import date
from pathlib import Path
from urllib.parse import quote_plus

from playwright.async_api import async_playwright

from build_toastman_analysis import active_stores, rebuild_summary, write_outputs


ROOT = Path(__file__).resolve().parents[1]
BRAND_ROOT = ROOT / "toastman"
STORES_PATH = BRAND_ROOT / "data" / "stores.json"
CHECKED_AT = date.today().isoformat()

ORDER_TEXTS = [
    "線上訂餐",
    "訂餐",
    "下單",
    "立即訂購",
    "立即點餐",
    "自取",
    "外送",
    "外帶",
    "Order",
    "Pickup",
    "Delivery",
]

MODE_LABELS = [
    ("自取", "pickup"),
    ("外帶", "pickup"),
    ("取餐", "pickup"),
    ("外送", "delivery"),
    ("運送", "delivery"),
    ("Delivery", "delivery"),
    ("Pickup", "pickup"),
]


def google_search_url(query: str) -> str:
    return "https://www.google.com/search?hl=zh-TW&gl=tw&pws=0&q=" + quote_plus(query)


def maps_search_url(query: str) -> str:
    return "https://www.google.com/maps/search/" + quote_plus(query) + "?hl=zh-TW&gl=tw"


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def provider_from_text(value: str) -> list[str]:
    text = (value or "").lower()
    providers = []
    checks = [
        ("nidin", "Nidin"),
        ("order.nidin.shop", "Nidin"),
        ("nidin.shop", "Nidin"),
        ("uber eats", "Uber Eats"),
        ("ubereats", "Uber Eats"),
        ("foodpanda", "foodpanda"),
        ("quickclick", "QuickClick"),
        ("快一點", "QuickClick"),
    ]
    for needle, provider in checks:
        if needle in text and provider not in providers:
            providers.append(provider)
    return providers


def platform_from_link(href: str, label: str = "") -> str:
    text = f"{href} {label}".lower()
    if "foodpanda" in text:
        return "foodpanda"
    if "ubereats" in text or "uber eats" in text:
        return "Uber Eats"
    if "nidin" in text:
        return "Nidin"
    if "lin.ee" in text or "line.me" in text:
        return "LINE"
    if "quickclick" in text or "快一點" in text:
        return "QuickClick"
    if "instagram" in text:
        return "Instagram"
    return ""


def make_query(store: dict) -> str:
    parts = [
        "吐司男",
        store.get("seedName") or store.get("storeName") or "",
        store.get("address") or "",
    ]
    return " ".join(part for part in parts if part)


async def accept_consent(page) -> None:
    for label in ["全部接受", "我同意", "同意", "Accept all", "I agree"]:
        try:
            await page.get_by_text(label, exact=False).first.click(timeout=900)
            await page.wait_for_timeout(800)
            return
        except Exception:
            pass


async def collect_clickables(page) -> list[dict]:
    return await page.evaluate(
        r"""
        () => [...document.querySelectorAll('a,button,[role="button"]')].map((el) => {
          const text = (el.innerText || el.textContent || '').replace(/\s+/g, ' ').trim();
          const aria = el.getAttribute('aria-label') || '';
          const href = el.href || '';
          const rect = el.getBoundingClientRect();
          return {
            text,
            aria,
            href,
            visible: rect.width > 0 && rect.height > 0,
            x: rect.x,
            y: rect.y
          };
        }).filter((item) => item.text || item.aria || item.href)
        """
    )


async def click_order_entry(page) -> tuple[bool, str, str]:
    items = await collect_clickables(page)
    searchviewer = [item for item in items if "searchviewer" in item.get("href", "")]
    if searchviewer:
        href = searchviewer[0]["href"]
        await page.goto(href, wait_until="domcontentloaded", timeout=45000)
        await page.wait_for_timeout(3500)
        return True, page.url, "searchviewer_href"

    for item in items:
        label = f"{item.get('aria', '')} {item.get('text', '')}"
        if not item.get("visible"):
            continue
        if any(word.lower() in label.lower() for word in ORDER_TEXTS):
            try:
                target_text = clean_text(item.get("text") or item.get("aria") or "")
                if target_text:
                    await page.get_by_text(target_text, exact=False).first.click(timeout=2000)
                else:
                    await page.mouse.click(item["x"] + 4, item["y"] + 4)
                await page.wait_for_timeout(4200)
                if "searchviewer" in page.url:
                    return True, page.url, "order_text_click"
                after_items = await collect_clickables(page)
                for after in after_items:
                    if "searchviewer" in after.get("href", ""):
                        await page.goto(after["href"], wait_until="domcontentloaded", timeout=45000)
                        await page.wait_for_timeout(3200)
                        return True, page.url, "post_click_searchviewer_href"
                body = await page.locator("body").inner_text(timeout=10000)
                if any(provider in body.lower() for provider in ["foodpanda", "ubereats", "uber eats", "nidin"]):
                    return True, page.url, "provider_text_after_click"
            except Exception:
                continue
    return False, "", "no_order_entry_visible"


async def parse_order_panel(page, panel_url: str) -> dict:
    result = {
        "panelUrl": panel_url or page.url,
        "providers": {"pickup": [], "delivery": [], "unknown": []},
        "links": [],
        "providersParsed": False,
    }

    modes_clicked = set()
    for label, mode in MODE_LABELS:
        try:
            await page.get_by_text(label, exact=False).first.click(timeout=1600)
            modes_clicked.add(mode)
            await page.wait_for_timeout(2500)
        except Exception:
            pass
        try:
            body = await page.locator("body").inner_text(timeout=10000)
        except Exception:
            body = ""
        for provider in provider_from_text(body):
            if provider not in result["providers"][mode]:
                result["providers"][mode].append(provider)
                result["providersParsed"] = True
        links = await page.evaluate(
            r"""
            () => [...document.querySelectorAll('a')].map((a) => ({
              href: a.href || '',
              text: (a.innerText || a.textContent || '').replace(/\s+/g, ' ').trim()
            })).filter((item) => item.href)
            """
        )
        for link in links:
            platform = platform_from_link(link.get("href", ""), link.get("text", ""))
            if not platform:
                continue
            result["links"].append(
                {
                    "platform": platform,
                    "kind": "marketplace" if platform in {"foodpanda", "Uber Eats", "Nidin", "QuickClick"} else "order_link",
                    "sourceType": "gmb_order_panel",
                    "orderMode": [mode],
                    "label": clean_text(link.get("text") or platform),
                    "href": link.get("href", ""),
                    "panelUrl": result["panelUrl"],
                    "observedAt": CHECKED_AT,
                    "confidence": "confirmed",
                }
            )

    if not modes_clicked:
        try:
            body = await page.locator("body").inner_text(timeout=10000)
        except Exception:
            body = ""
        for provider in provider_from_text(body):
            if provider not in result["providers"]["unknown"]:
                result["providers"]["unknown"].append(provider)
                result["providersParsed"] = True

    unique_links = {}
    for link in result["links"]:
        key = (link["platform"], link["href"])
        if key in unique_links:
            unique_links[key]["orderMode"] = sorted(set(unique_links[key]["orderMode"]) | set(link["orderMode"]))
        else:
            unique_links[key] = link
    result["links"] = list(unique_links.values())
    return result


async def attempt_target(page, store: dict, target_name: str, url: str, attempt_no: int) -> dict:
    attempt = {
        "attempt": attempt_no,
        "target": target_name,
        "url": url,
        "status": "started",
        "buttonDetected": False,
        "providersParsed": False,
        "pickupProviders": [],
        "deliveryProviders": [],
        "unknownProviders": [],
        "panelUrl": "",
    }
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(3800)
        await accept_consent(page)
        await page.mouse.move(420, 360)
        await page.mouse.wheel(0, 360)
        await page.wait_for_timeout(1400)
        body = await page.locator("body").inner_text(timeout=12000)
        if "/sorry/" in page.url or "unusual traffic" in body.lower():
            attempt["status"] = "blocked"
            return attempt
        button_detected, panel_url, click_method = await click_order_entry(page)
        attempt["buttonDetected"] = button_detected
        attempt["clickMethod"] = click_method
        if not button_detected:
            attempt["status"] = "no_button"
            return attempt
        attempt["panelUrl"] = panel_url or page.url
        parsed = await parse_order_panel(page, attempt["panelUrl"])
        attempt["providersParsed"] = parsed["providersParsed"]
        attempt["pickupProviders"] = parsed["providers"]["pickup"]
        attempt["deliveryProviders"] = parsed["providers"]["delivery"]
        attempt["unknownProviders"] = parsed["providers"]["unknown"]
        attempt["gmbOrderLinks"] = parsed["links"]
        attempt["status"] = "confirmed" if parsed["providersParsed"] else "button_confirmed_provider_pending"
        return attempt
    except Exception as exc:
        attempt["status"] = "error"
        attempt["error"] = str(exc)
        return attempt


def remove_gmb_claims(store: dict) -> None:
    store["orderingSystems"] = [claim for claim in store.get("orderingSystems", []) if claim.get("sourceType") != "gmb"]


def add_gmb_claim(store: dict, system: str, mode: str, panel_url: str) -> None:
    if not system:
        return
    for claim in store.get("orderingSystems", []):
        if claim.get("sourceType") == "gmb" and claim.get("system") == system and mode in claim.get("orderMode", []):
            return
    store.setdefault("orderingSystems", []).append(
        {
            "system": system,
            "sourceType": "gmb",
            "orderMode": [mode],
            "evidenceUrl": panel_url,
            "label": f"Google Order {mode}",
            "confidence": "confirmed",
        }
    )


def apply_recheck(store: dict, attempts: list[dict]) -> None:
    remove_gmb_claims(store)
    best = next((attempt for attempt in attempts if attempt.get("providersParsed")), None)
    pending = next((attempt for attempt in attempts if attempt.get("buttonDetected")), None)
    blocked = any(attempt.get("status") == "blocked" for attempt in attempts)

    panel_url = ""
    links = []
    pickup = []
    delivery = []
    unknown = []

    if best:
        panel_url = best.get("panelUrl", "")
        pickup = best.get("pickupProviders", [])
        delivery = best.get("deliveryProviders", [])
        unknown = best.get("unknownProviders", [])
        links = best.get("gmbOrderLinks", [])
        for system in pickup:
            add_gmb_claim(store, system, "pickup", panel_url)
        for system in delivery:
            add_gmb_claim(store, system, "delivery", panel_url)
        for system in unknown:
            add_gmb_claim(store, system, "unknown", panel_url)
        store["gmbOrderingStatus"] = "confirmed"
        store["gmbStatus"] = "confirmed"
        store["sourceCoverage"]["gmbFound"] = True
        store["sourceCoverage"]["googleFound"] = True
        store["hasGmbOrderingSystem"] = True
        store["manualReviewReason"] = ""
    elif pending:
        panel_url = pending.get("panelUrl", "")
        links = pending.get("gmbOrderLinks", [])
        store["gmbOrderingStatus"] = "button_confirmed_provider_pending"
        store["gmbStatus"] = "confirmed"
        store["sourceCoverage"]["gmbFound"] = True
        store["sourceCoverage"]["googleFound"] = True
        store["hasGmbOrderingSystem"] = True
        store["manualReviewReason"] = "Google Order entry was confirmed in re-check, but provider rows were not safely parsed."
    elif blocked:
        store["gmbOrderingStatus"] = "unavailable_or_blocked"
        store["hasGmbOrderingSystem"] = False
        store["manualReviewReason"] = "Google blocked or destabilized the re-check; not treated as proof of no Google Order entry."
    else:
        store["gmbOrderingStatus"] = "no_gmb_order_button" if store.get("gmbStatus") == "confirmed" else "needs_manual_review"
        store["hasGmbOrderingSystem"] = False
        store["manualReviewReason"] = "Multi-attempt desktop/mobile Google Search and Maps re-check did not expose a readable Google Order entry."

    has_gmb_provider = any(claim.get("sourceType") == "gmb" for claim in store.get("orderingSystems", []))
    store["gmbOrderPanelUrl"] = panel_url
    store["gmbPickupProviders"] = pickup
    store["gmbDeliveryProviders"] = delivery
    store["gmbOrderLinks"] = links
    store["hasAnyOrderingSystem"] = bool(store.get("orderingSystems"))
    store["sourceCoverage"]["thirdPartyFound"] = store["hasAnyOrderingSystem"]
    store["checkedAt"] = CHECKED_AT
    store["gmbSignals"] = {
        "buttonDetected": bool(pending),
        "providersParsed": has_gmb_provider,
        "attemptCount": len(attempts),
        "maxAttempts": 4,
        "attemptHistory": attempts,
        "panelUrl": panel_url,
        "checkedAt": CHECKED_AT,
        "checkMethod": "google_search_maps_desktop_mobile_multi_attempt",
        "storeContext": "street_front",
        "matchQuality": "named_gmb_profile" if store.get("sourceCoverage", {}).get("gmbFound") else "needs_manual_review",
        "notes": store.get("manualReviewReason", ""),
    }


async def recheck_store(playwright, store: dict) -> list[dict]:
    query = make_query(store)
    targets = [
        ("desktop_google_search", google_search_url(query), {"width": 1365, "height": 900}, None),
        ("desktop_maps_search", maps_search_url(query), {"width": 1365, "height": 900}, None),
        (
            "mobile_google_search",
            google_search_url(query),
            {"width": 390, "height": 844, "isMobile": True, "hasTouch": True},
            "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
        ),
        (
            "mobile_maps_search",
            maps_search_url(query),
            {"width": 390, "height": 844, "isMobile": True, "hasTouch": True},
            "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
        ),
    ]

    attempts = []
    browser = await playwright.chromium.launch(headless=True)
    try:
        for idx, (target_name, url, viewport, user_agent) in enumerate(targets, start=1):
            context = await browser.new_context(
                locale="zh-TW",
                timezone_id="Asia/Taipei",
                viewport=viewport,
                user_agent=user_agent,
            )
            page = await context.new_page()
            attempt = await attempt_target(page, store, target_name, url, idx)
            attempts.append(attempt)
            await context.close()
            if attempt.get("providersParsed"):
                break
            await asyncio.sleep(1.2)
    finally:
        await browser.close()
    return attempts


async def main() -> None:
    payload = json.loads(STORES_PATH.read_text(encoding="utf-8"))
    stores = payload["stores"]
    async with async_playwright() as playwright:
        for store in stores:
            print(json.dumps({"storeId": store["storeId"], "store": store.get("seedName") or store["storeName"], "status": "start"}, ensure_ascii=False))
            attempts = await recheck_store(playwright, store)
            apply_recheck(store, attempts)
            print(
                json.dumps(
                    {
                        "storeId": store["storeId"],
                        "gmbOrderingStatus": store["gmbOrderingStatus"],
                        "button": store["gmbSignals"]["buttonDetected"],
                        "providers": store["gmbSignals"]["providersParsed"],
                        "attempts": len(attempts),
                        "providersList": [claim["system"] for claim in store.get("orderingSystems", []) if claim.get("sourceType") == "gmb"],
                    },
                    ensure_ascii=False,
                )
            )
    stores = active_stores(stores)
    summary = rebuild_summary(stores)
    summary["source"]["googleOrderRecheck"] = "2026-06-18 multi-attempt re-check: desktop/mobile Google Search and Maps, order entry click, provider-panel parse. Button-only detections are marked button_confirmed_provider_pending."
    summary["notes"].append("2026-06-18 re-check used desktop/mobile Google Search and Maps. Confirmed blue Google Order entries without readable provider rows are counted as entry coverage pending provider evidence.")
    write_outputs(stores, summary)
    print(json.dumps({"stores": len(stores), "summary": summary}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
