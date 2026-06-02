from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
from pathlib import Path


os.environ.setdefault(
    "BRAND_ANALYSIS_REPORT_ROOT",
    str(Path(__file__).resolve().parents[1] / "milksha"),
)

from playwright.async_api import async_playwright  # noqa: E402

from build_milksha_analysis import DATA, build_summary, write_csv  # noqa: E402
from human_gmb_order_recheck import audit_store  # noqa: E402


STORES_PATH = DATA / "stores.json"
SUMMARY_PATH = DATA / "summary.json"


def write_outputs(payload: dict) -> dict:
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
    return summary


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--attempts", type=int, default=1)
    parser.add_argument("--per-store-timeout", type=int, default=120)
    parser.add_argument("--fresh-profile", action="store_true")
    parser.add_argument("--headed", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--status", default="unavailable_or_blocked")
    parser.add_argument("--ids", nargs="*", default=[])
    parser.add_argument("--mobile", action="store_true")
    args = parser.parse_args()

    payload = json.loads(STORES_PATH.read_text(encoding="utf-8"))
    stores = payload["stores"]
    if args.ids:
        id_set = set(args.ids)
        targets = [store for store in stores if store.get("storeId") in id_set]
    else:
        statuses = {item.strip() for item in args.status.split(",") if item.strip()}
        targets = [store for store in stores if store.get("gmbOrderingStatus") in statuses]
    if args.limit:
        targets = targets[: args.limit]

    profile_dir = DATA / ".gmb-milksha-recheck-profile"
    profile_dir.mkdir(exist_ok=True)
    if args.mobile:
        context_options = {
            "locale": "zh-TW",
            "timezone_id": "Asia/Taipei",
            "viewport": {"width": 430, "height": 932},
            "is_mobile": True,
            "has_touch": True,
            "user_agent": (
                "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) "
                "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1"
            ),
        }
    else:
        context_options = {
            "locale": "zh-TW",
            "timezone_id": "Asia/Taipei",
            "viewport": {"width": 1365, "height": 920},
            "user_agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
            ),
        }
    launch_options = {
        "headless": not args.headed,
        "args": ["--disable-blink-features=AutomationControlled", "--lang=zh-TW"],
    }

    async with async_playwright() as playwright:
        browser = None
        if args.fresh_profile:
            browser = await playwright.chromium.launch(**launch_options)
            context = await browser.new_context(**context_options)
        else:
            context = await playwright.chromium.launch_persistent_context(
                str(profile_dir),
                **launch_options,
                **context_options,
            )
        try:
            updated_by_id = {}
            for index, store in enumerate(targets, start=1):
                print(f"{index}/{len(targets)} rechecking {store.get('storeId')} {store.get('storeName')}", flush=True)
                try:
                    updated = await asyncio.wait_for(
                        audit_store(context, dict(store), attempts=args.attempts),
                        timeout=args.per_store_timeout,
                    )
                except asyncio.TimeoutError:
                    updated = dict(store)
                    updated["gmbOrderingStatus"] = "unavailable_or_blocked"
                    updated["hasGmbOrderingSystem"] = False
                    updated["manualReviewReason"] = (
                        f"Milksha blocked re-check timed out after {args.per_store_timeout}s; "
                        "kept as coverage gap."
                    )
                updated_by_id[updated["storeId"]] = updated
                payload["stores"] = [updated_by_id.get(item["storeId"], item) for item in stores]
                summary = write_outputs(payload)
                print(
                    json.dumps(
                        {
                            "storeId": updated.get("storeId"),
                            "status": updated.get("gmbOrderingStatus"),
                            "hasGmb": updated.get("hasGmbOrderingSystem"),
                            "pickup": updated.get("gmbPickupProviders"),
                            "delivery": updated.get("gmbDeliveryProviders"),
                            "remainingBlocked": summary["gmbOrderingStatusCounts"].get("unavailable_or_blocked", 0),
                        },
                        ensure_ascii=False,
                    ),
                    flush=True,
                )
                await asyncio.sleep(random.uniform(2.0, 5.0))
        finally:
            await context.close()
            if browser:
                await browser.close()

    payload["stores"] = [updated_by_id.get(store["storeId"], store) for store in stores]
    summary = write_outputs(payload)
    print(
        json.dumps(
            {
                "officialStoreCount": summary["officialStoreCount"],
                "gmbOrderingSystemCount": summary["gmbOrderingSystemCount"],
                "gmbCoverageGapCount": summary["gmbCoverageGapCount"],
                "gmbSystemCounts": summary["gmbSystemCounts"],
                "gmbOrderingStatusCounts": summary["gmbOrderingStatusCounts"],
            },
            ensure_ascii=False,
            indent=2,
        ),
        flush=True,
    )


if __name__ == "__main__":
    asyncio.run(main())
