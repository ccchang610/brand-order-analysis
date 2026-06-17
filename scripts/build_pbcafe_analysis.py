from __future__ import annotations

import asyncio
import csv
import json
import re
from collections import Counter
from datetime import date
from pathlib import Path
from urllib.parse import quote_plus

from playwright.async_api import async_playwright


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "pbcafe"
DATA = OUT / "data"
DATA.mkdir(parents=True, exist_ok=True)

BRAND = "\u5f7c\u5f97\u597d\u5496\u5561 Peter Better Cafe"
BRAND_SLUG = "pbcafe"
MARKET = "Taiwan"
OFFICIAL_URL = "https://www.pbcafe.com.tw/"
FRANCHISE_URL = "https://www.pbcafe.com.tw/pages/franchise"
CHECKED_AT = date.today().isoformat()

ALL = "\u5168\u53f0"
NORTH = "\u5317\u90e8"
CENTRAL = "\u4e2d\u90e8"
SOUTH = "\u5357\u90e8"
EAST = "\u6771\u90e8"
ISLANDS = "\u96e2\u5cf6"
UNCONFIRMED = "\u5f85\u78ba\u8a8d"

TAIWAN_CITIES = [
    "\u57fa\u9686\u5e02",
    "\u53f0\u5317\u5e02",
    "\u65b0\u5317\u5e02",
    "\u6843\u5712\u5e02",
    "\u65b0\u7af9\u5e02",
    "\u65b0\u7af9\u7e23",
    "\u82d7\u6817\u7e23",
    "\u53f0\u4e2d\u5e02",
    "\u5f70\u5316\u7e23",
    "\u5357\u6295\u7e23",
    "\u96f2\u6797\u7e23",
    "\u5609\u7fa9\u7e23",
    "\u5609\u7fa9\u5e02",
    "\u53f0\u5357\u5e02",
    "\u9ad8\u96c4\u5e02",
    "\u5c4f\u6771\u7e23",
    "\u5b9c\u862d\u7e23",
    "\u82b1\u84ee\u7e23",
    "\u53f0\u6771\u7e23",
    "\u6f8e\u6e56\u7e23",
    "\u91d1\u9580\u7e23",
    "\u9023\u6c5f\u7e23",
]

REGION_BY_CITY = {
    **{city: NORTH for city in TAIWAN_CITIES[:7] + ["\u5b9c\u862d\u7e23"]},
    **{city: CENTRAL for city in TAIWAN_CITIES[7:11]},
    **{city: SOUTH for city in TAIWAN_CITIES[11:16]},
    **{city: EAST for city in ["\u82b1\u84ee\u7e23", "\u53f0\u6771\u7e23"]},
    **{city: ISLANDS for city in ["\u6f8e\u6e56\u7e23", "\u91d1\u9580\u7e23", "\u9023\u6c5f\u7e23"]},
}

