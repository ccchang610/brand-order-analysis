import csv
import html
import json
import re
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "truedan"
REPORT_PATH = ROOT / "truedan_taiwan_ordering_overview.html"
SOURCE_URL = "https://www.truedan.com.tw/store.php"
CITY_PAGE = "https://www.truedan.com.tw/portal_d1_cnt.php?s_contury=1&s_city={city_id}"
CHECKED_AT = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

CITY_IDS = [
    ("金門", 59),
    ("基隆", 58),
    ("台北", 16),
    ("新北", 15),
    ("桃園", 14),
    ("新竹", 13),
    ("苗栗", 39),
    ("台中", 12),
    ("彰化", 11),
    ("南投", 43),
    ("雲林", 54),
    ("嘉義", 10),
    ("台南", 9),
    ("高雄", 5),
    ("屏東", 40),
    ("宜蘭", 42),
    ("花蓮", 6),
    ("澎湖", 45),
]

ALL_TAIWAN_CITIES = [
    "基隆市", "台北市", "新北市", "桃園市", "新竹市", "新竹縣", "苗栗縣",
    "台中市", "彰化縣", "南投縣", "雲林縣", "嘉義市", "嘉義縣", "台南市",
    "高雄市", "屏東縣", "宜蘭縣", "花蓮縣", "台東縣", "澎湖縣",
    "金門縣", "連江縣",
]

REGION_BY_CITY = {
    "基隆市": "北部", "台北市": "北部", "新北市": "北部", "桃園市": "北部",
    "新竹市": "北部", "新竹縣": "北部", "苗栗縣": "北部", "宜蘭縣": "北部",
    "台中市": "中部", "彰化縣": "中部", "南投縣": "中部", "雲林縣": "中部",
    "嘉義市": "南部", "嘉義縣": "南部", "台南市": "南部", "高雄市": "南部", "屏東縣": "南部",
    "花蓮縣": "東部", "台東縣": "東部",
    "澎湖縣": "離島", "金門縣": "離島", "連江縣": "離島",
}

MAP_POSITIONS = {
    "基隆市": (72, 18), "台北市": (62, 22), "新北市": (55, 28), "桃園市": (48, 35),
    "新竹市": (42, 44), "新竹縣": (48, 48), "苗栗縣": (43, 58), "台中市": (42, 72), "彰化縣": (36, 86),
    "南投縣": (52, 88), "雲林縣": (35, 103), "嘉義市": (36, 116), "嘉義縣": (42, 119), "台南市": (39, 135),
    "高雄市": (48, 153), "屏東縣": (57, 173), "宜蘭縣": (74, 43), "花蓮縣": (78, 92),
    "台東縣": (75, 145), "澎湖縣": (13, 121), "金門縣": (6, 86), "連江縣": (18, 18),
}


def fetch_text(url):
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
        },
    )
    with urllib.request.urlopen(req, timeout=25) as response:
        raw = response.read()
    return raw.decode("utf-8", errors="replace")


