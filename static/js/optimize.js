let optContractsLoaded = false;
let optPollTimer = null;
let optPresets = [];
let optLastPayload = null;
let optSort = { key: "rank", dir: "asc" };

const OPT_SORT_DESC_DEFAULT = new Set([
  "win_rate",
  "profit_factor",
  "net_profit_pct",
  "trades",
]);

const OPT_AXIS = [
  ["ha_len", "optHaLenOn"],
  ["ha_len2", "optHaLen2On"],
  ["osc_len", "optOscLenOn"],
  ["ha_htf", "optHaHtfOn"],
  ["exit_mode", "optExitModeOn"],
  ["rr_mult", "optRrOn"],
  ["swing_bars", "optSwingOn"],
  ["tp_pct", "optTpPctOn"],
  ["sl_pct", "optSlPctOn"],
  ["max_same", "optMaxSameOn"],
  ["reverse_exit", "optReverseOn"],
  ["require_bar", "optRequireBarOn"],
];

function optEsc(s) {
  return String(s ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/"/g, "&quot;");
}

function optStatus(msg, kind) {
  const el = document.querySelector("#optFormStatus");
  if (!el) return;
  el.textContent = msg || "";
  el.classList.toggle("ok", kind === "ok");
  el.classList.toggle("error", kind === "error");
}

function optCsv(id) {
  return (document.querySelector(id)?.value || "").trim();
}

function optNum(id, fallback) {
  const v = parseFloat(document.querySelector(id)?.value);
  return Number.isFinite(v) ? v : fallback;
}

function setOptProgress(pct, label) {
  const wrap = document.querySelector("#optProgress");
  const bar = document.querySelector("#optProgressBar");
  const text = document.querySelector("#optProgressLabel");
  if (wrap) wrap.hidden = false;
  if (bar) bar.style.width = `${Math.max(0, Math.min(100, pct))}%`;
  if (text) text.textContent = label || `${Math.round(pct)}%`;
}

function hideOptProgress() {
  const wrap = document.querySelector("#optProgress");
  if (wrap) wrap.hidden = true;
}

function optBoolLabel(v) {
  return v ? "Açık" : "Kapalı";
}

function optExitLabel(mode) {
  return mode === "Percent" ? "Yüzde" : mode || "";
}

function syncOptExitFields() {
  const raw = document.querySelector("#optExitMode")?.value || "Swing RR";
  const both = document.querySelector("#optExitModeOn")?.checked && raw.includes(",");
  const swing = both || raw.includes("Swing");
  const pct = both || raw.includes("Percent");
  document.querySelectorAll(".opt-exit-swing").forEach((el) => {
    el.hidden = !swing;
  });
  document.querySelectorAll(".opt-exit-percent").forEach((el) => {
    el.hidden = !pct;
  });
}

function syncOptAxisUi() {
  document.querySelectorAll("[data-opt-axis]").forEach((el) => {
    const on = el.querySelector(".opt-enable")?.checked;
    el.classList.toggle("opt-field-fixed", !on);
    const firstSpan = el.querySelector(".opt-range-row > label:first-child > span");
    if (firstSpan) firstSpan.textContent = on ? "Başlangıç" : "Değer";
  });
  syncOptExitFields();
  syncOptGridHint();
}

function optSpanCount(start, step, stop, integer) {
  let a = Number(start);
  let b = Number(stop);
  let s = Math.abs(Number(step));
  if (!Number.isFinite(a) || !Number.isFinite(b)) return 1;
  if (!Number.isFinite(s) || s === 0) s = 1;
  if (a > b) {
    const tmp = a;
    a = b;
    b = tmp;
  }
  const out = [];
  let x = a;
  for (let i = 0; i < 400; i += 1) {
    const val = integer ? Math.round(x) : x;
    if (!out.length || out[out.length - 1] !== val) out.push(val);
    const nxt = x + s;
    if (nxt > b + s * 1e-9) break;
    x = nxt;
  }
  return Math.max(1, out.length);
}

function optSelectValueCount(id) {
  const raw = document.querySelector(id)?.value || "";
  const parts = raw.split(",").map((p) => p.trim()).filter(Boolean);
  return Math.max(1, new Set(parts).size);
}

function estimateOptGridSize() {
  const flags = collectOptFlags();
  const axis = (on, base, fallback, integer) => {
    if (!on) return 1;
    const spec = optRange(base, fallback);
    return optSpanCount(spec.start, spec.step, spec.stop, integer);
  };
  const exitCount = flags.exit_mode ? optSelectValueCount("#optExitMode") : 1;
  const exitRaw = document.querySelector("#optExitMode")?.value || "Swing RR";
  const onlySwing = !exitRaw.includes("Percent");
  const onlyPct = exitRaw.includes("Percent") && !exitRaw.includes("Swing");
  let n = 1;
  n *= axis(flags.ha_len, "optHaLen", [48, 16, 80], true);
  n *= axis(flags.ha_len2, "optHaLen2", [72, 24, 96], true);
  n *= axis(flags.osc_len, "optOscLen", [7, 4, 11], true);
  n *= axis(flags.ha_htf, "optHaHtf", [30, 15, 30], true);
  n *= exitCount;
  n *= onlyPct ? 1 : axis(flags.rr_mult, "optRr", [1.2, 0.4, 2], false);
  n *= onlyPct ? 1 : axis(flags.swing_bars, "optSwing", [8, 3, 11], true);
  n *= onlySwing ? 1 : axis(flags.tp_pct, "optTpPct", [1.5, 0.5, 2.5], false);
  n *= onlySwing ? 1 : axis(flags.sl_pct, "optSlPct", [0.8, 0.35, 1.5], false);
  n *= axis(flags.max_same, "optMaxSame", [1, 1, 2], true);
  n *= flags.reverse_exit ? optSelectValueCount("#optReverse") : 1;
  n *= flags.require_bar ? optSelectValueCount("#optRequireBar") : 1;
  return n;
}

function syncOptGridHint() {
  const hint = document.querySelector("#optGridHint");
  if (!hint) return;
  const space = estimateOptGridSize();
  const scanAll = !!document.querySelector("#optScanAll")?.checked;
  const maxEl = document.querySelector("#optMaxCombos");
  if (maxEl) maxEl.disabled = scanAll;
  const cap = Math.max(20, Math.min(20000, Math.round(optNum("#optMaxCombos", 180))));
  const spaceTxt = Number(space).toLocaleString("tr-TR");
  if (scanAll) {
    if (space <= 20000) {
      hint.textContent = `Tamamını tara: ${spaceTxt} setin hepsi denenecek.`;
    } else {
      hint.textContent = `Izgara ${spaceTxt} set. Tamamını tara en fazla 20.000 — adımı büyütün veya eksenleri kapatın.`;
    }
    return;
  }
  if (space <= cap) {
    hint.textContent = `Şu anki ızgara ${spaceTxt} set. Maks. ${cap} → tamamı taranır. Daha fazla set için eksen açın, adımı küçültün veya Tamamını tara’yı işaretleyin.`;
  } else {
    hint.textContent = `Şu anki ızgara ${spaceTxt} olası set. Maks. ${cap} → ${cap} örnek alınır.`;
  }
}

function collectOptFlags() {
  const out = {};
  OPT_AXIS.forEach(([key, id]) => {
    out[key] = !!document.querySelector(`#${id}`)?.checked;
  });
  return out;
}

function applyOptFlags(flags) {
  const src = flags || {};
  OPT_AXIS.forEach(([key, id]) => {
    const el = document.querySelector(`#${id}`);
    if (!el) return;
    if (key in src) el.checked = !!src[key];
  });
  syncOptAxisUi();
}

function pineOverridesFromRow(params) {
  return {
    ha_len: params.ha_len,
    ha_len2: params.ha_len2,
    osc_len: params.osc_len,
    ha_htf: params.ha_htf || "30",
    exitMode: params.exitMode,
    rrMult: params.rrMult,
    swingBars: params.swingBars,
    tp_pct: params.tp_pct,
    sl_pct: params.sl_pct,
    allow_long: params.allow_long,
    allow_short: params.allow_short,
    reverse_exit: params.reverse_exit,
    require_bar: params.require_bar,
    maxSame: params.maxSame,
  };
}

function optFilterNum(id) {
  const el = document.querySelector(id);
  if (!el || String(el.value).trim() === "") return null;
  const v = parseFloat(el.value);
  return Number.isFinite(v) ? v : null;
}

function optRowValue(row, key) {
  const p = row.params || {};
  if (key in row && key !== "params") return row[key];
  if (key === "reverse_exit") return p.reverse_exit ? 1 : 0;
  if (key === "require_bar") return p.require_bar ? 1 : 0;
  if (key === "exitMode") return optExitLabel(p.exitMode);
  if (key === "ha_htf") return p.ha_htf || "";
  return p[key];
}

function optRowHaystack(row) {
  const p = row.params || {};
  return [
    row.rank,
    row.win_rate,
    row.profit_factor,
    row.net_profit_pct,
    row.max_drawdown,
    row.trades,
    p.ha_len,
    p.ha_len2,
    p.osc_len,
    p.ha_htf,
    optExitLabel(p.exitMode),
    p.rrMult,
    p.swingBars,
    p.tp_pct,
    p.sl_pct,
    optBoolLabel(p.reverse_exit),
    optBoolLabel(p.require_bar),
    p.maxSame,
  ]
    .map((v) => String(v ?? "").toLowerCase())
    .join(" ");
}

function filterOptRows(rows) {
  const passedOnly = !!document.querySelector("#optFilterPassed")?.checked;
  const minWr = optFilterNum("#optFilterWr");
  const minPf = optFilterNum("#optFilterPf");
  const minProfit = optFilterNum("#optFilterProfit");
  const maxDd = optFilterNum("#optFilterDd");
  const minTrades = optFilterNum("#optFilterTrades");
  const q = (document.querySelector("#optFilterText")?.value || "").trim().toLowerCase();
  return rows.filter((r) => {
    if (passedOnly && !r.passed) return false;
    if (minWr != null && Number(r.win_rate) < minWr) return false;
    if (minPf != null && Number(r.profit_factor) < minPf) return false;
    if (minProfit != null && Number(r.net_profit_pct) < minProfit) return false;
    if (maxDd != null && Number(r.max_drawdown) > maxDd) return false;
    if (minTrades != null && Number(r.trades) < minTrades) return false;
    if (q && !optRowHaystack(r).includes(q)) return false;
    return true;
  });
}

function sortOptRows(rows) {
  const key = optSort.key || "rank";
  const mul = optSort.dir === "desc" ? -1 : 1;
  return [...rows].sort((a, b) => {
    const av = optRowValue(a, key);
    const bv = optRowValue(b, key);
    if (typeof av === "string" || typeof bv === "string") {
      const cmp = String(av ?? "").localeCompare(String(bv ?? ""), "tr", { numeric: true });
      return mul * (cmp || (a.rank || 0) - (b.rank || 0));
    }
    const an = Number(av);
    const bn = Number(bv);
    if (!Number.isFinite(an) && !Number.isFinite(bn)) return (a.rank || 0) - (b.rank || 0);
    if (!Number.isFinite(an)) return 1;
    if (!Number.isFinite(bn)) return -1;
    if (an === bn) return (a.rank || 0) - (b.rank || 0);
    return mul * (an - bn);
  });
}

function syncOptSortHeaders() {
  document.querySelectorAll(".opt-results-table th[aria-sort]").forEach((th) => {
    const btn = th.querySelector("[data-opt-sort]");
    const key = btn?.getAttribute("data-opt-sort");
    if (key && key === optSort.key) th.setAttribute("aria-sort", optSort.dir === "desc" ? "descending" : "ascending");
    else th.setAttribute("aria-sort", "none");
  });
}

function paintOptTable() {
  const body = document.querySelector("#optResultBody");
  const countEl = document.querySelector("#optResultCount");
  const tools = document.querySelector("#optResultTools");
  if (!body) return;
  const all = optLastPayload?.results || [];
  if (tools) tools.hidden = all.length === 0;
  if (!all.length) {
    if (countEl) {
      countEl.hidden = true;
      countEl.textContent = "";
    }
    const err = optLastPayload?.error ? ` ${optLastPayload.error}` : "";
    body.innerHTML = `<tr class="empty"><td colspan="19">Eşikleri geçen (veya yakın) set yok.${optEsc(err)}</td></tr>`;
    return;
  }
  const filtered = sortOptRows(filterOptRows(all));
  if (countEl) {
    countEl.hidden = false;
    countEl.textContent = `${filtered.length} / ${all.length} satır gösteriliyor`;
  }
  if (!filtered.length) {
    body.innerHTML = `<tr class="empty"><td colspan="19">Filtreye uyan satır yok.</td></tr>`;
    return;
  }
  body.innerHTML = filtered
    .map((r) => {
      const p = r.params || {};
      const cls = [r.passed ? "opt-row-pass" : "opt-row-fail", r.tag === "referans" ? "opt-row-ref" : ""]
        .filter(Boolean)
        .join(" ");
      const json = optEsc(JSON.stringify(pineOverridesFromRow(p)));
      const rankLabel = r.tag === "referans" ? `${r.rank} · Ref` : r.rank;
      return `<tr class="${cls}">
        <td>${rankLabel}</td>
        <td>${r.win_rate}</td>
        <td>${r.profit_factor}</td>
        <td>${r.net_profit_pct}</td>
        <td>${r.max_drawdown}</td>
        <td>${r.trades}</td>
        <td>${p.ha_len ?? ""}</td>
        <td>${p.ha_len2 ?? ""}</td>
        <td>${p.osc_len ?? ""}</td>
        <td>${optEsc(p.ha_htf || "chart")}</td>
        <td>${optEsc(optExitLabel(p.exitMode))}</td>
        <td>${p.exitMode === "Percent" ? "—" : (p.rrMult ?? "")}</td>
        <td>${p.exitMode === "Percent" ? "—" : (p.swingBars ?? "")}</td>
        <td>${p.exitMode === "Percent" ? (p.tp_pct ?? "") : "—"}</td>
        <td>${p.exitMode === "Percent" ? (p.sl_pct ?? "") : "—"}</td>
        <td>${optBoolLabel(p.reverse_exit)}</td>
        <td>${optBoolLabel(p.require_bar)}</td>
        <td>${p.maxSame ?? ""}</td>
        <td><button type="button" class="btn secondary btn-sm" data-opt-copy="${json}">Kopyala</button></td>
      </tr>`;
    })
    .join("");
  body.querySelectorAll("[data-opt-copy]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const text = btn.getAttribute("data-opt-copy") || "";
      try {
        await navigator.clipboard.writeText(text);
        optStatus("Parametreler kopyalandı — alarm formuna yapıştırabilirsiniz.", "ok");
      } catch {
        optStatus(text, "ok");
      }
    });
  });
}

