from __future__ import annotations

import asyncio
import json
import re
from collections import defaultdict
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

from playwright.async_api import async_playwright

from build_pbcafe_analysis import rebuild_summary, write_outputs


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "pbcafe" / "data"
CHECKED_AT = date.today().isoformat()

MODE_LABELS = [("自取", "pickup"), ("運送", "delivery")]


def link_platform(text: str, href: str) -> str:
    blob = f"{text} {href}".lower()
    if "instagram.com" in blob or "instagram" in blob:
        return "Instagram"
    if "lin.ee" in blob or "line.me" in blob or re.search(r"\bline\b", blob):
        return "LINE"
    if "ubereats" in blob or "uber eats" in blob:
        return "Uber Eats"
    if "foodpanda" in blob:
        return "foodpanda"
    if "nidin" in blob:
        return "Nidin"
    if "quickclick" in blob:
        return "QuickClick"
    if "pbcafe.com.tw" in blob:
        return "Official"
    host = urlparse(href).netloc.replace("www.", "") if href else ""
    return host or (text[:40] if text else "Unknown")


def link_kind(platform: str) -> str:
    if platform in {"Uber Eats", "foodpanda", "Nidin", "QuickClick"}:
        return "marketplace"
    if platform in {"LINE", "Instagram"}:
        return "social_order_link"
    if platform == "Official":
        return "official"
    return "order_panel_link"


def stable_href_key(href: str) -> str:
    if not href:
        return ""
    parsed = urlparse(href)
    return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"


def normalize_link(raw: dict, store: dict, mode: str, panel_url: str) -> dict | None:
    text = re.sub(r"\s+", " ", raw.get("text") or raw.get("aria") or "").strip()
    href = (raw.get("href") or "").strip()
    if not text and not href:
        return None
    blob = f"{text} {href}".lower()
    if not any(
        needle in blob
        for needle in [
            "instagram",
            "line",
            "lin.ee",
            "ubereats",
            "uber eats",
            "foodpanda",
            "nidin",
            "quickclick",
            "pbcafe.com.tw",
        ]
    ):
        return None
    platform = link_platform(text, href)
    return {
        "platform": platform,
        "kind": link_kind(platform),
        "sourceType": "gmb_order_panel",
        "orderMode": [mode],
        "label": text or platform,
        "href": href,
        "panelUrl": panel_url,
        "observedAt": CHECKED_AT,
        "confidence": "confirmed",
        "note": "Visible after opening the Google Order button flow.",
        "storeId": store["storeId"],
        "storeName": store["storeName"],
    }


def merge_links(existing: list[dict], incoming: list[dict]) -> list[dict]:
    merged: dict[tuple[str, str, str], dict] = {}
    for link in [*existing, *incoming]:
        modes = link.get("orderMode") or ["unknown"]
        key = (link.get("platform", ""), stable_href_key(link.get("href", "")) or link.get("label", ""))
        if key not in merged:
            merged[key] = {**link, "orderMode": sorted(set(modes))}
        else:
            merged[key]["orderMode"] = sorted(set(merged[key].get("orderMode", [])) | set(modes))
    return sorted(merged.values(), key=lambda item: (item.get("platform", ""), item.get("label", ""), item.get("href", "")))


async def click_mode(page, label: str) -> bool:
    return await page.evaluate(
        """
        (label) => {
            const candidates = [...document.querySelectorAll('button,[role="button"],a')];
            const el = candidates.find((node) => (node.innerText || node.textContent || '').trim() === label);
            if (!el) return false;
            el.click();
            return true;
        }
        """,
        label,
    )


async def visible_order_links(page) -> list[dict]:
    return await page.evaluate(
        """
        () => [...document.querySelectorAll('a,button,[role="button"]')]
            .map((el) => {
                const rect = el.getBoundingClientRect();
                return {
                    text: (el.innerText || el.textContent || '').replace(/\\s+/g, ' ').trim(),
                    href: el.href || '',
                    aria: el.getAttribute('aria-label') || '',
                    visible: rect.width > 4 && rect.height > 4 && rect.bottom > 0 && rect.top < innerHeight
                };
            })
            .filter((item) => item.visible && (item.text || item.href || item.aria))
        """
    )


async def audit_store(page, store: dict) -> list[dict]:
    panel_url = store.get("gmbOrderPanelUrl") or store.get("gmbSignals", {}).get("panelUrl") or ""
    if not panel_url:
        return []
    await page.goto(panel_url, wait_until="domcontentloaded", timeout=60000)
    await page.wait_for_timeout(3500)
    found: list[dict] = []
    for label, mode in MODE_LABELS:
        await click_mode(page, label)
        await page.wait_for_timeout(1200)
        raw_links = await visible_order_links(page)
        for raw in raw_links:
            link = normalize_link(raw, store, mode, panel_url)
            if link:
                found.append(link)
    return found


async def main() -> None:
    payload = json.loads((DATA / "stores.json").read_text(encoding="utf-8"))
    stores = payload["stores"]
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(locale="zh-TW", timezone_id="Asia/Taipei")
        for store in stores:
            if store.get("gmbOrderingStatus") != "confirmed":
                store["gmbOrderLinks"] = []
                continue
            try:
                links = await audit_store(page, store)
            except Exception as exc:
                links = []
                store.setdefault("gmbSignals", {})["orderLinksAuditError"] = str(exc)
            store["gmbOrderLinks"] = merge_links([], links)
            store.setdefault("gmbSignals", {})["orderLinksAuditedAt"] = CHECKED_AT
            print(
                json.dumps(
                    {
                        "storeId": store["storeId"],
                        "storeName": store["storeName"],
                        "links": [
                            {
                                "platform": link["platform"],
                                "mode": link["orderMode"],
                                "label": link["label"],
                                "href": link["href"],
                            }
                            for link in store["gmbOrderLinks"]
                        ],
                    },
                    ensure_ascii=False,
                )
            )
        await browser.close()

    summary = rebuild_summary(stores)
    summary.setdefault("source", {})["googleMapsListRecheck"] = (
        "2026-06-17 Google Maps list recheck: current matching list-card online-order "
        "entries are authoritative for entry coverage; when a current matched card has "
        "no online-order entry, stale stored searchviewer/gmbOrderPanelUrl values are "
        "ignored and stale GMB provider claims are cleared."
    )
    summary["source"]["googleOrderLinksAudit"] = (
        "Google Order panel links are recorded separately in store.gmbOrderLinks. "
        "They include links visible after opening the Google Order button flow and "
        "do not alter Google Order provider counts unless they are provider rows."
    )
    stale_note = summary["source"]["googleMapsListRecheck"]
    if stale_note not in summary.setdefault("notes", []):
        summary["notes"].append(stale_note)
    note = (
        "Visible links inside the opened Google Order flow are preserved in gmbOrderLinks, "
        "including social ordering links such as Instagram or LINE when present."
    )
    if note not in summary.setdefault("notes", []):
        summary["notes"].append(note)
    write_outputs(stores, summary)

    link_counts = defaultdict(int)
    for store in stores:
        for link in store.get("gmbOrderLinks", []):
            link_counts[link["platform"]] += 1
    print(json.dumps({"stores": len(stores), "gmbOrderLinkCounts": dict(sorted(link_counts.items()))}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
