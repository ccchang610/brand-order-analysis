from __future__ import annotations

import argparse
import csv
import html
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

import requests


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "coco"
DATA = OUT / "data"

BRAND = "CoCo都可"
BRAND_SLUG = "coco"
MARKET = "Taiwan"
NIDIN_BRAND_URL = "https://order.nidin.shop/brand/cocotea"
NIDIN_API = "https://loctw-service-api.nidin.shop/shopper/v2"
NIDIN_BRAND_CODE = "cocotea"
NIDIN_BRAND_KEY = "26195837"
CHECKED_AT = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"
    ),
    "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
}
NIDIN_HEADERS = {
    **HEADERS,
    "MC-API-Brand-Key": NIDIN_BRAND_KEY,
    "MC-API-Brand-Code": NIDIN_BRAND_CODE,
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
    **{city: "北部" for city in ["基隆市", "台北市", "新北市", "桃園市", "新竹市", "新竹縣", "苗栗縣"]},
    **{city: "中部" for city in ["台中市", "彰化縣", "南投縣", "雲林縣"]},
    **{city: "南部" for city in ["嘉義市", "嘉義縣", "台南市", "高雄市", "屏東縣"]},
    **{city: "東部" for city in ["宜蘭縣", "花蓮縣", "台東縣"]},
    **{city: "離島" for city in ["澎湖縣", "金門縣", "連江縣"]},
}
REGIONS = ["北部", "中部", "南部", "東部", "離島"]


def clean(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "").replace("\xa0", " ")).strip()


def normalize_address(value: str) -> str:
    value = clean(value)
    return value.replace("臺", "台")


def city_from_address(address: str) -> str:
    text = normalize_address(address)
    for city in TAIWAN_CITIES:
        if city in text:
            return city
    return ""


def district_from_address(address: str, city: str) -> str:
    text = normalize_address(address)
    tail = text.split(city, 1)[1] if city and city in text else text
    match = re.search(r"([\u4e00-\u9fff]{1,5}(?:區|鄉|鎮|市))", tail)
    return match.group(1) if match else ""


def rate(count: int, total: int) -> float:
    return round(count / total, 4) if total else 0.0


