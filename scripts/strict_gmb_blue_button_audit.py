from __future__ import annotations

import asyncio
import csv
import json
import os
from collections import Counter
from datetime import date
from pathlib import Path

from playwright.async_api import async_playwright

from audit_gmb_order_panels import rebuild_summary

REPO_ROOT = Path(__file__).resolve().parents[1]
ROOT = Path(os.environ.get("BRAND_ANALYSIS_REPORT_ROOT", REPO_ROOT / "daming")).resolve()
DATA = ROOT / "data"
STORES_PATH = DATA / "stores.json"
SUMMARY_PATH = DATA / "summary.json"

PROVIDER_PATTERNS = {
    "foodpanda": "foodpanda",
    "Uber Eats": "Uber Eats",
    "UberEats": "Uber Eats",
    "ubereats": "Uber Eats",
    "Nidin": "Nidin",
    "nidin.shop": "Nidin",
    "QuickClick": "QuickClick",
    "quickclick": "QuickClick",
    "快一點": "QuickClick",
    "order.quickclick.cc": "QuickClick",
    "LINE": "LINE",
    "lin.ee": "LINE",
}
TRUSTED_GMB_PROVIDER_NAMES = set(PROVIDER_PATTERNS.values())

PICKUP_TEXT = "\u81ea\u53d6"
PICKUP_ALT_TEXT = "\u53d6\u8ca8"
DELIVERY_TEXT = "\u904b\u9001"
DELIVERY_ALT_TEXT = "\u5916\u9001"
ORDER_BUTTON_TEXT = "\u7dda\u4e0a\u9ede\u9910"
PICKUP_BUTTON_TEXT = "\u9ede\u9910\u5916\u5e36"
DELIVERY_BUTTON_TEXT = "\u9ede\u9910\u5916\u9001"
PANEL_MARKER_TEXT = "\u9078\u64c7\u4e0b\u55ae\u5c0d\u8c61"
PANEL_MARKERS = [
    PANEL_MARKER_TEXT,
    "\u53ef\u80fd\u9808\u652f\u4ed8\u624b\u7e8c\u8cbb",
    "\u5206\u9418\u5167\u9001\u9054",
    "Choose a provider",
    "Choose where to order",
]
BOT_CHECK_TEXTS = ("unusual traffic", "\u6d41\u91cf\u6709\u7570\u5e38", "\u70ba\u4f55\u986f\u793a\u6b64\u9801")
CLICKABLE_SELECTOR = "a, button, [role='button'], [aria-label]"


def provider_names(text: str) -> list[str]:
    found: list[str] = []
    lower = text.lower()
    for needle, name in PROVIDER_PATTERNS.items():
        if needle.lower() in lower and name not in found:
            found.append(name)
    return found


def trusted_gmb_providers(providers: list[str]) -> list[str]:
    found: list[str] = []
    for provider in providers:
        if provider in TRUSTED_GMB_PROVIDER_NAMES and provider not in found:
            found.append(provider)
    return found


def is_google_bot_check(page_url: str, body_text: str) -> bool:
    text = body_text.lower()
    return "google.com/sorry" in page_url or any(marker in text for marker in BOT_CHECK_TEXTS)


def is_order_panel_text(page_url: str, body_text: str) -> bool:
    return "searchviewer" in page_url or any(marker in body_text for marker in PANEL_MARKERS)


def clear_gmb_claims(store: dict) -> None:
    store["orderingSystems"] = [
        claim for claim in store.get("orderingSystems", []) if claim.get("sourceType") != "gmb"
    ]
    store["hasGmbOrderingSystem"] = False
    store["gmbPickupProviders"] = []
    store["gmbDeliveryProviders"] = []
    store["gmbOrderPanelUrl"] = ""
    store["gmbSignals"] = {}


def confirmed_gmb_claims(store: dict) -> list[dict]:
    return [
        claim
        for claim in store.get("orderingSystems", [])
        if claim.get("sourceType") == "gmb"
        and claim.get("confidence") == "confirmed"
        and claim.get("system") in TRUSTED_GMB_PROVIDER_NAMES
        and "candidate" not in claim.get("label", "").lower()
    ]


