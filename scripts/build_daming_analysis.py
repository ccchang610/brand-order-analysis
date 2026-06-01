from __future__ import annotations

import csv
import json
import re
import time
from collections import Counter
from datetime import date
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
DATA.mkdir(exist_ok=True)

BRAND = "大茗本位製茶堂"
MARKET = "Taiwan"
OFFICIAL_URL = "https://www.damingtea.com.tw/stores/"
CHECKED_AT = date.today().isoformat()
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
    "Referer": "https://www.damingtea.com.tw/",
}

TAIWAN_CITIES = [
    "台北市",
    "新北市",
    "基隆市",
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
    **{city: "北部" for city in ["台北市", "新北市", "基隆市", "桃園市", "新竹市", "新竹縣", "宜蘭縣"]},
    **{city: "中部" for city in ["苗栗縣", "台中市", "彰化縣", "南投縣", "雲林縣"]},
    **{city: "南部" for city in ["嘉義市", "嘉義縣", "台南市", "高雄市", "屏東縣"]},
    **{city: "東部" for city in ["花蓮縣", "台東縣"]},
    **{city: "離島" for city in ["澎湖縣", "金門縣", "連江縣"]},
}
REGIONS = ["北部", "中部", "南部", "東部", "離島"]


def fetch(url: str, timeout: int = 45) -> tuple[str, str]:
    request = Request(url, headers=HEADERS)
    with urlopen(request, timeout=timeout) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, "replace"), response.geturl()


