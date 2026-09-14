const FILTERS = [
  {
    id: "market_cap_min",
    label: "Piyasa değeri min",
    defaultParams: { min_usd: 300000000 },
    defaultParamsBist: { min_usd: 10000000000 },
    fields: [{ key: "min_usd", label: "Min" }],
  },
  {
    id: "volume_window_min",
    label: "Son X dk toplam hacim min",
    defaultParams: { minutes: 240, min_volume: 10000 },
    fields: [
      { key: "minutes", label: "Dakika" },
      { key: "min_volume", label: "Min hacim" },
    ],
  },
  {
    id: "open_gap_min",
    label: "Bar açılış artışı (min %)",
    defaultParams: { min_pct: 1 },
    fields: [{ key: "min_pct", label: "Min %" }],
  },
  {
    id: "momentum_positive",
    label: "Momentum pozitif",
    defaultParams: {},
    fields: [],
  },
  {
    id: "price_above_alma",
    label: "Fiyat ALMA üzerinde",
    defaultParams: { period: 144 },
    fields: [{ key: "period", label: "ALMA periyot" }],
  },
  {
    id: "alma_cross",
    label: "ALMA kesişimi (yukarı)",
    defaultParams: { fast: 9, slow: 21 },
    fields: [
      { key: "fast", label: "Hızlı ALMA" },
      { key: "slow", label: "Yavaş ALMA" },
    ],
  },
  {
    id: "ema_cross",
    label: "EMA kesişimi (yukarı)",
    defaultParams: { fast: 9, slow: 21 },
    fields: [
      { key: "fast", label: "Hızlı EMA" },
      { key: "slow", label: "Yavaş EMA" },
    ],
  },
  {
    id: "price_above_ema",
    label: "Fiyat EMA üzerinde",
    defaultParams: { period: 50 },
    fields: [{ key: "period", label: "EMA periyot" }],
  },
  {
    id: "rsi_range",
    label: "RSI aralığı",
    defaultParams: { min: 40, max: 70 },
    fields: [
      { key: "min", label: "Min" },
      { key: "max", label: "Max" },
    ],
  },
  {
    id: "rsi_oversold_bounce",
    label: "RSI aşırı satımdan dönüş",
    defaultParams: { threshold: 30 },
    fields: [{ key: "threshold", label: "Eşik" }],
  },
  {
    id: "adx_trend",
    label: "ADX trend gücü (min)",
    defaultParams: { min: 25 },
    fields: [{ key: "min", label: "Min ADX" }],
  },
  {
    id: "cci_range",
    label: "CCI aralığı",
    defaultParams: { min: -100, max: 100 },
    fields: [
      { key: "min", label: "Min" },
      { key: "max", label: "Max" },
    ],
  },
  {
    id: "atr_expansion",
    label: "ATR genişlemesi",
    defaultParams: { min_ratio: 1.1 },
    fields: [{ key: "min_ratio", label: "Min oran" }],
  },
];

const $ = (sel) => document.querySelector(sel);

let lastScanData = null;
const CUSTOM_SOURCE_KEY = "screenerCustomSourceUniverse";
const SAVED_CUSTOM_LISTS_KEY = "screenerSavedCustomLists";

function getCustomSourceUniverse() {
  const sel = $("#customSourceUniverse");
  if (sel?.value) return sel.value;
  return localStorage.getItem(CUSTOM_SOURCE_KEY) || "sp500";
}

function syncCustomSourceUI() {
  const isCustom = $("#universe")?.value === "custom";
  const sourceWrap = $("#customSourceWrap");
  const symbolsWrap = $("#customSymbolsWrap");
  const saveWrap = $("#customListSaveWrap");
  if (sourceWrap) sourceWrap.hidden = !isCustom;
  if (symbolsWrap) symbolsWrap.hidden = !isCustom;
  if (saveWrap) saveWrap.hidden = !isCustom;
  const sel = $("#customSourceUniverse");
  if (isCustom && sel) {
    const saved = localStorage.getItem(CUSTOM_SOURCE_KEY);
    if (saved) sel.value = saved;
  }
  if (isCustom) refreshSavedCustomListsSelect();
  syncBistProviderUI();
}

function setCustomSourceUniverse(universe) {
  if (universe && universe !== "custom") {
    localStorage.setItem(CUSTOM_SOURCE_KEY, universe);
    const sel = $("#customSourceUniverse");
    if (sel) sel.value = universe;
  }
}

function isBistScanContext() {
  const u = $("#universe")?.value || "sp500";
  return u === "bist" || (u === "custom" && getCustomSourceUniverse() === "bist");
}

let bistProviderMeta = { providers: [], tradingview_auth_configured: false };

async function loadBistProviderOptions() {
  try {
    const res = await apiFetch("/api/config/providers");
    if (!res.ok) return;
    const data = await res.json();
    bistProviderMeta = data;
    const sel = $("#bistDataProvider");
    if (!sel) return;
    const current = sel.value;
    sel.innerHTML = '<option value="">Varsayılan (.env)</option>';
    (data.bist_providers || []).forEach((p) => {
      const opt = document.createElement("option");
      opt.value = p.id;
      opt.textContent = p.label + (p.available === false ? " (yüklü değil)" : "");
      opt.disabled = p.available === false;
      sel.appendChild(opt);
    });
    if (current) sel.value = current;
    updateBistProviderHint();
  } catch {
    /* ignore */
  }
}

function updateBistProviderHint() {
  const hint = $("#bistProviderHint");
  const tvHelp = $("#bistTvHelp");
  const sel = $("#bistDataProvider");
  if (!hint || !sel) return;
  const chosen = sel.value;
  const row = (bistProviderMeta.bist_providers || []).find((p) => p.id === chosen);
  let text = row?.hint || "";
  if (!chosen) {
    text =
      `Varsayılan: ${bistProviderMeta.default_bist_provider || "yfinance"}. ` +
      (bistProviderMeta.borsapy_installed
        ? "borsapy yüklü."
        : "borsapy için pip install borsapy.");
  }
  if (chosen === "borsapy" || (!chosen && bistProviderMeta.default_bist_provider === "borsapy")) {
    if (bistProviderMeta.tradingview_auth_configured) {
      text += " TradingView oturumu bağlı (canlı veri mümkün).";
    } else {
      text += " Canlı BIST için TradingView cookie’lerini .env dosyasına ekleyin.";
    }
  }
  hint.textContent = text;
  if (tvHelp) {
    tvHelp.hidden = chosen !== "borsapy";
  }
}

function syncBistProviderUI() {
  const wrap = $("#bistProviderWrap");
  if (!wrap) return;
  const show = isBistScanContext();
  wrap.hidden = !show;
  if (show) updateBistProviderHint();
}

function getSelectedBistProvider() {
  if (!isBistScanContext()) return null;
  const v = $("#bistDataProvider")?.value?.trim();
  return v || null;
}

function parseSymbolsFromText(text) {
  if (!text || !text.trim()) {
    return [];
  }
  return [
    ...new Set(
      text
        .replace(/,/g, "\n")
        .replace(/;/g, "\n")
        .split("\n")
        .map((s) => s.trim().toUpperCase())
        .filter(Boolean)
    ),
  ].sort();
}

async function parseJsonResponse(res) {
  const text = await res.text();
  if (!text) return { data: {}, text: "" };
  try {
    return { data: JSON.parse(text), text };
  } catch {
    return { data: null, text };
  }
}

const SIGNAL_LABELS = {
  mom_10: "Momentum (10)",
  first_green_bar: "İlk yeşil mum",
  green_now: "Şu an yeşil",
  pine_al: "Pine AL",
  pine_al_mode: "Pine modu",
  pine_al_error: "Pine hata",
  market_cap: "Piyasa değeri",
  market_cap_currency: "Piyasa değeri birimi",
  market_cap_min: "Min piyasa değeri",
  volume_window: "Hacim penceresi",
  volume_window_minutes: "Hacim dk",
  rsi_14: "RSI (14)",
  rsi_bounce: "RSI dönüş",
  adx_14: "ADX (14)",
  cci_20: "CCI (20)",
  atr_ratio: "ATR oranı",
  alma_cross: "ALMA kesişimi",
  ma: "MA (Pine)",
  upper_fib: "Üst Fibo",
};

function signalFieldLabel(key) {
  if (SIGNAL_LABELS[key]) {
    return SIGNAL_LABELS[key];
  }
  const alma = key.match(/^price_above_alma_(\d+)$/);
  if (alma) {
    return `Fiyat ALMA (${alma[1]}) üzerinde`;
  }
  const ema = key.match(/^price_above_ema_(\d+)$/);
  if (ema) {
    return `Fiyat EMA (${ema[1]}) üzerinde`;
  }
  const emaCross = key.match(/^ema_(\d+)_(\d+)_cross$/);
  if (emaCross) {
    return `EMA ${emaCross[1]}/${emaCross[2]} kesişimi`;
  }
  return key.replace(/_/g, " ");
}

