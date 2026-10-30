let optContractsLoaded = false;
let optPollTimer = null;
let optReviewTimer = null;
let optPresets = [];
let optLastPayload = null;
let optJobId = null;
let optLastJobId = null;
let optSort = { key: "rank", dir: "asc" };
let optReviewState = null;
let optSearchPlan = null;
let optPlanTimer = null;
let optPlanSeq = 0;

const OPT_MAX_COMBOS = 50000;

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

function setOptRunState(running) {
  const start = document.querySelector("#btnOptRun");
  const stops = document.querySelectorAll(".btn-opt-stop");
  if (start) start.disabled = !!running || optReviewRunning(optReviewState?.run);
  stops.forEach((btn) => {
    if (btn.id === "btnOptStop") btn.hidden = !running;
    btn.disabled = !running;
  });
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

function fmtOptInt(n) {
  return Number(n || 0).toLocaleString("tr-TR");
}

function formatOptSearchPlan(plan) {
  if (!plan) return "";
  const space = fmtOptInt(plan.space);
  const cap = fmtOptInt(plan.cap);
  const scanAll = !!document.querySelector("#optScanAll")?.checked;
  if (plan.mode !== "refine") {
    if (scanAll) {
      if (plan.space > OPT_MAX_COMBOS) {
        return `Tamamını tara: ${space} set, 1 tur. ${fmtOptInt(OPT_MAX_COMBOS)}’i geçiyor — başlamadan teyit istenir; süre saatler veya bir gün olabilir.`;
      }
      return `Tamamını tara: ${space} set, 1 tur.`;
    }
    return `Izgara ${space} set. Maks. ${cap} → 1 tur, tamamı taranır.`;
  }
  const steps = (plan.strides || []).join(" → ");
  const tours = plan.tours || (plan.strides || []).length;
  const extra = plan.extra_tours || 0;
  if (plan.tour1_discovery) {
    return `Izgara ${space} set. ${tours} tur (keşif + ${steps}, +${extra} kademe). Tur 1 Sobol ${cap} tam adım; sonra kâr ve WR cepleri ayrı sıkılaşır.`;
  }
  const t1 = fmtOptInt(plan.tour1_space);
  if (plan.tour1_sampled) {
    return `Izgara ${space} set. ${tours} tur${extra}: ${steps}. Tur 1 hâlâ ${t1} → Sobol ${cap}. Izgarayı daraltabilirsiniz.`;
  }
  return `Izgara ${space} set. ${tours} tur${extra}: ${steps}. Tur 1 tam ${t1} set, sonra kazanan cepler.`;
}

function scheduleOptSearchPlan() {
  if (optPlanTimer) clearTimeout(optPlanTimer);
  optPlanTimer = setTimeout(() => {
    optPlanTimer = null;
    loadOptSearchPlan();
  }, 280);
}

async function loadOptSearchPlan() {
  const hint = document.querySelector("#optGridHint");
  if (!hint) return;
  const body = collectOptBody();
  if (!body.symbol) body.symbol = "PLAN";
  const seq = (optPlanSeq += 1);
  try {
    const res = await apiFetch("/api/optimize/plan", {
      method: "POST",
      body: JSON.stringify(body),
    });
    const plan = await res.json().catch(() => ({}));
    if (seq !== optPlanSeq) return;
    if (!res.ok) throw new Error(plan.detail || "Plan alınamadı");
    optSearchPlan = plan;
    hint.textContent = formatOptSearchPlan(plan);
  } catch (_err) {
    if (seq !== optPlanSeq) return;
  }
}

function syncOptGridHint() {
  const hint = document.querySelector("#optGridHint");
  if (!hint) return;
  const scanAll = !!document.querySelector("#optScanAll")?.checked;
  const maxEl = document.querySelector("#optMaxCombos");
  if (maxEl) maxEl.disabled = scanAll;
  if (optSearchPlan) {
    hint.textContent = formatOptSearchPlan(optSearchPlan);
  }
  scheduleOptSearchPlan();
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
  syncOptExportButtons(all.length);
  if (!all.length) {
    if (countEl) {
      countEl.hidden = true;
      countEl.textContent = "";
    }
    const err = optLastPayload?.error ? ` ${optLastPayload.error}` : "";
    const waiting = optLastPayload?.partial || !!optJobId;
    body.innerHTML = waiting
      ? `<tr class="empty"><td colspan="19">Sonuçlar bulundukça burada listelenir.</td></tr>`
      : `<tr class="empty"><td colspan="19">Eşikleri geçen (veya yakın) set yok.${optEsc(err)}</td></tr>`;
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
        <td><div class="opt-row-actions">
          <button type="button" class="btn secondary btn-sm" data-opt-chart="${json}">Grafik</button>
          <button type="button" class="btn secondary btn-sm" data-opt-copy="${json}">Kopyala</button>
        </div></td>
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
  body.querySelectorAll("[data-opt-chart]").forEach((btn) => {
    btn.addEventListener("click", () => openOptChart(btn.getAttribute("data-opt-chart")));
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

function renderOptResults(payload, live) {
  optLastPayload = payload || {};
  if (!live) optSort = { key: "rank", dir: "asc" };
  const title = document.querySelector("#optResultTitle");
  const hint = document.querySelector("#optResultHint");
  const passed = optLastPayload.passed ?? 0;
  const tested = optLastPayload.tested ?? 0;
  const space = optLastPayload.grid_size || 0;
  if (title) {
    const liveBit = optLastPayload.partial ? " · taranıyor" : "";
    title.textContent = `${optLastPayload.symbol || ""} sonuçları${liveBit}`;
  }
  if (hint) {
    const refine = optLastPayload.refine;
    let comboBit;
    if (refine && refine.mode === "refine") {
      const steps = (refine.strides || []).join("→");
      comboBit = `${refine.tours || (refine.strides || []).length} tur (${steps}) · ${tested} set / ${fmtOptInt(space)} olası`;
    } else if (space > tested) {
      comboBit = `${tested} ${optLastPayload.sampling === "qmc" ? "Sobol/LHS örnek" : "örnek"} / ${fmtOptInt(space)} olası`;
    } else {
      comboBit = `${tested} kombinasyon`;
    }
    const liveBit = optLastPayload.partial ? " · taranıyor" : "";
    hint.textContent = `${optLastPayload.bars || 0} bar · ${optLastPayload.from || ""} → ${optLastPayload.to || ""} · ${comboBit} · ${passed} eşik geçti${liveBit}`;
  }
  renderOptCompare(optLastPayload);
  syncOptSortHeaders();
  paintOptTable();
}

function optChartMoney(n) {
  return Number(n || 0).toLocaleString("tr-TR", { maximumFractionDigits: 0 });
}

function optChartPct(n, digits = 2) {
  const v = Number(n) || 0;
  const sign = v > 0 ? "+" : "";
  return `${sign}${v.toFixed(digits)}%`;
}

function optMonthLabel(period) {
  const names = ["Oca", "Şub", "Mar", "Nis", "May", "Haz", "Tem", "Ağu", "Eyl", "Eki", "Kas", "Ara"];
  const [y, m] = String(period || "").split("-");
  const i = Number(m) - 1;
  const label = names[i] || m || period;
  return Number(m) === 1 ? `${label} ${y}` : label;
}

function optChartDate(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return String(iso).slice(0, 10);
  return d.toLocaleDateString("tr-TR", { day: "numeric", month: "short", year: "numeric" });
}

function renderOptChartSvg(data) {
  const points = data.equity || [];
  const months = data.months || [];
  const width = 980;
  const height = 520;
  const pad = { left: 62, right: 18, top: 14, bottom: 34 };
  const equityH = 318;
  const barH = 108;
  const barTop = pad.top + equityH + 28;
  const innerW = width - pad.left - pad.right;
  const eqs = points.map((p) => Number(p.equity) || 0);
  const lo = Math.min(...eqs, data.start_equity || 0);
  const hi = Math.max(...eqs, data.start_equity || 0);
  const span = hi - lo || 1;
  const yEq = (v) => pad.top + (1 - (v - lo) / span) * equityH;
  const xEq = (i) => pad.left + (points.length <= 1 ? innerW / 2 : (i / (points.length - 1)) * innerW);
  const line = points
    .map((p, i) => `${i ? "L" : "M"}${xEq(i).toFixed(1)},${yEq(p.equity).toFixed(1)}`)
    .join(" ");
  const area = points.length
    ? `${line} L${xEq(points.length - 1).toFixed(1)},${(pad.top + equityH).toFixed(1)} L${xEq(0).toFixed(1)},${(pad.top + equityH).toFixed(1)} Z`
    : "";
  const yTicks = 4;
  const grid = Array.from({ length: yTicks + 1 }, (_, i) => {
    const val = hi - (span * i) / yTicks;
    const y = yEq(val).toFixed(1);
    return `<line x1="${pad.left}" y1="${y}" x2="${width - pad.right}" y2="${y}" class="opt-chart-grid"/>
      <text x="${pad.left - 8}" y="${y}" class="opt-chart-axis" text-anchor="end" dominant-baseline="middle">${optChartMoney(val)}</text>`;
  }).join("");
  const xLabels = points
    .map((p, i) => {
      const show = points.length <= 8 || i === 0 || i === points.length - 1 || i % Math.ceil(points.length / 6) === 0;
      if (!show) return "";
      return `<text x="${xEq(i).toFixed(1)}" y="${pad.top + equityH + 16}" class="opt-chart-axis" text-anchor="middle">${optEsc(optChartDate(p.t))}</text>`;
    })
    .join("");
  const dots = points
    .map((p, i) => {
      if (i === 0) return "";
      const title = `${optChartDate(p.t)} · ${optChartMoney(p.equity)} · ${optChartPct(p.pnl_pct)}`;
      return `<circle cx="${xEq(i).toFixed(1)}" cy="${yEq(p.equity).toFixed(1)}" r="3.2" class="opt-chart-dot"><title>${optEsc(title)}</title></circle>`;
    })
    .join("");
  const pnls = months.map((m) => Number(m.pnl) || 0);
  const maxAbs = Math.max(1, ...pnls.map((v) => Math.abs(v)));
  const zeroY = barTop + barH / 2;
  const barW = months.length ? Math.min(36, (innerW / months.length) * 0.62) : 16;
  const bars = months
    .map((m, i) => {
      const xCenter = pad.left + (months.length <= 1 ? innerW / 2 : ((i + 0.5) / months.length) * innerW);
      const pnl = Number(m.pnl) || 0;
      const h = (Math.abs(pnl) / maxAbs) * (barH / 2 - 4);
      const y = pnl >= 0 ? zeroY - h : zeroY;
      const cls = pnl >= 0 ? "opt-chart-bar-up" : "opt-chart-bar-down";
      return `<rect x="${(xCenter - barW / 2).toFixed(1)}" y="${y.toFixed(1)}" width="${barW.toFixed(1)}" height="${Math.max(1.5, h).toFixed(1)}" class="${cls}" rx="2">
        <title>${optEsc(`${optMonthLabel(m.period)} · ${optChartMoney(pnl)}`)}</title>
      </rect>
      <text x="${xCenter.toFixed(1)}" y="${barTop + barH + 16}" class="opt-chart-axis" text-anchor="middle">${optEsc(optMonthLabel(m.period))}</text>`;
    })
    .join("");
  return `<svg viewBox="0 0 ${width} ${height}" class="opt-chart-svg" role="img" aria-label="Strateji sermaye grafiği">
    <defs>
      <linearGradient id="optChartFill" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stop-color="#26a69a" stop-opacity="0.28"/>
        <stop offset="100%" stop-color="#26a69a" stop-opacity="0"/>
      </linearGradient>
    </defs>
    <rect x="${pad.left}" y="${pad.top}" width="${innerW}" height="${equityH}" class="opt-chart-plot"/>
    ${grid}
    ${area ? `<path d="${area}" class="opt-chart-area"/>` : ""}
    ${line ? `<path d="${line}" class="opt-chart-line"/>` : ""}
    ${dots}
    ${xLabels}
    <rect x="${pad.left}" y="${barTop}" width="${innerW}" height="${barH}" class="opt-chart-plot"/>
    <line x1="${pad.left}" y1="${zeroY}" x2="${width - pad.right}" y2="${zeroY}" class="opt-chart-grid"/>
    ${bars || `<text x="${width / 2}" y="${zeroY}" class="opt-chart-axis" text-anchor="middle">Aylık kâr/zarar yok</text>`}
  </svg>`;
}

function renderOptChartStats(data) {
  const m = data.metrics || {};
  const net = Number(m.net_profit_pct) || 0;
  const items = [
    ["Toplam kâr", optChartPct(net), net >= 0 ? "up" : "down"],
    ["Sermaye", `${optChartMoney(data.start_equity)} → ${optChartMoney(data.end_equity)}`, net >= 0 ? "up" : "down"],
    ["Maks. düşüş", `${Number(m.max_drawdown || 0).toFixed(2)}%`, "down"],
    ["Kârlı işlem", `${m.wins || 0}/${m.trades || 0} · WR ${Number(m.win_rate || 0).toFixed(2)}%`, ""],
    ["Kâr faktörü", Number(m.profit_factor || 0).toFixed(3), Number(m.profit_factor) >= 1 ? "up" : "down"],
  ];
  return items
    .map(([label, value, cls]) => `<div class="opt-chart-stat ${cls}"><span>${label}</span><strong>${optEsc(value)}</strong></div>`)
    .join("");
}

function bindOptChartLightDismiss(dialog) {
  if (!dialog || "closedBy" in HTMLDialogElement.prototype) return;
  let pressedOutside = false;
  const outside = (e) => {
    const r = dialog.getBoundingClientRect();
    return e.clientX < r.left || e.clientX > r.right || e.clientY < r.top || e.clientY > r.bottom;
  };
  dialog.addEventListener("pointerdown", (e) => {
    pressedOutside = outside(e);
  });
  dialog.addEventListener("pointerup", (e) => {
    if (pressedOutside && outside(e) && dialog.open) dialog.close();
  });
}

async function openOptChart(raw, extra) {
  const dialog = document.querySelector("#optChartDialog");
  const wrap = document.querySelector("#optChartWrap");
  const title = document.querySelector("#optChartTitle");
  const meta = document.querySelector("#optChartMeta");
  const stats = document.querySelector("#optChartStats");
  if (!dialog || !wrap) return;
  let params = {};
  try {
    params = JSON.parse(raw || "{}");
  } catch {
    optStatus("Grafik parametresi okunamadı.", "error");
    return;
  }
  const payload = optLastPayload || {};
  const ctx = extra || {};
  const symbol = ctx.symbol || payload.symbol;
  const timeframe = ctx.timeframe || payload.timeframe || "15m";
  const period = ctx.period || payload.period || "60d";
  const jobId = "job_id" in ctx ? (ctx.job_id || "") : (optLastJobId || optJobId || payload.job_id || "");
  wrap.innerHTML = '<p class="hint">Grafik hazırlanıyor…</p>';
  if (stats) stats.innerHTML = "";
  if (title) title.textContent = `${symbol || "Set"} — strateji grafiği`;
  if (meta) meta.textContent = "Sermaye eğrisi ve aylık kâr/zarar yükleniyor…";
  if (typeof dialog.showModal === "function") dialog.showModal();
  else dialog.setAttribute("open", "");
  try {
    const res = await apiFetch("/api/optimize/chart", {
      method: "POST",
      body: JSON.stringify({
        symbol,
        timeframe,
        period,
        job_id: jobId,
        params,
      }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || "Grafik alınamadı");
    if (title) title.textContent = `${data.symbol || symbol || ""} — strateji grafiği`;
    if (meta) {
      meta.textContent = `${data.timeframe || ""} · ${optChartDate(data.from)} – ${optChartDate(data.to)} · ${data.bars || 0} bar · ${data.metrics?.trades || 0} işlem`;
    }
    if (stats) stats.innerHTML = renderOptChartStats(data);
    wrap.innerHTML = renderOptChartSvg(data);
  } catch (err) {
    wrap.innerHTML = `<p class="hint">${optEsc(err.message || "Grafik yüklenemedi.")}</p>`;
  }
}

function syncOptExportButtons(count) {
  const n = Number(count);
  const on = Number.isFinite(n) ? n > 0 : (optLastPayload?.results || []).length > 0;
  ["#btnOptExportCsv", "#btnOptExportXml"].forEach((id) => {
    const el = document.querySelector(id);
    if (el) el.disabled = !on;
  });
}

function optExportRows() {
  const all = optLastPayload?.results || [];
  const filtered = sortOptRows(filterOptRows(all));
  return filtered.length ? filtered : all;
}

function optExportFilename(ext) {
  const p = optLastPayload || {};
  const sym = String(p.symbol || "bias").replace(/[^\w.-]+/g, "_");
  const tf = String(p.timeframe || "").replace(/[^\w]+/g, "");
  const day = new Date().toISOString().slice(0, 10);
  const bits = ["bias-tester", sym, tf, day].filter(Boolean);
  return `${bits.join("-")}.${ext}`;
}

function optCsvCell(value) {
  const s = String(value ?? "");
  if (/[",\r\n]/.test(s)) return `"${s.replace(/"/g, '""')}"`;
  return s;
}

function optXmlEsc(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&apos;");
}

function optDownloadText(filename, text, mime) {
  const blob = new Blob([text], { type: mime });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.rel = "noopener";
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

function optRowExportFields(row) {
  const p = row.params || {};
  const meta = optLastPayload || {};
  return {
    symbol: meta.symbol || "",
    timeframe: meta.timeframe || "",
    period: meta.period || "",
    rank: row.rank ?? "",
    tag: row.tag || "",
    passed: row.passed ? "evet" : "hayir",
    win_rate: row.win_rate ?? "",
    profit_factor: row.profit_factor ?? "",
    net_profit_pct: row.net_profit_pct ?? "",
    max_drawdown: row.max_drawdown ?? "",
    trades: row.trades ?? "",
    ha_len: p.ha_len ?? "",
    ha_len2: p.ha_len2 ?? "",
    osc_len: p.osc_len ?? "",
    ha_htf: p.ha_htf || "chart",
    exit_mode: p.exitMode || "",
    rr_mult: p.exitMode === "Percent" ? "" : (p.rrMult ?? ""),
    swing_bars: p.exitMode === "Percent" ? "" : (p.swingBars ?? ""),
    tp_pct: p.exitMode === "Percent" ? (p.tp_pct ?? "") : "",
    sl_pct: p.exitMode === "Percent" ? (p.sl_pct ?? "") : "",
    reverse_exit: p.reverse_exit ? "acik" : "kapali",
    require_bar: p.require_bar ? "acik" : "kapali",
    max_same: p.maxSame ?? "",
  };
}

const OPT_EXPORT_COLS = [
  ["symbol", "sembol"],
  ["timeframe", "periyot"],
  ["period", "veri_suresi"],
  ["rank", "sira"],
  ["tag", "etiket"],
  ["passed", "esik_gecti"],
  ["win_rate", "wr"],
  ["profit_factor", "pf"],
  ["net_profit_pct", "kar_pct"],
  ["max_drawdown", "dd_pct"],
  ["trades", "islem"],
  ["ha_len", "ha"],
  ["ha_len2", "smooth"],
  ["osc_len", "osc"],
  ["ha_htf", "htf"],
  ["exit_mode", "cikis"],
  ["rr_mult", "rr"],
  ["swing_bars", "swing"],
  ["tp_pct", "tp_pct"],
  ["sl_pct", "sl_pct"],
  ["reverse_exit", "rev"],
  ["require_bar", "mum"],
  ["max_same", "same"],
];

function buildOptCsv(rows) {
  const header = OPT_EXPORT_COLS.map(([, title]) => optCsvCell(title)).join(",");
  const lines = rows.map((row) => {
    const fields = optRowExportFields(row);
    return OPT_EXPORT_COLS.map(([key]) => optCsvCell(fields[key])).join(",");
  });
  return `\uFEFF${[header, ...lines].join("\r\n")}\r\n`;
}

function buildOptXml(rows) {
  const meta = optLastPayload || {};
  const scanAttrs = [
    ["symbol", meta.symbol],
    ["timeframe", meta.timeframe],
    ["period", meta.period],
    ["bars", meta.bars],
    ["from", meta.from],
    ["to", meta.to],
    ["tested", meta.tested],
    ["passed", meta.passed],
    ["gridSize", meta.grid_size],
  ]
    .filter(([, v]) => v != null && v !== "")
    .map(([k, v]) => `${k}="${optXmlEsc(v)}"`)
    .join(" ");
  const root = scanAttrs ? `<biasScan ${scanAttrs}>` : "<biasScan>";
  const body = rows
    .map((row) => {
      const fields = optRowExportFields(row);
      const cells = OPT_EXPORT_COLS.map(([key, title]) => `    <${title}>${optXmlEsc(fields[key])}</${title}>`).join("\n");
      return `  <row>\n${cells}\n  </row>`;
    })
    .join("\n");
  return `<?xml version="1.0" encoding="UTF-8"?>\n${root}\n${body}\n</biasScan>\n`;
}

function exportOptResults(kind) {
  const rows = optExportRows();
  if (!rows.length) {
    optStatus("Kaydedilecek sonuç yok.", "error");
    return;
  }
  const xml = kind === "xml";
  const filename = optExportFilename(xml ? "xml" : "csv");
  const text = xml ? buildOptXml(rows) : buildOptCsv(rows);
  const mime = xml ? "application/xml;charset=utf-8" : "text/csv;charset=utf-8";
  optDownloadText(filename, text, mime);
  optStatus(`${rows.length} satır ${xml ? "XML" : "CSV"} olarak indirildi.`, "ok");
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
    max_combos: Math.max(20, Math.min(OPT_MAX_COMBOS, Math.round(optNum("#optMaxCombos", 180)))),
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
  if (period === "13mo" || period === "2y") {
    extra += " 15m geçmiş TV grafiğindeki gibi parça parça iner; daha kısa süre de seçebilirsiniz.";
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

function finishOptJob(job) {
  hideOptProgress();
  setOptRunState(false);
  optJobId = null;
  if (job.status === "error") {
    optStatus(job.error || job.message || "Tarama hata verdi", "error");
    return;
  }
  const payload = job.result || {};
  const tested = payload.tested ?? 0;
  const passed = payload.passed ?? 0;
  const space = payload.grid_size || 0;
  if (job.status === "cancelled") {
    if (payload.results?.length) {
      renderOptResults(payload);
      optStatus(`Tarama durduruldu. ${tested} set denendi.`, "ok");
    } else {
      optStatus("Tarama durduruldu.", "error");
    }
    return;
  }
  renderOptResults(payload);
  let msg = passed
    ? `${passed} set eşikleri geçti.`
    : "Eşik geçen set yok; tabloda en yakın sonuçlar var.";
  if (!passed && space > tested) {
    msg = `Eşik geçen set yok. ${tested} örnek, ${Number(space).toLocaleString("tr-TR")} olası — ızgarayı daraltın veya optimize edilmeyen eksenleri kapatın.`;
  }
  optStatus(msg, passed ? "ok" : "error");
}

async function pollOptJob(jobId) {
  const stRes = await apiFetch(`/api/optimize/jobs/${jobId}`);
  const job = await stRes.json();
  if (!stRes.ok) throw new Error(job.detail || "Durum alınamadı");
  setOptProgress(job.progress ?? 0, job.message || "Çalışıyor…");
  if (job.status === "running") {
    if (job.phase === "cancelling") {
      optStatus("Durduruluyor…");
    } else if (job.phase === "downloading") {
      optStatus(job.message || "Veri indiriliyor…");
    } else {
      const passed = job.result?.passed ?? 0;
      optStatus(passed ? `Tarama devam ediyor… ${passed} eşik geçti.` : "Tarama devam ediyor…");
    }
    if (job.result?.results?.length) {
      renderOptResults(job.result, true);
    }
    optPollTimer = setTimeout(() => {
      pollOptJob(jobId).catch((err) => {
        optStatus(err.message, "error");
        hideOptProgress();
        setOptRunState(false);
        optJobId = null;
      });
    }, 900);
    return;
  }
  finishOptJob(job);
}

async function stopOptRun() {
  if (!optJobId) return;
  document.querySelectorAll(".btn-opt-stop").forEach((btn) => {
    btn.disabled = true;
  });
  optStatus("Durduruluyor…");
  try {
    const res = await apiFetch(`/api/optimize/jobs/${optJobId}/stop`, { method: "POST" });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || "Durdurulamadı");
    setOptProgress(data.progress ?? 0, data.message || "Durduruluyor…");
  } catch (err) {
    optStatus(err.message || "Durdurulamadı", "error");
    document.querySelectorAll(".btn-opt-stop").forEach((btn) => {
      btn.disabled = false;
    });
  }
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
  if (body.scan_all && space > OPT_MAX_COMBOS) {
    const ok = confirm(
      `Izgara ${Number(space).toLocaleString("tr-TR")} set. Tamamını tara ${OPT_MAX_COMBOS.toLocaleString("tr-TR")}’den fazla — saatler veya bir gün sürebilir. Yine de başlatılsın mı?`,
    );
    if (!ok) return;
  }
  setOptRunState(true);
  optJobId = null;
  optLastPayload = { results: [], partial: true };
  paintOptTable();
  const planText = formatOptSearchPlan(optSearchPlan);
  optStatus(planText || "Tarama başlatılıyor…");
  if (optSearchPlan?.mode === "refine") {
    setOptProgress(2, `Tur 1/${optSearchPlan.tours} keşif Sobol`);
  } else {
    setOptProgress(2, "Başlatılıyor…");
  }
  try {
    const res = await apiFetch("/api/optimize/bias", {
      method: "POST",
      body: JSON.stringify(body),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      throw new Error(data.detail || "Başlatılamadı");
    }
    optJobId = data.job_id;
    optLastJobId = data.job_id;
    await pollOptJob(data.job_id);
  } catch (err) {
    hideOptProgress();
    setOptRunState(false);
    optJobId = null;
    optStatus(err.message || "Hata", "error");
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

function optReviewRunning(run) {
  return !!run && (run.status === "running" || run.status === "cancelling");
}

function optReviewStatus(msg, kind) {
  const el = document.querySelector("#optReviewStatus");
  if (!el) return;
  el.textContent = msg || "";
  el.classList.toggle("ok", kind === "ok");
  el.classList.toggle("error", kind === "error");
}

function fmtOptNum(v, digits) {
  const n = Number(v);
  if (!Number.isFinite(n)) return "—";
  return n.toLocaleString("tr-TR", { maximumFractionDigits: digits ?? 2 });
}

function optReviewParamLine(rec) {
  const p = rec?.params || rec?.pine_overrides || {};
  const exit = p.exitMode || p.exit_mode || "";
  const parts = [
    `HA ${p.ha_len ?? "—"} / ${p.ha_len2 ?? "—"}`,
    `osc ${p.osc_len ?? "—"}`,
    `HTF ${p.ha_htf || "—"}`,
    exit,
  ];
  if (String(exit).toLowerCase().includes("percent")) {
    parts.push(`TP ${p.tp_pct ?? "—"} / SL ${p.sl_pct ?? "—"}`);
  } else {
    parts.push(`RR ${p.rrMult ?? p.rr_mult ?? "—"}`, `swing ${p.swingBars ?? p.swing_bars ?? "—"}`);
  }
  parts.push(`same ${p.maxSame ?? p.max_same ?? "—"}`);
  return parts.filter(Boolean).join(" · ");
}

function optRevMetric(label, value, key, highlights) {
  const text = `${label} ${value}`;
  if ((highlights || []).includes(key)) return `<strong>${optEsc(text)}</strong>`;
  return optEsc(text);
}

function optRevWhy(reasons) {
  return (reasons || [])
    .map((r) => {
      const text = String(r);
      const improved = /^(WR|PF|Kâr|DD)\b/.test(text);
      return improved ? `<strong>${optEsc(text)}</strong>` : optEsc(text);
    })
    .join(" · ");
}

function renderOptReviewRec(rec, item) {
  const hl = rec.highlights || [];
  const why = optRevWhy(rec.reasons);
  const params = rec.pine_overrides || pineOverridesFromRow(rec.params || {});
  const json = optEsc(JSON.stringify(params));
  const cfg = optReviewState?.run?.config || optReviewState?.settings?.config || {};
  const symbol = item?.symbol || "";
  const timeframe = item?.timeframe || cfg.timeframe || "30m";
  const period = item?.period || cfg.period || "13mo";
  return `<div class="opt-rev-rec">
    <div class="opt-rev-rec-top">
      <div class="opt-rev-rec-metrics">${optRevMetric("WR", `${fmtOptNum(rec.win_rate, 1)}%`, "win_rate", hl)} · ${optRevMetric("PF", fmtOptNum(rec.profit_factor, 2), "profit_factor", hl)} · ${optRevMetric("Kâr", `${fmtOptNum(rec.net_profit_pct, 1)}%`, "net_profit_pct", hl)} · ${optRevMetric("DD", `${fmtOptNum(rec.max_drawdown, 1)}%`, "max_drawdown", hl)} · ${optEsc(fmtOptNum(rec.trades, 0))} işlem</div>
      <button type="button" class="btn secondary btn-sm" data-opt-review-chart="${json}" data-symbol="${optEsc(symbol)}" data-timeframe="${optEsc(timeframe)}" data-period="${optEsc(period)}">Grafik</button>
    </div>
    <div class="opt-rev-rec-params">${optEsc(optReviewParamLine(rec))}</div>
    ${why ? `<div class="opt-rev-rec-why">${why}</div>` : ""}
  </div>`;
}

function renderOptReviewPay(item) {
  const recs = item.recommendations || [];
  const extras = item.extras || [];
  const alarm = item.alarm;
  const title = `${item.symbol || ""}${item.name ? ` · ${item.name}` : ""}`;
  const recLabel = alarm ? `${recs.length} revizyon` : `${recs.length} alarm önerisi`;
  const alarmLabel = alarm ? `alarm «${alarm.name || alarm.id}»` : "alarm yok";
  const extraBlock = extras.length
    ? `<details class="opt-rev-extra"><summary>${extras.length} diğer set</summary>${extras.map((r) => renderOptReviewRec(r, item)).join("")}</details>`
    : "";
  const body = item.status === "error"
    ? `<p class="opt-rev-note">${optEsc(item.error || item.note || "Tarama hata verdi")}</p>`
    : `${item.note ? `<p class="opt-rev-note">${optEsc(item.note)}</p>` : ""}${recs.map((r) => renderOptReviewRec(r, item)).join("")}${extraBlock}`;
  return `<article class="opt-rev-pay">
    <div class="opt-rev-pay-head">
      <h3>${optEsc(title)}</h3>
      <span class="opt-rev-pay-meta">${optEsc(recLabel)} · ${optEsc(alarmLabel)}${item.tested ? ` · ${item.tested} set` : ""}</span>
    </div>
    ${body}
  </article>`;
}

function renderOptReview(payload) {
  optReviewState = payload || null;
  const settings = payload?.settings || {};
  const run = payload?.run;
  const weekly = document.querySelector("#optReviewWeekly");
  if (weekly) weekly.checked = !!settings.weekly_enabled;
  const notify = document.querySelector("#optReviewNotifyEmail");
  if (notify) notify.checked = settings.notify_email !== false;
  const notifyTg = document.querySelector("#optReviewNotifyTelegram");
  if (notifyTg) notifyTg.checked = settings.notify_telegram !== false;
  const email = document.querySelector("#optReviewEmail");
  if (email && document.activeElement !== email) {
    email.value = settings.email_to || "veliakman@gmail.com; akbastt@gmail.com";
  }
  const tg = document.querySelector("#optReviewTelegram");
  if (tg && document.activeElement !== tg) tg.value = settings.telegram_to || "";
  const mailHint = document.querySelector("#optReviewMailHint");
  if (mailHint) {
    const smtp = settings.smtp_configured
      ? "SMTP hazır (zamanlanmış tarama ile aynı)."
      : "SMTP yok (.env: SMTP_HOST, SMTP_FROM).";
    const telegram = settings.telegram_configured
      ? "Telegram hazır."
      : "Telegram yok (.env: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID).";
    mailHint.textContent = `${smtp} ${telegram} Adresleri virgül veya noktalı virgülle ayırın.`;
  }
  const summary = document.querySelector("#optReviewSummary");
  const running = optReviewRunning(run);
  const done = run?.done_count || 0;
  const total = run?.total_count || 0;
  const remaining = run?.remaining_count ?? Math.max(0, total - done);
  const pct = total ? Math.round((done / total) * 100) : 0;
  if (summary) {
    if (run?.summary) summary.textContent = run.summary;
    else if (settings.weekly_enabled) summary.textContent = "Haftalık tarama açık · sonraki start Cuma 19:00 İstanbul.";
    else summary.textContent = "Henüz rapor yok. Haftalık tarama kapalı.";
  }
  const prog = document.querySelector("#optReviewProgress");
  const bar = document.querySelector("#optReviewProgressBar");
  const label = document.querySelector("#optReviewProgressLabel");
  if (prog) prog.hidden = !run || (!running && done === 0);
  if (bar) bar.style.width = `${Math.max(0, Math.min(100, pct))}%`;
  if (label) {
    label.textContent = running && run.current_symbol
      ? `${done}/${total} · ${run.current_symbol} · kalan ${remaining}`
      : `${done}/${total}`;
  }
  const start = document.querySelector("#btnOptReviewStart");
  const stop = document.querySelector("#btnOptReviewStop");
  if (start) start.disabled = running || !!optJobId;
  if (stop) {
    stop.hidden = !running;
    stop.disabled = run?.status === "cancelling";
  }
  const testerStart = document.querySelector("#btnOptRun");
  if (testerStart && running) testerStart.disabled = true;
  else if (testerStart && !optJobId) testerStart.disabled = false;
  const report = document.querySelector("#optReviewReport");
  const symbols = run?.symbols || [];
  if (report) {
    if (!symbols.length) {
      report.innerHTML = running
        ? `<p class="hint">İlk pay taranıyor: ${optEsc(run.current_symbol || "…")}</p>`
        : (document.querySelector("#optReviewPageRoot")
          ? `<p class="hint">Henüz kayıtlı revizyon raporu yok. Tester’dan taramayı başlatın.</p>`
          : "");
    } else {
      const live = running && run.current_symbol
        ? `<p class="hint">Şimdi ${optEsc(run.current_symbol)} · kalan ${remaining} pay</p>`
        : "";
      report.innerHTML = live + symbols.map(renderOptReviewPay).join("");
    }
  }
}

function scheduleOptReviewPoll(run) {
  if (optReviewTimer) {
    clearTimeout(optReviewTimer);
    optReviewTimer = null;
  }
  if (!optReviewRunning(run)) return;
  optReviewTimer = setTimeout(() => {
    loadOptReview().catch(() => {});
  }, 5000);
}

async function loadOptReview() {
  const res = await apiFetch("/api/optimize/review");
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || "Rapor alınamadı");
  renderOptReview(data);
  scheduleOptReviewPoll(data.run);
  return data;
}

async function saveOptReviewMail() {
  const email = document.querySelector("#optReviewEmail")?.value || "";
  const notify = !!document.querySelector("#optReviewNotifyEmail")?.checked;
  const notifyTg = !!document.querySelector("#optReviewNotifyTelegram")?.checked;
  const telegram = document.querySelector("#optReviewTelegram")?.value || "";
  try {
    const res = await apiFetch("/api/optimize/review/settings", {
      method: "PUT",
      body: JSON.stringify({
        email_to: email,
        notify_email: notify,
        notify_telegram: notifyTg,
        telegram_to: telegram,
      }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || "Kanal kaydı başarısız");
    const parts = [];
    if (notify) parts.push(`e-posta ${data.email_to || email}`);
    if (notifyTg) parts.push("Telegram");
    optReviewStatus(parts.length ? `Bitince: ${parts.join(" · ")}` : "Bitince bildirim kapalı.", "ok");
    if (optReviewState) optReviewState.settings = data;
  } catch (err) {
    optReviewStatus(err.message || "Kanal kaydı hatası", "error");
  }
}

async function sendOptReviewMail() {
  optReviewStatus("Rapor gönderiliyor (SMTP / Telegram)…");
  try {
    const res = await apiFetch("/api/optimize/review/email", { method: "POST" });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || "Gönderilemedi");
    const parts = [];
    if (data.email) parts.push("e-posta");
    if (data.telegram) parts.push("Telegram");
    const warn = (data.warnings || []).join(" · ");
    optReviewStatus(
      `${parts.length ? `Gönderildi: ${parts.join(" · ")}` : "Gönderilemedi."}${warn ? ` ${warn}` : ""}`,
      parts.length ? "ok" : "error",
    );
  } catch (err) {
    optReviewStatus(err.message || "Gönderilemedi", "error");
  }
}

async function saveOptReviewWeekly() {
  const on = !!document.querySelector("#optReviewWeekly")?.checked;
  try {
    const res = await apiFetch("/api/optimize/review/settings", {
      method: "PUT",
      body: JSON.stringify({ weekly_enabled: on }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || "Kayıt başarısız");
    optReviewStatus(on ? "Cuma 19:00 tarama açık." : "Haftalık tarama kapalı.", "ok");
    if (optReviewState) optReviewState.settings = data;
    renderOptReview({ ...(optReviewState || {}), settings: data });
  } catch (err) {
    optReviewStatus(err.message || "Kayıt hatası", "error");
  }
}

async function saveOptReviewGrid() {
  const body = collectOptBody();
  delete body.symbol;
  delete body.reference;
  try {
    const res = await apiFetch("/api/optimize/review/settings", {
      method: "PUT",
      body: JSON.stringify({ config: body }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || "Izgara kaydedilemedi");
    optReviewStatus("Haftalık tarama ızgarası kaydedildi (30m / 13 ay önerilir).", "ok");
    if (optReviewState) optReviewState.settings = data;
  } catch (err) {
    optReviewStatus(err.message || "Kayıt hatası", "error");
  }
}

async function startOptReview() {
  optReviewStatus("47 pay taraması başlatılıyor…");
  try {
    const res = await apiFetch("/api/optimize/review/start", {
      method: "POST",
      body: JSON.stringify({}),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || "Başlatılamadı");
    optReviewStatus("Revizyon taraması çalışıyor.", "ok");
    await loadOptReview();
  } catch (err) {
    optReviewStatus(err.message || "Başlatılamadı", "error");
  }
}

async function stopOptReview() {
  try {
    const res = await apiFetch("/api/optimize/review/stop", { method: "POST" });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || "Durdurulamadı");
    optReviewStatus("Durduruluyor…");
    renderOptReview({ ...(optReviewState || {}), run: data });
    scheduleOptReviewPoll(data);
  } catch (err) {
    optReviewStatus(err.message || "Durdurulamadı", "error");
  }
}

async function onOptTabShown() {
  await loadOptContracts();
  await loadOptPresets();
  syncOptAxisUi();
  try {
    await loadOptReview();
  } catch (err) {
    optReviewStatus(err.message || "Rapor alınamadı", "error");
  }
}

function initOptimize() {
  document.querySelector("#optForm")?.addEventListener("submit", startOptRun);
  document.querySelectorAll(".btn-opt-stop").forEach((btn) => {
    btn.addEventListener("click", stopOptRun);
  });
  document.querySelector("#optExitMode")?.addEventListener("change", syncOptExitFields);
  document.querySelectorAll(".opt-enable").forEach((el) => {
    el.addEventListener("change", syncOptAxisUi);
  });
  document.querySelector(".opt-results-table thead")?.addEventListener("click", onOptSortClick);
  document.querySelector("#btnOptExportCsv")?.addEventListener("click", () => exportOptResults("csv"));
  document.querySelector("#btnOptExportXml")?.addEventListener("click", () => exportOptResults("xml"));
  bindOptChartLightDismiss(document.querySelector("#optChartDialog"));
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
  document.querySelector("#optReviewWeekly")?.addEventListener("change", saveOptReviewWeekly);
  document.querySelector("#optReviewNotifyEmail")?.addEventListener("change", saveOptReviewMail);
  document.querySelector("#optReviewNotifyTelegram")?.addEventListener("change", saveOptReviewMail);
  document.querySelector("#btnOptReviewSaveMail")?.addEventListener("click", saveOptReviewMail);
  document.querySelector("#btnOptReviewSendMail")?.addEventListener("click", sendOptReviewMail);
  document.querySelector("#optReviewEmail")?.addEventListener("change", saveOptReviewMail);
  document.querySelector("#optReviewTelegram")?.addEventListener("change", saveOptReviewMail);
  document.querySelector("#optReviewReport")?.addEventListener("click", (ev) => {
    const btn = ev.target.closest("[data-opt-review-chart]");
    if (!btn) return;
    openOptChart(btn.getAttribute("data-opt-review-chart"), {
      symbol: btn.getAttribute("data-symbol") || "",
      timeframe: btn.getAttribute("data-timeframe") || "30m",
      period: btn.getAttribute("data-period") || "13mo",
      job_id: "",
    });
  });
  document.querySelector("#btnOptReviewSaveGrid")?.addEventListener("click", saveOptReviewGrid);
  document.querySelector("#btnOptReviewStart")?.addEventListener("click", startOptReview);
  document.querySelector("#btnOptReviewOpen")?.addEventListener("click", () => {
    window.open("/optimize/review", "_blank", "noopener");
  });
  document.querySelector("#btnOptReviewStop")?.addEventListener("click", stopOptReview);
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
if (document.querySelector("#optReviewPageRoot")) {
  const boot = typeof bootstrapAuth === "function" ? bootstrapAuth() : Promise.resolve();
  Promise.resolve(boot)
    .then(() => loadOptReview())
    .catch((err) => optReviewStatus(err.message || "Rapor alınamadı", "error"));
}