def clean(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").replace("\u200b", " ").replace("臺", "台")).strip()


def get_city(address: str) -> str:
    normalized = clean(address)
    if normalized.startswith("屏東市"):
        return "屏東縣"
    for city in TAIWAN_CITIES:
        if city in normalized:
            return city
    return ""


def get_district(address: str, city: str) -> str:
    normalized = clean(address)
    if normalized.startswith("屏東市"):
        return "屏東市"
    tail = normalized.split(city, 1)[1] if city and city in normalized else normalized
    for suffix in ("區", "鄉", "鎮", "市"):
        pos = tail.find(suffix)
        if pos >= 0:
            start = max(0, pos - 7)
            return re.sub(r"^[\d\s巷弄路街段號之-]+", "", tail[start : pos + 1])
    return ""


def classify_url(url: str, label: str, title: str = "") -> tuple[str, str, list[str], str]:
    haystack = f"{url} {label} {title}".lower().replace("\xa0", " ")
    if "order.nidin.shop" in haystack or "nidin" in haystack:
        return "Nidin", "official", ["pickup", "delivery"], "confirmed"
    if "ubereats" in haystack or "uber eats" in haystack:
        return "Uber Eats", "marketplace", ["delivery"], "confirmed"
    if "foodpanda" in haystack:
        return "foodpanda", "marketplace", ["delivery"], "confirmed"
    if "lin.ee" in haystack or "line" in haystack:
        return "LINE", "line", ["unknown"], "partial"
    return "外送平台（待確認）", "third_party", ["unknown"], "needs_manual_review"


def resolve_delivery_link(url: str) -> tuple[str, str]:
    try:
        body, final_url = fetch(url, timeout=25)
        soup = BeautifulSoup(body, "html.parser")
        title = clean(soup.title.get_text(" ", strip=True) if soup.title else "")
        meta_title = soup.find("meta", property="og:title")
        if meta_title and meta_title.get("content"):
            title = clean(meta_title["content"]) or title
        return final_url, title
    except Exception as exc:
        return url, f"unresolved:{type(exc).__name__}"


def parse_official_stores() -> list[dict]:
    body, _ = fetch(OFFICIAL_URL)
    soup = BeautifulSoup(body, "html.parser")
    stores: list[dict] = []
    seen: set[tuple[str, str]] = set()

    for index, item in enumerate(soup.select("li.facItem"), start=1):
        heading = item.find("h3")
        if not heading:
            continue
        name = clean(heading.get_text(" ", strip=True))
        links = [(clean(anchor.get_text(" ", strip=True)), anchor.get("href") or "") for anchor in item.find_all("a")]

        phone = ""
        address = ""
        map_url = ""
        official_store_url = ""
        ordering_claims = []

        for label, href in links:
            if href.startswith("tel:") and not phone:
                phone = label or href.replace("tel:", "")
            elif "damingtea.com.tw/stores-detail" in href and not official_store_url:
                official_store_url = href
            elif any(domain in href for domain in ["google.com", "maps.app.goo.gl", "g.co", "share.google"]) and not map_url:
                address = label
                map_url = href

        if not address:
            for line in item.get_text("\n", strip=True).split("\n"):
                candidate = clean(line)
                if get_city(candidate) or candidate.startswith("屏東市"):
                    address = candidate
                    break

        hours = ""
        lines = [clean(line) for line in item.get_text("\n", strip=True).split("\n") if clean(line)]
        for line in lines:
            if line != phone and re.search(r"\d{1,2}[:：]\d{2}|\d{1,2}\s*[~-]\s*\d{1,2}", line):
                hours = line
                break

        city = get_city(address)
        district = get_district(address, city)
        region = REGION_BY_CITY.get(city, "未分類")

        for label, href in links:
            if not href or href.startswith("tel:") or href == map_url or href == official_store_url:
                continue
            if label in {"立即訂餐", "外送平台"} or any(
                domain in href for domain in ["order.nidin.shop", "ubereats.com", "foodpanda.com.tw", "reurl.cc", "lin.ee"]
            ):
                evidence_url = href
                title = ""
                if "reurl.cc" in href:
                    time.sleep(0.12)
                    evidence_url, title = resolve_delivery_link(href)
                system, source_type, order_mode, confidence = classify_url(evidence_url, label, title)
                claim = {
                    "system": system,
                    "sourceType": source_type,
                    "orderMode": order_mode,
                    "evidenceUrl": evidence_url,
                    "originalUrl": href,
                    "label": label,
                    "confidence": confidence,
                }
                if title:
                    claim["evidenceTitle"] = title[:160]
                ordering_claims.append(claim)

        deduped_claims = []
        claim_keys = set()
        for claim in ordering_claims:
            key = (claim["system"], claim["sourceType"], claim["evidenceUrl"])
            if key in claim_keys:
                continue
            claim_keys.add(key)
            deduped_claims.append(claim)

        key = (name, address)
        if key in seen:
            continue
        seen.add(key)

        gmb_found = bool(map_url)
        third_party_found = any(claim["sourceType"] in {"marketplace", "third_party", "line"} for claim in deduped_claims)
        stores.append(
            {
                "brand": BRAND,
                "storeId": f"daming-{index:03d}",
                "storeName": name,
                "country": "Taiwan",
                "market": MARKET,
                "regionGroup": region,
                "city": city,
                "county": city,
                "district": district,
                "address": address,
                "latitude": None,
                "longitude": None,
                "phone": phone,
                "hours": hours,
                "officialSourceUrl": OFFICIAL_URL,
                "officialStoreUrl": official_store_url,
                "officialMapUrl": map_url,
                "googleSearchUrl": f"https://www.google.com/search?q={quote(BRAND + ' ' + name + ' ' + address)}",
                "gmbUrl": map_url,
                "gmbStatus": "confirmed" if gmb_found else "not_found",
                "gmbOrderingStatus": "unavailable_or_blocked" if gmb_found else "not_found",
                "sourceCoverage": {
                    "officialListed": True,
                    "gmbFound": gmb_found,
                    "googleFound": gmb_found,
                    "thirdPartyFound": third_party_found,
                },
                "orderingSystems": deduped_claims,
                "hasAnyOrderingSystem": bool(deduped_claims),
                "hasGmbOrderingSystem": any(claim["sourceType"] == "gmb" for claim in deduped_claims),
                "manualReviewReason": (
                    "Google Order button is dynamic/not batch-readable; all-source official/platform links are audited separately."
                    if gmb_found
                    else "No Google/GMB link found in official store listing."
                ),
                "evidenceNotes": (
                    "Official store list supplied store population, Google/Maps link, and visible order/delivery links. "
                    "Google Order provider evidence requires manual browser review."
                ),
                "checkedAt": CHECKED_AT,
            }
        )
    return stores


def count_systems(stores: list[dict], *, gmb_only: bool = False) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for store in stores:
        systems = set()
        for claim in store["orderingSystems"]:
            if gmb_only and claim.get("sourceType") != "gmb":
                continue
            if claim.get("confidence") in {"confirmed", "partial"}:
                systems.add(claim["system"])
        for system in systems:
            counts[system] += 1
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))