function formatSignalValue(value) {
  if (typeof value === "boolean") {
    return value ? "evet" : "hayır";
  }
  if (typeof value === "number") {
    return Number.isInteger(value) ? String(value) : value.toFixed(4).replace(/\.?0+$/, "");
  }
  return String(value);
}

function describeActiveCriteria(scanData) {
  const parts = collectFilters().map((f) => {
    const def = FILTERS.find((x) => x.id === f.id);
    if (!def) {
      return f.id;
    }
    const paramStr = Object.entries(f.params || {})
      .map(([k, v]) => `${k}=${v}`)
      .join(", ");
    return paramStr ? `${def.label} (${paramStr})` : def.label;
  });
  if ($("#requirePineAl").checked) {
    if (scanData?.pine_label) {
      parts.push(`Pine: ${scanData.pine_label}`);
    } else if (scanData?.pine_mode === "first_green_bar") {
      parts.push("Pine: yeşile dönen ilk mum");
    } else {
      parts.push("Pine AL zorunlu");
    }
  }
  if (scanData?.pine_inputs_applied?.length) {
    const cfg = scanData.pine_inputs_applied
      .map((p) => `${p.label}=${p.value}`)
      .join(", ");
    parts.push(`Pine ayar: ${cfg}`);
  }
  return parts.length ? parts.join(" · ") : "Ek filtre yok (yalnızca evren taraması)";
}

function renderSignalSummary(scanData) {
  const box = $("#scanSummary");
  const criteriaEl = $("#scanCriteriaList");
  const dl = $("#scanSignalExample");
  if (!box || !criteriaEl || !dl) {
    return;
  }

  if (!scanData?.results?.length) {
    box.hidden = true;
    criteriaEl.textContent = "";
    dl.innerHTML = "";
    return;
  }

  box.hidden = false;
  criteriaEl.textContent = describeActiveCriteria(scanData);

  const example = scanData.results[0].signals || {};
  dl.innerHTML = Object.entries(example)
    .map(
      ([key, value]) =>
        `<dt>${signalFieldLabel(key)}</dt><dd>${formatSignalValue(value)}</dd>`
    )
    .join("");
}

function isBinanceMarket(universe) {
  const u = universe ?? $("#universe")?.value ?? "sp500";
  if (u === "binance") return true;
  if (u === "custom") return getCustomSourceUniverse() === "binance";
  return false;
}

function effectiveScanMarket(universe, customSource) {
  if (universe === "custom") {
    return customSource || getCustomSourceUniverse() || "sp500";
  }
  return universe || $("#universe")?.value || "sp500";
}

function formatPrice(price, universe) {
  if (price == null || Number.isNaN(Number(price))) {
    return "—";
  }
  const u = universe || $("#universe")?.value || "sp500";
  if (isBistMarket(u)) {
    return new Intl.NumberFormat("tr-TR", {
      style: "currency",
      currency: "TRY",
      maximumFractionDigits: 2,
    }).format(price);
  }
  if (isBinanceMarket(u)) {
    const digits = price >= 1 ? 2 : price >= 0.01 ? 4 : 8;
    return (
      new Intl.NumberFormat("en-US", {
        minimumFractionDigits: 0,
        maximumFractionDigits: digits,
      }).format(price) + " USDT"
    );
  }
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 2,
  }).format(price);
}

function toTradingViewSymbol(symbol, universe) {
  const sym = String(symbol).trim().toUpperCase();
  if (isBistMarket(universe)) {
    return sym.startsWith("BIST:") ? sym : `BIST:${sym}`;
  }
  if (universe === "binance" || (universe === "custom" && getCustomSourceUniverse() === "binance")) {
    if (sym.startsWith("BINANCE:")) return sym;
    const base = sym.replace(/USDT$/i, "");
    return `BINANCE:${base}USDT`;
  }
  return sym;
}

function triggerFileDownload(filename, text) {
  const content = text.endsWith("\n") ? text : `${text}\n`;
  const blob = new Blob([content], { type: "text/plain;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.rel = "noopener";
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

function buildTvLinesFromScan(scanData, universe) {
  const fromApi = (scanData.tradingview_symbols || [])
    .map((s) => String(s).trim())
    .filter(Boolean);
  if (fromApi.length) {
    return [...new Set(fromApi)].sort();
  }
  const fromResults = (scanData.results || [])
    .map((r) => toTradingViewSymbol(r.symbol, universe))
    .filter(Boolean);
  return [...new Set(fromResults)].sort();
}

async function downloadTradingViewList() {
  const hasResults =
    (lastScanData?.results?.length || 0) > 0 ||
    (lastScanData?.tradingview_symbols?.length || 0) > 0;
  if (!hasResults) {
    setStatus("İndirilecek sonuç yok. Önce tarama yapın.", "error");
    return;
  }

  const universe =
    lastScanData.market || lastScanData.universe || $("#universe").value;
  const lines = buildTvLinesFromScan(lastScanData, universe);
  if (!lines.length) {
    setStatus("Liste boş.", "error");
    return;
  }

  const symbols = (lastScanData.results || []).map((r) => r.symbol).filter(Boolean);
  const text = `${lines.join("\n")}\n`;
  const ts = new Date().toISOString().slice(0, 16).replace(/[:T]/g, "-");
  const filename = `tradingview_${universe}_${ts}.txt`;

  setStatus("TradingView listesi hazırlanıyor…");

  try {
    const res = await apiFetch("/api/export/tradingview", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ symbols, universe }),
    });
    if (res.ok) {
      const serverText = await res.text();
      triggerFileDownload(filename, serverText.trim() ? serverText : text);
      setStatus(`${lines.length} sembol indirildi.`, "ok");
      return;
    }
  } catch {
    /* network — fall back to client-side file */
  }

  try {
    triggerFileDownload(filename, text);
    setStatus(`${lines.length} sembol indirildi (yerel dosya).`, "ok");
  } catch (e) {
    setStatus("İndirme başarısız: " + e.message, "error");
  }
}

function formatGroupedNumber(num) {
  if (num == null || Number.isNaN(Number(num))) {
    return "";
  }
  const n = Math.trunc(Number(num));
  return String(n).replace(/\B(?=(\d{3})+(?!\d))/g, ".");
}

function parseGroupedNumber(str) {
  if (str == null || str === "") {
    return NaN;
  }
  const cleaned = String(str).replace(/\s/g, "").replace(/\./g, "");
  return parseFloat(cleaned);
}

function isBistMarket(universe) {
  const u = universe ?? $("#universe")?.value ?? "sp500";
  if (u === "bist") return true;
  if (u === "custom") return getCustomSourceUniverse() === "bist";
  return false;
}

function getMarketCapFilterMeta() {
  if (isBistMarket()) {
    return {
      unit: "TL",
      example: formatGroupedNumber(10000000000),
      defaultVal: 10000000000,
    };
  }
  return {
    unit: "USD",
    example: formatGroupedNumber(300000000),
    defaultVal: 300000000,
  };
}

function marketCapFilterTitle() {
  const { unit } = getMarketCapFilterMeta();
  return `Piyasa değeri min (${unit})`;
}

function syncMarketCapFilterUI() {
  const item = document.querySelector('.filter-item[data-id="market_cap_min"]');
  if (!item) return;
  const meta = getMarketCapFilterMeta();
  const title = marketCapFilterTitle();
  const titleEl = item.querySelector(".filter-title");
  if (titleEl) titleEl.textContent = title;
  const paramLabel = item.querySelector(".filter-param-label");
  if (paramLabel) paramLabel.textContent = `Min (${meta.unit})`;
  const example = item.querySelector(".filter-param-example");
  if (example) example.textContent = `örn. ${meta.example} ${meta.unit}`;
  const inp = item.querySelector('[data-param="min_usd"]');
  if (inp && document.activeElement !== inp) {
    const n = parseGroupedNumber(inp.value);
    if (Number.isNaN(n)) {
      inp.value = formatGroupedNumber(meta.defaultVal);
    }
  }
}

function bindMarketCapInput() {
  const inp = document.querySelector(
    '[data-filter="market_cap_min"][data-param="min_usd"]'
  );
  if (!inp || inp.dataset.bound === "1") {
    return;
  }
  inp.dataset.bound = "1";
  inp.type = "text";
  inp.inputMode = "numeric";
  inp.autocomplete = "off";

  const formatField = () => {
    const n = parseGroupedNumber(inp.value);
    if (!Number.isNaN(n) && n >= 0) {
      inp.value = formatGroupedNumber(n);
    }
  };

  inp.addEventListener("blur", formatField);
  inp.addEventListener("change", formatField);
}

