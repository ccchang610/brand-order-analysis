from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from finalize_truedan_report import rebuild_summary


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "truedan"
STORES_PATH = DATA / "stores.json"
SUMMARY_PATH = DATA / "summary.json"
MAPS_AUDIT_PATH = DATA / "gmb_maps_audit.json"
MODE_AUDIT_PATH = DATA / "gmb_mode_audit.json"
FULL_AUDIT_PATH = DATA / "chrome_gmb_full_order_audit.json"

NOW = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
NO_BUTTON_STATUSES = {"online_text_without_button", "no_gmb_order_button"}


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def save(path: Path, payload) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def canonical_provider(row: dict) -> str:
    provider = (row.get("provider") or "").strip()
    href = (row.get("href") or "").lower()
    label = (row.get("label") or "").lower()
    blob = f"{provider.lower()} {href} {label}"
    if "ubereats" in blob or "uber eats" in blob:
        return "Uber Eats"
    if "foodpanda" in blob or "food-ordering" in blob:
        return "foodpanda"
    if "ocard" in blob:
        return "Ocard"
    if "nidin" in blob or "order.nidin.shop" in blob:
        return "Nidin"
    if "quickclick" in blob or "quickclick" in href:
        return "QuickClick"
    if provider:
        return provider
    host = urlparse(row.get("href") or "").netloc
    return host or "Unknown"


def provider_modes(audit_row: dict) -> tuple[dict[str, set[str]], list[dict], list[str]]:
    by_provider: dict[str, set[str]] = {}
    links: list[dict] = []
    confirmed_modes: list[str] = []
    checked_at = audit_row.get("checkedAt") or NOW

    for mode, payload in (audit_row.get("modes") or {}).items():
        if mode not in {"pickup", "delivery"}:
            continue
        providers = payload.get("providers") or []
        mode_was_read = bool(payload.get("clicked"))
        if not mode_was_read:
            continue
        if mode not in confirmed_modes:
            confirmed_modes.append(mode)
        panel_url = payload.get("url") or audit_row.get("searchUrl") or audit_row.get("landingUrl") or ""
        for row in providers:
            system = canonical_provider(row)
            if not system or system == "Unknown":
                continue
            href = row.get("href") or panel_url
            by_provider.setdefault(system, set()).add(mode)
            links.append(
                {
                    "platform": system,
                    "kind": "provider_row",
                    "sourceType": "gmb_order_panel",
                    "orderMode": [mode],
                    "label": row.get("label") or system,
                    "href": href,
                    "panelUrl": panel_url,
                    "observedAt": checked_at,
                    "confidence": "confirmed",
                }
            )
    return by_provider, dedupe_links(links), confirmed_modes