def preserve_confirmed_gmb_claims(store: dict, claims: list[dict], notes: str) -> dict:
    claims = [claim for claim in claims if claim.get("system") in TRUSTED_GMB_PROVIDER_NAMES]
    store["orderingSystems"].extend(claims)
    store["hasAnyOrderingSystem"] = bool(store.get("orderingSystems"))
    store["hasGmbOrderingSystem"] = bool(claims)
    store["gmbOrderingStatus"] = "confirmed" if claims else "unavailable_or_blocked"
    store["gmbPickupProviders"] = sorted(
        {claim["system"] for claim in claims if "pickup" in claim.get("orderMode", [])}
    )
    store["gmbDeliveryProviders"] = sorted(
        {claim["system"] for claim in claims if "delivery" in claim.get("orderMode", [])}
    )
    store["manualReviewReason"] = notes
    store["gmbSignals"] = {
        "buttonDetected": bool(claims),
        "providersParsed": bool(claims),
        "panelUrl": store.get("gmbOrderPanelUrl") or store.get("gmbUrl") or "",
        "checkedAt": date.today().isoformat(),
        "checkMethod": "gmb_blue_button_browser",
        "notes": notes,
    }
    return store


async def get_body_text(page) -> str:
    try:
        return await page.locator("body").inner_text(timeout=8000)
    except Exception:
        return ""


async def wait_for_order_panel_text(page, timeout_ms: int = 9000) -> str:
    deadline = asyncio.get_running_loop().time() + timeout_ms / 1000
    latest = ""
    while asyncio.get_running_loop().time() < deadline:
        latest = await get_body_text(page)
        if is_order_panel_text(page.url, latest):
            return latest
        await page.wait_for_timeout(500)
    return latest


async def visible_provider_names(page) -> list[str]:
    try:
        names = await page.evaluate(
            """
            ({ patterns, panelMarkers }) => {
                const normalize = value => (value || '').replace(/\\s+/g, ' ').trim();
                const isVisible = el => {
                    const rect = el.getBoundingClientRect();
                    const style = getComputedStyle(el);
                    return rect.width > 20
                        && rect.height > 10
                        && rect.bottom > 0
                        && rect.top < innerHeight
                        && style.display !== 'none'
                        && style.visibility !== 'hidden'
                        && Number(style.opacity || 1) > 0.2;
                };
                const panelText = el => normalize(`${el.innerText || el.textContent || ''} ${el.getAttribute('aria-label') || ''}`);
                const blockedRow = text => [
                    /搜尋結果/,
                    /網頁搜尋/,
                    /網路上的評論/,
                    /Google 評論/,
                    /damingtea/i,
                    /google\\.com\\/search/i,
                    /maps\\.app\\.goo\\.gl/i,
                    /g\\.co\\/kgs/i,
                    /grade\\./i,
                    /review/i,
                    /大茗/,
                    /菜單/,
                    /訂購/,
                    /品牌專區/,
                    /網站/,
                    /路線/,
                    /評論/,
                    /儲存/,
                    /分享/,
                    /致電/,
                    /營業時間/,
                    /已打烊/,
                    /線上點餐/
                ].some(pattern => pattern.test(text));
                const hasProvider = text => patterns.some(([needle]) => text.toLowerCase().includes(needle.toLowerCase()));
                const isGoogleOrderMerchantProvider = text => /nidin(\\.shop)?/i.test(text);
                let containers = [...document.querySelectorAll('[role="dialog"]')]
                    .filter(isVisible)
                    .filter(el => panelMarkers.some(marker => panelText(el).includes(marker)));
                const bodyText = panelText(document.body);
                if (!containers.length && location.href.includes('searchviewer') && panelMarkers.some(marker => bodyText.includes(marker))) {
                    containers = [document.body];
                }
                const found = [];
                for (const container of containers) {
                    const rows = [...container.querySelectorAll('a, button, [role="button"], [role="link"], [jsaction], [onclick], [tabindex]')]
                        .filter(isVisible)
                        .map(el => panelText(el))
                        .filter(text => text.length > 0 && text.length <= 180)
                        .filter(text => hasProvider(text))
                        .filter(text => isGoogleOrderMerchantProvider(text) || !blockedRow(text));
                    for (const rowText of rows) {
                        const lower = rowText.toLowerCase();
                        for (const [needle, name] of patterns) {
                            if (lower.includes(needle.toLowerCase()) && !found.includes(name)) {
                                found.push(name);
                            }
                        }
                    }
                }
                return found;
            }
            """,
            {"patterns": list(PROVIDER_PATTERNS.items()), "panelMarkers": PANEL_MARKERS},
        )
        return names
    except Exception:
        return []


