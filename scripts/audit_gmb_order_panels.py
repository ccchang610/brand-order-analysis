from __future__ import annotations

import asyncio
import json
import os
from collections import Counter
from datetime import date
from pathlib import Path

from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright

REPO_ROOT = Path(__file__).resolve().parents[1]
ROOT = Path(os.environ.get("BRAND_ANALYSIS_REPORT_ROOT", REPO_ROOT / "daming")).resolve()
DATA = ROOT / "data"
STORES_PATH = DATA / "stores.json"
SUMMARY_PATH = DATA / "summary.json"

PROVIDERS = {
    "foodpanda": "foodpanda",
    "ubereats": "Uber Eats",
    "uber eats": "Uber Eats",
    "UberEats": "Uber Eats",
    "Nidin": "Nidin",
    "QuickClick": "QuickClick",
    "quickclick": "QuickClick",
    "快一點": "QuickClick",
    "order.quickclick.cc": "QuickClick",
}


def provider_names(text: str) -> list[str]:
    found = []
    lower = text.lower()
    for needle, name in PROVIDERS.items():
        if needle.lower() in lower and name not in found:
            found.append(name)
    return found


async def panel_text_for_mode(page, mode: str) -> str:
    if await page.get_by_text(mode, exact=True).count():
        try:
            await page.get_by_text(mode, exact=True).first.click(timeout=3000)
            await page.wait_for_timeout(1200)
        except Exception:
            pass
    return await page.locator("body").inner_text(timeout=8000)


async def audit_store(context, store: dict, index: int, total: int) -> dict:
    if not store.get("gmbUrl"):
        store["gmbOrderingStatus"] = "not_found"
        store["manualReviewReason"] = "No GMB URL in official store listing."
        return store

    page = await context.new_page()
    result = {
        "status": "unavailable_or_blocked",
        "panelUrl": "",
        "pickupProviders": [],
        "deliveryProviders": [],
        "notes": "",
    }
    try:
        await page.goto(store["gmbUrl"], wait_until="domcontentloaded", timeout=45_000)
        await page.wait_for_timeout(3500)
        order_links = await page.locator("a[href*='searchviewer']").evaluate_all(
            """els => els.map(e => ({ href: e.href, text: (e.innerText || e.textContent || '').trim(), aria: e.getAttribute('aria-label') || '' }))"""
        )
        # Direct links on Google results can be official/store links, not Google Order
        # provider rows. Google Order providers must come from the opened order panel.
        direct_order_links = []
        for link in direct_order_links:
            link_text = f"{link.get('text', '')} {link.get('aria', '')}"
            href = link.get("href", "")
            if "searchviewer" in href:
                continue
            providers = provider_names(f"{href} {link_text}")
            if not providers:
                continue
            if "外帶" in link_text or "自取" in link_text:
                result["pickupProviders"].extend(provider for provider in providers if provider not in result["pickupProviders"])
                result["panelUrl"] = result["panelUrl"] or href
            elif "外送" in link_text or "運送" in link_text:
                result["deliveryProviders"].extend(provider for provider in providers if provider not in result["deliveryProviders"])
                result["panelUrl"] = result["panelUrl"] or href
            else:
                result["pickupProviders"].extend(provider for provider in providers if provider == "Nidin" and provider not in result["pickupProviders"])
                result["deliveryProviders"].extend(provider for provider in providers if provider != "Nidin" and provider not in result["deliveryProviders"])

        if not order_links:
            if result["pickupProviders"] or result["deliveryProviders"]:
                result["status"] = "confirmed"
                result["notes"] = "GMB direct order buttons were read by mode; no searchviewer panel was needed."
            else:
                result["status"] = "needs_manual_review"
                result["notes"] = "No readable GMB searchviewer or direct order-button provider was found; Google may show order buttons only in interactive sessions."
            return apply_result(store, result)

        panel_url = order_links[0]["href"]
        result["panelUrl"] = panel_url
        await page.goto(panel_url, wait_until="domcontentloaded", timeout=45_000)
        await page.wait_for_timeout(2500)
        body_text = await page.locator("body").inner_text(timeout=8000)

        if "自取" in body_text:
            pickup_text = await panel_text_for_mode(page, "自取")
            # If Google keeps the delivery provider list visible because pickup is disabled,
            # keep pickup empty unless the selected text explicitly names pickup/self-pickup providers.
            if "選擇下單對象" in pickup_text and "運送" not in pickup_text[: max(80, pickup_text.find("選擇下單對象"))]:
                result["pickupProviders"] = provider_names(pickup_text)

        if "運送" in body_text or "外送" in body_text:
            delivery_text = await panel_text_for_mode(page, "運送") if "運送" in body_text else body_text
            result["deliveryProviders"] = provider_names(delivery_text)

        if result["pickupProviders"] or result["deliveryProviders"]:
            result["status"] = "confirmed"
            result["notes"] = "Google Order panel was opened and providers were read by mode."
        else:
            result["status"] = "needs_manual_review"
            result["notes"] = "Google Order panel opened but no known provider names were parsed."
        return apply_result(store, result)
    except Exception as exc:
        result["status"] = "unavailable_or_blocked"
        result["notes"] = f"GMB audit failed: {type(exc).__name__}"
        return apply_result(store, result)
    finally:
        await page.close()
        print(f"{index}/{total} {store.get('storeName')} {result['status']} delivery={result['deliveryProviders']} pickup={result['pickupProviders']}")