function buildFilterItemHtml(f) {
  let itemLabel = f.label;
  let paramsHtml = "";

  if (f.id === "market_cap_min") {
    const meta = getMarketCapFilterMeta();
    const def = isBistMarket()
      ? f.defaultParamsBist?.min_usd ?? meta.defaultVal
      : f.defaultParams.min_usd ?? meta.defaultVal;
    itemLabel = marketCapFilterTitle();
    paramsHtml = `
      <div class="filter-param-block">
        <label class="filter-param">
          <span class="filter-param-label">Min (${meta.unit})</span>
          <input type="text" inputmode="numeric" autocomplete="off"
            class="market-cap-input" data-filter="${f.id}" data-param="min_usd"
            value="${formatGroupedNumber(def)}" />
        </label>
        <span class="filter-param-example">örn. ${meta.example} ${meta.unit}</span>
      </div>`;
  } else {
    paramsHtml = f.fields
      .map(
        (field) => `
      <label class="filter-param">
        <span class="filter-param-label">${field.label}</span>
        <input type="number" step="any" data-filter="${f.id}" data-param="${field.key}"
          value="${f.defaultParams[field.key] ?? ""}" />
      </label>`
      )
      .join("");
  }

  return `
    <div class="filter-item" data-id="${f.id}">
      <label class="check">
        <input type="checkbox" class="filter-enable" data-id="${f.id}" />
        <span class="filter-title">${itemLabel}</span>
      </label>
      ${f.fields.length ? `<div class="filter-params">${paramsHtml}</div>` : ""}
    </div>`;
}

function renderFilters() {
  const mid = Math.ceil(FILTERS.length / 2);
  const colA = $("#filterListColA");
  const colB = $("#filterListColB");
  if (!colA || !colB) return;
  colA.innerHTML = FILTERS.slice(0, mid).map(buildFilterItemHtml).join("");
  colB.innerHTML = FILTERS.slice(mid).map(buildFilterItemHtml).join("");
  bindMarketCapInput();
}

function collectFilters() {
  return FILTERS.map((f) => {
    const enabled = document.querySelector(`.filter-enable[data-id="${f.id}"]`)?.checked;
    const params = { ...f.defaultParams };
    document.querySelectorAll(`[data-filter="${f.id}"][data-param]`).forEach((inp) => {
      const v =
        f.id === "market_cap_min" && inp.dataset.param === "min_usd"
          ? parseGroupedNumber(inp.value)
          : parseFloat(inp.value);
      if (!Number.isNaN(v)) params[inp.dataset.param] = v;
    });
    return { id: f.id, enabled: !!enabled, params };
  }).filter((x) => x.enabled);
}

function countCustomSymbols(text) {
  return parseSymbolsFromText(text).length;
}

function setCustomListExportEnabled(enabled) {
  const btnTv = $("#btnExportTv");
  const btnCustom = $("#btnAddToCustomList");
  const btnTrack = $("#btnTrackResults");
  if (btnTv) btnTv.disabled = !enabled;
  if (btnCustom) btnCustom.disabled = !enabled;
  if (btnTrack) btnTrack.disabled = !enabled;
}

function loadSavedCustomLists() {
  try {
    const raw = localStorage.getItem(SAVED_CUSTOM_LISTS_KEY);
    const data = raw ? JSON.parse(raw) : {};
    return data && typeof data === "object" && !Array.isArray(data) ? data : {};
  } catch {
    return {};
  }
}

function persistSavedCustomLists(map) {
  localStorage.setItem(SAVED_CUSTOM_LISTS_KEY, JSON.stringify(map));
}

function refreshSavedCustomListsSelect(selectedName) {
  const sel = $("#savedCustomLists");
  if (!sel) return;
  const map = loadSavedCustomLists();
  const names = Object.keys(map).sort((a, b) =>
    a.localeCompare(b, "tr", { sensitivity: "base" })
  );
  const keep = selectedName ?? sel.value;
  sel.innerHTML = '<option value="">Kayıtlı liste seç…</option>';
  names.forEach((name) => {
    const opt = document.createElement("option");
    opt.value = name;
    const n = parseSymbolsFromText(map[name]?.symbols || "").length;
    const src = map[name]?.source || "?";
    opt.textContent = `${name} (${n} · ${src})`;
    sel.appendChild(opt);
  });
  if (keep && map[keep]) sel.value = keep;
}

function saveCurrentCustomList(explicitName) {
  const symbols = parseSymbolsFromText($("#customSymbols")?.value || "");
  if (!symbols.length) {
    setStatus("Kaydedilecek sembol yok.", "error");
    return false;
  }
  let name = (explicitName ?? $("#customListName")?.value ?? "").trim();
  if (!name) {
    name = (prompt("Liste adı girin:", $("#customListName")?.value || "") || "").trim();
  }
  if (!name) {
    setStatus("Kayıt iptal — isim gerekli.", "error");
    return false;
  }
  const map = loadSavedCustomLists();
  if (map[name]) {
    const ok = confirm(`«${name}» zaten var. Üzerine yazılsın mı?`);
    if (!ok) return false;
  }
  map[name] = {
    symbols: symbols.join("\n"),
    source: getCustomSourceUniverse(),
    updatedAt: new Date().toISOString(),
  };
  persistSavedCustomLists(map);
  if ($("#customListName")) $("#customListName").value = name;
  refreshSavedCustomListsSelect(name);
  setStatus(`«${name}» kaydedildi (${symbols.length} sembol).`, "ok");
  return true;
}

function loadSelectedCustomList() {
  const name = $("#savedCustomLists")?.value;
  if (!name) {
    setStatus("Yüklenecek kayıtlı liste seçin.", "error");
    return;
  }
  const entry = loadSavedCustomLists()[name];
  if (!entry) {
    setStatus("Kayıt bulunamadı.", "error");
    refreshSavedCustomListsSelect();
    return;
  }
  const symbols = parseSymbolsFromText(entry.symbols || "");
  $("#customSymbols").value = symbols.join("\n");
  $("#universe").value = "custom";
  if (entry.source) setCustomSourceUniverse(entry.source);
  if ($("#customListName")) $("#customListName").value = name;
  syncCustomSourceUI();
  applyMaxSymbols(symbols.length, name);
  syncMarketCapFilterUI();
  setStatus(`«${name}» yüklendi (${symbols.length} sembol).`, "ok");
}

function deleteSelectedCustomList() {
  const name = $("#savedCustomLists")?.value;
  if (!name) {
    setStatus("Silinecek kayıtlı liste seçin.", "error");
    return;
  }
  if (!confirm(`«${name}» silinsin mi?`)) return;
  const map = loadSavedCustomLists();
  delete map[name];
  persistSavedCustomLists(map);
  if ($("#customListName")?.value === name) $("#customListName").value = "";
  refreshSavedCustomListsSelect();
  setStatus(`«${name}» silindi.`, "ok");
}

function addResultsToCustomList() {
  if (!lastScanData?.results?.length) {
    setStatus("Önce tarama yapın.", "error");
    return;
  }

  const sourceUniverse = lastScanData.universe || $("#universe").value;
  const newSyms = lastScanData.results
    .map((r) => String(r.symbol).trim().toUpperCase())
    .filter(Boolean);
  const existing = parseSymbolsFromText($("#customSymbols").value);
  const prevSource = getCustomSourceUniverse();

  if (
    existing.length &&
    prevSource !== sourceUniverse &&
    sourceUniverse !== "custom"
  ) {
    const ok = confirm(
      `Özel listede ${prevSource} piyasasından semboller var. ` +
        `${sourceUniverse} sonuçlarıyla birleştirilsin mi?`
    );
    if (!ok) {
      return;
    }
  }

  const merged = [...new Set([...existing, ...newSyms])].sort();
  $("#customSymbols").value = merged.join("\n");
  $("#universe").value = "custom";
  $("#customSymbolsWrap").hidden = false;
  if (sourceUniverse !== "custom") {
    setCustomSourceUniverse(sourceUniverse);
  }
  syncCustomSourceUI();
  applyMaxSymbols(merged.length, "Özel liste");
  syncMarketCapFilterUI();

  const suggested =
    ($("#customListName")?.value || "").trim() ||
    `${getCustomSourceUniverse().toUpperCase()} ${new Date().toLocaleDateString("tr-TR")}`;
  const name = (prompt("Özel liste adı (kaydetmek için):", suggested) || "").trim();
  if (name) {
    if ($("#customListName")) $("#customListName").value = name;
    saveCurrentCustomList(name);
  } else {
    setStatus(
      `${newSyms.length} sembol özel listeye eklendi (toplam ${merged.length}). Kaydetmek için isim verin.`,
      "ok"
    );
  }
}

function applyMaxSymbols(count, labelText, fetchOk = true, message = null) {
  const input = $("#maxSymbols");
  const label = $("#maxSymbolsLabel");
  const n = Math.max(1, count);
  input.value = String(n);
  input.max = String(Math.max(n, 20000));
  input.min = "1";
  label.textContent = `Maks. taranacak hisse (evrende ${n})`;
  if (labelText) {
    let info = `${labelText} · ${n} hisse`;
    if (!fetchOk) info += " — liste yüklenemedi";
    else if (message) info += " (önbellek)";
    $("#universeInfo").textContent = info;
  }
  if (!fetchOk && message) {
    setStatus(message, "error");
  }
}

