from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from playwright.async_api import async_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))

from human_gmb_order_recheck import (  # noqa: E402
    DELIVERY_TEXTS,
    PICKUP_TEXTS,
    human_pause,
    is_order_panel_text,
    read_mode,
    wait_for_panel_text,
)
from strict_gmb_blue_button_audit import (  # noqa: E402
    STORES_PATH,
    apply_result,
    clear_gmb_claims,
    is_google_bot_check,
    write_outputs,
)


def target_stores(stores: list[dict], args: argparse.Namespace) -> list[dict]:
    if args.ids:
        ids = set(args.ids)
        return [store for store in stores if store.get("storeId") in ids]
    if args.target == "pickup":
        return [store for store in stores if store.get("gmbPickupProviders")]
    if args.target == "confirmed":
        return [store for store in stores if store.get("gmbOrderingStatus") == "confirmed"]
    return stores


async def recheck_store(context, store: dict) -> dict:
    page = await context.new_page()
    target_url = store.get("gmbOrderPanelUrl") or store.get("gmbUrl") or ""
    result = {
        "status": "button_confirmed_provider_pending",
        "panelUrl": target_url,
        "pickupProviders": [],
        "deliveryProviders": [],
        "buttonDetected": False,
        "checkMethod": "stored_panel_mode_recheck",
        "attemptCount": 1,
        "maxAttempts": 1,
        "notes": "Stored Google Order panel was re-opened and mode availability was checked.",
    }
    try:
        if not target_url:
            result["status"] = "gmb_not_found"
            result["notes"] = "No GMB or Google Order panel URL was available."
            clear_gmb_claims(store)
            return apply_result(store, result)

        await page.goto(target_url, wait_until="domcontentloaded", timeout=45_000)
        await human_pause(page, 1200, 2400)
        text = await wait_for_panel_text(page, timeout_ms=7000)

        if is_google_bot_check(page.url, text):
            result["status"] = "unavailable_or_blocked"
            result["notes"] = "Google blocked the stored panel mode re-check."
            return store

        if not is_order_panel_text(page.url, text):
            result["status"] = "button_confirmed_provider_pending"
            result["notes"] = "Stored panel URL opened, but the Google Order provider panel was not readable."
            clear_gmb_claims(store)
            return apply_result(store, result)

        result["buttonDetected"] = True
        result["panelUrl"] = page.url
        result["pickupProviders"] = await read_mode(page, PICKUP_TEXTS)
        result["deliveryProviders"] = await read_mode(page, DELIVERY_TEXTS)

        if result["pickupProviders"] or result["deliveryProviders"]:
            result["status"] = "confirmed"
            result["notes"] = "Stored Google Order panel re-check read visible, clickable providers by mode."
        else:
            result["status"] = "button_confirmed_provider_pending"
            result["notes"] = "Google Order panel opened, but no visible provider rows were readable."

        clear_gmb_claims(store)
        return apply_result(store, result)
    except Exception as exc:
        result["status"] = "unavailable_or_blocked"
        result["notes"] = f"Stored panel mode re-check failed: {type(exc).__name__}."
        return store
    finally:
        await page.close()


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", choices=["pickup", "confirmed", "all"], default="pickup")
    parser.add_argument("--ids", nargs="*", default=[])
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    payload = json.loads(STORES_PATH.read_text(encoding="utf-8"))
    stores = payload["stores"]
    targets = target_stores(stores, args)
    if args.limit:
        targets = targets[: args.limit]

    profile_dir = STORES_PATH.parent / ".gmb-human-profile"
    profile_dir.mkdir(exist_ok=True)

    updated: dict[str, dict] = {}
    async with async_playwright() as playwright:
        context = await playwright.chromium.launch_persistent_context(
            str(profile_dir),
            headless=True,
            locale="zh-TW",
            timezone_id="Asia/Taipei",
            viewport={"width": 1365, "height": 920},
            args=["--disable-blink-features=AutomationControlled", "--lang=zh-TW"],
        )
        for index, store in enumerate(targets, start=1):
            checked = await recheck_store(context, dict(store))
            updated[checked["storeId"]] = checked
            payload["stores"] = [updated.get(item["storeId"], item) for item in stores]
            summary = write_outputs(payload)
            print(
                json.dumps(
                    {
                        "index": index,
                        "total": len(targets),
                        "storeId": checked.get("storeId"),
                        "storeName": checked.get("storeName"),
                        "status": checked.get("gmbOrderingStatus"),
                        "pickup": checked.get("gmbPickupProviders", []),
                        "delivery": checked.get("gmbDeliveryProviders", []),
                        "gmbPickupStores": summary.get("gmbPickupOrderingSystemCount"),
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )
            await asyncio.sleep(1.2)
        await context.close()

    payload["stores"] = [updated.get(store["storeId"], store) for store in stores]
    summary = write_outputs(payload)
    print(
        json.dumps(
            {
                "officialStoreCount": summary["officialStoreCount"],
                "gmbOrderingSystemCount": summary["gmbOrderingSystemCount"],
                "gmbCoverageGapCount": summary["gmbCoverageGapCount"],
                "gmbOrderingStatusCounts": summary["gmbOrderingStatusCounts"],
                "gmbPickupOrderingSystemCount": summary.get("gmbPickupOrderingSystemCount"),
                "gmbDeliveryOrderingSystemCount": summary.get("gmbDeliveryOrderingSystemCount"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