def clean_text(value):
    value = re.sub(r"<[^>]+>", "", value)
    value = html.unescape(value)
    value = value.replace("\u3000", " ")
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def parse_city_page(page_city, city_id, page):
    records = []
    blocks = re.findall(r'<article class="store col-4">(.*?)</article>', page, flags=re.S)
    for idx, block in enumerate(blocks, 1):
        name_match = re.search(r"<h3>(.*?)</h3>", block, flags=re.S)
        phone_match = re.search(r"sa-tel.*?<b>(.*?)</b>", block, flags=re.S)
        address_match = re.search(r"sa-add.*?<b>(.*?)</b>", block, flags=re.S)
        hours_match = re.search(r"sa-open.*?<span>(.*?)</span>", block, flags=re.S)
        map_match = re.search(r"data-src='([^']+)'", block)
        if not name_match:
            continue
        name = clean_text(name_match.group(1))
        phone = clean_text(phone_match.group(1)) if phone_match else ""
        address = clean_text(address_match.group(1)) if address_match else ""
        hours = clean_text(hours_match.group(1)) if hours_match else ""
        map_url = html.unescape(map_match.group(1)) if map_match else ""
        county = parse_county(address, page_city)
        store_id = f"truedan-tw-{city_id}-{idx:02d}"
        records.append({
            "brand": "珍煮丹",
            "storeId": store_id,
            "storeName": name,
            "country": "台灣",
            "market": "Taiwan",
            "regionGroup": REGION_BY_CITY.get(county, "\u672a\u5206\u985e"),
            "city": county,
            "county": county,
            "district": parse_district(address),
            "address": address,
            "latitude": None,
            "longitude": None,
            "phone": phone,
            "hours": hours,
            "officialSourceUrl": CITY_PAGE.format(city_id=city_id),
            "officialStoreUrl": CITY_PAGE.format(city_id=city_id),
            "officialMapUrl": map_url,
            "googleSearchUrl": google_search_url(f"珍煮丹 {name} {address}"),
            "gmbUrl": "",
            "gmbStatus": "needs_manual_review",
            "gmbOrderingStatus": "needs_manual_review",
            "gmbOrderLinks": [],
            "sourceCoverage": {
                "officialListed": True,
                "gmbFound": False,
                "googleFound": False,
                "thirdPartyFound": False,
            },
            "orderingSystems": [],
            "hasAnyOrderingSystem": False,
            "hasGmbOrderingSystem": False,
            "manualReviewReason": "已從官網取得門市；尚未逐店完成人工節奏 Google Business Profile / Google Order 與平台定位查核。",
            "evidenceNotes": [
                "官網頁面含 Google Maps address embed，可作為 GMB 查核 lead，但不能直接算作已找到命名 GBP。",
            ],
            "checkedAt": CHECKED_AT,
        })
    return records


def parse_district(address):
    match = re.search(r"(?:縣|市)([^縣市鄉鎮區]{1,8}(?:區|鄉|鎮|市))", address)
    return match.group(1) if match else ""


def parse_county(address, fallback_page_city):
    match = re.match(r"(.{2,3}?[\u7e23\u5e02])", address)
    if match:
        county = match.group(1)
        if county in REGION_BY_CITY:
            return county
    fallback = {
        "\u53f0\u5317": "\u53f0\u5317\u5e02", "\u65b0\u5317": "\u65b0\u5317\u5e02", "\u6843\u5712": "\u6843\u5712\u5e02", "\u53f0\u4e2d": "\u53f0\u4e2d\u5e02",
        "\u53f0\u5357": "\u53f0\u5357\u5e02", "\u9ad8\u96c4": "\u9ad8\u96c4\u5e02", "\u57fa\u9686": "\u57fa\u9686\u5e02", "\u65b0\u7af9": "\u65b0\u7af9\u5e02",
        "\u82d7\u6817": "\u82d7\u6817\u7e23", "\u5f70\u5316": "\u5f70\u5316\u7e23", "\u5357\u6295": "\u5357\u6295\u7e23", "\u96f2\u6797": "\u96f2\u6797\u7e23",
        "\u5609\u7fa9": "\u5609\u7fa9\u5e02", "\u5c4f\u6771": "\u5c4f\u6771\u7e23", "\u5b9c\u862d": "\u5b9c\u862d\u7e23", "\u82b1\u84ee": "\u82b1\u84ee\u7e23",
        "\u6f8e\u6e56": "\u6f8e\u6e56\u7e23", "\u91d1\u9580": "\u91d1\u9580\u7e23",
    }
    return fallback.get(fallback_page_city, fallback_page_city)


def google_search_url(query):
    return "https://www.google.com/search?q=" + urllib.parse.quote(query)


def pct(value, denom):
    return round(value / denom, 4) if denom else 0


