from __future__ import annotations

import csv
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, quote, urlencode, urljoin, urlparse

import requests
from bs4 import BeautifulSoup


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "teamagichand"
DATA = OUT / "data"

BRAND = "茶之魔手"
BRAND_SLUG = "teamagichand"
MARKET = "Taiwan"
OFFICIAL_SITE = "https://www.teamagichand.com.tw/"
OFFICIAL_STORE_URL = "https://www.teamagichand.com.tw/store/"
NIDIN_BRAND_URL = "https://order.nidin.shop/brand/teamagichand"
NIDIN_API = "https://loctw-service-api.nidin.shop/shopper/v2"
FOODPANDA_CHAIN_URL = "https://www.foodpanda.com.tw/chain/ch3sh/cha-zhi-mo-shou"
PB_ORDER_URL = "https://app.esgpb.com/order/"
CHECKED_AT = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
OFFICIAL_LISTED_CITIES = [
    "台南市",
    "高雄市",
    "屏東縣",
    "嘉義縣",
    "雲林縣",
    "彰化縣",
    "台中市",
    "南投縣",
    "新竹縣",
    "桃園市",
    "台北市",
    "新北市",
    "宜蘭縣",
    "花蓮縣",
    "台東縣",
    "澎湖縣",
]

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
    **{city: "北部" for city in ["基隆市", "台北市", "新北市", "桃園市", "新竹市", "新竹縣", "苗栗縣"]},
    **{city: "中部" for city in ["台中市", "彰化縣", "南投縣", "雲林縣"]},
    **{city: "南部" for city in ["嘉義市", "嘉義縣", "台南市", "高雄市", "屏東縣"]},
    **{city: "東部" for city in ["宜蘭縣", "花蓮縣", "台東縣"]},
    **{city: "離島" for city in ["澎湖縣", "金門縣", "連江縣"]},
}
REGIONS = ["北部", "中部", "南部", "東部", "離島"]


def clean(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "").replace("\xa0", " ")).strip()


def normalize_text(value: str) -> str:
    return clean(value).replace("臺", "台")


def normalize_key(value: str) -> str:
    value = normalize_text(value)
    value = re.sub(r"[^\w\u4e00-\u9fff]", "", value)
    return value.lower()


def city_from_address(address: str) -> str:
    text = normalize_text(address)
    for city in TAIWAN_CITIES:
        if city in text or city.replace("台", "臺") in text:
            return city
    return ""


def district_from_address(address: str, city: str) -> str:
    text = normalize_text(address)
    tail = text.split(city, 1)[1] if city and city in text else text
    match = re.search(r"([\u4e00-\u9fff]{1,5}(?:區|鄉|鎮|市))", tail)
    return match.group(1) if match else ""


def rate(count: int, total: int) -> float:
    return round(count / total, 4) if total else 0.0


def map_coords(map_url: str) -> tuple[float | None, float | None]:
    try:
        query = parse_qs(urlparse(map_url).query)
        daddr = query.get("daddr", [""])[0]
        lat, lng = [part.strip() for part in daddr.split(",", 1)]
        return float(lat), float(lng)
    except Exception:
        return None, None


def official_city_url(city: str) -> str:
    return f"{OFFICIAL_STORE_URL}?{urlencode({'index_m_id': '1', 'city': city})}"


