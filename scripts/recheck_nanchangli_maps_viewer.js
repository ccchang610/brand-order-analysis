const fs = require("node:fs");
const path = require("node:path");
const { chromium } = require("playwright-core");

const ROOT = path.resolve(__dirname, "..");
const STORES_PATH = path.join(ROOT, "nanchangli", "data", "stores.json");
const OUT_PATH = path.join(ROOT, "nanchangli", "work", "maps-viewer-rerun.jsonl");
const CHROME = "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe";
const CHECKED_AT = new Date().toISOString().slice(0, 10);

function args() {
  const out = { start: 0, limit: 5, ids: [] };
  const argv = process.argv.slice(2);
  for (let i = 0; i < argv.length; i += 1) {
    if (argv[i] === "--start") out.start = Number(argv[++i] || 0);
    else if (argv[i] === "--limit") out.limit = Number(argv[++i] || 5);
    else if (argv[i] === "--ids") while (argv[i + 1] && !argv[i + 1].startsWith("--")) out.ids.push(argv[++i]);
  }
  return out;
}

const compact = value => String(value || "").replace(/\s+/g, "").toLowerCase();
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
const mapsUrl = query => `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(query)}`;

function providerFromRow(text, href) {
  const value = `${text || ""} ${href || ""}`;
  const providers = [];
  if (/foodpanda/i.test(value)) providers.push("foodpanda");
  if (/Uber\s*Eats|UberEats|ubereats\.com/i.test(value)) providers.push("Uber Eats");
  if (/Nidin|nidin\.shop/i.test(value)) providers.push("Nidin");
  if (/QuickClick|quickclick|快一點/i.test(value)) providers.push("QuickClick");
  if (/食在麻吉|eathere|MaceWebPhone/i.test(value)) providers.push("食在麻吉 eathere");
  if (/PB\s*Order|pborder|esgpb/i.test(value)) providers.push("PB Order");
  if (/Ocard|ocard\.co/i.test(value)) providers.push("Ocard");
  if (/(^|[^A-Za-z])LINE([^A-Za-z]|$)|line\.me|lin\.ee/i.test(value)) providers.push("LINE");
  return [...new Set(providers)];
}

async function readProfileIdentity(page) {
  return page.evaluate(() => {
    const text = element => String(element?.innerText || element?.textContent || "").replace(/\s+/g, " ").trim();
    const name = text(document.querySelector("h1"));
    const address = text(document.querySelector('[data-item-id*="address"]'));
    const phone = text(document.querySelector('[data-item-id^="phone"]'));
    return { name, address, phone };
  });
}

async function openNamedPlaceFromResults(page, store) {
  const visibleName = await page.locator("h1").first().innerText({ timeout: 1200 }).catch(() => "");
  if (visibleName.trim()) return;
  const candidates = await page.locator('a[href*="/maps/place/"]').evaluateAll(elements => elements.map(element => ({
    href: element.href,
    text: String(element.getAttribute("aria-label") || element.innerText || element.textContent || "").replace(/\s+/g, " ").trim(),
  })));
  const names = [store.storeName, ...(store.storeAliases || []), ...(store.searchAliases || [])].map(compact).filter(name => name.length >= 2);
  const candidate = candidates.find(row => names.some(name => compact(row.text).includes(name) || name.includes(compact(row.text))));
  if (!candidate) return;
  await page.goto(candidate.href, { waitUntil: "domcontentloaded", timeout: 60000 });
  await page.waitForTimeout(3500);
}

function profileMatches(identity, store) {
  const profileName = compact(identity.name);
  const names = [store.storeName, ...(store.storeAliases || []), ...(store.searchAliases || [])].map(compact).filter(name => name.length >= 2);
  const nameMatched = profileName && names.some(name => profileName.includes(name) || name.includes(profileName));
  const address = compact(String(store.address || "").replace(/^\d{3,6}/, ""));
  const streetNumber = compact((String(store.address || "").match(/[^市區]+(?:路|街)[^號]*\d+(?:之\d+)?號/) || [""])[0]);
  const profileAddress = compact(identity.address);
  const phoneTail = String(store.phone || "").replace(/\D/g, "").slice(-6);
  const digits = String(identity.phone || "").replace(/\D/g, "");
  const identityMatched = (streetNumber && profileAddress.includes(streetNumber)) || (address.slice(-8) && profileAddress.includes(address.slice(-8))) || (phoneTail.length >= 6 && digits.includes(phoneTail));
  return nameMatched && identityMatched;
}

