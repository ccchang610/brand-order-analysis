const fs = require("node:fs");
const path = require("node:path");
const { chromium } = require("playwright-core");

const ROOT = path.resolve(__dirname, "..");
const BRAND_ROOT = path.join(ROOT, "macu");
const STORES_PATH = path.join(BRAND_ROOT, "data", "stores.json");
const SUMMARY_PATH = path.join(BRAND_ROOT, "data", "summary.json");
const INLINE_PATH = path.join(BRAND_ROOT, "data-inline.js");
const CSV_PATH = path.join(BRAND_ROOT, "data", "stores.csv");
const CHROME = "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe";
const CHECKED_AT = new Date().toISOString().slice(0, 10);

const PROVIDERS = [
  ["foodpanda", "foodpanda"],
  ["Uber Eats", "Uber Eats"],
  ["ubereats", "Uber Eats"],
  ["Nidin", "Nidin"],
  ["nidin.shop", "Nidin"],
  ["LINE", "LINE"],
  ["lin.ee", "LINE"],
  ["QuickClick", "QuickClick"],
  ["quickclick", "QuickClick"],
  ["快一點", "QuickClick"],
  ["eathere", "食在麻吉 eathere"],
  ["MaceWebPhone", "食在麻吉 eathere"],
  ["PB Order", "PB Order"],
  ["pborder", "PB Order"],
  ["esgpb", "PB Order"],
];
const TAIWAN_CITIES = ["基隆市", "台北市", "新北市", "桃園市", "新竹市", "新竹縣", "苗栗縣", "台中市", "彰化縣", "南投縣", "雲林縣", "嘉義市", "嘉義縣", "台南市", "高雄市", "屏東縣", "宜蘭縣", "花蓮縣", "台東縣", "澎湖縣", "金門縣", "連江縣"];
const REGIONS = ["北部", "中部", "南部", "東部", "離島"];
const BRAND_LEVEL_PLATFORM_EVIDENCE = [
  {
    platform: "LINE",
    status: "brand_level_official_order_link_pending_store_match",
    sourceType: "official",
    orderMode: ["pickup", "delivery"],
    evidenceUrl: "https://page.line.me/bjf7099i?oat__id=5728761&openQrModal=true",
    matchedBy: ["brandLevelOfficialLink"],
    notes: "Official #ORDER link resolves to LINE. Counted as all-source brand-level platform evidence, not Google Order provider evidence.",
  },
  {
    platform: "食在麻吉 eathere",
    status: "brand_level_official_order_lookup_link_pending_store_match",
    sourceType: "official",
    orderMode: ["pickup", "delivery"],
    evidenceUrl: "https://www.eathere.com.tw/MaceWebPhone/order.php",
    matchedBy: ["brandLevelOfficialLookupLink"],
    notes: "Official #SEARCH link resolves to eathere. Counted as all-source brand-level platform evidence, not Google Order provider evidence.",
  },
];


function args() {
  const out = { start: 0, limit: 10, ids: [], idsFile: "", outJsonl: "", headed: false, timeoutMs: 150000, retryTerminal: false, rebuildOnly: false };
  const argv = process.argv.slice(2);
  for (let i = 0; i < argv.length; i++) {
    if (argv[i] === "--start") out.start = Number(argv[++i] || 0);
    else if (argv[i] === "--limit") out.limit = Number(argv[++i] || 10);
    else if (argv[i] === "--headed") out.headed = true;
    else if (argv[i] === "--timeout-ms") out.timeoutMs = Number(argv[++i] || 150000);
    else if (argv[i] === "--ids-file") out.idsFile = argv[++i] || "";
    else if (argv[i] === "--out-jsonl") out.outJsonl = argv[++i] || "";
    else if (argv[i] === "--retry-terminal") out.retryTerminal = true;
    else if (argv[i] === "--rebuild-only") out.rebuildOnly = true;
    else if (argv[i] === "--ids") while (argv[i + 1] && !argv[i + 1].startsWith("--")) out.ids.push(argv[++i]);
  }
  return out;
}

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

function searchUrl(store) {
  const q = `麻古茶坊 ${store.storeName || ""} ${String(store.address || "").replace(/^\d{3,6}/, "")}`;
  return `https://www.google.com/search?q=${encodeURIComponent(q)}&hl=zh-TW`;
}

function compact(value) {
  return String(value || "").replace(/\s+/g, "").toLowerCase();
}

function namedMatch(text, store) {
  const blob = compact(text);
  const branch = compact(String(store.storeName || "").replace(/麻古茶坊|麻古|MACU|Tea/gi, ""));
  const district = compact(store.district || "");
  return (blob.includes("麻古") || blob.includes("macu")) && ((branch && blob.includes(branch)) || (district && blob.includes(district)));
}

