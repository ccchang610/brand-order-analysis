from __future__ import annotations

import asyncio
import csv
import json
import re
from collections import Counter
from datetime import date
from pathlib import Path
from urllib.parse import quote_plus, urlparse

from playwright.async_api import async_playwright


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "toastman"
DATA = OUT / "data"
DATA.mkdir(parents=True, exist_ok=True)

BRAND = "吐司男 TOAST MAN"
BRAND_SLUG = "toastman"
MARKET = "Taiwan"
OFFICIAL_URL = "https://toastman.tw/"
STORE_URL = "https://toastman.tw/store/"
CHECKED_AT = date.today().isoformat()

ALL = "全台"
NORTH = "北部"
CENTRAL = "中部"
SOUTH = "南部"
EAST = "東部"
ISLANDS = "離島"

TAIWAN_CITIES = [
    "基隆市",
    "台北市",
    "新北市",
    "桃園市",
    "新竹市",
    "新竹縣",
    "苗栗縣",
    "台中市",
    "彰化縣",
    "南投縣",
    "雲林縣",
    "嘉義縣",
    "嘉義市",
    "台南市",
    "高雄市",
    "屏東縣",
    "宜蘭縣",
    "花蓮縣",
    "台東縣",
    "澎湖縣",
    "金門縣",
    "連江縣",
]

REGION_BY_CITY = {
    **{city: NORTH for city in TAIWAN_CITIES[:7] + ["宜蘭縣"]},
    **{city: CENTRAL for city in TAIWAN_CITIES[7:11]},
    **{city: SOUTH for city in TAIWAN_CITIES[11:16]},
    **{city: EAST for city in ["花蓮縣", "台東縣"]},
    **{city: ISLANDS for city in ["澎湖縣", "金門縣", "連江縣"]},
}

# Official store population source: the brand store page currently exposes store
# history as text, while the "營業據點" section is rendered without store text.
# Exclude Hong Kong stores and the explicitly marked 誠品南西快閃店.
STORE_SEEDS = [
    ("toastman-001", "吐司男 台中學士創始店", "台中市", "北區"),
    ("toastman-002", "吐司男 台中中科店", "台中市", "西屯區"),
    ("toastman-003", "吐司男 彰化中山店", "彰化縣", "彰化市"),
    ("toastman-004", "吐司男 台北南京店", "台北市", "松山區"),
    ("toastman-005", "吐司男 嘉義民生店", "嘉義市", "西區"),
    ("toastman-006", "吐司男 台中精科店", "台中市", "南屯區"),
    ("toastman-007", "吐司男 台中逢甲店", "台中市", "西屯區"),
    ("toastman-008", "吐司男 新北板橋新海店", "新北市", "板橋區"),
    ("toastman-009", "吐司男 台中沙鹿北勢東店", "台中市", "沙鹿區"),
    ("toastman-010", "吐司男 台中大里益民店", "台中市", "大里區"),
    ("toastman-011", "吐司男 台中黎明店", "台中市", "南屯區"),
    ("toastman-012", "吐司男 新竹埔頂店", "新竹市", "東區"),
    ("toastman-013", "吐司男 宜蘭大學店", "宜蘭縣", "宜蘭市"),
    ("toastman-014", "吐司男 台南金華店", "台南市", "南區"),
    ("toastman-015", "吐司男 桃園楊梅店", "桃園市", "楊梅區"),
    ("toastman-016", "吐司男 高雄承億店", "高雄市", "前鎮區"),
]

MANUAL_CLOSED_STORE_IDS = {
    # User-confirmed Google Business Profile screenshot: 新竹埔頂店 shows 永久歇業.
    "toastman-012",
}


def google_search_url(query: str) -> str:
    return "https://www.google.com/search?q=" + quote_plus(query)


def maps_search_url(query: str) -> str:
    return "https://www.google.com/maps/search/" + quote_plus(query) + "?hl=zh-TW&gl=tw"


