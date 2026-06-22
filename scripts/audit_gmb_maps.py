
import argparse
import json
import random
import re
import time
import urllib.parse
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "truedan"
STORES_PATH = DATA_DIR / "stores.json"
SUMMARY_PATH = DATA_DIR / "summary.json"
AUDIT_PATH = DATA_DIR / "gmb_maps_audit.json"
NOW = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
BRAND = "\u73cd\u716e\u4e39"
ONLINE_ORDER = "\u7dda\u4e0a\u9ede\u9910"
CLOSED_TERMS = ["\u6c38\u4e45\u505c\u696d", "\u5df2\u505c\u696d", "\u5df2\u6b47\u696d"]
BOT_TERMS = ["unusual traffic", "\u70ba\u4f55\u986f\u793a\u6b64\u9801", "Our systems have detected unusual traffic"]
ORDER_BUTTON_SELECTORS = [
    f'text={ONLINE_ORDER}',
    f'button:has-text("{ONLINE_ORDER}")',
    f'a:has-text("{ONLINE_ORDER}")',
    '[aria-label*="' + ONLINE_ORDER + '"]',
]
PROVIDERS = {
    "Uber Eats": ["Uber Eats", "ubereats.com"],
    "foodpanda": ["foodpanda", "foodpanda.com.tw"],
    "Nidin": ["Nidin", "nidin", "nidin.shop", "order.nidin.shop"],
    "LINE": ["LINE", "line.me", "lin.ee", "liff.line.me"],
    "QuickClick": ["QuickClick", "quickclick", "\u5feb\u4e00\u9ede"],
}

def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))

def save_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def esc_print(value):
    print(str(value).encode("unicode_escape").decode("ascii", errors="ignore"), flush=True)

def norm(value):
    return re.sub(r"\s+", "", value or "")

def maps_search_url(store):
    q = f"{BRAND} {store['storeName']} {store['address']}"
    return "https://www.google.com/maps/search/" + urllib.parse.quote(q)

def body_text(page):
    try:
        return page.locator("body").inner_text(timeout=8000)
    except Exception:
        return ""

def find_providers(text):
    found = []
    lower = text.lower()
    for provider, needles in PROVIDERS.items():
        for needle in needles:
            if needle.lower() in lower:
                found.append(provider)
                break
    return sorted(set(found))

def click_online_order(page):
    try:
        href = page.evaluate("""() => { const el = Array.from(document.querySelectorAll('a[href*=searchviewer]')).find(a => (a.innerText||'').includes('????') || (a.href||'').includes('searchviewer')); return el ? el.href : ''; }""")
        if href:
            page.goto(href, wait_until="domcontentloaded", timeout=35000)
            return True, "searchviewer href", href
    except Exception:
        pass
    for selector in ORDER_BUTTON_SELECTORS:
        try:
            loc = page.locator(selector).first
            if loc.count() > 0:
                href = loc.get_attribute("href") or ""
                if href and "searchviewer" in href:
                    page.goto(href, wait_until="domcontentloaded", timeout=35000)
                    return True, selector + " -> href", href
                loc.click(timeout=6000)
                return True, selector, page.url
        except Exception:
            continue
    return False, "", ""

