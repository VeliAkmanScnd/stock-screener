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

function getCustomSourceUniverse() {
  return localStorage.getItem(CUSTOM_SOURCE_KEY) || "sp500";
}

function setCustomSourceUniverse(universe) {
  if (universe && universe !== "custom") {
    localStorage.setItem(CUSTOM_SOURCE_KEY, universe);
  }
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

function formatPrice(price, universe) {
  if (price == null || Number.isNaN(Number(price))) {
    return "—";
  }
  const u = universe || $("#universe")?.value || "sp500";
  if (u === "bist") {
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
  if (universe === "bist") {
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

  const universe = lastScanData.universe || $("#universe").value;
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
  if (btnTv) btnTv.disabled = !enabled;
  if (btnCustom) btnCustom.disabled = !enabled;
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
  applyMaxSymbols(merged.length, "Özel liste");
  syncMarketCapFilterUI();
  setStatus(
    `${newSyms.length} sembol özel listeye eklendi (toplam ${merged.length}, kaynak: ${getCustomSourceUniverse()}).`,
    "ok"
  );
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
    const n = countCustomSymbols($("#customSymbols").value);
    applyMaxSymbols(n, "Özel liste");
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

async function runScan() {
  const btn = $("#btnScan");
  const spinner = btn.querySelector(".spinner");
  btn.disabled = true;
  spinner.hidden = false;

  const universe = $("#universe").value;
  const body = {
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
  };

  const isBist = body.universe === "bist";
  setStatus(
    isBist
      ? "BIST taraması… (bu birkaç dakika sürebilir)"
      : "Tarama devam ediyor… (bu birkaç dakika sürebilir)"
  );

  try {
    const res = await apiFetch("/api/scan", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const { data, text } = await parseJsonResponse(res);
    if (!data) {
      setStatus(text?.slice(0, 300) || "Sunucu yanıtı okunamadı", "error");
      return;
    }
    if (!res.ok) {
      setStatus(data.detail || "Tarama hatası", "error");
      return;
    }
    lastScanData = { ...data, universe: body.universe, timeframe: body.timeframe };
    renderResults(data, body.universe);
    setCustomListExportEnabled(
      !!(data.results?.length || data.tradingview_symbols?.length)
    );
    let msg = `Tamamlandı — ${data.count} eşleşme`;
    if (data.stats) {
      const s = data.stats;
      msg += ` · taranan ${s.scanned}/${s.requested}`;
      if (s.skipped_inactive > 0) {
        msg += ` · elenen (delist/ölü) ${s.skipped_inactive}`;
      }
    }
    if (data.pine_mode === "first_green_bar") {
      msg += " · yeşile dönen ilk mum";
    } else if (data.pine_label) {
      msg += ` · ${data.pine_label}`;
    }
    setStatus(msg, "ok");
  } catch (e) {
    setStatus("Bağlantı hatası: " + e.message, "error");
  } finally {
    btn.disabled = false;
    spinner.hidden = true;
  }
}

function renderResults(data, universe) {
  const market = universe || lastScanData?.universe || $("#universe")?.value || "sp500";
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
  loadSavedPine();

  $("#universe").addEventListener("change", () => {
    const u = $("#universe").value;
    $("#customSymbolsWrap").hidden = u !== "custom";
    const pineHelpBist = $("#pineHelpBist");
    if (pineHelpBist) pineHelpBist.hidden = u !== "bist";
    syncMarketCapFilterUI();
    loadUniverseInfo();
  });

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
  $("#btnExportTv").addEventListener("click", downloadTradingViewList);
  $("#btnAddToCustomList").addEventListener("click", addResultsToCustomList);
});
