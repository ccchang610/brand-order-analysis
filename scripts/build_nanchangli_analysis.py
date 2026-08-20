from __future__ import annotations

import csv
import json
from collections import Counter
from datetime import date
from pathlib import Path
from urllib.parse import quote


ROOT = Path(__file__).resolve().parents[1]
REPORT_ROOT = ROOT / "nanchangli"
DATA_ROOT = REPORT_ROOT / "data"
CHECKED_AT = date.today().isoformat()

TAIWAN_CITIES = [
    "基隆市", "台北市", "新北市", "桃園市", "新竹市", "新竹縣", "苗栗縣",
    "台中市", "彰化縣", "南投縣", "雲林縣", "嘉義市", "嘉義縣", "台南市",
    "高雄市", "屏東縣", "宜蘭縣", "花蓮縣", "台東縣", "澎湖縣", "金門縣", "連江縣",
]
REGIONS = ["北部", "中部", "南部", "東部", "離島"]
SYSTEMS_IN_SCOPE = [
    "Nidin", "Uber Eats", "foodpanda", "LINE", "QuickClick",
    "食在麻吉 eathere", "PB Order", "Ocard", "MOS Order",
]


def google_search_url(name: str, address: str) -> str:
    return "https://www.google.com/search?q=" + quote(f"{name} {address} 線上點餐") + "&hl=zh-TW"