def audit_store(page, store, index, total):
    url = maps_search_url(store)
    result = {
        "checkedAt": NOW,
        "storeId": store["storeId"],
        "storeName": store["storeName"],
        "address": store["address"],
        "mapsSearchUrl": url,
        "gmbStatus": "needs_manual_review",
        "gmbOrderingStatus": "needs_manual_review",
        "gmbUrl": "",
        "buttonDetected": False,
        "providers": [],
        "panelTextSample": "",
        "panelUrl": "",
        "title": "",
        "notes": [],
    }
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=35000)
        page.wait_for_timeout(4500 + random.randint(0, 1800))
        result["title"] = page.title()
        text = body_text(page)
        if any(term in text for term in BOT_TERMS):
            result["gmbStatus"] = "unavailable_or_blocked"
            result["gmbOrderingStatus"] = "unavailable_or_blocked"
            result["notes"].append("Google Maps displayed bot-check/unusual-traffic content.")
            return result
        name_match = norm(store["storeName"]) in norm(text) or norm(BRAND + store["storeName"]) in norm(text)
        address_key = norm(store["address"])[-10:]
        address_match = address_key and address_key in norm(text)
        if any(term in text for term in CLOSED_TERMS):
            result["gmbStatus"] = "closed_or_moved"
            result["gmbOrderingStatus"] = "closed_or_moved"
            result["notes"].append("Closed term visible in Google Maps text.")
            return result
        if name_match:
            result["gmbStatus"] = "confirmed"
            result["gmbUrl"] = page.url
        elif address_match:
            result["gmbStatus"] = "needs_manual_review"
            result["notes"].append("Address appears but named GMB match was not clearly confirmed.")
        else:
            result["gmbStatus"] = "not_found"
            result["gmbOrderingStatus"] = "not_found"
            result["notes"].append("No matching store name/address visible in Maps result text.")
            return result
        has_order_text = ONLINE_ORDER in text
        if not has_order_text:
            result["gmbOrderingStatus"] = "no_gmb_order_button"
            result["notes"].append("No visible online-order text in Google Maps profile text.")
            return result
        clicked, selector, panel_url = click_online_order(page)
        result["buttonDetected"] = True
        result["panelUrl"] = panel_url or page.url
        result["notes"].append("Visible online-order entry detected." + (f" Opened via {selector}." if clicked else " Open failed."))
        if not clicked:
            result["gmbOrderingStatus"] = "button_confirmed_provider_pending"
            return result
        page.wait_for_timeout(6500 + random.randint(0, 2500))
        after = body_text(page)
        result["panelTextSample"] = after[:1600]
        providers = find_providers(after)
        result["providers"] = providers
        if providers:
            result["gmbOrderingStatus"] = "confirmed"
        else:
            result["gmbOrderingStatus"] = "button_confirmed_provider_pending"
            result["notes"].append("Order entry opened, but provider rows were not safely parsed.")
        return result
    except PlaywrightTimeoutError as exc:
        result["gmbStatus"] = "unavailable_or_blocked"
        result["gmbOrderingStatus"] = "unavailable_or_blocked"
        result["notes"].append(f"Timeout: {str(exc)[:180]}")
        return result
    except Exception as exc:
        result["gmbStatus"] = "needs_manual_review"
        result["gmbOrderingStatus"] = "needs_manual_review"
        result["notes"].append(f"Error: {type(exc).__name__}: {str(exc)[:180]}")
        return result

def apply_result(store, result):
    store["gmbStatus"] = result["gmbStatus"]
    store["gmbOrderingStatus"] = result["gmbOrderingStatus"]
    store["gmbUrl"] = result.get("gmbUrl", "") or store.get("gmbUrl", "")
    store["sourceCoverage"]["googleFound"] = result["gmbStatus"] in ["confirmed", "closed_or_moved", "needs_manual_review"]
    store["sourceCoverage"]["gmbFound"] = result["gmbStatus"] == "confirmed"
    store["hasGmbOrderingSystem"] = result["gmbOrderingStatus"] in ["confirmed", "button_confirmed_provider_pending"]
    store["gmbSignals"] = {
        "buttonDetected": result["buttonDetected"],
        "providersParsed": bool(result["providers"]),
        "attemptCount": 1,
        "maxAttempts": 3,
        "attemptHistory": [{
            "attempt": 1,
            "target": "googleMapsSearch",
            "status": result["gmbOrderingStatus"],
            "buttonDetected": result["buttonDetected"],
            "providersParsed": bool(result["providers"]),
            "title": result.get("title", ""),
            "notes": result.get("notes", []),
        }],
        "panelUrl": result.get("panelUrl", ""),
        "checkedAt": result["checkedAt"],
        "checkMethod": "playwright_google_maps_search",
        "matchQuality": "named_gmb_profile" if result["gmbStatus"] == "confirmed" else result["gmbStatus"],
        "notes": "; ".join(result.get("notes", [])),
    }
    if result["providers"]:
        existing = {(item.get("system"), item.get("sourceType")) for item in store.get("orderingSystems", [])}
        for provider in result["providers"]:
            key = (provider, "gmb")
            if key not in existing:
                store.setdefault("orderingSystems", []).append({
                    "system": provider,
                    "sourceType": "gmb",
                    "orderMode": ["unknown"],
                    "evidenceUrl": result.get("panelUrl") or result.get("gmbUrl") or result["mapsSearchUrl"],
                    "confidence": "confirmed",
                })
        store["hasAnyOrderingSystem"] = True
    if result.get("panelUrl"):
        store["gmbOrderPanelUrl"] = result.get("panelUrl")
    if result["gmbOrderingStatus"] == "confirmed":
        store["manualReviewReason"] = ""
    elif result["gmbOrderingStatus"] == "button_confirmed_provider_pending":
        store["manualReviewReason"] = "Google Maps online-order entry was visible/opened, but provider rows were not safely parsed. Manual review needed."
    elif result["gmbOrderingStatus"] == "no_gmb_order_button":
        store["manualReviewReason"] = "Matching Google Maps profile was visible, but no online-order entry was found in this bounded pass."
    elif result["gmbOrderingStatus"] == "unavailable_or_blocked":
        store["manualReviewReason"] = "Google Maps/GMB check was blocked or timed out; this is a coverage gap, not non-adoption evidence."
    else:
        store["manualReviewReason"] = "; ".join(result.get("notes", []))