def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def normalize_provider(text: str) -> list[str]:
    value = (text or "").lower()
    providers = []
    tests = [
        ("nidin", "Nidin"),
        ("order.nidin.shop", "Nidin"),
        ("nidin.shop", "Nidin"),
        ("uber eats", "Uber Eats"),
        ("ubereats", "Uber Eats"),
        ("foodpanda", "foodpanda"),
        ("line", "LINE"),
        ("lin.ee", "LINE"),
        ("quickclick", "QuickClick"),
        ("快一點", "QuickClick"),
    ]
    for needle, provider in tests:
        if needle in value and provider not in providers:
            providers.append(provider)
    return providers


def platform_from_url_or_text(href: str, text: str = "") -> str:
    haystack = f"{href} {text}".lower()
    if "foodpanda" in haystack:
        return "foodpanda"
    if "ubereats" in haystack or "uber eats" in haystack:
        return "Uber Eats"
    if "nidin" in haystack:
        return "Nidin"
    if "lin.ee" in haystack or "line.me" in haystack or "line@" in haystack:
        return "LINE"
    if "quickclick" in haystack or "快一點" in haystack:
        return "QuickClick"
    if "instagram" in haystack:
        return "Instagram"
    return ""


async def extract_profile(page, query: str) -> dict:
    await page.goto(maps_search_url(query), wait_until="domcontentloaded", timeout=60000)
    await page.wait_for_timeout(4500)
    try:
        await page.get_by_text("同意", exact=True).click(timeout=1200)
    except Exception:
        pass
    try:
        await page.get_by_role("heading", name=re.compile("吐司男")).first.click(timeout=2500)
        await page.wait_for_timeout(2800)
    except Exception:
        pass

    body = clean_text(await page.locator("body").inner_text(timeout=12000))
    title = ""
    try:
        title = clean_text(await page.locator("h1").first.inner_text(timeout=3000))
    except Exception:
        title = ""

    items = await page.evaluate(
        r"""
        () => [...document.querySelectorAll('a,button,[role="button"]')].map((el) => {
          const text = (el.innerText || el.textContent || '').replace(/\s+/g, ' ').trim();
          return {
            text,
            aria: el.getAttribute('aria-label') || '',
            href: el.href || ''
          };
        }).filter((item) => item.text || item.aria || item.href)
        """
    )

    address = ""
    phone = ""
    website = ""
    order_urls = []
    third_party_links = []

    for item in items:
        text = clean_text(item.get("text", ""))
        aria = clean_text(item.get("aria", ""))
        href = item.get("href", "")
        label = f"{aria} {text}"
        if not address and ("地址:" in aria or "地址：" in aria):
            address = clean_text(re.sub(r"^地址[:：]\s*", "", aria))
        if not phone and ("電話:" in aria or "電話：" in aria):
            phone = clean_text(re.sub(r"^電話[:：]\s*", "", aria))
        if href and not website and ("toastman.tw" in href or "nidin" in href or "lin.ee" in href or "line.me" in href):
            website = href
        if href and ("searchviewer" in href or "order" in href.lower()) and ("訂餐" in label or "外送" in label or "自取" in label or "online" in label.lower()):
            order_urls.append(href)
        platform = platform_from_url_or_text(href, label)
        if href and platform:
            third_party_links.append({"platform": platform, "href": href, "label": label})

    # Some Maps pages expose the order control as a button. Click visible order-like
    # controls and record the resulting searchviewer URL when it appears.
    for word in ["線上訂餐", "訂餐", "下單", "自取", "外送"]:
        try:
            await page.get_by_text(word, exact=False).first.click(timeout=1800)
            await page.wait_for_timeout(2600)
            if "searchviewer" in page.url:
                order_urls.append(page.url)
                await page.go_back(wait_until="domcontentloaded", timeout=15000)
                await page.wait_for_timeout(1000)
                break
        except Exception:
            pass

    status = "confirmed" if ("吐司男" in body or "TOAST MAN" in body.upper() or "Toast Man" in body) else "needs_manual_review"
    if "永久歇業" in body or "已歇業" in body:
        status = "closed_or_moved"
    if title and "吐司男" not in title and "TOAST" not in title.upper():
        status = "needs_manual_review"

    return {
        "title": title,
        "address": address,
        "phone": phone,
        "website": website,
        "gmbUrl": page.url,
        "gmbStatus": status,
        "bodyText": body[:1600],
        "orderUrls": list(dict.fromkeys(order_urls)),
        "thirdPartyLinks": third_party_links,
    }


