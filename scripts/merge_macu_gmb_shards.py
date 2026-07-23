
from __future__ import annotations

import argparse
import json
from pathlib import Path
from collections import Counter

ROOT = Path(__file__).resolve().parents[1]
STORES_PATH = ROOT / "macu" / "data" / "stores.json"

STRONG = {"confirmed"}
ENTRY = {"confirmed", "button_confirmed_provider_pending"}

def has_gmb_provider(store: dict) -> bool:
    return any(c.get("sourceType") == "gmb" and c.get("system") for c in store.get("orderingSystems", []))

def merge_store(current: dict, incoming: dict) -> tuple[dict, str]:
    current_status = current.get("gmbOrderingStatus")
    incoming_status = incoming.get("gmbOrderingStatus")
    if incoming_status in STRONG:
        return incoming, "accepted_confirmed"
    if current_status in STRONG and has_gmb_provider(current):
        merged = dict(current)
        signals = dict(current.get("gmbSignals") or {})
        signals["pickupSupplementWeakerResult"] = {
            "status": incoming_status,
            "modeReadStates": (incoming.get("gmbSignals") or {}).get("modeReadStates", {}),
            "checkedAt": (incoming.get("gmbSignals") or {}).get("checkedAt"),
            "note": "Supplement result was weaker than existing confirmed provider evidence; providers preserved.",
        }
        merged["gmbSignals"] = signals
        return merged, "preserved_existing_confirmed"
    if incoming_status in ENTRY:
        return incoming, "accepted_entry"
    return current, "ignored_weaker"

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("shard_dir", nargs="?", default="macu/work/pickup-rerun")
    args = parser.parse_args()
    shard_dir = ROOT / args.shard_dir
    payload = json.loads(STORES_PATH.read_text(encoding="utf-8"))
    by_id = {s["storeId"]: s for s in payload["stores"]}
    stats = Counter()
    rows = 0
    for path in sorted(shard_dir.glob("shard-*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            rows += 1
            record = json.loads(line)
            incoming = record.get("store") or record
            store_id = incoming.get("storeId") or record.get("storeId")
            if store_id not in by_id:
                stats["unknown_store"] += 1
                continue
            merged, action = merge_store(by_id[store_id], incoming)
            by_id[store_id] = merged
            stats[action] += 1
    payload["stores"] = [by_id[s["storeId"]] for s in payload["stores"]]
    STORES_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"rows": rows, "stats": dict(stats)}, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