def fetch_nidin_stores() -> list[dict]:
    stores: list[dict] = []
    page = 1
    total = None
    while total is None or len(stores) < total:
        params = {
            "brand_code": NIDIN_BRAND_CODE,
            "count": 20,
            "page": page,
            "latitude": 25.033,
            "longitude": 121.565,
            "distance_km": 1000,
            "src_type": 3,
        }
        response = requests.get(
            f"{NIDIN_API}/store/listByPositionNew",
            headers=NIDIN_HEADERS,
            params=params,
            timeout=45,
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("status") != 200:
            raise RuntimeError(f"Nidin API status {payload.get('status')}: {payload.get('message')}")
        batch = payload.get("list") or []
        meta = payload.get("meta") or {}
        total = int(meta.get("total_amount") or len(batch))
        stores.extend(batch)
        if not batch:
            break
        page += 1
    by_id = {int(item["id"]): item for item in stores if item.get("id")}
    return [by_id[key] for key in sorted(by_id)]


def nidin_order_modes(item: dict) -> list[str]:
    modes = []
    if int(item.get("store_allow_order") or 0) == 1:
        modes.append("pickup")
        if item.get("delivery_info") or clean(item.get("delivery_way_description")):
            modes.append("delivery")
    return modes


def store_record(item: dict, index: int) -> dict:
    address = normalize_address(item.get("address") or "")
    city = city_from_address(address)
    district = district_from_address(address, city)
    modes = nidin_order_modes(item)
    store_url = f"https://order.nidin.shop/menu/{item['id']}"
    ordering_systems = []
    if modes:
        ordering_systems.append(
            {
                "system": "Nidin",
                "sourceType": "third_party",
                "orderMode": modes,
                "evidenceUrl": store_url,
                "label": "Nidin CoCo都可門市點餐頁",
                "confidence": "confirmed",
                "evidenceNote": (
                    "Matched from the user-supplied Nidin CoCo brand portal. Counted as all-source "
                    "platform evidence, not as Google Order provider evidence."
                ),
            }
        )
    branch = clean(item.get("name") or item.get("name_short") or "")
    return {
        "brand": BRAND,
        "storeId": f"coco-tw-{index:03d}",
        "platformStoreId": item.get("id"),
        "storeName": branch,
        "country": "Taiwan",
        "market": MARKET,
        "regionGroup": REGION_BY_CITY.get(city, "未解析"),
        "city": city or "未解析",
        "county": city or "未解析",
        "district": district,
        "address": address,
        "latitude": item.get("latitude") or "",
        "longitude": item.get("longitude") or "",
        "phone": clean(item.get("tel") or ""),
        "hours": f"{clean(item.get('start_time'))}-{clean(item.get('end_time'))}".strip("-"),
        "officialSourceUrl": NIDIN_BRAND_URL,
        "officialStoreUrl": store_url,
        "officialMapUrl": "",
        "googleSearchUrl": f"https://www.google.com/search?q={quote(f'{BRAND} {branch} {address}')}&hl=zh-TW",
        "gmbUrl": "",
        "gmbStatus": "needs_manual_review",
        "gmbOrderingStatus": "needs_manual_review",
        "gmbOrderLinks": [],
        "gmbPickupProviders": [],
        "gmbDeliveryProviders": [],
        "gmbOrderModesConfirmed": [],
        "sourceCoverage": {
            "officialListed": True,
            "gmbFound": False,
            "googleFound": False,
            "thirdPartyFound": bool(ordering_systems),
        },
        "orderingSystems": ordering_systems,
        "hasAnyOrderingSystem": bool(ordering_systems),
        "hasGmbOrderingSystem": False,
        "manualReviewReason": (
            "Nidin platform store is confirmed. Matching named GMB profile and Google Order "
            "pickup/delivery provider panel still need live review."
        ),
        "evidenceNotes": [
            "No Taiwan Chinese official store locator was found during intake; this report uses the user-supplied Nidin CoCo brand portal as the primary public store population source.",
            f"Nidin platform store id {item.get('id')} has order_status={item.get('order_status')} and store_allow_order={item.get('store_allow_order')}.",
            clean(item.get("delivery_way_description") or ""),
        ],
        "platformAudit": [
            {
                "platform": "Nidin",
                "status": "confirmed" if modes else "listed_but_order_unavailable",
                "sourceType": "third_party",
                "orderMode": modes,
                "evidenceUrl": store_url,
                "matchedBy": ["platformStoreId", "brandPortal"],
                "checkedAt": CHECKED_AT,
                "notes": clean(item.get("delivery_way_description") or ""),
            }
        ],
        "gmbSignals": {
            "buttonDetected": False,
            "providersParsed": False,
            "attemptCount": 0,
            "maxAttempts": 0,
            "attemptHistory": [],
            "panelUrl": "",
            "checkedAt": CHECKED_AT,
            "checkMethod": "not_yet_audited",
            "matchQuality": "pending_named_gmb_match",
            "notes": "GMB/Google Order live audit not yet completed for this generated baseline row.",
        },
        "checkedAt": CHECKED_AT,
    }


def count_systems(stores: list[dict], source_type: str | None = None, mode: str | None = None) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for store in stores:
        systems: set[str] = set()
        for claim in store.get("orderingSystems", []):
            if source_type and claim.get("sourceType") != source_type:
                continue
            if mode and mode not in (claim.get("orderMode") or []):
                continue
            if claim.get("confidence") in {"confirmed", "partial", "ambiguous", None} and claim.get("system"):
                systems.add(claim["system"])
        counts.update(systems)
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0].lower())))


def count_google_order_options(stores: list[dict], mode: str | None = None) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for store in stores:
        systems: set[str] = set()
        for claim in store.get("orderingSystems", []):
            if claim.get("sourceType") != "gmb":
                continue
            if mode and mode not in (claim.get("orderMode") or []):
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


