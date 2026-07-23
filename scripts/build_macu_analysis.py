from __future__ import annotations

import csv
import html
import json
import re
import ssl
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "macu"
DATA = OUT / "data"

BRAND = "麻古茶坊 MACU Tea"
BRAND_SLUG = "macu"
MARKET = "Taiwan"
OFFICIAL_WEBSITE = "https://www.macutea.com.tw/"
STORE_URL = "https://www.macutea.com.tw/shop.php"
CHECKED_AT = date.today().isoformat()

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"
    ),
    "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
}

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
    "嘉義市",
    "嘉義縣",
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
    **{city: "北部" for city in ["基隆市", "台北市", "新北市", "桃園市", "新竹市", "新竹縣", "苗栗縣", "宜蘭縣"]},
    **{city: "中部" for city in ["台中市", "彰化縣", "南投縣", "雲林縣"]},
    **{city: "南部" for city in ["嘉義市", "嘉義縣", "台南市", "高雄市", "屏東縣"]},
    **{city: "東部" for city in ["花蓮縣", "台東縣"]},
    **{city: "離島" for city in ["澎湖縣", "金門縣", "連江縣"]},
}
REGIONS = ["北部", "中部", "南部", "東部", "離島"]

PLATFORM_CANDIDATES = [
    {"platform": "Nidin", "url": "https://order.nidin.shop/brand/macu", "sourceType": "third_party"},
    {"platform": "Nidin", "url": "https://order.nidin.shop/brand/macutea", "sourceType": "third_party"},
    {"platform": "Uber Eats", "url": "https://www.ubereats.com/tw/brand/macu", "sourceType": "marketplace"},
    {"platform": "foodpanda", "url": "https://www.foodpanda.com.tw/search?q=%E9%BA%BB%E5%8F%A4%E8%8C%B6%E5%9D%8A", "sourceType": "marketplace"},
    {"platform": "QuickClick", "url": "https://order.quickclick.cc/tw/portals/MACU", "sourceType": "third_party"},
    {"platform": "QuickClick", "url": "https://order.quickclick.cc/tw/portals/macu", "sourceType": "third_party"},
    {"platform": "食在麻吉 eathere", "url": "https://www.eathere.com.tw/", "sourceType": "third_party"},
    {"platform": "PB Order", "url": "https://www.pborder.com.tw/", "sourceType": "third_party"},
]


def fetch_text(url: str, timeout: int = 30) -> tuple[str, str, int | None]:
    request = urllib.request.Request(url, headers=HEADERS)
    context = ssl.create_default_context()
    try:
        with urllib.request.urlopen(request, timeout=timeout, context=context) as response:
            raw = response.read()
            charset = response.headers.get_content_charset() or "utf-8"
            return raw.decode(charset, errors="replace"), response.geturl(), response.status
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        return raw.decode("utf-8", errors="replace"), exc.geturl(), exc.code


def strip_tags(value: str) -> str:
    value = re.sub(r"<script\b.*?</script>", "", value, flags=re.S | re.I)
    value = re.sub(r"<style\b.*?</style>", "", value, flags=re.S | re.I)
    value = re.sub(r"<[^>]+>", "", value)
    value = html.unescape(value)
    value = value.replace("\u3000", " ")
    return re.sub(r"\s+", " ", value).strip()


def first_match(pattern: str, text: str, default: str = "") -> str:
    match = re.search(pattern, text, flags=re.S | re.I)
    return html.unescape(match.group(1).strip()) if match else default


def city_from_address(address: str, fallback: str = "") -> str:
    clean_address = re.sub(r"^\d{3,6}", "", address or "").strip().replace("臺", "台")
    for city in TAIWAN_CITIES:
        if clean_address.startswith(city) or city in clean_address[:8]:
            return city
    fallback = fallback.replace("臺", "台").strip()
    if fallback in TAIWAN_CITIES:
        return fallback
    return fallback or "未分類"


