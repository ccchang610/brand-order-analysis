from __future__ import annotations

import argparse
import asyncio
import json
import random
from datetime import date
from pathlib import Path
from urllib.parse import quote_plus

from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright

from strict_gmb_blue_button_audit import (
    BOT_CHECK_TEXTS,
    DATA,
    STORES_PATH,
    apply_result,
    clear_gmb_claims,
    confirmed_gmb_claims,
    is_google_bot_check,
    provider_names,
    visible_provider_names,
    write_outputs,
)

ORDER_BUTTON_TEXTS = [
    "\u7dda\u4e0a\u9ede\u9910",
    "\u9ede\u9910\u5916\u5e36",
    "\u9ede\u9910\u5916\u9001",
    "\u7dda\u4e0a\u8a02\u9910",
    "Order online",
]
PICKUP_TEXTS = ["\u81ea\u53d6", "\u5916\u5e36", "Pickup"]
DELIVERY_TEXTS = ["\u904b\u9001", "\u5916\u9001", "Delivery"]
PANEL_TEXTS = [
    "\u9078\u64c7\u4e0b\u55ae\u5c0d\u8c61",
    "\u53ef\u80fd\u9808\u652f\u4ed8\u624b\u7e8c\u8cbb",
    "\u5206\u9418\u5167\u9001\u9054",
    "Choose a provider",
    "Choose where to order",
]
CLICKABLE_SELECTOR = "a, button, [role='button'], [aria-label]"

STATUS_RANK = {
    "confirmed": 4,
    "button_confirmed_provider_pending": 3,
    "unavailable_or_blocked": 2,
    "no_gmb_order_button": 1,
}


def search_url(store: dict) -> str:
    query = f"{store.get('brand') or '大茗'} {store.get('storeName','')} {store.get('address','')}"
    return f"https://www.google.com/search?q={quote_plus(query)}&hl=zh-TW"


def should_preserve_existing(store: dict, result: dict) -> bool:
    if result["status"] in {"confirmed", "button_confirmed_provider_pending"}:
        return False
    return bool(
        confirmed_gmb_claims(store)
        or store.get("gmbOrderingStatus") == "button_confirmed_provider_pending"
    )


def better_result(current: dict | None, candidate: dict) -> dict:
    if current is None:
        return candidate
    if STATUS_RANK.get(candidate.get("status"), 0) > STATUS_RANK.get(current.get("status"), 0):
        return candidate
    if candidate.get("pickupProviders") or candidate.get("deliveryProviders"):
        return candidate
    return current


def preserve_existing_state(store: dict, result: dict) -> dict:
    reason = result.get("notes") or result.get("status") or "No improved result during re-check."
    trusted_claims = confirmed_gmb_claims(store)
    pending_entry = (
        not trusted_claims
        and store.get("gmbOrderingStatus") == "button_confirmed_provider_pending"
    )
    store["orderingSystems"] = [
        claim for claim in store.get("orderingSystems", []) if claim.get("sourceType") != "gmb"
    ] + trusted_claims
    store["hasGmbOrderingSystem"] = bool(trusted_claims or pending_entry)
    store["gmbOrderingStatus"] = "confirmed" if trusted_claims else "button_confirmed_provider_pending"
    store["gmbPickupProviders"] = sorted(
        {claim["system"] for claim in trusted_claims if "pickup" in claim.get("orderMode", [])}
    )
    store["gmbDeliveryProviders"] = sorted(
        {claim["system"] for claim in trusted_claims if "delivery" in claim.get("orderMode", [])}
    )
    store["manualReviewReason"] = (
        f"Human-paced re-check did not improve prior GMB ordering evidence ({reason}); "
        "preserved existing Google Order status instead of downgrading it."
    )
    store["gmbSignals"] = {
        **(store.get("gmbSignals") or {}),
        "buttonDetected": bool(store.get("hasGmbOrderingSystem") or result.get("buttonDetected")),
        "providersParsed": bool(trusted_claims),
        "panelUrl": store.get("gmbOrderPanelUrl") or result.get("panelUrl") or store.get("gmbUrl") or "",
        "checkedAt": date.today().isoformat(),
        "checkMethod": "human_paced_gmb_recheck",
        "attemptCount": result.get("attemptCount"),
        "maxAttempts": result.get("maxAttempts"),
        "attemptHistory": result.get("attemptHistory", []),
        "notes": store["manualReviewReason"],
    }
    return store