def parse_official_city_rows(city_name: str, store_offset: int) -> list[dict]:
    city_url = official_city_url(city_name)
    response = requests.get(city_url, headers=HEADERS, timeout=45)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    rows: list[dict] = []
    for index, tr in enumerate(soup.select("table.storeList tbody tr"), start=store_offset + 1):
        cells = tr.find_all("td")
        if len(cells) < 3:
            continue
        name = clean(cells[0].get_text(" ", strip=True))
        phone = clean(cells[1].get_text(" ", strip=True))
        addr_link = cells[2].select_one("a.addrLink") or cells[2].find("a")
        address = normalize_text(addr_link.get_text(" ", strip=True) if addr_link else cells[2].get_text(" ", strip=True))
        map_url = addr_link.get("href", "") if addr_link else ""
        city = city_from_address(address) or city_name
        district = district_from_address(address, city)
        lat, lng = map_coords(map_url)
        store_id = f"{BRAND_SLUG}-tw-{index:03d}"
        rows.append(
            {
                "brand": BRAND,
                "storeId": store_id,
                "storeName": name,
                "country": "Taiwan",
                "market": MARKET,
                "regionGroup": REGION_BY_CITY.get(city, "未解析"),
                "city": city or "未解析",
                "county": city or "未解析",
                "district": district,
                "address": address,
                "latitude": lat,
                "longitude": lng,
                "phone": phone,
                "hours": "",
                "officialSourceUrl": city_url,
                "officialStoreUrl": city_url,
                "officialMapUrl": map_url,
                "googleSearchUrl": f"https://www.google.com/search?q={quote(f'{BRAND} {name} {address}')}&hl=zh-TW",
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
                    "thirdPartyFound": False,
                },
                "orderingSystems": [],
                "hasAnyOrderingSystem": False,
                "hasGmbOrderingSystem": False,
                "manualReviewReason": (
                    "Official store is listed. Matching named GMB profile and Google Order pickup/delivery "
                    "provider panel still need live review."
                ),
                "evidenceNotes": [
                    "Official store locator is the active store population source.",
                    "Official Maps link is an address/coordinate lead only; it is not counted as a named GMB match until rechecked.",
                ],
                "platformAudit": [],
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
        )
    return rows


def official_store_rows() -> list[dict]:
    rows: list[dict] = []
    seen: set[tuple[str, str, str]] = set()
    for city in OFFICIAL_LISTED_CITIES:
        for store in parse_official_city_rows(city, len(rows)):
            key = (normalize_key(store["storeName"]), normalize_key(store["address"]), store.get("phone") or "")
            if key in seen:
                continue
            seen.add(key)
            rows.append(store)
    for index, store in enumerate(rows, start=1):
        store["storeId"] = f"{BRAND_SLUG}-tw-{index:03d}"
    return rows