def district_from_address(address: str, city: str) -> str:
    clean_address = re.sub(r"^\d{3,6}", "", address or "").strip().replace("臺", "台")
    tail = clean_address.split(city, 1)[1] if city and city in clean_address else clean_address
    match = re.match(r"([\u4e00-\u9fff]{1,6}(?:區|鄉|鎮|市))", tail)
    return match.group(1) if match else ""


def google_search_url(store_name: str, address: str) -> str:
    query = f"麻古茶坊 {store_name} {address}".strip()
    return "https://www.google.com/search?q=" + urllib.parse.quote(query) + "&hl=zh-TW"


def parse_official_stores(page: str) -> list[dict]:
    stores: list[dict] = []
    article_blocks = re.findall(r"<article>\s*(.*?)\s*</article>", page, flags=re.S | re.I)
    for block in article_blocks:
        city_name = strip_tags(first_match(r'<div class="ch">\s*(.*?)\s*</div>', block))
        if city_name == "海外":
            continue
        store_list = first_match(r'<ul class="storeList">\s*(.*?)\s*</ul>', block)
        if not store_list:
            continue
        items = re.findall(r'<li class="grid-x align-middle align-justify">\s*(.*?)\s*</li>', store_list, flags=re.S | re.I)
        for item in items:
            raw_title = first_match(r'<div class="inner">\s*(.*?)\s*</div>', item)
            store_code = first_match(r"<i[^>]*>\s*(.*?)\s*</i>", raw_title)
            store_name = strip_tags(re.sub(r"<i\b.*?</i>", "", raw_title, flags=re.S | re.I))
            ch_values = re.findall(r'<div class="ch cell auto">\s*(.*?)\s*</div>', item, flags=re.S | re.I)
            address = strip_tags(ch_values[0]) if len(ch_values) >= 1 else ""
            phone = strip_tags(ch_values[1]) if len(ch_values) >= 2 else ""
            hours = strip_tags(ch_values[2]) if len(ch_values) >= 3 else ""
            map_url = first_match(r'href="([^"]+)"[^>]*>\s*GOOGLE MAP\s*</a>', item)
            city = city_from_address(address, city_name)
            district = district_from_address(address, city)
            stores.append(
                {
                    "brand": BRAND,
                    "officialStoreCode": store_code,
                    "storeName": store_name,
                    "country": "Taiwan",
                    "market": MARKET,
                    "regionGroup": REGION_BY_CITY.get(city, "未分類"),
                    "city": city,
                    "county": city,
                    "district": district,
                    "address": address,
                    "latitude": None,
                    "longitude": None,
                    "phone": phone,
                    "hours": hours,
                    "officialSourceUrl": STORE_URL,
                    "officialStoreUrl": STORE_URL + "#" + urllib.parse.quote(store_name),
                    "officialMapUrl": map_url,
                    "googleSearchUrl": google_search_url(store_name, address),
                    "gmbUrl": map_url,
                    "gmbStatus": "needs_manual_review",
                    "gmbOrderingStatus": "needs_manual_review",
                    "gmbOrderLinks": [],
                    "gmbPickupProviders": [],
                    "gmbDeliveryProviders": [],
                    "gmbOrderModesConfirmed": [],
                    "sourceCoverage": {
                        "officialListed": True,
                        "gmbFound": False,
                        "googleFound": bool(map_url),
                        "thirdPartyFound": False,
                    },
                    "orderingSystems": [],
                    "hasAnyOrderingSystem": False,
                    "hasGmbOrderingSystem": False,
                    "manualReviewReason": (
                        "官方門市頁提供 Google Map 連結，但尚未逐店確認為正確命名的 Google Business Profile；"
                        "Google Order 自取/外送 provider 需另行打開面板查核。"
                    ),
                    "evidenceNotes": [
                        "官方門市頁是 active store population 來源。",
                        "官方 Google Map 連結只作為 GMB identity lead；未打開 Google Order 面板前不計入 GMB provider evidence。",
                    ],
                    "platformAudit": [],
                    "gmbSignals": {
                        "buttonDetected": False,
                        "providersParsed": False,
                        "modeReadStates": {"pickupProviders": "unknown", "deliveryProviders": "unknown"},
                        "attemptCount": 0,
                        "maxAttempts": 0,
                        "attemptHistory": [],
                        "panelUrl": "",
                        "checkedAt": CHECKED_AT,
                        "checkMethod": "official_store_population_first_pass",
                        "unresolvedReason": "needs_mode_aware_google_order_panel_audit",
                        "notes": "Not yet opened in Google Order panel; pickup and delivery provider rows are pending.",
                    },
                    "checkedAt": CHECKED_AT,
                }
            )

    deduped: dict[tuple[str, str], dict] = {}
    for store in stores:
        key = (store["storeName"], store["address"])
        if key not in deduped:
            deduped[key] = store
    stores = list(deduped.values())
    for index, store in enumerate(stores, start=1):
        store["storeId"] = f"macu-tw-{index:03d}"
    stores.sort(key=lambda item: (REGIONS.index(item["regionGroup"]) if item["regionGroup"] in REGIONS else 99, item["city"], item["storeName"]))
    return stores