async function visibleOrderHref(page) {
  return page.evaluate(() => {
    const visible = element => {
      const rect = element.getBoundingClientRect();
      const style = getComputedStyle(element);
      return rect.width > 20 && rect.height > 12 && style.display !== "none" && style.visibility !== "hidden" && Number(style.opacity || 1) > 0.1;
    };
    const links = [...document.querySelectorAll("a[href]")]
      .filter(visible)
      .map(element => ({
        text: String(element.innerText || element.textContent || "").replace(/\s+/g, " ").trim(),
        href: element.href,
        area: element.getBoundingClientRect().width * element.getBoundingClientRect().height,
      }))
      .filter(row => /searchviewer\/|線上點餐|點餐外帶|點餐外送|Order online/i.test(`${row.href} ${row.text}`))
      .sort((a, b) => a.area - b.area);
    return links[0] || null;
  });
}

async function resolveMaps(page, store) {
  const aliases = [...(store.storeAliases || []), ...(store.searchAliases || [])].slice(0, 1).join(" ");
  const queries = [
    `${store.storeName} ${store.address}`,
    `${store.storeName} ${aliases} ${store.phone || ""}`,
  ];
  const attempts = [];
  let best = null;
  for (const query of queries) {
    await page.goto(mapsUrl(query), { waitUntil: "domcontentloaded", timeout: 60000 });
    await page.waitForTimeout(5000);
    await openNamedPlaceFromResults(page, store);
    const body = await page.locator("body").innerText({ timeout: 10000 }).catch(() => "");
    if (/unusual traffic|流量有異常|為何顯示此頁/i.test(`${body} ${page.url()}`)) {
      attempts.push({ query, status: "google_blocked", url: page.url() });
      continue;
    }
    const identity = await readProfileIdentity(page);
    const matched = profileMatches(identity, store);
    const order = matched ? await visibleOrderHref(page) : null;
    const row = { query, status: matched ? (order ? "button_visible" : "profile_matched_no_button") : "profile_mismatch", url: page.url(), identity, order };
    attempts.push(row);
    if (matched) best = { identity, gmbUrl: page.url(), order, query };
    if (order) break;
    await sleep(1200);
  }
  return { best, attempts };
}

async function findModeControl(page, mode) {
  const labels = mode === "pickup" ? /^(取貨|自取|外帶|Pickup)$/i : /^(運送|外送|Delivery)$/i;
  return page.evaluate(source => {
    const labels = new RegExp(source, "i");
    const visible = element => {
      const rect = element.getBoundingClientRect();
      const style = getComputedStyle(element);
      return rect.width > 20 && rect.height > 12 && style.display !== "none" && style.visibility !== "hidden" && Number(style.opacity || 1) > 0.1;
    };
    const rows = [...document.querySelectorAll("button,[role='button']")]
      .filter(visible)
      .map(element => ({
        element,
        text: String(element.innerText || element.textContent || "").replace(/\s+/g, " ").trim(),
        area: element.getBoundingClientRect().width * element.getBoundingClientRect().height,
      }))
      .filter(row => labels.test(row.text))
      .sort((a, b) => a.area - b.area);
    const element = rows[0]?.element;
    if (!element) return { found: false, disabled: false, clicked: false };
    const style = getComputedStyle(element);
    const disabled = Boolean(element.disabled) || element.getAttribute("aria-disabled") === "true" || style.pointerEvents === "none" || Number(style.opacity || 1) < 0.45;
    if (disabled) return { found: true, disabled: true, clicked: false };
    element.click();
    return { found: true, disabled: false, clicked: true };
  }, labels.source);
}

async function parseViewerRows(page, mode) {
  return page.evaluate(mode => {
    const visible = element => {
      const rect = element.getBoundingClientRect();
      const style = getComputedStyle(element);
      return rect.width > 100 && rect.height > 20 && rect.bottom > 0 && rect.top < innerHeight && style.display !== "none" && style.visibility !== "hidden" && Number(style.opacity || 1) > 0.1;
    };
    return [...document.querySelectorAll("a[href]")]
      .filter(visible)
      .map(element => ({
        text: String(element.innerText || element.textContent || "").replace(/\s+/g, " ").trim().slice(0, 260),
        href: element.href,
        mode,
      }))
      .filter(row => row.text && !/瞭解詳情|Google/i.test(row.text));
  }, mode);
}

