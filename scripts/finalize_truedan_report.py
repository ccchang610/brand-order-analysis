from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE_DATA = ROOT / "data" / "truedan"
REPORT = ROOT / "truedan"
DATA = REPORT / "data"


def rate(count: int, total: int) -> float:
    return round(count / total, 4) if total else 0


def read_stores() -> list[dict]:
    raw = json.loads((SOURCE_DATA / "stores.json").read_text(encoding="utf-8"))
    if isinstance(raw, dict):
        return raw.get("stores", [])
    return raw


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


def rebuild_summary(stores: list[dict]) -> dict:
    summary = json.loads((SOURCE_DATA / "summary.json").read_text(encoding="utf-8"))
    total = len(stores)
    all_counts = count_systems(stores)
    gmb_counts = count_systems(stores, source_type="gmb")
    gmb_found = sum(
        1
        for store in stores
        if store.get("sourceCoverage", {}).get("gmbFound") or store.get("gmbStatus") == "confirmed"
    )
    google_found = sum(1 for store in stores if store.get("sourceCoverage", {}).get("googleFound"))
    third_party = sum(1 for store in stores if store.get("sourceCoverage", {}).get("thirdPartyFound"))
    any_ordering = sum(1 for store in stores if store.get("hasAnyOrderingSystem"))
    google_order_entry = sum(
        1
        for store in stores
        if store.get("hasGmbOrderingSystem")
        or store.get("gmbOrderingStatus") in {"confirmed", "button_confirmed_provider_pending"}
    )
    gmb_ordering = sum(
        1
        for store in stores
        if any(claim.get("sourceType") == "gmb" and claim.get("system") for claim in store.get("orderingSystems", []))
    )
    gmb_gap = sum(
        1
        for store in stores
        if not store.get("hasGmbOrderingSystem")
        and store.get("gmbOrderingStatus") != "button_confirmed_provider_pending"
    )

    summary.update(
        {
            "brand": "珍煮丹 TRUEDAN",
            "brandSlug": "truedan",
            "market": "Taiwan",
            "sitePath": "./truedan/",
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
            "gmbOrderingSystemCount": gmb_ordering,
            "gmbOrderingSystemAdoptionRate": rate(gmb_ordering, total),
            "gmbCoverageGapCount": gmb_gap,
            "unknownOrderingSystemCount": total - any_ordering,
            "allSourceSystemCounts": all_counts,
            "allSourcePickupSystemCounts": count_systems(stores, mode="pickup"),
            "allSourceDeliverySystemCounts": count_systems(stores, mode="delivery"),
            "gmbSystemCounts": gmb_counts,
            "gmbPickupSystemCounts": count_systems(stores, source_type="gmb", mode="pickup"),
            "gmbDeliverySystemCounts": count_systems(stores, source_type="gmb", mode="delivery"),
            "gmbOrderOptionCounts": count_google_order_options(stores),
            "gmbOrderPickupOptionCounts": count_google_order_options(stores, mode="pickup"),
            "gmbOrderDeliveryOptionCounts": count_google_order_options(stores, mode="delivery"),
            "allSourceSystemAdoptionRates": {system: rate(count, total) for system, count in all_counts.items()},
            "gmbSystemAdoptionRates": {system: rate(count, total) for system, count in gmb_counts.items()},
            "gmbStatusCounts": dict(Counter(store.get("gmbStatus") for store in stores)),
            "gmbOrderingStatusCounts": dict(Counter(store.get("gmbOrderingStatus") for store in stores)),
            "sourceCoverageCounts": {
                "officialListed": total,
                "gmbFound": gmb_found,
                "googleFound": google_found,
                "thirdPartyFound": third_party,
            },
        }
    )
    summary["gmbOrderOptionAdoptionRates"] = {
        system: rate(count, total) for system, count in summary["gmbOrderOptionCounts"].items()
    }
    systems = sorted(set(all_counts) | set(gmb_counts))
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
    if isinstance(summary.get("source"), list):
        summary["source"] = {"officialStorePages": summary["source"]}
    summary.setdefault("source", {}).update(
        {
            "officialWebsite": "https://www.truedan.com.tw/",
            "officialStoreList": "https://www.truedan.com.tw/store.php",
            "notes": (
                "Official per-city pages are the store population source. Google Order provider evidence "
                "is counted only from opened Google Order panels, with pickup and delivery separated when readable."
            ),
        }
    )
    summary["notes"] = [
        note for note in summary.get("notes", []) if isinstance(note, str)
    ] + [
        "Fixed dashboard output mirrors the shared brand-order-analysis layout used by chage, with Taiwan map, region/city filters, all-source counts, Google Order pickup/delivery provider views, and store-level evidence."
    ]
    return summary


def write_csv(stores: list[dict]) -> None:
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
            row = {field: store.get(field, "") for field in fields}
            row["gmbPickupProviders"] = "; ".join(store.get("gmbPickupProviders") or [])
            row["gmbDeliveryProviders"] = "; ".join(store.get("gmbDeliveryProviders") or [])
            row["allSourceSystems"] = "; ".join(
                sorted({claim.get("system", "") for claim in store.get("orderingSystems", []) if claim.get("system")})
            )
            row["gmbSystems"] = "; ".join(
                sorted(
                    {
                        claim.get("system", "")
                        for claim in store.get("orderingSystems", [])
                        if claim.get("sourceType") == "gmb" and claim.get("system")
                    }
                )
            )
            writer.writerow(row)


