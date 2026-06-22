from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "truedan"
STORES = DATA / "stores.json"
SUMMARY = DATA / "summary.json"
MAPS_AUDIT = DATA / "gmb_maps_audit.json"
MODE_AUDIT = DATA / "gmb_mode_audit.json"
NOW = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

FIXES = {
    "truedan-tw-15-03": {
        "name": "板橋府中店",
        "gmbUrl": "https://www.google.com/search?kgmid=/g/11mvqqw_mq&q=%E7%8F%8D%E7%85%AE%E4%B8%B9%E5%BA%9C%E4%B8%AD%E5%BA%97&source=sh/x/loc/uni/m1/1",
        "panelUrl": "https://www.google.com/search?kgmid=/g/11mvqqw_mq&q=%E7%8F%8D%E7%85%AE%E4%B8%B9%E5%BA%9C%E4%B8%AD%E5%BA%97&source=sh/x/loc/uni/m1/1#sv=CAESzQEKuQEStgEKd0FKaVQ0dEk2ekRhOUxhQ0QzNXNPNnFvdkI1M3dKVE1FbVc0eXdPTlNKemVVblIzdUhtNjJUMWVfZEdkT0poQmNEdHhjS2t1cGxudmNhWjNmSWo3VmpLMklTM2d6NHFXTUdtRjdvUi13cWc4SEdpOW5UMjczVWpVEhdRVkE1YXQtekk5bkJ2cjBQMXBEcjZRWRoiQURzcjlmUW9CVFhCcmxVNE5LelBSNFRQa1lQVllrQVo1dxIEODEyNBoBMyoAMAA4AUAAGCogkNaKmwJKAhAB",
        "foodpandaUrl": "https://www.foodpanda.com.tw/food-ordering?c=tw&s=s&vc=ztmh&adj_t=1naixy2v_1nsybtos&adj_campaign=google_reserve_place_order_action_CH-SEO_&adj_deep_link=foodpanda%3A%2F%2F%3Fc%3Dtw%26s%3Ds%26vc%3Dztmh&adj_fallback=https://foodpanda.com.tw/restaurant/ztmh/zhen-zhu-dan-ban-qiao-fu-zhong-dian?utm_campaign=google_reserve_place_order_action_CH-SEO_&adj_redirect_macos=https://foodpanda.com.tw/restaurant/ztmh/zhen-zhu-dan-ban-qiao-fu-zhong-dian?utm_campaign=google_reserve_place_order_action_CH-SEO_",
        "nidinUrl": "https://order.nidin.shop/menu/3867",
    },
    "truedan-tw-14-05": {
        "name": "桃園大園店",
        "gmbUrl": "https://www.google.com/search?kgmid=/g/11frdw_yxp&q=%E7%8F%8D%E7%85%AE%E4%B8%B9%E5%A4%A7%E5%9C%92%E5%BA%97&source=sh/x/loc/uni/m1/1",
        "panelUrl": "https://www.google.com/search?kgmid=/g/11frdw_yxp&q=%E7%8F%8D%E7%85%AE%E4%B8%B9%E5%A4%A7%E5%9C%92%E5%BA%97&source=sh/x/loc/uni/m1/1#sv=CAESzQEKuQEStgEKd0FKaVQ0dEplaHdoZnB4WVB2ZDVDOG1VVjhDYmNMWXEwYnJWeFJjX1hYVjR5X1N2VVgzVE1XVEMxYWtEcnROdUVqM2NTTDJaWktaS0xGby1QNmRqT1pRZ1V1RjVJNnJ3bWxoVE1uR2sxMkFrMDQzYVM3M0U2MmdnEhdSMUE1YW9HN0pLbk8xZThQamN5QmdBWRoiQURzcjlmVGtQQXlQd2NkM1BQT1UzUXc1cm9wSUtEQm1PQRIEODEyNBoBMyoAMAA4AUAAGCogitWc_AhKAhAB",
        "foodpandaUrl": "https://www.foodpanda.com.tw/food-ordering?c=tw&s=s&vc=u2as&adj_t=1naixy2v_1nsybtos&adj_campaign=google_reserve_place_order_action_CH-SEO_&adj_deep_link=foodpanda%3A%2F%2F%3Fc%3Dtw%26s%3Ds%26vc%3Du2as&adj_fallback=https://foodpanda.com.tw/restaurant/u2as/zhen-zhu-dan-tao-yuan-da-yuan-dian?utm_campaign=google_reserve_place_order_action_CH-SEO_&adj_redirect_macos=https://foodpanda.com.tw/restaurant/u2as/zhen-zhu-dan-tao-yuan-da-yuan-dian?utm_campaign=google_reserve_place_order_action_CH-SEO_",
        "nidinUrl": "https://order.nidin.shop/menu/6581",
    },
    "truedan-tw-5-07": {
        "name": "漢神巨蛋店",
        "gmbUrl": "https://www.google.com/search?kgmid=/g/11lh6g80vv&q=%E7%8F%8D%E7%85%AE%E4%B8%B9+%E9%AB%98%E9%9B%84%E6%BC%A2%E7%A5%9E%E5%B7%A8%E8%9B%8B%E8%B3%BC%E7%89%A9%E5%BB%A3%E5%A0%B4%E5%BA%97&source=sh/x/loc/uni/m1/1",
        "panelUrl": "https://www.google.com/search?kgmid=/g/11lh6g80vv&q=%E7%8F%8D%E7%85%AE%E4%B8%B9+%E9%AB%98%E9%9B%84%E6%BC%A2%E7%A5%9E%E5%B7%A8%E8%9B%8B%E8%B3%BC%E7%89%A9%E5%BB%A3%E5%A0%B4%E5%BA%97&source=sh/x/loc/uni/m1/1#sv=CAESzQEKuQEStgEKd0FKaVQ0dEw1eUNwc19fRTZ5N29VM2xWVnpybzRuSHJtX0oyRXlkVUVHNkEwZ2ZBa25aMGh0ZXIxdkNyTjY5LS1BQlNOcVRrSzdKM0pHVXRKNjNLMnV6ZUctNktmM2NaNXhBMmJoRmlWckNJQ29oTlA4WmFZR3NnEhdUVkE1YXVuOUhNRGwxZThQc3AyQ3VBRRoiQURzcjlmUkJ2eGVOYTlHd25YZjNhZkx4VnRLQXR1UUU2dxIEODEyNBoBMyoAMAA4AUAAGCogrJr0_g1KAhAB",
        "foodpandaUrl": "https://www.foodpanda.com.tw/food-ordering?c=tw&s=s&vc=uzup&adj_t=1naixy2v_1nsybtos&adj_campaign=google_reserve_place_order_action_CH-SEO_&adj_deep_link=foodpanda%3A%2F%2F%3Fc%3Dtw%26s%3Ds%26vc%3Duzup&adj_fallback=https://foodpanda.com.tw/restaurant/uzup/zhen-zhu-dan-han-shen-ju-dan?utm_campaign=google_reserve_place_order_action_CH-SEO_&adj_redirect_macos=https://foodpanda.com.tw/restaurant/uzup/zhen-zhu-dan-han-shen-ju-dan?utm_campaign=google_reserve_place_order_action_CH-SEO_",
        "nidinUrl": "https://order.nidin.shop/menu/6590",
        "ocardUrl": "https://order.ocard.co/truedan/w8XkMw",
    },
}


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def save(path: Path, payload) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def upsert_claim(store: dict, claim: dict) -> None:
    store["orderingSystems"] = [
        item
        for item in store.get("orderingSystems", [])
        if not (item.get("system") == claim["system"] and item.get("sourceType") == claim["sourceType"])
    ] + [claim]