def apply_result(store: dict, result: dict) -> dict:
    existing = list(store.get("orderingSystems", []))
    panel_url = result.get("panelUrl") or store.get("gmbUrl") or ""

    for provider in result.get("pickupProviders", []):
        existing.append(
            {
                "system": provider,
                "sourceType": "gmb",
                "orderMode": ["pickup"],
                "evidenceUrl": panel_url,
                "label": "Google Order 自取",
                "confidence": "confirmed",
            }
        )
    for provider in result.get("deliveryProviders", []):
        existing.append(
            {
                "system": provider,
                "sourceType": "gmb",
                "orderMode": ["delivery"],
                "evidenceUrl": panel_url,
                "label": "GMB 運送",
                "confidence": "confirmed",
            }
        )

    deduped = []
    seen = set()
    for claim in existing:
        key = (claim.get("system"), claim.get("sourceType"), tuple(claim.get("orderMode", [])), claim.get("evidenceUrl"))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(claim)

    store["orderingSystems"] = deduped
    store["hasAnyOrderingSystem"] = bool(deduped)
    store["hasGmbOrderingSystem"] = any(claim.get("sourceType") == "gmb" for claim in deduped)
    store["gmbOrderingStatus"] = result["status"]
    store["gmbOrderPanelUrl"] = panel_url
    store["gmbPickupProviders"] = result.get("pickupProviders", [])
    store["gmbDeliveryProviders"] = result.get("deliveryProviders", [])
    store["manualReviewReason"] = result.get("notes", "")
    return store


def count_systems(stores: list[dict], *, gmb_only: bool = False, mode: str | None = None) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for store in stores:
        systems = set()
        for claim in store.get("orderingSystems", []):
            if gmb_only and claim.get("sourceType") != "gmb":
                continue
            if mode and mode not in claim.get("orderMode", []):
                continue
            if claim.get("confidence") in {"confirmed", "partial"}:
                systems.add(claim["system"])
        for system in systems:
            counts[system] += 1
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))