STORE_SEEDS = [
    ("pbcafe-001", "\u5f7c\u5f97\u597d\u5496\u5561 \u4e2d\u5c71\u6c11\u6b0a\u5e97", "\u53f0\u5317\u5e02", "\u4e2d\u5c71\u5340", "\u53f0\u5317\u5e02\u4e2d\u5c71\u5340\u4e2d\u5c71\u5317\u8def\u4e8c\u6bb5160\u865f"),
    ("pbcafe-002", "\u5f7c\u5f97\u597d\u5496\u5561 \u5fe0\u5b5d\u5fa9\u8208\u5e97", "\u53f0\u5317\u5e02", "\u5927\u5b89\u5340", "\u53f0\u5317\u5e02\u5927\u5b89\u5340\u5b89\u6771\u885752-3\u865f"),
    ("pbcafe-003", "\u5f7c\u5f97\u597d\u5496\u5561 \u5357\u6e2f\u6606\u967d\u5e97", "\u53f0\u5317\u5e02", "\u5357\u6e2f\u5340", "\u53f0\u5317\u5e02\u5357\u6e2f\u5340\u6606\u967d\u885792\u865f"),
    ("pbcafe-004", "\u5f7c\u5f97\u597d\u5496\u5561 \u4e09\u5275\u9580\u5e02", "\u53f0\u5317\u5e02", "\u4e2d\u6b63\u5340", "\u53f0\u5317\u5e02\u4e2d\u6b63\u5340\u516b\u5fb7\u8def\u4e00\u6bb5104\u865f"),
    ("pbcafe-005", "\u5f7c\u5f97\u597d\u5496\u5561 \u6c11\u751f\u96d9\u9023\u5e97", "\u53f0\u5317\u5e02", "\u5927\u540c\u5340", "\u53f0\u5317\u5e02\u5927\u540c\u5340\u6c11\u751f\u897f\u8def146\u865f"),
    ("pbcafe-006", "\u5f7c\u5f97\u597d\u5496\u5561 \u5927\u5de8\u86cb\u570b\u9928\u5e97", "\u53f0\u5317\u5e02", "\u5927\u5b89\u5340", "\u53f0\u5317\u5e02\u5927\u5b89\u5340\u5149\u5fa9\u5357\u8def180\u5df79\u865f"),
    ("pbcafe-007", "\u5f7c\u5f97\u597d\u5496\u5561 \u77f3\u724c\u69ae\u7e3d\u9580\u5e02", "\u53f0\u5317\u5e02", "\u5317\u6295\u5340", "\u53f0\u5317\u5e02\u5317\u6295\u5340\u77f3\u724c\u8def\u4e8c\u6bb5120\u865f"),
    ("pbcafe-008", "\u5f7c\u5f97\u597d\u5496\u5561 \u6771\u9580\u6c38\u5eb7\u9580\u5e02", "\u53f0\u5317\u5e02", "\u5927\u5b89\u5340", "\u53f0\u5317\u5e02\u5927\u5b89\u5340\u4fe1\u7fa9\u8def\u4e8c\u6bb5108\u865f"),
    ("pbcafe-009", "\u5f7c\u5f97\u597d\u5496\u5561 \u4fe1\u7fa9\u5927\u5b89\u5e97", "\u53f0\u5317\u5e02", "\u5927\u5b89\u5340", "\u53f0\u5317\u5e02\u5927\u5b89\u5340\u4fe1\u7fa9\u8def\u4e09\u6bb5170\u865f"),
    ("pbcafe-010", "\u5f7c\u5f97\u597d\u5496\u5561 \u5c0f\u5de8\u86cb\u5e97", "\u53f0\u5317\u5e02", "\u677e\u5c71\u5340", "\u53f0\u5317\u5e02\u677e\u5c71\u5340\u5357\u4eac\u6771\u8def\u56db\u6bb5116\u865f"),
    ("pbcafe-011", "\u5f7c\u5f97\u597d\u5496\u5561 \u5167\u6e56\u884c\u5584\u5e97", "\u53f0\u5317\u5e02", "\u5167\u6e56\u5340", "\u53f0\u5317\u5e02\u5167\u6e56\u5340\u884c\u5584\u8def64\u865f"),
    ("pbcafe-012", "\u5f7c\u5f97\u597d\u5496\u5561 \u53e4\u4ead\u5e97", "\u53f0\u5317\u5e02", "\u4e2d\u6b63\u5340", "\u53f0\u5317\u5e02\u4e2d\u6b63\u5340\u7f85\u65af\u798f\u8def\u4e8c\u6bb5132\u865f"),
    ("pbcafe-013", "\u5f7c\u5f97\u597d\u5496\u5561 \u5357\u9580\u5e97", "\u53f0\u5317\u5e02", "\u4e2d\u6b63\u5340", "\u53f0\u5317\u5e02\u4e2d\u6b63\u5340\u7f85\u65af\u798f\u8def\u4e00\u6bb524\u865f"),
    ("pbcafe-014", "\u5f7c\u5f97\u597d\u5496\u5561 \u5167\u79d1\u6d32\u5b50\u5e97", "\u53f0\u5317\u5e02", "\u5167\u6e56\u5340", "\u53f0\u5317\u5e02\u5167\u6e56\u5340\u6d32\u5b50\u885750\u865f"),
    ("pbcafe-015", "\u5f7c\u5f97\u597d\u5496\u5561 \u5317\u6295\u5e97", "\u53f0\u5317\u5e02", "\u5317\u6295\u5340", "\u53f0\u5317\u5e02\u5317\u6295\u5340\u5927\u696d\u8def530\u865f"),
    ("pbcafe-016", "\u5f7c\u5f97\u597d\u5496\u5561 \u5e02\u5e9c\u677e\u83f8\u5e97", "\u53f0\u5317\u5e02", "\u4fe1\u7fa9\u5340", "\u53f0\u5317\u5e02\u4fe1\u7fa9\u5340\u57fa\u9686\u8def\u4e00\u6bb5188\u865f"),
    ("pbcafe-017", "\u5f7c\u5f97\u597d\u5496\u5561 \u6566\u5357\u5e97", "\u53f0\u5317\u5e02", "\u5927\u5b89\u5340", "\u53f0\u5317\u5e02\u5927\u5b89\u5340\u6566\u5316\u5357\u8def\u4e8c\u6bb5103\u5df78\u865f"),
    ("pbcafe-018", "\u5f7c\u5f97\u597d\u5496\u5561 \u4e16\u8cbf\u5e97", "\u53f0\u5317\u5e02", "\u4fe1\u7fa9\u5340", "\u53f0\u5317\u5e02\u4fe1\u7fa9\u5340\u57fa\u9686\u8def\u4e8c\u6bb551\u865f1\u6a13"),
    ("pbcafe-019", "\u5f7c\u5f97\u597d\u5496\u5561 \u4e09\u91cd\u4e09\u548c\u5e97", "\u65b0\u5317\u5e02", "\u4e09\u91cd\u5340", "\u65b0\u5317\u5e02\u4e09\u91cd\u5340\u4ec1\u611b\u88576\u865f"),
    ("pbcafe-020", "\u5f7c\u5f97\u597d\u5496\u5561 \u6c38\u5b89\u5e97", "\u65b0\u5317\u5e02", "\u4e2d\u548c\u5340", "\u65b0\u5317\u5e02\u4e2d\u548c\u5340\u4e2d\u548c\u8def400\u5df714\u5f041\u865f"),
    ("pbcafe-021", "\u5f7c\u5f97\u597d\u5496\u5561 \u91d1\u9580\u8857\u5e97", "\u65b0\u5317\u5e02", "\u677f\u6a4b\u5340", "\u65b0\u5317\u5e02\u677f\u6a4b\u5340\u91d1\u9580\u88571\u5df71\u865f"),
    ("pbcafe-022", "\u5f7c\u5f97\u597d\u5496\u5561 \u677f\u6a4b\u6587\u5316\u5e97", "\u65b0\u5317\u5e02", "\u677f\u6a4b\u5340", "\u65b0\u5317\u5e02\u677f\u6a4b\u5340\u4ecb\u58fd\u88572\u865f"),
    ("pbcafe-023", "\u5f7c\u5f97\u597d\u5496\u5561 \u65b0\u838a\u8f14\u5927\u5e97", "\u65b0\u5317\u5e02", "\u65b0\u838a\u5340", "\u65b0\u5317\u5e02\u65b0\u838a\u5340\u798f\u71df\u8def183\u865f1\u6a13"),
    ("pbcafe-024", "\u5f7c\u5f97\u597d\u5496\u5561 \u677f\u6a4b\u5fe0\u5b5d\u5e97", "\u65b0\u5317\u5e02", "\u677f\u6a4b\u5340", "\u65b0\u5317\u5e02\u677f\u6a4b\u5340\u5fe0\u5b5d\u8def52\u865f"),
    ("pbcafe-025", "\u5f7c\u5f97\u597d\u5496\u5561 \u677f\u6a4b\u65b0\u57d4\u5e97", "\u65b0\u5317\u5e02", "\u677f\u6a4b\u5340", "\u65b0\u5317\u5e02\u677f\u6a4b\u5340\u81ea\u7531\u8def37\u865f"),
    ("pbcafe-026", "\u5f7c\u5f97\u597d\u5496\u5561 \u6797\u53e3\u9577\u5e9a\u5e97", "\u6843\u5712\u5e02", "\u9f9c\u5c71\u5340", "\u6843\u5712\u5e02\u9f9c\u5c71\u5340\u6587\u8208\u8def55\u865f"),
    ("pbcafe-027", "\u5f7c\u5f97\u597d\u5496\u5561 \u6843\u5712\u5357\u5d01\u5e97", "\u6843\u5712\u5e02", "\u8606\u7af9\u5340", "\u6843\u5712\u5e02\u8606\u7af9\u5340\u4e2d\u6b63\u8def329\u865f"),
    ("pbcafe-028", "\u5f7c\u5f97\u597d\u5496\u5561 \u53f0\u5357\u5d07\u5fb7\u5e97", "\u53f0\u5357\u5e02", "\u6771\u5340", "\u53f0\u5357\u5e02\u6771\u5340\u5d07\u5fb7\u8def622\u865f"),
    ("pbcafe-029", "\u5f7c\u5f97\u597d\u5496\u5561 \u6843\u5712\u53f0\u9054\u96fb\u54e1\u5de5\u9910\u5ef3\uff08\u5b98\u65b9\u5c55\u5e97\u6b77\u7a0b\u63d0\u53ca\uff09", "\u6843\u5712\u5e02", "", ""),
    ("pbcafe-030", "\u5f85\u78ba\u8a8d\u9580\u5e02\uff08\u5b98\u65b92025\u5e7430\u5bb6\u8207Google/Maps\u53ef\u898b\u6e05\u55ae\u5dee\u984d\uff09", UNCONFIRMED, "", ""),
]