def quickclick_audit() -> dict:
    attempts = []
    for slug in ["COCOTEA", "cocotea", "CoCo", "COCO", "coco"]:
        url = f"https://order.quickclick.cc/tw/portals/{slug}"
        try:
            response = requests.get(url, headers=HEADERS, timeout=20, allow_redirects=True)
            final_url = response.url
            text = response.text[:500].lower()
            status = "not_found"
            if response.status_code < 400 and "invalid portal" not in final_url.lower() and "invalid" not in text:
                status = "needs_manual_review"
            attempts.append(
                {
                    "url": url,
                    "finalUrl": final_url,
                    "httpStatus": response.status_code,
                    "status": status,
                }
            )
        except Exception as exc:
            attempts.append({"url": url, "status": "unavailable_or_blocked", "detail": type(exc).__name__})
    status = "not_found" if all(item.get("status") == "not_found" for item in attempts) else "needs_manual_review"
    return {"status": status, "attempts": attempts, "checkedAt": CHECKED_AT}


def platform_reachability_audit() -> dict:
    checks = {
        "Uber Eats": "https://www.ubereats.com/tw/search?q=CoCo%E9%83%BD%E5%8F%AF",
        "foodpanda": "https://www.foodpanda.com.tw/search?q=CoCo%E9%83%BD%E5%8F%AF",
    }
    results = {}
    for platform, url in checks.items():
        try:
            response = requests.get(url, headers=HEADERS, timeout=20, allow_redirects=True)
            results[platform] = {
                "status": "public_search_page_checked_not_exhaustive",
                "evidenceUrl": url,
                "httpStatus": response.status_code,
                "finalUrl": response.url,
                "notes": "Search page reachability only; platform store matching is not exhaustive without app/API access.",
            }
        except Exception as exc:
            results[platform] = {
                "status": "unavailable_or_blocked",
                "evidenceUrl": url,
                "notes": f"Direct public search request failed: {type(exc).__name__}.",
            }
    return results


