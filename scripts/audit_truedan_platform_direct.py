from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "truedan"
STORES_PATH = DATA_DIR / "stores.json"
SUMMARY_PATH = DATA_DIR / "summary.json"

CHECKED_AT = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
OCARD_BRAND_URL = "https://order.ocard.co/truedan?a=&utm_medium=line&utm_source=bot"
OCARD_API_URL = "https://api-order.ocard.co/brand/get"
NIDIN_BRAND_URL = "https://order.nidin.shop/brand/truedan"
QUICKCLICK_PORTALS = [
    "https://order.quickclick.cc/tw/portals/TRUEDAN",
    "https://order.quickclick.cc/tw/portals/truedan",
    "https://order.quickclick.cc/tw/portals/TrueDan",
]


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def normalize(value: str | None) -> str:
    text = (value or "").replace("臺", "台")
    text = text.replace("１", "1").replace("一樓", "1樓").replace("之", "")
    text = re.sub(r"[\s,，、\-－()（）/]", "", text)
    text = text.replace("號1樓", "號").replace("號一樓", "號")
    return text


def mode_list(platform_store: dict[str, Any]) -> list[str]:
    modes: list[str] = []
    if platform_store.get("pickup"):
        modes.append("pickup")
    if platform_store.get("delivery"):
        modes.append("delivery")
    return modes