function optMetricLine(row) {
  if (!row) return "—";
  return `WR ${row.win_rate} · PF ${row.profit_factor} · Kâr ${row.net_profit_pct}% · DD ${row.max_drawdown}% · ${row.trades} işlem`;
}

function renderOptCompare(payload) {
  const card = document.querySelector("#optCompareCard");
  if (!card) return;
  const ref = payload?.reference;
  const best = payload?.best;
  if (!ref && !best) {
    card.hidden = true;
    card.innerHTML = "";
    return;
  }
  let note = payload?.coverage_note || "";
  if (ref && best) {
    if (best.profit_factor > ref.profit_factor && best.net_profit_pct > ref.net_profit_pct) {
      note = `${note ? `${note} ` : ""}Taramada referanstan daha yüksek PF ve kâr var.`;
    } else if (best.profit_factor > ref.profit_factor) {
      note = `${note ? `${note} ` : ""}Taramada daha yüksek PF var; kârı da kontrol edin.`;
    } else {
      note = `${note ? `${note} ` : ""}Referans bu örneklemde PF açısından önde veya eşit.`;
    }
  }
  card.hidden = false;
  card.innerHTML = `
    <div class="opt-compare-item">
      <h3>Manuel referans</h3>
      <p>${ref ? optEsc(optMetricLine(ref)) : "Bu taramaya referans eklenmedi."}</p>
    </div>
    <div class="opt-compare-item">
      <h3>Taramanın en iyisi</h3>
      <p>${best ? optEsc(optMetricLine(best)) : "Eşikleri geçen tarama seti yok."}</p>
    </div>
    ${note ? `<p class="opt-compare-note">${optEsc(note)}</p>` : ""}
  `;
}