function providerFromText(text) {
  const raw = String(text || "");
  const compacted = raw.replace(/\s+/g, "");
  const found = new Set();
  if (/foodpanda/i.test(raw)) found.add("foodpanda");
  if (/Uber\s*Eats|UberEats/i.test(raw)) found.add("Uber Eats");
  if (/(^|[^A-Za-z])LINE([^A-Za-z]|$)|line\.me|lin\.ee/i.test(raw)) found.add("LINE");
  if (raw.includes("食在麻吉")) found.add("食在麻吉 eathere");
  if (/QuickClick|quickclick|快一點/i.test(raw)) found.add("QuickClick");
  if (/PB\s*Order|pborder|esgpb/i.test(raw)) found.add("PB Order");
  if (/Nidin|nidin\.shop/i.test(raw)) found.add("Nidin");
  return [...found].filter(provider => compacted.includes(provider.replace(/\s+/g, "")) || provider !== "食在麻吉 eathere" || raw.includes("食在麻吉"));
}

async function settle(page) {
  await page.waitForTimeout(2500);
  await page.mouse.move(420, 360, { steps: 14 }).catch(() => {});
  await page.mouse.wheel(0, 360).catch(() => {});
  await page.waitForTimeout(1200);
  await page.mouse.wheel(0, -180).catch(() => {});
}

async function bodyText(page) {
  return await page.locator("body").innerText({ timeout: 9000 }).catch(() => "");
}

async function clickVisibleText(page, texts) {
  for (const text of texts) {
    const locators = [
      page.getByRole("button", { name: new RegExp(text), exact: false }),
      page.getByRole("link", { name: new RegExp(text), exact: false }),
      page.getByText(new RegExp(text)),
    ];
    for (const locator of locators) {
      const count = Math.min(await locator.count().catch(() => 0), 8);
      for (let i = 0; i < count; i++) {
        const item = locator.nth(i);
        if (!(await item.isVisible().catch(() => false))) continue;
        if (!(await item.isEnabled().catch(() => false))) continue;
        const box = await item.boundingBox().catch(() => null);
        if (!box || box.width < 20 || box.height < 12 || box.width > 760) continue;
        await item.click({ timeout: 5000 }).catch(() => {});
        await page.waitForTimeout(2200);
        return true;
      }
    }
  }
  return await page.evaluate((texts) => {
    const norm = value => String(value || "").replace(/\s+/g, " ").trim();
    const visible = el => {
      const r = el.getBoundingClientRect();
      const s = getComputedStyle(el);
      return r.width > 18 && r.height > 12 && r.bottom > 0 && r.top < innerHeight && s.display !== "none" && s.visibility !== "hidden" && Number(s.opacity || 1) > 0.2;
    };
    const nodes = [...document.querySelectorAll("a,button,[role='button'],[role='link'],[jsaction],[onclick],[tabindex],div,span")]
      .filter(visible)
      .map(el => ({ el, text: norm(`${el.innerText || el.textContent || ""} ${el.getAttribute("aria-label") || ""}`) }))
      .filter(x => x.text.length <= 48 && texts.some(t => x.text.includes(t)))
      .map(x => x.el.closest("a,button,[role='button'],[role='link'],[jsaction],[onclick],[tabindex]") || x.el)
      .filter(visible)
      .sort((a, b) => a.getBoundingClientRect().top - b.getBoundingClientRect().top);
    if (!nodes[0]) return false;
    nodes[0].click();
    return true;
  }, texts).catch(() => false);
}

async function googleOrderPanel(page) {
  return await page.evaluate(() => {
    const normalize = value => String(value || "").replace(/\s+/g, " ").trim();
    const visible = el => {
      const r = el.getBoundingClientRect();
      const s = getComputedStyle(el);
      return r.width > 20 && r.height > 12 && r.bottom > 0 && r.top < innerHeight && r.right > 0 && r.left < innerWidth && s.display !== "none" && s.visibility !== "hidden" && Number(s.opacity || 1) > 0.15;
    };
    const markerTexts = ["選擇下單對象", "Choose a provider", "Choose where to order"];
    const candidates = [...document.querySelectorAll("dialog,aside,section,div")]
      .filter(visible)
      .map(el => {
        const r = el.getBoundingClientRect();
        const text = normalize(el.innerText || el.textContent || "");
        return { el, text, area: r.width * r.height, rect: { top: r.top, left: r.left, width: r.width, height: r.height } };
      })
      .filter(x => markerTexts.some(marker => x.text.includes(marker)) && x.area > 8000 && x.text.length > 40)
      .sort((a, b) => a.area - b.area);
    const picked = candidates[0];
    if (!picked) {
      const bodyText = normalize(document.body ? document.body.innerText || "" : "");
      return { hasPanel: false, text: bodyText.slice(0, 1200), rect: null };
    }
    return { hasPanel: true, text: picked.text, rect: picked.rect };
  }).catch(() => ({ hasPanel: false, text: "", rect: null }));
}