STORE_SEEDS = [
    ("001", "福生小吃", ["福生小食店"], "台南市中西區海安路一段100號", "06-2282998", "中西區", "https://www.twtainan.net/zh-tw/shop/consume/2199/"),
    ("002", "葉鳳浮水魚羹", [], "台南市中西區保安路81號", "06-2215111", "中西區", "https://ifoodie.tw/restaurant/56399ecf2756dd5d6810f995-%E8%91%89%E9%B3%B3%E6%B5%AE%E6%B0%B4%E9%AD%9A%E7%BE%B9"),
    ("003", "大勇街無名鹹粥", ["無名鹹粥"], "台南市中西區大勇街85號", "06-2267028", "中西區", "https://www.twtainan.net/file/29384/"),
    ("004", "下大道旗魚羹", ["下大道旗魚焿"], "台南市中西區西門路一段703巷40號", "06-2236933", "中西區", "https://foodintainan.com.tw/sia-da-dao/"),
    ("005", "你我他之家滷味", ["你我他之家鴨翅專賣店", "你我他之家"], "台南市中西區大德街69號", "06-2251396", "中西區", "https://data.tainan.gov.tw/Resource/dd7cc156-c597-453e-8ba1-3252709fa03d?handler=GoJson"),
    ("006", "下大道蘭米糕", ["下大道蘭米糕店"], "台南市中西區康樂街6號", "06-2210076", "中西區", "https://foodintainan.com.tw/lanmigao/"),
    ("007", "木村家紅茶", ["木村家職人茶屋 台南夏林店", "木村家職人茶屋"], "台南市中西區永華路一段210號", "", "中西區", "https://www.ubereats.com/tw/store/%E6%9C%A8%E6%9D%91%E5%AE%B6%E8%81%B7%E4%BA%BA%E8%8C%B6%E5%B1%8B-%E5%8F%B0%E5%8D%97%E5%A4%8F%E6%9E%97%E5%BA%97/9asdeRjJWHqkY-gjB0wkNQ"),
    ("008", "阿樂師油雞", ["阿樂師油雞內用店"], "台南市中西區大勇街53號", "", "中西區", "https://travel.yam.com/place/23866"),
    ("009", "牛家莊牛肉湯", ["台南市牛家莊牛肉湯"], "台南市中西區永華路一段108號", "06-2222406", "中西區", "https://nphssf64.tn.edu.tw/downloadfile.php?aid=9&code=ae123c305ce96629add2195f73d9453f&download=64"),
    ("010", "醇涎坊古早味鍋燒意麵", ["醇涎坊鍋燒意麵"], "台南市中西區保安路53號", "06-2215033", "中西區", "https://www.fonfood.com/store/137903"),
    ("011", "鼎富發豬油拌飯", [], "台南市中西區大德街38號", "06-2222327", "中西區", "https://menutaiwan.com/restaurants/8IlAaSRRm6"),
    ("012", "品佳菊花茶", [], "台南市中西區大勇街12號", "", "中西區", "https://foodintainan.com.tw/pin-jia/"),
    ("013", "冬瓜寶冬瓜茶", ["冬瓜寶冬瓜茶冷飲專賣店"], "台南市中西區海安路一段41號", "06-2221223", "中西區", "https://www.twtainan.net/zh-tw/shop/consume/1730/"),
    ("014", "廣東沙茶爐", [], "台南市南區金華路二段391號", "06-2646480", "南區", "https://www.fonfood.com/store/912941"),
    ("015", "鄉舟燒肉飯", [], "台南市中西區海安路一段43號", "", "中西區", "https://serv.gcis.nat.gov.tw/moeadsBF/cmpy/reportAction.do?fileName=376610000Asetup10707.pdf&method=report&reportClass=bmsItem&subPath=10707"),
    ("016", "老牌鹹酥雞", ["老牌鹽酥雞"], "台南市中西區大智街80之4號", "06-2219281", "中西區", "https://ifoodie.tw/restaurant/56e45b422756dd0f36c4bf39-%E8%80%81%E7%89%8C%E9%B9%BD%E9%85%A5%E9%9B%9E"),
    ("017", "順龍八寶冰", ["順龍八寶冰圓仔湯"], "台南市中西區保安路25號", "06-2113182", "中西區", "https://ifoodie.tw/en/post/5e766c51d6895d7a8466ff72"),
    ("018", "錦城石頭火鍋", [], "台南市中西區海安路一段22號", "06-2209200", "中西區", "https://w3fs.tainan.gov.tw/Download.ashx?n=6Ie65Y2X5biC55Kw5L%2Bd6aSQ5buz5ZCN5ZauLnBkZg%3D%3D&u=LzAwMS9VcGxvYWQvMTU5L3JlbGZpbGUvMC8xNTk5NS80NTFhYjQyYi0wZTdmLTQ4NjAtODA4Ny0zNzIzNDI2ZWE3ZTUucGRm"),
    ("019", "益田日本料理", ["東京益田", "益田日本居酒屋料理"], "台南市中西區海安路一段10號", "06-2267711", "中西區", "https://9pub.tw/club_d.php?id=245"),
    ("020", "阿文豬心", ["阿文豬心冬粉"], "台南市中西區大智街92號", "06-2220199", "中西區", "https://www.tainanlohas.cc/2022/03/Awen-Pork-Heart.html"),
    ("021", "嘉義火雞肉飯（本土火雞）", ["保安路嘉義火雞肉飯", "黃家嘉義火雞肉飯"], "台南市中西區保安路83號", "06-2262659", "中西區", "https://spot.line.me/detail/483791997841183965"),
    ("022", "阿川紅燒土魠魚焿", ["阿川紅燒土魠魚羹"], "台南市中西區海安路一段111號", "06-2274592", "中西區", "https://w3fs.tainan.gov.tw/Download.ashx?icon=..pdf&n=QW1hemluZyBUYWluYW4tMjAxMC5wZGY%3D&u=LzAwMS9VcGxvYWQvMTM1L3JlbGZpbGUvMTM2OTAvMTM5NTY2NC9iM2IzYzczMS1lMjJiLTQzN2ItODFjNy1jYzhhNTI1NmEwNTUucGRm"),
    ("023", "阿鳳浮水虱目魚羹", [], "台南市中西區保安路59號", "06-2256646", "中西區", "https://spot.line.me/detail/483791993495885010"),
    ("024", "千茶丘", [], "台南市中西區西門路一段703巷17號", "06-2236633", "中西區", "https://www.ubereats.com/tw/neighborhood/junxi-vil-tainan-tnn"),
    ("025", "白寶奶奶港式菠蘿包", ["白寶奶奶港式菠蘿包 民族總店", "白寶奶奶港式菠蘿包 民族店"], "台南市中西區民族路二段112之1號", "06-2210807", "中西區", "https://www.ubereats.com/tw/store/%E7%99%BD%E5%AF%B6%E5%A5%B6%E5%A5%B6%E6%B8%AF%E5%BC%8F%E8%8F%A0%E8%98%BF%E5%8C%85-%E6%B0%91%E6%97%8F%E5%BA%97/Yvf5S2NUUK2isgYGUY4pww"),
    ("026", "許家堡杏仁凍", ["許家堡永華 杏仁專賣店", "許家堡杏仁專賣店"], "台南市中西區永華路一段256號", "06-2265958", "中西區", "https://www.ubereats.com/tw-en/store/%E8%A8%B1%E5%AE%B6%E5%A0%A1%E6%B0%B8%E8%8F%AF-%E6%9D%8F%E4%BB%81%E5%B0%88%E8%B3%A3%E5%BA%97/vQu_5VSJVk2v8zFfmOOWRg"),
    ("027", "卡佛列多義大利麵", [], "台南市中西區國華街二段86號", "", "中西區", "https://www.foodpanda.com.tw/restaurant/a2qd/qia-fo-lie-duo-yi-da-li-mian"),
    ("028", "cama café 台南西門店", ["cama café", "cama cafe 台南西門店"], "台南市中西區西門路一段701號1樓", "06-2201988", "中西區", "https://www.twtainan.net/zh-tw/shop/consume/9242/"),
    ("029", "摩斯漢堡 台南西門店", ["摩斯漢堡", "MOS BURGER 台南西門店"], "台南市中西區西門路一段701號", "06-2213009", "中西區", "https://www.mos.com.tw/shop/search_detail.aspx?id=B357"),
    ("030", "樂雅樂 台南西門店", ["樂雅樂", "樂雅樂餐廳 台南西門店"], "台南市中西區西門路一段701號1樓", "", "中西區", "https://www.royalpark.com.tw/branch/3/1"),
]