async def inspect_order_panel(page, url: str) -> dict:
    result = {"pickup": [], "delivery": [], "links": [], "panelUrl": url, "buttonDetected": False}
    if not url:
        return result
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(3500)
    except Exception:
        return result

    result["panelUrl"] = page.url
    result["buttonDetected"] = True
    for label, mode in [("自取", "pickup"), ("外送", "delivery"), ("運送", "delivery")]:
        try:
            await page.get_by_text(label, exact=False).first.click(timeout=1800)
            await page.wait_for_timeout(2200)
        except Exception:
            pass
        try:
            text = await page.locator("body").inner_text(timeout=10000)
        except Exception:
            text = ""
        for provider in normalize_provider(text):
            if provider not in result[mode]:
                result[mode].append(provider)
        links = await page.evaluate(
            r"""
            () => [...document.querySelectorAll('a')].map((a) => ({
              href: a.href || '',
              text: (a.innerText || a.textContent || '').replace(/\s+/g, ' ').trim()
            })).filter((item) => item.href)
            """
        )
        for item in links:
            platform = platform_from_url_or_text(item.get("href", ""), item.get("text", ""))
            if not platform:
                continue
            result["links"].append(
                {
                    "platform": platform,
                    "kind": "marketplace" if platform in {"foodpanda", "Uber Eats", "Nidin", "QuickClick"} else "order_link",
                    "sourceType": "gmb_order_panel",
                    "orderMode": [mode],
                    "label": clean_text(item.get("text", "")) or platform,
                    "href": item.get("href", ""),
                    "panelUrl": result["panelUrl"],
                    "observedAt": CHECKED_AT,
                    "confidence": "confirmed",
                }
            )
    unique_links = {}
    for link in result["links"]:
        key = (link["platform"], link["href"])
        if key in unique_links:
            unique_links[key]["orderMode"] = sorted(set(unique_links[key]["orderMode"]) | set(link["orderMode"]))
        else:
            unique_links[key] = link
    result["links"] = list(unique_links.values())
    return result


def source_type_for_link(platform: str) -> str:
    if platform == "LINE":
        return "line"
    return "marketplace"


def is_active_store(store: dict) -> bool:
    return store.get("gmbStatus") != "closed_or_moved" and store.get("storeId") not in MANUAL_CLOSED_STORE_IDS


def active_stores(stores: list[dict]) -> list[dict]:
    return [store for store in stores if is_active_store(store)]


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


def count_google_order_options(stores: list[dict], mode: str | None = None) -> dict:
    counts = Counter()
    for store in stores:
        systems = set()
        for claim in store.get("orderingSystems", []):
            if claim.get("sourceType") != "gmb":
                continue
            if mode and mode not in claim.get("orderMode", []):
                continue
            systems.add(claim.get("system"))
        for link in store.get("gmbOrderLinks", []):
            modes = link.get("orderMode") or []
            if mode and mode not in modes:
                continue
            systems.add(link.get("platform"))
        counts.update(system for system in systems if system)
    return dict(counts)