async function clickOrderMode(page, mode) {
  const labels = mode === "pickup" ? ["\u53d6\u8ca8", "\u81ea\u53d6", "\u5916\u5e36", "Pickup"] : ["\u904b\u9001", "\u5916\u9001", "Delivery"];
  return await page.evaluate((labels) => {
    const normalize = value => String(value || "").replace(/\s+/g, " ").trim();
    const visible = el => {
      const r = el.getBoundingClientRect();
      const s = getComputedStyle(el);
      return r.width > 18 && r.height > 12 && r.bottom > 0 && r.top < innerHeight && r.right > 0 && r.left < innerWidth && s.display !== "none" && s.visibility !== "hidden" && Number(s.opacity || 1) > 0.15;
    };
    const disabled = el => {
      const s = getComputedStyle(el);
      const aria = String(el.getAttribute("aria-disabled") || "").toLowerCase();
      return Boolean(el.disabled) || aria === "true" || /disabled|inactive/i.test(el.className || "") || Number(s.opacity || 1) < 0.45 || s.pointerEvents === "none";
    };
    const selected = el => {
      const ariaPressed = String(el.getAttribute("aria-pressed") || "").toLowerCase();
      const ariaSelected = String(el.getAttribute("aria-selected") || "").toLowerCase();
      const ariaCurrent = String(el.getAttribute("aria-current") || "").toLowerCase();
      return ariaPressed === "true" || ariaSelected === "true" || ariaCurrent === "true" || /selected|active|checked/i.test(el.className || "");
    };
    const markerTexts = ["\u9078\u64c7\u4e0b\u55ae\u5c0d\u8c61", "Choose a provider", "Choose where to order"];
    const panels = [...document.querySelectorAll("dialog,aside,section,div")]
      .filter(visible)
      .map(el => ({ el, text: normalize(el.innerText || el.textContent || ""), area: el.getBoundingClientRect().width * el.getBoundingClientRect().height }))
      .filter(x => markerTexts.some(marker => x.text.includes(marker)) && x.area > 8000 && x.text.length > 40)
      .sort((a, b) => a.area - b.area);
    const root = panels[0]?.el || document.body;
    const controls = [...root.querySelectorAll("button,[role='button'],[aria-pressed],[aria-selected],div,span")]
      .filter(visible)
      .map(el => ({ el, text: normalize(`${el.innerText || el.textContent || ""} ${el.getAttribute("aria-label") || ""}`), rect: el.getBoundingClientRect() }))
      .filter(x => x.text.length <= 24 && labels.some(label => x.text === label))
      .sort((a, b) => {
        const aRole = a.el.getAttribute("role") === "button" || a.el.tagName === "BUTTON" ? 0 : 1;
        const bRole = b.el.getAttribute("role") === "button" || b.el.tagName === "BUTTON" ? 0 : 1;
        return aRole - bRole || a.rect.top - b.rect.top || a.rect.left - b.rect.left;
      });
    const control = controls[0];
    if (!control) return { found: false, clicked: false, disabled: false, selected: false, state: "not_found", text: "" };
    const target = control.el.closest("button,[role='button'],[tabindex],[jsaction],[onclick]") || control.el;
    const isDisabled = disabled(target) || disabled(control.el);
    const isSelected = selected(target) || selected(control.el);
    if (isDisabled) return { found: true, clicked: false, disabled: true, selected: false, state: "disabled", text: control.text };
    if (!isSelected) target.click();
    return { found: true, clicked: true, disabled: false, selected: isSelected, state: isSelected ? "active" : "clicked", text: control.text };
  }, labels).catch(() => ({ found: false, clicked: false, disabled: false, selected: false, state: "error", text: "" }));
}