function renderOptResults(payload) {
  optLastPayload = payload || {};
  optSort = { key: "rank", dir: "asc" };
  const title = document.querySelector("#optResultTitle");
  const hint = document.querySelector("#optResultHint");
  const passed = optLastPayload.passed ?? 0;
  const tested = optLastPayload.tested ?? 0;
  const space = optLastPayload.grid_size || 0;
  if (title) title.textContent = `${optLastPayload.symbol || ""} sonuçları`;
  if (hint) {
    const comboBit = space > tested
      ? `${tested} örnek / ${Number(space).toLocaleString("tr-TR")} olası`
      : `${tested} kombinasyon`;
    hint.textContent = `${optLastPayload.bars || 0} bar · ${optLastPayload.from || ""} → ${optLastPayload.to || ""} · ${comboBit} · ${passed} eşik geçti`;
  }
  renderOptCompare(optLastPayload);
  syncOptSortHeaders();
  paintOptTable();
}

function onOptSortClick(ev) {
  const btn = ev.target.closest("[data-opt-sort]");
  if (!btn) return;
  const key = btn.getAttribute("data-opt-sort");
  if (!key) return;
  if (optSort.key === key) {
    optSort.dir = optSort.dir === "asc" ? "desc" : "asc";
  } else {
    optSort = { key, dir: OPT_SORT_DESC_DEFAULT.has(key) ? "desc" : "asc" };
  }
  syncOptSortHeaders();
  paintOptTable();
}