def make_summary(stores: list[dict]) -> dict:
    total = len(stores)
    city_counts = {city: 0 for city in TAIWAN_CITIES}
    region_counts = {region: 0 for region in REGIONS}
    source_coverage_counts: Counter[str] = Counter()

    for store in stores:
        city_counts.setdefault(store["city"] or "未分類", 0)
        city_counts[store["city"] or "未分類"] += 1
        region_counts.setdefault(store["regionGroup"], 0)
        region_counts[store["regionGroup"]] += 1
        for key, enabled in store["sourceCoverage"].items():
            if enabled:
                source_coverage_counts[key] += 1

    all_source_counts = count_systems(stores)
    gmb_counts = count_systems(stores, gmb_only=True)

    def rate(count: int) -> float:
        return round(count / total, 4) if total else 0

    systems = sorted(set(all_source_counts) | set(gmb_counts))
    comparison = [
        {
            "system": system,
            "allSourceStoreCount": all_source_counts.get(system, 0),
            "allSourceAdoptionRate": rate(all_source_counts.get(system, 0)),
            "gmbStoreCount": gmb_counts.get(system, 0),
            "gmbAdoptionRate": rate(gmb_counts.get(system, 0)),
            "countGap": all_source_counts.get(system, 0) - gmb_counts.get(system, 0),
            "percentagePointGap": round(rate(all_source_counts.get(system, 0)) - rate(gmb_counts.get(system, 0)), 4),
        }
        for system in systems
    ]

    any_count = sum(1 for store in stores if store["hasAnyOrderingSystem"])
    gmb_order_count = sum(1 for store in stores if store["hasGmbOrderingSystem"])
    gmb_gap = sum(1 for store in stores if store["gmbOrderingStatus"] != "confirmed")
    unknown = sum(1 for store in stores if not store["hasAnyOrderingSystem"])

    return {
        "generatedAt": CHECKED_AT,
        "brand": BRAND,
        "market": MARKET,
        "officialStoreCount": total,
        "gmbFoundCount": sum(1 for store in stores if store["sourceCoverage"]["gmbFound"]),
        "googleFoundCount": sum(1 for store in stores if store["sourceCoverage"]["googleFound"]),
        "thirdPartyFoundCount": sum(1 for store in stores if store["sourceCoverage"]["thirdPartyFound"]),
        "verificationGapCount": gmb_gap,
        "anyOrderingSystemCount": any_count,
        "anyOrderingSystemAdoptionRate": rate(any_count),
        "gmbOrderingSystemCount": gmb_order_count,
        "gmbOrderingSystemAdoptionRate": rate(gmb_order_count),
        "gmbCoverageGapCount": gmb_gap,
        "unknownOrderingSystemCount": unknown,
        "cityCounts": city_counts,
        "regionCounts": region_counts,
        "allSourceSystemCounts": all_source_counts,
        "gmbSystemCounts": gmb_counts,
        "allSourceSystemAdoptionRates": {system: rate(count) for system, count in all_source_counts.items()},
        "gmbSystemAdoptionRates": {system: rate(count) for system, count in gmb_counts.items()},
        "systemComparison": comparison,
        "gmbStatusCounts": dict(Counter(store["gmbStatus"] for store in stores)),
        "gmbOrderingStatusCounts": dict(Counter(store["gmbOrderingStatus"] for store in stores)),
        "sourceCoverageCounts": dict(source_coverage_counts),
        "source": {
            "officialStoreList": OFFICIAL_URL,
            "officialWebsite": "https://www.damingtea.com.tw/",
            "notes": (
                "Official store page provides the store population, embedded Google/Maps links, "
                "Nidin order links, and delivery platform links. Google Order buttons were not "
                "batch-readable from static HTML and are counted as Google Order provider evidence gaps."
            ),
        },
        "notes": [
            "Adoption rates use official store count as denominator.",
            "All-source ordering systems come from official page order/delivery links and resolved platform links.",
            "Google Order provider evidence are not inferred from official-page links; dynamic Google Order entries require manual browser review.",
        ],
    }