async function panelProviders(page) {
  return await page.evaluate(() => {
    const normalize = value => String(value || "").replace(/\s+/g, " ").trim();
    const visible = el => {
      const r = el.getBoundingClientRect();
      const s = getComputedStyle(el);
      return r.width > 20 && r.height > 12 && r.bottom > 0 && r.top < innerHeight && r.right > 0 && r.left < innerWidth && s.display !== "none" && s.visibility !== "hidden" && Number(s.opacity || 1) > 0.15;
    };
    const providerFrom = text => {
      const out = [];
      if (/foodpanda/i.test(text)) out.push("foodpanda");
      if (/Uber\s*Eats|UberEats/i.test(text)) out.push("Uber Eats");
      if (/(^|[^A-Za-z])LINE([^A-Za-z]|$)|line\.me|lin\.ee/i.test(text)) out.push("LINE");
      if (text.includes("食在麻吉")) out.push("食在麻吉 eathere");
      if (/QuickClick|quickclick|快一點/i.test(text)) out.push("QuickClick");
      if (/PB\s*Order|pborder|esgpb/i.test(text)) out.push("PB Order");
      if (/Nidin|nidin\.shop/i.test(text)) out.push("Nidin");
      return out;
    };
    const markerTexts = ["選擇下單對象", "Choose a provider", "Choose where to order"];
    const panels = [...document.querySelectorAll("dialog,aside,section,div")]
      .filter(visible)
      .map(el => {
        const r = el.getBoundingClientRect();
        const text = normalize(el.innerText || el.textContent || "");
        return { el, text, area: r.width * r.height, rect: r };
      })
      .filter(x => markerTexts.some(marker => x.text.includes(marker)) && x.area > 8000 && x.text.length > 40)
      .sort((a, b) => a.area - b.area);
    const panel = panels[0];
    if (!panel) return { hasPanel: false, providers: [], rowTexts: [], text: normalize(document.body?.innerText || "").slice(0, 1200) };
    const marker = [...panel.el.querySelectorAll("div,span,p")]
      .filter(visible)
      .map(el => ({ el, text: normalize(el.innerText || el.textContent || ""), rect: el.getBoundingClientRect() }))
      .filter(x => markerTexts.some(marker => x.text.includes(marker)))
      .sort((a, b) => a.rect.top - b.rect.top)[0];
    const markerTop = marker ? marker.rect.top : panel.rect.top;
    const rows = [...panel.el.querySelectorAll("a,button,[role='button'],[role='link'],[jsaction],[onclick],[tabindex]")]
      .filter(visible)
      .map(el => {
        const r = el.getBoundingClientRect();
        const text = normalize(`${el.innerText || el.textContent || ""} ${el.getAttribute("aria-label") || ""} ${el.href || el.getAttribute("href") || ""}`);
        return { el, text, rect: r, area: r.width * r.height };
      })
      .filter(x => x.rect.top > markerTop + 8 && x.rect.height >= 24 && x.rect.height <= 120 && x.rect.width >= 120 && x.text.length <= 180)
      .sort((a, b) => a.area - b.area || a.rect.top - b.rect.top || a.rect.left - b.rect.left);
    const providers = new Set();
    const rowTexts = [];
    for (const row of rows) {
      const rowProviders = providerFrom(row.text);
      if (rowProviders.length !== 1) continue;
      rowTexts.push(row.text.slice(0, 220));
      rowProviders.forEach(provider => providers.add(provider));
    }
    return { hasPanel: true, providers: [...providers], rowTexts, text: panel.text.slice(0, 1200) };
  }).catch(() => ({ hasPanel: false, providers: [], rowTexts: [], text: "" }));
}

async function readMode(page, mode) {
  const modeState = await clickOrderMode(page, mode);
  await page.waitForTimeout(modeState.clicked ? 1800 : 900);
  if (modeState.disabled) return { hasPanel: true, providers: [], modeState, modeReadState: "disabled", rowTexts: [], text: "mode disabled" };
  if (!modeState.found) return { hasPanel: true, providers: [], modeState, modeReadState: "not_found", rowTexts: [], text: "mode control not found" };
  if (!modeState.clicked) return { hasPanel: true, providers: [], modeState, modeReadState: "unknown", rowTexts: [], text: "mode not clicked" };
  const panel = await panelProviders(page);
  return { ...panel, modeState, modeReadState: panel.providers?.length ? "active" : "active_no_provider" };
}
async function auditStore(context, store) {
  const page = await context.newPage();
  const history = [];
  const targets = [store.gmbOrderPanelUrl, searchUrl(store), store.gmbUrl || store.officialMapUrl].filter(Boolean);
  let best = null;
  try {
    for (const target of targets) {
      const result = { status: "needs_manual_review", gmbStatus: "needs_manual_review", pickup: [], delivery: [], pickupState: "unknown", deliveryState: "unknown", hasGmbOrderingSystem: false, panelUrl: "", notes: "", target };
      try {
        await page.goto(target, { waitUntil: "domcontentloaded", timeout: 45000 });
        await settle(page);
        const initialText = await bodyText(page);
        if (/unusual traffic|流量有異常|為何顯示此頁/i.test(initialText + page.url())) {
          result.status = "unavailable_or_blocked";
          result.notes = "Google bot-check or unusual traffic page appeared.";
          history.push({ target, status: result.status, buttonDetected: false, providersParsed: false });
          best = best || result;
          continue;
        }
        if (!namedMatch(initialText, store)) {
          result.status = "no_gmb_profile_match";
          result.gmbStatus = "not_found";
          result.notes = "No highly similar named GMB profile was visible.";
          history.push({ target, status: result.status, buttonDetected: false, providersParsed: false });
          best = best || result;
          continue;
        }
        result.gmbStatus = "confirmed";
        const clicked = await clickVisibleText(page, ["點餐外帶", "點餐外送", "線上點餐", "線上訂餐", "Order online"]);
        await page.waitForTimeout(2800);
        const opened = await panelProviders(page);
        if (!clicked && !opened.hasPanel) {
          result.status = "no_gmb_order_button";
          result.notes = "Named GMB profile matched, but no Google Order entry was opened.";
          history.push({ target, status: result.status, buttonDetected: false, providersParsed: false });
          best = best || result;
          continue;
        }
        const pickup = await readMode(page, "pickup");
        const delivery = await readMode(page, "delivery");
        result.pickup = pickup.providers;
        result.delivery = delivery.providers;
        result.pickupState = pickup.modeReadState || "unknown";
        result.deliveryState = delivery.modeReadState || "unknown";
        result.pickupRowTexts = pickup.rowTexts || [];
        result.deliveryRowTexts = delivery.rowTexts || [];
        result.panelUrl = page.url();
        if (result.pickup.length || result.delivery.length) {
          result.status = "confirmed";
          result.hasGmbOrderingSystem = true;
          result.notes = "Playwright batch opened Google Order flow and read visible pickup/delivery providers.";
        } else {
          result.status = "button_confirmed_provider_pending";
          result.hasGmbOrderingSystem = true;
          result.notes = "Google Order entry/panel opened, but provider rows were not parsed.";
        }
        history.push({ target, status: result.status, buttonDetected: true, providersParsed: Boolean(result.pickup.length || result.delivery.length) });
        best = result;
        if (result.status === "confirmed") break;
      } catch (error) {
        result.status = "unavailable_or_blocked";
        result.notes = `Playwright audit failed: ${error.name || "Error"}.`;
        history.push({ target, status: result.status, buttonDetected: false, providersParsed: false });
        best = best || result;
      }
    }
    return applyResult(store, best || { status: "unavailable_or_blocked", notes: "No target completed.", pickup: [], delivery: [], history }, history);
  } finally {
    await page.close().catch(() => {});
  }
}