def rebuild_summary(stores: list[dict]) -> dict:
    official_count = len(stores)
    city_counts = {city: 0 for city in TAIWAN_CITIES}
    region_counts = {NORTH: 0, CENTRAL: 0, SOUTH: 0, EAST: 0, ISLANDS: 0}
    for store in stores:
        city_counts[store["city"]] = city_counts.get(store["city"], 0) + 1
        region_counts[store["regionGroup"]] = region_counts.get(store["regionGroup"], 0) + 1
    all_counts = count_systems(stores)
    gmb_counts = count_systems(stores, source_type="gmb")
    gmb_option_counts = count_google_order_options(stores)
    systems = sorted(set(all_counts) | set(gmb_counts) | set(gmb_option_counts))
    any_count = sum(1 for s in stores if s["hasAnyOrderingSystem"])
    gmb_entry_count = sum(1 for s in stores if s["hasGmbOrderingSystem"])
    return {
        "generatedAt": CHECKED_AT,
        "brand": BRAND,
        "brandSlug": BRAND_SLUG,
        "market": MARKET,
        "sitePath": "/brand-order-analysis/toastman/",
        "officialStoreCount": official_count,
        "gmbFoundCount": sum(1 for s in stores if s["sourceCoverage"]["gmbFound"]),
        "gmbMissingCount": sum(1 for s in stores if not s["sourceCoverage"]["gmbFound"]),
        "googleFoundCount": sum(1 for s in stores if s["sourceCoverage"]["googleFound"]),
        "thirdPartyFoundCount": sum(1 for s in stores if s["sourceCoverage"]["thirdPartyFound"]),
        "verificationGapCount": sum(1 for s in stores if s["manualReviewReason"]),
        "anyOrderingSystemCount": any_count,
        "anyOrderingSystemAdoptionRate": round(any_count / official_count, 4),
        "googleOrderEntryCount": gmb_entry_count,
        "googleOrderEntryRate": round(gmb_entry_count / official_count, 4),
        "gmbOrderingSystemCount": gmb_entry_count,
        "gmbOrderingSystemAdoptionRate": round(gmb_entry_count / official_count, 4),
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
        "gmbOrderOptionCounts": gmb_option_counts,
        "gmbOrderPickupOptionCounts": count_google_order_options(stores, mode="pickup"),
        "gmbOrderDeliveryOptionCounts": count_google_order_options(stores, mode="delivery"),
        "allSourceSystemAdoptionRates": {k: round(v / official_count, 4) for k, v in all_counts.items()},
        "gmbSystemAdoptionRates": {k: round(v / official_count, 4) for k, v in gmb_counts.items()},
        "gmbOrderOptionAdoptionRates": {k: round(v / official_count, 4) for k, v in gmb_option_counts.items()},
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
            "officialStorePage": STORE_URL,
            "officialStoreCountEvidence": "Official store page text lists Taiwan milestone stores through 2024; the live 營業據點 section exposes only region headings in HTML during this run.",
            "googleMapsDiscovery": "Google Maps public search was used to find named Taiwan store profiles and visible order entries.",
            "notes": "Google Order provider rows are counted only when observed in an opened Google order/searchviewer panel. Other provider links visible from Maps/search are counted as all-source evidence, not strict GMB provider evidence.",
        },
        "notes": [
            "Official denominator is 16 Taiwan stores from the brand store page milestone text, excluding Hong Kong stores and the explicitly marked 誠品南西快閃店.",
            "The current official 營業據點 section does not expose store names or addresses in the page text; Google/Maps is therefore used to enrich address and ordering evidence.",
            "Blocked, ambiguous, closed, or no-button Google Order checks are counted as coverage gaps, not proof of no ordering system.",
            "Visible Google Order panel links are preserved in gmbOrderLinks and included in Google Order option charts without changing strict provider-row counts.",
        ],
    }


