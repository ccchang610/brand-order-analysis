from __future__ import annotations

import asyncio
import json
import re
from collections import defaultdict
from datetime import date
from pathlib import Path
from urllib.parse import quote_plus

from playwright.async_api import async_playwright

from build_pbcafe_analysis import (
    REGION_BY_CITY,
    UNCONFIRMED,
    inspect_order_panel,
    rebuild_summary,
    write_outputs,
)


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "pbcafe" / "data"
CHECKED_AT = date.today().isoformat()
BRAND = "\u5f7c\u5f97\u597d\u5496\u5561"

MAP_QUERIES = [
    BRAND + "\u53f0\u5317",
    BRAND + "\u65b0\u5317",
    BRAND + "\u6843\u5712",
    BRAND + "\u53f0\u5357",
    BRAND + "\u53f0\u7063",
]


def maps_search_url(query: str) -> str:
    return "https://www.google.com/maps/search/" + quote_plus(query) + "?hl=zh-TW&gl=tw"


def compact(value: str) -> str:
    value = value or ""
    value = value.replace("臺", "台")
    value = re.sub(r"Peter\s*Better\s*Cafe", "", value, flags=re.I)
    value = value.replace(BRAND, "")
    value = re.sub(r"[()\uff08\uff09\s\u00a0,.\-/·・:：]", "", value)
    value = value.replace("門市", "").replace("店", "")
    return value.lower()


def city_from_address(address: str, fallback: str) -> str:
    text = (address or "").replace("臺", "台")
    for city in REGION_BY_CITY:
        if city and city in text:
            return city
    return fallback


def match_store(card: dict, stores: list[dict]) -> dict | None:
    title_key = compact(card.get("title") or card.get("text") or "")
    address_key = compact(card.get("address") or "")
    best = None
    best_score = 0
    for store in stores:
        if store["city"] == UNCONFIRMED:
            continue
        if "\u53f0\u9054\u96fb" in store["storeName"]:
            continue
        store_key = compact(store["storeName"])
        seed_address_key = compact(store.get("address", ""))
        score = 0
        if store_key and (store_key in title_key or title_key in store_key):
            score += 8
        if address_key and seed_address_key and (address_key in seed_address_key or seed_address_key in address_key):
            score += 4
        if store_key and any(token and token in title_key for token in re.split(r"[0-9]+", store_key)):
            score += 1
        if score > best_score:
            best = store
            best_score = score
    return best if best_score >= 4 else None


def parse_card_text(text: str) -> dict:
    lines = [line.strip() for line in re.split(r"\n|\s{2,}", text or "") if line.strip()]
    merged = " ".join(lines)
    title = ""
    address = ""
    phone = ""
    rating_seen = False
    parts = re.split(r"\s+", merged)
    for idx, part in enumerate(parts):
        if BRAND in part:
            title = part
            if idx + 1 < len(parts) and not re.match(r"^\d(?:\.\d)?", parts[idx + 1]):
                nxt = parts[idx + 1]
                if "咖啡店" not in nxt:
                    title = f"{title} {nxt}"
            break
    address_match = re.search(r"咖啡店\s*[·・]\s*(?:[\ue000-\uf8ff]\s*[·・]\s*)?([^營即]+)", merged)
    if address_match:
        address = address_match.group(1).strip()
    phone_match = re.search(r"0\d{1,2}\s?\d{3,4}\s?\d{3,4}", merged)
    if phone_match:
        phone = phone_match.group(0).strip()
    if not title and BRAND in merged:
        title = merged.split("咖啡店", 1)[0].strip()
    return {"title": title, "address": address, "phone": phone, "text": merged, "ratingSeen": rating_seen}