function applyResult(store, result, history) {
  const updated = { ...store, sourceCoverage: { ...(store.sourceCoverage || {}) } };
  updated.orderingSystems = (store.orderingSystems || []).filter(c => c.sourceType !== "gmb");
  updated.gmbStatus = result.gmbStatus || (result.status === "no_gmb_profile_match" ? "not_found" : "confirmed");
  updated.gmbOrderingStatus = result.status;
  updated.gmbOrderPanelUrl = result.panelUrl || "";
  updated.gmbUrl = result.target || store.gmbUrl || "";
  updated.gmbPickupProviders = [...new Set(result.pickup || [])];
  updated.gmbDeliveryProviders = [...new Set(result.delivery || [])];
  updated.gmbOrderModesConfirmed = [
    ...(updated.gmbPickupProviders.length ? ["pickup"] : []),
    ...(updated.gmbDeliveryProviders.length ? ["delivery"] : []),
  ];
  updated.gmbShareUrl = updated.gmbShareUrl || "";
  updated.gmbOrderLinks = Array.isArray(updated.gmbOrderLinks) ? updated.gmbOrderLinks : [];
  updated.sourceCoverage.gmbFound = updated.gmbStatus === "confirmed";
  updated.sourceCoverage.officialOrderingFound = Boolean(updated.sourceCoverage.officialOrderingFound);
  updated.sourceCoverage.googleFound = true;
  const add = (system, mode) => updated.orderingSystems.push({ system, sourceType: "gmb", orderMode: [mode], evidenceUrl: updated.gmbOrderPanelUrl || updated.gmbUrl, label: `Google Order ${mode}`, confidence: "confirmed" });
  updated.gmbPickupProviders.forEach(p => add(p, "pickup"));
  updated.gmbDeliveryProviders.forEach(p => add(p, "delivery"));
  updated.hasGmbOrderingSystem = Boolean(result.hasGmbOrderingSystem || updated.gmbPickupProviders.length || updated.gmbDeliveryProviders.length);
  updated.hasAnyOrderingSystem = Boolean(updated.orderingSystems.length);
  updated.manualReviewReason = result.notes || "";
  updated.gmbSignals = {
    ...(store.gmbSignals || {}),
    buttonDetected: updated.hasGmbOrderingSystem,
    providersParsed: Boolean(updated.gmbPickupProviders.length || updated.gmbDeliveryProviders.length),
    modeReadStates: { pickupProviders: result.pickupState || (updated.gmbPickupProviders.length ? "active" : "unknown"), deliveryProviders: result.deliveryState || (updated.gmbDeliveryProviders.length ? "active" : "unknown") },
    attemptCount: history.length,
    maxAttempts: 1,
    attemptHistory: history,
    panelUrl: updated.gmbOrderPanelUrl,
    checkedAt: CHECKED_AT,
    checkMethod: "playwright_core_chrome_google_order_batch",
    unresolvedReason: result.status === "confirmed" ? "" : result.status,
    notes: updated.manualReviewReason,
    providerRowTexts: { pickup: result.pickupRowTexts || [], delivery: result.deliveryRowTexts || [] },
  };
  return normalizeStoreAllSourceEvidence(updated);
}

