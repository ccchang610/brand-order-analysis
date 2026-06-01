from __future__ import annotations

import csv
import json
from collections import Counter
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "chage"
DATA = REPORT / "data"
STORES_PATH = DATA / "stores.json"
SUMMARY_PATH = DATA / "summary.json"

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
REGIONS = ["北部", "中部", "南部", "東部", "離島"]


def rate(count: int, total: int) -> float:
    return round(count / total, 4) if total else 0


def has_gmb_provider(store: dict) -> bool:
    return any(
        claim.get("sourceType") == "gmb" and claim.get("confidence") in {"confirmed", "partial"}
        for claim in store.get("orderingSystems", [])
    )


def has_google_order_entry(store: dict) -> bool:
    return bool(store.get("hasGmbOrderingSystem")) or store.get("gmbOrderingStatus") in {
        "confirmed",
        "button_confirmed_provider_pending",
    }


def count_systems(stores: list[dict], source_type: str | None = None, mode: str | None = None) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for store in stores:
        systems = set()
        for claim in store.get("orderingSystems", []):
            if source_type and claim.get("sourceType") != source_type:
                continue
            if mode and mode not in claim.get("orderMode", []):
                continue
            if claim.get("confidence") in {"confirmed", "partial"}:
                systems.add(claim.get("system", ""))
        counts.update(system for system in systems if system)
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))