async function loadUniverseInfo() {
  const universe = $("#universe")?.value || "sp500";

  if (universe === "custom") {
    syncCustomSourceUI();
    const n = countCustomSymbols($("#customSymbols").value);
    const src = getCustomSourceUniverse();
    const srcLabels = {
      bist: "BIST",
      sp500: "S&P 500",
      nasdaq: "NASDAQ",
      nyse: "NYSE",
      all_us: "ABD (tümü)",
      binance: "Binance",
    };
    applyMaxSymbols(n, `Özel liste (${srcLabels[src] || src})`);
    const pineHelpBist = $("#pineHelpBist");
    if (pineHelpBist) pineHelpBist.hidden = src !== "bist";
    return;
  }

  try {
    const res = await apiFetch(`/api/symbols/info?universe=${encodeURIComponent(universe)}`);
    const data = await res.json();
    applyMaxSymbols(data.count, data.label, data.fetch_ok !== false, data.message);
    const pineHelpBist = $("#pineHelpBist");
    if (pineHelpBist) pineHelpBist.hidden = universe !== "bist";
    if (data.fetch_ok === false && data.count < 100) {
      setStatus(
        data.message ||
          "Hisse listesi indirilemedi. «Listeyi yenile» ile tekrar deneyin veya özel liste kullanın.",
        "error"
      );
    }
  } catch {
    $("#universeInfo").textContent = "Evren yüklenemedi";
    $("#maxSymbolsLabel").textContent = "Maks. taranacak hisse";
    setStatus("Evren bilgisi alınamadı.", "error");
  }
}

async function loadSavedPine() {
  const sel = $("#savedPine");
  const prev = sel.value;
  const res = await apiFetch("/api/pine/scripts");
  const scripts = await res.json();
  sel.innerHTML = '<option value="">— Seçin —</option>';
  scripts.forEach((s) => {
    const opt = document.createElement("option");
    opt.value = s.id;
    const status = !s.available ? "eksik" : s.al_condition ? "AL ✓" : "AL ?";
    opt.textContent = `${s.name} (${status})`;
    opt.dataset.available = s.available ? "1" : "0";
    opt.dataset.condition = s.al_condition || "";
    sel.appendChild(opt);
  });
  updateDeleteMissingPineButton(scripts);
  if (prev) sel.value = prev;
  onPineSelect();
}

function updateDeleteMissingPineButton(scripts) {
  const btn = $("#btnDeleteMissingPine");
  if (!btn) return;
  const missing = (scripts || []).filter((s) => !s.available);
  btn.disabled = missing.length === 0;
  btn.textContent =
    missing.length > 0 ? `Eksikleri sil (${missing.length})` : "Eksikleri sil";
}

let currentPineScriptId = null;
let currentPineParameters = [];
let currentPineHasSavedDefaults = false;

function pineParamValue(p) {
  if (p.value !== undefined && p.value !== null && p.value !== "") {
    return p.value;
  }
  return p.default;
}

function updatePineParamsHint() {
  const hint = $("#pineParamsHint");
  if (!hint) return;
  hint.textContent = currentPineHasSavedDefaults
    ? "Kayıtlı varsayılanlar yüklendi. Değiştirip «Varsayılan olarak kaydet» ile güncelleyebilirsiniz."
    : "Pine dosyası varsayılanları. Değiştirip «Varsayılan olarak kaydet» ile kalıcı kaydedin.";
}

function renderPineInputField(p, value) {
  const min = p.min !== undefined ? ` min="${p.min}"` : "";
  const max = p.max !== undefined ? ` max="${p.max}"` : "";
  const step = p.step !== undefined ? ` step="${p.step}"` : p.type === "float" ? ' step="0.1"' : "";
  if (p.type === "bool") {
    const checked = value === true || value === "true" ? " checked" : "";
    return `<input type="checkbox" data-pine-input="${p.name}" data-pine-type="bool"${checked} />`;
  }
  if (p.options?.length) {
    const opts = p.options
      .map((o) => {
        const sel = String(value) === String(o) ? " selected" : "";
        return `<option value="${o}"${sel}>${o}</option>`;
      })
      .join("");
    return `<select data-pine-input="${p.name}" data-pine-type="string">${opts}</select>`;
  }
  if (p.type === "int" || p.type === "float") {
    return `<input type="number" data-pine-input="${p.name}" data-pine-type="${p.type}" value="${value}"${min}${max}${step} />`;
  }
  return `<input type="text" data-pine-input="${p.name}" data-pine-type="string" value="${value}" />`;
}

function renderPineParams(parameters, scriptId, hasSavedDefaults = false) {
  const box = $("#pineParamsBox");
  const form = $("#pineInputsForm");
  if (!box || !form) return;

  currentPineScriptId = scriptId || null;
  currentPineParameters = parameters || [];
  currentPineHasSavedDefaults = !!hasSavedDefaults;
  const editable = (parameters || []).filter((p) => p.group !== "Visual");

  if (!editable.length) {
    box.hidden = true;
    form.innerHTML = "";
    return;
  }

  box.hidden = false;
  updatePineParamsHint();

  const groups = [];
  const byGroup = new Map();
  editable.forEach((p) => {
    const g = p.group || "General";
    if (!byGroup.has(g)) {
      byGroup.set(g, []);
      groups.push(g);
    }
    byGroup.get(g).push(p);
  });

  form.innerHTML = groups
    .map((group) => {
      const rows = byGroup
        .get(group)
        .map((p) => {
          const val = pineParamValue(p);
          return `
        <div class="pine-input-row">
          <label>
            <span class="pine-input-label">${p.label}</span>
            <span class="pine-input-name">${p.name}</span>
          </label>
          ${renderPineInputField(p, val)}
        </div>`;
        })
        .join("");
      return `<div class="pine-input-group-title">${group}</div>${rows}`;
    })
    .join("");

}

async function savePineInputsAsDefault() {
  if (!currentPineScriptId) {
    setStatus("Önce bir Pine script seçin.", "error");
    return;
  }
  const overrides = collectPineInputs();
  setStatus("Parametreler kaydediliyor…");
  try {
    const res = await apiFetch(`/api/pine/scripts/${currentPineScriptId}/input-defaults`, {
      method: "PUT",
      body: JSON.stringify({ overrides }),
    });
    const { data, text } = await parseJsonResponse(res);
    if (!res.ok) {
      setStatus(data?.detail || text?.slice(0, 200) || "Kayıt hatası", "error");
      return;
    }
    currentPineHasSavedDefaults = !!data.has_saved_defaults;
    updatePineParamsHint();
    setStatus(data.message || "Kaydedildi.", "ok");
  } catch (e) {
    setStatus("Kayıt hatası: " + e.message, "error");
  }
}

async function resetPineInputsToDefaults() {
  if (!currentPineScriptId) return;
  if (
    currentPineHasSavedDefaults &&
    !confirm("Kayıtlı varsayılanlar silinsin ve Pine dosyası değerlerine dönülsün mü?")
  ) {
    return;
  }
  if (!currentPineHasSavedDefaults) {
    renderPineParams(
      currentPineParameters.map((p) => ({ ...p, value: p.pine_default ?? p.default })),
      currentPineScriptId,
      false
    );
    setStatus("Pine dosyası varsayılanları yüklendi.", "ok");
    return;
  }
  try {
    const res = await apiFetch(`/api/pine/scripts/${currentPineScriptId}/input-defaults`, {
      method: "DELETE",
    });
    const { data, text } = await parseJsonResponse(res);
    if (!res.ok) {
      setStatus(data?.detail || text?.slice(0, 200) || "Sıfırlama hatası", "error");
      return;
    }
    currentPineHasSavedDefaults = false;
    renderPineParams(data.parameters || [], currentPineScriptId, false);
    setStatus(data.message || "Varsayılanlara dönüldü.", "ok");
  } catch (e) {
    setStatus("Sıfırlama hatası: " + e.message, "error");
  }
}

function collectPineInputs() {
  const form = $("#pineInputsForm");
  if (!form) return {};
  const out = {};
  form.querySelectorAll("[data-pine-input]").forEach((el) => {
    const name = el.dataset.pineInput;
    const type = el.dataset.pineType;
    if (type === "bool") {
      out[name] = el.checked;
    } else if (type === "int") {
      const v = parseInt(el.value, 10);
      if (!Number.isNaN(v)) out[name] = v;
    } else if (type === "float") {
      const v = parseFloat(el.value);
      if (!Number.isNaN(v)) out[name] = v;
    } else {
      out[name] = el.value;
    }
  });
  return out;
}

async function loadPineParamsForScript(id) {
  if (!id) {
    renderPineParams([], null);
    return;
  }
  try {
    const res = await apiFetch(`/api/pine/scripts/${id}`);
    const data = await res.json();
    renderPineParams(data.parameters || [], id, data.has_saved_defaults);
  } catch {
    renderPineParams([], id, false);
  }
}

