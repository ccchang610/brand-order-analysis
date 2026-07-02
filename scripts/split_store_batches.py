from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


def load_stores(path: Path) -> list[dict]:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if isinstance(payload, dict) and "stores" in payload:
        return payload["stores"]
    if isinstance(payload, list):
        return payload
    raise ValueError("Expected a stores array or an object with a stores key")


def parse_csv(value: str) -> set[str]:
    return {item.strip() for item in value.split(",") if item.strip()}


def selected(stores: list[dict], statuses: set[str], ids: set[str], include_confirmed: bool) -> list[dict]:
    rows = stores
    if ids:
        rows = [store for store in rows if store.get("storeId") in ids]
    if statuses:
        rows = [store for store in rows if store.get("gmbOrderingStatus") in statuses or store.get("gmbStatus") in statuses]
    if not include_confirmed:
        rows = [
            store
            for store in rows
            if store.get("gmbOrderingStatus") != "confirmed"
            or not store.get("hasGmbOrderingSystem")
            or store.get("manualReviewReason")
        ]
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Split canonical stores.json into subagent batch files.")
    parser.add_argument("--stores", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--brand", required=True)
    parser.add_argument("--brand-slug", required=True)
    parser.add_argument("--task-type", default="gmb_identity")
    parser.add_argument("--batch-size", type=int, default=25)
    parser.add_argument("--status", default="", help="Comma-separated gmbOrderingStatus/gmbStatus values to include.")
    parser.add_argument("--ids", default="", help="Comma-separated storeId values to include.")
    parser.add_argument("--include-confirmed", action="store_true")
    args = parser.parse_args()

    if args.batch_size < 1:
        raise ValueError("--batch-size must be positive")
    stores = selected(load_stores(args.stores), parse_csv(args.status), parse_csv(args.ids), args.include_confirmed)
    args.out.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    written = []
    for index in range(0, len(stores), args.batch_size):
        batch_no = index // args.batch_size + 1
        batch = stores[index : index + args.batch_size]
        batch_id = f"{args.brand_slug}-{args.task_type}-{batch_no:03d}"
        payload = {
            "batchId": batch_id,
            "brand": args.brand,
            "brandSlug": args.brand_slug,
            "taskType": args.task_type,
            "createdAt": now,
            "sourceRules": {
                "gmbProviderRule": "sourceType:gmb only when provider row is visible inside opened Google Order panel",
                "doNotInferPlatformAbsenceFromGoogleOrder": True,
                "googleOrderConcurrency": 1,
            },
            "stores": batch,
        }
        out_path = args.out / f"{batch_id}.json"
        out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        written.append(str(out_path))
    print(json.dumps({"storeCount": len(stores), "batchCount": len(written), "files": written}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