def parse_official_links(page: str) -> list[dict]:
    links = []
    for match in re.finditer(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', page, flags=re.S | re.I):
        url = html.unescape(match.group(1))
        label = strip_tags(match.group(2))
        if "lihi.cc" in url or "ORDER" in label or "點餐" in label or "查訂單" in label:
            links.append({"label": label, "url": urllib.parse.urljoin(OFFICIAL_WEBSITE, url)})
    deduped = []
    seen = set()
    for link in links:
        key = (link["label"], link["url"])
        if key not in seen:
            seen.add(key)
            deduped.append(link)
    return deduped


def resolve_url(url: str) -> dict:
    request = urllib.request.Request(url, method="GET", headers=HEADERS)
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            body = response.read(5000).decode(response.headers.get_content_charset() or "utf-8", errors="replace")
            return {"url": url, "finalUrl": response.geturl(), "status": response.status, "title": strip_tags(first_match(r"<title[^>]*>(.*?)</title>", body))}
    except Exception as exc:
        return {"url": url, "finalUrl": "", "status": "error", "error": type(exc).__name__}


def classify_platform(url: str) -> str:
    value = (url or "").lower()
    if "nidin.shop" in value:
        return "Nidin"
    if "ubereats" in value:
        return "Uber Eats"
    if "foodpanda" in value:
        return "foodpanda"
    if "quickclick" in value:
        return "QuickClick"
    if "line.me" in value or "lin.ee" in value or "liff.line.me" in value:
        return "LINE"
    if "esgpb" in value or "pborder" in value:
        return "PB Order"
    return ""


def audit_platforms(page: str, stores: list[dict]) -> dict:
    official_links = parse_official_links(page)
    resolved_links = [{**link, **resolve_url(link["url"])} for link in official_links]
    candidate_results = []
    for candidate in PLATFORM_CANDIDATES:
        result = resolve_url(candidate["url"])
        candidate_results.append({**candidate, **result})

    official_order_platforms = []
    for link in resolved_links:
        platform = classify_platform(link.get("finalUrl") or link["url"])
        if platform and ("ORDER" in link.get("label", "") or "點餐" in link.get("label", "")):
            official_order_platforms.append({**link, "platform": platform})

    # A brand-level official order link is recorded as platform-level evidence
    # only. Store-level adoption remains pending until each store can be matched
    # by a platform store id, address, or phone.
    platform_audit = {
        "checkedAt": CHECKED_AT,
        "officialLinks": resolved_links,
        "platformCandidates": candidate_results,
        "officialOrderPlatforms": official_order_platforms,
        "storePlatformStatusCounts": {},
        "notes": (
            "Official lihi/order links were resolved as brand-level leads. "
            "No store-level platform match is counted unless a store can be matched directly by name, address, phone, or platform id."
        ),
    }
    if official_order_platforms:
        for store in stores:
            for order_link in official_order_platforms:
                store["platformAudit"].append(
                    {
                        "platform": order_link["platform"],
                        "status": "brand_level_official_order_link_pending_store_match",
                        "sourceType": "official",
                        "orderMode": ["pickup", "delivery"],
                        "evidenceUrl": order_link.get("finalUrl") or order_link["url"],
                        "matchedBy": ["brandLevelOfficialLink"],
                        "checkedAt": CHECKED_AT,
                        "notes": "官方頁面有品牌層級點餐連結；尚未逐店匹配平台門市。",
                    }
                )
        platform_audit["storePlatformStatusCounts"] = dict(
            Counter(
                f"{row['platform']}:{row['status']}"
                for store in stores
                for row in store.get("platformAudit", [])
            )
        )
    return platform_audit


def rate(count: int, total: int) -> float:
    return round(count / total, 4) if total else 0


def count_systems(stores: list[dict], source_type: str | None = None, mode: str | None = None) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for store in stores:
        systems = set()
        for claim in store.get("orderingSystems", []):
            if source_type and claim.get("sourceType") != source_type:
                continue
            if mode and mode not in claim.get("orderMode", []):
                continue
            if claim.get("confidence") in {"confirmed", "partial", "ambiguous"} and claim.get("system"):
                systems.add(claim["system"])
        counts.update(systems)
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0].lower())))