def google_search_url(query: str) -> str:
    return "https://www.google.com/search?q=" + quote_plus(query)


def maps_search_url(query: str) -> str:
    return "https://www.google.com/maps/search/" + quote_plus(query) + "?hl=zh-TW&gl=tw"


def provider_names(text: str) -> list[str]:
    providers = []
    patterns = [
        ("foodpanda", "foodpanda"),
        ("UberEats", "Uber Eats"),
        ("Uber Eats", "Uber Eats"),
        ("ubereats", "Uber Eats"),
        ("Nidin", "Nidin"),
        ("nidin.shop", "Nidin"),
        ("QuickClick", "QuickClick"),
        ("quickclick", "QuickClick"),
        ("LINE", "LINE"),
        ("lin.ee", "LINE"),
    ]
    lower = text.lower()
    for needle, name in patterns:
        if needle.lower() in lower and name not in providers:
            providers.append(name)
    return providers


async def extract_profile(page, query: str) -> dict:
    await page.goto(maps_search_url(query), wait_until="domcontentloaded", timeout=60000)
    await page.wait_for_timeout(4500)
    try:
        await page.get_by_text(query, exact=False).first.click(timeout=2000)
        await page.wait_for_timeout(3500)
    except Exception:
        pass
    links = await page.evaluate(
        r"""
        () => [...document.querySelectorAll('a,button,[role="button"]')].map((el) => {
            const text = (el.innerText || el.textContent || el.getAttribute('aria-label') || '').replace(/\s+/g, ' ').trim();
            return {text, href: el.href || '', aria: el.getAttribute('aria-label') || ''};
        }).filter((item) => item.text || item.href || item.aria)
        """
    )
    body = await page.locator("body").inner_text(timeout=10000)
    address = ""
    phone = ""
    website = ""
    order_url = ""
    for item in links:
        text = item.get("text", "")
        aria = item.get("aria", "")
        href = item.get("href", "")
        if ("地址:" in aria or text.startswith("\ue0c8")) and not address:
            address = re.sub(r"^\ue0c8\s*", "", text).strip()
            address = re.sub(r"^\d{3,5}", "", address).strip()
        if ("電話號碼:" in aria or text.startswith("\ue0b0")) and not phone:
            phone = re.sub(r"^\ue0b0\s*", "", text).strip()
        if ("網站:" in aria or "pbcafe.com.tw" in text or "facebook.com" in text) and href and not website:
            website = href
        if "\u7dda\u4e0a\u9ede\u9910" in text and "searchviewer" in href and not order_url:
            order_url = href
    status = "confirmed" if query in body or "\u5f7c\u5f97\u597d\u5496\u5561" in body else "needs_manual_review"
    if "\u6c38\u4e45\u6b47\u696d" in body:
        status = "closed_or_moved"
    return {
        "gmbUrl": page.url,
        "gmbStatus": status,
        "address": address,
        "phone": phone,
        "website": website,
        "orderUrl": order_url,
        "bodyText": body[:1200],
    }