function optRange(base, fallback) {
  return {
    start: optNum(`#${base}From`, fallback[0]),
    step: optNum(`#${base}Step`, fallback[1]),
    stop: optNum(`#${base}To`, fallback[2]),
  };
}

function setOptRange(base, start, step, stop) {
  const fromEl = document.querySelector(`#${base}From`);
  const stepEl = document.querySelector(`#${base}Step`);
  const toEl = document.querySelector(`#${base}To`);
  if (fromEl) fromEl.value = start;
  if (stepEl) stepEl.value = step;
  if (toEl) toEl.value = stop;
}

function applyOptRange(base, spec, fallback) {
  if (spec && typeof spec === "object" && !Array.isArray(spec)) {
    setOptRange(base, spec.start ?? fallback[0], spec.step ?? fallback[1], spec.stop ?? fallback[2]);
    return;
  }
  setOptRange(base, fallback[0], fallback[1], fallback[2]);
}

function collectOptBody() {
  return {
    symbol: optCsv("#optSymbol"),
    timeframe: document.querySelector("#optTimeframe")?.value || "15m",
    period: document.querySelector("#optPeriod")?.value || "60d",
    mode: document.querySelector("#optMode")?.value || "quick",
    side: document.querySelector("#optSide")?.value || "both",
    max_combos: Math.max(20, Math.min(20000, Math.round(optNum("#optMaxCombos", 180)))),
    scan_all: !!document.querySelector("#optScanAll")?.checked,
    min_win_rate: optNum("#optMinWinRate", 45),
    max_drawdown: optNum("#optMaxDd", 18),
    min_profit_factor: optNum("#optMinPf", 1.3),
    min_profit: optNum("#optMinProfit", 8),
    min_trades: Math.round(optNum("#optMinTrades", 10)),
    ha_len: optRange("optHaLen", [48, 16, 80]),
    ha_len2: optRange("optHaLen2", [72, 24, 96]),
    osc_len: optRange("optOscLen", [7, 4, 11]),
    ha_htf: optRange("optHaHtf", [30, 15, 30]),
    exit_mode: document.querySelector("#optExitMode")?.value || "Swing RR",
    rr_mult: optRange("optRr", [1.2, 0.4, 2]),
    swing_bars: optRange("optSwing", [8, 3, 11]),
    tp_pct: optRange("optTpPct", [1.5, 0.5, 2.5]),
    sl_pct: optRange("optSlPct", [0.8, 0.35, 1.5]),
    max_same: optRange("optMaxSame", [1, 1, 2]),
    reverse_exit: document.querySelector("#optReverse")?.value || "true",
    require_bar: document.querySelector("#optRequireBar")?.value || "false",
    optimize: collectOptFlags(),
    reference: collectOptReference(),
  };
}