def write_data(stores: list[dict], summary: dict) -> None:
    (DATA / "stores.json").write_text(
        json.dumps({"generatedAt": CHECKED_AT, "brand": BRAND, "source": summary["source"], "stores": stores}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (DATA / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

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
            all_systems = sorted({claim["system"] for claim in store["orderingSystems"]})
            gmb_systems = sorted({claim["system"] for claim in store["orderingSystems"] if claim["sourceType"] == "gmb"})
            evidence = sorted({claim["evidenceUrl"] for claim in store["orderingSystems"] if claim.get("evidenceUrl")})
            writer.writerow(
                {
                    "storeId": store["storeId"],
                    "storeName": store["storeName"],
                    "regionGroup": store["regionGroup"],
                    "city": store["city"],
                    "district": store["district"],
                    "address": store["address"],
                    "phone": store["phone"],
                    "hours": store["hours"],
                    "gmbStatus": store["gmbStatus"],
                    "gmbOrderingStatus": store["gmbOrderingStatus"],
                    "hasAnyOrderingSystem": store["hasAnyOrderingSystem"],
                    "hasGmbOrderingSystem": store["hasGmbOrderingSystem"],
                    "allSourceSystems": "、".join(all_systems),
                    "gmbSystems": "、".join(gmb_systems),
                    "officialSourceUrl": store["officialSourceUrl"],
                    "officialStoreUrl": store["officialStoreUrl"],
                    "gmbUrl": store["gmbUrl"],
                    "evidenceLinks": " | ".join(evidence),
                    "manualReviewReason": store["manualReviewReason"],
                }
            )


def write_dashboard_files() -> None:
    (ROOT / "index.html").write_text(
        """<!doctype html>
<html lang="zh-Hant">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>大茗點餐系統總覽</title>
  <link rel="stylesheet" href="styles.css" />
</head>
<body>
  <header class="topbar">
    <div>
      <p class="eyebrow">Brand Order Analysis</p>
      <h1>大茗本位製茶堂點餐系統總覽</h1>
      <p class="subhead">官方門市、Google/GMB 覆蓋、整體點餐系統與 Google Order 供應商一次看。</p>
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
      <label>
        城市
        <select id="cityFilter"></select>
      </label>
      <label>
        系統
        <select id="systemFilter"></select>
      </label>
      <label>
        Google Order 供應商狀態
        <select id="gmbFilter">
          <option value="all">全部</option>
          <option value="confirmed">Google Order 有供應商</option>
          <option value="gap">Google Order 供應商缺口</option>
        </select>
      </label>
      <label class="search">
        搜尋門市
        <input id="searchInput" type="search" placeholder="門市、地址、城市" />
      </label>
    </section>

    <section class="panel">
      <div class="section-title">
        <div>
          <p class="eyebrow">1. Store Footprint</p>
          <h2>品牌門市總攬</h2>
        </div>
        <p>官方門市為分母，Google/GMB 連結來自官網嵌入的地圖連結。</p>
      </div>
      <div class="kpi-grid" id="storeKpis"></div>
      <div class="split">
        <div>
          <h3>台灣縣市門市分布</h3>
          <div class="map-grid" id="taiwanMap"></div>
        </div>
        <div>
          <h3>城市排行</h3>
          <div class="bars" id="cityBars"></div>
        </div>
      </div>
    </section>

    <section class="panel">
      <div class="section-title">
        <div>
          <p class="eyebrow">2. All Sources</p>
          <h2>品牌整體點餐系統</h2>
        </div>
        <p>整合官網立即訂餐、外送平台連結與已解析短網址。</p>
      </div>
      <div class="kpi-grid" id="allSourceKpis"></div>
      <div class="split">
        <div>
          <h3>整體系統排行</h3>
          <div class="bars" id="systemBars"></div>
        </div>
        <div>
          <h3>大區導入率</h3>
          <div class="matrix" id="regionMatrix"></div>
        </div>
      </div>
    </section>

    <section class="panel warning">
      <div class="section-title">
        <div>
          <p class="eyebrow">3. Google Order</p>
          <h2>Google Order 供應商總覽</h2>
        </div>
        <p>只統計藍色點餐按鈕點進去後可見的 Google Order 供應商；缺口不推論為未導入。</p>
      </div>
      <div class="kpi-grid" id="gmbKpis"></div>
      <div class="empty-chart" id="gmbChart"></div>
    </section>

    <section class="panel">
      <div class="section-title">
        <div>
          <p class="eyebrow">4. Comparison</p>
          <h2>整體來源 vs Google Order 供應商</h2>
        </div>
      </div>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>系統</th>
              <th>全來源門市</th>
              <th>全來源導入率</th>
              <th>Google Order 供應商門市</th>
              <th>Google Order 供應商覆蓋率</th>
              <th>差距</th>
            </tr>
          </thead>
          <tbody id="comparisonRows"></tbody>
        </table>
      </div>
    </section>

    <section class="panel">
      <div class="section-title">
        <div>
          <p class="eyebrow">5. Store Details</p>
          <h2>門市明細</h2>
        </div>
        <p id="detailCount"></p>
      </div>
      <div class="table-wrap details">
        <table>
          <thead>
            <tr>
              <th>門市</th>
              <th>地區</th>
              <th>地址</th>
              <th>整體系統</th>
              <th>Google Order 供應商</th>
              <th>證據</th>
            </tr>
          </thead>
          <tbody id="storeRows"></tbody>
        </table>
      </div>
    </section>
  </main>

  <script src="app.js"></script>
</body>
</html>
""",
        encoding="utf-8",
    )

    (ROOT / "styles.css").write_text(
        """*{box-sizing:border-box}body{margin:0;background:#f7f5ef;color:#20201d;font-family:Inter,'Noto Sans TC','Microsoft JhengHei',system-ui,sans-serif}a{color:#25636b;text-decoration:none}a:hover{text-decoration:underline}.topbar{display:flex;justify-content:space-between;gap:24px;align-items:flex-end;padding:28px 32px 22px;background:#fdfbf5;border-bottom:1px solid #ddd6c8;position:sticky;top:0;z-index:5}.eyebrow{margin:0 0 5px;color:#6f6a5f;font-size:12px;text-transform:uppercase;letter-spacing:.08em}.topbar h1{margin:0;font-size:28px;letter-spacing:0}.subhead{margin:8px 0 0;color:#5f5b52}.meta{display:flex;gap:12px;align-items:center;flex-wrap:wrap;font-size:13px}.meta span,.meta a{border:1px solid #d9d0bf;border-radius:999px;padding:8px 10px;background:#fff}main{padding:22px 32px 48px}.controls{display:grid;grid-template-columns:2fr 1fr 1fr 1fr 1.5fr;gap:12px;align-items:end;margin-bottom:18px}.segmented{display:flex;gap:6px;flex-wrap:wrap}.segmented button,.controls select,.controls input{height:38px;border:1px solid #cfc7b8;background:#fff;border-radius:8px;padding:0 10px;color:#20201d}.segmented button{cursor:pointer}.segmented button.active{background:#1f6f64;color:#fff;border-color:#1f6f64}.controls label{font-size:12px;color:#665f54;display:flex;flex-direction:column;gap:5px}.search input{width:100%}.panel{background:#fff;border:1px solid #ddd6c8;border-radius:8px;padding:20px;margin:0 0 18px;box-shadow:0 10px 24px rgba(37,33,24,.06)}.panel.warning{border-color:#e3c37b;background:#fffaf0}.section-title{display:flex;justify-content:space-between;gap:16px;align-items:flex-end;margin-bottom:16px}.section-title h2{margin:0;font-size:21px}.section-title p:last-child{margin:0;color:#666;max-width:560px}.kpi-grid{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:10px;margin-bottom:18px}.kpi{border:1px solid #e5ded1;border-radius:8px;padding:13px;background:#fbfaf6;min-height:92px}.kpi strong{display:block;font-size:27px;line-height:1.1}.kpi span{display:block;color:#6d675e;font-size:12px;margin-top:8px}.split{display:grid;grid-template-columns:1.15fr .85fr;gap:18px}.split h3{margin:0 0 10px;font-size:15px}.map-grid{display:grid;grid-template-columns:repeat(5,1fr);gap:8px}.city-tile{min-height:60px;border-radius:8px;padding:8px;border:1px solid #ded7ca;background:#f4f2ec;display:flex;flex-direction:column;justify-content:space-between}.city-tile.active{outline:3px solid #4c8d89}.city-tile .name{font-size:12px;color:#4e4a43}.city-tile .count{font-size:22px;font-weight:700}.city-tile[data-region='北部']{background:#e8f4f1}.city-tile[data-region='中部']{background:#f3efd9}.city-tile[data-region='南部']{background:#f7e6d7}.city-tile[data-region='東部']{background:#e7eef7}.city-tile[data-region='離島']{background:#eee8f5}.bars{display:flex;flex-direction:column;gap:8px}.bar-row{display:grid;grid-template-columns:94px 1fr 48px;gap:8px;align-items:center;font-size:13px}.bar-track{height:12px;background:#ede7dc;border-radius:999px;overflow:hidden}.bar-fill{height:100%;background:#28786d;border-radius:999px}.bar-fill.alt{background:#c46a3b}.matrix{display:grid;gap:8px}.matrix-row{display:grid;grid-template-columns:80px 1fr 60px;gap:8px;align-items:center}.matrix-track{height:18px;background:#ede7dc;border-radius:999px;overflow:hidden}.matrix-fill{height:100%;background:#5874a6}.empty-chart{border:1px dashed #d2b46e;background:#fff6df;border-radius:8px;padding:16px;color:#66501b}.table-wrap{overflow:auto;border:1px solid #e5ded1;border-radius:8px}table{width:100%;border-collapse:collapse;font-size:13px;background:#fff}th,td{padding:10px;border-bottom:1px solid #ece6dc;text-align:left;vertical-align:top}th{position:sticky;top:0;background:#f8f5ed;color:#4f4a41;z-index:1}tr:last-child td{border-bottom:0}.pill{display:inline-flex;align-items:center;border-radius:999px;padding:3px 8px;background:#eef2e6;color:#3a5f36;margin:2px;font-size:12px}.pill.market{background:#f6e8df;color:#7b3f23}.pill.gap{background:#fff0c9;color:#795400}.details table{min-width:900px}@media(max-width:980px){.topbar{position:static;display:block}.controls{grid-template-columns:1fr 1fr}.kpi-grid{grid-template-columns:repeat(2,1fr)}.split{grid-template-columns:1fr}.map-grid{grid-template-columns:repeat(3,1fr)}main{padding:16px}.section-title{display:block}}""",
        encoding="utf-8",
    )

    (ROOT / "app.js").write_text(
        """const regions=['全台','北部','中部','南部','東部','離島'];let stores=[],summary={},state={region:'全台',city:'all',system:'all',gmb:'all',q:''};const pct=v=>`${Math.round((v||0)*1000)/10}%`;const byId=id=>document.getElementById(id);Promise.all([fetch('data/stores.json').then(r=>r.json()),fetch('data/summary.json').then(r=>r.json())]).then(([storePayload,summaryPayload])=>{stores=storePayload.stores;summary=summaryPayload;init();render();});function init(){byId('generatedAt').textContent=`更新 ${summary.generatedAt}`;byId('regionFilters').innerHTML=regions.map(r=>`<button data-region="${r}">${r}</button>`).join('');byId('regionFilters').addEventListener('click',e=>{if(e.target.dataset.region){state.region=e.target.dataset.region;state.city='all';render();}});byId('cityFilter').addEventListener('change',e=>{state.city=e.target.value;render();});byId('systemFilter').addEventListener('change',e=>{state.system=e.target.value;render();});byId('gmbFilter').addEventListener('change',e=>{state.gmb=e.target.value;render();});byId('searchInput').addEventListener('input',e=>{state.q=e.target.value.trim().toLowerCase();render();});}function filtered(){return stores.filter(s=>{if(state.region!=='全台'&&s.regionGroup!==state.region)return false;if(state.city!=='all'&&s.city!==state.city)return false;if(state.system!=='all'&&!s.orderingSystems.some(o=>o.system===state.system))return false;if(state.gmb==='confirmed'&&s.gmbStatus!=='confirmed')return false;if(state.gmb==='gap'&&s.gmbOrderingStatus==='confirmed')return false;if(state.q&&!`${s.storeName} ${s.address} ${s.city} ${s.district}`.toLowerCase().includes(state.q))return false;return true;});}function render(){document.querySelectorAll('#regionFilters button').forEach(b=>b.classList.toggle('active',b.dataset.region===state.region));const availableCities=[...new Set(stores.filter(s=>state.region==='全台'||s.regionGroup===state.region).map(s=>s.city).filter(Boolean))].sort();byId('cityFilter').innerHTML='<option value="all">全部城市</option>'+availableCities.map(c=>`<option ${state.city===c?'selected':''}>${c}</option>`).join('');const systems=[...new Set(stores.flatMap(s=>s.orderingSystems.map(o=>o.system)))].sort();byId('systemFilter').innerHTML='<option value="all">全部系統</option>'+systems.map(s=>`<option ${state.system===s?'selected':''}>${s}</option>`).join('');const rows=filtered();renderKpis(rows);renderMap(rows);renderBars(rows);renderComparison(rows);renderTable(rows);}function countUniqueSystem(rows,gmbOnly=false){const m=new Map();rows.forEach(s=>{new Set(s.orderingSystems.filter(o=>!gmbOnly||o.sourceType==='gmb').map(o=>o.system)).forEach(sys=>m.set(sys,(m.get(sys)||0)+1));});return [...m.entries()].sort((a,b)=>b[1]-a[1]||a[0].localeCompare(b[0]));}function renderKpis(rows){const n=rows.length||0;const gmb=rows.filter(s=>s.sourceCoverage.gmbFound).length;const google=rows.filter(s=>s.sourceCoverage.googleFound).length;const third=rows.filter(s=>s.sourceCoverage.thirdPartyFound).length;const any=rows.filter(s=>s.hasAnyOrderingSystem).length;const gmbOrder=rows.filter(s=>s.hasGmbOrderingSystem).length;const gmbGap=rows.filter(s=>s.gmbOrderingStatus!=='confirmed').length;byId('storeKpis').innerHTML=kpis([['官方門市',n,'目前篩選範圍'],['GMB/Maps 找到',gmb,`${n?pct(gmb/n):'0%'}`],['Google 找到',google,`${n?pct(google/n):'0%'}`],['第三方來源',third,`${n?pct(third/n):'0%'}`],['查證缺口',gmbGap,'Google Order 供應商需人工複核']]);byId('allSourceKpis').innerHTML=kpis([['有任一系統',any,`${n?pct(any/n):'0%'}`],['未知門市',n-any,'未見官方/平台連結'],['主要系統數',countUniqueSystem(rows).length,'全來源'],['Nidin',countUniqueSystem(rows).find(x=>x[0]==='Nidin')?.[1]||0,'官方訂餐'],['Uber Eats',countUniqueSystem(rows).find(x=>x[0]==='Uber Eats')?.[1]||0,'外送平台']]);byId('gmbKpis').innerHTML=kpis([['GMB 找到',gmb,`${n?pct(gmb/n):'0%'}`],['Google Order 有供應商',gmbOrder,`${n?pct(gmbOrder/n):'0%'}`],['Google Order 供應商覆蓋率',n?pct(gmbOrder/n):'0%','分母為官方門市'],['Google Order 供應商缺口',gmbGap,'非未導入'],['需人工複查',gmbGap,'動態按鈕']]);byId('gmbChart').textContent=gmbOrder?'Google Order 供應商已找到資料。':'本次靜態稽核未直接讀到 Google Order 供應商；請以「覆蓋缺口」解讀，不代表門市沒有點餐系統。';}function kpis(items){return items.map(([label,value,note])=>`<div class="kpi"><strong>${value}</strong><span>${label}</span><span>${note}</span></div>`).join('');}function renderMap(rows){const counts=new Map();rows.forEach(s=>counts.set(s.city,(counts.get(s.city)||0)+1));const cityList=Object.keys(summary.cityCounts);byId('taiwanMap').innerHTML=cityList.map(city=>`<div class="city-tile ${state.city===city?'active':''}" data-region="${regionOf(city)}" onclick="state.city='${city}';render()"><span class="name">${city}</span><span class="count">${counts.get(city)||0}</span></div>`).join('');}function regionOf(city){return stores.find(s=>s.city===city)?.regionGroup||'離島';}function renderBars(rows){const cityCounts=[...rows.reduce((m,s)=>m.set(s.city,(m.get(s.city)||0)+1),new Map()).entries()].sort((a,b)=>b[1]-a[1]).slice(0,12);byId('cityBars').innerHTML=bars(cityCounts,'');const systems=countUniqueSystem(rows);byId('systemBars').innerHTML=bars(systems,'alt');const n=rows.length||1;const regionRows=regions.filter(r=>r!=='全台').map(r=>{const rr=rows.filter(s=>s.regionGroup===r);const any=rr.filter(s=>s.hasAnyOrderingSystem).length;return [r,rr.length?any/rr.length:0,`${any}/${rr.length}`];});byId('regionMatrix').innerHTML=regionRows.map(([r,rate,label])=>`<div class="matrix-row"><span>${r}</span><div class="matrix-track"><div class="matrix-fill" style="width:${rate*100}%"></div></div><b>${label}</b></div>`).join('');}function bars(entries,cls){const max=Math.max(1,...entries.map(e=>e[1]));return entries.length?entries.map(([name,value])=>`<div class="bar-row"><span>${name}</span><div class="bar-track"><div class="bar-fill ${cls}" style="width:${value/max*100}%"></div></div><b>${value}</b></div>`).join(''):'<p>沒有資料</p>';}function renderComparison(rows){const all=countUniqueSystem(rows);const gmb=countUniqueSystem(rows,true);const gmbMap=new Map(gmb);const n=rows.length||1;byId('comparisonRows').innerHTML=all.map(([system,count])=>{const g=gmbMap.get(system)||0;return `<tr><td>${system}</td><td>${count}</td><td>${pct(count/n)}</td><td>${g}</td><td>${pct(g/n)}</td><td>${count-g}</td></tr>`}).join('')||'<tr><td colspan="6">沒有系統資料</td></tr>';}function renderTable(rows){byId('detailCount').textContent=`${rows.length} 家門市`;byId('storeRows').innerHTML=rows.map(s=>{const all=[...new Set(s.orderingSystems.map(o=>o.system))];const gmb=[...new Set(s.orderingSystems.filter(o=>o.sourceType==='gmb').map(o=>o.system))];const links=s.orderingSystems.slice(0,3).map(o=>`<a href="${o.evidenceUrl}" target="_blank">${o.system}</a>`).join('、');return `<tr><td><b>${s.storeName}</b><br><small>${s.phone||''}</small></td><td>${s.regionGroup}<br>${s.city} ${s.district}</td><td>${s.address}</td><td>${all.map(x=>`<span class="pill">${x}</span>`).join('')||'<span class="pill gap">未見連結</span>'}</td><td><span class="pill gap">${s.gmbOrderingStatus}</span></td><td><a href="${s.gmbUrl}" target="_blank">GMB/Maps</a>${links?'、'+links:''}</td></tr>`}).join('');}""",
        encoding="utf-8",
    )


def main() -> None:
    stores = parse_official_stores()
    stores.sort(key=lambda store: (REGIONS.index(store["regionGroup"]) if store["regionGroup"] in REGIONS else 99, store["city"], store["district"], store["storeName"]))
    summary = make_summary(stores)
    write_data(stores, summary)
    write_dashboard_files()
    print(
        json.dumps(
            {
                "stores": len(stores),
                "regionCounts": summary["regionCounts"],
                "allSourceSystemCounts": summary["allSourceSystemCounts"],
                "gmbSystemCounts": summary["gmbSystemCounts"],
                "unknownOrderingSystemCount": summary["unknownOrderingSystemCount"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
