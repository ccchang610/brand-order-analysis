from __future__ import annotations

import argparse
import json
from pathlib import Path


REQUIRED = {"batchId", "workerId", "taskType", "storeId", "status", "evidence", "checkedAt"}
TASK_TYPES = {"platform_direct", "gmb_identity", "gmb_order_panel", "unresolved_recheck", "qa_sample"}
STATUSES = {"confirmed", "partially_confirmed", "not_found", "blocked", "ambiguous", "needs_manual_review"}


def load_known_store_ids(path: Path | None) -> set[str]:
    if not path:
        return set()
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    stores = payload["stores"] if isinstance(payload, dict) and "stores" in payload else payload
    return {store.get("storeId") for store in stores if store.get("storeId")}


def iter_jsonl(path: Path):
    for line_no, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            yield line_no, json.loads(line)
        except json.JSONDecodeError as exc:
            yield line_no, {"__error__": f"invalid json: {exc}"}


def validate_row(row: dict, known_store_ids: set[str]) -> list[str]:
    errors = []
    if "__error__" in row:
        return [row["__error__"]]
    missing = sorted(REQUIRED - row.keys())
    if missing:
        errors.append(f"missing required fields: {', '.join(missing)}")
    if row.get("taskType") and row["taskType"] not in TASK_TYPES:
        errors.append(f"unsupported taskType: {row['taskType']}")
    if row.get("status") and row["status"] not in STATUSES:
        errors.append(f"unsupported status: {row['status']}")
    if known_store_ids and row.get("storeId") not in known_store_ids:
        errors.append(f"unknown storeId: {row.get('storeId')}")
    if not isinstance(row.get("evidence", []), list):
        errors.append("evidence must be an array")
    for index, evidence in enumerate(row.get("evidence", []), start=1):
        if not isinstance(evidence, dict):
            errors.append(f"evidence[{index}] must be an object")
            continue
        if evidence.get("sourceType") == "gmb" and not evidence.get("notes"):
            errors.append(f"evidence[{index}] sourceType:gmb requires notes proving it came from the opened Google Order panel")
    return errors


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate subagent worker JSONL output before merge.")
    parser.add_argument("jsonl", nargs="+", type=Path)
    parser.add_argument("--stores", type=Path)
    args = parser.parse_args()

    known_store_ids = load_known_store_ids(args.stores)
    checked = 0
    errors = []
    for path in args.jsonl:
        for line_no, row in iter_jsonl(path):
            checked += 1
            for error in validate_row(row, known_store_ids):
                errors.append({"file": str(path), "line": line_no, "storeId": row.get("storeId"), "error": error})
    print(json.dumps({"checkedRows": checked, "errorCount": len(errors), "errors": errors}, ensure_ascii=False, indent=2))
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