function collectOptReference() {
  return {
    enabled: !!document.querySelector("#optRefOn")?.checked,
    ha_len: Math.round(optNum("#optRefHaLen", 100)),
    ha_len2: Math.round(optNum("#optRefHaLen2", 100)),
    osc_len: Math.round(optNum("#optRefOscLen", 7)),
    ha_htf: String(Math.round(optNum("#optRefHaHtf", 30))),
    exit_mode: document.querySelector("#optRefExitMode")?.value || "Swing RR",
    rr_mult: optNum("#optRefRr", 1),
    swing_bars: Math.round(optNum("#optRefSwing", 4)),
    tp_pct: optNum("#optRefTpPct", 2),
    sl_pct: optNum("#optRefSlPct", 1),
    max_same: Math.round(optNum("#optRefMaxSame", 2)),
    reverse_exit: document.querySelector("#optRefReverse")?.value || "true",
    require_bar: document.querySelector("#optRefRequireBar")?.value || "false",
  };
}

function fillOptRefFromGrid() {
  const set = (id, val) => {
    const el = document.querySelector(id);
    if (el && val !== undefined && val !== null && val !== "") el.value = val;
  };
  set("#optRefHaLen", document.querySelector("#optHaLenFrom")?.value);
  set("#optRefHaLen2", document.querySelector("#optHaLen2From")?.value);
  set("#optRefOscLen", document.querySelector("#optOscLenFrom")?.value);
  set("#optRefHaHtf", document.querySelector("#optHaHtfFrom")?.value);
  const exitRaw = document.querySelector("#optExitMode")?.value || "Swing RR";
  set("#optRefExitMode", exitRaw.includes("Percent") && !exitRaw.includes("Swing") ? "Percent" : "Swing RR");
  set("#optRefRr", document.querySelector("#optRrFrom")?.value);
  set("#optRefSwing", document.querySelector("#optSwingFrom")?.value);
  set("#optRefTpPct", document.querySelector("#optTpPctFrom")?.value);
  set("#optRefSlPct", document.querySelector("#optSlPctFrom")?.value);
  set("#optRefMaxSame", document.querySelector("#optMaxSameFrom")?.value);
  const rev = (document.querySelector("#optReverse")?.value || "true").split(",")[0].trim();
  const mum = (document.querySelector("#optRequireBar")?.value || "false").split(",")[0].trim();
  set("#optRefReverse", rev);
  set("#optRefRequireBar", mum);
}

function syncOptPeriodHint() {
  const hint = document.querySelector("#optPeriodHint");
  if (!hint) return;
  const tf = document.querySelector("#optTimeframe")?.value || "15m";
  const period = document.querySelector("#optPeriod")?.value || "60d";
  let extra = "TradingView’deki kendi setinizi yazın; tarama onu her zaman dener ve tabloda Ref olarak işaretler.";
  if (period === "13mo" && tf === "15m") {
    extra += " 13 ay 15m ile inmez; 30 dakika seçin.";
  } else if (period === "13mo") {
    extra += " 13 ay için 30 dakika veya 1 saat uygundur.";
  } else if (tf === "15m" && (period === "6mo" || period === "8mo" || period === "2y")) {
    extra += " 15m indirme en fazla ~8 aydır.";
  }
  hint.textContent = extra;
}