def build_summary(stores, sources):
    official_count = len(stores)
    city_counts = {city: 0 for city in ALL_TAIWAN_CITIES}
    for store in stores:
        city_counts[store["city"]] = city_counts.get(store["city"], 0) + 1

    region_counts = {region: 0 for region in ["北部", "中部", "南部", "東部", "離島", "未分類"]}
    for city, count in city_counts.items():
        region_counts[REGION_BY_CITY.get(city, "未分類")] += count

    gmb_found = sum(1 for s in stores if s["sourceCoverage"]["gmbFound"])
    google_found = sum(1 for s in stores if s["sourceCoverage"]["googleFound"])
    third_party_found = sum(1 for s in stores if s["sourceCoverage"]["thirdPartyFound"])
    any_ordering = sum(1 for s in stores if s["hasAnyOrderingSystem"])
    gmb_ordering = sum(1 for s in stores if s["hasGmbOrderingSystem"])
    unknown_ordering = official_count - any_ordering
    statuses = Counter(s["gmbOrderingStatus"] for s in stores)

    return {
        "generatedAt": CHECKED_AT,
        "brand": "珍煮丹",
        "brandSlug": "truedan",
        "market": "Taiwan",
        "sitePath": "./",
        "officialStoreCount": official_count,
        "gmbFoundCount": gmb_found,
        "googleFoundCount": google_found,
        "thirdPartyFoundCount": third_party_found,
        "verificationGapCount": official_count,
        "anyOrderingSystemCount": any_ordering,
        "anyOrderingSystemAdoptionRate": pct(any_ordering, official_count),
        "gmbOrderingSystemCount": gmb_ordering,
        "gmbOrderingSystemAdoptionRate": pct(gmb_ordering, official_count),
        "gmbCoverageGapCount": official_count,
        "unknownOrderingSystemCount": unknown_ordering,
        "cityCounts": city_counts,
        "regionCounts": {k: v for k, v in region_counts.items() if v or k != "未分類"},
        "allSourceSystemCounts": {},
        "gmbSystemCounts": {},
        "gmbOrderOptionCounts": {},
        "gmbOrderPickupOptionCounts": {},
        "gmbOrderDeliveryOptionCounts": {},
        "allSourceSystemAdoptionRates": {},
        "gmbSystemAdoptionRates": {},
        "gmbOrderOptionAdoptionRates": {},
        "systemComparison": [
            comparison_row(system, official_count)
            for system in ["Nidin", "Uber Eats", "foodpanda", "LINE", "QuickClick", "Foodomo", "官方點餐"]
        ],
        "gmbStatusCounts": Counter(s["gmbStatus"] for s in stores),
        "gmbOrderingStatusCounts": statuses,
        "sourceCoverageCounts": {
            "officialListed": official_count,
            "gmbFound": gmb_found,
            "googleFound": google_found,
            "thirdPartyFound": third_party_found,
        },
        "source": sources,
        "notes": [
            "本版已用官網 per-city pages 建立官方台灣門市母體與縣市分布。",
            "官網未提供逐店平台點餐 URL；Google Order、Uber Eats、foodpanda、Nidin、LINE、QuickClick 需後續逐店定位查核。",
            "官網 HTML 註解保留 store.truedan.com.tw 連結；2026-06-22 抓取該網域回 502，因此標示為需人工複查，不列入 confirmed adoption。",
        ],
    }


def comparison_row(system, denominator):
    return {
        "system": system,
        "allSourceStoreCount": 0,
        "allSourceAdoptionRate": 0,
        "gmbStoreCount": 0,
        "gmbAdoptionRate": 0,
        "countGap": 0,
        "percentagePointGap": 0,
    }


def write_outputs(stores, summary):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    (DATA_DIR / "stores.json").write_text(json.dumps(stores, ensure_ascii=False, indent=2), encoding="utf-8")
    (DATA_DIR / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    with (DATA_DIR / "stores.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=[
            "storeId", "storeName", "regionGroup", "city", "district", "address",
            "phone", "hours", "officialSourceUrl", "officialMapUrl",
            "gmbStatus", "gmbOrderingStatus", "manualReviewReason",
        ])
        writer.writeheader()
        for store in stores:
            writer.writerow({key: store.get(key, "") for key in writer.fieldnames})
    REPORT_PATH.write_text(build_html(stores, summary), encoding="utf-8")