async def build() -> tuple[list[dict], dict]:
    profiles = {}
    panels = {}
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
        for store_id, store_name, city, district in STORE_SEEDS:
            try:
                profile = await extract_profile(page, store_name)
                profiles[store_id] = profile
                panel_url = profile["orderUrls"][0] if profile.get("orderUrls") else ""
                if panel_url:
                    panels[store_id] = await inspect_order_panel(order_page, panel_url)
                print(json.dumps({"storeId": store_id, "query": store_name, "gmbStatus": profile.get("gmbStatus"), "order": bool(panel_url)}, ensure_ascii=False))
            except Exception as exc:
                profiles[store_id] = {"error": str(exc), "gmbStatus": "unavailable_or_blocked", "gmbUrl": ""}
                print(json.dumps({"storeId": store_id, "error": str(exc)}, ensure_ascii=False))
        await browser.close()

    stores = []
    for store_id, seed_name, city, district in STORE_SEEDS:
        profile = profiles.get(store_id, {})
        panel = panels.get(store_id, {"pickup": [], "delivery": [], "links": [], "panelUrl": ""})
        ordering_systems = []
        panel_url = panel.get("panelUrl") or (profile.get("orderUrls") or [""])[0]

        for mode in ["pickup", "delivery"]:
            for system in panel.get(mode, []):
                ordering_systems.append(
                    {
                        "system": system,
                        "sourceType": "gmb",
                        "orderMode": [mode],
                        "evidenceUrl": panel_url,
                        "label": f"Google Order {mode}",
                        "confidence": "confirmed",
                    }
                )

        gmb_status = profile.get("gmbStatus", "needs_manual_review")
        for link in profile.get("thirdPartyLinks", []):
            if gmb_status == "closed_or_moved":
                continue
            platform = link["platform"]
            if any(c["system"] == platform for c in ordering_systems):
                continue
            ordering_systems.append(
                {
                    "system": platform,
                    "sourceType": source_type_for_link(platform),
                    "orderMode": ["unknown"],
                    "evidenceUrl": link["href"],
                    "label": clean_text(link.get("label", "")) or platform,
                    "confidence": "partial",
                }
            )

        has_gmb_provider = any(claim["sourceType"] == "gmb" for claim in ordering_systems)
        has_named_gmb = gmb_status == "confirmed"
        if has_gmb_provider:
            gmb_ordering_status = "confirmed"
        elif profile.get("orderUrls"):
            gmb_ordering_status = "button_confirmed_provider_pending"
        elif gmb_status == "closed_or_moved":
            gmb_ordering_status = "needs_manual_review"
        elif gmb_status in {"confirmed", "needs_manual_review"}:
            gmb_ordering_status = "no_gmb_order_button" if has_named_gmb else "needs_manual_review"
        else:
            gmb_ordering_status = "unavailable_or_blocked"

        manual_reason = ""
        if gmb_status == "closed_or_moved":
            manual_reason = "Google Maps indicated the profile may be closed or moved; keep in manual review against official milestone population."
        elif not has_named_gmb:
            manual_reason = "A highly similar named Google Maps profile was not confidently confirmed in this bounded run."
        elif gmb_ordering_status == "button_confirmed_provider_pending":
            manual_reason = "Google Maps exposed an order entry, but provider rows were not safely parsed from the opened panel."
        elif gmb_ordering_status == "no_gmb_order_button":
            manual_reason = "Named Google Maps profile was found, but no blue Google Order entry was visible in this bounded check."

        profile_title = profile.get("title") or ""
        display_name = profile_title if ("吐司男" in profile_title or "TOAST" in profile_title.upper()) else seed_name
        stores.append(
            {
                "brand": BRAND,
                "storeId": store_id,
                "storeName": display_name,
                "seedName": seed_name,
                "country": "Taiwan",
                "market": MARKET,
                "regionGroup": REGION_BY_CITY.get(city, ""),
                "city": city,
                "county": city,
                "district": district,
                "address": profile.get("address", ""),
                "latitude": None,
                "longitude": None,
                "phone": profile.get("phone", ""),
                "hours": "",
                "officialSourceUrl": STORE_URL,
                "officialStoreUrl": "",
                "officialMapUrl": "",
                "googleSearchUrl": google_search_url(seed_name),
                "gmbUrl": profile.get("gmbUrl", ""),
                "gmbStatus": gmb_status,
                "gmbOrderingStatus": gmb_ordering_status,
                "sourceCoverage": {
                    "officialListed": True,
                    "gmbFound": has_named_gmb,
                    "googleFound": gmb_status in {"confirmed", "needs_manual_review", "closed_or_moved"},
                    "thirdPartyFound": bool(ordering_systems),
                },
                "orderingSystems": ordering_systems,
                "hasAnyOrderingSystem": bool(ordering_systems),
                "hasGmbOrderingSystem": has_gmb_provider or gmb_ordering_status == "button_confirmed_provider_pending",
                "manualReviewReason": manual_reason,
                "evidenceNotes": "Official page provides milestone store names; Google Maps/Google Order bounded checks enrich current address and order evidence.",
                "checkedAt": CHECKED_AT,
                "gmbOrderPanelUrl": panel_url,
                "gmbPickupProviders": panel.get("pickup", []),
                "gmbDeliveryProviders": panel.get("delivery", []),
                "gmbOrderLinks": panel.get("links", []),
                "gmbSignals": {
                    "buttonDetected": bool(profile.get("orderUrls")),
                    "providersParsed": has_gmb_provider,
                    "attemptCount": 1,
                    "maxAttempts": 1,
                    "panelUrl": panel_url,
                    "checkedAt": CHECKED_AT,
                    "checkMethod": "google_maps_profile_and_order_panel_bounded",
                    "matchQuality": "named_gmb_profile" if has_named_gmb else "needs_manual_review",
                    "storeContext": "street_front",
                    "notes": manual_reason,
                },
            }
        )

    stores = active_stores(stores)
    summary = rebuild_summary(stores)
    return stores, summary