def count_google_order_options(stores: list[dict], mode: str | None = None) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for store in stores:
        systems = set()
        for claim in store.get("orderingSystems", []):
            if claim.get("sourceType") != "gmb":
                continue
            if mode and mode not in claim.get("orderMode", []):
                continue
            if claim.get("system"):
                systems.add(claim["system"])
        for link in store.get("gmbOrderLinks", []) or []:
            if mode and mode not in (link.get("orderMode") or []):
                continue
            if link.get("platform"):
                systems.add(link["platform"])
        counts.update(systems)
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0].lower())))


def build_summary(stores: list[dict], platform_direct_audit: dict) -> dict:
    total = len(stores)
    city_counter = Counter(store["city"] for store in stores)
    region_counter = Counter(store["regionGroup"] for store in stores)
    all_counts = count_systems(stores)
    gmb_counts = count_systems(stores, source_type="gmb")
    systems = sorted(set(all_counts) | set(gmb_counts) | {"Nidin", "Uber Eats", "foodpanda", "LINE", "QuickClick", "食在麻吉 eathere", "PB Order"})
    gmb_order_entry = sum(1 for store in stores if store.get("hasGmbOrderingSystem") or store.get("gmbOrderingStatus") == "button_confirmed_provider_pending")

    summary = {
        "generatedAt": CHECKED_AT,
        "brand": BRAND,
        "brandSlug": BRAND_SLUG,
        "market": MARKET,
        "sitePath": "./macu/",
        "officialStoreCount": total,
        "gmbFoundCount": sum(1 for store in stores if store.get("sourceCoverage", {}).get("gmbFound") or store.get("gmbStatus") == "confirmed"),
        "gmbMissingCount": sum(1 for store in stores if not store.get("sourceCoverage", {}).get("gmbFound") and store.get("gmbStatus") != "confirmed"),
        "googleFoundCount": sum(1 for store in stores if store.get("sourceCoverage", {}).get("googleFound")),
        "thirdPartyFoundCount": sum(1 for store in stores if store.get("sourceCoverage", {}).get("thirdPartyFound")),
        "verificationGapCount": sum(1 for store in stores if store.get("gmbOrderingStatus") != "confirmed"),
        "anyOrderingSystemCount": sum(1 for store in stores if store.get("hasAnyOrderingSystem")),
        "googleOrderEntryCount": gmb_order_entry,
        "googleOrderEntryRate": rate(gmb_order_entry, total),
        "gmbOrderingSystemCount": sum(1 for store in stores if any(claim.get("sourceType") == "gmb" for claim in store.get("orderingSystems", []))),
        "gmbCoverageGapCount": sum(1 for store in stores if not store.get("hasGmbOrderingSystem") and store.get("gmbOrderingStatus") != "button_confirmed_provider_pending"),
        "unknownOrderingSystemCount": sum(1 for store in stores if not store.get("hasAnyOrderingSystem")),
        "cityCounts": {city: city_counter.get(city, 0) for city in TAIWAN_CITIES},
        "regionCounts": {region: region_counter.get(region, 0) for region in REGIONS},
        "allSourceSystemCounts": all_counts,
        "allSourcePickupSystemCounts": count_systems(stores, mode="pickup"),
        "allSourceDeliverySystemCounts": count_systems(stores, mode="delivery"),
        "gmbSystemCounts": gmb_counts,
        "gmbPickupSystemCounts": count_systems(stores, source_type="gmb", mode="pickup"),
        "gmbDeliverySystemCounts": count_systems(stores, source_type="gmb", mode="delivery"),
        "gmbOrderOptionCounts": count_google_order_options(stores),
        "gmbOrderPickupOptionCounts": count_google_order_options(stores, mode="pickup"),
        "gmbOrderDeliveryOptionCounts": count_google_order_options(stores, mode="delivery"),
        "gmbStatusCounts": dict(Counter(store.get("gmbStatus") for store in stores)),
        "gmbOrderingStatusCounts": dict(Counter(store.get("gmbOrderingStatus") for store in stores)),
        "sourceCoverageCounts": {
            "officialListed": total,
            "gmbFound": sum(1 for store in stores if store.get("sourceCoverage", {}).get("gmbFound")),
            "googleFound": sum(1 for store in stores if store.get("sourceCoverage", {}).get("googleFound")),
            "thirdPartyFound": sum(1 for store in stores if store.get("sourceCoverage", {}).get("thirdPartyFound")),
        },
        "source": {
            "officialWebsite": OFFICIAL_WEBSITE,
            "officialStoreList": STORE_URL,
            "googleMapLinksFromOfficialStores": True,
            "platformDirectAudit": platform_direct_audit,
            "externalReferences": {
                "uberEatsBrandPage": "https://www.ubereats.com/tw/brand/macu",
                "foodpandaPublicSearch": "https://www.foodpanda.com.tw/search?q=%E9%BA%BB%E5%8F%A4%E8%8C%B6%E5%9D%8A",
            },
            "notes": (
                "Official shop.php is the active store population source. "
                "Official Google Map links are stored as GMB leads only; strict Google Order provider evidence requires opening the order panel and reading pickup/delivery provider rows."
            ),
        },
        "notes": [
            "官方門市母體來自麻古茶坊 shop.php，並去重相同店名/地址。",
            "官網 Google Map 連結不直接等於 GMB confirmed；需逐店確認命名 profile 並打開 Google Order 面板。",
            "目前本地報表先保留 Google Order 自取/外送 provider 為待查核；未打開面板前不推定 Uber Eats、foodpanda、Nidin、LINE、QuickClick、PB Order 等為 GMB provider。",
            "Uber Eats brand page 與 foodpanda 公開店頁作為平台線索；未逐店匹配前不列入 store-level adoption。",
        ],
    }
    summary["anyOrderingSystemAdoptionRate"] = rate(summary["anyOrderingSystemCount"], total)
    summary["gmbOrderingSystemAdoptionRate"] = rate(summary["gmbOrderingSystemCount"], total)
    summary["allSourceSystemAdoptionRates"] = {system: rate(count, total) for system, count in all_counts.items()}
    summary["gmbSystemAdoptionRates"] = {system: rate(count, total) for system, count in gmb_counts.items()}
    summary["gmbOrderOptionAdoptionRates"] = {system: rate(count, total) for system, count in summary["gmbOrderOptionCounts"].items()}
    summary["systemComparison"] = [
        {
            "system": system,
            "allSourceStoreCount": all_counts.get(system, 0),
            "allSourceAdoptionRate": rate(all_counts.get(system, 0), total),
            "gmbStoreCount": gmb_counts.get(system, 0),
            "gmbAdoptionRate": rate(gmb_counts.get(system, 0), total),
            "countGap": all_counts.get(system, 0) - gmb_counts.get(system, 0),
            "percentagePointGap": round(rate(all_counts.get(system, 0), total) - rate(gmb_counts.get(system, 0), total), 4),
        }
        for system in systems
    ]
    return summary


