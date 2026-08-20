#!/usr/bin/env python3
"""Merge the strict Google Maps -> Search Viewer recheck into 南廠里 data.

Only current, visible provider rows inside the opened order viewer become GMB
provider claims. Pickup and delivery are kept as separate evidence dimensions.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STORES_PATH = ROOT / "nanchangli" / "data" / "stores.json"
RESULTS_PATH = ROOT / "nanchangli" / "work" / "maps-viewer-rerun.jsonl"
CHECKED_AT = "2026-08-19"


def read_results() -> dict[str, dict]:
    results: dict[str, dict] = {}
    for line in RESULTS_PATH.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            results[row["storeId"]] = row
    return results


def provider_claim(platform: str, mode: str, viewer: dict) -> dict:
    row = next(
        (
            link
            for link in viewer.get("links", [])
            if link.get("platform") == platform and mode in link.get("orderMode", [])
        ),
        {},
    )
    return {
        "system": platform,
        "sourceType": "gmb",
        "orderMode": [mode],
        "evidenceUrl": viewer.get("panelUrl", ""),
        "providerUrl": row.get("href", ""),
        "label": f"Google Order {'pickup' if mode == 'pickup' else 'delivery'} visible provider row",
        "confidence": "confirmed",
        "checkedAt": CHECKED_AT,
    }


def merge_store(store: dict, result: dict) -> None:
    status = result.get("status", "unavailable")
    viewer = result.get("viewer") or {}
    attempts = result.get("attempts") or []

    # Preserve official-site and direct-platform evidence. This audit replaces
    # only the previous Google Order / GMB interpretation.
    non_gmb_claims = [
        claim for claim in store.get("orderingSystems", []) if claim.get("sourceType") != "gmb"
    ]

    store["checkedAt"] = CHECKED_AT
    store["gmbUrl"] = result.get("gmbUrl") or store.get("gmbUrl", "")
    store.setdefault("sourceCoverage", {})["googleFound"] = status != "unavailable"
    store["sourceCoverage"]["gmbFound"] = result.get("gmbStatus") == "confirmed"

    common_signals = {
        "attemptCount": len(attempts),
        "maxAttempts": 2,
        "attemptHistory": attempts,
        "checkedAt": CHECKED_AT,
        "checkMethod": "google_maps_named_profile_searchviewer_visible_rows",
    }

    if status == "confirmed":
        pickup = list(dict.fromkeys(viewer.get("pickup", [])))
        delivery = list(dict.fromkeys(viewer.get("delivery", [])))
        raw_mode_states = viewer.get("modeStates", {})

        def merged_mode_state(mode: str, providers: list[str]) -> str:
            raw_state = raw_mode_states.get(mode)
            if raw_state == "active":
                return "confirmed" if providers else "confirmed_none_visible"
            if raw_state == "active_no_provider":
                return "confirmed_none_visible"
            return "not_available" if raw_state in {"inactive", "disabled"} else "unknown"

        claims = [provider_claim(p, "pickup", viewer) for p in pickup]
        claims += [provider_claim(p, "delivery", viewer) for p in delivery]
        store["orderingSystems"] = non_gmb_claims + claims
        store["gmbStatus"] = "confirmed"
        store["gmbOrderingStatus"] = "confirmed"
        store["gmbOrderPanelUrl"] = viewer.get("panelUrl", "")
        store["gmbOrderLinks"] = viewer.get("links", [])
        store["gmbPickupProviders"] = pickup
        store["gmbDeliveryProviders"] = delivery
        store["gmbOrderModesConfirmed"] = [
            mode for mode in ("pickup", "delivery") if viewer.get("modeStates", {}).get(mode) == "active"
        ]
        store["hasGmbOrderingSystem"] = bool(pickup or delivery)
        store["manualReviewReason"] = ""
        store["gmbSignals"] = {
            **common_signals,
            "buttonDetected": True,
            "buttonText": result.get("blueButtonText", ""),
            "providersParsed": bool(pickup or delivery),
            "modeReadStates": {
                "pickupProviders": merged_mode_state("pickup", pickup),
                "deliveryProviders": merged_mode_state("delivery", delivery),
            },
            "panelUrl": viewer.get("panelUrl", ""),
            "unresolvedReason": "",
            "notes": "Opened the Google Maps online-order entry, then separately opened pickup and delivery and recorded only visible provider rows.",
            "providerRowTexts": {
                "pickup": viewer.get("pickupRows", []),
                "delivery": viewer.get("deliveryRows", []),
            },
        }
        return

    if status == "no_gmb_order_button":
        store["orderingSystems"] = non_gmb_claims
        store["gmbStatus"] = "confirmed"
        store["gmbOrderingStatus"] = "no_gmb_order_button"
        store["gmbOrderPanelUrl"] = ""
        store["gmbOrderLinks"] = []
        store["gmbPickupProviders"] = []
        store["gmbDeliveryProviders"] = []
        store["gmbOrderModesConfirmed"] = []
        store["hasGmbOrderingSystem"] = False
        store["manualReviewReason"] = ""
        store["gmbSignals"] = {
            **common_signals,
            "buttonDetected": False,
            "providersParsed": False,
            "modeReadStates": {"pickupProviders": "not_available", "deliveryProviders": "not_available"},
            "panelUrl": "",
            "unresolvedReason": "no_gmb_order_button",
            "notes": "Named Google Maps business profile was opened; no online-order entry was visible in either bounded attempt.",
            "providerRowTexts": {"pickup": [], "delivery": []},
        }
        return

    # A failed identity match is weaker than prior positive evidence, so do not
    # erase confirmed provider claims in this branch.
    store["gmbStatus"] = "not_found" if status == "no_gmb_profile_match" else store.get("gmbStatus", "unknown")
    store["gmbOrderingStatus"] = status
    store["manualReviewReason"] = "Current Google Maps rerun could not match the intended named profile."
    store["gmbSignals"] = {
        **common_signals,
        "buttonDetected": False,
        "providersParsed": False,
        "modeReadStates": {"pickupProviders": "unknown", "deliveryProviders": "unknown"},
        "panelUrl": "",
        "unresolvedReason": status,
        "notes": store["manualReviewReason"],
        "providerRowTexts": {"pickup": [], "delivery": []},
    }


def main() -> None:
    payload = json.loads(STORES_PATH.read_text(encoding="utf-8"))
    stores = payload["stores"]
    results = read_results()
    expected = {store["storeId"] for store in stores}
    missing = sorted(expected - set(results))
    extra = sorted(set(results) - expected)
    if missing or extra or len(results) != len(stores):
        raise SystemExit(f"result coverage mismatch: missing={missing}, extra={extra}, rows={len(results)}")

    for store in stores:
        merge_store(store, results[store["storeId"]])

    payload["stores"] = stores
    STORES_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    counts = Counter(result.get("status", "unknown") for result in results.values())
    provider_counts = Counter()
    for result in results.values():
        viewer = result.get("viewer") or {}
        for provider in set(viewer.get("pickup", []) + viewer.get("delivery", [])):
            provider_counts[provider] += 1
    print(json.dumps({"rows": len(results), "statuses": counts, "gmbProviderStores": provider_counts}, ensure_ascii=False))


if __name__ == "__main__":
    main()