def dedupe_links(links: list[dict]) -> list[dict]:
    seen: set[tuple] = set()
    out: list[dict] = []
    for link in links:
        key = (
            link.get("platform"),
            tuple(link.get("orderMode") or []),
            link.get("href"),
            link.get("panelUrl"),
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(link)
    return out


def panel_url_for(audit_row: dict) -> str:
    for mode in ("pickup", "delivery"):
        payload = (audit_row.get("modes") or {}).get(mode) or {}
        if payload.get("clicked") and payload.get("url"):
            return payload["url"]
    return audit_row.get("searchUrl") or audit_row.get("landingUrl") or ""


def gmb_claims(audit_row: dict, by_provider: dict[str, set[str]]) -> list[dict]:
    panel_url = panel_url_for(audit_row)
    return [
        {
            "system": system,
            "sourceType": "gmb",
            "orderMode": sorted(modes),
            "evidenceUrl": panel_url,
            "confidence": "confirmed",
            "evidenceNote": "Visible provider row inside the scoped Google Order panel; mode set only after the panel tab was active/clicked.",
        }
        for system, modes in sorted(by_provider.items())
    ]


def clear_strict_gmb(store: dict) -> None:
    store["orderingSystems"] = [
        claim for claim in store.get("orderingSystems", []) if claim.get("sourceType") != "gmb"
    ]
    store["gmbOrderLinks"] = [
        link for link in store.get("gmbOrderLinks", []) if link.get("sourceType") != "gmb_order_panel"
    ]
    store["gmbPickupProviders"] = []
    store["gmbDeliveryProviders"] = []
    store["gmbOrderModesConfirmed"] = []


def apply_confirmed(store: dict, audit_row: dict, maps_audit: dict, mode_audit: dict) -> None:
    by_provider, links, confirmed_modes = provider_modes(audit_row)
    clear_strict_gmb(store)
    store["orderingSystems"].extend(gmb_claims(audit_row, by_provider))
    store["gmbOrderLinks"].extend(links)
    store["gmbPickupProviders"] = sorted(provider for provider, modes in by_provider.items() if "pickup" in modes)
    store["gmbDeliveryProviders"] = sorted(provider for provider, modes in by_provider.items() if "delivery" in modes)
    store["gmbOrderModesConfirmed"] = confirmed_modes
    store["gmbStatus"] = "confirmed"
    store["gmbOrderingStatus"] = "confirmed" if by_provider else "panel_without_known_provider"
    store["hasGmbOrderingSystem"] = bool(by_provider)
    store["hasAnyOrderingSystem"] = bool(store.get("orderingSystems"))
    store["gmbOrderPanelUrl"] = panel_url_for(audit_row)
    store["manualReviewReason"] = "" if by_provider else "Google Order panel opened, but no known provider row was visible in a scoped panel read."
    store.setdefault("sourceCoverage", {}).update(
        {"officialListed": True, "gmbFound": True, "googleFound": True, "thirdPartyFound": True}
    )
    store["gmbSignals"] = {
        "buttonDetected": True,
        "providersParsed": bool(by_provider),
        "attemptCount": 1,
        "maxAttempts": 1,
        "attemptHistory": [
            {
                "attempt": 1,
                "target": "chrome_google_search_business_card",
                "status": store["gmbOrderingStatus"],
                "buttonDetected": True,
                "providersParsed": bool(by_provider),
                "title": audit_row.get("title"),
                "notes": [
                    "Scoped Chrome re-run opened the Google Order flow.",
                    "Provider rows were parsed only inside the visible Google Order panel.",
                    "Pickup/delivery were counted only when the inner mode control was active or clicked.",
                ],
            }
        ],
        "panelUrl": store["gmbOrderPanelUrl"],
        "checkedAt": audit_row.get("checkedAt") or NOW,
        "checkMethod": "chrome_google_order_panel_scoped_full_rerun",
        "matchQuality": "named_gmb_profile_or_google_business_card",
        "notes": "Full Truedan rerun with scoped Google Order panel parsing and mode-aware provider rows.",
    }

    maps_audit[store["storeId"]] = {
        "storeId": store["storeId"],
        "storeName": store.get("storeName"),
        "address": store.get("address"),
        "checkedAt": audit_row.get("checkedAt") or NOW,
        "gmbStatus": "confirmed",
        "gmbOrderingStatus": store["gmbOrderingStatus"],
        "gmbUrl": store.get("gmbUrl") or audit_row.get("searchUrl"),
        "panelUrl": store["gmbOrderPanelUrl"],
        "buttonDetected": True,
        "providers": sorted(by_provider),
        "pickupProviders": store["gmbPickupProviders"],
        "deliveryProviders": store["gmbDeliveryProviders"],
        "notes": ["Scoped Chrome Google Order panel read; background Google links were not counted."],
    }
    mode_audit[store["storeId"]] = {
        "storeId": store["storeId"],
        "storeName": store.get("storeName"),
        "panelUrl": store["gmbOrderPanelUrl"],
        "checkedAt": audit_row.get("checkedAt") or NOW,
        "modes": {
            mode: {
                "clicked": bool((audit_row.get("modes") or {}).get(mode, {}).get("clicked")),
                "providers": [
                    {
                        "provider": canonical_provider(row),
                        "label": row.get("label") or canonical_provider(row),
                        "href": row.get("href") or "",
                    }
                    for row in ((audit_row.get("modes") or {}).get(mode, {}).get("providers") or [])
                    if bool((audit_row.get("modes") or {}).get(mode, {}).get("clicked"))
                ],
            }
            for mode in ("pickup", "delivery")
        },
        "notes": ["Mode-aware provider read from the visible Google Order panel only."],
    }


def apply_no_button(store: dict, audit_row: dict, maps_audit: dict, mode_audit: dict) -> None:
    clear_strict_gmb(store)
    store["gmbStatus"] = "confirmed"
    store["gmbOrderingStatus"] = "no_gmb_order_button"
    store["hasGmbOrderingSystem"] = False
    store["hasAnyOrderingSystem"] = bool(store.get("orderingSystems"))
    store["gmbOrderPanelUrl"] = ""
    store.setdefault("sourceCoverage", {}).update(
        {"officialListed": True, "gmbFound": True, "googleFound": True, "thirdPartyFound": True}
    )
    store["manualReviewReason"] = (
        "Scoped Chrome re-check found the matching Google result/profile context but no clickable blue Google Order entry. "
        "Existing direct platform links are kept as all-source evidence only."
    )
    store["gmbSignals"] = {
        "buttonDetected": False,
        "providersParsed": False,
        "attemptCount": 1,
        "maxAttempts": 1,
        "attemptHistory": [
            {
                "attempt": 1,
                "target": "chrome_google_search_business_card",
                "status": "no_gmb_order_button",
                "buttonDetected": False,
                "providersParsed": False,
                "title": audit_row.get("title"),
                "notes": [
                    "Online-order text or platform links may appear elsewhere on Google.",
                    "No provider was counted because no active Google Order panel could be opened in the scoped check.",
                ],
            }
        ],
        "panelUrl": "",
        "checkedAt": audit_row.get("checkedAt") or NOW,
        "checkMethod": "chrome_google_order_panel_scoped_full_rerun",
        "matchQuality": "named_result_context_without_current_order_button",
        "storeContext": "hospital_or_venue_counter",
        "notes": "No current blue Google Order entry was visible after bounded re-check; all-source platform evidence remains separate.",
    }
    maps_audit[store["storeId"]] = {
        "storeId": store["storeId"],
        "storeName": store.get("storeName"),
        "address": store.get("address"),
        "checkedAt": audit_row.get("checkedAt") or NOW,
        "gmbStatus": "confirmed",
        "gmbOrderingStatus": "no_gmb_order_button",
        "gmbUrl": store.get("gmbUrl") or audit_row.get("searchUrl"),
        "panelUrl": "",
        "buttonDetected": False,
        "providers": [],
        "pickupProviders": [],
        "deliveryProviders": [],
        "notes": ["Scoped Chrome re-check found no clickable blue Google Order entry."],
    }
    mode_audit[store["storeId"]] = {
        "storeId": store["storeId"],
        "storeName": store.get("storeName"),
        "panelUrl": "",
        "checkedAt": audit_row.get("checkedAt") or NOW,
        "modes": {
            "pickup": {"clicked": False, "providers": []},
            "delivery": {"clicked": False, "providers": []},
        },
        "notes": ["No current Google Order panel was opened; stale searchviewer evidence was cleared."],
    }


def validate(stores: list[dict], audit_rows: list[dict]) -> dict:
    total = len(stores)
    status_counts = Counter(row.get("status") for row in audit_rows)
    gmb_confirmed = sum(
        1 for store in stores if any(claim.get("sourceType") == "gmb" for claim in store.get("orderingSystems", []))
    )
    return {
        "stores": total,
        "auditRows": len(audit_rows),
        "auditStatusCounts": dict(status_counts),
        "gmbProviderStores": gmb_confirmed,
        "gmbOrderingStatusCounts": dict(Counter(store.get("gmbOrderingStatus") for store in stores)),
    }


def main() -> None:
    stores = load(STORES_PATH)
    audit_rows = load(FULL_AUDIT_PATH)
    maps_audit = {item["storeId"]: item for item in load(MAPS_AUDIT_PATH)}
    mode_audit = {item["storeId"]: item for item in load(MODE_AUDIT_PATH)}
    stores_by_id = {store["storeId"]: store for store in stores}

    for audit_row in audit_rows:
        store = stores_by_id[audit_row["storeId"]]
        if audit_row.get("status") == "confirmed":
            apply_confirmed(store, audit_row, maps_audit, mode_audit)
        elif audit_row.get("status") in NO_BUTTON_STATUSES:
            apply_no_button(store, audit_row, maps_audit, mode_audit)

    summary = rebuild_summary(stores)
    summary["generatedAt"] = NOW
    notes = [note for note in summary.get("notes", []) if isinstance(note, str)]
    notes.append(
        "Full Chrome GMB rerun applied: provider rows are scoped to the Google Order panel and pickup/delivery are counted only after the inner mode control is active or clicked."
    )
    summary["notes"] = list(dict.fromkeys(notes))

    save(STORES_PATH, stores)
    save(SUMMARY_PATH, summary)
    save(MAPS_AUDIT_PATH, list(maps_audit.values()))
    save(MODE_AUDIT_PATH, list(mode_audit.values()))
    print(json.dumps(validate(stores, audit_rows), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