DIRECT_PLATFORM_EVIDENCE = {
    "007": [("Uber Eats", "marketplace", ["pickup", "delivery"], STORE_SEEDS[6][6])],
    "013": [("Uber Eats", "marketplace", ["pickup", "delivery"], "https://www.ubereats.com/tw-en/store/%E5%86%AC%E7%93%9C%E5%AF%B6-%E5%86%AC%E7%93%9C%E8%8C%B6%E5%86%B7%E9%A3%B2%E5%B0%88%E8%B3%A3%E5%BA%97/yzdkZNFCWy-8IPmhagUWdA")],
    "014": [("Uber Eats", "marketplace", ["delivery"], "https://www.ubereats.com/tw/store/%E5%BB%A3%E6%9D%B1%E6%B2%99%E8%8C%B6%E7%88%90/vq2_BBqzQ3GOQ7hAYdCtkg")],
    "025": [("Uber Eats", "marketplace", ["pickup", "delivery"], STORE_SEEDS[24][6])],
    "026": [("Uber Eats", "marketplace", ["pickup", "delivery"], STORE_SEEDS[25][6])],
    "027": [("foodpanda", "marketplace", ["delivery"], STORE_SEEDS[26][6])],
    "030": [
        ("foodpanda", "marketplace", ["delivery"], "https://www.foodpanda.com.tw/restaurant/vp2i/le-ya-le-tai-nan-xi-men-dian"),
        ("Uber Eats", "marketplace", ["delivery"], "https://www.ubereats.com/tw/store/%E6%A8%82%E9%9B%85%E6%A8%82-%E5%8F%B0%E5%8D%97%E8%A5%BF%E9%96%80%E5%BA%97/Suy7syTCQC2Q9Ad-YXJ_SA"),
    ],
}