def build_summary(stores: list[dict], raw_nidin_count: int, quickclick: dict, platform_reachability: dict) -> dict:
    total = len(stores)
    city_counter = Counter(store.get("city") for store in stores)
    region_counter = Counter(store.get("regionGroup") for store in stores)
    all_counts = count_systems(stores)
    gmb_counts = count_systems(stores, source_type="gmb")
    gmb_options = count_google_order_options(stores)
    systems = sorted(set(all_counts) | set(gmb_counts))

    gmb_found = sum(1 for store in stores if store.get("sourceCoverage", {}).get("gmbFound") or store.get("gmbStatus") == "confirmed")
    google_found = sum(1 for store in stores if store.get("sourceCoverage", {}).get("googleFound"))
    third_party = sum(1 for store in stores if store.get("sourceCoverage", {}).get("thirdPartyFound"))
    any_ordering = sum(1 for store in stores if store.get("hasAnyOrderingSystem"))
    gmb_provider = sum(
        1
        for store in stores
        if any(claim.get("sourceType") == "gmb" and claim.get("system") for claim in store.get("orderingSystems", []))
    )
    google_order_entry = sum(
        1
        for store in stores
        if store.get("hasGmbOrderingSystem")
        or store.get("gmbOrderingStatus") in {"confirmed", "button_confirmed_provider_pending"}
    )

    return {
        "generatedAt": CHECKED_AT,
        "brand": BRAND,
        "brandSlug": BRAND_SLUG,
        "market": MARKET,
        "sitePath": "./coco/",
        "officialStoreCount": total,
        "gmbFoundCount": gmb_found,
        "gmbMissingCount": total - gmb_found,
        "googleFoundCount": google_found,
        "thirdPartyFoundCount": third_party,
        "verificationGapCount": sum(
            1
            for store in stores
            if store.get("gmbStatus") != "confirmed"
            or store.get("gmbOrderingStatus")
            in {
                "not_found",
                "unavailable_or_blocked",
                "duplicate_or_ambiguous",
                "needs_manual_review",
                "button_confirmed_provider_pending",
            }
        ),
        "anyOrderingSystemCount": any_ordering,
        "anyOrderingSystemAdoptionRate": rate(any_ordering, total),
        "googleOrderEntryCount": google_order_entry,
        "googleOrderEntryRate": rate(google_order_entry, total),
        "gmbOrderingSystemCount": gmb_provider,
        "gmbOrderingSystemAdoptionRate": rate(gmb_provider, total),
        "gmbCoverageGapCount": sum(
            1
            for store in stores
            if not store.get("hasGmbOrderingSystem")
            and store.get("gmbOrderingStatus") != "button_confirmed_provider_pending"
        ),
        "unknownOrderingSystemCount": total - any_ordering,
        "cityCounts": {city: city_counter.get(city, 0) for city in TAIWAN_CITIES},
        "regionCounts": {region: region_counter.get(region, 0) for region in REGIONS},
        "allSourceSystemCounts": all_counts,
        "allSourcePickupSystemCounts": count_systems(stores, mode="pickup"),
        "allSourceDeliverySystemCounts": count_systems(stores, mode="delivery"),
        "gmbSystemCounts": gmb_counts,
        "gmbPickupSystemCounts": count_systems(stores, source_type="gmb", mode="pickup"),
        "gmbDeliverySystemCounts": count_systems(stores, source_type="gmb", mode="delivery"),
        "gmbOrderOptionCounts": gmb_options,
        "gmbOrderPickupOptionCounts": count_google_order_options(stores, mode="pickup"),
        "gmbOrderDeliveryOptionCounts": count_google_order_options(stores, mode="delivery"),
        "allSourceSystemAdoptionRates": {system: rate(count, total) for system, count in all_counts.items()},
        "gmbSystemAdoptionRates": {system: rate(count, total) for system, count in gmb_counts.items()},
        "gmbOrderOptionAdoptionRates": {system: rate(count, total) for system, count in gmb_options.items()},
        "systemComparison": [
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
        ],
        "gmbStatusCounts": dict(Counter(store.get("gmbStatus") for store in stores)),
        "gmbOrderingStatusCounts": dict(Counter(store.get("gmbOrderingStatus") for store in stores)),
        "sourceCoverageCounts": {
            "officialListed": total,
            "gmbFound": gmb_found,
            "googleFound": google_found,
            "thirdPartyFound": third_party,
        },
        "source": {
            "officialWebsite": "",
            "officialStoreList": "",
            "primaryStorePopulation": NIDIN_BRAND_URL,
            "primaryStorePopulationType": "user_supplied_nidin_brand_portal",
            "nidinApi": f"{NIDIN_API}/store/listByPositionNew",
            "notes": (
                "No Taiwan Chinese official store locator was found during intake. "
                "The user-supplied Nidin CoCo brand portal is used as the primary public store population source; "
                "Google Order provider evidence remains separate and requires live GMB panel reads."
            ),
        },
        "notes": [
            "Nidin platform-direct check found the CoCo brand portal and returned the active baseline store population used in this report.",
            "Nidin all-source ordering evidence is counted as third-party/platform evidence, not as Google Order provider evidence.",
            "Google Order provider rows are counted only when a named GMB profile is opened and the visible Google Order panel is read by pickup/delivery mode.",
            "QuickClick, Uber Eats, foodpanda, LINE, and other platform fields are preserved as platform-direct audit metadata where no exhaustive public API was available.",
        ],
        "platformDirectAudit": {
            "checkedAt": CHECKED_AT,
            "platformsChecked": ["Nidin", "QuickClick", "Uber Eats", "foodpanda", "LINE"],
            "Nidin": {
                "brandUrl": NIDIN_BRAND_URL,
                "apiUrl": f"{NIDIN_API}/store/listByPositionNew",
                "status": "confirmed",
                "platformStoreCount": raw_nidin_count,
                "reportStoreCount": total,
                "pickupStoreCount": sum(
                    1
                    for store in stores
                    if any(claim.get("system") == "Nidin" and "pickup" in claim.get("orderMode", []) for claim in store.get("orderingSystems", []))
                ),
                "deliveryStoreCount": sum(
                    1
                    for store in stores
                    if any(claim.get("system") == "Nidin" and "delivery" in claim.get("orderMode", []) for claim in store.get("orderingSystems", []))
                ),
            },
            "QuickClick": quickclick,
            "Uber Eats": platform_reachability.get("Uber Eats", {}),
            "foodpanda": platform_reachability.get("foodpanda", {}),
            "LINE": {
                "status": "not_found",
                "notes": "No exhaustive public LINE ordering source was discovered from the Nidin baseline build; LINE links seen inside future Google Order panels should be recorded in gmbOrderLinks.",
            },
        },
    }