function onPineSelect() {
  const sel = $("#savedPine");
  const opt = sel.selectedOptions[0];
  const box = $("#pineConditionBox");
  const text = $("#pineConditionText");
  const btnDel = $("#btnDeletePine");
  if (btnDel) btnDel.disabled = !sel.value;

  if (!sel.value) {
    box.hidden = true;
    text.textContent = "";
    renderPineParams([], null);
    return;
  }

  const isMissing = opt?.dataset.available === "0";
  box.hidden = false;
  if (isMissing) {
    text.textContent =
      "Dosya içeriği bulunamadı. Bu kayıt taramada kullanılamaz; «Sil» veya «Eksikleri sil» ile kaldırabilirsiniz.";
    text.classList.add("warn");
    renderPineParams([], null);
    return;
  }
  text.classList.remove("warn");
  text.textContent = opt?.dataset.condition || "AL koşulu tespit edilmedi.";
  loadPineParamsForScript(sel.value);
}

async function deletePineScriptById(id, displayName) {
  const res = await apiFetch(`/api/pine/scripts/${id}`, { method: "DELETE" });
  if (!res.ok) {
    const { data } = await parseJsonResponse(res);
    throw new Error(data?.detail || "Silme hatası");
  }
  if (displayName) {
    return displayName;
  }
}

async function deletePineScript() {
  const sel = $("#savedPine");
  const id = sel.value;
  if (!id) {
    setStatus("Silmek için bir script seçin.", "error");
    return;
  }
  const name = sel.selectedOptions[0]?.textContent || id;
  if (!confirm(`"${name}" kaydını silmek istediğinize emin misiniz?`)) {
    return;
  }

  try {
    await deletePineScriptById(id);
  } catch (e) {
    setStatus(e.message, "error");
    return;
  }

  sel.value = "";
  $("#pineConditionBox").hidden = true;
  $("#pineConditionText").textContent = "";
  $("#btnDeletePine").disabled = true;
  await loadSavedPine();
  setStatus("Kayıtlı script silindi.", "ok");
}

async function deleteMissingPineScripts() {
  const res = await apiFetch("/api/pine/scripts");
  const scripts = await res.json();
  const missing = scripts.filter((s) => !s.available);
  if (!missing.length) {
    setStatus("Silinecek eksik kayıt yok.", "ok");
    return;
  }
  if (
    !confirm(
      `${missing.length} eksik kayıt kalıcı olarak silinsin mi?\n\n${missing.map((s) => s.name).join(", ")}`
    )
  ) {
    return;
  }

  let removed = 0;
  for (const s of missing) {
    try {
      await deletePineScriptById(s.id);
      removed += 1;
    } catch (e) {
      setStatus(`${s.name}: ${e.message}`, "error");
      await loadSavedPine();
      return;
    }
  }

  $("#savedPine").value = "";
  $("#pineConditionBox").hidden = true;
  $("#pineConditionText").textContent = "";
  $("#btnDeletePine").disabled = true;
  await loadSavedPine();
  setStatus(`${removed} eksik kayıt silindi.`, "ok");
}

async function uploadPine() {
  const file = $("#pineFile").files[0];
  if (!file) {
    setStatus("Lütfen bir Pine dosyası seçin.", "error");
    return;
  }
  const fd = new FormData();
  fd.append("file", file);
  fd.append("name", $("#pineName").value.trim());

  setStatus("Yükleniyor ve AL koşulu aranıyor…");
  const res = await apiFetch("/api/pine/upload", { method: "POST", body: fd });
  const { data, text } = await parseJsonResponse(res);
  if (!res.ok) {
    setStatus(data?.detail || text?.slice(0, 200) || "Yükleme hatası", "error");
    return;
  }
  setStatus(data.message, data.al_detected ? "ok" : "error");
  if (data.al_condition) {
    $("#pineConditionBox").hidden = false;
    $("#pineConditionText").textContent = data.al_condition;
  }
  renderPineParams(data.parameters || [], data.id, false);
  await loadSavedPine();
  $("#savedPine").value = String(data.id);
}

function collectScanBody() {
  const universe = $("#universe").value;
  return {
    universe,
    custom_symbols: $("#customSymbols").value,
    custom_source_universe: universe === "custom" ? getCustomSourceUniverse() : null,
    timeframe: $("#timeframe").value,
    filters: collectFilters(),
    pine_script_id: $("#savedPine").value ? parseInt($("#savedPine").value, 10) : null,
    pine_condition_override: $("#pineOverride").value.trim() || null,
    pine_input_overrides: $("#savedPine").value ? collectPineInputs() : {},
    require_pine_al: $("#requirePineAl").checked,
    max_symbols: parseInt($("#maxSymbols").value, 10) || 80,
    bist_data_provider: getSelectedBistProvider(),
  };
}

const SCHEDULE_TYPE_LABELS = {
  hourly: "Saatlik",
  every_4h: "4 saatte bir",
  daily: "Günlük",
  weekly: "Haftalık",
};

const SCHEDULE_WEEKDAY_LABELS = ["Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz"];

let editingScheduleId = null;
let scheduledScansById = {};
let scheduleJobNextRuns = {};

function setScheduleWeekdays(days) {
  const selected = new Set(
    days?.length ? days : [0, 1, 2, 3, 4, 5, 6],
  );
  document.querySelectorAll("#scheduleWeekdays input").forEach((el) => {
    el.checked = selected.has(parseInt(el.value, 10));
  });
}

function applyPineInputOverrides(overrides) {
  if (!overrides) return;
  Object.entries(overrides).forEach(([name, val]) => {
    const inp = document.querySelector(`[data-pine-input="${CSS.escape(name)}"]`);
    if (!inp) return;
    if (inp.type === "checkbox") {
      inp.checked = val === true || val === "true";
    } else {
      inp.value = val;
    }
  });
}

async function applyScanConfigToUI(cfg) {
  if (!cfg) return;
  $("#universe").value = cfg.universe || "sp500";
  $("#customSymbolsWrap").hidden = cfg.universe !== "custom";
  if (cfg.custom_symbols != null) {
    $("#customSymbols").value = cfg.custom_symbols;
  }
  if (cfg.custom_source_universe) {
    setCustomSourceUniverse(cfg.custom_source_universe);
  }
  syncCustomSourceUI();
  $("#timeframe").value = cfg.timeframe || "1d";
  if (cfg.bist_data_provider && $("#bistDataProvider")) {
    $("#bistDataProvider").value = cfg.bist_data_provider;
  }
  updateBistProviderHint();
  if (cfg.max_symbols != null) {
    $("#maxSymbols").value = cfg.max_symbols;
  }
  $("#requirePineAl").checked = !!cfg.require_pine_al;
  $("#pineOverride").value = cfg.pine_condition_override || "";
  const pineHelpBist = $("#pineHelpBist");
  if (pineHelpBist) pineHelpBist.hidden = cfg.universe !== "bist";
  syncMarketCapFilterUI();

  const bist =
    cfg.universe === "bist" ||
    (cfg.universe === "custom" && cfg.custom_source_universe === "bist");
  FILTERS.forEach((f) => {
    const cb = document.querySelector(`.filter-enable[data-id="${f.id}"]`);
    if (cb) cb.checked = false;
    const defs =
      f.id === "market_cap_min" && bist
        ? f.defaultParamsBist || f.defaultParams
        : f.defaultParams;
    f.fields.forEach(({ key }) => {
      const inp = document.querySelector(`[data-filter="${f.id}"][data-param="${key}"]`);
      if (!inp) return;
      const def = defs[key];
      if (f.id === "market_cap_min" && key === "min_usd") {
        inp.value = formatGroupedNumber(def);
      } else if (def != null) {
        inp.value = def;
      }
    });
  });

  (cfg.filters || []).forEach((f) => {
    const cb = document.querySelector(`.filter-enable[data-id="${f.id}"]`);
    if (cb) cb.checked = !!f.enabled;
    Object.entries(f.params || {}).forEach(([key, val]) => {
      const inp = document.querySelector(
        `[data-filter="${f.id}"][data-param="${key}"]`,
      );
      if (!inp || val == null) return;
      if (f.id === "market_cap_min" && key === "min_usd") {
        inp.value = formatGroupedNumber(val);
      } else {
        inp.value = val;
      }
    });
  });

  if (cfg.pine_script_id) {
    $("#savedPine").value = String(cfg.pine_script_id);
    const opt = $("#savedPine").selectedOptions[0];
    const box = $("#pineConditionBox");
    const text = $("#pineConditionText");
    if (box) box.hidden = false;
    if (opt?.dataset.available === "0") {
      if (text) {
        text.textContent =
          "Dosya içeriği bulunamadı. Bu kayıt taramada kullanılamaz; «Sil» veya «Eksikleri sil» ile kaldırabilirsiniz.";
        text.classList.add("warn");
      }
    } else if (text) {
      text.classList.remove("warn");
      text.textContent = opt?.dataset.condition || "AL koşulu tespit edilmedi.";
    }
    if ($("#btnDeletePine")) $("#btnDeletePine").disabled = false;
    await loadPineParamsForScript(cfg.pine_script_id);
    applyPineInputOverrides(cfg.pine_input_overrides);
  } else {
    $("#savedPine").value = "";
    onPineSelect();
  }
  loadUniverseInfo();
}