def fetch_nidin_stores() -> list[dict]:
    stores: list[dict] = []
    page = 1
    total = None
    while total is None or len(stores) < total:
        params = {
            "brand_code": "teamagichand",
            "count": 20,
            "page": page,
            "latitude": 23.6978,
            "longitude": 120.9605,
            "distance_km": 10000,
            "src_type": 3,
        }
        response = requests.get(
            f"{NIDIN_API}/store/listByPositionNew",
            headers={**HEADERS, "MC-API-Brand-Code": "teamagichand"},
            params=params,
            timeout=45,
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("status") != 200:
            raise RuntimeError(f"Nidin API status {payload.get('status')}: {payload.get('message')}")
        batch = payload.get("list") or []
        total = int((payload.get("meta") or {}).get("total_amount") or len(batch))
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


def match_nidin_to_official(stores: list[dict], nidin_items: list[dict]) -> dict:
    by_address = {normalize_key(store["address"]): store for store in stores}
    by_name_city = {(normalize_key(store["storeName"]), store["city"]): store for store in stores}
    matched: dict[str, dict] = {}
    unmatched: list[dict] = []
    for item in nidin_items:
        address = normalize_text(item.get("address") or "")
        city = city_from_address(address)
        name = normalize_text(item.get("name") or item.get("name_short") or "")
        store = by_address.get(normalize_key(address)) or by_name_city.get((normalize_key(name), city))
        evidence_url = f"https://order.nidin.shop/menu/{item['id']}"
        modes = nidin_order_modes(item)
        audit_row = {
            "platform": "Nidin",
            "status": "confirmed" if store and modes else "listed_but_order_unavailable" if store else "platform_store_not_in_official_list",
            "sourceType": "third_party",
            "orderMode": modes,
            "evidenceUrl": evidence_url,
            "matchedBy": ["address"] if store and normalize_key(store["address"]) == normalize_key(address) else ["storeName", "city"] if store else [],
            "checkedAt": CHECKED_AT,
            "notes": clean(item.get("delivery_way_description") or ""),
            "platformStoreId": item.get("id"),
            "platformStoreName": name,
            "platformStoreAddress": address,
        }
        if not store:
            unmatched.append(audit_row)
            continue
        store.setdefault("platformAudit", []).append(audit_row)
        store.setdefault("sourceCoverage", {})["thirdPartyFound"] = True
        if modes:
            store["orderingSystems"].append(
                {
                    "system": "Nidin",
                    "sourceType": "third_party",
                    "orderMode": modes,
                    "evidenceUrl": evidence_url,
                    "label": "Nidin 茶之魔手門市點餐頁",
                    "confidence": "confirmed",
                    "evidenceNote": "Matched directly from Nidin brand API by official address/store identity; not counted as Google Order provider evidence.",
                }
            )
            store["hasAnyOrderingSystem"] = True
            store["manualReviewReason"] = (
                "Nidin direct platform ordering is confirmed. GMB/Google Order pickup/delivery provider evidence still needs live review."
            )
        matched[store["storeId"]] = audit_row
    return {"matched": matched, "unmatched": unmatched}


def foodpanda_platform_audit() -> dict:
    try:
        response = requests.get(FOODPANDA_CHAIN_URL, headers=HEADERS, timeout=45)
        status_code = response.status_code
        text = response.text
        state_status = "brand_page_found"
        vendor_name = ""
        vendor_address = ""
        marker = "window.__PRELOADED_STATE__="
        if marker in text:
            start = text.index(marker) + len(marker)
            end = text.index("</script>", start)
            state = json.loads(text[start:end].strip().rstrip(";"))
            vendor_info = state.get("vendorInfo") or {}
            vendor_name = clean(vendor_info.get("name") or "")
            vendor_address = normalize_text(vendor_info.get("address") or "")
            state_status = "brand_page_found_single_location_payload"
        return {
            "status": state_status,
            "sourceType": "marketplace",
            "evidenceUrl": FOODPANDA_CHAIN_URL,
            "checkedAt": CHECKED_AT,
            "httpStatus": status_code,
            "notes": (
                "Foodpanda chain page is public evidence for the brand, but the public page exposes a current/single "
                "vendor payload rather than an exhaustive store list. Store-level foodpanda should be confirmed by "
                "direct page, Google Order panel, or manual review before counting as all-store platform coverage."
            ),
            "visibleVendorName": vendor_name,
            "visibleVendorAddress": vendor_address,
        }
    except Exception as exc:
        return {
            "status": "unavailable_or_blocked",
            "sourceType": "marketplace",
            "evidenceUrl": FOODPANDA_CHAIN_URL,
            "checkedAt": CHECKED_AT,
            "notes": f"Foodpanda direct chain page check failed: {type(exc).__name__}.",
        }


def fetch_pb_order_stores() -> list[dict]:
    response = requests.get(PB_ORDER_URL, headers=HEADERS, timeout=30)
    response.raise_for_status()
    response.encoding = "utf-8"
    soup = BeautifulSoup(response.text, "html.parser")
    rows: list[dict] = []
    for card in soup.select(".el-card"):
        strings = [clean(item) for item in card.stripped_strings if clean(item)]
        if len(strings) < 2:
            continue
        name = strings[0]
        if "魔手" not in name:
            continue
        address = next((item for item in strings[1:] if "市" in item and ("路" in item or "街" in item)), strings[1])
        links = [
            urljoin(PB_ORDER_URL, anchor.get("href"))
            for anchor in card.find_all("a", href=True)
            if "/order/store/" in anchor.get("href", "") and "/pick_up/" in anchor.get("href", "")
        ]
        if not links:
            continue
        rows.append(
            {
                "platformStoreName": name,
                "platformStoreAddress": normalize_text(address),
                "evidenceUrl": links[0],
                "orderMode": ["pickup"],
            }
        )
    return rows


def match_pb_to_official(stores: list[dict], pb_items: list[dict]) -> dict:
    matched: dict[str, dict] = {}
    unmatched: list[dict] = []
    for item in pb_items:
        platform_address = normalize_key(item.get("platformStoreAddress", ""))
        store = next(
            (
                candidate
                for candidate in stores
                if platform_address
                and (
                    platform_address in normalize_key(candidate.get("address", ""))
                    or normalize_key(candidate.get("address", "")) in platform_address
                )
            ),
            None,
        )
        audit_row = {
            "platform": "PB Order",
            "status": "confirmed" if store else "platform_store_not_in_official_list",
            "sourceType": "third_party",
            "orderMode": item.get("orderMode") or ["pickup"],
            "evidenceUrl": item.get("evidenceUrl", ""),
            "matchedBy": ["address"] if store else [],
            "checkedAt": CHECKED_AT,
            "platformStoreName": item.get("platformStoreName", ""),
            "platformStoreAddress": item.get("platformStoreAddress", ""),
            "notes": "Matched from the public PB ordering page. This is all-source pickup evidence, not Google Order provider evidence.",
        }
        if not store:
            unmatched.append(audit_row)
            continue
        if not any(
            claim.get("system") == "PB Order" and claim.get("evidenceUrl") == audit_row["evidenceUrl"]
            for claim in store.get("orderingSystems", [])
        ):
            store.setdefault("orderingSystems", []).append(
                {
                    "system": "PB Order",
                    "sourceType": "third_party",
                    "orderMode": audit_row["orderMode"],
                    "evidenceUrl": audit_row["evidenceUrl"],
                    "label": "PB Order pickup",
                    "confidence": "confirmed",
                    "evidenceNote": audit_row["notes"],
                }
            )
        if not any(row.get("platform") == "PB Order" and row.get("evidenceUrl") == audit_row["evidenceUrl"] for row in store.setdefault("platformAudit", [])):
            store["platformAudit"].append(audit_row)
        store.setdefault("sourceCoverage", {})["thirdPartyFound"] = True
        store["hasAnyOrderingSystem"] = True
        matched[store["storeId"]] = audit_row
    return {"matched": matched, "unmatched": unmatched}


def quickclick_platform_audit() -> dict:
    attempts = []
    for slug in ["teamagichand", "teaMagicHand", "TeaMagicHand", "magictea", "Teamagichand"]:
        url = f"https://order.quickclick.cc/tw/portals/{slug}"
        try:
            response = requests.get(url, headers=HEADERS, timeout=20, allow_redirects=True)
            attempts.append(
                {
                    "url": url,
                    "finalUrl": response.url,
                    "httpStatus": response.status_code,
                    "status": "possible_hit" if "error" not in response.url.lower() else "not_found",
                }
            )
        except Exception as exc:
            attempts.append({"url": url, "status": "unavailable_or_blocked", "detail": type(exc).__name__})
    return {
        "status": "not_found" if all(row["status"] == "not_found" for row in attempts) else "needs_manual_review",
        "sourceType": "third_party",
        "checkedAt": CHECKED_AT,
        "attempts": attempts,
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
        for link in store.get("gmbOrderLinks") or []:
            if link.get("sourceType") != "gmb_order_panel":
                continue
            if mode and mode not in (link.get("orderMode") or []):
                continue
            if link.get("platform"):
                systems.add(link["platform"])
        counts.update(systems)
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0].lower())))