function applyOptConfig(cfg) {
  if (!cfg || typeof cfg !== "object") return;
  const set = (id, val) => {
    const el = document.querySelector(id);
    if (el && val !== undefined && val !== null && val !== "") el.value = val;
  };
  set("#optSymbol", cfg.symbol);
  set("#optTimeframe", cfg.timeframe);
  set("#optPeriod", cfg.period);
  set("#optMode", cfg.mode);
  set("#optSide", cfg.side);
  set("#optMaxCombos", cfg.max_combos);
  if (document.querySelector("#optScanAll") && cfg.scan_all !== undefined) {
    document.querySelector("#optScanAll").checked = !!cfg.scan_all;
  }
  set("#optMinWinRate", cfg.min_win_rate);
  set("#optMaxDd", cfg.max_drawdown);
  set("#optMinPf", cfg.min_profit_factor);
  set("#optMinProfit", cfg.min_profit);
  set("#optMinTrades", cfg.min_trades);
  applyOptRange("optHaLen", cfg.ha_len, [48, 16, 80]);
  applyOptRange("optHaLen2", cfg.ha_len2, [72, 24, 96]);
  applyOptRange("optOscLen", cfg.osc_len, [7, 4, 11]);
  applyOptRange("optHaHtf", cfg.ha_htf, [30, 15, 30]);
  applyOptRange("optRr", cfg.rr_mult, [1.2, 0.4, 2]);
  applyOptRange("optSwing", cfg.swing_bars, [8, 3, 11]);
  applyOptRange("optTpPct", cfg.tp_pct, [1.5, 0.5, 2.5]);
  applyOptRange("optSlPct", cfg.sl_pct, [0.8, 0.35, 1.5]);
  applyOptRange("optMaxSame", cfg.max_same, [1, 1, 2]);
  set("#optExitMode", cfg.exit_mode);
  set("#optReverse", cfg.reverse_exit);
  set("#optRequireBar", cfg.require_bar);
  applyOptFlags(cfg.optimize);
  if (cfg.reference && typeof cfg.reference === "object") {
    const ref = cfg.reference;
    const on = document.querySelector("#optRefOn");
    if (on && "enabled" in ref) on.checked = !!ref.enabled;
    set("#optRefHaLen", ref.ha_len);
    set("#optRefHaLen2", ref.ha_len2);
    set("#optRefOscLen", ref.osc_len);
    set("#optRefHaHtf", ref.ha_htf);
    set("#optRefExitMode", ref.exit_mode);
    set("#optRefRr", ref.rr_mult);
    set("#optRefSwing", ref.swing_bars);
    set("#optRefTpPct", ref.tp_pct);
    set("#optRefSlPct", ref.sl_pct);
    set("#optRefMaxSame", ref.max_same);
    set("#optRefReverse", ref.reverse_exit === false || ref.reverse_exit === "false" ? "false" : "true");
    set("#optRefRequireBar", ref.require_bar === true || ref.require_bar === "true" ? "true" : "false");
  }
  syncOptPeriodHint();
  syncOptGridHint();
}

async function pollOptJob(jobId) {
  const stRes = await apiFetch(`/api/optimize/jobs/${jobId}`);
  const job = await stRes.json();
  if (!stRes.ok) throw new Error(job.detail || "Durum alınamadı");
  setOptProgress(job.progress ?? 0, job.message || "Çalışıyor…");
  if (job.status === "running") {
    optPollTimer = setTimeout(() => {
      pollOptJob(jobId).catch((err) => {
        optStatus(err.message, "error");
        hideOptProgress();
      });
    }, 900);
    return;
  }
  if (job.status === "error") {
    optStatus(job.error || job.message || "Tarama hata verdi", "error");
    hideOptProgress();
    return;
  }
  hideOptProgress();
  renderOptResults(job.result || {});
  const passed = job.result?.passed ?? 0;
  const tested = job.result?.tested ?? 0;
  const space = job.result?.grid_size || 0;
  let msg = passed
    ? `${passed} set eşikleri geçti.`
    : "Eşik geçen set yok; tabloda en yakın sonuçlar var.";
  if (!passed && space > tested) {
    msg = `Eşik geçen set yok. ${tested} örnek, ${Number(space).toLocaleString("tr-TR")} olası — ızgarayı daraltın veya optimize edilmeyen eksenleri kapatın.`;
  }
  optStatus(msg, passed ? "ok" : "error");
}