def recompute_summary(summary, stores):
    summary["generatedAt"] = NOW
    summary["gmbFoundCount"] = sum(1 for s in stores if s["sourceCoverage"].get("gmbFound"))
    summary["googleFoundCount"] = sum(1 for s in stores if s["sourceCoverage"].get("googleFound"))
    summary["thirdPartyFoundCount"] = sum(1 for s in stores if s["sourceCoverage"].get("thirdPartyFound"))
    summary["anyOrderingSystemCount"] = sum(1 for s in stores if s.get("hasAnyOrderingSystem"))
    summary["gmbOrderingSystemCount"] = sum(1 for s in stores if s.get("hasGmbOrderingSystem"))
    denom = len(stores) or 1
    summary["anyOrderingSystemAdoptionRate"] = round(summary["anyOrderingSystemCount"] / denom, 4)
    summary["gmbOrderingSystemAdoptionRate"] = round(summary["gmbOrderingSystemCount"] / denom, 4)
    summary["gmbStatusCounts"] = dict(Counter(s.get("gmbStatus") for s in stores))
    summary["gmbOrderingStatusCounts"] = dict(Counter(s.get("gmbOrderingStatus") for s in stores))
    summary["sourceCoverageCounts"] = {
        "officialListed": len(stores),
        "gmbFound": summary["gmbFoundCount"],
        "googleFound": summary["googleFoundCount"],
        "thirdPartyFound": summary["thirdPartyFoundCount"],
    }
    summary["gmbCoverageGapCount"] = sum(1 for s in stores if s.get("gmbOrderingStatus") not in ["confirmed", "button_confirmed_provider_pending"])
    system_counts = Counter()
    gmb_counts = Counter()
    for s in stores:
        systems = {item.get("system") for item in s.get("orderingSystems", []) if item.get("system")}
        gmb_systems = {item.get("system") for item in s.get("orderingSystems", []) if item.get("sourceType") == "gmb" and item.get("system")}
        system_counts.update(systems)
        gmb_counts.update(gmb_systems)
    summary["allSourceSystemCounts"] = dict(system_counts)
    summary["gmbSystemCounts"] = dict(gmb_counts)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--headless", action="store_true")
    args = parser.parse_args()
    stores = load_json(STORES_PATH)
    summary = load_json(SUMMARY_PATH)
    existing = load_json(AUDIT_PATH) if AUDIT_PATH.exists() else []
    audit_by_id = {item["storeId"]: item for item in existing if "storeId" in item}
    subset = stores[args.start: args.start + args.limit if args.limit else None]
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=args.headless)
        page = browser.new_page(locale="zh-TW", timezone_id="Asia/Taipei", viewport={"width": 1366, "height": 900})
        total = len(subset)
        for idx, store in enumerate(subset, 1):
            result = audit_store(page, store, args.start + idx, len(stores))
            audit_by_id[store["storeId"]] = result
            apply_result(store, result)
            esc_print(f"{args.start + idx}/{len(stores)} {store['storeId']} {result['gmbStatus']} {result['gmbOrderingStatus']} providers={','.join(result['providers'])}")
            save_json(AUDIT_PATH, list(audit_by_id.values()))
            save_json(STORES_PATH, stores)
            recompute_summary(summary, stores)
            save_json(SUMMARY_PATH, summary)
            page.wait_for_timeout(1500 + random.randint(0, 1200))
        browser.close()
    recompute_summary(summary, stores)
    save_json(SUMMARY_PATH, summary)

if __name__ == "__main__":
    main()