function fillScheduleFormFromRow(row) {
  $("#scheduleName").value = row.name || "";
  $("#scheduleType").value = row.schedule_type || "daily";
  const windowed = isWindowScheduleType(row.schedule_type);
  if (windowed) {
    $("#scheduleStartHour").value = row.hour ?? 10;
    $("#scheduleEndHour").value = row.end_hour ?? 18;
    $("#scheduleWindowMinute").value = row.minute ?? 0;
  } else {
    $("#scheduleHour").value = row.hour ?? 8;
    $("#scheduleMinute").value = row.minute ?? 30;
  }
  const days =
    row.weekdays?.length
      ? row.weekdays
      : row.schedule_type === "daily" || windowed
        ? [0, 1, 2, 3, 4, 5, 6]
        : [];
  setScheduleWeekdays(days);
  $("#scheduleTimezone").value = row.timezone || "Europe/Istanbul";
  $("#scheduleEmail").value = row.email_to || "";
  updateScheduleFormVisibility();
}

function resetScheduleModalForCreate() {
  editingScheduleId = null;
  const title = $("#scheduleModalTitle");
  const hint = $("#scheduleModalHint");
  const submitBtn = $("#scheduleSubmitBtn");
  if (title) title.textContent = "Zamanlanmış tarama oluştur";
  if (hint) {
    hint.innerHTML =
      "Mevcut evren, filtreler, Pine ayarları ve zaman dilimi kaydedilir. TV listesi e-postası yalnızca tarama <strong>çalıştığında</strong> gönderilir (Şimdi veya planlanan saatte).";
  }
  if (submitBtn) submitBtn.textContent = "Oluştur";
  $("#scheduleScanForm")?.reset();
  setScheduleWeekdays([0, 1, 2, 3, 4, 5, 6]);
  updateScheduleFormVisibility();
}

function setScheduleModalEditMode(row) {
  editingScheduleId = row.id;
  const title = $("#scheduleModalTitle");
  const hint = $("#scheduleModalHint");
  const submitBtn = $("#scheduleSubmitBtn");
  if (title) title.textContent = "Zamanlanmış tarama düzenle";
  if (hint) {
    hint.innerHTML =
      "Zamanlama ve e-posta buradan güncellenir. <strong>Kaydet</strong> ayrıca üstteki evren, filtreler ve Pine ayarlarını da bu taramaya yazar.";
  }
  if (submitBtn) submitBtn.textContent = "Kaydet";
  fillScheduleFormFromRow(row);
}

function parseUtcIso(iso) {
  if (!iso) return null;
  if (iso.endsWith("Z") || /[+-]\d{2}:\d{2}$/.test(iso)) return new Date(iso);
  return new Date(`${iso}Z`);
}

function formatLocalDateTime(iso, timeZone = "Europe/Istanbul") {
  const d = parseUtcIso(iso);
  if (!d || Number.isNaN(d.getTime())) return iso || "";
  return d.toLocaleString("tr-TR", { timeZone });
}

function getSelectedScheduleWeekdays() {
  return [...document.querySelectorAll("#scheduleWeekdays input:checked")]
    .map((el) => parseInt(el.value, 10))
    .sort((a, b) => a - b);
}

function formatWeekdaysList(days) {
  if (!days?.length) return "";
  return days.map((d) => SCHEDULE_WEEKDAY_LABELS[d] || d).join(", ");
}

function formatScheduleTime(row) {
  const m = String(row.minute).padStart(2, "0");
  const tz = row.timezone || "Europe/Istanbul";
  if (row.schedule_type === "hourly") {
    const start = String(row.hour).padStart(2, "0");
    const end =
      row.end_hour != null ? String(row.end_hour).padStart(2, "0") : "23";
    let label = `Her saat ${start}:${m}–${end}:${m} (${tz})`;
    if (row.weekdays?.length && row.weekdays.length < 7) {
      label = `${formatWeekdaysList(row.weekdays)} · ${label}`;
    }
    return label;
  }
  if (row.schedule_type === "every_4h") {
    const start = String(row.hour).padStart(2, "0");
    const end =
      row.end_hour != null ? String(row.end_hour).padStart(2, "0") : "23";
    let label = `4 saatte bir ${start}:${m}–${end}:${m} (${tz})`;
    if (row.weekdays?.length && row.weekdays.length < 7) {
      label = `${formatWeekdaysList(row.weekdays)} · ${label}`;
    }
    return label;
  }
  const h = String(row.hour).padStart(2, "0");
  if (row.schedule_type === "weekly") {
    return `${SCHEDULE_WEEKDAY_LABELS[row.weekday ?? 0]} ${h}:${m} (${tz})`;
  }
  if (row.schedule_type === "daily" && row.weekdays?.length) {
    const dayLabel =
      row.weekdays.length === 7 ? "Her gün" : formatWeekdaysList(row.weekdays);
    return `${dayLabel} ${h}:${m} (${tz})`;
  }
  return `${h}:${m} (${tz})`;
}

function isWindowScheduleType(t) {
  return t === "hourly" || t === "every_4h";
}

function setDefaultMarketWeekdays() {
  document.querySelectorAll("#scheduleWeekdays input").forEach((el) => {
    const day = parseInt(el.value, 10);
    el.checked = day >= 0 && day <= 4;
  });
}

function updateScheduleFormVisibility() {
  const t = $("#scheduleType")?.value || "daily";
  const timeWrap = $("#scheduleTimeWrap");
  const windowWrap = $("#scheduleWindowWrap");
  const weekdaysWrap = $("#scheduleWeekdaysWrap");
  const weekdaysLabel = $("#scheduleWeekdaysLabel");
  const windowed = isWindowScheduleType(t);
  if (timeWrap) timeWrap.hidden = windowed;
  if (windowWrap) windowWrap.hidden = !windowed;
  if (weekdaysWrap) weekdaysWrap.hidden = t !== "daily" && !windowed;
  if (weekdaysLabel) {
    weekdaysLabel.textContent = windowed
      ? "Günler (BIST için genelde Pzt–Cum)"
      : "Günler (günlük tarama)";
  }
}

function formatScheduleLastStatus(row) {
  if (row.last_status === "error") {
    const err = row.last_error ? ` title="${escapeHtml(row.last_error)}"` : "";
    return `<span class="status-pill err"${err}>hata</span>`;
  }
  if (row.last_status === "success_no_email") {
    const err = row.last_error
      ? ` title="${escapeHtml(row.last_error)}"`
      : ' title="E-posta gönderilemedi"';
    return `<span class="status-pill warn"${err}>e-posta yok</span>`;
  }
  if (row.last_status === "success") {
    return `<span class="status-pill ok" title="E-posta gönderildi">tamam</span>`;
  }
  return "";
}

