from __future__ import annotations

import asyncio
import argparse
import json
import os
from pathlib import Path


os.environ.setdefault(
    "BRAND_ANALYSIS_REPORT_ROOT",
    str(Path(__file__).resolve().parents[1] / "milksha"),
)

from strict_gmb_blue_button_audit import audit_store  # noqa: E402
from playwright.async_api import async_playwright  # noqa: E402

from build_milksha_analysis import DATA, build_summary, write_csv  # noqa: E402


STORES_PATH = DATA / "stores.json"
SUMMARY_PATH = DATA / "summary.json"


async def main(limit: int | None = None, concurrency: int = 1) -> None:
    payload = json.loads(STORES_PATH.read_text(encoding="utf-8"))
    stores = payload["stores"]
    targets = stores[:limit] if limit else stores

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        context = await browser.new_context(locale="zh-TW", timezone_id="Asia/Taipei", viewport={"width": 1360, "height": 980})
        updated_by_id = {}
        semaphore = asyncio.Semaphore(concurrency)

        async def run_one(index: int, store: dict) -> None:
            async with semaphore:
                updated = await audit_store(context, dict(store), index, len(targets))
                updated_by_id[updated["storeId"]] = updated
                await asyncio.sleep(1.2)

        await asyncio.gather(*(run_one(index, store) for index, store in enumerate(targets, start=1)))
        await browser.close()

    stores = [updated_by_id.get(store["storeId"], store) for store in stores]
    payload["stores"] = stores

    previous_summary = json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))
    source = previous_summary.get("source") or {}
    summary = build_summary(
        stores,
        int(source.get("nidinApiStoreCount") or 0),
        int(source.get("nidinMatchedOfficialStoreCount") or 0),
    )

    STORES_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    SUMMARY_PATH.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_csv(stores)

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
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--concurrency", type=int, default=1)
    args = parser.parse_args()
    asyncio.run(main(limit=args.limit, concurrency=args.concurrency))