def write_csv(stores: list[dict]) -> None:
    fields = [
        "storeId",
        "officialStoreCode",
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
        "gmbPickupProviders",
        "gmbDeliveryProviders",
        "allSourceSystems",
        "gmbSystems",
        "officialSourceUrl",
        "officialMapUrl",
        "gmbUrl",
        "manualReviewReason",
    ]
    with (DATA / "stores.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for store in stores:
            all_systems = sorted({claim.get("system") for claim in store.get("orderingSystems", []) if claim.get("system")})
            gmb_systems = sorted({claim.get("system") for claim in store.get("orderingSystems", []) if claim.get("sourceType") == "gmb" and claim.get("system")})
            writer.writerow(
                {
                    **{field: store.get(field, "") for field in fields},
                    "gmbPickupProviders": "、".join(store.get("gmbPickupProviders") or []),
                    "gmbDeliveryProviders": "、".join(store.get("gmbDeliveryProviders") or []),
                    "allSourceSystems": "、".join(all_systems),
                    "gmbSystems": "、".join(gmb_systems),
                }
            )


def report_html() -> str:
    return """<!doctype html>
<html lang="zh-Hant">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>麻古茶坊 MACU Tea 點餐系統總覽</title>
  <link rel="stylesheet" href="../assets/styles.css?v=35" />
</head>
<body>
  <header class="topbar">
    <div>
      <p class="eyebrow">Brand Order Analysis</p>
      <h1>麻古茶坊 MACU Tea 點餐系統總覽</h1>
      <p class="subhead">台灣官方門市、Google/Maps/GMB lead、平台 direct audit 線索、Google Order provider evidence；GMB provider 只計入已打開 Google Order 面板且可區分自取/外送的 rows。<span class="version">v1 macu-local-report</span></p>
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
      <label>Google Order <select id="gmbFilter"><option value="all">全部</option><option value="confirmed">Google Order provider 已確認</option><option value="gap">未找到 Google Order 入口</option><option value="no_gmb_found">GMB/Maps 未確認</option></select></label>
      <label class="search">搜尋門市<input id="searchInput" type="search" placeholder="門市、地址、縣市" /></label>
    </section>

    <section class="insight-strip" id="insightStrip"></section>

    <section class="panel">
      <div class="section-title">
        <div><p class="eyebrow">1. Store Footprint</p><h2>官方門市與台灣分布</h2></div>
        <p>以麻古茶坊官網 shop.php 建立 active store population；縣市與區域篩選會同步更新 KPI、地圖、城市排行與明細表。</p>
      </div>
      <div class="kpi-grid" id="storeKpis"></div>
      <div class="split map-layout">
        <div>
          <h3>台灣門市地圖</h3>
          <p class="map-source">包含台灣 22 縣市；官網目前無門市的縣市顯示 0。</p>
          <div class="taiwan-map" id="taiwanMap"></div>
        </div>
        <div><h3>城市排行</h3><div class="bars" id="cityBars"></div></div>
      </div>
    </section>

    <section class="panel">
      <div class="section-title">
        <div><p class="eyebrow">2. All Sources</p><h2>全來源點餐系統</h2></div>
        <p>官方 order/link、平台頁、Google/GMB、第三方與 marketplace evidence 分開保存；未逐店匹配的平台只留在 platformAudit，不列入 adoption。</p>
      </div>
      <div class="kpi-grid" id="allSourceKpis"></div>
      <div class="split">
        <div><h3>全來源自取</h3><div class="bars" id="pickupBars"></div></div>
        <div><h3>全來源外送</h3><div class="bars" id="deliveryBars"></div></div>
      </div>
      <div class="split compact">
        <div><h3>區域導入率</h3><div class="matrix" id="regionMatrix"></div></div>
        <div><h3>證據邊界</h3><p class="note">品牌層級 Uber Eats / foodpanda / Nidin / LINE 等線索，不代表每個官方門市都可點餐；store-level adoption 需要直接平台門市頁、地址/電話/門市 ID 匹配，或 Google Order 面板 provider row。</p></div>
      </div>
    </section>

    <section class="panel warning">
      <div class="section-title">
        <div><p class="eyebrow">3. Google Order</p><h2>Google Order provider / link 總覽</h2></div>
        <p>只有 Google Business Profile 藍色點餐流程打開後，在自取或外送面板中可見的 provider row 才列為 GMB provider evidence；若未找到藍色點餐入口，標記為已確認無 Google Order 入口；若入口存在但 provider row 無法解析，另列為 provider pending。</p>
      </div>
      <div class="kpi-grid" id="gmbKpis"></div>
      <div class="split">
        <div><h3>Google Order 自取供應商</h3><div class="bars" id="gmbPickupBars"></div></div>
        <div><h3>Google Order 外送供應商</h3><div class="bars" id="gmbDeliveryBars"></div></div>
      </div>
    </section>

    <section class="panel">
      <div class="section-title"><div><p class="eyebrow">4. Comparison</p><h2>全來源 vs Google Order provider</h2></div></div>
      <div class="table-wrap"><table><thead><tr><th>系統</th><th>全來源門市</th><th>全來源率</th><th>Google Order provider 門市</th><th>Google Order provider 率</th><th>差距</th></tr></thead><tbody id="comparisonRows"></tbody></table></div>
    </section>

    <section class="panel">
      <div class="section-title"><div><p class="eyebrow">5. Store Details</p><h2>門市明細</h2></div><p id="detailCount"></p></div>
      <div class="table-wrap details"><table><thead><tr><th>門市</th><th>區域</th><th>地址</th><th>全來源點餐</th><th>Google Order 證據</th><th>來源 / 待辦</th></tr></thead><tbody id="storeRows"></tbody></table></div>
    </section>
  </main>

  <script src="data-inline.js?v=1"></script>
  <script src="../assets/taiwan-map.js?v=35"></script>
  <script src="../assets/app.js?v=37"></script>
</body>
</html>
"""


def write_outputs(stores: list[dict], summary: dict) -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    payload = {
        "generatedAt": summary["generatedAt"],
        "brand": BRAND,
        "source": summary["source"],
        "stores": stores,
    }
    (DATA / "stores.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (DATA / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (OUT / "data-inline.js").write_text(
        "window.DAMING_DATA = " + json.dumps({"storesPayload": payload, "summary": summary}, ensure_ascii=False) + ";\n",
        encoding="utf-8",
    )
    (OUT / "index.html").write_text(report_html(), encoding="utf-8")
    write_csv(stores)


def update_root_index(summary: dict) -> None:
    index_path = ROOT / "index.html"
    html_text = index_path.read_text(encoding="utf-8")
    if 'href="macu/"' in html_text:
        html_text = re.sub(r'(<a class="card" href="macu/">.*?</a>)', brand_card(summary), html_text, flags=re.S)
    else:
        insert_at = html_text.rfind("    </section>")
        html_text = html_text[:insert_at] + brand_card(summary) + "\n" + html_text[insert_at:]
    index_path.write_text(html_text, encoding="utf-8")


def brand_card(summary: dict) -> str:
    stores = summary["officialStoreCount"]
    return f"""
      <a class="card" href="macu/">
        <h2>麻古茶坊 MACU Tea</h2>
        <p>台灣官方門市、Google/Maps lead、平台 direct audit 線索與 Google Order 自取/外送 provider 逐店稽核。</p>
        <div class="meta"><span class="pill">/macu/</span><span class="pill">{stores} stores</span></div>
      </a>"""


def main() -> None:
    page, final_url, status = fetch_text(STORE_URL)
    stores = parse_official_stores(page)
    platform_direct_audit = audit_platforms(page, stores)
    summary = build_summary(stores, platform_direct_audit)
    summary["source"]["officialStoreFetch"] = {"url": STORE_URL, "finalUrl": final_url, "status": status}
    write_outputs(stores, summary)
    update_root_index(summary)
    print(
        json.dumps(
            {
                "report": str(OUT),
                "officialStoreCount": summary["officialStoreCount"],
                "cityCounts": summary["cityCounts"],
                "regionCounts": summary["regionCounts"],
                "gmbOrderingStatusCounts": summary["gmbOrderingStatusCounts"],
                "officialOrderPlatforms": platform_direct_audit.get("officialOrderPlatforms", []),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