async def collect_query(page, query: str) -> list[dict]:
    await page.goto(maps_search_url(query), wait_until="domcontentloaded", timeout=60000)
    await page.wait_for_timeout(5000)
    if await page.locator('[role="feed"]').count() == 0:
        return []
    feed = page.locator('[role="feed"]').first
    found: dict[str, dict] = {}
    last_scroll = -1
    for step in range(26):
        rows = await page.evaluate(
            r"""
            () => {
                const cards = [...document.querySelectorAll('.Nv2PK')].map((card, index) => {
                    const rect = card.getBoundingClientRect();
                    const text = (card.innerText || card.textContent || '').replace(/\s+/g, ' ').trim();
                    const order = [...card.querySelectorAll('a[href*="searchviewer"]')]
                        .map((a) => a.href)
                        .filter(Boolean);
                    const title = card.querySelector('.qBF1Pd')?.innerText?.trim() || '';
                    return {
                        index,
                        title,
                        text,
                        orderUrl: order[0] || '',
                        x: rect.x,
                        y: rect.y,
                        h: rect.height,
                        visible: rect.width > 40 && rect.height > 40 && rect.bottom > 0 && rect.top < innerHeight
                    };
                }).filter((row) => row.visible && row.text.includes('\u5f7c\u5f97\u597d\u5496\u5561'));

                const looseLinks = [...document.querySelectorAll('a[href*="searchviewer"]')]
                    .map((a) => {
                        const rect = a.getBoundingClientRect();
                        return {href: a.href, y: rect.y, visible: rect.width > 8 && rect.height > 8 && rect.bottom > 0 && rect.top < innerHeight};
                    })
                    .filter((link) => link.visible);

                for (const link of looseLinks) {
                    const card = cards.find((row) => link.y >= row.y && link.y <= row.y + row.h + 8);
                    if (card && !card.orderUrl) card.orderUrl = link.href;
                }
                return cards;
            }
            """
        )
        for row in rows:
            parsed = parse_card_text(row.get("text", ""))
            card = {
                **row,
                "title": row.get("title") or parsed["title"],
                "address": parsed["address"],
                "phone": parsed["phone"],
                "query": query,
            }
            key = compact(card["title"] + "|" + card["address"])
            if key and (key not in found or card.get("orderUrl")):
                found[key] = card
        scroll_top = await feed.evaluate("(el) => el.scrollTop")
        scroll_height = await feed.evaluate("(el) => el.scrollHeight")
        client_height = await feed.evaluate("(el) => el.clientHeight")
        if scroll_top == last_scroll and step > 2:
            break
        last_scroll = scroll_top
        if scroll_top + client_height >= scroll_height - 20:
            break
        await feed.evaluate("(el, delta) => { el.scrollTop += delta; }", 720)
        await page.wait_for_timeout(1000)
    return list(found.values())


def set_gmb_claims(store: dict, pickup: list[str], delivery: list[str], panel_url: str, notes: str, history: list[dict]) -> None:
    store["orderingSystems"] = [
        claim for claim in store.get("orderingSystems", []) if claim.get("sourceType") != "gmb"
    ]
    for system in pickup:
        store["orderingSystems"].append(
            {
                "system": system,
                "sourceType": "gmb",
                "orderMode": ["pickup"],
                "evidenceUrl": panel_url,
                "label": "Google Order pickup",
                "confidence": "confirmed",
            }
        )
    for system in delivery:
        store["orderingSystems"].append(
            {
                "system": system,
                "sourceType": "gmb",
                "orderMode": ["delivery"],
                "evidenceUrl": panel_url,
                "label": "Google Order delivery",
                "confidence": "confirmed",
            }
        )
    providers_parsed = bool(pickup or delivery)
    store["hasAnyOrderingSystem"] = bool(store["orderingSystems"])
    store["hasGmbOrderingSystem"] = providers_parsed
    store.setdefault("sourceCoverage", {})["thirdPartyFound"] = bool(store["orderingSystems"])
    store["gmbOrderingStatus"] = "confirmed" if providers_parsed else "button_confirmed_provider_pending"
    store["manualReviewReason"] = "" if providers_parsed else "Google Maps list showed an online-order entry, but provider rows were not readable in this recheck."
    store["gmbOrderPanelUrl"] = panel_url
    store["gmbPickupProviders"] = pickup
    store["gmbDeliveryProviders"] = delivery
    signals = store.get("gmbSignals") or {}
    store["gmbSignals"] = {
        **signals,
        "buttonDetected": True,
        "providersParsed": providers_parsed,
        "attemptCount": len(history),
        "maxAttempts": 3,
        "attemptHistory": history,
        "panelUrl": panel_url,
        "checkedAt": CHECKED_AT,
        "checkMethod": "google_maps_list_order_recheck",
        "notes": notes,
    }


def clear_gmb_claims(store: dict, status: str, reason: str, history: list[dict]) -> None:
    store["orderingSystems"] = [
        claim for claim in store.get("orderingSystems", []) if claim.get("sourceType") != "gmb"
    ]
    store["hasAnyOrderingSystem"] = bool(store["orderingSystems"])
    store["hasGmbOrderingSystem"] = False
    store.setdefault("sourceCoverage", {})["thirdPartyFound"] = bool(store["orderingSystems"])
    store["gmbOrderingStatus"] = status
    store["manualReviewReason"] = reason
    store["gmbOrderPanelUrl"] = ""
    store["gmbPickupProviders"] = []
    store["gmbDeliveryProviders"] = []
    signals = store.get("gmbSignals") or {}
    store["gmbSignals"] = {
        **signals,
        "buttonDetected": False,
        "providersParsed": False,
        "attemptCount": len(history),
        "maxAttempts": 3,
        "attemptHistory": history,
        "panelUrl": "",
        "checkedAt": CHECKED_AT,
        "checkMethod": "google_maps_list_order_recheck",
        "notes": reason,
    }