function escapeHtml(text) {
  return String(text)
    .replace(/&/g, "&amp;")
    .replace(/"/g, "&quot;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

async function pollScheduledScanRun(scanId, attempt = 0) {
  const maxAttempts = 180;
  try {
    const res = await apiFetch(`/api/scheduled-scans/${scanId}/runs`);
    const runs = await res.json();
    const latest = runs[0];
    if (!latest || latest.status === "running") {
      if (attempt === 0) {
        setStatus("Zamanlanmış tarama çalışıyor…", "");
      }
      if (attempt < maxAttempts) {
        setTimeout(() => pollScheduledScanRun(scanId, attempt + 1), 5000);
        return;
      }
      setStatus("Tarama uzun sürüyor veya zaman aşımı. Sonuçlar tabloda görünecek.", "error");
      loadScheduledScans();
      return;
    }
    if (latest.status === "error") {
      setStatus(
        `Zamanlanmış tarama hatası: ${latest.error_message || "bilinmiyor"}`,
        "error",
      );
    } else {
      let msg = `Zamanlanmış tarama tamamlandı: ${latest.match_count ?? 0} eşleşme.`;
      if (latest.email_sent) {
        msg += " TV listesi e-posta ile gönderildi.";
        setStatus(msg, "ok");
      } else if (latest.error_message) {
        msg += ` E-posta gönderilemedi: ${latest.error_message}`;
        setStatus(msg, "error");
      } else {
        msg += " E-posta gönderilmedi.";
        setStatus(msg, "error");
      }
    }
    loadScheduledScans();
  } catch (e) {
    setStatus("Tarama durumu alınamadı: " + e.message, "error");
    loadScheduledScans();
  }
}

function buildSchedulePreviewText() {
  const body = collectScanBody();
  const t = $("#scheduleType")?.value || "daily";
  const windowed = isWindowScheduleType(t);
  const previewRow = {
    schedule_type: t,
    hour: windowed
      ? parseInt($("#scheduleStartHour")?.value || "10", 10)
      : parseInt($("#scheduleHour")?.value || "8", 10),
    end_hour: windowed
      ? parseInt($("#scheduleEndHour")?.value || "18", 10)
      : null,
    minute: windowed
      ? parseInt($("#scheduleWindowMinute")?.value || "0", 10)
      : parseInt($("#scheduleMinute")?.value || "30", 10),
    weekdays:
      t === "daily" || windowed ? getSelectedScheduleWeekdays() : [],
    timezone: $("#scheduleTimezone")?.value || "Europe/Istanbul",
  };
  const parts = [
    `Evren: ${body.universe}`,
    `Zaman dilimi (tarama): ${body.timeframe}`,
    `Maks: ${body.max_symbols}`,
    `Periyot: ${SCHEDULE_TYPE_LABELS[t] || t} — ${formatScheduleTime(previewRow)}`,
  ];
  if (body.require_pine_al) parts.push("Pine AL zorunlu");
  if (body.pine_script_id) parts.push(`Pine script #${body.pine_script_id}`);
  return parts.join(" · ");
}

function openScheduleModal() {
  resetScheduleModalForCreate();
  const modal = $("#scheduleScanModal");
  if (!modal) return;
  $("#scheduleFormStatus").textContent = "";
  $("#schedulePreview").textContent = buildSchedulePreviewText();
  modal.hidden = false;
}

async function openEditScheduleModal(id) {
  let row = scheduledScansById[id];
  if (!row) {
    try {
      const res = await apiFetch(`/api/scheduled-scans/${id}`);
      row = await res.json();
      scheduledScansById[id] = row;
    } catch (e) {
      setStatus("Zamanlanmış tarama yüklenemedi: " + e.message, "error");
      return;
    }
  }
  setScheduleModalEditMode(row);
  await applyScanConfigToUI(row.scan_config);
  const modal = $("#scheduleScanModal");
  if (!modal) return;
  $("#scheduleFormStatus").textContent = "";
  $("#schedulePreview").textContent = buildSchedulePreviewText();
  modal.hidden = false;
}

function closeScheduleModal() {
  const modal = $("#scheduleScanModal");
  if (modal) modal.hidden = true;
  resetScheduleModalForCreate();
}

async function loadScheduleConfig() {
  try {
    const res = await apiFetch("/api/scheduled-scans/config");
    const data = await res.json();
    const hint = $("#scheduledScansHint");
    if (hint) {
      hint.textContent = data.smtp_configured
        ? "SMTP yapılandırıldı. E-posta yalnızca tarama çalıştığında gider — «Şimdi» ile test edin."
        : "SMTP yapılandırılmamış (.env: SMTP_HOST, SMTP_FROM). Uygulamayı yeniden başlatın.";
    }
    if ($("#scheduleTimezone") && data.default_timezone) {
      $("#scheduleTimezone").value = data.default_timezone;
    }
    scheduleJobNextRuns = {};
    for (const job of data.scheduler?.jobs || []) {
      if (!job?.id?.startsWith("scheduled_scan_") || !job.next_run) continue;
      const id = job.id.replace("scheduled_scan_", "");
      scheduleJobNextRuns[id] = job.next_run;
    }
  } catch {
    /* ignore */
  }
}

function resolveNextRunAt(row) {
  if (row.next_run_at) return row.next_run_at;
  return scheduleJobNextRuns[String(row.id)] || null;
}

async function loadScheduledScans() {
  const tbody = $("#scheduledScansBody");
  if (!tbody) return;
  try {
    const res = await apiFetch("/api/scheduled-scans");
    const rows = await res.json();
    scheduledScansById = Object.fromEntries(rows.map((r) => [String(r.id), r]));
    if (!rows.length) {
      tbody.innerHTML =
        '<tr class="empty"><td colspan="7">Henüz zamanlanmış tarama yok.</td></tr>';
      return;
    }
    tbody.innerHTML = rows
      .map((r) => {
        const tz = r.timezone || "Europe/Istanbul";
        const last = r.last_run_at
          ? `${formatLocalDateTime(r.last_run_at, tz)} · ${r.last_match_count ?? 0} eşleşme`
          : "—";
        const nextAt = resolveNextRunAt(r);
        const next =
          r.enabled && nextAt
            ? formatLocalDateTime(nextAt, tz)
            : r.enabled
              ? "—"
              : "Durduruldu";
        const status = formatScheduleLastStatus(r);
        return `<tr>
          <td><strong>${r.name}</strong> ${status}</td>
          <td>${SCHEDULE_TYPE_LABELS[r.schedule_type] || r.schedule_type}</td>
          <td>${formatScheduleTime(r)}</td>
          <td>${r.email_to}</td>
          <td>${last}</td>
          <td>${next}</td>
          <td class="scheduled-actions">
            <button type="button" class="btn secondary btn-sm" data-edit-sched="${r.id}">Düzenle</button>
            <button type="button" class="btn secondary btn-sm" data-run-now="${r.id}">Şimdi</button>
            <button type="button" class="btn secondary btn-sm" data-toggle="${r.id}" data-enabled="${r.enabled ? "1" : "0"}">${r.enabled ? "Durdur" : "Başlat"}</button>
            <button type="button" class="btn danger btn-sm" data-delete-sched="${r.id}">Sil</button>
          </td>
        </tr>`;
      })
      .join("");

    tbody.querySelectorAll("[data-edit-sched]").forEach((btn) => {
      btn.addEventListener("click", () => {
        openEditScheduleModal(btn.dataset.editSched);
      });
    });
    tbody.querySelectorAll("[data-run-now]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const id = btn.dataset.runNow;
        btn.disabled = true;
        try {
          await apiFetch(`/api/scheduled-scans/${id}/run-now`, { method: "POST" });
          pollScheduledScanRun(id);
        } catch (e) {
          setStatus("Tarama başlatılamadı: " + e.message, "error");
        } finally {
          btn.disabled = false;
        }
      });
    });
    tbody.querySelectorAll("[data-toggle]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const id = btn.dataset.toggle;
        const enabled = btn.dataset.enabled !== "1";
        await apiFetch(`/api/scheduled-scans/${id}`, {
          method: "PATCH",
          body: JSON.stringify({ enabled }),
        });
        loadScheduledScans();
      });
    });
    tbody.querySelectorAll("[data-delete-sched]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        if (!confirm("Bu zamanlanmış tarama silinsin mi?")) return;
        await apiFetch(`/api/scheduled-scans/${btn.dataset.deleteSched}`, {
          method: "DELETE",
        });
        loadScheduledScans();
      });
    });
  } catch {
    tbody.innerHTML =
      '<tr class="empty"><td colspan="7">Liste yüklenemedi.</td></tr>';
  }
}

async function submitScheduleScan(e) {
  e.preventDefault();
  const status = $("#scheduleFormStatus");
  const scheduleType = $("#scheduleType").value;
  const windowed = isWindowScheduleType(scheduleType);
  const weekdays =
    scheduleType === "daily" || windowed ? getSelectedScheduleWeekdays() : null;
  if (scheduleType === "daily" && !weekdays.length) {
    if (status) status.textContent = "En az bir gün seçin.";
    return;
  }
  if (windowed && !weekdays.length) {
    if (status) status.textContent = "En az bir gün seçin.";
    return;
  }
  const startHour = parseInt($("#scheduleStartHour").value, 10);
  const endHour = parseInt($("#scheduleEndHour").value, 10);
  if (windowed && endHour < startHour) {
    if (status) status.textContent = "Bitiş saati başlangıçtan önce olamaz.";
    return;
  }
  const payload = {
    name: $("#scheduleName").value.trim(),
    schedule_type: scheduleType,
    hour: windowed ? startHour : parseInt($("#scheduleHour").value, 10) || 0,
    end_hour: windowed ? endHour : null,
    minute: windowed
      ? parseInt($("#scheduleWindowMinute").value, 10) || 0
      : parseInt($("#scheduleMinute").value, 10) || 0,
    weekdays,
    timezone: $("#scheduleTimezone").value.trim() || "Europe/Istanbul",
    email_to: $("#scheduleEmail").value.trim(),
    enabled: editingScheduleId
      ? scheduledScansById[editingScheduleId]?.enabled !== false
      : true,
    scan_config: collectScanBody(),
  };
  if (!payload.name) {
    if (status) status.textContent = "Preset adı gerekli.";
    return;
  }
  try {
    const isEdit = editingScheduleId != null;
    const url = isEdit
      ? `/api/scheduled-scans/${editingScheduleId}`
      : "/api/scheduled-scans";
    const res = await apiFetch(url, {
      method: isEdit ? "PATCH" : "POST",
      body: JSON.stringify(payload),
    });
    const { data, text } = await parseJsonResponse(res);
    if (!res.ok) {
      if (status) status.textContent = data?.detail || text?.slice(0, 200) || "Hata";
      return;
    }
    closeScheduleModal();
    setStatus(
      isEdit
        ? "Zamanlanmış tarama güncellendi."
        : "Zamanlanmış tarama oluşturuldu. E-posta, tarama çalıştığında gönderilir — listeden «Şimdi» ile test edebilirsiniz.",
      "ok",
    );
    loadScheduledScans();
  } catch (err) {
    if (status) status.textContent = err.message;
  }
}