def source_coverage_counts(stores: list[dict]) -> dict[str, int]:
    keys = ["officialListed", "gmbFound", "googleFound", "thirdPartyFound"]
    return {key: sum(1 for store in stores if store.get("sourceCoverage", {}).get(key)) for key in keys}


def build_summary(stores: list[dict], platform_direct: dict | None = None) -> dict:
    official_count = len(stores)
    city_counts = {city: 0 for city in TAIWAN_CITIES}
    for store in stores:
        city_counts[store["city"]] = city_counts.get(store["city"], 0) + 1
    region_counts = {region: 0 for region in REGIONS}
    for store in stores:
        region_counts[store["regionGroup"]] = region_counts.get(store["regionGroup"], 0) + 1

    all_counts = count_systems(stores)
    gmb_counts = count_systems(stores, source_type="gmb")
    gmb_options = count_google_order_options(stores)
    any_ordering = sum(1 for store in stores if store.get("hasAnyOrderingSystem"))
    gmb_ordering = sum(1 for store in stores if store.get("hasGmbOrderingSystem"))
    gmb_entry = sum(
        1
        for store in stores
        if store.get("hasGmbOrderingSystem") or store.get("gmbOrderingStatus") == "button_confirmed_provider_pending"
    )
    systems = sorted(set(all_counts) | set(gmb_counts))
    comparison = [
        {
            "system": system,
            "allSourceStoreCount": all_counts.get(system, 0),
            "allSourceAdoptionRate": rate(all_counts.get(system, 0), official_count),
            "gmbStoreCount": gmb_counts.get(system, 0),
            "gmbAdoptionRate": rate(gmb_counts.get(system, 0), official_count),
            "countGap": all_counts.get(system, 0) - gmb_counts.get(system, 0),
            "percentagePointGap": round(
                rate(all_counts.get(system, 0), official_count) - rate(gmb_counts.get(system, 0), official_count),
                4,
            ),
        }
        for system in systems
    ]
    coverage_counts = source_coverage_counts(stores)
    gmb_gap_count = sum(
        1
        for store in stores
        if store.get("gmbOrderingStatus")
        in {
            "needs_manual_review",
            "not_found",
            "no_gmb_profile_match",
            "unavailable_or_blocked",
            "duplicate_or_ambiguous",
            "no_gmb_order_button",
        }
        or not (store.get("hasGmbOrderingSystem") or store.get("gmbOrderingStatus") == "button_confirmed_provider_pending")
    )
    summary = {
        "generatedAt": CHECKED_AT,
        "brand": BRAND,
        "brandSlug": BRAND_SLUG,
        "market": MARKET,
        "sitePath": f"./{BRAND_SLUG}/",
        "officialStoreCount": official_count,
        "gmbFoundCount": coverage_counts["gmbFound"],
        "googleFoundCount": coverage_counts["googleFound"],
        "thirdPartyFoundCount": coverage_counts["thirdPartyFound"],
        "verificationGapCount": sum(1 for store in stores if store.get("gmbStatus") != "confirmed"),
        "anyOrderingSystemCount": any_ordering,
        "anyOrderingSystemAdoptionRate": rate(any_ordering, official_count),
        "gmbOrderingSystemCount": gmb_ordering,
        "gmbOrderingSystemAdoptionRate": rate(gmb_ordering, official_count),
        "gmbCoverageGapCount": gmb_gap_count,
        "unknownOrderingSystemCount": official_count - any_ordering,
        "cityCounts": city_counts,
        "regionCounts": region_counts,
        "allSourceSystemCounts": all_counts,
        "gmbSystemCounts": gmb_counts,
        "gmbOrderOptionCounts": gmb_options,
        "gmbOrderPickupOptionCounts": count_google_order_options(stores, mode="pickup"),
        "gmbOrderDeliveryOptionCounts": count_google_order_options(stores, mode="delivery"),
        "allSourceSystemAdoptionRates": {system: rate(count, official_count) for system, count in all_counts.items()},
        "gmbSystemAdoptionRates": {system: rate(count, official_count) for system, count in gmb_counts.items()},
        "gmbOrderOptionAdoptionRates": {system: rate(count, official_count) for system, count in gmb_options.items()},
        "systemComparison": comparison,
        "gmbStatusCounts": dict(Counter(store.get("gmbStatus", "") for store in stores)),
        "gmbOrderingStatusCounts": dict(Counter(store.get("gmbOrderingStatus", "") for store in stores)),
        "sourceCoverageCounts": coverage_counts,
        "source": {
            "officialWebsite": OFFICIAL_SITE,
            "officialStoreList": OFFICIAL_STORE_URL,
            "notes": "Official store locator table is the active store population source. Google Order provider evidence is counted only after opening a matched GMB/Google Order panel.",
        },
        "notes": [
            "茶之魔手官網門市頁為官方 active store population 來源。",
            "Nidin brand API was checked directly and matched by official address/store identity; this is all-source platform evidence, not Google Order provider evidence.",
            "Foodpanda chain page was checked as platform-direct brand evidence, but the public page did not expose an exhaustive store list in the fetched payload.",
            "Google Order provider rows must be read from opened GMB order flows and separated into pickup/delivery modes.",
        ],
        "platformDirectAudit": platform_direct or {},
        "googleOrderEntryCount": gmb_entry,
        "googleOrderEntryRate": rate(gmb_entry, official_count),
        "allSourcePickupSystemCounts": count_systems(stores, mode="pickup"),
        "allSourceDeliverySystemCounts": count_systems(stores, mode="delivery"),
        "gmbPickupSystemCounts": count_systems(stores, source_type="gmb", mode="pickup"),
        "gmbDeliverySystemCounts": count_systems(stores, source_type="gmb", mode="delivery"),
    }
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
        "gmbStatus",
        "gmbOrderingStatus",
        "hasAnyOrderingSystem",
        "hasGmbOrderingSystem",
        "allSourceSystems",
        "gmbSystems",
        "pickupProviders",
        "deliveryProviders",
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
            all_systems = sorted({claim["system"] for claim in store.get("orderingSystems", []) if claim.get("system")})
            gmb_systems = sorted(
                {
                    claim["system"]
                    for claim in store.get("orderingSystems", [])
                    if claim.get("sourceType") == "gmb" and claim.get("system")
                }
            )
            evidence = sorted(
                {claim["evidenceUrl"] for claim in store.get("orderingSystems", []) if claim.get("evidenceUrl")}
            )
            writer.writerow(
                {
                    "storeId": store.get("storeId", ""),
                    "storeName": store.get("storeName", ""),
                    "regionGroup": store.get("regionGroup", ""),
                    "city": store.get("city", ""),
                    "district": store.get("district", ""),
                    "address": store.get("address", ""),
                    "phone": store.get("phone", ""),
                    "gmbStatus": store.get("gmbStatus", ""),
                    "gmbOrderingStatus": store.get("gmbOrderingStatus", ""),
                    "hasAnyOrderingSystem": store.get("hasAnyOrderingSystem", False),
                    "hasGmbOrderingSystem": store.get("hasGmbOrderingSystem", False),
                    "allSourceSystems": "、".join(all_systems),
                    "gmbSystems": "、".join(gmb_systems),
                    "pickupProviders": "、".join(store.get("gmbPickupProviders") or []),
                    "deliveryProviders": "、".join(store.get("gmbDeliveryProviders") or []),
                    "officialSourceUrl": store.get("officialSourceUrl", ""),
                    "officialStoreUrl": store.get("officialStoreUrl", ""),
                    "gmbUrl": store.get("gmbUrl", ""),
                    "evidenceLinks": " | ".join(evidence),
                    "manualReviewReason": store.get("manualReviewReason", ""),
                }
            )


