
import argparse
import json
import random
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "truedan"
STORES_PATH = DATA_DIR / "stores.json"
SUMMARY_PATH = DATA_DIR / "summary.json"
AUDIT_PATH = DATA_DIR / "gmb_maps_audit.json"
MODE_AUDIT_PATH = DATA_DIR / "gmb_mode_audit.json"
NOW = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
MODES = [("pickup", "\u81ea\u53d6"), ("delivery", "\u904b\u9001")]
PROVIDERS = {
    "Uber Eats": ["Uber Eats", "ubereats.com"],
    "foodpanda": ["foodpanda", "foodpanda.com.tw"],
    "Nidin": ["Nidin", "nidin", "nidin.shop", "order.nidin.shop"],
    "LINE": ["LINE", "line.me", "lin.ee", "liff.line.me"],
    "QuickClick": ["QuickClick", "quickclick", "\u5feb\u4e00\u9ede"],
}

def load(path):
    return json.loads(path.read_text(encoding="utf-8"))

def save(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def esc_print(value):
    print(str(value).encode("unicode_escape").decode("ascii", errors="ignore"), flush=True)

def provider_for(text, href):
    blob = f"{text} {href}".lower()
    for provider, needles in PROVIDERS.items():
        if any(needle.lower() in blob for needle in needles):
            return provider
    return ""

def visible_provider_links(page):
    links = page.evaluate("""() => Array.from(document.querySelectorAll('a')).map(a => ({text:(a.innerText||a.textContent||'').trim(), href:a.href || a.getAttribute('href') || ''})).filter(x => x.text || x.href)""")
    rows = []
    for item in links:
        provider = provider_for(item.get("text", ""), item.get("href", ""))
        if provider:
            rows.append({"provider": provider, "label": item.get("text", ""), "href": item.get("href", "")})
    # de-dupe per provider/href
    seen = set()
    out = []
    for row in rows:
        key = (row["provider"], row.get("href", ""))
        if key not in seen:
            seen.add(key)
            out.append(row)
    return out

def parse_modes(page, panel_url):
    result = {"panelUrl": panel_url, "checkedAt": NOW, "modes": {}, "notes": []}
    page.goto(panel_url, wait_until="domcontentloaded", timeout=35000)
    page.wait_for_timeout(4500 + random.randint(0, 1200))
    for mode_key, label in MODES:
        clicked = False
        try:
            loc = page.locator(f'[role=button]:has-text("{label}")').first
            if loc.count() > 0:
                loc.click(timeout=5000)
                clicked = True
                page.wait_for_timeout(2800 + random.randint(0, 1000))
        except Exception as exc:
            result["notes"].append(f"{mode_key} click failed: {type(exc).__name__}")
        providers = visible_provider_links(page)
        result["modes"][mode_key] = {"clicked": clicked, "providers": providers}
    return result

def update_store(store, mode_result):
    by_provider = {}
    gmb_links = []
    for mode, payload in mode_result["modes"].items():
        for row in payload.get("providers", []):
            provider = row["provider"]
            by_provider.setdefault(provider, set()).add(mode)
            gmb_links.append({
                "platform": provider,
                "kind": "provider_link",
                "sourceType": "gmb_order_panel",
                "orderMode": [mode],
                "label": row.get("label") or provider,
                "href": row.get("href", ""),
                "panelUrl": mode_result["panelUrl"],
                "observedAt": NOW,
                "confidence": "confirmed",
            })
    if not by_provider:
        return []
    existing = [o for o in store.get("orderingSystems", []) if o.get("sourceType") != "gmb"]
    for provider, modes in sorted(by_provider.items()):
        existing.append({
            "system": provider,
            "sourceType": "gmb",
            "orderMode": sorted(modes),
            "evidenceUrl": mode_result["panelUrl"],
            "confidence": "confirmed",
        })
    store["orderingSystems"] = existing
    store["gmbOrderLinks"] = [link for link in store.get("gmbOrderLinks", []) if link.get("sourceType") != "gmb_order_panel"] + gmb_links
    store["gmbPickupProviders"] = sorted([p for p, modes in by_provider.items() if "pickup" in modes])
    store["gmbDeliveryProviders"] = sorted([p for p, modes in by_provider.items() if "delivery" in modes])
    store["gmbOrderingStatus"] = "confirmed"
    store["hasGmbOrderingSystem"] = True
    store["hasAnyOrderingSystem"] = True
    store["manualReviewReason"] = ""
    if "gmbSignals" in store:
        store["gmbSignals"]["providersParsed"] = True
        store["gmbSignals"]["checkedAt"] = NOW
        store["gmbSignals"]["notes"] = "Mode-aware Google searchviewer pass parsed providers by pickup/delivery."
    return sorted(by_provider.keys())

def recompute(summary, stores):
    summary["generatedAt"] = NOW
    summary["gmbFoundCount"] = sum(1 for s in stores if s.get("sourceCoverage", {}).get("gmbFound"))
    summary["googleFoundCount"] = sum(1 for s in stores if s.get("sourceCoverage", {}).get("googleFound"))
    summary["anyOrderingSystemCount"] = sum(1 for s in stores if s.get("hasAnyOrderingSystem"))
    summary["gmbOrderingSystemCount"] = sum(1 for s in stores if s.get("hasGmbOrderingSystem"))
    denom = len(stores) or 1
    summary["anyOrderingSystemAdoptionRate"] = round(summary["anyOrderingSystemCount"] / denom, 4)
    summary["gmbOrderingSystemAdoptionRate"] = round(summary["gmbOrderingSystemCount"] / denom, 4)
    summary["gmbStatusCounts"] = dict(Counter(s.get("gmbStatus") for s in stores))
    summary["gmbOrderingStatusCounts"] = dict(Counter(s.get("gmbOrderingStatus") for s in stores))
    all_counts = Counter()
    gmb_counts = Counter()
    pickup_counts = Counter()
    delivery_counts = Counter()
    for s in stores:
        all_systems = {o.get("system") for o in s.get("orderingSystems", []) if o.get("system")}
        gmb_systems = {o.get("system") for o in s.get("orderingSystems", []) if o.get("sourceType") == "gmb" and o.get("system")}
        all_counts.update(all_systems)
        gmb_counts.update(gmb_systems)
        for o in s.get("orderingSystems", []):
            if o.get("sourceType") != "gmb":
                continue
            if "pickup" in o.get("orderMode", []):
                pickup_counts[o.get("system")] += 1
            if "delivery" in o.get("orderMode", []):
                delivery_counts[o.get("system")] += 1
    summary["allSourceSystemCounts"] = dict(all_counts)
    summary["gmbSystemCounts"] = dict(gmb_counts)
    summary["gmbOrderPickupOptionCounts"] = dict(pickup_counts)
    summary["gmbOrderDeliveryOptionCounts"] = dict(delivery_counts)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--only-pending", action="store_true")
    parser.add_argument("--headless", action="store_true")
    args = parser.parse_args()
    stores = load(STORES_PATH)
    summary = load(SUMMARY_PATH)
    audit = {item["storeId"]: item for item in load(AUDIT_PATH) if item.get("panelUrl")}
    mode_audit = {item["storeId"]: item for item in load(MODE_AUDIT_PATH)} if MODE_AUDIT_PATH.exists() else {}
    targets = stores[args.start: args.start + args.limit if args.limit else None]
    if args.only_pending:
        targets = [s for s in targets if s.get("gmbOrderingStatus") != "confirmed" or not s.get("gmbPickupProviders") and not s.get("gmbDeliveryProviders")]
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=args.headless)
        page = browser.new_page(locale="zh-TW", timezone_id="Asia/Taipei", viewport={"width": 1000, "height": 900})
        for idx, store in enumerate(targets, 1):
            panel_url = audit.get(store["storeId"], {}).get("panelUrl") or store.get("gmbOrderPanelUrl")
            if not panel_url:
                continue
            result = parse_modes(page, panel_url)
            result["storeId"] = store["storeId"]
            result["storeName"] = store["storeName"]
            providers = update_store(store, result)
            mode_audit[store["storeId"]] = result
            esc_print(f"{idx}/{len(targets)} {store['storeId']} pickup={store.get('gmbPickupProviders', [])} delivery={store.get('gmbDeliveryProviders', [])} providers={providers}")
            save(MODE_AUDIT_PATH, list(mode_audit.values()))
            save(STORES_PATH, stores)
            recompute(summary, stores)
            save(SUMMARY_PATH, summary)
            page.wait_for_timeout(1000 + random.randint(0, 800))
        browser.close()
    recompute(summary, stores)
    save(SUMMARY_PATH, summary)

if __name__ == "__main__":
    main()
