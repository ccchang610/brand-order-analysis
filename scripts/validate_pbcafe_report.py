import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "pbcafe" / "data"


def unique_systems(stores, source_type=None):
    counts = {}
    for store in stores:
        systems = set()
        for claim in store.get("orderingSystems", []):
            if source_type and claim.get("sourceType") != source_type:
                continue
            systems.add(claim.get("system"))
        for system in systems:
            counts[system] = counts.get(system, 0) + 1
    return counts


def google_order_options(stores, mode=None):
    counts = {}
    for store in stores:
        systems = set()
        for claim in store.get("orderingSystems", []):
            if claim.get("sourceType") != "gmb":
                continue
            if mode and mode not in claim.get("orderMode", []):
                continue
            systems.add(claim.get("system"))
        for link in store.get("gmbOrderLinks", []):
            if mode and mode not in link.get("orderMode", []):
                continue
            systems.add(link.get("platform"))
        for system in systems:
            counts[system] = counts.get(system, 0) + 1
    return counts


def main() -> int:
    stores_payload = json.loads((DATA / "stores.json").read_text(encoding="utf-8"))
    summary = json.loads((DATA / "summary.json").read_text(encoding="utf-8"))
    stores = stores_payload["stores"]
    failures = []

    official_count = summary["officialStoreCount"]
    if official_count != len(stores):
        failures.append(f"officialStoreCount {official_count} != stores {len(stores)}")

    city_sum = sum(summary["cityCounts"].values())
    if city_sum != official_count:
        failures.append(f"cityCounts sum {city_sum} != {official_count}")

    region_sum = sum(summary["regionCounts"].values())
    if region_sum != official_count:
        failures.append(f"regionCounts sum {region_sum} != {official_count}")

    any_count = sum(1 for store in stores if store.get("hasAnyOrderingSystem"))
    if any_count != summary["anyOrderingSystemCount"]:
        failures.append(f"anyOrderingSystemCount {summary['anyOrderingSystemCount']} != {any_count}")

    gmb_count = sum(1 for store in stores if store.get("hasGmbOrderingSystem"))
    if gmb_count != summary["gmbOrderingSystemCount"]:
        failures.append(f"gmbOrderingSystemCount {summary['gmbOrderingSystemCount']} != {gmb_count}")

    if round(any_count / official_count, 4) != summary["anyOrderingSystemAdoptionRate"]:
        failures.append("anyOrderingSystemAdoptionRate mismatch")

    if round(gmb_count / official_count, 4) != summary["gmbOrderingSystemAdoptionRate"]:
        failures.append("gmbOrderingSystemAdoptionRate mismatch")

    gmb_system_counts = unique_systems(stores, "gmb")
    if gmb_system_counts != summary["gmbSystemCounts"]:
        failures.append(f"gmbSystemCounts {summary['gmbSystemCounts']} != {gmb_system_counts}")

    pickup_options = google_order_options(stores, "pickup")
    if pickup_options != summary.get("gmbOrderPickupOptionCounts"):
        failures.append(f"gmbOrderPickupOptionCounts {summary.get('gmbOrderPickupOptionCounts')} != {pickup_options}")

    delivery_options = google_order_options(stores, "delivery")
    if delivery_options != summary.get("gmbOrderDeliveryOptionCounts"):
        failures.append(f"gmbOrderDeliveryOptionCounts {summary.get('gmbOrderDeliveryOptionCounts')} != {delivery_options}")

    stale = []
    for store in stores:
        gmb_claims = [claim for claim in store.get("orderingSystems", []) if claim.get("sourceType") == "gmb"]
        if store.get("gmbOrderingStatus") != "confirmed" and gmb_claims:
            stale.append(
                {
                    "storeId": store.get("storeId"),
                    "storeName": store.get("storeName"),
                    "status": store.get("gmbOrderingStatus"),
                    "systems": sorted({claim.get("system") for claim in gmb_claims}),
                }
            )
    if stale:
        failures.append({"staleNonConfirmedGmbClaims": stale})

    no_button_artifacts = []
    for store in stores:
        if store.get("gmbOrderingStatus") != "no_gmb_order_button":
            continue
        has_artifact = (
            store.get("gmbOrderPanelUrl")
            or store.get("gmbPickupProviders")
            or store.get("gmbDeliveryProviders")
            or store.get("hasGmbOrderingSystem")
            or store.get("hasAnyOrderingSystem")
        )
        if has_artifact:
            no_button_artifacts.append(
                {
                    "storeId": store.get("storeId"),
                    "storeName": store.get("storeName"),
                    "gmbOrderPanelUrl": store.get("gmbOrderPanelUrl"),
                    "pickup": store.get("gmbPickupProviders"),
                    "delivery": store.get("gmbDeliveryProviders"),
                }
            )
    if no_button_artifacts:
        failures.append({"noButtonArtifacts": no_button_artifacts})

    banqiao_wenhua = next((store for store in stores if store.get("storeId") == "pbcafe-022"), None)
    if not banqiao_wenhua:
        failures.append("Missing pbcafe-022 Banqiao Wenhua store")
    else:
        has_instagram_order_link = any(
            link.get("platform") == "Instagram"
            and "instagram.com/peterbetter_wenhua" in link.get("href", "")
            and set(link.get("orderMode", [])) >= {"pickup", "delivery"}
            for link in banqiao_wenhua.get("gmbOrderLinks", [])
        )
        if not has_instagram_order_link:
            failures.append("pbcafe-022 missing Instagram gmbOrderLinks pickup/delivery evidence")

    result = {
        "ok": not failures,
        "failures": failures,
        "counts": {
            "stores": len(stores),
            "confirmed": summary["gmbOrderingStatusCounts"].get("confirmed"),
            "no_gmb_order_button": summary["gmbOrderingStatusCounts"].get("no_gmb_order_button"),
            "no_gmb_profile_match": summary["gmbOrderingStatusCounts"].get("no_gmb_profile_match"),
            "thirdPartyFoundCount": summary["thirdPartyFoundCount"],
            "gmbSystemCounts": summary["gmbSystemCounts"],
            "gmbOrderPickupOptionCounts": summary.get("gmbOrderPickupOptionCounts"),
            "gmbOrderDeliveryOptionCounts": summary.get("gmbOrderDeliveryOptionCounts"),
            "gmbOrderLinkStores": sum(1 for store in stores if store.get("gmbOrderLinks")),
        },
        "metadataNotePresent": bool(summary.get("source", {}).get("googleMapsListRecheck")),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