def write_outputs(stores: list[dict], summary: dict) -> None:
    OUT.mkdir(exist_ok=True)
    DATA.mkdir(exist_ok=True)
    payload = {
        "generatedAt": summary["generatedAt"],
        "brand": BRAND,
        "source": summary["source"],
        "stores": stores,
    }
    (DATA / "stores.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (DATA / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (OUT / "data-inline.js").write_text(
        "window.DAMING_DATA = "
        + json.dumps({"storesPayload": payload, "summary": summary}, ensure_ascii=True)
        + ";\n",
        encoding="ascii",
    )
    write_csv(stores)
    write_html()


def write_html() -> None:
    html = """<!doctype html>
<html lang="zh-Hant">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>茶之魔手 點餐系統總覽</title>
  <link rel="stylesheet" href="../assets/styles.css?v=35" />
</head>
<body>
  <header class="topbar">
    <div>
      <p class="eyebrow">Brand Order Analysis</p>
      <h1>茶之魔手 點餐系統總覽</h1>
      <p class="subhead">台灣官方門市、Google/Maps/GMB 覆蓋、全來源平台點餐與 Google Order provider evidence，並區分自取與外送模式。<span class="version">teamagichand local audit</span></p>
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
        <div><p class="eyebrow">1. Store Footprint</p><h2>官方門市與地理分布</h2></div>
        <p>以茶之魔手官網門市表格作為 active store population；官方 Maps 連結只作為地址 lead，GMB 需另行命名 profile 確認。</p>
      </div>
      <div class="kpi-grid" id="storeKpis"></div>
      <div class="split map-layout">
        <div>
          <h3>台灣門市地圖</h3>
          <p class="map-source">顯示台灣 22 縣市；無門市縣市保留 0。</p>
          <div class="taiwan-map" id="taiwanMap"></div>
        </div>
        <div><h3>城市排行</h3><div class="bars" id="cityBars"></div></div>
      </div>
    </section>

    <section class="panel">
      <div class="section-title">
        <div><p class="eyebrow">2. All Sources</p><h2>全來源點餐系統</h2></div>
        <p>包含官方/平台直查、Google Order provider rows 與第三方公開證據；不把 Google Order 缺口當成沒有平台點餐。</p>
      </div>
      <div class="kpi-grid" id="allSourceKpis"></div>
      <div class="split">
        <div><h3>自取系統</h3><div class="bars" id="pickupBars"></div></div>
        <div><h3>外送系統</h3><div class="bars" id="deliveryBars"></div></div>
      </div>
      <div class="split compact">
        <div><h3>區域採用率</h3><div class="matrix" id="regionMatrix"></div></div>
        <div><h3>判讀說明</h3><p class="note">全來源與 Google Order provider rows 分開計算；GMB provider 只採計開啟 Google Order panel 後可見的供應商列。</p></div>
      </div>
    </section>

    <section class="panel warning">
      <div class="section-title">
        <div><p class="eyebrow">3. Google Order</p><h2>Google Order provider / link 總覽</h2></div>
        <p>只有在正確 Google Business Profile 的藍色線上點餐流程中讀到 provider row，才列入嚴格 GMB provider evidence；自取與外送分開顯示。</p>
      </div>
      <div class="kpi-grid" id="gmbKpis"></div>
      <div class="split">
        <div><h3>Google Order 自取</h3><div class="bars" id="gmbPickupBars"></div></div>
        <div><h3>Google Order 外送</h3><div class="bars" id="gmbDeliveryBars"></div></div>
      </div>
    </section>

    <section class="panel">
      <div class="section-title"><div><p class="eyebrow">4. Comparison</p><h2>全來源 vs Google Order provider</h2></div></div>
      <div class="table-wrap"><table><thead><tr><th>系統</th><th>全來源門市</th><th>全來源比例</th><th>Google Order provider 門市</th><th>Google Order provider 比例</th><th>差距</th></tr></thead><tbody id="comparisonRows"></tbody></table></div>
    </section>

    <section class="panel">
      <div class="section-title"><div><p class="eyebrow">5. Store Details</p><h2>門市明細</h2></div><p id="detailCount"></p></div>
      <div class="table-wrap details"><table><thead><tr><th>門市</th><th>地址</th><th>區域</th><th>全來源系統</th><th>Google Order 證據</th><th>連結 / 查核</th></tr></thead><tbody id="storeRows"></tbody></table></div>
    </section>
  </main>

  <script src="data-inline.js?v=1"></script>
  <script src="../assets/taiwan-map.js?v=35"></script>
  <script src="../assets/app.js?v=37"></script>
</body>
</html>
"""
    (OUT / "index.html").write_text(html, encoding="utf-8")