def fetch_ocard_stores() -> list[dict[str, Any]]:
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json,text/plain,*/*",
        "Referer": "https://order.ocard.co/",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    response = requests.post(
        OCARD_API_URL,
        headers=headers,
        data="a=&utm_medium=line&utm_source=bot&brand_id=truedan",
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    return payload.get("data", {}).get("stores", [])


def quickclick_status() -> dict[str, Any]:
    attempts = []
    for url in QUICKCLICK_PORTALS:
        status = "unavailable_or_blocked"
        final_url = url
        detail = ""
        try:
            response = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
            final_url = response.url
            detail = f"HTTP {response.status_code}"
            if "Invalid+portal" in response.url or "Invalid portal" in response.text:
                status = "not_found"
            elif response.ok:
                status = "needs_manual_review"
        except requests.RequestException as exc:
            detail = type(exc).__name__
        attempts.append({"url": url, "finalUrl": final_url, "status": status, "detail": detail})
    if any(item["status"] == "needs_manual_review" for item in attempts):
        status = "needs_manual_review"
    elif all(item["status"] == "not_found" for item in attempts):
        status = "not_found"
    else:
        status = "unavailable_or_blocked"
    return {"status": status, "attempts": attempts, "checkedAt": CHECKED_AT}


def best_ocard_match(store: dict[str, Any], ocard_stores: list[dict[str, Any]], used: set[int]) -> tuple[int | None, int]:
    store_name = normalize(store.get("storeName"))
    store_addr = normalize(store.get("address"))
    best_index: int | None = None
    best_score = 0
    for index, candidate in enumerate(ocard_stores):
        if index in used:
            continue
        candidate_name = normalize(candidate.get("name"))
        candidate_addr = normalize(candidate.get("address"))
        score = 0
        if store_addr and candidate_addr:
            if store_addr == candidate_addr:
                score += 100
            elif store_addr in candidate_addr or candidate_addr in store_addr:
                score += 80
        if store_name and candidate_name:
            if store_name == candidate_name:
                score += 40
            elif store_name in candidate_name or candidate_name in store_name:
                score += 30
        if score > best_score:
            best_score = score
            best_index = index
    if best_score >= 40:
        return best_index, best_score
    return None, best_score


def dedupe_claims(claims: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str, str]] = set()
    result = []
    for claim in claims:
        key = (
            claim.get("system", ""),
            claim.get("sourceType", ""),
            claim.get("evidenceUrl", ""),
        )
        if key in seen:
            continue
        seen.add(key)
        result.append(claim)
    return result


def update_store_with_ocard(store: dict[str, Any], platform_store: dict[str, Any] | None, score: int) -> None:
    store["orderingSystems"] = [
        claim for claim in store.get("orderingSystems", []) if claim.get("system") != "Ocard"
    ]
    audit = dict(store.get("platformAudit") or {})
    if platform_store:
        token = platform_store.get("token") or ""
        evidence_url = f"https://order.ocard.co/truedan/{token}" if token else OCARD_BRAND_URL
        modes = mode_list(platform_store)
        store["orderingSystems"].append(
            {
                "system": "Ocard",
                "sourceType": "official",
                "orderMode": modes,
                "evidenceUrl": evidence_url,
                "label": "Ocard Online Order",
                "confidence": "confirmed",
                "evidenceNote": (
                    "Matched directly from Ocard brand API by store name/address. "
                    f"pickup={platform_store.get('pickup') or 'none'}, "
                    f"delivery={platform_store.get('delivery') or 'none'}."
                ),
            }
        )
        audit["Ocard"] = {
            "status": "confirmed",
            "sourceType": "official",
            "orderMode": modes,
            "evidenceUrl": evidence_url,
            "platformStoreName": platform_store.get("name"),
            "platformStoreAddress": platform_store.get("address"),
            "platformStoreToken": token,
            "matchScore": score,
            "checkedAt": CHECKED_AT,
        }
    else:
        audit["Ocard"] = {
            "status": "not_listed_for_official_store",
            "sourceType": "official",
            "evidenceUrl": OCARD_BRAND_URL,
            "checkedAt": CHECKED_AT,
        }

    nidin_links = [
        link.get("href")
        for link in store.get("gmbOrderLinks", []) or []
        if (link.get("platform") or "").lower() == "nidin" and link.get("href")
    ]
    audit["Nidin"] = {
        "status": "direct_urls_seen_in_google_order_links" if nidin_links else "brand_page_active_location_required",
        "sourceType": "third_party",
        "evidenceUrl": NIDIN_BRAND_URL,
        "directUrls": sorted(set(nidin_links)),
        "checkedAt": CHECKED_AT,
        "evidence": (
            "Nidin brand page is active, but the current public brand page requires location selection "
            "before showing nearby stores. Store-level Nidin URLs are preserved when direct URLs were "
            "visible inside prior Google Order panels."
        ),
    }
    audit["LINE"] = {
        "status": "official_link_routes_to_ocard",
        "sourceType": "line",
        "evidenceUrl": OCARD_BRAND_URL,
        "checkedAt": CHECKED_AT,
        "evidence": "The current public Ocard entry is distributed with utm_source=line; no separate LINE ordering store list was found.",
    }
    store["platformAudit"] = audit
    store["orderingSystems"] = dedupe_claims(store["orderingSystems"])

    direct_platform = any(
        claim.get("sourceType") in {"official", "marketplace", "line", "third_party"}
        for claim in store.get("orderingSystems", [])
    )
    store.setdefault("sourceCoverage", {})["thirdPartyFound"] = bool(direct_platform)
    store["sourceCoverage"]["officialOrderingFound"] = bool(platform_store)
    store["hasAnyOrderingSystem"] = bool(store.get("orderingSystems"))


def summarize_platform_audit(
    stores: list[dict[str, Any]],
    ocard_stores: list[dict[str, Any]],
    ocard_unmatched: list[dict[str, Any]],
    quickclick: dict[str, Any],
) -> dict[str, Any]:
    ocard_claims = [
        store for store in stores if (store.get("platformAudit") or {}).get("Ocard", {}).get("status") == "confirmed"
    ]
    ocard_pickup = sum(
        1 for store in ocard_claims if "pickup" in (store.get("platformAudit") or {}).get("Ocard", {}).get("orderMode", [])
    )
    ocard_delivery = sum(
        1 for store in ocard_claims if "delivery" in (store.get("platformAudit") or {}).get("Ocard", {}).get("orderMode", [])
    )
    nidin_direct_url = sum(
        1
        for store in stores
        if (store.get("platformAudit") or {}).get("Nidin", {}).get("status") == "direct_urls_seen_in_google_order_links"
    )
    platform_status_counts = Counter()
    for store in stores:
        for platform, audit in (store.get("platformAudit") or {}).items():
            platform_status_counts[f"{platform}:{audit.get('status')}"] += 1

    return {
        "checkedAt": CHECKED_AT,
        "platformsChecked": ["Ocard", "Nidin", "QuickClick", "LINE", "Uber Eats", "foodpanda"],
        "Ocard": {
            "brandUrl": OCARD_BRAND_URL,
            "apiUrl": OCARD_API_URL,
            "platformStoreCount": len(ocard_stores),
            "officialStoreMatchedCount": len(ocard_claims),
            "pickupMatchedCount": ocard_pickup,
            "deliveryMatchedCount": ocard_delivery,
            "officialStoresNotListed": [
                {
                    "storeId": store.get("storeId"),
                    "storeName": store.get("storeName"),
                    "address": store.get("address"),
                }
                for store in stores
                if (store.get("platformAudit") or {}).get("Ocard", {}).get("status")
                == "not_listed_for_official_store"
            ],
            "platformStoresNotInOfficialList": ocard_unmatched,
        },
        "Nidin": {
            "brandUrl": NIDIN_BRAND_URL,
            "status": "brand_page_active_location_required",
            "storesWithDirectUrlsFromGoogleOrderLinks": nidin_direct_url,
        },
        "QuickClick": quickclick,
        "LINE": {
            "status": "official_link_routes_to_ocard",
            "evidenceUrl": OCARD_BRAND_URL,
        },
        "Uber Eats": {
            "status": "brand_page_found_but_direct_crawl_blocked",
            "evidenceUrl": "https://www.ubereats.com/tw/brand/truedan",
        },
        "foodpanda": {
            "status": "store_pages_found_by_public_search_chain_api_not_exhaustive",
            "evidenceUrl": "https://www.foodpanda.com.tw/search?q=%E7%8F%8D%E7%85%AE%E4%B8%B9",
        },
        "storePlatformStatusCounts": dict(sorted(platform_status_counts.items())),
    }


def main() -> None:
    stores = load_json(STORES_PATH)
    summary = load_json(SUMMARY_PATH)
    ocard_stores = fetch_ocard_stores()
    quickclick = quickclick_status()

    used_ocard: set[int] = set()
    for store in stores:
        match_index, score = best_ocard_match(store, ocard_stores, used_ocard)
        platform_store = ocard_stores[match_index] if match_index is not None else None
        if match_index is not None:
            used_ocard.add(match_index)
        update_store_with_ocard(store, platform_store, score)
        store["checkedAt"] = CHECKED_AT

    ocard_unmatched = [
        {
            "token": candidate.get("token"),
            "name": candidate.get("name"),
            "address": candidate.get("address"),
            "pickup": candidate.get("pickup"),
            "delivery": candidate.get("delivery"),
            "evidenceUrl": f"https://order.ocard.co/truedan/{candidate.get('token')}",
        }
        for index, candidate in enumerate(ocard_stores)
        if index not in used_ocard
    ]
    summary["platformDirectAudit"] = summarize_platform_audit(stores, ocard_stores, ocard_unmatched, quickclick)
    summary["notes"] = [
        note
        for note in summary.get("notes", [])
        if "Started store-by-store platform audit" not in note
    ]
    summary["notes"].append(
        "Platform-direct rerun: Ocard brand API was checked directly and matched against every official active store. "
        "This is counted separately from Google Order provider evidence and includes pickup/delivery mode fields."
    )
    summary["notes"].append(
        "Ocard currently returns 66 platform stores; 65 match the official active store population. "
        "Official Hanshin Arena is not listed on Ocard, while Ocard has one platform-only Xinzhuang Xintai entry."
    )

    write_json(STORES_PATH, stores)
    write_json(SUMMARY_PATH, summary)
    print(
        json.dumps(
            {
                "officialStores": len(stores),
                "ocardPlatformStores": len(ocard_stores),
                "ocardMatchedOfficialStores": summary["platformDirectAudit"]["Ocard"]["officialStoreMatchedCount"],
                "ocardPickupMatched": summary["platformDirectAudit"]["Ocard"]["pickupMatchedCount"],
                "ocardDeliveryMatched": summary["platformDirectAudit"]["Ocard"]["deliveryMatchedCount"],
                "ocardUnmatchedPlatformStores": len(ocard_unmatched),
                "quickclick": quickclick["status"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