def write_outputs(stores: list[dict], summary: dict) -> None:
    stores = active_stores(stores)
    if summary.get("officialStoreCount") != len(stores):
        summary = rebuild_summary(stores)
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
                "seedName",
                "regionGroup",
                "city",
                "district",
                "address",
                "phone",
                "gmbStatus",
                "gmbOrderingStatus",
                "systems",
                "gmbProviders",
                "gmbOrderLinks",
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
                    "seedName": store["seedName"],
                    "regionGroup": store["regionGroup"],
                    "city": store["city"],
                    "district": store["district"],
                    "address": store["address"],
                    "phone": store["phone"],
                    "gmbStatus": store["gmbStatus"],
                    "gmbOrderingStatus": store["gmbOrderingStatus"],
                    "systems": ", ".join(sorted({c["system"] for c in store["orderingSystems"]})),
                    "gmbProviders": ", ".join(sorted({c["system"] for c in store["orderingSystems"] if c["sourceType"] == "gmb"})),
                    "gmbOrderLinks": ", ".join(sorted({f"{link.get('platform')}: {link.get('href')}" for link in store.get("gmbOrderLinks", []) if link.get("href")})),
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
  <title>吐司男點餐系統總覽</title>
  <link rel="stylesheet" href="../assets/styles.css?v=34" />