def apply_store_fix(store: dict, fix: dict) -> None:
    store["gmbStatus"] = "confirmed"
    store["gmbOrderingStatus"] = "confirmed"
    store["gmbUrl"] = fix["gmbUrl"]
    store["gmbOrderPanelUrl"] = fix["panelUrl"]
    store["gmbPickupProviders"] = ["foodpanda"]
    store["gmbDeliveryProviders"] = ["foodpanda"]
    store["hasGmbOrderingSystem"] = True
    store["hasAnyOrderingSystem"] = True
    store["manualReviewReason"] = ""
    store.setdefault("sourceCoverage", {}).update(
        {"officialListed": True, "gmbFound": True, "googleFound": True, "thirdPartyFound": True}
    )
    store["gmbOrderLinks"] = [
        link for link in store.get("gmbOrderLinks", []) if link.get("sourceType") != "gmb_order_panel"
    ]
    for mode in ("pickup", "delivery"):
        store["gmbOrderLinks"].append(
            {
                "platform": "foodpanda",
                "kind": "provider_link",
                "sourceType": "gmb_order_panel",
                "orderMode": [mode],
                "label": "foodpanda",
                "href": fix["foodpandaUrl"],
                "panelUrl": fix["panelUrl"],
                "observedAt": NOW,
                "confidence": "confirmed",
            }
        )
    upsert_claim(
        store,
        {
            "system": "foodpanda",
            "sourceType": "gmb",
            "orderMode": ["delivery", "pickup"],
            "evidenceUrl": fix["panelUrl"],
            "confidence": "confirmed",
        },
    )
    upsert_claim(
        store,
        {
            "system": "Nidin",
            "sourceType": "third_party",
            "orderMode": ["unknown"],
            "evidenceUrl": fix["nidinUrl"],
            "label": "Nidin store menu",
            "confidence": "confirmed",
            "evidenceNote": "Direct Google result opened to the named Nidin store menu; pickup/delivery mode was not readable without location state.",
        },
    )
    store.setdefault("platformAudit", {})["Nidin"] = {
        "status": "direct_url_confirmed_mode_unknown",
        "sourceType": "third_party",
        "evidenceUrl": fix["nidinUrl"],
        "directUrls": [fix["nidinUrl"]],
        "checkedAt": NOW,
        "evidence": "Direct named Nidin menu page was visible from Google results; mode was not readable in the public page state.",
    }
    if fix.get("ocardUrl"):
        store.setdefault("platformAudit", {})["Ocard"] = {
            "status": "store_page_found_not_available",
            "sourceType": "official",
            "evidenceUrl": fix["ocardUrl"],
            "checkedAt": NOW,
            "evidence": "Direct Ocard store page opened for the named store, but it displayed Not available for now, so it is not counted as confirmed adoption.",
        }
    store["gmbSignals"] = {
        "buttonDetected": True,
        "providersParsed": True,
        "attemptCount": 1,
        "maxAttempts": 1,
        "attemptHistory": [
            {
                "attempt": 1,
                "target": "chrome_google_search_kgmid",
                "status": "confirmed",
                "buttonDetected": True,
                "providersParsed": True,
                "title": fix["name"],
                "notes": [
                    "User-supplied GMB kgmid was opened in Chrome.",
                    "Google Order pickup and delivery buttons were clicked.",
                    "foodpanda reserve provider link was visible after opening each mode.",
                ],
            }
        ],
        "panelUrl": fix["panelUrl"],
        "checkedAt": NOW,
        "checkMethod": "chrome_google_search_kgmid_google_order_buttons",
        "matchQuality": "named_gmb_profile",
        "notes": "Mode-aware Chrome check parsed foodpanda provider from Google Order pickup and delivery buttons.",
    }