async function runScan() {
  const btn = $("#btnScan");
  const spinner = btn.querySelector(".spinner");
  btn.disabled = true;
  spinner.hidden = false;

  const body = collectScanBody();
  const displayMarket = effectiveScanMarket(
    body.universe,
    body.custom_source_universe
  );
  const isBist = isBistMarket(displayMarket);
  setScanProgress(0, isBist ? "BIST taraması başlatılıyor…" : "Tarama başlatılıyor…");

  try {
    const res = await apiFetch("/api/scan", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const { data: startData, text } = await parseJsonResponse(res);
    if (!startData) {
      setStatus(text?.slice(0, 300) || "Sunucu yanıtı okunamadı", "error");
      return;
    }
    if (!res.ok) {
      setStatus(startData.detail || "Tarama hatası", "error");
      return;
    }

    const jobId = startData.job_id;
    if (!jobId) {
      setStatus("Tarama kimliği alınamadı", "error");
      return;
    }

    let data = null;
    while (true) {
      await new Promise((r) => setTimeout(r, 500));
      const stRes = await apiFetch(`/api/scan/jobs/${jobId}`);
      const { data: job, text: jobText } = await parseJsonResponse(stRes);
      if (!job) {
        setStatus(jobText?.slice(0, 300) || "İlerleme okunamadı", "error");
        return;
      }
      if (!stRes.ok) {
        setStatus(job.detail || "Tarama durumu alınamadı", "error");
        return;
      }

      setScanProgress(job.progress ?? 0, job.message || "Tarama devam ediyor…");

      if (job.status === "done") {
        data = job.result;
        break;
      }
      if (job.status === "error") {
        setStatus(job.error || job.message || "Tarama hatası", "error");
        return;
      }
    }

    if (!data) {
      setStatus("Tarama sonucu boş", "error");
      return;
    }

    lastScanData = {
      ...data,
      universe: body.universe,
      market: displayMarket,
      timeframe: body.timeframe,
    };
    renderResults(data, displayMarket);
    setCustomListExportEnabled(
      !!(data.results?.length || data.tradingview_symbols?.length)
    );
    let msg = `Tamamlandı — ${data.count} eşleşme`;
    if (data.stats) {
      const s = data.stats;
      msg += ` · taranan ${s.scanned}/${s.requested}`;
      if (s.downloaded != null && s.downloaded < s.requested) {
        msg += ` · veri ${s.downloaded}/${s.requested}`;
      }
      if (s.skipped_inactive > 0) {
        msg += ` · elenen ${s.skipped_inactive}`;
      }
    }
    if (data.pine_mode === "first_green_bar") {
      msg += " · yeşile dönen ilk mum";
    } else if (data.pine_label) {
      msg += ` · ${data.pine_label}`;
    }
    setScanProgress(100, msg);
    setStatus(msg, "ok");
  } catch (e) {
    setStatus("Bağlantı hatası: " + e.message, "error");
  } finally {
    btn.disabled = false;
    spinner.hidden = true;
    setTimeout(hideScanProgress, 2500);
  }
}

function renderResults(data, universe) {
  const market =
    universe ||
    lastScanData?.market ||
    effectiveScanMarket(
      lastScanData?.universe,
      lastScanData?.custom_source_universe
    ) ||
    $("#universe")?.value ||
    "sp500";
  $("#resultCount").textContent = `${data.count} eşleşme`;
  setCustomListExportEnabled(!!data.results?.length);
  renderSignalSummary(data);
  const tbody = $("#resultsBody");
  if (!data.results?.length) {
    tbody.innerHTML =
      '<tr class="empty"><td colspan="2">Kriterlere uyan hisse bulunamadı.</td></tr>';
    return;
  }
  tbody.innerHTML = data.results
    .map(
      (r) => `
    <tr>
      <td class="symbol">${r.symbol}</td>
      <td class="price">${formatPrice(r.price, market)}</td>
    </tr>`
    )
    .join("");
}

function setStatus(msg, type = "") {
  const el = $("#statusMsg");
  el.textContent = msg;
  el.className = "status" + (type ? ` ${type}` : "");
}

function setScanProgress(pct, message) {
  const wrap = $("#scanProgress");
  const bar = $("#scanProgressBar");
  const label = $("#scanProgressLabel");
  if (!wrap || !bar || !label) return;
  wrap.hidden = false;
  const p = Math.max(0, Math.min(100, Number(pct) || 0));
  bar.style.width = `${p}%`;
  label.textContent = `${p}%`;
  if (message) setStatus(message);
}

function hideScanProgress() {
  const wrap = $("#scanProgress");
  if (wrap) wrap.hidden = true;
}

document.addEventListener("DOMContentLoaded", async () => {
  try {
    if (typeof bootstrapAuth === "function") {
      await bootstrapAuth();
    }
  } catch (e) {
    console.error("Auth bootstrap failed:", e);
  }
  renderFilters();
  loadUniverseInfo();
  loadBistProviderOptions();
  loadSavedPine();
  loadScheduleConfig().then(() => loadScheduledScans());
  syncCustomSourceUI();

  $("#universe").addEventListener("change", () => {
    const u = $("#universe").value;
    syncCustomSourceUI();
    const pineHelpBist = $("#pineHelpBist");
    if (pineHelpBist) {
      pineHelpBist.hidden =
        u !== "bist" && !(u === "custom" && getCustomSourceUniverse() === "bist");
    }
    syncMarketCapFilterUI();
    syncBistProviderUI();
    loadUniverseInfo();
  });

  $("#customSourceUniverse")?.addEventListener("change", () => {
    setCustomSourceUniverse($("#customSourceUniverse").value);
    const pineHelpBist = $("#pineHelpBist");
    if (pineHelpBist) pineHelpBist.hidden = getCustomSourceUniverse() !== "bist";
    syncBistProviderUI();
    loadUniverseInfo();
  });

  $("#bistDataProvider")?.addEventListener("change", updateBistProviderHint);

  $("#btnRefreshUniverse").addEventListener("click", async () => {
    const universe = $("#universe").value;
    if (universe === "custom") return;
    setStatus("Hisse listesi indiriliyor…");
    try {
      const res = await apiFetch(
        `/api/symbols/info?universe=${encodeURIComponent(universe)}&refresh=1`
      );
      const data = await res.json();
      applyMaxSymbols(data.count, data.label, data.fetch_ok !== false, data.message);
      setStatus(
        data.fetch_ok !== false
          ? `${data.label}: ${data.count} hisse yüklendi.`
          : data.message || "Liste yüklenemedi.",
        data.fetch_ok !== false ? "ok" : "error"
      );
    } catch (e) {
      setStatus("Yenileme hatası: " + e.message, "error");
    }
  });

  $("#customSymbols").addEventListener("input", () => {
    if ($("#universe").value === "custom") loadUniverseInfo();
  });

  $("#savedPine").addEventListener("change", onPineSelect);
  $("#btnUploadPine").addEventListener("click", uploadPine);
  $("#btnDeletePine").addEventListener("click", deletePineScript);
  $("#btnDeleteMissingPine")?.addEventListener("click", deleteMissingPineScripts);
  $("#btnResetPineInputs")?.addEventListener("click", resetPineInputsToDefaults);
  $("#btnSavePineInputs")?.addEventListener("click", savePineInputsAsDefault);
  $("#btnScan").addEventListener("click", runScan);
  $("#btnScheduleScan")?.addEventListener("click", openScheduleModal);
  $("#btnScheduleCancel")?.addEventListener("click", closeScheduleModal);
  $("#scheduleScanForm")?.addEventListener("submit", submitScheduleScan);
  $("#scheduleType")?.addEventListener("change", () => {
    if (isWindowScheduleType($("#scheduleType").value) && !editingScheduleId) {
      setDefaultMarketWeekdays();
    }
    updateScheduleFormVisibility();
    $("#schedulePreview").textContent = buildSchedulePreviewText();
  });
  [
    "scheduleHour",
    "scheduleMinute",
    "scheduleStartHour",
    "scheduleEndHour",
    "scheduleWindowMinute",
    "scheduleTimezone",
  ].forEach((id) => {
    $("#" + id)?.addEventListener("change", () => {
      $("#schedulePreview").textContent = buildSchedulePreviewText();
    });
  });
  document.querySelectorAll("#scheduleWeekdays input").forEach((el) => {
    el.addEventListener("change", () => {
      $("#schedulePreview").textContent = buildSchedulePreviewText();
    });
  });
  $("#btnExportTv").addEventListener("click", downloadTradingViewList);
  $("#btnAddToCustomList").addEventListener("click", addResultsToCustomList);
  $("#btnSaveCustomList")?.addEventListener("click", () => saveCurrentCustomList());
  $("#btnLoadCustomList")?.addEventListener("click", loadSelectedCustomList);
  $("#btnDeleteCustomList")?.addEventListener("click", deleteSelectedCustomList);
  $("#savedCustomLists")?.addEventListener("change", () => {
    const name = $("#savedCustomLists")?.value;
    if (name && $("#customListName")) $("#customListName").value = name;
  });
  refreshSavedCustomListsSelect();
});