def write_csv(stores: list[dict]) -> None:
    fields = [
        "storeId",
        "platformStoreId",
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
        "officialStoreUrl",
        "gmbUrl",
        "gmbOrderPanelUrl",
        "manualReviewReason",
    ]
    with (DATA / "stores.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for store in stores:
            all_systems = sorted({claim.get("system", "") for claim in store.get("orderingSystems", []) if claim.get("system")})
            gmb_systems = sorted(
                {
                    claim.get("system", "")
                    for claim in store.get("orderingSystems", [])
                    if claim.get("sourceType") == "gmb" and claim.get("system")
                }
            )
            row = {field: store.get(field, "") for field in fields}
            row["gmbPickupProviders"] = "; ".join(store.get("gmbPickupProviders") or [])
            row["gmbDeliveryProviders"] = "; ".join(store.get("gmbDeliveryProviders") or [])
            row["allSourceSystems"] = "; ".join(all_systems)
            row["gmbSystems"] = "; ".join(gmb_systems)
            writer.writerow(row)


def report_html() -> str:
    title = f"{BRAND} 台灣點餐系統總覽"
    return f"""<!doctype html>
<html lang="zh-Hant">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{html.escape(title)}</title>
  <link rel="stylesheet" href="../assets/styles.css?v=35" />
</head>
<body>
  <header class="topbar">
    <div>
      <p class="eyebrow">Brand Order Analysis</p>
      <h1>{html.escape(title)}</h1>
      <p class="subhead">以使用者提供的 Nidin CoCo 品牌頁作為目前最強公開門市母體，分離全來源點餐證據與 Google Order provider evidence；GMB 自取/外送供應商只在 opened Google Order panel 可讀時才列入。<span class="version">v1 coco-local-report</span></p>
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
      <label>Google Order <select id="gmbFilter"><option value="all">全部</option><option value="confirmed">Google Order 有供應商</option><option value="gap">Google Order 待查核</option><option value="no_gmb_found">GMB/Maps 未找到</option></select></label>
      <label class="search">搜尋門市<input id="searchInput" type="search" placeholder="門市、地址、城市" /></label>
    </section>

    <section class="insight-strip" id="insightStrip"></section>

    <section class="panel">
      <div class="section-title">
        <div><p class="eyebrow">1. Store Footprint</p><h2>門市分布與來源覆蓋</h2></div>
        <p>Nidin CoCo 品牌頁回傳的台灣門市母體，並以 22 縣市地圖檢視分布；GMB/Google 欄位會隨後續 live audit 回寫。</p>
      </div>
      <div class="kpi-grid" id="storeKpis"></div>
      <div class="split map-layout">
        <div>
          <h3>台灣門市地圖</h3>
          <p class="map-source">支援全台 22 縣市，無門市縣市顯示 0。</p>
          <div class="taiwan-map" id="taiwanMap"></div>
        </div>
        <div><h3>城市排序</h3><div class="bars" id="cityBars"></div></div>
      </div>
    </section>

    <section class="panel">
      <div class="section-title">
        <div><p class="eyebrow">2. All Sources</p><h2>全來源點餐系統</h2></div>
        <p>Nidin direct portal 是目前已確認的全來源點餐證據；Uber Eats、foodpanda、LINE、QuickClick 等平台若後續可匹配到門市，會以非 GMB sourceType 寫入。</p>
      </div>
      <div class="kpi-grid" id="allSourceKpis"></div>
      <div class="split">
        <div><h3>自取系統</h3><div class="bars" id="pickupBars"></div></div>
        <div><h3>外送系統</h3><div class="bars" id="deliveryBars"></div></div>
      </div>
      <div class="split compact">
        <div><h3>區域導入率</h3><div class="matrix" id="regionMatrix"></div></div>
        <div><h3>說明</h3><p class="note">全來源採用門市母體與平台 direct evidence；Google Order provider evidence 另列，避免把背景頁、官方連結或 marketplace snippet 誤算成 GMB provider。</p></div>
      </div>
    </section>

    <section class="panel warning">
      <div class="section-title">
        <div><p class="eyebrow">3. Google Order</p><h2>Google Order provider / link 總覽</h2></div>
        <p>只有在正確 GMB profile 的藍色線上點餐流程內，讀到可見 provider row 時，才列入 Google Order provider。待查核是 coverage gap，不代表沒有點餐。</p>
      </div>
      <div class="kpi-grid" id="gmbKpis"></div>
      <div class="split">
        <div><h3>Google Order 自取選項</h3><div class="bars" id="gmbPickupBars"></div></div>
        <div><h3>Google Order 外送選項</h3><div class="bars" id="gmbDeliveryBars"></div></div>
      </div>
    </section>

    <section class="panel">
      <div class="section-title"><div><p class="eyebrow">4. Comparison</p><h2>全來源 vs Google Order provider</h2></div></div>
      <div class="table-wrap"><table><thead><tr><th>系統</th><th>全來源門市</th><th>全來源採用率</th><th>Google Order provider 門市</th><th>Google Order provider 覆蓋率</th><th>差距</th></tr></thead><tbody id="comparisonRows"></tbody></table></div>
    </section>

    <section class="panel">
      <div class="section-title"><div><p class="eyebrow">5. Store Details</p><h2>門市明細</h2></div><p id="detailCount"></p></div>
      <div class="table-wrap details"><table><thead><tr><th>門市</th><th>區域</th><th>地址</th><th>全來源點餐</th><th>Google Order 證據</th><th>連結 / 審核</th></tr></thead><tbody id="storeRows"></tbody></table></div>
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
        "generatedAt": summary.get("generatedAt"),
        "brand": summary.get("brand"),
        "source": summary.get("source"),
        "stores": stores,
    }
    (DATA / "stores.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (DATA / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (OUT / "data-inline.js").write_text(
        "window.DAMING_DATA = "
        + json.dumps({"storesPayload": payload, "summary": summary}, ensure_ascii=False)
        + ";\n",
        encoding="utf-8",
    )
    (OUT / "index.html").write_text(report_html(), encoding="utf-8")
    write_csv(stores)


def load_existing_stores() -> list[dict]:
    payload = json.loads((DATA / "stores.json").read_text(encoding="utf-8"))
    return payload["stores"] if isinstance(payload, dict) and "stores" in payload else payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--from-existing", action="store_true", help="Rebuild summary/HTML from existing coco/data/stores.json.")
    args = parser.parse_args()

    if args.from_existing:
        stores = load_existing_stores()
        raw_count = len(stores)
        quickclick = {}
        reachability = {}
    else:
        raw = fetch_nidin_stores()
        stores = [store_record(item, index) for index, item in enumerate(raw, start=1)]
        raw_count = len(raw)
        quickclick = quickclick_audit()
        reachability = platform_reachability_audit()

    summary = build_summary(stores, raw_count, quickclick, reachability)
    write_outputs(stores, summary)
    print(
        json.dumps(
            {
                "report": str(OUT),
                "officialStoreCount": summary["officialStoreCount"],
                "anyOrderingSystemCount": summary["anyOrderingSystemCount"],
                "gmbFoundCount": summary["gmbFoundCount"],
                "gmbOrderingSystemCount": summary["gmbOrderingSystemCount"],
                "allSourceSystemCounts": summary["allSourceSystemCounts"],
                "gmbOrderingStatusCounts": summary["gmbOrderingStatusCounts"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