async def human_pause(page, low: int = 450, high: int = 1300) -> None:
    await page.wait_for_timeout(random.randint(low, high))


async def human_settle(page) -> None:
    await human_pause(page, 900, 1800)
    try:
        await page.mouse.move(random.randint(280, 900), random.randint(180, 620), steps=random.randint(12, 28))
        await human_pause(page, 250, 700)
        await page.mouse.wheel(0, random.randint(180, 520))
        await human_pause(page, 500, 1200)
        await page.mouse.wheel(0, -random.randint(80, 260))
    except Exception:
        pass


async def body_text(page) -> str:
    try:
        return await page.locator("body").inner_text(timeout=8000)
    except Exception:
        return ""


async def visible_text_probe(page) -> dict:
    text = await body_text(page)
    return {
        "botCheck": is_google_bot_check(page.url, text),
        "hasOrderText": any(marker.lower() in text.lower() for marker in ORDER_BUTTON_TEXTS),
        "providers": provider_names(text),
        "text": text,
    }


async def click_first_text(page, texts: list[str]) -> bool:
    for text in texts:
        for locator in (
            page.get_by_role("button", name=text, exact=False),
            page.get_by_role("link", name=text, exact=False),
            page.get_by_text(text, exact=False),
        ):
            try:
                count = min(await locator.count(), 8)
                for index in range(count):
                    candidate = locator.nth(index)
                    if not await candidate.is_visible(timeout=900):
                        continue
                    if not await candidate.is_enabled():
                        continue
                    await candidate.click(timeout=6000)
                    await human_pause(page, 1200, 2600)
                    return True
            except Exception:
                continue
        try:
            clicked = await page.evaluate(
                """
                ({ texts, selector }) => {
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
                        .filter(item => texts.some(text => item.text.includes(text)))
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
                {"texts": [text], "selector": CLICKABLE_SELECTOR},
            )
            if clicked:
                await human_pause(page, 1200, 2600)
                return True
        except Exception:
            continue
    return False


async def wait_for_panel_text(page, timeout_ms: int = 9000) -> str:
    deadline = asyncio.get_running_loop().time() + timeout_ms / 1000
    latest = ""
    while asyncio.get_running_loop().time() < deadline:
        latest = await body_text(page)
        if is_order_panel_text(page.url, latest):
            return latest
        await human_pause(page, 450, 900)
    return latest


def is_order_panel_text(page_url: str, text: str) -> bool:
    return "searchviewer" in page_url or any(marker in text for marker in PANEL_TEXTS)


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
            await human_pause(page, 900, 1700)
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
                await human_pause(page, 900, 1700)
                return True
        except Exception:
            continue
    return False


async def read_mode(page, mode_texts: list[str]) -> list[str]:
    clicked = await click_enabled_mode_text(page, mode_texts)
    if not clicked:
        return []
    text = await wait_for_panel_text(page)
    if not is_order_panel_text(page.url, text):
        return []
    return await visible_provider_names(page)


async def inspect_order_flow(page) -> dict:
    result = {
        "status": "no_gmb_order_button",
        "panelUrl": page.url,
        "pickupProviders": [],
        "deliveryProviders": [],
        "notes": "No Google Order button was found during human-paced browser check.",
        "buttonDetected": False,
    }

    original_url = page.url
    probe = await visible_text_probe(page)
    if probe["botCheck"]:
        result["status"] = "unavailable_or_blocked"
        result["notes"] = "Google blocked the page during human-paced Google Order re-check."
        return result

    for button_text, mode_key in (
        ("\u9ede\u9910\u5916\u5e36", "pickupProviders"),
        ("\u9ede\u9910\u5916\u9001", "deliveryProviders"),
    ):
        try:
            await page.goto(original_url, wait_until="domcontentloaded", timeout=30000)
            await human_settle(page)
            clicked = await click_first_text(page, [button_text])
        except Exception:
            clicked = False
        if clicked:
            result["buttonDetected"] = True
            result["panelUrl"] = page.url
            clicked_text = await wait_for_panel_text(page)
            mode_state = await mode_control_state(
                page,
                PICKUP_TEXTS if mode_key == "pickupProviders" else DELIVERY_TEXTS,
            )
            if is_order_panel_text(page.url, clicked_text) and mode_state == "active":
                result[mode_key] = await visible_provider_names(page)

    if not result["buttonDetected"]:
        try:
            await page.goto(original_url, wait_until="domcontentloaded", timeout=30000)
            await human_settle(page)
        except Exception:
            pass
        clicked = await click_first_text(page, ORDER_BUTTON_TEXTS)
        result["buttonDetected"] = clicked or probe["hasOrderText"]
        await human_pause(page, 900, 1700)

    if not result["buttonDetected"]:
        return result

    result["panelUrl"] = page.url
    text_after_click = await wait_for_panel_text(page)
    if is_google_bot_check(page.url, text_after_click):
        result["status"] = "unavailable_or_blocked"
        result["notes"] = "Google blocked the order panel during human-paced Google Order re-check."
        return result

    lower_text = text_after_click.lower()
    if is_order_panel_text(page.url, text_after_click):
        if not result["pickupProviders"]:
            result["pickupProviders"] = await read_mode(page, PICKUP_TEXTS)
        if not result["deliveryProviders"]:
            result["deliveryProviders"] = await read_mode(page, DELIVERY_TEXTS)

    if result["pickupProviders"] or result["deliveryProviders"]:
        result["status"] = "confirmed"
        result["notes"] = "Human-paced Google Order re-check opened the blue order flow and read providers."
    else:
        result["status"] = "button_confirmed_provider_pending"
        result["notes"] = "Human-paced Google Order re-check confirmed a blue Google Order entry, but provider names still need manual panel review."
    return result


async def audit_store(context, store: dict, attempts: int = 3) -> dict:
    page = await context.new_page()
    previous_confirmed = confirmed_gmb_claims(store)
    attempts = max(1, attempts)
    try:
        targets = [
            store.get("gmbOrderPanelUrl") if "google.com" in (store.get("gmbOrderPanelUrl") or "") else "",
            store.get("gmbUrl"),
            search_url(store),
        ]
        best_result = None
        last_result = None
        history = []
        for target in [url for url in targets if url]:
            for attempt in range(1, attempts + 1):
                try:
                    await page.goto(target, wait_until="domcontentloaded", timeout=45000)
                    await human_settle(page)
                    result = await inspect_order_flow(page)
                except PlaywrightTimeoutError:
                    result = {
                        "status": "unavailable_or_blocked",
                        "panelUrl": target,
                        "pickupProviders": [],
                        "deliveryProviders": [],
                        "buttonDetected": False,
                        "notes": "Timed out during human-paced Google Order re-check.",
                    }

                result["attemptCount"] = attempt
                result["maxAttempts"] = attempts
                result["targetUrl"] = target
                result["checkMethod"] = "human_paced_gmb_recheck_multi_attempt"
                history.append(
                    {
                        "attempt": attempt,
                        "target": "gmbUrl" if target == store.get("gmbUrl") else "googleSearch",
                        "status": result.get("status"),
                        "buttonDetected": bool(result.get("buttonDetected")),
                        "providersParsed": bool(result.get("pickupProviders") or result.get("deliveryProviders")),
                    }
                )
                last_result = result
                best_result = better_result(best_result, result)

                if result["status"] == "confirmed":
                    result["attemptHistory"] = history
                    clear_gmb_claims(store)
                    return apply_result(store, result)

                if attempt < attempts:
                    await asyncio.sleep(random.uniform(2.5, 6.5))

        final_result = best_result or last_result
        if final_result:
            final_result["attemptHistory"] = history
            final_result["attemptCount"] = len(history)
            final_result["maxAttempts"] = attempts
        if final_result and should_preserve_existing(store, final_result):
            return preserve_existing_state(store, final_result)
        if previous_confirmed and final_result and final_result["status"] == "unavailable_or_blocked":
            store["hasGmbOrderingSystem"] = True
            store["gmbOrderingStatus"] = "confirmed"
            store["manualReviewReason"] = "Google blocked re-check; preserved previous confirmed GMB blue-button evidence."
            store["gmbSignals"] = {
                **(store.get("gmbSignals") or {}),
                "buttonDetected": True,
                "providersParsed": True,
                "panelUrl": store.get("gmbOrderPanelUrl") or final_result.get("panelUrl") or store.get("gmbUrl") or "",
                "checkedAt": date.today().isoformat(),
                "checkMethod": "human_paced_gmb_recheck",
                "attemptCount": final_result.get("attemptCount"),
                "maxAttempts": final_result.get("maxAttempts"),
                "attemptHistory": final_result.get("attemptHistory", []),
                "notes": store["manualReviewReason"],
            }
            return store
        if final_result:
            clear_gmb_claims(store)
            return apply_result(store, final_result)
        return store
    finally:
        await page.close()


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", choices=["gaps", "review", "all"], default="gaps")
    parser.add_argument("--ids", nargs="*", default=[])
    parser.add_argument("--headed", action="store_true")
    parser.add_argument("--per-store-timeout", type=int, default=180)
    parser.add_argument("--attempts", type=int, default=3)
    args = parser.parse_args()

    payload = json.loads(STORES_PATH.read_text(encoding="utf-8"))
    stores = payload["stores"]
    if args.ids:
        target_ids = set(args.ids)
        targets = [store for store in stores if store.get("storeId") in target_ids]
    elif args.target == "gaps":
        targets = [store for store in stores if not store.get("hasGmbOrderingSystem")]
    elif args.target == "review":
        targets = [
            store
            for store in stores
            if store.get("gmbOrderingStatus")
            in {"button_confirmed_provider_pending", "unavailable_or_blocked", "no_gmb_order_button", "needs_manual_review"}
        ]
    else:
        targets = stores

    profile_dir = DATA / ".gmb-human-profile"
    profile_dir.mkdir(exist_ok=True)

    async with async_playwright() as playwright:
        context = await playwright.chromium.launch_persistent_context(
            str(profile_dir),
            headless=not args.headed,
            locale="zh-TW",
            timezone_id="Asia/Taipei",
            viewport={"width": 1365, "height": 920},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
            ),
            args=[
                "--disable-blink-features=AutomationControlled",
                "--lang=zh-TW",
            ],
        )
        updated = {}
        for idx, store in enumerate(targets, start=1):
            print(f"{idx}/{len(targets)} checking {store.get('storeId')} {store.get('storeName')}", flush=True)
            try:
                checked = await asyncio.wait_for(
                    audit_store(context, dict(store), attempts=args.attempts),
                    timeout=args.per_store_timeout,
                )
            except asyncio.TimeoutError:
                checked = dict(store)
                if not checked.get("hasGmbOrderingSystem"):
                    checked["gmbOrderingStatus"] = "unavailable_or_blocked"
                    checked["manualReviewReason"] = (
                        f"Human-paced Google Order re-check timed out after {args.per_store_timeout}s; "
                        "kept as manual review instead of treating as no Google Order."
                    )
            updated[checked["storeId"]] = checked
            payload["stores"] = [updated.get(item["storeId"], item) for item in stores]
            write_outputs(payload)
            print(
                json.dumps(
                    {
                        "storeId": checked.get("storeId"),
                        "storeName": checked.get("storeName"),
                        "status": checked.get("gmbOrderingStatus"),
                        "hasGmb": checked.get("hasGmbOrderingSystem"),
                        "pickup": checked.get("gmbPickupProviders"),
                        "delivery": checked.get("gmbDeliveryProviders"),
                        "attempts": (checked.get("gmbSignals") or {}).get("attemptCount"),
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )
            await asyncio.sleep(random.uniform(1.8, 4.5))
        await context.close()

    payload["stores"] = [updated.get(store["storeId"], store) for store in stores]
    summary = write_outputs(payload)
    print(
        json.dumps(
            {
                "officialStoreCount": summary["officialStoreCount"],
                "gmbOrderingSystemCount": summary["gmbOrderingSystemCount"],
                "gmbCoverageGapCount": summary["gmbCoverageGapCount"],
                "gmbOrderingStatusCounts": summary["gmbOrderingStatusCounts"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