def rebuild_summary(stores: list[dict]) -> dict:
    total = len(stores)
    city_counts: Counter[str] = Counter()
    region_counts: Counter[str] = Counter()
    source_coverage_counts: Counter[str] = Counter()
    gmb_status_counts: Counter[str] = Counter()
    for store in stores:
        city_counts[store.get("city") or "未分類"] += 1
        region_counts[store.get("regionGroup") or "未分類"] += 1
        gmb_status_counts[store.get("gmbStatus") or "unknown"] += 1
        for key, enabled in store.get("sourceCoverage", {}).items():
            if enabled:
                source_coverage_counts[key] += 1

    taiwan_cities = [
        "台北市",
        "新北市",
        "基隆市",
        "桃園市",
        "新竹市",
        "新竹縣",
        "苗栗縣",
        "台中市",
        "彰化縣",
        "南投縣",
        "雲林縣",
        "嘉義市",
        "嘉義縣",
        "台南市",
        "高雄市",
        "屏東縣",
        "宜蘭縣",
        "花蓮縣",
        "台東縣",
        "澎湖縣",
        "金門縣",
        "連江縣",
    ]
    region_names = ["北部", "中部", "南部", "東部", "離島"]
    summary = {
        "brand": stores[0].get("brand", "") if stores else "",
        "market": stores[0].get("market", "") if stores else "",
        "generatedAt": date.today().isoformat(),
        "officialStoreCount": total,
        "gmbFoundCount": sum(1 for store in stores if store.get("sourceCoverage", {}).get("gmbFound")),
        "gmbMissingCount": sum(1 for store in stores if not store.get("sourceCoverage", {}).get("gmbFound")),
        "googleFoundCount": sum(1 for store in stores if store.get("sourceCoverage", {}).get("googleFound")),
        "thirdPartyFoundCount": sum(1 for store in stores if store.get("sourceCoverage", {}).get("thirdPartyFound")),
        "cityCounts": {city: city_counts.get(city, 0) for city in taiwan_cities},
        "regionCounts": {region: region_counts.get(region, 0) for region in region_names},
        "gmbStatusCounts": dict(gmb_status_counts),
        "sourceCoverageCounts": dict(source_coverage_counts),
        "source": {
            "officialStoreList": stores[0].get("officialSourceUrl", "") if stores else "",
            "officialWebsite": "https://www.damingtea.com.tw/",
            "notes": "Official store page provides the store population, embedded Google/Maps links, Nidin order links, and delivery platform links. Google Order panels were opened separately to read pickup/delivery providers.",
        },
    }

    def rate(count: int) -> float:
        return round(count / total, 4) if total else 0

    all_counts = count_systems(stores)
    all_pickup_counts = count_systems(stores, mode="pickup")
    all_delivery_counts = count_systems(stores, mode="delivery")
    gmb_counts = count_systems(stores, gmb_only=True)
    gmb_pickup_counts = count_systems(stores, gmb_only=True, mode="pickup")
    gmb_delivery_counts = count_systems(stores, gmb_only=True, mode="delivery")
    systems = sorted(set(all_counts) | set(gmb_counts))

    summary.update(
        {
            "anyOrderingSystemCount": sum(1 for store in stores if store.get("hasAnyOrderingSystem")),
            "gmbOrderingSystemCount": sum(1 for store in stores if store.get("hasGmbOrderingSystem")),
            "gmbCoverageGapCount": sum(1 for store in stores if not store.get("hasGmbOrderingSystem")),
            "unknownOrderingSystemCount": sum(1 for store in stores if not store.get("hasAnyOrderingSystem")),
            "allSourceSystemCounts": all_counts,
            "allSourcePickupSystemCounts": all_pickup_counts,
            "allSourceDeliverySystemCounts": all_delivery_counts,
            "gmbSystemCounts": gmb_counts,
            "gmbPickupSystemCounts": gmb_pickup_counts,
            "gmbDeliverySystemCounts": gmb_delivery_counts,
            "allSourceSystemAdoptionRates": {system: rate(count) for system, count in all_counts.items()},
            "gmbSystemAdoptionRates": {system: rate(count) for system, count in gmb_counts.items()},
            "gmbOrderingStatusCounts": dict(Counter(store.get("gmbOrderingStatus") for store in stores)),
        }
    )
    summary["anyOrderingSystemAdoptionRate"] = rate(summary["anyOrderingSystemCount"])
    summary["gmbOrderingSystemAdoptionRate"] = rate(summary["gmbOrderingSystemCount"])
    summary["systemComparison"] = [
        {
            "system": system,
            "allSourceStoreCount": all_counts.get(system, 0),
            "allSourceAdoptionRate": rate(all_counts.get(system, 0)),
            "gmbStoreCount": gmb_counts.get(system, 0),
            "gmbAdoptionRate": rate(gmb_counts.get(system, 0)),
            "countGap": all_counts.get(system, 0) - gmb_counts.get(system, 0),
            "percentagePointGap": round(rate(all_counts.get(system, 0)) - rate(gmb_counts.get(system, 0)), 4),
        }
        for system in systems
    ]
    summary["notes"] = [
        "Adoption rates use official store count as denominator.",
        "All-source ordering systems come from official page order/delivery links, resolved platform links, and Google Order provider evidence.",
        "Google Order pickup and delivery providers are separated from the Google online-order panel where readable.",
    ]
    return summary


async def main(limit: int | None = None, concurrency: int = 3) -> None:
    payload = json.loads(STORES_PATH.read_text(encoding="utf-8"))
    stores = payload["stores"]
    targets = stores[:limit] if limit else stores
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        context = await browser.new_context(locale="zh-TW", viewport={"width": 1280, "height": 900})
        updated_by_id = {}
        semaphore = asyncio.Semaphore(concurrency)

        async def run_one(index: int, store: dict) -> None:
            async with semaphore:
                updated = await audit_store(context, store, index, len(targets))
                updated_by_id[updated["storeId"]] = updated
                await asyncio.sleep(0.5)

        await asyncio.gather(*(run_one(index, store) for index, store in enumerate(targets, start=1)))
        await browser.close()

    stores = [updated_by_id.get(store["storeId"], store) for store in stores]
    payload["stores"] = stores
    STORES_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    SUMMARY_PATH.write_text(json.dumps(rebuild_summary(stores), ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    asyncio.run(main())