def esc(value):
    return html.escape(str(value or ""))


def build_map(summary):
    max_count = max(summary["cityCounts"].values()) or 1
    items = []
    for city in ALL_TAIWAN_CITIES:
        x, y = MAP_POSITIONS.get(city, (0, 0))
        count = summary["cityCounts"].get(city, 0)
        radius = 5 + (count / max_count) * 13 if count else 4
        region = REGION_BY_CITY.get(city, "未分類")
        items.append(f"""
          <g class="map-node" data-region="{esc(region)}" data-city="{esc(city)}">
            <circle cx="{x}" cy="{y}" r="{radius:.1f}" class="bubble {'zero' if count == 0 else ''}"></circle>
            <text x="{x}" y="{y - radius - 3:.1f}" class="map-label">{esc(city.replace('縣市',''))}</text>
            <text x="{x}" y="{y + 4}" class="map-count">{count}</text>
          </g>""")
    return "\n".join(items)


def build_city_rows(summary):
    rows = []
    for city, count in sorted(summary["cityCounts"].items(), key=lambda kv: (-kv[1], kv[0])):
        region = REGION_BY_CITY.get(city, "未分類")
        rate = "待查"
        rows.append(f"""
          <tr data-region="{esc(region)}" data-city="{esc(city)}">
            <td>{esc(city)}</td><td>{esc(region)}</td><td>{count}</td><td>{rate}</td>
            <td>官網門市頁已列；平台與 GMB 尚待逐店查核</td>
          </tr>""")
    return "\n".join(rows)


def build_store_rows(stores):
    rows = []
    for store in stores:
        rows.append(f"""
          <tr data-region="{esc(store['regionGroup'])}" data-city="{esc(store['city'])}" data-q="{esc((store['storeName'] + ' ' + store['address']).lower())}">
            <td><strong>{esc(store['storeName'])}</strong><span>{esc(store['phone'])}</span></td>
            <td>{esc(store['regionGroup'])}</td>
            <td>{esc(store['city'])}</td>
            <td>{esc(store['district'])}</td>
            <td>{esc(store['address'])}</td>
            <td><span class="badge neutral">待查</span></td>
            <td><a href="{esc(store['officialSourceUrl'])}" target="_blank" rel="noreferrer">官網</a> · <a href="{esc(store['googleSearchUrl'])}" target="_blank" rel="noreferrer">Google 搜尋</a></td>
            <td>{esc(store['manualReviewReason'])}</td>
          </tr>""")
    return "\n".join(rows)


def build_region_cards(summary):
    return "\n".join(
        f"""<button type="button" class="filter" data-filter-kind="region" data-filter-value="{esc(region)}">{esc(region)} <b>{count}</b></button>"""
        for region, count in summary["regionCounts"].items()
    )


def build_city_bars(summary):
    max_count = max(summary["cityCounts"].values()) or 1
    rows = []
    for city, count in sorted(summary["cityCounts"].items(), key=lambda kv: (-kv[1], kv[0])):
        width = round((count / max_count) * 100, 1) if count else 2
        rows.append(f"""
          <div class="bar-row" data-region="{esc(REGION_BY_CITY.get(city, '未分類'))}" data-city="{esc(city)}">
            <span>{esc(city)}</span>
            <div><i style="width:{width}%"></i></div>
            <b>{count}</b>
          </div>""")
    return "\n".join(rows)