async def main() -> None:
    payload = json.loads((DATA / "stores.json").read_text(encoding="utf-8"))
    stores = payload["stores"]
    cards_by_store: dict[str, list[dict]] = defaultdict(list)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            locale="zh-TW",
            timezone_id="Asia/Taipei",
            viewport={"width": 1600, "height": 1200},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"
            ),
        )
        list_page = await context.new_page()
        order_page = await context.new_page()

        for query in MAP_QUERIES:
            cards = await collect_query(list_page, query)
            print(json.dumps({"query": query, "cards": len(cards), "orderCards": sum(1 for c in cards if c.get("orderUrl"))}, ensure_ascii=False))
            for card in cards:
                store = match_store(card, stores)
                if store:
                    cards_by_store[store["storeId"]].append(card)

        for store in stores:
            history = []
            cards = cards_by_store.get(store["storeId"], [])
            order_cards = [card for card in cards if card.get("orderUrl")]
            for card in cards[:5]:
                history.append(
                    {
                        "target": "google_maps_list",
                        "query": card.get("query"),
                        "title": card.get("title"),
                        "address": card.get("address"),
                        "buttonDetected": bool(card.get("orderUrl")),
                        "orderUrl": card.get("orderUrl", ""),
                    }
                )

            if store.get("address"):
                new_city = city_from_address(store["address"], store["city"])
                store["city"] = new_city
                store["county"] = new_city
                store["regionGroup"] = REGION_BY_CITY.get(new_city, store["regionGroup"])

            # If a matching current Maps result-list card is visible but has no online-order
            # entry, that current absence must override any stale stored searchviewer URL.
            order_url = order_cards[0]["orderUrl"] if order_cards else ""
            if not cards:
                order_url = store.get("gmbOrderPanelUrl") or ""
            if order_url and store["city"] != UNCONFIRMED and "\u53f0\u9054\u96fb" not in store["storeName"]:
                try:
                    pickup, delivery, panel_url = await inspect_order_panel(order_page, order_url)
                    history.append(
                        {
                            "target": "google_order_panel",
                            "status": "confirmed" if pickup or delivery else "button_confirmed_provider_pending",
                            "buttonDetected": True,
                            "providersParsed": bool(pickup or delivery),
                            "pickupProviders": pickup,
                            "deliveryProviders": delivery,
                            "panelUrl": panel_url,
                        }
                    )
                    set_gmb_claims(
                        store,
                        pickup,
                        delivery,
                        panel_url,
                        "Google Maps list recheck opened the online-order entry and read visible provider rows by mode.",
                        history,
                    )
                except Exception as exc:
                    history.append(
                        {
                            "target": "google_order_panel",
                            "status": "unavailable_or_blocked",
                            "buttonDetected": True,
                            "providersParsed": False,
                            "error": str(exc),
                        }
                    )
                    store["gmbOrderingStatus"] = "unavailable_or_blocked"
                    store["manualReviewReason"] = "Google Maps list showed an online-order entry, but the provider panel was blocked or timed out during recheck."
                    store.setdefault("gmbSignals", {})
                    store["gmbSignals"] = {
                        **store["gmbSignals"],
                        "buttonDetected": True,
                        "providersParsed": False,
                        "attemptHistory": history,
                        "checkedAt": CHECKED_AT,
                        "checkMethod": "google_maps_list_order_recheck",
                        "notes": store["manualReviewReason"],
                    }
            else:
                if store["city"] != UNCONFIRMED and "\u53f0\u9054\u96fb" not in store["storeName"]:
                    clear_gmb_claims(
                        store,
                        "no_gmb_order_button",
                        "Google Maps list and stored profile recheck did not show an online-order entry in this bounded scan.",
                        history,
                    )
                else:
                    clear_gmb_claims(
                        store,
                        store.get("gmbOrderingStatus") or "no_gmb_profile_match",
                        store.get("manualReviewReason", ""),
                        history,
                    )

            print(
                json.dumps(
                    {
                        "storeId": store["storeId"],
                        "name": store["storeName"],
                        "status": store["gmbOrderingStatus"],
                        "providers": sorted({claim["system"] for claim in store.get("orderingSystems", []) if claim.get("sourceType") == "gmb"}),
                        "listCards": len(cards),
                        "orderCards": len(order_cards),
                    },
                    ensure_ascii=False,
                )
            )

        await browser.close()

    summary = rebuild_summary(stores)
    recheck_note = (
        "2026-06-17 Google Maps list recheck: current matching list-card online-order "
        "entries are authoritative for entry coverage; when a current matched card has "
        "no online-order entry, stale stored searchviewer/gmbOrderPanelUrl values are "
        "ignored and stale GMB provider claims are cleared."
    )
    summary.setdefault("source", {})["googleMapsListRecheck"] = recheck_note
    notes = summary.setdefault("notes", [])
    if recheck_note not in notes:
        notes.append(recheck_note)
    write_outputs(stores, summary)
    print(json.dumps({"stores": len(stores), "summary": summary}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