def recompute(summary: dict, stores: list[dict]) -> dict:
    total = len(stores)
    all_counts: Counter[str] = Counter()
    gmb_counts: Counter[str] = Counter()
    all_pickup: Counter[str] = Counter()
    all_delivery: Counter[str] = Counter()
    gmb_pickup: Counter[str] = Counter()
    gmb_delivery: Counter[str] = Counter()
    gmb_options: Counter[str] = Counter()
    gmb_option_pickup: Counter[str] = Counter()
    gmb_option_delivery: Counter[str] = Counter()
    for store in stores:
        all_seen = set()
        gmb_seen = set()
        store_options = set()
        store_pickup_options = set()
        store_delivery_options = set()
        for claim in store.get("orderingSystems", []):
            system = claim.get("system")
            if not system:
                continue
            modes = claim.get("orderMode") or []
            all_seen.add(system)
            if "pickup" in modes:
                all_pickup[system] += 1
            if "delivery" in modes:
                all_delivery[system] += 1
            if claim.get("sourceType") == "gmb":
                gmb_seen.add(system)
                store_options.add(system)
                if "pickup" in modes:
                    gmb_pickup[system] += 1
                    store_pickup_options.add(system)
                if "delivery" in modes:
                    gmb_delivery[system] += 1
                    store_delivery_options.add(system)
        for link in store.get("gmbOrderLinks", []) or []:
            platform = link.get("platform")
            if not platform:
                continue
            store_options.add(platform)
            if "pickup" in (link.get("orderMode") or []):
                store_pickup_options.add(platform)
            if "delivery" in (link.get("orderMode") or []):
                store_delivery_options.add(platform)
        all_counts.update(all_seen)
        gmb_counts.update(gmb_seen)
        gmb_options.update(store_options)
        gmb_option_pickup.update(store_pickup_options)
        gmb_option_delivery.update(store_delivery_options)
    rate = lambda n: round(n / total, 4) if total else 0
    gmb_found = sum(1 for s in stores if s.get("sourceCoverage", {}).get("gmbFound") or s.get("gmbStatus") == "confirmed")
    google_found = sum(1 for s in stores if s.get("sourceCoverage", {}).get("googleFound"))
    third_party = sum(1 for s in stores if s.get("sourceCoverage", {}).get("thirdPartyFound"))
    any_ordering = sum(1 for s in stores if s.get("hasAnyOrderingSystem"))
    gmb_ordering = sum(1 for s in stores if any(c.get("sourceType") == "gmb" for c in s.get("orderingSystems", [])))
    google_order_entry = sum(1 for s in stores if s.get("hasGmbOrderingSystem") or s.get("gmbOrderingStatus") in {"confirmed", "button_confirmed_provider_pending"})
    summary.update(
        {
            "generatedAt": NOW,
            "gmbFoundCount": gmb_found,
            "gmbMissingCount": total - gmb_found,
            "googleFoundCount": google_found,
            "thirdPartyFoundCount": third_party,
            "anyOrderingSystemCount": any_ordering,
            "anyOrderingSystemAdoptionRate": rate(any_ordering),
            "googleOrderEntryCount": google_order_entry,
            "googleOrderEntryRate": rate(google_order_entry),
            "gmbOrderingSystemCount": gmb_ordering,
            "gmbOrderingSystemAdoptionRate": rate(gmb_ordering),
            "gmbCoverageGapCount": sum(1 for s in stores if not s.get("hasGmbOrderingSystem") and s.get("gmbOrderingStatus") != "button_confirmed_provider_pending"),
            "unknownOrderingSystemCount": total - any_ordering,
            "allSourceSystemCounts": dict(all_counts),
            "allSourcePickupSystemCounts": dict(all_pickup),
            "allSourceDeliverySystemCounts": dict(all_delivery),
            "gmbSystemCounts": dict(gmb_counts),
            "gmbPickupSystemCounts": dict(gmb_pickup),
            "gmbDeliverySystemCounts": dict(gmb_delivery),
            "gmbOrderOptionCounts": dict(gmb_options),
            "gmbOrderPickupOptionCounts": dict(gmb_option_pickup),
            "gmbOrderDeliveryOptionCounts": dict(gmb_option_delivery),
            "gmbStatusCounts": dict(Counter(s.get("gmbStatus") for s in stores)),
            "gmbOrderingStatusCounts": dict(Counter(s.get("gmbOrderingStatus") for s in stores)),
            "sourceCoverageCounts": {
                "officialListed": total,
                "gmbFound": gmb_found,
                "googleFound": google_found,
                "thirdPartyFound": third_party,
            },
        }
    )
    summary["allSourceSystemAdoptionRates"] = {k: rate(v) for k, v in all_counts.items()}
    summary["gmbSystemAdoptionRates"] = {k: rate(v) for k, v in gmb_counts.items()}
    summary["gmbOrderOptionAdoptionRates"] = {k: rate(v) for k, v in gmb_options.items()}
    systems = sorted(set(all_counts) | set(gmb_counts))
    summary["systemComparison"] = [
        {
            "system": system,
            "allSourceStoreCount": all_counts.get(system, 0),
            "allSourceAdoptionRate": rate(all_counts.get(system, 0)),
            "gmbStoreCount": gmb_counts.get(system, 0),
            "gmbAdoptionRate": rate(gmb_counts.get(system, 0)),
            "countGap": all_counts.get(system, 0) - gmb_counts.get(system, 0),
            "percentagePointGap": round(rate(all_counts.get(system, 0)) - rate(gmb_counts.get(system, 0)), 4),
        }
        for system in systems
    ]
    return summary


