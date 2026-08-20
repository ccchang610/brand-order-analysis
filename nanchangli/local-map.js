(function () {
  let selectedStoreId = "";

  window.platformAuditClaims = function (store) {
    return platformAuditRows(store)
      .filter(row => row.platform && row.evidenceUrl && !/not_found|no_match|error|invalid|closed|historical|blocked|ambiguous/i.test(row.status || ""))
      .map(row => ({
        system: row.platform,
        sourceType: row.sourceType || "third_party",
        orderMode: (row.orderMode || []).length ? row.orderMode : ["unknown"],
        evidenceUrl: row.evidenceUrl,
        label: row.status || row.platform,
        confidence: "platform_lead",
      }));
  };

  function pointFor(store, index) {
    const address = store.address || "";
    const number = Number((address.match(/(\d+)(?:號|之)/) || [0, index + 1])[1]);
    const jitter = ((Number((store.storeId || "").slice(-2)) || index) % 5) * 1.15;
    if (address.includes("海安路")) return [31 + jitter, 61 - Math.min(number, 130) * .26];
    if (address.includes("保安路")) return [24 + Math.min(number, 100) * .43, 55 + jitter * .3];
    if (address.includes("大勇街")) return [58 + jitter * .4, 62 - Math.min(number, 100) * .28];
    if (address.includes("西門路")) return [75 + jitter * .35, 48 - (number % 100) * .16];
    if (address.includes("永華路")) return [24 + Math.min(number, 280) * .18, 28 + jitter * .25];
    if (address.includes("大德街")) return [47 + jitter * .35, 49 - Math.min(number, 90) * .22];
    if (address.includes("國華街")) return [61 + jitter * .3, 46 - Math.min(number, 100) * .18];
    if (address.includes("康樂街")) return [19 + jitter * .35, 46 - Math.min(number, 80) * .16];
    if (address.includes("金華路")) return [8 + jitter, 18];
    if (address.includes("民族路")) return [89 + jitter * .35, 12];
    return [12 + (index % 8) * 10, 66 - Math.floor(index / 8) * 7];
  }

  function escapeHtml(value) {
    return String(value || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  function providerList(items) {
    const providers = [...new Set(items || [])];
    return providers.length
      ? providers.map(provider => `<span class="map-provider">${escapeHtml(provider)}</span>`).join("")
      : `<span class="map-mode-empty">未見供應商</span>`;
  }

  function storePanel(store) {
    if (!store) {
      return `<div class="map-store-placeholder"><b>點選地圖上的店家編號</b><span>被選店家會保持高亮，其他店家則降低彩度。</span></div>`;
    }
    const number = Number((store.storeId || "").slice(-3));
    const hasEntry = storeHasGmbProvider(store);
    const status = hasEntry ? "Google Order 有供應商證據" : "GMB 已確認，未見 Google Order 入口";
    const mapsLink = store.gmbUrl
      ? `<a class="map-store-link" href="${escapeHtml(store.gmbUrl)}" target="_blank" rel="noopener">開啟 GMB / Maps</a>`
      : "";
    return `<button class="map-store-close" type="button" aria-label="關閉店家資訊">×</button><div class="map-store-heading"><span>店家 ${number}</span><div><h3>${escapeHtml(store.storeName)}</h3><p>${escapeHtml(store.address)}</p></div></div>
      <div class="map-store-meta"><span>${escapeHtml(store.phone || "未提供電話")}</span><strong class="${hasEntry ? "has-provider" : "no-entry"}">${status}</strong></div>
      <div class="map-mode-grid"><div><b>自取</b><div>${providerList(store.gmbPickupProviders)}</div></div><div><b>外送</b><div>${providerList(store.gmbDeliveryProviders)}</div></div></div>
      ${mapsLink}`;
  }

  function clearSelection(map) {
    selectedStoreId = "";
    map.querySelectorAll(".pin").forEach(pin => {
      pin.classList.remove("active", "dimmed");
      pin.setAttribute("aria-pressed", "false");
    });
    const panel = map.querySelector(".map-store-panel");
    if (panel) panel.innerHTML = storePanel();
  }

  function bindPanelClose(map) {
    const close = map.querySelector(".map-store-close");
    if (close) close.addEventListener("click", () => clearSelection(map));
  }

  function selectStore(map, storeId) {
    selectedStoreId = storeId;
    const store = stores.find(item => item.storeId === storeId);
    map.querySelectorAll(".pin").forEach(pin => {
      const active = pin.dataset.store === storeId;
      pin.classList.toggle("active", active);
      pin.classList.toggle("dimmed", !active);
      pin.setAttribute("aria-pressed", active ? "true" : "false");
    });
    const panel = map.querySelector(".map-store-panel");
    if (panel) panel.innerHTML = storePanel(store);
    bindPanelClose(map);
  }

  function localRenderMap(rows) {
    const map = document.getElementById("taiwanMap");
    if (!map) return;
    if (selectedStoreId && !rows.some(store => store.storeId === selectedStoreId)) selectedStoreId = "";

    const pins = rows.map((store, index) => {
      const [x, y] = pointFor(store, index);
      const number = Number((store.storeId || "").slice(-3)) || index + 1;
      const status = store.gmbOrderingStatus || "";
      const cls = storeHasGmbProvider(store) ? "provider" : status === "button_confirmed_provider_pending" ? "pending" : status === "no_gmb_profile_match" ? "unmatched" : "";
      const active = selectedStoreId === store.storeId;
      const selectionClass = selectedStoreId ? (active ? " active" : " dimmed") : "";
      const label = `${number}. ${store.storeName}｜${store.address}`;
      return `<g class="pin ${cls}${selectionClass}" data-store="${store.storeId}" tabindex="0" role="button" aria-label="${label}" aria-pressed="${active ? "true" : "false"}" transform="translate(${x.toFixed(1)} ${y.toFixed(1)})"><title>${label}</title><circle class="pin-halo" r="3.45"></circle><circle class="pin-dot" r="2.55"></circle><text y=".15">${number}</text></g>`;
    }).join("");

    const selectedStore = rows.find(store => store.storeId === selectedStoreId);
    map.innerHTML = `<svg viewBox="0 0 100 72" role="img" aria-label="南廠里周邊指定店家街區示意圖">
      <rect class="block" x="1" y="1" width="98" height="70" rx="3"></rect>
      <path class="boundary" d="M17 18 L82 18 L86 61 L18 65 Z"></path>
      <text class="boundary-label" x="20" y="22">南廠里周邊核心區</text>
      <path class="road major" d="M32 3 L32 69"></path><text class="road-label" x="29" y="10" transform="rotate(-90 29 10)">海安路一段</text>
      <path class="road major" d="M77 3 L77 69"></path><text class="road-label" x="74" y="15" transform="rotate(-90 74 15)">西門路一段</text>
      <path class="road" d="M59 4 L59 69"></path><text class="road-label" x="56" y="15" transform="rotate(-90 56 15)">大勇街</text>
      <path class="road" d="M18 4 L18 69"></path><text class="road-label" x="15" y="15" transform="rotate(-90 15 15)">康樂街</text>
      <path class="road major" d="M3 29 L97 29"></path><text class="road-label" x="4" y="27">永華路一段</text>
      <path class="road major" d="M3 56 L97 56"></path><text class="road-label" x="4" y="54">保安路</text>
      <path class="road" d="M3 43 L97 43"></path><text class="road-label" x="4" y="41">大德街／國華街周邊</text>
      ${pins}
    </svg><aside class="map-store-panel" aria-live="polite">${storePanel(selectedStore)}</aside><div class="map-legend"><span><i class="provider"></i>已解析 GMB provider</span><span><i class="pending"></i>入口已確認、provider 待確認</span><span><i></i>GMB 已匹配、無按鈕</span><span><i class="unmatched"></i>GMB 未高信度匹配</span></div>`;

    map.querySelectorAll(".pin").forEach(pin => {
      const activate = () => selectStore(map, pin.dataset.store);
      pin.addEventListener("click", activate);
      pin.addEventListener("keydown", event => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          activate();
        }
      });
    });
    bindPanelClose(map);
  }

  window.renderMap = localRenderMap;
  window.setTimeout(() => {
    try { if (typeof render === "function") render(); } catch (error) { console.error(error); }
  }, 0);
  document.addEventListener("pointerdown", event => {
    if (!selectedStoreId) return;
    const map = document.getElementById("taiwanMap");
    if (!map || event.target.closest(".pin") || event.target.closest(".map-store-panel")) return;
    clearSelection(map);
  });
  document.addEventListener("keydown", event => {
    if (event.key !== "Escape" || !selectedStoreId) return;
    const map = document.getElementById("taiwanMap");
    if (map) clearSelection(map);
  });
})();