def build_store(seed: tuple) -> dict:
    suffix, name, aliases, address, phone, district, supporting_url = seed
    claims = []
    platform_audit = {}
    for system, source_type, modes, url in DIRECT_PLATFORM_EVIDENCE.get(suffix, []):
        claims.append({
            "system": system,
            "sourceType": source_type,
            "orderMode": modes,
            "evidenceUrl": url,
            "label": "platform direct store page",
            "confidence": "confirmed",
        })
        platform_audit[system] = {
            "platform": system,
            "status": "confirmed",
            "sourceType": source_type,
            "orderMode": modes,
            "evidenceUrl": url,
            "matchedBy": ["storeName", "address"],
            "checkedAt": CHECKED_AT,
            "notes": "Direct platform store page matched the named store and address.",
        }
    if suffix == "011":
        platform_audit["Uber Eats"] = {
            "platform": "Uber Eats",
            "status": "historical_platform_listing_closed_2023_02_15",
            "sourceType": "marketplace",
            "orderMode": [],
            "evidenceUrl": "https://www.ubereats.com/tw-en/store/%E9%BC%8E%E5%AF%8C%E7%99%BC%E8%B1%AC%E6%B2%B9%E6%8B%8C%E9%A3%AF/SwNANzt4TX2Fm8x9vRgeVg",
            "matchedBy": ["storeName", "address"],
            "checkedAt": CHECKED_AT,
            "notes": "Uber Eats page says the listing closed on 2023-02-15; retained as history and not counted as current adoption.",
        }
    if suffix == "005":
        movement_note = "Government business registry shows a 2025 move to 大德街69號; the older 西門路一段703巷26號 listing is historical."
    else:
        movement_note = ""
    return {
        "brand": "南廠里指定店家",
        "storeId": f"nanchangli-{suffix}",
        "storeName": name,
        "storeAliases": aliases,
        "country": "Taiwan",
        "market": "Taiwan",
        "regionGroup": "南部",
        "city": "台南市",
        "county": "台南市",
        "district": district,
        "village": "南廠里名單",
        "address": address,
        "latitude": None,
        "longitude": None,
        "phone": phone,
        "hours": "",
        "officialSourceUrl": "",
        "officialStoreUrl": "",
        "officialMapUrl": "",
        "supportingSourceUrl": supporting_url,
        "googleSearchUrl": google_search_url(name, address),
        "gmbUrl": "",
        "gmbStatus": "needs_manual_review",
        "gmbOrderingStatus": "needs_manual_review",
        "gmbOrderLinks": [],
        "gmbPickupProviders": [],
        "gmbDeliveryProviders": [],
        "sourceCoverage": {
            "officialListed": True,
            "gmbFound": False,
            "googleFound": False,
            "thirdPartyFound": bool(supporting_url),
        },
        "orderingSystems": claims,
        "platformAudit": platform_audit,
        "hasAnyOrderingSystem": bool(claims),
        "hasGmbOrderingSystem": False,
        "manualReviewReason": "GMB identity and Google Order pickup/delivery modes not yet audited.",
        "evidenceNotes": [
            "Store population comes from the user-provided 30-store target list.",
            "Address is seeded from a named public source and must be reconciled against the current named GMB profile.",
            *( [movement_note] if movement_note else [] ),
        ],
        "checkedAt": CHECKED_AT,
    }


def all_source_claims(store: dict) -> list[dict]:
    claims = list(store.get("orderingSystems", []))
    for row in (store.get("platformAudit") or {}).values():
        if not row.get("platform") or not row.get("evidenceUrl"):
            continue
        if any(token in row.get("status", "") for token in ["not_found", "closed", "historical", "blocked", "ambiguous"]):
            continue
        claims.append({
            "system": row["platform"],
            "sourceType": row.get("sourceType", "third_party"),
            "orderMode": row.get("orderMode") or ["unknown"],
            "evidenceUrl": row["evidenceUrl"],
        })
    return claims


def count_systems(stores: list[dict], source_type: str | None = None, mode: str | None = None) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for store in stores:
        claims = store.get("orderingSystems", []) if source_type else all_source_claims(store)
        systems = {
            claim.get("system")
            for claim in claims
            if claim.get("system")
            and (not source_type or claim.get("sourceType") == source_type)
            and (not mode or mode in claim.get("orderMode", []))
        }
        counts.update(systems)
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))


