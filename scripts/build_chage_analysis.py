from __future__ import annotations

import csv
import html
import json
import re
import time
from collections import Counter
from datetime import date
from pathlib import Path
from urllib.parse import quote, urljoin

import requests
from bs4 import BeautifulSoup


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "chage"
DATA = OUT / "data"
DATA.mkdir(parents=True, exist_ok=True)

BRAND = "茶聚 CHAGE"
MARKET = "Taiwan"
OFFICIAL_URL = "https://www.chage.com.tw/index.php?lang=tw"
STORE_INDEX = "https://www.chage.com.tw/edcontent.php?lang=tw&tb=3"
QUICKCLICK_URL = "https://order.quickclick.cc/tw/portals/CHAGE"
CHECKED_AT = date.today().isoformat()

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
    "Referer": OFFICIAL_URL,
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

KNOWN_MARKETPLACE_EVIDENCE = {
    "台北長安店": [
        ("Uber Eats", "https://www.ubereats.com/tw/store/%E8%8C%B6%E8%81%9A-%E5%8F%B0%E5%8C%97%E9%95%B7%E5%AE%89%E5%BA%97/kJ0LsvXZTFae7tiryrjcTQ"),
    ],
    "中壢環中店": [
        ("Uber Eats", "https://www.ubereats.com/tw/store/%E8%8C%B6%E8%81%9A-%E4%B8%AD%E5%A3%A2%E7%92%B0%E4%B8%AD%E5%BA%97/M7pvHQE9UhiCUkjxLoKRhw"),
    ],
    "台北莊敬店": [
        ("Uber Eats", "https://www.ubereats.com/tw/store/%E8%8C%B6%E8%81%9A-%E5%8F%B0%E5%8C%97%E8%8E%8A%E6%95%AC%E5%BA%97/c1pVR_fWSv6WP5kdcQpk5A"),
    ],
    "南港玉成店": [
        ("Uber Eats", "https://www.ubereats.com/tw-en/store/%E8%8C%B6%E8%81%9A-%E5%8D%97%E6%B8%AF%E7%8E%89%E6%88%90%E5%BA%97/a0ctazHKWrOFGREQRvrY1Q"),
    ],
    "永和竹林店": [
        ("Uber Eats", "https://www.ubereats.com/tw/store/%E8%8C%B6%E8%81%9A-%E6%B0%B8%E5%92%8C%E7%AB%B9%E6%9E%97%E5%BA%97/snGuo_RkSU6NICCA1GjsuA"),
    ],
    "南港店": [
        ("Uber Eats", "https://www.ubereats.com/tw/store/%E8%8C%B6%E8%81%9A-%E5%8D%97%E6%B8%AF%E5%BA%97/uX4IsL11RA6tpXXfW-V_bw"),
    ],
    "中壢福州店": [
        ("Uber Eats", "https://www.ubereats.com/tw-en/store/%E8%8C%B6%E8%81%9A-%E4%B8%AD%E5%A3%A2%E7%A6%8F%E5%B7%9E%E5%BA%97/Vvfiy3nXWOSxlrHls2B_pA"),
    ],
    "桃園中正店": [
        ("foodpanda", "https://www.foodpanda.com.tw/restaurant/fujc/fujc"),
    ],
    "中山伊通店": [
        ("foodpanda", "https://www.foodpanda.com.tw/restaurant/yl6l/cha-ju-zhong-shan-yi-tong-dian"),
    ],
    "鶯歌建國店": [
        ("foodpanda", "https://www.foodpanda.com.tw/chain/cu8ec/cha-ju"),
    ],
}


def fetch(url: str, timeout: int = 45) -> str:
    response = requests.get(url, headers=HEADERS, timeout=timeout)
    response.raise_for_status()
    response.encoding = response.apparent_encoding or response.encoding
    return response.text