def main() -> None:
    stores = load(STORES)
    summary = load(SUMMARY)
    maps_audit = {item["storeId"]: item for item in load(MAPS_AUDIT)}
    mode_audit = {item["storeId"]: item for item in load(MODE_AUDIT)}
    stores_by_id = {store["storeId"]: store for store in stores}
    for store_id, fix in FIXES.items():
        store = stores_by_id[store_id]
        apply_store_fix(store, fix)
        maps_audit[store_id] = {
            "checkedAt": NOW,
            "storeId": store_id,
            "storeName": store["storeName"],
            "address": store["address"],
            "gmbStatus": "confirmed",
            "gmbOrderingStatus": "confirmed",
            "gmbUrl": fix["gmbUrl"],
            "buttonDetected": True,
            "providers": ["foodpanda"],
            "panelUrl": fix["panelUrl"],
            "title": fix["name"],
            "notes": ["Chrome kgmid check confirmed pickup and delivery Google Order buttons with foodpanda provider links."],
        }
        mode_audit[store_id] = {
            "storeId": store_id,
            "storeName": store["storeName"],
            "panelUrl": fix["panelUrl"],
            "checkedAt": NOW,
            "modes": {
                mode: {
                    "clicked": True,
                    "providers": [{"provider": "foodpanda", "label": "foodpanda", "href": fix["foodpandaUrl"]}],
                }
                for mode in ("pickup", "delivery")
            },
            "notes": ["Chrome kgmid check; only foodpanda reserve provider links were counted as strict Google Order provider evidence."],
        }
    save(STORES, stores)
    save(SUMMARY, recompute(summary, stores))
    save(MAPS_AUDIT, list(maps_audit.values()))
    save(MODE_AUDIT, list(mode_audit.values()))


if __name__ == "__main__":
    main()