def rebuild_summary(stores: list[dict]) -> dict:
    total = len(stores)
    city_counts = Counter(store.get("city") or "未分類" for store in stores)
    region_counts = Counter(store.get("regionGroup") or "未分類" for store in stores)
    source_counts: Counter[str] = Counter()
    for store in stores:
        for key, enabled in store.get("sourceCoverage", {}).items():
            if enabled:
                source_counts[key] += 1

    all_counts = count_systems(stores)
    all_pickup = count_systems(stores, mode="pickup")
    all_delivery = count_systems(stores, mode="delivery")
    gmb_counts = count_systems(stores, source_type="gmb")
    gmb_pickup = count_systems(stores, source_type="gmb", mode="pickup")
    gmb_delivery = count_systems(stores, source_type="gmb", mode="delivery")
    provider_count = sum(1 for store in stores if has_gmb_provider(store))
    entry_count = sum(1 for store in stores if has_google_order_entry(store))
    gap_count = sum(1 for store in stores if not has_google_order_entry(store) and not has_gmb_provider(store))

    systems = sorted(set(all_counts) | set(gmb_counts))
    summary = {
        "brand": "茶聚 CHAGE",
        "market": "Taiwan",
        "generatedAt": date.today().isoformat(),
        "officialStoreCount": total,
        "gmbFoundCount": sum(1 for store in stores if store.get("sourceCoverage", {}).get("gmbFound")),
        "gmbMissingCount": sum(1 for store in stores if not store.get("sourceCoverage", {}).get("gmbFound")),
        "googleFoundCount": sum(1 for store in stores if store.get("sourceCoverage", {}).get("googleFound")),
        "thirdPartyFoundCount": sum(1 for store in stores if store.get("sourceCoverage", {}).get("thirdPartyFound")),
        "verificationGapCount": gap_count,
        "anyOrderingSystemCount": sum(1 for store in stores if store.get("hasAnyOrderingSystem")),
        "googleOrderEntryCount": entry_count,
        "googleOrderEntryRate": rate(entry_count, total),
        "gmbOrderingSystemCount": provider_count,
        "gmbOrderingSystemAdoptionRate": rate(provider_count, total),
        "gmbCoverageGapCount": gap_count,
        "unknownOrderingSystemCount": sum(1 for store in stores if not store.get("hasAnyOrderingSystem")),
        "cityCounts": {city: city_counts.get(city, 0) for city in TAIWAN_CITIES},
        "regionCounts": {region: region_counts.get(region, 0) for region in REGIONS},
        "allSourceSystemCounts": all_counts,
        "allSourcePickupSystemCounts": all_pickup,
        "allSourceDeliverySystemCounts": all_delivery,
        "gmbSystemCounts": gmb_counts,
        "gmbPickupSystemCounts": gmb_pickup,
        "gmbDeliverySystemCounts": gmb_delivery,
        "allSourceSystemAdoptionRates": {system: rate(count, total) for system, count in all_counts.items()},
        "gmbSystemAdoptionRates": {system: rate(count, total) for system, count in gmb_counts.items()},
        "systemComparison": [
            {
                "system": system,
                "allSourceStoreCount": all_counts.get(system, 0),
                "allSourceAdoptionRate": rate(all_counts.get(system, 0), total),
                "gmbStoreCount": gmb_counts.get(system, 0),
                "gmbAdoptionRate": rate(gmb_counts.get(system, 0), total),
                "countGap": all_counts.get(system, 0) - gmb_counts.get(system, 0),
                "percentagePointGap": round(
                    rate(all_counts.get(system, 0), total) - rate(gmb_counts.get(system, 0), total),
                    4,
                ),
            }
            for system in systems
        ],
        "gmbStatusCounts": dict(Counter(store.get("gmbStatus") for store in stores)),
        "gmbOrderingStatusCounts": dict(Counter(store.get("gmbOrderingStatus") for store in stores)),
        "sourceCoverageCounts": dict(source_counts),
        "source": {
            "officialWebsite": "https://www.chage.com.tw/index.php?lang=tw",
            "officialStoreList": "https://www.chage.com.tw/edcontent.php?lang=tw&tb=3",
            "officialOrdering": "https://order.quickclick.cc/tw/portals/CHAGE",
            "lineAccount": "https://lin.ee/xRo0az8u",
            "notes": "Official store pages provide the store population and all-source ordering links. Google Order provider evidence counts only provider rows visible inside the opened Google Order panel.",
        },
        "notes": [
            "官方門市數作為所有導入率分母。",
            "全來源點餐系統整合官網 QuickClick、平台頁與 Google Order provider evidence。",
            "Google Order provider 覆蓋率只計入 sourceType=gmb 的面板供應商；button_confirmed_provider_pending 只列入 googleOrderEntryCount。",
            "GMB / Google 阻擋、無藍色入口、未找到或歧義結果列為 coverage gap，不當作沒有導入點餐系統。",
        ],
    }
    summary["anyOrderingSystemAdoptionRate"] = rate(summary["anyOrderingSystemCount"], total)
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
        "googleOrderProviderEvidence",
        "allSourceSystems",
        "gmbSystems",
        "officialSourceUrl",
        "officialStoreUrl",
        "gmbUrl",
        "gmbOrderPanelUrl",
        "evidenceLinks",
        "manualReviewReason",
    ]
    with (DATA / "stores.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for store in stores:
            all_systems = sorted({claim["system"] for claim in store.get("orderingSystems", [])})
            gmb_systems = sorted(
                {claim["system"] for claim in store.get("orderingSystems", []) if claim.get("sourceType") == "gmb"}
            )
            evidence = sorted({claim["evidenceUrl"] for claim in store.get("orderingSystems", []) if claim.get("evidenceUrl")})
            writer.writerow(
                {
                    **{field: store.get(field, "") for field in fields},
                    "googleOrderProviderEvidence": has_gmb_provider(store),
                    "allSourceSystems": "、".join(all_systems),
                    "gmbSystems": "、".join(gmb_systems),
                    "evidenceLinks": " | ".join(evidence),
                }
            )


def update_index() -> None:
    index_path = REPORT / "index.html"
    if not index_path.exists():
        return
    html = index_path.read_text(encoding="utf-8")
    replacements = {
        "v1 chage-local-first-pass": "v2 chage-google-order-audit",
        "本版尚未逐店打開 Google 藍色點餐面板，因此不回填任何 GMB provider；這些列為 GMB 點餐複核缺口。": "本版已逐店開啟 Google Search / Maps 檢查藍色點餐入口；只有在 Google Order 面板中可見的供應商列才計入 GMB provider evidence。",
        "GMB 點餐系統總攬": "Google Order Provider 總攬",
        "官方 QuickClick 逐店計入；Uber Eats / foodpanda 目前為公開搜尋可驗證的保守樣本，不代表平台完整覆蓋率。": "官方 QuickClick 逐店計入；Uber Eats / foodpanda 以公開可驗證平台頁與 Google Order 面板證據補強，來源類型分開計算。",
    }
    for old, new in replacements.items():
        html = html.replace(old, new)
    index_path.write_text(html, encoding="utf-8")


def main() -> None:
    payload = json.loads(STORES_PATH.read_text(encoding="utf-8"))
    stores = payload["stores"]
    summary = rebuild_summary(stores)
    STORES_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    SUMMARY_PATH.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (REPORT / "data-inline.js").write_text(
        "window.DAMING_DATA = "
        + json.dumps({"storesPayload": payload, "summary": summary}, ensure_ascii=False)
        + ";\n",
        encoding="utf-8",
    )
    write_csv(stores)
    update_index()
    print(
        json.dumps(
            {
                "officialStoreCount": summary["officialStoreCount"],
                "googleOrderEntryCount": summary["googleOrderEntryCount"],
                "gmbOrderingSystemCount": summary["gmbOrderingSystemCount"],
                "gmbCoverageGapCount": summary["gmbCoverageGapCount"],
                "gmbSystemCounts": summary["gmbSystemCounts"],
                "gmbOrderingStatusCounts": summary["gmbOrderingStatusCounts"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