async function startOptRun(e) {
  e.preventDefault();
  if (optPollTimer) {
    clearTimeout(optPollTimer);
    optPollTimer = null;
  }
  const body = collectOptBody();
  if (!body.symbol) {
    optStatus("Sembol gerekli.", "error");
    return;
  }
  const space = estimateOptGridSize();
  if (body.scan_all && space > 20000) {
    optStatus(
      `Izgara ${Number(space).toLocaleString("tr-TR")} set. Tamamını tara en fazla 20.000 — adımı büyütün veya eksenleri kapatın.`,
      "error",
    );
    return;
  }
  const btn = document.querySelector("#btnOptRun");
  if (btn) btn.disabled = true;
  optStatus("Tarama başlatılıyor…");
  setOptProgress(2, "Başlatılıyor…");
  try {
    const res = await apiFetch("/api/optimize/bias", {
      method: "POST",
      body: JSON.stringify(body),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      throw new Error(data.detail || "Başlatılamadı");
    }
    await pollOptJob(data.job_id);
  } catch (err) {
    hideOptProgress();
    optStatus(err.message || "Hata", "error");
  } finally {
    if (btn) btn.disabled = false;
  }
}

async function loadOptContracts() {
  if (optContractsLoaded) return;
  const list = document.querySelector("#optSymbolList");
  const hint = document.querySelector("#optTvHint");
  const symbol = document.querySelector("#optSymbol");
  try {
    const res = await apiFetch("/api/optimize/contracts");
    const data = await res.json();
    const rows = data.contracts || [];
    if (list) {
      list.innerHTML = rows
        .map((r) => `<option value="${optEsc(r.contract)}">${optEsc(r.ticker)} ${optEsc(r.name || "")}</option>`)
        .join("");
    }
    if (symbol && !symbol.value && rows[0]) symbol.value = rows[0].contract;
    if (hint) {
      hint.textContent = data.tv_auth
        ? "TradingView oturumu tanımlı — veri session üzerinden çekilecek."
        : "TradingView sessionid / sessionid_sign .env içinde yok; tester çalışmaz.";
    }
    optContractsLoaded = true;
  } catch (err) {
    if (hint) hint.textContent = err.message || "Kontrat listesi alınamadı.";
  }
}

function renderOptPresets() {
  const sel = document.querySelector("#optPresetSelect");
  if (!sel) return;
  const current = sel.value;
  sel.innerHTML = `<option value="">— Kayıt seç —</option>${optPresets
    .map((p) => {
      const tag = p.symbol || "genel";
      return `<option value="${p.id}">${optEsc(p.name)} (${optEsc(tag)})</option>`;
    })
    .join("")}`;
  if (current && optPresets.some((p) => String(p.id) === current)) sel.value = current;
}

async function loadOptPresets() {
  const thisOnly = document.querySelector("#optPresetThisSymbol")?.checked;
  const symbol = thisOnly ? optCsv("#optSymbol") : "";
  const q = symbol ? `?symbol=${encodeURIComponent(symbol)}` : "";
  try {
    const res = await apiFetch(`/api/optimize/presets${q}`);
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Kayıtlar alınamadı");
    optPresets = data.presets || [];
    renderOptPresets();
  } catch (err) {
    optStatus(err.message || "Kayıt listesi alınamadı", "error");
  }
}

function selectedOptPreset() {
  const id = Number(document.querySelector("#optPresetSelect")?.value);
  if (!id) return null;
  return optPresets.find((p) => p.id === id) || null;
}

async function saveOptPreset() {
  const nameEl = document.querySelector("#optPresetName");
  const name = (nameEl?.value || "").trim();
  if (!name) {
    optStatus("Kayıt için bir ad yazın.", "error");
    nameEl?.focus();
    return;
  }
  const thisOnly = document.querySelector("#optPresetThisSymbol")?.checked;
  const body = {
    name,
    symbol: thisOnly ? optCsv("#optSymbol") : "",
    config: collectOptBody(),
  };
  const existing = selectedOptPreset();
  const sameName = existing && existing.name === name;
  try {
    const res = await apiFetch(sameName ? `/api/optimize/presets/${existing.id}` : "/api/optimize/presets", {
      method: sameName ? "PUT" : "POST",
      body: JSON.stringify(body),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || "Kaydedilemedi");
    optStatus(sameName ? `"${name}" güncellendi.` : `"${name}" kaydedildi.`, "ok");
    await loadOptPresets();
    const sel = document.querySelector("#optPresetSelect");
    if (sel && data.id) sel.value = String(data.id);
  } catch (err) {
    optStatus(err.message || "Kaydedilemedi", "error");
  }
}

function loadSelectedOptPreset() {
  const row = selectedOptPreset();
  if (!row) {
    optStatus("Yüklenecek kayıt seçin.", "error");
    return;
  }
  applyOptConfig(row.config || {});
  const nameEl = document.querySelector("#optPresetName");
  if (nameEl) nameEl.value = row.name || "";
  optStatus(`"${row.name}" yüklendi.`, "ok");
}

async function deleteSelectedOptPreset() {
  const row = selectedOptPreset();
  if (!row) {
    optStatus("Silinecek kayıt seçin.", "error");
    return;
  }
  if (!confirm(`"${row.name}" silinsin mi?`)) return;
  try {
    const res = await apiFetch(`/api/optimize/presets/${row.id}`, { method: "DELETE" });
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      throw new Error(data.detail || "Silinemedi");
    }
    optStatus(`"${row.name}" silindi.`, "ok");
    const nameEl = document.querySelector("#optPresetName");
    if (nameEl) nameEl.value = "";
    await loadOptPresets();
  } catch (err) {
    optStatus(err.message || "Silinemedi", "error");
  }
}

async function onOptTabShown() {
  await loadOptContracts();
  await loadOptPresets();
  syncOptAxisUi();
}

function initOptimize() {
  document.querySelector("#optForm")?.addEventListener("submit", startOptRun);
  document.querySelector("#optExitMode")?.addEventListener("change", syncOptExitFields);
  document.querySelectorAll(".opt-enable").forEach((el) => {
    el.addEventListener("change", syncOptAxisUi);
  });
  document.querySelector(".opt-results-table thead")?.addEventListener("click", onOptSortClick);
  document.querySelector("#btnOptRefFromGrid")?.addEventListener("click", fillOptRefFromGrid);
  document.querySelector("#optPeriod")?.addEventListener("change", syncOptPeriodHint);
  document.querySelector("#optTimeframe")?.addEventListener("change", syncOptPeriodHint);
  document.querySelector("#optForm")?.addEventListener("input", syncOptGridHint);
  document.querySelector("#optMaxCombos")?.addEventListener("change", syncOptGridHint);
  document.querySelector("#optScanAll")?.addEventListener("change", syncOptGridHint);
  syncOptPeriodHint();
  syncOptGridHint();
  ["#optFilterPassed", "#optFilterWr", "#optFilterPf", "#optFilterProfit", "#optFilterDd", "#optFilterTrades", "#optFilterText"].forEach((id) => {
    document.querySelector(id)?.addEventListener("input", paintOptTable);
    document.querySelector(id)?.addEventListener("change", paintOptTable);
  });
  document.querySelector("#btnOptPresetSave")?.addEventListener("click", saveOptPreset);
  document.querySelector("#btnOptPresetLoad")?.addEventListener("click", loadSelectedOptPreset);
  document.querySelector("#btnOptPresetDelete")?.addEventListener("click", deleteSelectedOptPreset);
  document.querySelector("#optPresetThisSymbol")?.addEventListener("change", loadOptPresets);
  document.querySelector("#optSymbol")?.addEventListener("change", () => {
    if (document.querySelector("#optPresetThisSymbol")?.checked) loadOptPresets();
  });
  syncOptAxisUi();
  document.querySelector("#optMode")?.addEventListener("change", (ev) => {
    const full = ev.target.value === "full";
    const set = (id, val) => {
      const el = document.querySelector(id);
      if (el) el.value = val;
    };
    if (full) {
      setOptRange("optHaLen", 40, 12, 88);
      setOptRange("optHaLen2", 60, 16, 108);
      setOptRange("optOscLen", 5, 2, 11);
      setOptRange("optHaHtf", 15, 15, 30);
      setOptRange("optRr", 1.0, 0.2, 2.0);
      setOptRange("optSwing", 6, 5, 16);
      setOptRange("optMaxSame", 1, 1, 3);
      setOptRange("optTpPct", 1.5, 1.0, 2.5);
      setOptRange("optSlPct", 1.0, 0.5, 1.5);
      set("#optExitMode", "Swing RR, Percent");
      set("#optReverse", "true, false");
      set("#optRequireBar", "true, false");
      applyOptFlags({
        ha_len: true,
        ha_len2: true,
        osc_len: true,
        ha_htf: true,
        exit_mode: true,
        rr_mult: true,
        swing_bars: true,
        tp_pct: true,
        sl_pct: true,
        max_same: true,
        reverse_exit: true,
        require_bar: true,
      });
    } else {
      setOptRange("optHaLen", 48, 16, 80);
      setOptRange("optHaLen2", 72, 24, 96);
      setOptRange("optOscLen", 7, 4, 11);
      setOptRange("optHaHtf", 30, 15, 30);
      setOptRange("optRr", 1.2, 0.4, 2.0);
      setOptRange("optSwing", 8, 3, 11);
      setOptRange("optTpPct", 1.5, 0.5, 2.5);
      setOptRange("optSlPct", 0.8, 0.35, 1.5);
      setOptRange("optMaxSame", 1, 1, 2);
      set("#optExitMode", "Swing RR");
      set("#optReverse", "true");
      set("#optRequireBar", "false");
      applyOptFlags({
        ha_len: true,
        ha_len2: true,
        osc_len: true,
        ha_htf: true,
        exit_mode: false,
        rr_mult: true,
        swing_bars: true,
        tp_pct: true,
        sl_pct: true,
        max_same: true,
        reverse_exit: false,
        require_bar: false,
      });
    }
    syncOptAxisUi();
  });
}

initOptimize();
window.onOptTabShown = onOptTabShown;