def rate(value: int, total: int) -> float:
    return round(value / total, 4) if total else 0.0


def count_options(stores: list[dict], mode: str | None = None) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for store in stores:
        options = set()
        for claim in store.get("orderingSystems", []):
            if claim.get("sourceType") != "gmb":
                continue
            if mode and mode not in claim.get("orderMode", []):
                continue
            if claim.get("system"):
                options.add(claim["system"])
        for link in store.get("gmbOrderLinks", []):
            if mode and mode not in link.get("orderMode", []):
                continue
            if link.get("platform"):
                options.add(link["platform"])
        counts.update(options)
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))


def rebuild_summary(stores: list[dict], previous: dict | None = None) -> dict:
    previous = previous or {}
    total = len(stores)
    all_counts = count_systems(stores)
    gmb_counts = count_systems(stores, source_type="gmb")
    option_counts = count_options(stores)
    systems = sorted(set(SYSTEMS_IN_SCOPE) | set(all_counts) | set(gmb_counts))
    any_count = sum(bool(all_source_claims(store)) for store in stores)
    gmb_provider_count = sum(any(c.get("sourceType") == "gmb" for c in store.get("orderingSystems", [])) for store in stores)
    google_order_entry_count = sum(
        bool(store.get("hasGmbOrderingSystem"))
        or store.get("gmbOrderingStatus") == "button_confirmed_provider_pending"
        for store in stores
    )
    return {
        **previous,
        "generatedAt": CHECKED_AT,
        "brand": "南廠里店家點餐系統總覽",
        "brandSlug": "nanchangli",
        "market": "Taiwan / Tainan neighborhood target list",
        "sitePath": "./nanchangli/",
        "officialStoreCount": total,
        "gmbFoundCount": sum(bool(s.get("sourceCoverage", {}).get("gmbFound")) for s in stores),
        "gmbMissingCount": sum(not bool(s.get("sourceCoverage", {}).get("gmbFound")) for s in stores),
        "googleFoundCount": sum(bool(s.get("sourceCoverage", {}).get("googleFound")) for s in stores),
        "thirdPartyFoundCount": sum(bool(s.get("sourceCoverage", {}).get("thirdPartyFound")) for s in stores),
        "verificationGapCount": sum(s.get("gmbOrderingStatus") != "confirmed" for s in stores),
        "anyOrderingSystemCount": any_count,
        "anyOrderingSystemAdoptionRate": rate(any_count, total),
        "googleOrderEntryCount": google_order_entry_count,
        "googleOrderEntryRate": rate(google_order_entry_count, total),
        "gmbOrderingSystemCount": gmb_provider_count,
        "gmbOrderingSystemAdoptionRate": rate(gmb_provider_count, total),
        "gmbCoverageGapCount": sum(
            not s.get("hasGmbOrderingSystem")
            and s.get("gmbOrderingStatus") != "button_confirmed_provider_pending"
            for s in stores
        ),
        "unknownOrderingSystemCount": sum(not bool(all_source_claims(s)) for s in stores),
        "cityCounts": {city: sum(s.get("city") == city for s in stores) for city in TAIWAN_CITIES},
        "regionCounts": {region: sum(s.get("regionGroup") == region for s in stores) for region in REGIONS},
        "allSourceSystemCounts": all_counts,
        "allSourcePickupSystemCounts": count_systems(stores, mode="pickup"),
        "allSourceDeliverySystemCounts": count_systems(stores, mode="delivery"),
        "gmbSystemCounts": gmb_counts,
        "gmbPickupSystemCounts": count_systems(stores, source_type="gmb", mode="pickup"),
        "gmbDeliverySystemCounts": count_systems(stores, source_type="gmb", mode="delivery"),
        "gmbOrderOptionCounts": option_counts,
        "gmbOrderPickupOptionCounts": count_options(stores, mode="pickup"),
        "gmbOrderDeliveryOptionCounts": count_options(stores, mode="delivery"),
        "allSourceSystemAdoptionRates": {k: rate(v, total) for k, v in all_counts.items()},
        "gmbSystemAdoptionRates": {k: rate(v, total) for k, v in gmb_counts.items()},
        "gmbOrderOptionAdoptionRates": {k: rate(v, total) for k, v in option_counts.items()},
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
        "gmbStatusCounts": dict(Counter(s.get("gmbStatus", "unknown") for s in stores)),
        "gmbOrderingStatusCounts": dict(Counter(s.get("gmbOrderingStatus", "unknown") for s in stores)),
        "sourceCoverageCounts": {
            key: sum(bool(s.get("sourceCoverage", {}).get(key)) for s in stores)
            for key in ["officialListed", "gmbFound", "googleFound", "thirdPartyFound"]
        },
        "source": {
            "population": "User-provided 30-store target list",
            "geography": "Named neighborhood analysis centered on 南廠里; stores are retained even when the supplied name resolves just outside the strict village boundary.",
            "notes": "Current addresses are reconciled from named public sources and then checked against named GMB profiles. Google Order providers require visible mode-specific panel rows.",
        },
        "notes": [
            "本報表以使用者指定的 30 家店為母體，不以連鎖品牌官方門市數作分母。",
            "你我他之家已以 2025 年商業登記的現址大德街 69 號為主，西門路舊址保留在證據備註。",
            "名單中若有店址落在嚴格南廠里界外，仍保留於使用者指定母體並顯示實際地址。",
            "Google Order 嚴格統計只計入正確 GMB 藍色點餐流程內、依自取或外送模式可見的 provider row；平台直接頁面另列全來源證據。",
        ],
    }