async def mode_control_state(page, mode_texts: list[str]) -> str:
    try:
        return await page.evaluate(
            """
            ({ modeTexts, selector }) => {
                const normalize = value => (value || '').replace(/\\s+/g, ' ').trim();
                const parseColor = value => {
                    const match = /rgba?\\((\\d+),\\s*(\\d+),\\s*(\\d+)/.exec(value || '');
                    return match ? [Number(match[1]), Number(match[2]), Number(match[3])] : [0, 0, 0];
                };
                const isVisible = el => {
                    const rect = el.getBoundingClientRect();
                    const style = getComputedStyle(el);
                    return rect.width > 20
                        && rect.height > 12
                        && rect.bottom > 0
                        && rect.top < innerHeight
                        && style.display !== 'none'
                        && style.visibility !== 'hidden';
                };
                const isDisabled = el => {
                    for (let node = el; node && node !== document.body; node = node.parentElement) {
                        const aria = (node.getAttribute('aria-disabled') || '').toLowerCase();
                        const cls = (node.getAttribute('class') || '').toLowerCase();
                        const style = getComputedStyle(node);
                        if (node.disabled || aria === 'true' || cls.includes('disabled') || style.pointerEvents === 'none' || Number(style.opacity) < 0.45) {
                            return true;
                        }
                    }
                    return false;
                };
                const isActive = el => {
                    for (let node = el; node && node !== document.body; node = node.parentElement) {
                        const ariaSelected = (node.getAttribute('aria-selected') || '').toLowerCase();
                        const ariaPressed = (node.getAttribute('aria-pressed') || '').toLowerCase();
                        const cls = (node.getAttribute('class') || '').toLowerCase();
                        const text = normalize(node.innerText || node.textContent || '');
                        const style = getComputedStyle(node);
                        const bg = parseColor(style.backgroundColor);
                        const border = parseColor(style.borderColor);
                        const blueBg = bg[2] > bg[0] + 28 && bg[2] >= bg[1] + 5;
                        const blueBorder = border[2] > border[0] + 35 && border[2] >= border[1] + 8;
                        if (ariaSelected === 'true' || ariaPressed === 'true' || cls.includes('selected') || cls.includes('active') || /^×\\s*/.test(text) || blueBg || blueBorder) {
                            return true;
                        }
                    }
                    return false;
                };
                const nodes = [...document.querySelectorAll(selector)]
                    .filter(isVisible)
                    .filter(el => {
                        const text = normalize(`${el.innerText || el.textContent || ''} ${el.getAttribute('aria-label') || ''}`);
                        return text.length <= 40 && modeTexts.some(mode => text.includes(mode));
                    });
                if (!nodes.length) return 'missing';
                if (nodes.some(node => !isDisabled(node) && isActive(node))) return 'active';
                return 'inactive';
            }
            """,
            {"modeTexts": mode_texts, "selector": "button, [role='button'], a, div, span"},
        )
    except Exception:
        return "missing"


