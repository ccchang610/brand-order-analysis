from __future__ import annotations

import csv
import json
import re
from collections import Counter
from datetime import date
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "milksha"
DATA = OUT / "data"
DATA.mkdir(parents=True, exist_ok=True)

BRAND = "迷客夏 Milksha"
BRAND_SLUG = "milksha"
MARKET = "Taiwan"
OFFICIAL_URL = "https://www.milksha.com/"
STORE_URL = "https://www.milksha.com/store_detail.php?uID=1"
OFFICIAL_ORDER_URL = "https://www.milksha.com/order.php"
NIDIN_URL = "https://milksha.nidin.shop/"
NIDIN_API = "https://loctw-service-api.nidin.shop/shopper/v2"
NIDIN_BRAND_CODE = "milkshoptea"
NIDIN_BRAND_KEY = "98985253"
CHECKED_AT = date.today().isoformat()

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"
    ),
    "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
}

NIDIN_HEADERS = {
    **HEADERS,
    "Content-Type": "application/json",
    "MC-API-Brand-Key": NIDIN_BRAND_KEY,
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


def clean(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").replace("\xa0", " ")).strip()


def canonical(value: str) -> str:
    return (
        clean(value)
        .replace("臺", "台")
        .replace("巿", "市")
        .replace("　", " ")
        .replace("❄️", "")
        .replace("❄", "")
    )


def canonical_name(value: str) -> str:
    value = canonical(value)
    value = re.sub(r"(?i)milksha\s*plus", "", value)
    value = re.sub(r"(?i)milksha", "", value)
    value = value.replace("迷客夏", "")
    value = re.sub(r"[()（）].*?[)）]", "", value)
    value = value.replace("Plus", "")
    value = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]", "", value)
    return value


def canonical_address(value: str) -> str:
    value = canonical(value)
    value = re.sub(r"^\d{3,6}", "", value)
    value = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]", "", value)
    return value


def city_from_address(address: str) -> str:
    text = canonical(address)
    for city in TAIWAN_CITIES:
        if city in text:
            return city
    return ""


def district_from_address(address: str, city: str) -> str:
    text = canonical(address)
    tail = text.split(city, 1)[1] if city and city in text else text
    match = re.search(r"([\u4e00-\u9fff]{1,5}(?:區|鄉|鎮|市))", tail)
    return match.group(1) if match else ""


def fetch_html(url: str) -> str:
    response = requests.get(url, headers=HEADERS, timeout=45)
    response.raise_for_status()
    response.encoding = "utf-8"
    return response.text


def split_store_anchor(text: str) -> tuple[str, str, str, str]:
    text = clean(re.sub(r"^MAP\s*", "", text))
    city_pattern = "|".join(re.escape(city) for city in TAIWAN_CITIES + [c.replace("台", "臺") for c in TAIWAN_CITIES])
    matches = list(re.finditer(rf"(?:\d{{3,6}}\s*)?(?:{city_pattern})", canonical(text)))
    match = None
    for candidate in matches:
        tail_probe = canonical(text[candidate.end() : candidate.end() + 12])
        prefix_probe = canonical(text[max(0, candidate.start() - 8) : candidate.start()])
        if re.search(r"\d{3,6}\s*$", prefix_probe) or re.match(r"[\u4e00-\u9fff]{1,5}(?:區|鄉|鎮|市)", tail_probe):
            match = candidate
            break
    if match is None and matches:
        match = matches[-1]
    if not match:
        return text, "", "", ""
    name = clean(text[: match.start()])
    tail = clean(text[match.start() :])

    phone_match = None
    phone_pattern = re.compile(r"(?<!\d)(?:0\d{1,3}[-\s]?\d{3,4}[-\s]?\d{3,4}|\(0\d{1,3}\)\s*\d{3,4}[-\s]?\d{3,4}|09\d{2}[-\s]?\d{3}[-\s]?\d{3})(?!\d)")
    for candidate in phone_pattern.finditer(tail):
        phone_match = candidate

    if phone_match:
        address = clean(tail[: phone_match.start()])
        phone = clean(phone_match.group(0))
        hours = clean(tail[phone_match.end() :])
    else:
        hour_match = re.search(r"(平日|假日|週一|週二|週三|週四|週五|週六|週日|\d{1,2}[:：]\d{2})", tail)
        if hour_match:
            address = clean(tail[: hour_match.start()])
            hours = clean(tail[hour_match.start() :])
        else:
            address = tail
            hours = ""
        phone = ""
    return name, canonical(address), phone, hours