def main() -> None:
    stores = official_store_rows()
    nidin_items = fetch_nidin_stores()
    nidin_match = match_nidin_to_official(stores, nidin_items)
    pb_items = fetch_pb_order_stores()
    pb_match = match_pb_to_official(stores, pb_items)
    platform_direct = {
        "checkedAt": CHECKED_AT,
        "platformsChecked": ["Nidin", "foodpanda", "Uber Eats", "LINE", "QuickClick", "PB 點餐"],
        "Nidin": {
            "brandUrl": NIDIN_BRAND_URL,
            "apiUrl": f"{NIDIN_API}/store/listByPositionNew",
            "platformStoreCount": len(nidin_items),
            "officialStoreMatchedCount": len(nidin_match["matched"]),
            "pickupMatchedCount": sum(
                1 for row in nidin_match["matched"].values() if "pickup" in (row.get("orderMode") or [])
            ),
            "deliveryMatchedCount": sum(
                1 for row in nidin_match["matched"].values() if "delivery" in (row.get("orderMode") or [])
            ),
            "platformStoresNotInOfficialList": nidin_match["unmatched"],
        },
        "foodpanda": foodpanda_platform_audit(),
        "Uber Eats": {
            "status": "public_store_pages_found_by_search_no_exhaustive_brand_api",
            "sourceType": "marketplace",
            "evidenceUrl": "https://www.ubereats.com/tw",
            "checkedAt": CHECKED_AT,
            "notes": "Public Uber Eats single-store pages can be found by search, but no stable public brand-wide store API/list was confirmed during this local run.",
        },
        "LINE": {
            "status": "not_found_as_separate_brand_ordering_portal",
            "sourceType": "line",
            "checkedAt": CHECKED_AT,
            "notes": "No separate LINE ordering brand store list was found. Nidin pages may be distributed through LINE by individual stores, but store-level LINE ordering was not inferred without a direct LINE/OA evidence URL.",
        },
        "QuickClick": quickclick_platform_audit(),
        "PB Order": {
            "status": "confirmed" if pb_match["matched"] else "not_found",
            "sourceType": "third_party",
            "brandUrl": PB_ORDER_URL,
            "checkedAt": CHECKED_AT,
            "platformStoreCount": len(pb_items),
            "officialStoreMatchedCount": len(pb_match["matched"]),
            "pickupMatchedCount": len(pb_match["matched"]),
            "deliveryMatchedCount": 0,
            "platformStoresNotInOfficialList": pb_match["unmatched"],
            "notes": "PB public ordering page exposes pickup order links. Matched by official address; counted as all-source pickup evidence, not Google Order provider evidence.",
        },
    }
    summary = build_summary(stores, platform_direct)
    write_outputs(stores, summary)
    print(
        json.dumps(
            {
                "officialStoreCount": summary["officialStoreCount"],
                "cityCounts": summary["cityCounts"],
                "allSourceSystemCounts": summary["allSourceSystemCounts"],
                "platformDirectAudit": {
                    "Nidin": summary["platformDirectAudit"]["Nidin"],
                    "foodpanda": summary["platformDirectAudit"]["foodpanda"]["status"],
                    "QuickClick": summary["platformDirectAudit"]["QuickClick"]["status"],
                },
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
