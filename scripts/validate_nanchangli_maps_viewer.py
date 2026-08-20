#!/usr/bin/env python3
"""Validate the merged 南廠里 strict Google Order dataset and local bundle."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "nanchangli" / "data"


def main() -> None:
    stores = json.loads((DATA / "stores.json").read_text(encoding="utf-8"))["stores"]
    summary = json.loads((DATA / "summary.json").read_text(encoding="utf-8"))

    assert len(stores) == 30
    assert len({store["storeId"] for store in stores}) == 30
    statuses = Counter(store["gmbOrderingStatus"] for store in stores)
    assert statuses == {"confirmed": 9, "no_gmb_order_button": 21}, statuses

    provider_stores: Counter[str] = Counter()
    for store in stores:
        gmb_claims = [claim for claim in store.get("orderingSystems", []) if claim.get("sourceType") == "gmb"]
        if store["gmbOrderingStatus"] == "confirmed":
            assert store.get("gmbOrderPanelUrl", "").startswith("https://www.google.com/searchviewer/")
            assert store.get("gmbOrderLinks")
            assert store.get("hasGmbOrderingSystem") is True
            confirmed_modes = set(store.get("gmbOrderModesConfirmed", []))
            assert confirmed_modes and confirmed_modes <= {"pickup", "delivery"}
            mode_states = store["gmbSignals"]["modeReadStates"]
            assert mode_states["pickupProviders"] in {"confirmed", "confirmed_none_visible", "not_available"}
            assert mode_states["deliveryProviders"] in {"confirmed", "confirmed_none_visible", "not_available"}
            assert gmb_claims
            for claim in gmb_claims:
                assert claim["orderMode"] in (["pickup"], ["delivery"])
                assert claim["orderMode"][0] in confirmed_modes
                assert claim.get("evidenceUrl") == store["gmbOrderPanelUrl"]
                assert claim.get("providerUrl", "").startswith("http")
            for provider in set(store["gmbPickupProviders"] + store["gmbDeliveryProviders"]):
                provider_stores[provider] += 1
        else:
            assert store.get("gmbStatus") == "confirmed"
            assert not store.get("gmbOrderPanelUrl")
            assert not store.get("gmbOrderLinks")
            assert not store.get("gmbPickupProviders")
            assert not store.get("gmbDeliveryProviders")
            assert not gmb_claims
            assert store.get("hasGmbOrderingSystem") is False

    afeng = next(store for store in stores if store["storeId"] == "nanchangli-023")
    assert set(afeng["gmbPickupProviders"]) == {"foodpanda", "Uber Eats"}
    assert set(afeng["gmbDeliveryProviders"]) == {"foodpanda", "Uber Eats"}
    assert provider_stores == {"Uber Eats": 8, "foodpanda": 6}, provider_stores
    assert summary["officialStoreCount"] == 30
    assert summary["gmbOrderingStatusCounts"] == dict(statuses)

    data_js = (ROOT / "nanchangli" / "data-inline.js").read_text(encoding="utf-8")
    index_html = (ROOT / "nanchangli" / "index.html").read_text(encoding="utf-8")
    assert "window.DAMING_DATA" in data_js
    assert '"confirmed": 9' in data_js
    assert "data-inline.js" in index_html

    print(
        json.dumps(
            {
                "stores": len(stores),
                "statuses": statuses,
                "gmbProviderStores": provider_stores,
                "afeng": {
                    "pickup": afeng["gmbPickupProviders"],
                    "delivery": afeng["gmbDeliveryProviders"],
                },
                "htmlBundle": "ok",
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