def official_stores() -> list[dict]:
    soup = BeautifulSoup(fetch_html(STORE_URL), "html.parser")
    stores: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for anchor in soup.find_all("a"):
        href = anchor.get("href") or ""
        if not any(token in href for token in ("share.google", "maps.app.goo.gl", "goo.gl", "google.com")):
            continue
        text = clean(anchor.get_text(" ", strip=True))
        if not text.startswith("MAP "):
            continue
        name, address, phone, hours = split_store_anchor(text)
        if not name or not address:
            continue
        key = (canonical_name(name), canonical_address(address))
        if key in seen:
            continue
        seen.add(key)
        city = city_from_address(address)
        stores.append(
            {
                "brand": BRAND,
                "storeId": f"milksha-{len(stores) + 1:03d}",
                "storeName": name,
                "country": "Taiwan",
                "market": MARKET,
                "regionGroup": REGION_BY_CITY.get(city, "未判定"),
                "city": city or "未判定",
                "county": city or "未判定",
                "district": district_from_address(address, city),
                "address": address,
                "latitude": "",
                "longitude": "",
                "phone": phone,
                "hours": hours,
                "officialSourceUrl": STORE_URL,
                "officialStoreUrl": STORE_URL,
                "officialMapUrl": href,
                "googleSearchUrl": f"https://www.google.com/search?q={requests.utils.quote(f'{BRAND} {name} {address}')}&hl=zh-TW",
                "gmbUrl": urljoin(STORE_URL, href),
                "gmbStatus": "confirmed",
                "gmbOrderingStatus": "needs_manual_review",
                "sourceCoverage": {
                    "officialListed": True,
                    "gmbFound": True,
                    "googleFound": True,
                    "thirdPartyFound": False,
                },
                "orderingSystems": [],
                "hasAnyOrderingSystem": False,
                "hasGmbOrderingSystem": False,
                "manualReviewReason": "Google Order provider panel not audited yet.",
                "evidenceNotes": "Official Milksha store locator provides this store and its Google Maps link.",
                "checkedAt": CHECKED_AT,
            }
        )
    return stores


def nidin_stores() -> list[dict]:
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
        response = requests.get(f"{NIDIN_API}/store/listByPositionNew", headers=NIDIN_HEADERS, params=params, timeout=45)
        response.raise_for_status()
        payload = response.json()
        batch = payload.get("list") or []
        meta = payload.get("meta") or {}
        total = meta.get("total_amount") or len(batch)
        stores.extend(batch)
        if not batch:
            break
        page += 1
    return stores


def match_nidin(official: list[dict], nidin: list[dict]) -> int:
    remaining = set(range(len(nidin)))
    matches = 0

    for store in official:
        store_name = canonical_name(store["storeName"])
        store_addr = canonical_address(store["address"])
        best_index = None
        best_score = 0
        for index in list(remaining):
            item = nidin[index]
            n_name = canonical_name(item.get("name") or item.get("name_short") or "")
            n_addr = canonical_address(item.get("address") or "")
            score = 0
            if n_name and (store_name == n_name or store_name in n_name or n_name in store_name):
                score += 5
            if n_addr and (store_addr == n_addr or store_addr in n_addr or n_addr in store_addr):
                score += 6
            if store.get("phone") and item.get("tel") and re.sub(r"\D", "", store["phone"]) == re.sub(r"\D", "", item["tel"]):
                score += 4
            if store.get("city") and store["city"] in canonical(item.get("address") or ""):
                score += 1
            if score > best_score:
                best_score = score
                best_index = index
        if best_index is None or best_score < 5:
            continue

        item = nidin[best_index]
        remaining.remove(best_index)
        matches += 1
        if item.get("latitude"):
            store["latitude"] = item["latitude"]
        if item.get("longitude"):
            store["longitude"] = item["longitude"]
        nidin_store_url = f"https://milksha.nidin.shop/menu/{item['id']}"
        store["orderingSystems"].append(
            {
                "system": "Nidin",
                "sourceType": "official",
                "orderMode": ["pickup", "delivery"],
                "evidenceUrl": nidin_store_url,
                "label": "迷點連結 Nidin",
                "confidence": "confirmed",
            }
        )
        store["hasAnyOrderingSystem"] = True
        store["sourceCoverage"]["thirdPartyFound"] = True
        store["evidenceNotes"] = f"Matched official store to Milksha Nidin store id {item['id']}."
    return matches