async def click_mode_control(page, mode_texts: list[str]) -> bool:
    try:
        clicked = await page.evaluate(
            """
            ({ modeTexts, selector }) => {
                const normalize = value => (value || '').replace(/\\s+/g, ' ').trim();
                const isVisible = el => {
                    const rect = el.getBoundingClientRect();
                    const style = getComputedStyle(el);
                    return rect.width > 20
                        && rect.height > 12
                        && rect.bottom > 0
                        && rect.top < innerHeight
                        && style.display !== 'none'
                        && style.visibility !== 'hidden';
                };
                const isDisabled = el => {
                    for (let node = el; node && node !== document.body; node = node.parentElement) {
                        const aria = (node.getAttribute('aria-disabled') || '').toLowerCase();
                        const cls = (node.getAttribute('class') || '').toLowerCase();
                        const style = getComputedStyle(node);
                        if (node.disabled || aria === 'true' || cls.includes('disabled') || style.pointerEvents === 'none' || Number(style.opacity) < 0.45) {
                            return true;
                        }
                    }
                    return false;
                };
                const nodes = [...document.querySelectorAll(selector)]
                    .filter(isVisible)
                    .filter(el => {
                        const text = normalize(`${el.innerText || el.textContent || ''} ${el.getAttribute('aria-label') || ''}`);
                        return text.length <= 40 && modeTexts.some(mode => text.includes(mode));
                    })
                    .map(el => {
                        let target = el.closest('button,[role="button"],a') || el;
                        return { el, target };
                    })
                    .filter(item => !isDisabled(item.target))
                    .sort((a, b) => {
                        const ar = a.target.getBoundingClientRect();
                        const br = b.target.getBoundingClientRect();
                        return (ar.top - br.top) || (ar.left - br.left);
                    });
                if (!nodes.length) return false;
                nodes[0].target.click();
                return true;
            }
            """,
            {"modeTexts": mode_texts, "selector": "button, [role='button'], a, div, span"},
        )
        if clicked:
            await page.wait_for_timeout(1200)
            return True
    except Exception:
        pass
    return False


async def click_enabled_mode_text(page, mode_texts: list[str]) -> bool:
    for text in mode_texts:
        locator = page.get_by_text(text, exact=False)
        try:
            count = min(await locator.count(), 5)
            for index in range(count):
                candidate = locator.nth(index)
                if not await candidate.is_visible(timeout=700):
                    continue
                if not await candidate.is_enabled(timeout=700):
                    continue
                box = await candidate.bounding_box(timeout=700)
                if not box or box["width"] < 12 or box["height"] < 12:
                    continue
                await candidate.click(timeout=5000)
                await page.wait_for_timeout(1200)
                return True
        except Exception:
            continue
    return False


async def click_mode_and_read(page, mode_text: str) -> str:
    clicked = await click_enabled_mode_text(page, [mode_text])
    if not clicked:
        return ""
    return await wait_for_order_panel_text(page)


