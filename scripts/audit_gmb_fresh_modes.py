
import argparse
import json
import random
import sys
import urllib.parse
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from audit_gmb_modes import parse_modes, update_store, recompute

DATA_DIR = ROOT / "data" / "truedan"
STORES_PATH = DATA_DIR / "stores.json"
SUMMARY_PATH = DATA_DIR / "summary.json"
AUDIT_PATH = DATA_DIR / "gmb_maps_audit.json"
MODE_AUDIT_PATH = DATA_DIR / "gmb_mode_audit.json"
BRAND = "\u73cd\u716e\u4e39"
ONLINE_ORDER = "\u7dda\u4e0a\u9ede\u9910"
NOW = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def load(path): return json.loads(path.read_text(encoding="utf-8"))
def save(path, data): path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
def esc_print(v): print(str(v).encode("unicode_escape").decode("ascii", errors="ignore"), flush=True)
def maps_url(store): return "https://www.google.com/maps/search/" + urllib.parse.quote(f"{BRAND} {store['storeName']} {store['address']}")
def norm(v): return ''.join(str(v or '').split())

def fresh_panel_url(page, store):
    url = maps_url(store)
    page.goto(url, wait_until="domcontentloaded", timeout=35000)
    page.wait_for_timeout(4500 + random.randint(0, 1200))
    text = page.locator("body").inner_text(timeout=8000)
    name_match = norm(store["storeName"]) in norm(text) or norm(BRAND + store["storeName"]) in norm(text)
    href = page.evaluate("""() => { const el = Array.from(document.querySelectorAll('a[href*=searchviewer]')).find(a => (a.innerText||'').includes('????') || (a.href||'').includes('searchviewer')); return el ? el.href : ''; }""")
    return {"mapsSearchUrl": url, "gmbUrl": page.url, "title": page.title(), "nameMatch": name_match, "hasOnlineOrderText": ONLINE_ORDER in text, "panelUrl": href}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", type=int, default=0)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--only-missing-mode", action="store_true")
    ap.add_argument("--headless", action="store_true")
    args = ap.parse_args()
    stores = load(STORES_PATH)
    summary = load(SUMMARY_PATH)
    maps_audit = {x["storeId"]: x for x in load(AUDIT_PATH)} if AUDIT_PATH.exists() else {}
    mode_audit = {x["storeId"]: x for x in load(MODE_AUDIT_PATH)} if MODE_AUDIT_PATH.exists() else {}
    targets = stores[args.start: args.start + args.limit if args.limit else None]
    if args.only_missing_mode:
        targets = [s for s in targets if s.get("gmbOrderingStatus") in ["confirmed", "button_confirmed_provider_pending"] and not (s.get("gmbPickupProviders") or s.get("gmbDeliveryProviders"))]
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=args.headless)
        page = browser.new_page(locale="zh-TW", timezone_id="Asia/Taipei", viewport={"width": 1100, "height": 900})
        for idx, store in enumerate(targets, 1):
            info = fresh_panel_url(page, store)
            if not info["nameMatch"]:
                store["gmbStatus"] = "not_found"
                store["gmbOrderingStatus"] = "not_found"
                maps_audit[store["storeId"]] = {"storeId": store["storeId"], **info, "gmbStatus": "not_found", "gmbOrderingStatus": "not_found", "checkedAt": NOW}
                esc_print(f"{idx}/{len(targets)} {store['storeId']} not_found")
                continue
            store["gmbStatus"] = "confirmed"
            store.setdefault("sourceCoverage", {})["gmbFound"] = True
            store.setdefault("sourceCoverage", {})["googleFound"] = True
            store["gmbUrl"] = info["gmbUrl"]
            if not info["panelUrl"]:
                store["gmbOrderingStatus"] = "no_gmb_order_button" if not info["hasOnlineOrderText"] else "button_confirmed_provider_pending"
                maps_audit[store["storeId"]] = {"storeId": store["storeId"], **info, "gmbStatus": "confirmed", "gmbOrderingStatus": store["gmbOrderingStatus"], "checkedAt": NOW}
                esc_print(f"{idx}/{len(targets)} {store['storeId']} {store['gmbOrderingStatus']} no_panel")
                continue
            maps_audit[store["storeId"]] = {"storeId": store["storeId"], "storeName": store["storeName"], "address": store["address"], **info, "gmbStatus": "confirmed", "gmbOrderingStatus": "panel_found", "checkedAt": NOW}
            result = parse_modes(page, info["panelUrl"])
            result["storeId"] = store["storeId"]
            result["storeName"] = store["storeName"]
            providers = update_store(store, result)
            if not providers:
                store["gmbOrderingStatus"] = "button_confirmed_provider_pending"
            mode_audit[store["storeId"]] = result
            esc_print(f"{idx}/{len(targets)} {store['storeId']} pickup={store.get('gmbPickupProviders', [])} delivery={store.get('gmbDeliveryProviders', [])} providers={providers}")
            save(AUDIT_PATH, list(maps_audit.values()))
            save(MODE_AUDIT_PATH, list(mode_audit.values()))
            save(STORES_PATH, stores)
            recompute(summary, stores)
            save(SUMMARY_PATH, summary)
            page.wait_for_timeout(1200 + random.randint(0, 900))
        browser.close()
    save(AUDIT_PATH, list(maps_audit.values()))
    save(MODE_AUDIT_PATH, list(mode_audit.values()))
    save(STORES_PATH, stores)
    recompute(summary, stores)
    save(SUMMARY_PATH, summary)

if __name__ == "__main__":
    main()