def report_html() -> str:
    return """<!doctype html>
<html lang="zh-Hant">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>珍煮丹 TRUEDAN 點餐系統分析</title>
  <link rel="stylesheet" href="../assets/styles.css?v=35" />
</head>
<body>
  <header class="topbar">
    <div>
      <p class="eyebrow">Brand Order Analysis</p>
      <h1>珍煮丹 TRUEDAN 點餐系統分析</h1>
      <p class="subhead">台灣官方門市、Google/Maps/GMB 覆蓋、Google Order provider evidence，以及 pickup / delivery 模式分布。<span class="version">truedan gmb mode audit</span></p>
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
      <label>Google Order <select id="gmbFilter"><option value="all">全部</option><option value="confirmed">Google Order 有證據</option><option value="gap">Google Order 缺口</option><option value="no_gmb_found">GMB/Maps 未找到</option></select></label>
      <label class="search">搜尋門市<input id="searchInput" type="search" placeholder="門市、地址、城市" /></label>
    </section>

    <section class="insight-strip" id="insightStrip"></section>

    <section class="panel">
      <div class="section-title">
        <div><p class="eyebrow">1. Store Footprint</p><h2>官方門市與地理分布</h2></div>
        <p>以珍煮丹官網台灣門市頁為母體，呈現 22 縣市分布、區域篩選與 Google/Maps 覆蓋狀態。</p>
      </div>
      <div class="kpi-grid" id="storeKpis"></div>
      <div class="split map-layout">
        <div>
          <h3>台灣門市地圖</h3>
          <p class="map-source">包含台灣 22 縣市，沒有門市的縣市顯示 0。</p>
          <div class="taiwan-map" id="taiwanMap"></div>
        </div>
        <div><h3>城市排行</h3><div class="bars" id="cityBars"></div></div>
      </div>
    </section>

    <section class="panel">
      <div class="section-title">
        <div><p class="eyebrow">2. All Sources</p><h2>全來源點餐系統</h2></div>
        <p>整合官方門市、Google、GMB 與第三方來源。外帶與外送分開計算，避免把 provider-only 結果混成不明模式。</p>
      </div>
      <div class="kpi-grid" id="allSourceKpis"></div>
      <div class="split">
        <div><h3>自取系統</h3><div class="bars" id="pickupBars"></div></div>
        <div><h3>外送系統</h3><div class="bars" id="deliveryBars"></div></div>
      </div>
      <div class="split compact">
        <div><h3>區域導入率</h3><div class="matrix" id="regionMatrix"></div></div>
        <div><h3>讀法</h3><p class="note">全來源包含 Google Order provider rows 與其他公開來源；Google Order 嚴格統計只計入點開 Google Order 面板後可見的 provider row。</p></div>
      </div>
    </section>

    <section class="panel warning">
      <div class="section-title">
        <div><p class="eyebrow">3. Google Order</p><h2>Google Order provider / link 分布</h2></div>
        <p>只把 Google Business Profile 藍色點餐流程中可見的 provider row 算為 GMB provider evidence；面板內連結另以 provider/link 視角呈現。</p>
      </div>
      <div class="kpi-grid" id="gmbKpis"></div>
      <div class="split">
        <div><h3>Google Order 自取選項</h3><div class="bars" id="gmbPickupBars"></div></div>
        <div><h3>Google Order 外送選項</h3><div class="bars" id="gmbDeliveryBars"></div></div>
      </div>
    </section>

    <section class="panel">
      <div class="section-title"><div><p class="eyebrow">4. Comparison</p><h2>全來源 vs Google Order provider</h2></div></div>
      <div class="table-wrap"><table><thead><tr><th>系統</th><th>全來源門市</th><th>全來源占比</th><th>Google Order provider 門市</th><th>Google Order provider 占比</th><th>缺口</th></tr></thead><tbody id="comparisonRows"></tbody></table></div>
    </section>

    <section class="panel">
      <div class="section-title"><div><p class="eyebrow">5. Store Details</p><h2>逐店明細</h2></div><p id="detailCount"></p></div>
      <div class="table-wrap details"><table><thead><tr><th>門市</th><th>區域</th><th>地址</th><th>全來源點餐</th><th>Google Order 證據</th><th>連結 / 審核</th></tr></thead><tbody id="storeRows"></tbody></table></div>
    </section>
  </main>

  <script src="data-inline.js?v=1"></script>
  <script src="../assets/taiwan-map.js?v=35"></script>
  <script src="../assets/app.js?v=35"></script>
</body>
</html>
"""


def main() -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    stores = read_stores()
    summary = rebuild_summary(stores)
    payload = {
        "generatedAt": summary.get("generatedAt"),
        "brand": summary.get("brand"),
        "source": summary.get("source"),
        "stores": stores,
    }
    (DATA / "stores.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (DATA / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (REPORT / "data-inline.js").write_text(
        "window.DAMING_DATA = "
        + json.dumps({"storesPayload": payload, "summary": summary}, ensure_ascii=False)
        + ";\n",
        encoding="utf-8",
    )
    (REPORT / "index.html").write_text(report_html(), encoding="utf-8")
    write_csv(stores)
    print(
        json.dumps(
            {
                "report": str(REPORT),
                "officialStoreCount": summary["officialStoreCount"],
                "gmbFoundCount": summary["gmbFoundCount"],
                "gmbOrderingSystemCount": summary["gmbOrderingSystemCount"],
                "gmbCoverageGapCount": summary["gmbCoverageGapCount"],
                "gmbPickupSystemCounts": summary["gmbPickupSystemCounts"],
                "gmbDeliverySystemCounts": summary["gmbDeliverySystemCounts"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