</head>
<body>
  <header class="topbar">
    <div>
      <p class="eyebrow">Brand Order Analysis</p>
      <h1>吐司男點餐系統總覽</h1>
      <p class="subhead">以官網門市頁品牌歷程列出的台灣門市為基準，彙整 Google/Maps、Google Order、Nidin、Uber Eats、foodpanda、LINE、QuickClick 等公開點餐證據。<span class="version">toastman local audit</span></p>
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
      <label>Google Order 狀態<select id="gmbFilter"><option value="all">全部</option><option value="confirmed">Google Order 有證據</option><option value="gap">Google Order 證據缺口</option><option value="no_gmb_found">GMB/Maps 未找到</option></select></label>
      <label class="search">搜尋門市<input id="searchInput" type="search" placeholder="門市、地址、城市" /></label>
    </section>

    <section class="insight-strip" id="insightStrip"></section>

    <section class="panel">
      <div class="section-title">
        <div><p class="eyebrow">1. Store Footprint</p><h2>官方門市與地理分布</h2></div>
        <p>官網目前可讀文字提供品牌歷程與台灣門市名稱；營業據點區塊在 HTML 中僅露出北/中/南區標題，因此地址與 GMB 狀態以 Google/Maps bounded check 補強。</p>
      </div>
      <div class="kpi-grid" id="storeKpis"></div>
      <div class="split map-layout">
        <div>
          <h3>台灣門市地圖</h3>
          <p class="map-source">所有城市維持 22 縣市框架，0 代表本次官方種子未列該縣市門市。</p>
          <div class="taiwan-map" id="taiwanMap"></div>
        </div>
        <div><h3>城市排行</h3><div class="bars" id="cityBars"></div></div>
      </div>
    </section>

    <section class="panel">
      <div class="section-title">
        <div><p class="eyebrow">2. All Sources</p><h2>全來源點餐系統</h2></div>
        <p>全來源證據包含 Google/Maps 上可見的點餐、平台或 LINE/Nidin 連結；這些不會自動轉成 Google Order provider row。</p>
      </div>
      <div class="kpi-grid" id="allSourceKpis"></div>
      <div class="split">
        <div><h3>自取系統</h3><div class="bars" id="pickupBars"></div></div>
        <div><h3>外送系統</h3><div class="bars" id="deliveryBars"></div></div>
      </div>
      <div class="split compact">
        <div><h3>區域導入率</h3><div class="matrix" id="regionMatrix"></div></div>
        <div><h3>判讀說明</h3><p class="note">Google Order provider 僅在開啟藍色點餐流程後、面板內可見 provider row 時才計入；一般 Maps 網站列或有機結果只作為全來源證據。</p></div>
      </div>
    </section>

    <section class="panel warning">
      <div class="section-title">
        <div><p class="eyebrow">3. Google Order</p><h2>Google Order provider/link 視圖</h2></div>
        <p>下列統計保留 strict provider row 與面板可見連結兩個層次。證據缺口代表未讀到 Google Order provider，不等於門市沒有點餐系統。</p>
      </div>
      <div class="kpi-grid" id="gmbKpis"></div>
      <div class="split">
        <div><h3>Google Order 自取選項</h3><div class="bars" id="gmbPickupBars"></div></div>
        <div><h3>Google Order 外送選項</h3><div class="bars" id="gmbDeliveryBars"></div></div>
      </div>
    </section>

    <section class="panel">
      <div class="section-title"><div><p class="eyebrow">4. Comparison</p><h2>全來源 vs Google Order provider</h2></div></div>
      <div class="table-wrap"><table><thead><tr><th>系統</th><th>全來源門市</th><th>全來源率</th><th>Google Order provider 門市</th><th>Google Order provider 率</th><th>缺口</th></tr></thead><tbody id="comparisonRows"></tbody></table></div>
    </section>

    <section class="panel">
      <div class="section-title"><div><p class="eyebrow">5. Store Details</p><h2>門市明細</h2></div><p id="detailCount"></p></div>
      <div class="table-wrap"><table class="details"><thead><tr><th>門市</th><th>區域</th><th>地址</th><th>全來源點餐</th><th>Google Order 證據</th><th>連結 / 複核</th></tr></thead><tbody id="storeRows"></tbody></table></div>
    </section>
  </main>

  <script src="../assets/taiwan-map.js?v=34"></script>
  <script src="data-inline.js"></script>
  <script src="../assets/app.js?v=34"></script>
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