async def inspect_order_panel(page, url: str) -> tuple[list[str], list[str], str]:
    if not url:
        return [], [], ""
    await page.goto(url, wait_until="domcontentloaded", timeout=60000)
    await page.wait_for_timeout(3500)
    modes = [("\u81ea\u53d6", "pickup"), ("\u904b\u9001", "delivery")]
    results = {"pickup": [], "delivery": []}
    for label, mode in modes:
        clicked = await page.evaluate(
            r"""
            (label) => {
                const el = [...document.querySelectorAll('button,[role="button"],a')]
                    .find((node) => (node.innerText || node.textContent || '').trim() === label);
                if (!el) return false;
                el.click();
                return true;
            }
            """,
            label,
        )
        await page.wait_for_timeout(2500 if clicked else 800)
        text = await page.locator("body").inner_text(timeout=10000)
        results[mode] = provider_names(text)
    return results["pickup"], results["delivery"], page.url


async def build() -> tuple[list[dict], dict]:
    profile_cache = {}
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            locale="zh-TW",
            timezone_id="Asia/Taipei",
            viewport={"width": 1365, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"
            ),
        )
        page = await context.new_page()
        order_page = await context.new_page()
        for store_id, name, city, _district, _address in STORE_SEEDS:
            if city == UNCONFIRMED or "Google/Maps" in name or "\u53f0\u9054\u96fb" in name:
                continue
            try:
                profile = await extract_profile(page, name)
                if profile.get("orderUrl"):
                    pickup, delivery, panel_url = await inspect_order_panel(order_page, profile["orderUrl"])
                    profile["gmbPickupProviders"] = pickup
                    profile["gmbDeliveryProviders"] = delivery
                    profile["gmbOrderPanelUrl"] = panel_url
                profile_cache[store_id] = profile
                print(json.dumps({"storeId": store_id, "name": name, "order": bool(profile.get("orderUrl"))}, ensure_ascii=False))
            except Exception as exc:
                profile_cache[store_id] = {"error": str(exc)}
                print(json.dumps({"storeId": store_id, "error": str(exc)}, ensure_ascii=False))
        await browser.close()

    stores = []
    for store_id, name, city, district, seed_address in STORE_SEEDS:
        profile = profile_cache.get(store_id, {})
        is_gap = city == UNCONFIRMED or "\u53f0\u9054\u96fb" in name
        address = profile.get("address") or seed_address
        phone = profile.get("phone") or ""
        pickup = profile.get("gmbPickupProviders", [])
        delivery = profile.get("gmbDeliveryProviders", [])
        ordering_systems = []
        panel_url = profile.get("gmbOrderPanelUrl") or profile.get("orderUrl") or ""
        for system in pickup:
            ordering_systems.append(
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
            ordering_systems.append(
                {
                    "system": system,
                    "sourceType": "gmb",
                    "orderMode": ["delivery"],
                    "evidenceUrl": panel_url,
                    "label": "Google Order delivery",
                    "confidence": "confirmed",
                }
            )
        if profile.get("orderUrl") and not ordering_systems:
            ordering_systems.append(
                {
                    "system": "Google Order entry",
                    "sourceType": "google",
                    "orderMode": ["unknown"],
                    "evidenceUrl": profile["orderUrl"],
                    "label": "Google Order entry, provider pending",
                    "confidence": "needs_manual_review",
                }
            )

        has_gmb_provider = any(claim["sourceType"] == "gmb" for claim in ordering_systems)
        gmb_status = profile.get("gmbStatus") or ("not_found" if is_gap else "confirmed")
        if has_gmb_provider:
            gmb_ordering_status = "confirmed"
        elif profile.get("orderUrl"):
            gmb_ordering_status = "button_confirmed_provider_pending"
        elif is_gap:
            gmb_ordering_status = "no_gmb_profile_match"
        else:
            gmb_ordering_status = "no_gmb_order_button"
        manual_reason = ""
        if is_gap:
            manual_reason = "Official franchise history states 30 Taiwan stores in 2025, but this store was not confirmed as a named Google Maps/GMB profile during bounded search."
        elif gmb_ordering_status == "button_confirmed_provider_pending":
            manual_reason = "Google Maps shows a blue online-order entry, but provider rows were not parsed in this run."
        elif gmb_ordering_status == "no_gmb_order_button":
            manual_reason = "Named Google Maps profile found, but no blue Google Order entry was visible in this bounded check."

        stores.append(
            {
                "brand": BRAND,
                "storeId": store_id,
                "storeName": name,
                "country": "Taiwan",
                "market": MARKET,
                "regionGroup": REGION_BY_CITY.get(city, UNCONFIRMED),
                "city": city,
                "county": city,
                "district": district,
                "address": address,
                "latitude": None,
                "longitude": None,
                "phone": phone,
                "hours": "",
                "officialSourceUrl": FRANCHISE_URL,
                "officialStoreUrl": "",
                "officialMapUrl": "",
                "googleSearchUrl": google_search_url(name + " " + address),
                "gmbUrl": profile.get("gmbUrl", ""),
                "gmbStatus": gmb_status,
                "gmbOrderingStatus": gmb_ordering_status,
                "sourceCoverage": {
                    "officialListed": True,
                    "gmbFound": gmb_status == "confirmed",
                    "googleFound": not is_gap,
                    "thirdPartyFound": bool(ordering_systems),
                },
                "orderingSystems": ordering_systems,
                "hasAnyOrderingSystem": bool(ordering_systems),
                "hasGmbOrderingSystem": has_gmb_provider or gmb_ordering_status == "button_confirmed_provider_pending",
                "manualReviewReason": manual_reason,
                "evidenceNotes": "Official site provides brand history and total count, not a store locator. Store-level records are built from Google/Maps discovery and Google Order panel checks where available.",
                "checkedAt": CHECKED_AT,
                "gmbOrderPanelUrl": panel_url,
                "gmbPickupProviders": pickup,
                "gmbDeliveryProviders": delivery,
                "gmbSignals": {
                    "buttonDetected": bool(profile.get("orderUrl")),
                    "providersParsed": has_gmb_provider,
                    "attemptCount": 1 if not is_gap else 0,
                    "maxAttempts": 1,
                    "panelUrl": panel_url,
                    "checkedAt": CHECKED_AT,
                    "checkMethod": "google_maps_profile_and_searchviewer_panel",
                    "matchQuality": "named_gmb_profile" if gmb_status == "confirmed" else "missing_named_gmb",
                    "notes": manual_reason,
                },
            }
        )

    summary = rebuild_summary(stores)
    return stores, summary


def count_systems(stores: list[dict], source_type: str | None = None, mode: str | None = None) -> dict:
    counts = Counter()
    for store in stores:
        systems = set()
        for claim in store.get("orderingSystems", []):
            if source_type and claim.get("sourceType") != source_type:
                continue
            if mode and mode not in claim.get("orderMode", []):
                continue
            systems.add(claim.get("system"))
        counts.update(system for system in systems if system)
    return dict(counts)


def rebuild_summary(stores: list[dict]) -> dict:
    official_count = len(stores)
    city_counts = {city: 0 for city in TAIWAN_CITIES}
    city_counts[UNCONFIRMED] = 0
    region_counts = {NORTH: 0, CENTRAL: 0, SOUTH: 0, EAST: 0, ISLANDS: 0, UNCONFIRMED: 0}
    for store in stores:
        city_counts[store["city"]] = city_counts.get(store["city"], 0) + 1
        region_counts[store["regionGroup"]] = region_counts.get(store["regionGroup"], 0) + 1
    all_counts = count_systems(stores)
    gmb_counts = count_systems(stores, source_type="gmb")
    systems = sorted(set(all_counts) | set(gmb_counts))
    return {
        "generatedAt": CHECKED_AT,
        "brand": BRAND,
        "brandSlug": BRAND_SLUG,
        "market": MARKET,
        "sitePath": "/brand-order-analysis/pbcafe/",
        "officialStoreCount": official_count,
        "gmbFoundCount": sum(1 for s in stores if s["sourceCoverage"]["gmbFound"]),
        "gmbMissingCount": sum(1 for s in stores if not s["sourceCoverage"]["gmbFound"]),
        "googleFoundCount": sum(1 for s in stores if s["sourceCoverage"]["googleFound"]),
        "thirdPartyFoundCount": sum(1 for s in stores if s["sourceCoverage"]["thirdPartyFound"]),
        "verificationGapCount": sum(1 for s in stores if s["manualReviewReason"]),
        "anyOrderingSystemCount": sum(1 for s in stores if s["hasAnyOrderingSystem"]),
        "anyOrderingSystemAdoptionRate": round(sum(1 for s in stores if s["hasAnyOrderingSystem"]) / official_count, 4),
        "googleOrderEntryCount": sum(1 for s in stores if s["hasGmbOrderingSystem"]),
        "googleOrderEntryRate": round(sum(1 for s in stores if s["hasGmbOrderingSystem"]) / official_count, 4),
        "gmbOrderingSystemCount": sum(1 for s in stores if s["hasGmbOrderingSystem"]),
        "gmbOrderingSystemAdoptionRate": round(sum(1 for s in stores if s["hasGmbOrderingSystem"]) / official_count, 4),
        "gmbCoverageGapCount": sum(1 for s in stores if s["gmbOrderingStatus"] not in ("confirmed", "button_confirmed_provider_pending")),
        "unknownOrderingSystemCount": sum(1 for s in stores if not s["hasAnyOrderingSystem"]),
        "cityCounts": city_counts,
        "regionCounts": region_counts,
        "allSourceSystemCounts": all_counts,
        "allSourcePickupSystemCounts": count_systems(stores, mode="pickup"),
        "allSourceDeliverySystemCounts": count_systems(stores, mode="delivery"),
        "gmbSystemCounts": gmb_counts,
        "gmbPickupSystemCounts": count_systems(stores, source_type="gmb", mode="pickup"),
        "gmbDeliverySystemCounts": count_systems(stores, source_type="gmb", mode="delivery"),
        "allSourceSystemAdoptionRates": {k: round(v / official_count, 4) for k, v in all_counts.items()},
        "gmbSystemAdoptionRates": {k: round(v / official_count, 4) for k, v in gmb_counts.items()},
        "systemComparison": [
            {
                "system": system,
                "allSourceStoreCount": all_counts.get(system, 0),
                "allSourceAdoptionRate": round(all_counts.get(system, 0) / official_count, 4),
                "gmbStoreCount": gmb_counts.get(system, 0),
                "gmbAdoptionRate": round(gmb_counts.get(system, 0) / official_count, 4),
                "countGap": all_counts.get(system, 0) - gmb_counts.get(system, 0),
                "percentagePointGap": round((all_counts.get(system, 0) - gmb_counts.get(system, 0)) / official_count, 4),
            }
            for system in systems
        ],
        "gmbStatusCounts": dict(Counter(s["gmbStatus"] for s in stores)),
        "gmbOrderingStatusCounts": dict(Counter(s["gmbOrderingStatus"] for s in stores)),
        "sourceCoverageCounts": {
            key: sum(1 for s in stores if s["sourceCoverage"].get(key))
            for key in ["officialListed", "gmbFound", "googleFound", "thirdPartyFound"]
        },
        "source": {
            "officialWebsite": OFFICIAL_URL,
            "officialFranchisePage": FRANCHISE_URL,
            "officialStoreCountEvidence": "The official franchise history says Peter Better Cafe reached 30 stores in 2025. No official store locator was found.",
            "googleMapsDiscovery": "Google Maps public search was used to identify named Taiwan store profiles.",
            "notes": "Google Order providers are counted only when provider rows were visible inside opened searchviewer panels.",
        },
        "notes": [
            "Official store denominator is 30 based on the brand franchise page's 2025 expansion history.",
            "The official website has no public store locator in this run; store-level population is therefore a Google/Maps-derived working list with explicit unresolved gaps.",
            "Closed or renamed historical stores such as Zhonghe Far Eastern and Xinzhuang Xintai were excluded from the active population.",
            "Google Order entry coverage and provider rows are separated from all-source ordering evidence.",
        ],
    }


def write_outputs(stores: list[dict], summary: dict) -> None:
    stores_payload = {
        "generatedAt": CHECKED_AT,
        "brand": BRAND,
        "source": summary["source"],
        "stores": stores,
    }
    (DATA / "stores.json").write_text(json.dumps(stores_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (DATA / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    with (DATA / "stores.csv").open("w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=[
                "storeId",
                "storeName",
                "regionGroup",
                "city",
                "district",
                "address",
                "phone",
                "gmbStatus",
                "gmbOrderingStatus",
                "systems",
                "gmbProviders",
                "gmbUrl",
                "manualReviewReason",
            ],
        )
        writer.writeheader()
        for store in stores:
            writer.writerow(
                {
                    "storeId": store["storeId"],
                    "storeName": store["storeName"],
                    "regionGroup": store["regionGroup"],
                    "city": store["city"],
                    "district": store["district"],
                    "address": store["address"],
                    "phone": store["phone"],
                    "gmbStatus": store["gmbStatus"],
                    "gmbOrderingStatus": store["gmbOrderingStatus"],
                    "systems": ", ".join(sorted({c["system"] for c in store["orderingSystems"]})),
                    "gmbProviders": ", ".join(sorted({c["system"] for c in store["orderingSystems"] if c["sourceType"] == "gmb"})),
                    "gmbUrl": store["gmbUrl"],
                    "manualReviewReason": store["manualReviewReason"],
                }
            )
    inline = f"window.DAMING_DATA = {json.dumps({'storesPayload': stores_payload, 'summary': summary}, ensure_ascii=False)};\n"
    (OUT / "data-inline.js").write_text(inline, encoding="utf-8")
    html = """<!doctype html>
<html lang="zh-Hant">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>彼得好咖啡點餐系統總覽</title>
  <link rel="stylesheet" href="../assets/styles.css?v=31" />
</head>
<body>
  <header class="topbar">
    <div>
      <p class="eyebrow">Brand Order Analysis</p>
      <h1>彼得好咖啡點餐系統總覽</h1>
      <p class="subhead">官方展店總數、Google/Maps 門市盤點、Google Order 供應商與待人工複核缺口。<span class="version">pbcafe local audit</span></p>
    </div>
    <div class="meta">
      <span id="generatedAt">Loading</span>
      <a href="data/stores.csv">CSV</a>
      <a href="data/summary.json">Summary JSON</a>
    </div>
  </header>

  <main>
    <section class="controls">
      <div class="segmented" id="regionFilters"></div>
      <label>城市<select id="cityFilter"></select></label>
      <label>系統<select id="systemFilter"></select></label>
      <label>Google Order 狀態<select id="gmbFilter"><option value="all">全部</option><option value="confirmed">Google Order 有供應商</option><option value="gap">Google Order 供應商缺口</option><option value="no_gmb_found">GMB/Maps 未找到</option></select></label>
      <label class="search">搜尋門市<input id="searchInput" type="search" placeholder="門市、地址、城市" /></label>
    </section>

    <section class="insight-strip" id="insightStrip"></section>

    <section class="panel">
      <div class="section-title">
        <div><p class="eyebrow">1. Store Footprint</p><h2>品牌門市總覽</h2></div>
        <p>官方網站未提供門市清單；本版以官方加盟頁 2025 年 30 家門市作為分母，逐店資料來自 Google/Maps 可見門市與公開點餐面板。</p>
      </div>
      <div class="kpi-grid" id="storeKpis"></div>
      <div class="split map-layout">
        <div>
          <h3>台灣門市地圖</h3>
          <p class="map-source">地圖顯示已定位城市；官方提及但未能在 Google/Maps 確認的門市列於明細表。</p>
          <div class="taiwan-map" id="taiwanMap"></div>
        </div>
        <div><h3>城市排行</h3><div class="bars" id="cityBars"></div></div>
      </div>
    </section>

    <section class="panel">
      <div class="section-title">
        <div><p class="eyebrow">2. All Sources</p><h2>品牌整體點餐系統</h2></div>
        <p>本版已計入公開 Google Order 面板中實際可見供應商；未打開或未解析的藍色點餐入口保留為待複核。</p>
      </div>
      <div class="kpi-grid" id="allSourceKpis"></div>
      <div class="split">
        <div><h3>全來源自取系統</h3><div class="bars" id="pickupBars"></div></div>
        <div><h3>全來源外送系統</h3><div class="bars" id="deliveryBars"></div></div>
      </div>
      <div class="split compact">
        <div><h3>大區導入率</h3><div class="matrix" id="regionMatrix"></div></div>
        <div><h3>解讀</h3><p class="note">Google Maps 門市卡上的「線上點餐」只算入口；foodpanda / Uber Eats 等供應商必須在打開 Google Order 面板後看見供應商列才計入 GMB provider。</p></div>
      </div>
    </section>

    <section class="panel warning">
      <div class="section-title">
        <div><p class="eyebrow">3. Google Order</p><h2>Google Order 供應商總覽</h2></div>
        <p>只計入 Google 商家頁藍色「線上點餐」按鈕點入後，在自取或運送面板實際看到的供應商。</p>
      </div>
      <div class="kpi-grid" id="gmbKpis"></div>
      <div class="split">
        <div><h3>Google Order 自取供應商</h3><div class="bars" id="gmbPickupBars"></div></div>
        <div><h3>Google Order 外送供應商</h3><div class="bars" id="gmbDeliveryBars"></div></div>
      </div>
    </section>

    <section class="panel">
      <div class="section-title"><div><p class="eyebrow">4. Comparison</p><h2>全來源 vs Google Order 供應商</h2></div></div>
      <div class="table-wrap"><table><thead><tr><th>系統</th><th>全來源門市</th><th>全來源導入率</th><th>Google Order 供應商門市</th><th>Google Order 供應商覆蓋率</th><th>差距</th></tr></thead><tbody id="comparisonRows"></tbody></table></div>
    </section>

    <section class="panel">
      <div class="section-title"><div><p class="eyebrow">5. Store Details</p><h2>門市明細</h2></div><p id="detailCount"></p></div>
      <div class="table-wrap"><table class="details"><thead><tr><th>門市</th><th>區域</th><th>地址</th><th>全來源系統</th><th>Google Order 供應商</th><th>證據 / 複核</th></tr></thead><tbody id="storeRows"></tbody></table></div>
    </section>
  </main>

  <script src="../assets/taiwan-map.js?v=31"></script>
  <script src="data-inline.js"></script>
  <script src="../assets/app.js?v=31"></script>
</body>
</html>
"""
    (OUT / "index.html").write_text(html, encoding="utf-8")


async def main() -> None:
    stores, summary = await build()
    write_outputs(stores, summary)
    print(json.dumps({"stores": len(stores), "summary": summary}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