def build_html(stores, summary):
    official = summary["officialStoreCount"]
    north = summary["regionCounts"].get("北部", 0)
    central = summary["regionCounts"].get("中部", 0)
    south = summary["regionCounts"].get("南部", 0)
    east = summary["regionCounts"].get("東部", 0)
    islands = summary["regionCounts"].get("離島", 0)
    return f"""<!doctype html>
<html lang="zh-Hant">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>珍煮丹台灣點餐系統與門市分布總覽</title>
  <style>
    :root {{
      --bg: #f3f7f4;
      --surface: #ffffff;
      --ink: #17201b;
      --muted: #65716a;
      --line: #dce6df;
      --green: #2f7a5d;
      --green2: #dff0e8;
      --brown: #735039;
      --warn: #b57926;
      --pink: #ff2b85;
      --blue: #0098ff;
      --linegreen: #06c755;
      --uber: #06c167;
      --shadow: 0 12px 28px rgba(28, 56, 40, .08);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "Noto Sans TC", "Microsoft JhengHei", Arial, sans-serif;
      background: var(--bg);
      color: var(--ink);
      line-height: 1.5;
    }}
    a {{ color: var(--green); text-underline-offset: 3px; }}
    header {{
      padding: 28px 22px 18px;
      border-bottom: 1px solid var(--line);
      background: #fbfdfb;
    }}
    .wrap {{ width: min(1240px, calc(100vw - 32px)); margin: 0 auto; }}
    h1 {{ margin: 0; font-size: clamp(28px, 4vw, 44px); letter-spacing: 0; line-height: 1.12; }}
    h2 {{ margin: 0 0 14px; font-size: 20px; letter-spacing: 0; }}
    h3 {{ margin: 0 0 8px; font-size: 15px; letter-spacing: 0; }}
    .sub {{ max-width: 920px; margin: 10px 0 0; color: var(--muted); }}
    .meta {{ display: flex; gap: 8px; flex-wrap: wrap; margin-top: 16px; }}
    .chip {{
      border: 1px solid var(--line);
      border-radius: 999px;
      background: #fff;
      padding: 6px 10px;
      color: var(--muted);
      font-size: 13px;
      font-weight: 700;
    }}
    main {{ padding: 22px 0 56px; }}
    .grid {{ display: grid; grid-template-columns: repeat(12, 1fr); gap: 14px; }}
    .card {{
      background: var(--surface);
      border: 1px solid var(--line);
      border-radius: 8px;
      box-shadow: var(--shadow);
    }}
    .kpi {{ grid-column: span 3; padding: 16px; min-height: 120px; }}
    .kpi strong {{ display: block; font-size: 34px; line-height: 1; color: var(--green); }}
    .kpi span {{ display: block; margin-top: 8px; color: var(--muted); font-size: 13px; }}
    .wide {{ grid-column: span 12; padding: 18px; }}
    .half {{ grid-column: span 6; padding: 18px; }}
    .third {{ grid-column: span 4; padding: 18px; }}
    .toolbar {{
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
      align-items: center;
      margin-bottom: 14px;
    }}
    button, input {{
      min-height: 36px;
      border: 1px solid var(--line);
      border-radius: 7px;
      background: #fff;
      color: var(--ink);
      font: inherit;
    }}
    button {{ padding: 7px 10px; font-weight: 800; cursor: pointer; }}
    button.active {{ background: var(--green); color: white; border-color: var(--green); }}
    button b {{ margin-left: 4px; color: inherit; }}
    input {{ padding: 7px 10px; min-width: 260px; }}
    .map-layout {{ display: grid; grid-template-columns: minmax(320px, 1fr) 360px; gap: 18px; align-items: start; }}
    .tw-map {{
      width: 100%;
      max-height: 680px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: linear-gradient(180deg, #f9fcfa, #eef7f2);
    }}
    .island-note {{ fill: #8b968f; font-size: 4px; }}
    .bubble {{
      fill: var(--green2);
      stroke: var(--green);
      stroke-width: .9;
      transition: opacity .15s, fill .15s, stroke .15s;
    }}
    .bubble.zero {{ fill: #f3f5f3; stroke: #cbd5ce; }}
    .map-label {{ font-size: 4px; text-anchor: middle; fill: #3c4942; font-weight: 800; }}
    .map-count {{ font-size: 5px; text-anchor: middle; fill: #173326; font-weight: 900; }}
    .filtered .map-node {{ opacity: .22; }}
    .filtered .map-node.active {{ opacity: 1; }}
    .filtered .map-node.active .bubble {{ fill: #bfe6d2; stroke-width: 1.6; }}
    .bar-row {{ display: grid; grid-template-columns: 76px 1fr 36px; gap: 9px; align-items: center; margin: 8px 0; }}
    .bar-row span, .bar-row b {{ font-size: 13px; }}
    .bar-row div {{ height: 10px; border-radius: 999px; background: #edf2ef; overflow: hidden; }}
    .bar-row i {{ display: block; height: 100%; border-radius: 999px; background: var(--green); }}
    table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
    th, td {{ padding: 10px 9px; border-bottom: 1px solid var(--line); text-align: left; vertical-align: top; }}
    th {{ color: var(--muted); font-size: 12px; background: #f8fbf9; }}
    tr[hidden] {{ display: none; }}
    td span {{ display: block; color: var(--muted); font-size: 12px; margin-top: 2px; }}
    .badge {{
      display: inline-flex;
      border-radius: 999px;
      padding: 4px 8px;
      font-size: 12px;
      font-weight: 900;
      white-space: nowrap;
    }}
    .neutral {{ background: #eef2ef; color: #415148; }}
    .nidin {{ background: var(--blue); color: #fff; }}
    .uber {{ background: #000; color: #fff; }}
    .panda {{ background: var(--pink); color: #fff; }}
    .line {{ background: var(--linegreen); color: #fff; }}
    .quick {{ background: #fcb900; color: #111; }}
    .callout {{ border-left: 4px solid var(--warn); background: #fff8e9; padding: 12px 14px; border-radius: 7px; color: #5d4521; }}
    .systems {{ display: flex; gap: 8px; flex-wrap: wrap; }}
    .source-list {{ margin: 0; padding-left: 18px; color: var(--muted); }}
    @media (max-width: 960px) {{
      .kpi, .half, .third {{ grid-column: span 12; }}
      .map-layout {{ grid-template-columns: 1fr; }}
      input {{ min-width: 100%; }}
      .wide {{ padding: 14px; }}
      th:nth-child(4), td:nth-child(4), th:nth-child(8), td:nth-child(8) {{ display: none; }}
    }}
  </style>
</head>
<body>
  <header>
    <div class="wrap">
      <h1>珍煮丹台灣點餐系統與門市分布總覽</h1>
      <p class="sub">本版依照 brand-order-analysis workflow 重跑：從珍煮丹官網逐縣市頁建立台灣官方門市母體，補上台灣地圖、區域/縣市分布、city ranking、store-level table、JSON/CSV 資料集。平台點餐覆蓋仍標示為待逐店查核，不把未打開 Google Order panel 的結果當作 provider evidence。</p>
      <div class="meta">
        <span class="chip">Generated: {esc(CHECKED_AT)}</span>
        <span class="chip">Official source: truedan.com.tw per-city pages</span>
        <span class="chip">Active official stores: {official}</span>
      </div>
    </div>
  </header>

  <main class="wrap">
    <section class="grid">
      <article class="card kpi"><strong data-kpi="stores">{official}</strong><span>官網台灣門市數，來自逐縣市頁解析</span></article>
      <article class="card kpi"><strong data-kpi="north">{north}</strong><span>北部門市</span></article>
      <article class="card kpi"><strong data-kpi="central">{central}</strong><span>中部門市</span></article>
      <article class="card kpi"><strong data-kpi="south">{south}</strong><span>南部門市</span></article>
    </section>

    <section class="grid" style="margin-top:14px">
      <article class="card wide">
        <h2>台灣地圖與區域篩選</h2>
        <div class="toolbar">
          <button type="button" class="filter active" data-filter-kind="all" data-filter-value="all">全台 <b>{official}</b></button>
          {build_region_cards(summary)}
        </div>
        <div class="map-layout">
          <svg class="tw-map" viewBox="0 0 100 200" role="img" aria-label="珍煮丹台灣門市分布泡泡地圖">
            <path d="M59 16 C70 20 82 37 80 55 C78 78 88 95 82 117 C76 139 67 163 60 181 C54 194 44 190 43 176 C42 160 37 150 33 136 C28 117 31 96 36 80 C40 66 38 51 45 38 C49 29 51 20 59 16 Z" fill="#eef7f2" stroke="#c8d8cf" stroke-width="1.2"></path>
            <text x="4" y="77" class="island-note">金門</text>
            <text x="10" y="111" class="island-note">澎湖</text>
            <text x="12" y="10" class="island-note">連江</text>
            {build_map(summary)}
          </svg>
          <div>
            <h3>縣市排名</h3>
            <div id="cityBars">{build_city_bars(summary)}</div>
          </div>
        </div>
      </article>
    </section>

    <section class="grid" style="margin-top:14px">
      <article class="card third"><h2>區域分布</h2><p>北部 {north}、中部 {central}、南部 {south}、東部 {east}、離島 {islands}。所有數字均由官網縣市頁門市卡片加總。</p></article>
      <article class="card third"><h2>平台覆蓋狀態</h2><p>官網無逐店平台連結。Google Order、Uber Eats、foodpanda、Nidin、LINE、QuickClick 目前全部列為待逐店定位查核；不把搜尋不到視為不存在。</p></article>
      <article class="card third"><h2>官方點餐線索</h2><p>官網 HTML 註解保留 <code>store.truedan.com.tw</code>，但目前抓取回 502。此線索列為「需人工複查」，不列入 confirmed adoption。</p></article>
    </section>

    <section class="grid" style="margin-top:14px">
      <article class="card half">
        <h2>平台待查清單</h2>
        <div class="systems">
          <span class="badge neutral">GMB / Google Order 待查 {official}</span>
          <span class="badge uber">Uber Eats 待查</span>
          <span class="badge panda">foodpanda 待查</span>
          <span class="badge nidin">Nidin 待查</span>
          <span class="badge line">LINE 待查</span>
          <span class="badge quick">QuickClick 待查</span>
        </div>
        <p class="callout">依 skill 規則，只有打開正確 Google Business Profile 的藍色點餐流程並讀到 provider row，才能算作 GMB provider evidence。本版尚未進行這層逐店瀏覽器查核。</p>
      </article>
      <article class="card half">
        <h2>資料輸出</h2>
        <ul class="source-list">
          <li><a href="data/truedan/stores.json">data/truedan/stores.json</a>：{official} 筆門市資料</li>
          <li><a href="data/truedan/summary.json">data/truedan/summary.json</a>：縣市/區域統計與 coverage gap</li>
          <li><a href="data/truedan/stores.csv">data/truedan/stores.csv</a>：門市表格匯出</li>
        </ul>
      </article>
    </section>

    <section class="grid" style="margin-top:14px">
      <article class="card wide">
        <h2>縣市分布表</h2>
        <table>
          <thead><tr><th>縣市</th><th>區域</th><th>門市數</th><th>點餐覆蓋率</th><th>說明</th></tr></thead>
          <tbody id="cityRows">{build_city_rows(summary)}</tbody>
        </table>
      </article>
    </section>

    <section class="grid" style="margin-top:14px">
      <article class="card wide">
        <h2>門市明細</h2>
        <div class="toolbar">
          <input id="search" type="search" placeholder="搜尋門市、地址、電話">
          <span class="chip" id="visibleCount">顯示 {official} / {official}</span>
        </div>
        <table>
          <thead><tr><th>門市</th><th>區域</th><th>縣市</th><th>行政區</th><th>地址</th><th>點餐系統</th><th>證據</th><th>待查原因</th></tr></thead>
          <tbody id="storeRows">{build_store_rows(stores)}</tbody>
        </table>
      </article>
    </section>

    <section class="grid" style="margin-top:14px">
      <article class="card wide">
        <h2>來源與限制</h2>
        <ul class="source-list">
          <li><a href="https://www.truedan.com.tw/store.php" target="_blank" rel="noreferrer">珍煮丹門市據點</a>：取得台灣縣市 ID 與門市頁入口。</li>
          <li><a href="https://www.truedan.com.tw/joinmember.php" target="_blank" rel="noreferrer">珍煮丹加入會員</a>：確認優惠券不適用於門市外送、線上點餐平台。</li>
          <li><a href="https://www.truedan.com.tw/product.php" target="_blank" rel="noreferrer">珍煮丹飲品菜單</a>：確認官網為菜單展示，不是逐店下單頁。</li>
          <li>每店 Google Search 連結已在 stores.json 產生，可作為下一輪 GMB / Google Order / 平台逐店查核入口。</li>
        </ul>
      </article>
    </section>
  </main>

  <script>
    const state = {{ kind: "all", value: "all", q: "" }};
    const filters = [...document.querySelectorAll(".filter")];
    const storeRows = [...document.querySelectorAll("#storeRows tr")];
    const cityRows = [...document.querySelectorAll("#cityRows tr")];
    const barRows = [...document.querySelectorAll(".bar-row")];
    const map = document.querySelector(".tw-map");
    const nodes = [...document.querySelectorAll(".map-node")];
    const search = document.querySelector("#search");
    const visibleCount = document.querySelector("#visibleCount");
    const total = storeRows.length;
    const kpiStores = document.querySelector('[data-kpi="stores"]');
    const kpiNorth = document.querySelector('[data-kpi="north"]');
    const kpiCentral = document.querySelector('[data-kpi="central"]');
    const kpiSouth = document.querySelector('[data-kpi="south"]');

    function matches(row) {{
      const geo = state.kind === "all" || row.dataset[state.kind] === state.value;
      const text = !state.q || (row.dataset.q || row.textContent.toLowerCase()).includes(state.q);
      return geo && text;
    }}

    function geoMatches(row) {{
      return state.kind === "all" || row.dataset[state.kind] === state.value;
    }}

    function render() {{
      let visible = 0;
      storeRows.forEach(row => {{
        const show = matches(row);
        row.hidden = !show;
        if (show) visible++;
      }});
      cityRows.forEach(row => row.hidden = !geoMatches(row));
      barRows.forEach(row => row.hidden = !geoMatches(row));
      nodes.forEach(node => {{
        const active = state.kind === "all" || node.dataset[state.kind] === state.value;
        node.classList.toggle("active", active);
      }});
      map.classList.toggle("filtered", state.kind !== "all");
      visibleCount.textContent = `顯示 ${{visible}} / ${{total}}`;
    }}

    filters.forEach(button => {{
      button.addEventListener("click", () => {{
        filters.forEach(item => item.classList.toggle("active", item === button));
        state.kind = button.dataset.filterKind;
        state.value = button.dataset.filterValue;
        render();
      }});
    }});
    search.addEventListener("input", () => {{
      state.q = search.value.trim().toLowerCase();
      render();
    }});
    render();
  </script>
</body>
</html>"""


def main():
    stores = []
    sources = []
    for page_city, city_id in CITY_IDS:
        url = CITY_PAGE.format(city_id=city_id)
        page = fetch_text(url)
        records = parse_city_page(page_city, city_id, page)
        stores.extend(records)
        sources.append({
            "city": page_city,
            "cityId": city_id,
            "url": url,
            "storeCount": len(records),
        })

    deduped = {}
    for store in stores:
        key = (store["storeName"], store["address"])
        deduped[key] = store
    stores = list(deduped.values())
    stores.sort(key=lambda item: (item["regionGroup"], item["city"], item["storeName"]))
    summary = build_summary(stores, sources)
    write_outputs(stores, summary)
    print(json.dumps({
        "stores": len(stores),
        "cityCounts": summary["cityCounts"],
        "regionCounts": summary["regionCounts"],
        "report": str(REPORT_PATH),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