async def click_blue_button_and_read(page, button_text: str) -> str:
    locators = [
        page.get_by_role("button", name=button_text, exact=False),
        page.get_by_text(button_text, exact=False),
    ]
    for locator in locators:
        try:
            count = min(await locator.count(), 8)
            for index in range(count):
                candidate = locator.nth(index)
                if not await candidate.is_visible(timeout=900):
                    continue
                if not await candidate.is_enabled():
                    continue
                await candidate.click(timeout=5000)
                await page.wait_for_timeout(1800)
                return await wait_for_order_panel_text(page)
        except Exception:
            continue
    try:
        clicked = await page.evaluate(
            """
            ({ text, selector }) => {
                const normalize = value => (value || '').replace(/\\s+/g, ' ').trim();
                const isVisible = el => {
                    const rect = el.getBoundingClientRect();
                    const style = getComputedStyle(el);
                    return rect.width > 20
                        && rect.height > 12
                        && rect.bottom > 0
                        && rect.top < innerHeight
                        && style.display !== 'none'
                        && style.visibility !== 'hidden'
                        && style.opacity !== '0';
                };
                const isDisabled = el => {
                    for (let node = el; node && node !== document.body; node = node.parentElement) {
                        const aria = (node.getAttribute('aria-disabled') || '').toLowerCase();
                        const cls = (node.getAttribute('class') || '').toLowerCase();
                        const style = getComputedStyle(node);
                        if (node.disabled || aria === 'true' || cls.includes('disabled') || style.pointerEvents === 'none' || Number(style.opacity) < 0.45) {
                            return true;
                        }
                    }
                    return false;
                };
                const nodes = [...document.querySelectorAll(selector)]
                    .filter(isVisible)
                    .filter(el => !isDisabled(el))
                    .map(el => ({
                        el,
                        text: normalize(`${el.innerText || el.textContent || ''} ${el.getAttribute('aria-label') || ''}`)
                    }))
                    .filter(item => item.text.includes(text))
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
            {"text": button_text, "selector": CLICKABLE_SELECTOR},
        )
        if clicked:
            await page.wait_for_timeout(1800)
            return await wait_for_order_panel_text(page)
    except Exception:
        pass
    return ""


async def read_two_button_flow(page, store: dict, result: dict) -> bool:
    found_any_button = False
    for button_text, mode_key in (
        (PICKUP_BUTTON_TEXT, "pickupProviders"),
        (DELIVERY_BUTTON_TEXT, "deliveryProviders"),
    ):
        try:
            await page.goto(store["gmbUrl"], wait_until="domcontentloaded", timeout=45_000)
            await page.wait_for_timeout(2500)
        except Exception:
            continue
        panel_text = await click_blue_button_and_read(page, button_text)
        if not panel_text:
            continue
        found_any_button = True
        result["panelUrl"] = result["panelUrl"] or page.url or store.get("gmbUrl", "")
        providers = await visible_provider_names(page)
        mode_state = await mode_control_state(
            page,
            [PICKUP_TEXT, PICKUP_ALT_TEXT] if mode_key == "pickupProviders" else [DELIVERY_TEXT, DELIVERY_ALT_TEXT],
        )
        if providers and mode_state == "active":
            result[mode_key] = providers

    return found_any_button


async def find_order_panel_url(page) -> str:
    links = await page.locator("a[href*='searchviewer']").evaluate_all(
        """els => els.map(e => ({
            href: e.href,
            text: (e.innerText || e.textContent || '').trim(),
            aria: e.getAttribute('aria-label') || ''
        }))"""
    )
    if links:
        return links[0]["href"]

    if await page.get_by_text(ORDER_BUTTON_TEXT, exact=False).count():
        try:
            await page.get_by_text(ORDER_BUTTON_TEXT, exact=False).first.click(timeout=5000)
            await page.wait_for_timeout(2500)
        except Exception:
            pass
        current_text = await get_body_text(page)
        if is_order_panel_text(page.url, current_text):
            return "__CURRENT_PAGE_PANEL__"
        links = await page.locator("a[href*='searchviewer']").evaluate_all(
            """els => els.map(e => ({ href: e.href }))"""
        )
        if links:
            return links[0]["href"]

    return ""


async def audit_store(context, store: dict, index: int, total: int) -> dict:
    previous_confirmed_gmb = confirmed_gmb_claims(store)
    clear_gmb_claims(store)
    if not store.get("gmbUrl"):
        store["gmbOrderingStatus"] = "gmb_not_found"
        store["manualReviewReason"] = "Official store exists, but no GMB URL was captured."
        print(f"{index}/{total} {store.get('storeName')} gmb_not_found")
        return store

    result = {
        "status": "no_gmb_order_button",
        "panelUrl": "",
        "pickupProviders": [],
        "deliveryProviders": [],
        "notes": "",
    }

    page = await context.new_page()
    try:
        await page.goto(store["gmbUrl"], wait_until="domcontentloaded", timeout=45_000)
        await page.wait_for_timeout(4000)
        first_body = await get_body_text(page)
        if is_google_bot_check(page.url, first_body):
            result["status"] = "unavailable_or_blocked"
            result["notes"] = "Google blocked the GMB page during automated blue-button audit."
            if previous_confirmed_gmb:
                return preserve_confirmed_gmb_claims(
                    store,
                    previous_confirmed_gmb,
                    "Google blocked automated re-open; preserved previous confirmed Google Order evidence.",
                )
            return apply_result(store, result)

        found_two_button_flow = await read_two_button_flow(page, store, result)
        if result["pickupProviders"] or result["deliveryProviders"]:
            result["status"] = "confirmed"
            result["notes"] = "Strict GMB audit: opened explicit blue pickup/delivery order buttons and read providers by mode."
            return apply_result(store, result)
        if found_two_button_flow:
            result["status"] = "button_confirmed_provider_pending"
            result["notes"] = "Blue pickup/delivery order buttons opened, but no known provider name was parsed."
            return apply_result(store, result)

        await page.goto(store["gmbUrl"], wait_until="domcontentloaded", timeout=45_000)
        await page.wait_for_timeout(2500)
        panel_url = await find_order_panel_url(page)
        if not panel_url:
            result["status"] = "no_gmb_order_button"
            result["notes"] = "No Google Order blue online-order entry/searchviewer panel was found."
            return apply_result(store, result)

        result["panelUrl"] = panel_url
        if panel_url != "__CURRENT_PAGE_PANEL__":
            await page.goto(panel_url, wait_until="domcontentloaded", timeout=45_000)
            await page.wait_for_timeout(2500)
        body = await get_body_text(page)

        if PICKUP_TEXT in body or PICKUP_ALT_TEXT in body:
            pickup_text = await click_mode_and_read(page, PICKUP_ALT_TEXT if PICKUP_ALT_TEXT in body else PICKUP_TEXT)
            if is_order_panel_text(page.url, pickup_text):
                result["pickupProviders"] = await visible_provider_names(page)

        if DELIVERY_TEXT in body or DELIVERY_ALT_TEXT in body:
            delivery_text = await click_mode_and_read(page, DELIVERY_TEXT) if DELIVERY_TEXT in body else body
            if is_order_panel_text(page.url, delivery_text):
                result["deliveryProviders"] = await visible_provider_names(page)

        if result["pickupProviders"] or result["deliveryProviders"]:
            result["status"] = "confirmed"
            result["notes"] = "Strict GMB audit: opened the blue online-order button panel and read providers by pickup/delivery mode."
        else:
            result["status"] = "button_confirmed_provider_pending"
            result["notes"] = "Google Order panel opened, but no known provider name was parsed."
        return apply_result(store, result)
    except Exception as exc:
        result["status"] = "unavailable_or_blocked"
        result["notes"] = f"Strict GMB audit failed while opening the blue online-order flow: {type(exc).__name__}."
        return apply_result(store, result)
    finally:
        await page.close()
        print(
            f"{index}/{total} {store.get('storeName')} {result['status']} "
            f"pickup={result['pickupProviders']} delivery={result['deliveryProviders']}"
        )


def apply_result(store: dict, result: dict) -> dict:
    claims = list(store.get("orderingSystems", []))
    panel_url = result.get("panelUrl") or store.get("gmbUrl") or ""
    pickup_providers = trusted_gmb_providers(result.get("pickupProviders", []))
    delivery_providers = trusted_gmb_providers(result.get("deliveryProviders", []))
    parsed_providers = bool(pickup_providers or delivery_providers)
    button_detected = bool(result.get("buttonDetected")) or parsed_providers or result["status"] == "button_confirmed_provider_pending"
    if result["status"] == "confirmed" and not parsed_providers:
        result["status"] = "button_confirmed_provider_pending"
        result["notes"] = (
            "Google Order entry was opened, but no trusted provider row was parsed. "
            "Official Nidin links are excluded from Google Order provider evidence."
        )

    for provider in pickup_providers:
        claims.append(
            {
                "system": provider,
                "sourceType": "gmb",
                "orderMode": ["pickup"],
                "evidenceUrl": panel_url,
                "label": "Google Order pickup",
                "confidence": "confirmed",
            }
        )
    for provider in delivery_providers:
        claims.append(
            {
                "system": provider,
                "sourceType": "gmb",
                "orderMode": ["delivery"],
                "evidenceUrl": panel_url,
                "label": "Google Order delivery",
                "confidence": "confirmed",
            }
        )

    seen = set()
    deduped = []
    for claim in claims:
        key = (
            claim.get("system"),
            claim.get("sourceType"),
            tuple(claim.get("orderMode", [])),
            claim.get("evidenceUrl"),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(claim)

    store["orderingSystems"] = deduped
    store["hasAnyOrderingSystem"] = bool(deduped)
    store["hasGmbOrderingSystem"] = any(claim.get("sourceType") == "gmb" for claim in deduped) or result[
        "status"
    ] == "button_confirmed_provider_pending"
    store["gmbOrderingStatus"] = result["status"]
    store["gmbOrderPanelUrl"] = panel_url
    if result["status"] not in {"not_found", "duplicate_or_ambiguous"}:
        coverage = store.setdefault("sourceCoverage", {})
        coverage["googleFound"] = True
        coverage["gmbFound"] = True
        store["gmbStatus"] = "confirmed"
        if panel_url and not store.get("gmbUrl"):
            store["gmbUrl"] = panel_url
    store["gmbPickupProviders"] = pickup_providers
    store["gmbDeliveryProviders"] = delivery_providers
    store["manualReviewReason"] = result.get("notes", "")
    store["gmbSignals"] = {
        "buttonDetected": button_detected,
        "providersParsed": parsed_providers,
        "panelUrl": panel_url,
        "checkedAt": date.today().isoformat(),
        "checkMethod": result.get("checkMethod", "gmb_blue_button_browser"),
        "attemptCount": result.get("attemptCount"),
        "maxAttempts": result.get("maxAttempts"),
        "attemptHistory": result.get("attemptHistory", []),
        "notes": result.get("notes", ""),
    }
    return store


def write_csv(stores: list[dict]) -> None:
    fields = [
        "storeId",
        "storeName",
        "regionGroup",
        "city",
        "district",
        "address",
        "phone",
        "hours",
        "gmbStatus",
        "gmbOrderingStatus",
        "hasAnyOrderingSystem",
        "hasGmbOrderingSystem",
        "allSourceSystems",
        "gmbSystems",
        "officialSourceUrl",
        "officialStoreUrl",
        "gmbUrl",
        "evidenceLinks",
        "manualReviewReason",
    ]
    with (DATA / "stores.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for store in stores:
            all_systems = sorted({claim["system"] for claim in store.get("orderingSystems", [])})
            gmb_systems = sorted(
                {claim["system"] for claim in store.get("orderingSystems", []) if claim.get("sourceType") == "gmb"}
            )
            evidence = sorted(
                {claim["evidenceUrl"] for claim in store.get("orderingSystems", []) if claim.get("evidenceUrl")}
            )
            writer.writerow(
                {
                    "storeId": store.get("storeId", ""),
                    "storeName": store.get("storeName", ""),
                    "regionGroup": store.get("regionGroup", ""),
                    "city": store.get("city", ""),
                    "district": store.get("district", ""),
                    "address": store.get("address", ""),
                    "phone": store.get("phone", ""),
                    "hours": store.get("hours", ""),
                    "gmbStatus": store.get("gmbStatus", ""),
                    "gmbOrderingStatus": store.get("gmbOrderingStatus", ""),
                    "hasAnyOrderingSystem": store.get("hasAnyOrderingSystem", False),
                    "hasGmbOrderingSystem": store.get("hasGmbOrderingSystem", False),
                    "allSourceSystems": "\u3001".join(all_systems),
                    "gmbSystems": "\u3001".join(gmb_systems),
                    "officialSourceUrl": store.get("officialSourceUrl", ""),
                    "officialStoreUrl": store.get("officialStoreUrl", ""),
                    "gmbUrl": store.get("gmbUrl", ""),
                    "evidenceLinks": " | ".join(evidence),
                    "manualReviewReason": store.get("manualReviewReason", ""),
                }
            )


def write_outputs(payload: dict) -> dict:
    stores = payload["stores"]
    summary = rebuild_summary(stores)
    STORES_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    SUMMARY_PATH.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (ROOT / "data-inline.js").write_text(
        "window.DAMING_DATA = "
        + json.dumps({"storesPayload": payload, "summary": summary}, ensure_ascii=True)
        + ";\n",
        encoding="ascii",
    )
    write_csv(stores)
    return summary


async def main(limit: int | None = None, concurrency: int = 1) -> None:
    payload = json.loads(STORES_PATH.read_text(encoding="utf-8"))
    stores = payload["stores"]
    targets = stores[:limit] if limit else stores

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        context = await browser.new_context(locale="zh-TW", viewport={"width": 1360, "height": 980})
        updated_by_id = {}
        semaphore = asyncio.Semaphore(concurrency)

        async def run_one(index: int, store: dict) -> None:
            async with semaphore:
                updated = await audit_store(context, dict(store), index, len(targets))
                updated_by_id[updated["storeId"]] = updated
                await asyncio.sleep(1.2)

        await asyncio.gather(*(run_one(index, store) for index, store in enumerate(targets, start=1)))
        await browser.close()

    payload["stores"] = [updated_by_id.get(store["storeId"], store) for store in stores]
    summary = write_outputs(payload)
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