def clean(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").replace("\xa0", " ")).strip()


def canonical_city(value: str) -> str:
    return value.replace("臺", "台")


def city_from_address(address: str, fallback: str = "") -> str:
    normalized = canonical_city(clean(address))
    for city in TAIWAN_CITIES:
        if city in normalized:
            return city
    fallback = canonical_city(fallback)
    if fallback.endswith("門市"):
        fallback = fallback[:-2]
    if fallback in {"台北", "新北", "桃園", "台中", "台南", "高雄", "基隆", "新竹", "嘉義"}:
        return f"{fallback}市"
    if fallback in {"苗栗", "彰化", "南投", "雲林", "屏東", "宜蘭", "花蓮", "台東", "澎湖", "金門", "連江"}:
        return f"{fallback}縣"
    return ""


def district_from_address(address: str, city: str) -> str:
    normalized = canonical_city(clean(address))
    tail = normalized.split(city, 1)[1] if city and city in normalized else normalized
    match = re.search(r"([^0-9\s,，]{1,8}?(?:區|鄉|鎮|市))", tail)
    return match.group(1) if match else ""


def parse_summary_text(text: str) -> tuple[str, str, str]:
    text = clean(text)
    address = ""
    phone = ""
    hours = ""
    address_match = re.search(r"門市地址\s*[:：]\s*(.*?)(?:門市電話|營業時間|$)", text)
    phone_match = re.search(r"門市電話\s*[:：]\s*(.*?)(?:營業時間|$)", text)
    hours_match = re.search(r"營業時間\s*[:：]\s*(.*)$", text)
    if address_match:
        address = clean(address_match.group(1))
    if phone_match:
        phone = clean(phone_match.group(1))
    if hours_match:
        hours = clean(hours_match.group(1))
    return address, phone, hours


def category_links() -> list[tuple[str, str]]:
    soup = BeautifulSoup(fetch(STORE_INDEX), "html.parser")
    links: list[tuple[str, str]] = []
    for anchor in soup.select(".page_menu_block a[href*='cid=']"):
        title = clean(anchor.get("title") or anchor.get_text(" ", strip=True))
        url = urljoin(STORE_INDEX, anchor.get("href") or "")
        if title and url and (title, url) not in links:
            links.append((title, url))
    return links


def list_store_cards(category_title: str, category_url: str) -> list[dict]:
    cards: list[dict] = []
    seen_urls: set[str] = set()
    page = 1
    while page <= 20:
        url = category_url if page == 1 else f"{category_url}&currentpage={page}"
        soup = BeautifulSoup(fetch(url), "html.parser")
        page_cards = []
        for item in soup.select(".layoutlist_3 .row.item"):
            anchor = item.select_one(".list_subject > a[href*='edcontent_d.php']")
            if not anchor:
                continue
            detail_url = urljoin(STORE_INDEX, anchor.get("href") or "")
            if detail_url in seen_urls:
                continue
            seen_urls.add(detail_url)
            name = clean(anchor.get("title") or anchor.find(text=True) or anchor.get_text(" ", strip=True))
            summary = clean(item.select_one(".summary").get_text(" ", strip=True) if item.select_one(".summary") else "")
            address, phone, hours = parse_summary_text(summary)
            page_cards.append(
                {
                    "categoryTitle": category_title,
                    "name": name,
                    "detailUrl": detail_url,
                    "address": address,
                    "phone": phone,
                    "hours": hours,
                }
            )
        cards.extend(page_cards)
        next_link = soup.select_one(f"a[href*='currentpage={page + 1}']")
        if not next_link or not page_cards:
            break
        page += 1
        time.sleep(0.08)
    return cards


def classify_link(url: str, label: str) -> dict | None:
    haystack = f"{url} {label}".lower()
    if "order.quickclick.cc" in haystack:
        return {
            "system": "QuickClick",
            "sourceType": "official",
            "orderMode": ["pickup", "delivery"],
            "evidenceUrl": url,
            "label": label or "線上點餐",
            "confidence": "confirmed",
        }
    if "ubereats" in haystack:
        return {
            "system": "Uber Eats",
            "sourceType": "marketplace",
            "orderMode": ["delivery"],
            "evidenceUrl": url,
            "label": label or "Uber Eats",
            "confidence": "confirmed",
        }
    if "foodpanda" in haystack:
        return {
            "system": "foodpanda",
            "sourceType": "marketplace",
            "orderMode": ["delivery"],
            "evidenceUrl": url,
            "label": label or "foodpanda",
            "confidence": "confirmed",
        }
    return None


def parse_detail(card: dict) -> dict:
    soup = BeautifulSoup(fetch(card["detailUrl"]), "html.parser")
    title = clean(soup.select_one("h1.pageTitle").get_text(" ", strip=True) if soup.select_one("h1.pageTitle") else card["name"])
    links = []
    line_links = []
    order_claims = []

    for anchor in soup.find_all("a"):
        href = anchor.get("href") or ""
        label = clean(anchor.get("title") or anchor.get_text(" ", strip=True))
        if not href or href.startswith("tel:"):
            continue
        full_url = urljoin(card["detailUrl"], href)
        links.append({"label": label, "url": full_url})
        if "lin.ee" in full_url.lower() or "page.line.me" in full_url.lower() or "line" in label.lower():
            line_links.append({"label": label or "LINE", "url": full_url})
        claim = classify_link(full_url, label)
        if claim:
            order_claims.append(claim)

    for system, url in KNOWN_MARKETPLACE_EVIDENCE.get(title, []):
        order_claims.append(
            {
                "system": system,
                "sourceType": "marketplace",
                "orderMode": ["delivery"],
                "evidenceUrl": url,
                "label": system,
                "confidence": "partial",
                "evidenceNote": "Google indexed marketplace result matched by store name; not a full marketplace crawl.",
            }
        )

    iframe = soup.select_one("iframe[src*='google.com/maps']")
    map_url = iframe.get("src") if iframe else ""

    deduped_claims = []
    seen_claims: set[tuple[str, str, str]] = set()
    for claim in order_claims:
        key = (claim["system"], claim["sourceType"], claim["evidenceUrl"])
        if key in seen_claims:
            continue
        seen_claims.add(key)
        deduped_claims.append(claim)

    address = card["address"]
    city = city_from_address(address, card["categoryTitle"])
    district = district_from_address(address, city)
    gmb_found = bool(map_url)
    third_party_found = any(claim["sourceType"] == "marketplace" for claim in deduped_claims)

    gmb_status = "confirmed" if gmb_found else "needs_manual_review"
    gmb_ordering_status = "needs_manual_review" if gmb_found else "not_found"
    manual_review = (
        "官方頁含 Google Maps 嵌入，但尚未逐店打開 Google 藍色點餐面板讀取供應商。"
        if gmb_found
        else "官方頁未提供可解析的 Google Maps 嵌入。"
    )

    if line_links:
        manual_review += " LINE 連結為加入會員/官方帳號，未當作點餐系統計入。"

    return {
        "brand": BRAND,
        "storeName": title,
        "country": "Taiwan",
        "market": MARKET,
        "regionGroup": REGION_BY_CITY.get(city, "未分類"),
        "city": city,
        "county": city,
        "district": district,
        "address": address,
        "latitude": None,
        "longitude": None,
        "phone": card["phone"],
        "hours": card["hours"],
        "officialSourceUrl": STORE_INDEX,
        "officialStoreUrl": card["detailUrl"],
        "officialMapUrl": map_url,
        "googleSearchUrl": f"https://www.google.com/search?q={quote('茶聚 ' + title + ' ' + address)}",
        "gmbUrl": map_url,
        "gmbStatus": gmb_status,
        "gmbOrderingStatus": gmb_ordering_status,
        "sourceCoverage": {
            "officialListed": True,
            "gmbFound": gmb_found,
            "googleFound": gmb_found,
            "thirdPartyFound": third_party_found,
        },
        "orderingSystems": deduped_claims,
        "hasAnyOrderingSystem": bool(deduped_claims),
        "hasGmbOrderingSystem": False,
        "manualReviewReason": manual_review,
        "evidenceNotes": [
            "官方門市詳情頁提供 QuickClick 線上點餐入口。",
            "Google Order 供應商需另以人工節奏打開 Google 點餐面板確認；本次未把官網/平台連結回填成 Google Order provider。",
        ],
        "lineLinks": line_links,
        "checkedAt": CHECKED_AT,
        "gmbSignals": {
            "buttonDetected": False,
            "providersParsed": False,
            "attemptCount": 0,
            "maxAttempts": 0,
            "attemptHistory": [],
            "panelUrl": "",
            "checkedAt": CHECKED_AT,
            "checkMethod": "official_site_and_public_search_first_pass",
            "notes": "Google Order panel audit not performed in this first-pass local report.",
        },
    }


def count_systems(stores: list[dict], source_type: str | None = None, mode: str | None = None) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for store in stores:
        systems = set()
        for claim in store["orderingSystems"]:
            if source_type and claim["sourceType"] != source_type:
                continue
            if mode and mode not in claim["orderMode"]:
                continue
            systems.add(claim["system"])
        counter.update(systems)
    return dict(counter.most_common())


def build_summary(stores: list[dict]) -> dict:
    total = len(stores)
    gmb_found = sum(1 for store in stores if store["sourceCoverage"]["gmbFound"])
    google_found = sum(1 for store in stores if store["sourceCoverage"]["googleFound"])
    third_party = sum(1 for store in stores if store["sourceCoverage"]["thirdPartyFound"])
    any_ordering = sum(1 for store in stores if store["hasAnyOrderingSystem"])
    gmb_ordering = sum(1 for store in stores if store["hasGmbOrderingSystem"])
    city_counter = Counter(store["city"] for store in stores if store["city"])
    region_counter = Counter(store["regionGroup"] for store in stores if store["regionGroup"])
    city_counts = {city: city_counter.get(city, 0) for city in TAIWAN_CITIES}
    region_counts = {region: region_counter.get(region, 0) for region in REGIONS}
    all_counts = count_systems(stores)
    gmb_counts = count_systems(stores, source_type="gmb")

    return {
        "brand": BRAND,
        "market": MARKET,
        "generatedAt": CHECKED_AT,
        "officialStoreCount": total,
        "gmbFoundCount": gmb_found,
        "gmbMissingCount": total - gmb_found,
        "googleFoundCount": google_found,
        "thirdPartyFoundCount": third_party,
        "verificationGapCount": sum(1 for store in stores if store["gmbOrderingStatus"] in {"needs_manual_review", "unavailable_or_blocked", "duplicate_or_ambiguous", "not_found"}),
        "anyOrderingSystemCount": any_ordering,
        "anyOrderingSystemAdoptionRate": round(any_ordering / total, 4) if total else 0,
        "gmbOrderingSystemCount": gmb_ordering,
        "gmbOrderingSystemAdoptionRate": round(gmb_ordering / total, 4) if total else 0,
        "gmbCoverageGapCount": total - gmb_ordering,
        "unknownOrderingSystemCount": total - any_ordering,
        "cityCounts": city_counts,
        "regionCounts": region_counts,
        "allSourceSystemCounts": all_counts,
        "allSourcePickupSystemCounts": count_systems(stores, mode="pickup"),
        "allSourceDeliverySystemCounts": count_systems(stores, mode="delivery"),
        "gmbSystemCounts": gmb_counts,
        "gmbPickupSystemCounts": count_systems(stores, source_type="gmb", mode="pickup"),
        "gmbDeliverySystemCounts": count_systems(stores, source_type="gmb", mode="delivery"),
        "allSourceSystemAdoptionRates": {system: round(count / total, 4) for system, count in all_counts.items()} if total else {},
        "gmbSystemAdoptionRates": {system: round(count / total, 4) for system, count in gmb_counts.items()} if total else {},
        "systemComparison": [
            {
                "system": system,
                "allSourceStoreCount": count,
                "allSourceAdoptionRate": round(count / total, 4) if total else 0,
                "gmbStoreCount": gmb_counts.get(system, 0),
                "gmbAdoptionRate": round(gmb_counts.get(system, 0) / total, 4) if total else 0,
                "countGap": count - gmb_counts.get(system, 0),
                "percentagePointGap": round((count - gmb_counts.get(system, 0)) / total, 4) if total else 0,
            }
            for system, count in all_counts.items()
        ],
        "gmbStatusCounts": dict(Counter(store["gmbStatus"] for store in stores)),
        "gmbOrderingStatusCounts": dict(Counter(store["gmbOrderingStatus"] for store in stores)),
        "sourceCoverageCounts": {
            "officialListed": total,
            "gmbFound": gmb_found,
            "googleFound": google_found,
            "thirdPartyFound": third_party,
        },
        "source": {
            "officialWebsite": OFFICIAL_URL,
            "officialStoreList": STORE_INDEX,
            "officialOrdering": QUICKCLICK_URL,
            "lineAccount": "https://lin.ee/xRo0az8u",
            "foodpandaChainExample": "https://www.foodpanda.com.tw/chain/cu8ec/cha-ju",
            "notes": (
                "Official store pages are the store population source. QuickClick is counted from official store detail pages. "
                "Uber Eats and foodpanda counts are conservative, store-name matched public-search examples, not exhaustive platform crawls. "
                "Google Order provider counts are zero because Google Order panels were not opened and parsed in this first-pass report."
            ),
        },
        "notes": [
            "本版為本地初版總攬：官方門市與官方 QuickClick 點餐覆蓋已逐店解析。",
            "GMB 只記錄官方頁 Google Maps 嵌入覆蓋；Google Order 供應商需後續逐店人工節奏複核。",
            "LINE 連結目前在官網呈現為加入會員/官方帳號，未計入點餐系統。",
            "Uber Eats / foodpanda 以公開搜尋可驗證的分店頁做保守抽樣，不代表完整平台覆蓋率。",
        ],
    }


def write_outputs(stores: list[dict], summary: dict) -> None:
    for index, store in enumerate(stores, start=1):
        store["storeId"] = f"chage-{index:03d}"

    stores_payload = {"stores": stores}
    (DATA / "stores.json").write_text(json.dumps(stores_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (DATA / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    fieldnames = [
        "storeId",
        "storeName",
        "regionGroup",
        "city",
        "district",
        "address",
        "phone",
        "hours",
        "officialStoreUrl",
        "gmbStatus",
        "gmbOrderingStatus",
        "hasAnyOrderingSystem",
        "hasGmbOrderingSystem",
        "allSourceSystems",
        "gmbSystems",
        "manualReviewReason",
    ]
    with (DATA / "stores.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for store in stores:
            writer.writerow(
                {
                    **{key: store.get(key, "") for key in fieldnames},
                    "allSourceSystems": "; ".join(sorted({claim["system"] for claim in store["orderingSystems"]})),
                    "gmbSystems": "; ".join(sorted({claim["system"] for claim in store["orderingSystems"] if claim["sourceType"] == "gmb"})),
                }
            )

    inline = "window.DAMING_DATA = " + json.dumps({"storesPayload": stores_payload, "summary": summary}, ensure_ascii=False) + ";\n"
    (OUT / "data-inline.js").write_text(inline, encoding="utf-8")

    index_html = f"""<!doctype html>
<html lang="zh-Hant">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{html.escape(BRAND)} 點餐系統總攬</title>
  <link rel="stylesheet" href="../assets/styles.css?v=31" />
</head>
<body>
  <header class="topbar">
    <div>
      <p class="eyebrow">Brand Order Analysis</p>
      <h1>{html.escape(BRAND)} 點餐系統總攬</h1>
      <p class="subhead">官方門市、Google/GMB 覆蓋、官方 QuickClick、外送平台公開證據與 LINE 連結檢查。<span class="version">v1 chage-local-first-pass</span></p>
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
      <label>Google Order 狀態<select id="gmbFilter"><option value="all">全部</option><option value="confirmed">Google Order 有點餐</option><option value="gap">Google Order 缺口</option><option value="no_gmb_found">GMB 未找到</option></select></label>
      <label class="search">搜尋門市<input id="searchInput" type="search" placeholder="門市、地址、城市" /></label>
    </section>

    <section class="insight-strip" id="insightStrip"></section>

    <section class="panel">
      <div class="section-title">
        <div><p class="eyebrow">1. Store Footprint</p><h2>品牌門市總攬</h2></div>
        <p>官方門市頁作為分母；GMB/Maps 以官方單店頁的 Google Maps 嵌入作為找到門市的第一層證據。</p>
      </div>
      <div class="kpi-grid" id="storeKpis"></div>
      <div class="split map-layout">
        <div>
          <h3>台灣門市地圖</h3>
          <p class="map-source">地圖支援全台 22 縣市，無門市縣市顯示 0。</p>
          <div class="taiwan-map" id="taiwanMap"></div>
        </div>
        <div><h3>城市排行</h3><div class="bars" id="cityBars"></div></div>
      </div>
    </section>

    <section class="panel">
      <div class="section-title">
        <div><p class="eyebrow">2. All Sources</p><h2>品牌整體點餐系統</h2></div>
        <p>官方 QuickClick 逐店計入；Uber Eats / foodpanda 目前為公開搜尋可驗證的保守樣本，不代表平台完整覆蓋率。</p>
      </div>
      <div class="kpi-grid" id="allSourceKpis"></div>
      <div class="split">
        <div><h3>全來源自取系統</h3><div class="bars" id="pickupBars"></div></div>
        <div><h3>全來源外送系統</h3><div class="bars" id="deliveryBars"></div></div>
      </div>
      <div class="split compact">
        <div><h3>大區導入率</h3><div class="matrix" id="regionMatrix"></div></div>
        <div><h3>解讀</h3><p class="note">QuickClick 是官網單店頁「線上點餐」入口；LINE 目前為加入會員/官方帳號，不作為點餐系統計入。</p></div>
      </div>
    </section>

    <section class="panel warning">
      <div class="section-title">
        <div><p class="eyebrow">3. Google Order</p><h2>Google Order 點餐系統總攬</h2></div>
        <p>本版尚未逐店打開 Google 藍色點餐面板，因此不回填任何 Google Order provider；這些列為 Google Order 複核缺口。</p>
      </div>
      <div class="kpi-grid" id="gmbKpis"></div>
      <div class="split">
        <div><h3>Google Order 自取系統</h3><div class="bars" id="gmbPickupBars"></div></div>
        <div><h3>Google Order 外送系統</h3><div class="bars" id="gmbDeliveryBars"></div></div>
      </div>
    </section>

    <section class="panel">
      <div class="section-title"><div><p class="eyebrow">4. Comparison</p><h2>全來源 vs Google Order</h2></div></div>
      <div class="table-wrap"><table><thead><tr><th>系統</th><th>全來源門市</th><th>全來源導入率</th><th>Google Order 門市</th><th>Google Order 導入率</th><th>差距</th></tr></thead><tbody id="comparisonRows"></tbody></table></div>
    </section>

    <section class="panel">
      <div class="section-title"><div><p class="eyebrow">5. Store Details</p><h2>門市明細</h2></div><p id="detailCount"></p></div>
      <div class="table-wrap details"><table><thead><tr><th>門市</th><th>地區</th><th>地址</th><th>全來源系統</th><th>GMB</th><th>證據</th></tr></thead><tbody id="storeRows"></tbody></table></div>
    </section>
  </main>

  <script src="data-inline.js?v=1"></script>
  <script src="../assets/taiwan-map.js?v=18"></script>
  <script src="../assets/app.js?v=31"></script>
</body>
</html>
"""
    (OUT / "index.html").write_text(index_html, encoding="utf-8")


def main() -> None:
    stores: list[dict] = []
    seen_keys: set[tuple[str, str]] = set()
    for title, url in category_links():
        for card in list_store_cards(title, url):
            store = parse_detail(card)
            key = (store["storeName"], store["address"])
            if key in seen_keys:
                continue
            seen_keys.add(key)
            stores.append(store)
            time.sleep(0.05)

    stores.sort(key=lambda item: (REGIONS.index(item["regionGroup"]) if item["regionGroup"] in REGIONS else 99, item["city"], item["storeName"]))
    summary = build_summary(stores)
    write_outputs(stores, summary)
    print(f"wrote {len(stores)} stores to {OUT}")


if __name__ == "__main__":
    main()