def count_systems(stores: list[dict], *, gmb_only: bool = False, mode: str | None = None) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for store in stores:
        systems = set()
        for claim in store.get("orderingSystems", []):
            if gmb_only and claim.get("sourceType") != "gmb":
                continue
            if mode and mode not in claim.get("orderMode", []):
                continue
            if claim.get("confidence") in {"confirmed", "partial"}:
                systems.add(claim["system"])
        for system in systems:
            counts[system] += 1
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))


def rate(count: int, total: int) -> float:
    return round(count / total, 4) if total else 0.0


def build_summary(stores: list[dict], nidin_total: int, nidin_matches: int) -> dict:
    total = len(stores)
    city_counts = {city: 0 for city in TAIWAN_CITIES}
    region_counts = {region: 0 for region in REGIONS}
    source_coverage_counts: Counter[str] = Counter()
    gmb_status_counts: Counter[str] = Counter()
    gmb_ordering_status_counts: Counter[str] = Counter()
    for store in stores:
        city_counts[store.get("city") or "未判定"] = city_counts.get(store.get("city") or "未判定", 0) + 1
        region_counts[store.get("regionGroup") or "未判定"] = region_counts.get(store.get("regionGroup") or "未判定", 0) + 1
        gmb_status_counts[store.get("gmbStatus") or "unknown"] += 1
        gmb_ordering_status_counts[store.get("gmbOrderingStatus") or "unknown"] += 1
        for key, enabled in store.get("sourceCoverage", {}).items():
            if enabled:
                source_coverage_counts[key] += 1

    any_ordering = sum(1 for store in stores if store.get("hasAnyOrderingSystem"))
    gmb_ordering = sum(1 for store in stores if store.get("hasGmbOrderingSystem"))
    all_counts = count_systems(stores)
    gmb_counts = count_systems(stores, gmb_only=True)
    systems = sorted(set(all_counts) | set(gmb_counts))
    comparison = [
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

    return {
        "generatedAt": CHECKED_AT,
        "brand": BRAND,
        "brandSlug": BRAND_SLUG,
        "market": MARKET,
        "sitePath": "/brand-order-analysis/milksha/",
        "officialStoreCount": total,
        "gmbFoundCount": source_coverage_counts.get("gmbFound", 0),
        "gmbMissingCount": total - source_coverage_counts.get("gmbFound", 0),
        "googleFoundCount": source_coverage_counts.get("googleFound", 0),
        "thirdPartyFoundCount": source_coverage_counts.get("thirdPartyFound", 0),
        "verificationGapCount": sum(1 for store in stores if store.get("gmbOrderingStatus") != "confirmed"),
        "anyOrderingSystemCount": any_ordering,
        "anyOrderingSystemAdoptionRate": rate(any_ordering, total),
        "googleOrderEntryCount": gmb_ordering,
        "googleOrderEntryRate": rate(gmb_ordering, total),
        "gmbOrderingSystemCount": gmb_ordering,
        "gmbOrderingSystemAdoptionRate": rate(gmb_ordering, total),
        "gmbCoverageGapCount": total - gmb_ordering,
        "unknownOrderingSystemCount": total - any_ordering,
        "cityCounts": city_counts,
        "regionCounts": region_counts,
        "allSourceSystemCounts": all_counts,
        "allSourcePickupSystemCounts": count_systems(stores, mode="pickup"),
        "allSourceDeliverySystemCounts": count_systems(stores, mode="delivery"),
        "gmbSystemCounts": gmb_counts,
        "gmbPickupSystemCounts": count_systems(stores, gmb_only=True, mode="pickup"),
        "gmbDeliverySystemCounts": count_systems(stores, gmb_only=True, mode="delivery"),
        "allSourceSystemAdoptionRates": {system: rate(count, total) for system, count in all_counts.items()},
        "gmbSystemAdoptionRates": {system: rate(count, total) for system, count in gmb_counts.items()},
        "systemComparison": comparison,
        "gmbStatusCounts": dict(gmb_status_counts),
        "gmbOrderingStatusCounts": dict(gmb_ordering_status_counts),
        "sourceCoverageCounts": dict(source_coverage_counts),
        "source": {
            "officialWebsite": OFFICIAL_URL,
            "officialStoreList": STORE_URL,
            "officialOrdering": OFFICIAL_ORDER_URL,
            "officialOrderingProvider": NIDIN_URL,
            "nidinApiStoreCount": nidin_total,
            "nidinMatchedOfficialStoreCount": nidin_matches,
            "notes": "Official Milksha store locator provides the store population. Official online ordering links to Nidin. Google Order provider evidence must be counted only after opening the Google Order panel.",
        },
        "notes": [
            "Initial Milksha build uses the official store locator as the official store population.",
            "Nidin is counted as all-source official ordering evidence only for official stores matched to the Milksha Nidin store API.",
            "Google Order provider evidence remains pending until GMB blue-button panels are opened and provider rows are confirmed.",
        ],
    }


def write_csv(stores: list[dict]) -> None:
    fields = [
        "storeId",
        "storeName",
        "city",
        "district",
        "regionGroup",
        "address",
        "phone",
        "hours",
        "gmbUrl",
        "gmbOrderingStatus",
        "allSourceSystems",
        "gmbSystems",
        "manualReviewReason",
    ]
    with (DATA / "stores.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for store in stores:
            all_systems = sorted({claim["system"] for claim in store.get("orderingSystems", [])})
            gmb_systems = sorted({claim["system"] for claim in store.get("orderingSystems", []) if claim.get("sourceType") == "gmb"})
            writer.writerow(
                {
                    "storeId": store["storeId"],
                    "storeName": store["storeName"],
                    "city": store["city"],
                    "district": store["district"],
                    "regionGroup": store["regionGroup"],
                    "address": store["address"],
                    "phone": store["phone"],
                    "hours": store["hours"],
                    "gmbUrl": store["gmbUrl"],
                    "gmbOrderingStatus": store["gmbOrderingStatus"],
                    "allSourceSystems": ", ".join(all_systems),
                    "gmbSystems": ", ".join(gmb_systems),
                    "manualReviewReason": store["manualReviewReason"],
                }
            )


def write_html() -> None:
    (OUT / "index.html").write_text(
        """<!doctype html>
<html lang="zh-Hant">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>迷客夏 Milksha 點餐系統總攬</title>
  <link rel="stylesheet" href="../assets/styles.css?v=31" />
</head>
<body>
  <header class="topbar">
    <div>
      <p class="eyebrow">Brand Order Analysis</p>
      <h1>迷客夏 Milksha 點餐系統總攬</h1>
      <p class="subhead">以迷客夏官網台灣門市清單為母體，對照官方迷點連結 Nidin 與 Google/GMB 訂餐入口。<span class="version">v1 milksha-initial</span></p>
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
      <label>Google Order 狀態<select id="gmbFilter"><option value="all">全部</option><option value="confirmed">Google Order 已確認</option><option value="gap">Google Order 缺口</option><option value="no_gmb_found">GMB 未找到</option></select></label>
      <label class="search">搜尋門市<input id="searchInput" type="search" placeholder="門市、地址、城市" /></label>
    </section>

    <section class="insight-strip" id="insightStrip"></section>

    <section class="panel">
      <div class="section-title">
        <div><p class="eyebrow">1. Store Footprint</p><h2>門市分布</h2></div>
        <p>官方門市頁提供台灣門市與 Google Maps 連結；地圖用官網地址解析縣市。</p>
      </div>
      <div class="kpi-grid" id="storeKpis"></div>
      <div class="split map-layout">
        <div>
          <h3>台灣門市地圖</h3>
          <p class="map-source">依 22 縣市統計，未設店縣市顯示 0。</p>
          <div class="taiwan-map" id="taiwanMap"></div>
        </div>
        <div><h3>城市排行</h3><div class="bars" id="cityBars"></div></div>
      </div>
    </section>

    <section class="panel">
      <div class="section-title">
        <div><p class="eyebrow">2. All Sources</p><h2>全來源點餐系統</h2></div>
        <p>官方線上點餐頁連到迷點連結 Nidin；本報表只把可對到 Nidin 門市 API 的店列為逐店確認。</p>
      </div>
      <div class="kpi-grid" id="allSourceKpis"></div>
      <div class="split">
        <div><h3>自取系統</h3><div class="bars" id="pickupBars"></div></div>
        <div><h3>外送系統</h3><div class="bars" id="deliveryBars"></div></div>
      </div>
      <div class="split compact">
        <div><h3>區域導入率</h3><div class="matrix" id="regionMatrix"></div></div>
        <div><h3>判讀備註</h3><p class="note">Nidin 來自迷客夏官方線上點餐頁與 Nidin 品牌門市 API；Google Order provider evidence 需另以 GMB 藍色訂餐面板逐店確認。</p></div>
      </div>
    </section>

    <section class="panel warning">
      <div class="section-title">
        <div><p class="eyebrow">3. Google Order</p><h2>Google Order 供應商證據</h2></div>
        <p>只有打開 Google Order 面板並讀到供應商列才算 GMB 供應商。未確認店家視為 coverage gap，不代表沒有點餐系統。</p>
      </div>
      <div class="kpi-grid" id="gmbKpis"></div>
      <div class="split">
        <div><h3>Google Order 自取供應商</h3><div class="bars" id="gmbPickupBars"></div></div>
        <div><h3>Google Order 外送供應商</h3><div class="bars" id="gmbDeliveryBars"></div></div>
      </div>
    </section>

    <section class="panel">
      <div class="section-title"><div><p class="eyebrow">4. Comparison</p><h2>全來源 vs Google Order</h2></div></div>
      <div class="table-wrap"><table><thead><tr><th>系統</th><th>全來源門市</th><th>全來源採用率</th><th>Google Order 門市</th><th>Google Order 覆蓋率</th><th>差距</th></tr></thead><tbody id="comparisonRows"></tbody></table></div>
    </section>

    <section class="panel">
      <div class="section-title"><div><p class="eyebrow">5. Store Details</p><h2>門市明細</h2></div><span id="detailCount"></span></div>
      <div class="table-wrap"><table><thead><tr><th>門市</th><th>區域</th><th>地址</th><th>全來源系統</th><th>Google Order 證據</th><th>連結 / 備註</th></tr></thead><tbody id="storeRows"></tbody></table></div>
    </section>
  </main>

  <script src="../assets/taiwan-map.js?v=31"></script>
  <script src="../assets/app.js?v=31"></script>
</body>
</html>
""",
        encoding="utf-8",
    )


def main() -> None:
    stores = official_stores()
    nidin = nidin_stores()
    nidin_matches = match_nidin(stores, nidin)
    summary = build_summary(stores, len(nidin), nidin_matches)

    (DATA / "stores.json").write_text(json.dumps({"stores": stores}, ensure_ascii=False, indent=2), encoding="utf-8")
    (DATA / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    write_csv(stores)
    write_html()
    print(json.dumps({"official": len(stores), "nidinApi": len(nidin), "nidinMatched": nidin_matches}, ensure_ascii=False))


if __name__ == "__main__":
    main()
