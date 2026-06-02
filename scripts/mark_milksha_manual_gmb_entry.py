from __future__ import annotations

import json
from datetime import date

from build_milksha_analysis import DATA, build_summary, write_csv


STORES_PATH = DATA / "stores.json"
SUMMARY_PATH = DATA / "summary.json"


MANUAL_ENTRIES = {
    "milksha-037": {
        "status": "button_confirmed_provider_pending",
        "reason": "User-provided screenshot confirms a visible Google Business Profile online-order entry for Milksha 嘉義民族店; provider rows were not visible in the screenshot and automated mobile re-check was blocked.",
        "panelUrl": "https://maps.app.goo.gl/6MdEji3KNVARVBqs7",
    }
}


def main() -> None:
    payload = json.loads(STORES_PATH.read_text(encoding="utf-8"))
    for store in payload["stores"]:
        entry = MANUAL_ENTRIES.get(store.get("storeId"))
        if not entry:
            continue
        store["gmbOrderingStatus"] = entry["status"]
        store["hasGmbOrderingSystem"] = True
        store["gmbOrderModesConfirmed"] = ["unknown"]
        store["manualReviewReason"] = entry["reason"]
        store["gmbSignals"] = {
            **(store.get("gmbSignals") or {}),
            "buttonDetected": True,
            "providersParsed": False,
            "panelUrl": entry["panelUrl"],
            "checkedAt": date.today().isoformat(),
            "checkMethod": "user_screenshot_manual_gmb_entry_confirmation",
            "notes": entry["reason"],
        }

    previous = json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))
    source = previous.get("source") or {}
    summary = build_summary(
        payload["stores"],
        int(source.get("nidinApiStoreCount") or 0),
        int(source.get("nidinMatchedOfficialStoreCount") or 0),
    )
    STORES_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    SUMMARY_PATH.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_csv(payload["stores"])
    print(json.dumps(summary["gmbOrderingStatusCounts"], ensure_ascii=False))


if __name__ == "__main__":
    main()