def write_outputs(stores: list[dict]) -> None:
    DATA_ROOT.mkdir(parents=True, exist_ok=True)
    payload = {"stores": stores}
    previous_path = DATA_ROOT / "summary.json"
    previous = json.loads(previous_path.read_text(encoding="utf-8")) if previous_path.exists() else {}
    summary = rebuild_summary(stores, previous)
    (DATA_ROOT / "stores.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (DATA_ROOT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (REPORT_ROOT / "data-inline.js").write_text(
        "window.DAMING_DATA = " + json.dumps({"storesPayload": payload, "summary": summary}, ensure_ascii=True) + ";\n",
        encoding="ascii",
    )
    fields = [
        "storeId", "storeName", "district", "address", "phone", "gmbStatus", "gmbOrderingStatus",
        "hasAnyOrderingSystem", "hasGmbOrderingSystem", "gmbPickupProviders", "gmbDeliveryProviders",
        "allSourceSystems", "gmbSystems", "gmbUrl", "gmbOrderPanelUrl", "manualReviewReason",
    ]
    with (DATA_ROOT / "stores.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for store in stores:
            writer.writerow({
                **{field: store.get(field, "") for field in fields},
                "gmbPickupProviders": "；".join(store.get("gmbPickupProviders", [])),
                "gmbDeliveryProviders": "；".join(store.get("gmbDeliveryProviders", [])),
                "allSourceSystems": "；".join(sorted({c.get("system") for c in all_source_claims(store) if c.get("system")})),
                "gmbSystems": "；".join(sorted({c.get("system") for c in store.get("orderingSystems", []) if c.get("sourceType") == "gmb" and c.get("system")})),
            })
    print(json.dumps({
        "officialStoreCount": summary["officialStoreCount"],
        "anyOrderingSystemCount": summary["anyOrderingSystemCount"],
        "gmbOrderingStatusCounts": summary["gmbOrderingStatusCounts"],
        "allSourceSystemCounts": summary["allSourceSystemCounts"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    existing_path = DATA_ROOT / "stores.json"
    if existing_path.exists():
        stores = json.loads(existing_path.read_text(encoding="utf-8"))["stores"]
    else:
        stores = [build_store(seed) for seed in STORE_SEEDS]
    write_outputs(stores)