function count(items) {
  return items.reduce((acc, item) => (acc[item || "unknown"] = (acc[item || "unknown"] || 0) + 1, acc), {});
}
function rate(n, d) { return d ? Number((n / d).toFixed(4)) : 0; }
function platformAuditRows(store) {
  const audit = store.platformAudit || {};
  if (Array.isArray(audit)) return audit.filter(Boolean);
  return Object.values(audit).filter(Boolean);
}
function platformAuditClaims(store) {
  return platformAuditRows(store)
    .filter(row => row.platform && row.evidenceUrl && !/not_found|no_match|error|invalid/i.test(row.status || ""))
    .map(row => ({
      system: row.platform,
      sourceType: row.sourceType || "third_party",
      orderMode: row.orderMode?.length ? row.orderMode : ["unknown"],
      evidenceUrl: row.evidenceUrl,
      label: row.status || row.platform,
      confidence: "platform_lead",
    }));
}
function allSourceClaims(store) {
  return [...(store.orderingSystems || []), ...platformAuditClaims(store)];
}
function normalizeStoreAllSourceEvidence(store) {
  if (!store.platformAudit || Array.isArray(store.platformAudit)) {
    const rows = platformAuditRows(store);
    store.platformAudit = {};
    for (const row of rows) {
      if (row.platform) store.platformAudit[row.platform] = row;
    }
  }
  for (const evidence of BRAND_LEVEL_PLATFORM_EVIDENCE) {
    store.platformAudit[evidence.platform] = {
      ...evidence,
      ...(store.platformAudit[evidence.platform] || {}),
      platform: evidence.platform,
      sourceType: evidence.sourceType,
      orderMode: store.platformAudit[evidence.platform]?.orderMode || evidence.orderMode,
      evidenceUrl: store.platformAudit[evidence.platform]?.evidenceUrl || evidence.evidenceUrl,
      checkedAt: store.platformAudit[evidence.platform]?.checkedAt || CHECKED_AT,
      notes: store.platformAudit[evidence.platform]?.notes || evidence.notes,
    };
  }
  store.sourceCoverage = { ...(store.sourceCoverage || {}) };
  store.sourceCoverage.officialOrderingFound = true;
  store.sourceCoverage.thirdPartyFound = true;
  store.hasAnyOrderingSystem = Boolean(allSourceClaims(store).length);
  return store;
}
function countSystems(stores, sourceType = null, mode = null) {
  const out = new Map();
  for (const store of stores) {
    const systems = new Set();
    const claims = sourceType ? (store.orderingSystems || []) : allSourceClaims(store);
    for (const c of claims) {
      if (sourceType && c.sourceType !== sourceType) continue;
      if (mode && !(c.orderMode || []).includes(mode)) continue;
      if (c.system) systems.add(c.system);
    }
    systems.forEach(system => out.set(system, (out.get(system) || 0) + 1));
  }
  return Object.fromEntries([...out].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0])));
}
function rebuildSummary(stores, previous) {
  stores.forEach(normalizeStoreAllSourceEvidence);
  const total = stores.length;
  const allCounts = countSystems(stores);
  const gmbCounts = countSystems(stores, "gmb");
  const systems = [...new Set([...Object.keys(allCounts), ...Object.keys(gmbCounts), "Nidin", "Uber Eats", "foodpanda", "LINE", "QuickClick", "食在麻吉 eathere", "PB Order"])].sort();
  const gmbOrderingSystemCount = stores.filter(s => (s.orderingSystems || []).some(c => c.sourceType === "gmb")).length;
  const anyOrderingSystemCount = stores.filter(s => allSourceClaims(s).length).length;
  const storePlatformStatusCounts = count(stores.flatMap(s => platformAuditRows(s).map(row => `${row.platform}:${row.status}`)));
  return {
    ...previous,
    generatedAt: CHECKED_AT,
    officialStoreCount: total,
    gmbFoundCount: stores.filter(s => s.sourceCoverage?.gmbFound || s.gmbStatus === "confirmed").length,
    gmbMissingCount: stores.filter(s => !(s.sourceCoverage?.gmbFound) && s.gmbStatus !== "confirmed").length,
    googleFoundCount: stores.filter(s => s.sourceCoverage?.googleFound).length,
    thirdPartyFoundCount: stores.filter(s => s.sourceCoverage?.thirdPartyFound).length,
    verificationGapCount: stores.filter(s => s.gmbOrderingStatus !== "confirmed").length,
    anyOrderingSystemCount,
    anyOrderingSystemAdoptionRate: rate(anyOrderingSystemCount, total),
    googleOrderEntryCount: stores.filter(s => s.hasGmbOrderingSystem || s.gmbOrderingStatus === "button_confirmed_provider_pending").length,
    googleOrderEntryRate: rate(stores.filter(s => s.hasGmbOrderingSystem || s.gmbOrderingStatus === "button_confirmed_provider_pending").length, total),
    gmbOrderingSystemCount,
    gmbOrderingSystemAdoptionRate: rate(gmbOrderingSystemCount, total),
    gmbCoverageGapCount: stores.filter(s => !s.hasGmbOrderingSystem && s.gmbOrderingStatus !== "button_confirmed_provider_pending").length,
    unknownOrderingSystemCount: stores.filter(s => !allSourceClaims(s).length).length,
    cityCounts: Object.fromEntries(TAIWAN_CITIES.map(city => [city, stores.filter(s => s.city === city).length])),
    regionCounts: Object.fromEntries(REGIONS.map(region => [region, stores.filter(s => s.regionGroup === region).length])),
    allSourceSystemCounts: allCounts,
    allSourcePickupSystemCounts: countSystems(stores, null, "pickup"),
    allSourceDeliverySystemCounts: countSystems(stores, null, "delivery"),
    gmbSystemCounts: gmbCounts,
    gmbPickupSystemCounts: countSystems(stores, "gmb", "pickup"),
    gmbDeliverySystemCounts: countSystems(stores, "gmb", "delivery"),
    gmbOrderOptionCounts: gmbCounts,
    gmbOrderPickupOptionCounts: countSystems(stores, "gmb", "pickup"),
    gmbOrderDeliveryOptionCounts: countSystems(stores, "gmb", "delivery"),
    gmbStatusCounts: count(stores.map(s => s.gmbStatus)),
    gmbOrderingStatusCounts: count(stores.map(s => s.gmbOrderingStatus)),
    sourceCoverageCounts: { officialListed: total, gmbFound: stores.filter(s => s.sourceCoverage?.gmbFound).length, googleFound: stores.filter(s => s.sourceCoverage?.googleFound).length, thirdPartyFound: stores.filter(s => s.sourceCoverage?.thirdPartyFound).length },
    storePlatformStatusCounts,
    allSourceSystemAdoptionRates: Object.fromEntries(Object.entries(allCounts).map(([k, v]) => [k, rate(v, total)])),
    gmbSystemAdoptionRates: Object.fromEntries(Object.entries(gmbCounts).map(([k, v]) => [k, rate(v, total)])),
    gmbOrderOptionAdoptionRates: Object.fromEntries(Object.entries(gmbCounts).map(([k, v]) => [k, rate(v, total)])),
    systemComparison: systems.map(system => ({ system, allSourceStoreCount: allCounts[system] || 0, allSourceAdoptionRate: rate(allCounts[system] || 0, total), gmbStoreCount: gmbCounts[system] || 0, gmbAdoptionRate: rate(gmbCounts[system] || 0, total), countGap: (allCounts[system] || 0) - (gmbCounts[system] || 0), percentagePointGap: Number((rate(allCounts[system] || 0, total) - rate(gmbCounts[system] || 0, total)).toFixed(4)) })),
  };
}
function csvEscape(value) {
  const text = Array.isArray(value) ? value.join("、") : String(value ?? "");
  return `"${text.replace(/"/g, '""')}"`;
}
function writeAll(payload, summary) {
  payload.stores.forEach(normalizeStoreAllSourceEvidence);
  fs.writeFileSync(STORES_PATH, JSON.stringify(payload, null, 2) + "\n", "utf8");
  fs.writeFileSync(SUMMARY_PATH, JSON.stringify(summary, null, 2) + "\n", "utf8");
  fs.writeFileSync(INLINE_PATH, `window.DAMING_DATA = ${JSON.stringify({ storesPayload: payload, summary })};\n`, "utf8");
  const fields = ["storeId", "storeName", "regionGroup", "city", "district", "address", "phone", "gmbStatus", "gmbOrderingStatus", "hasAnyOrderingSystem", "hasGmbOrderingSystem", "gmbPickupProviders", "gmbDeliveryProviders", "allSourceSystems", "gmbSystems", "gmbUrl", "gmbOrderPanelUrl", "manualReviewReason"];
  const csvRows = payload.stores.map(s => ({
    ...s,
    allSourceSystems: [...new Set(allSourceClaims(s).map(c => c.system).filter(Boolean))].sort(),
    gmbSystems: [...new Set((s.orderingSystems || []).filter(c => c.sourceType === "gmb").map(c => c.system).filter(Boolean))].sort(),
  }));
  fs.writeFileSync(CSV_PATH, "\ufeff" + [fields.join(","), ...csvRows.map(s => fields.map(f => csvEscape(s[f])).join(","))].join("\n") + "\n", "utf8");
}
async function main() {
  const opts = args();
  if (opts.idsFile) {
    opts.ids.push(...fs.readFileSync(opts.idsFile, "utf8").split(/\r?\n/).map(x => x.trim()).filter(Boolean));
  }
  const completedShardIds = new Set();
  if (opts.outJsonl) {
    fs.mkdirSync(path.dirname(path.resolve(opts.outJsonl)), { recursive: true });
    if (fs.existsSync(opts.outJsonl)) {
      for (const line of fs.readFileSync(opts.outJsonl, "utf8").split(/\r?\n/)) {
        if (!line.trim()) continue;
        try {
          const row = JSON.parse(line);
          if (row.storeId) completedShardIds.add(row.storeId);
        } catch {}
      }
    } else {
      fs.writeFileSync(opts.outJsonl, "", "utf8");
    }
  }
  const payload = JSON.parse(fs.readFileSync(STORES_PATH, "utf8"));
  const previous = JSON.parse(fs.readFileSync(SUMMARY_PATH, "utf8"));
  const allStores = payload.stores;
  const openStatuses = new Set(["needs_manual_review"]);
  const targets = opts.ids.length
    ? allStores.filter(s => opts.ids.includes(s.storeId) && !completedShardIds.has(s.storeId))
    : allStores
      .filter(s => opts.retryTerminal ? s.gmbOrderingStatus !== "confirmed" : openStatuses.has(s.gmbOrderingStatus))
      .slice(opts.start, opts.start + opts.limit);
  if (opts.rebuildOnly) {
    payload.stores = allStores.map(s => normalizeStoreAllSourceEvidence(s));
    const summary = rebuildSummary(payload.stores, previous);
    writeAll(payload, summary);
    console.log(JSON.stringify({ officialStoreCount: summary.officialStoreCount, anyOrderingSystemCount: summary.anyOrderingSystemCount, allSourceSystemCounts: summary.allSourceSystemCounts, gmbSystemCounts: summary.gmbSystemCounts, gmbOrderingStatusCounts: summary.gmbOrderingStatusCounts, storePlatformStatusCounts: summary.storePlatformStatusCounts }, null, 2));
    return;
  }
  const browser = await chromium.launch({ executablePath: CHROME, headless: !opts.headed, args: ["--lang=zh-TW", "--disable-blink-features=AutomationControlled"] });
  const context = await browser.newContext({ locale: "zh-TW", timezoneId: "Asia/Taipei", viewport: { width: 1365, height: 920 }, userAgent: "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36" });
  const updated = new Map();
  try {
    let i = 0;
    for (const store of targets) {
      i += 1;
      console.log(`${i}/${targets.length} checking ${store.storeId} ${store.storeName}`);
      let checked;
      try {
        checked = await Promise.race([auditStore(context, store), new Promise((_, reject) => setTimeout(() => reject(new Error("store timeout")), opts.timeoutMs))]);
      } catch (error) {
        checked = applyResult(store, { status: "unavailable_or_blocked", gmbStatus: store.gmbStatus, pickup: [], delivery: [], target: store.gmbUrl || store.googleSearchUrl, notes: `Playwright batch timed out or failed: ${error.message}.` }, [{ target: store.gmbUrl || store.googleSearchUrl, status: "unavailable_or_blocked", buttonDetected: false, providersParsed: false }]);
      }
      updated.set(checked.storeId, checked);
      if (opts.outJsonl) {
        fs.appendFileSync(opts.outJsonl, JSON.stringify({ storeId: checked.storeId, store: checked }) + "\n", "utf8");
        console.log(JSON.stringify({ storeId: checked.storeId, storeName: checked.storeName, gmbStatus: checked.gmbStatus, gmbOrderingStatus: checked.gmbOrderingStatus, pickup: checked.gmbPickupProviders, delivery: checked.gmbDeliveryProviders, pickupState: checked.gmbSignals?.modeReadStates?.pickupProviders, deliveryState: checked.gmbSignals?.modeReadStates?.deliveryProviders }));
      } else {
        payload.stores = allStores.map(s => updated.get(s.storeId) || s);
        const summary = rebuildSummary(payload.stores, previous);
        writeAll(payload, summary);
        console.log(JSON.stringify({ storeId: checked.storeId, storeName: checked.storeName, gmbStatus: checked.gmbStatus, gmbOrderingStatus: checked.gmbOrderingStatus, pickup: checked.gmbPickupProviders, delivery: checked.gmbDeliveryProviders, counts: summary.gmbOrderingStatusCounts }));
      }
      await sleep(1500 + Math.random() * 2500);
    }
  } finally {
    await browser.close();
  }
  if (opts.outJsonl) {
    console.log(JSON.stringify({ shard: opts.outJsonl, checkedCount: updated.size }, null, 2));
    return;
  }
  payload.stores = allStores.map(s => updated.get(s.storeId) || s);
  const summary = rebuildSummary(payload.stores, previous);
  writeAll(payload, summary);
  console.log(JSON.stringify({ officialStoreCount: summary.officialStoreCount, gmbFoundCount: summary.gmbFoundCount, googleOrderEntryCount: summary.googleOrderEntryCount, gmbOrderingSystemCount: summary.gmbOrderingSystemCount, gmbOrderingStatusCounts: summary.gmbOrderingStatusCounts, gmbSystemCounts: summary.gmbSystemCounts }, null, 2));
}
main().catch(error => { console.error(error); process.exit(1); });