async function auditViewer(context, href) {
  const page = await context.newPage();
  try {
    await page.goto(href, { waitUntil: "domcontentloaded", timeout: 60000 });
    await page.waitForTimeout(4500);
    const body = await page.locator("body").innerText({ timeout: 10000 }).catch(() => "");
    if (/unusual traffic|流量有異常|為何顯示此頁/i.test(`${body} ${page.url()}`)) return { blocked: true, panelUrl: page.url() };
    const hasPanel = /線上點餐|選擇下單對象|Choose a provider|Choose where to order/i.test(body);
    if (!hasPanel) return { blocked: false, hasPanel: false, panelUrl: page.url() };
    const result = { blocked: false, hasPanel: true, panelUrl: page.url(), pickup: [], delivery: [], pickupRows: [], deliveryRows: [], modeStates: {}, links: [] };
    for (const mode of ["pickup", "delivery"]) {
      const control = await findModeControl(page, mode);
      if (control.disabled) {
        result.modeStates[mode] = "disabled";
        continue;
      }
      if (!control.found) {
        result.modeStates[mode] = "not_found";
        continue;
      }
      await page.waitForTimeout(1800);
      const rows = await parseViewerRows(page, mode);
      const accepted = [];
      for (const row of rows) {
        const providers = providerFromRow(row.text, row.href);
        if (providers.length !== 1) continue;
        accepted.push({ ...row, provider: providers[0] });
      }
      result[mode] = [...new Set(accepted.map(row => row.provider))];
      result[`${mode}Rows`] = accepted.map(row => row.text);
      result.modeStates[mode] = accepted.length ? "active" : "active_no_provider";
      result.links.push(...accepted.map(row => ({ platform: row.provider, kind: "provider_row_link", sourceType: "gmb_order_panel", orderMode: [mode], label: row.text, href: row.href, panelUrl: page.url(), observedAt: CHECKED_AT, confidence: "confirmed" })));
    }
    return result;
  } finally {
    await page.close().catch(() => {});
  }
}

async function auditStore(context, store) {
  const page = await context.newPage();
  try {
    const resolved = await resolveMaps(page, store);
    if (!resolved.best) {
      const blocked = resolved.attempts.every(attempt => attempt.status === "google_blocked");
      return { storeId: store.storeId, storeName: store.storeName, gmbStatus: blocked ? "unavailable_or_blocked" : "not_found", status: blocked ? "unavailable_or_blocked" : "no_gmb_profile_match", attempts: resolved.attempts };
    }
    const { best } = resolved;
    if (!best.order) return { storeId: store.storeId, storeName: store.storeName, gmbStatus: "confirmed", status: "no_gmb_order_button", gmbUrl: best.gmbUrl, attempts: resolved.attempts };
    const viewer = await auditViewer(context, best.order.href);
    if (viewer.blocked || !viewer.hasPanel) return { storeId: store.storeId, storeName: store.storeName, gmbStatus: "confirmed", status: "button_confirmed_provider_pending", gmbUrl: best.gmbUrl, blueButtonText: best.order.text, attempts: resolved.attempts, viewer };
    const hasProviders = viewer.pickup.length || viewer.delivery.length;
    return { storeId: store.storeId, storeName: store.storeName, gmbStatus: "confirmed", status: hasProviders ? "confirmed" : "button_confirmed_provider_pending", gmbUrl: best.gmbUrl, blueButtonText: best.order.text, attempts: resolved.attempts, viewer };
  } finally {
    await page.close().catch(() => {});
  }
}

async function main() {
  const options = args();
  fs.mkdirSync(path.dirname(OUT_PATH), { recursive: true });
  const completed = new Set();
  if (fs.existsSync(OUT_PATH)) {
    for (const line of fs.readFileSync(OUT_PATH, "utf8").split(/\r?\n/)) {
      if (!line.trim()) continue;
      try { completed.add(JSON.parse(line).storeId); } catch {}
    }
  }
  const stores = JSON.parse(fs.readFileSync(STORES_PATH, "utf8")).stores;
  const targets = (options.ids.length ? stores.filter(store => options.ids.includes(store.storeId)) : stores.slice(options.start, options.start + options.limit)).filter(store => !completed.has(store.storeId));
  const browser = await chromium.launch({ executablePath: CHROME, headless: true, args: ["--lang=zh-TW", "--disable-blink-features=AutomationControlled"] });
  const context = await browser.newContext({ locale: "zh-TW", timezoneId: "Asia/Taipei", viewport: { width: 2200, height: 1200 }, userAgent: "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36" });
  await context.route("**/*", route => ["image", "media", "font"].includes(route.request().resourceType()) ? route.abort() : route.continue());
  try {
    let index = 0;
    for (const store of targets) {
      index += 1;
      const result = await auditStore(context, store).catch(error => ({ storeId: store.storeId, storeName: store.storeName, gmbStatus: "unavailable_or_blocked", status: "unavailable_or_blocked", error: `${error.name}: ${error.message}` }));
      fs.appendFileSync(OUT_PATH, JSON.stringify(result) + "\n", "utf8");
      console.log(JSON.stringify({ progress: `${index}/${targets.length}`, storeId: result.storeId, storeName: result.storeName, status: result.status, pickup: result.viewer?.pickup || [], delivery: result.viewer?.delivery || [] }));
      await sleep(1500 + Math.random() * 1200);
    }
  } finally {
    await browser.close();
  }
}

main().catch(error => { console.error(error); process.exit(1); });
