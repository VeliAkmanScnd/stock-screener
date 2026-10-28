let optContractsLoaded = false;
let optPollTimer = null;

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
  const swing = raw.includes("Swing");
  const pct = raw.includes("Percent");
  document.querySelectorAll(".opt-exit-swing").forEach((el) => {
    el.hidden = !swing;
  });
  document.querySelectorAll(".opt-exit-percent").forEach((el) => {
    el.hidden = !pct;
  });
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

function renderOptResults(payload) {
  const body = document.querySelector("#optResultBody");
  const title = document.querySelector("#optResultTitle");
  const hint = document.querySelector("#optResultHint");
  if (!body) return;
  const rows = payload?.results || [];
  const passed = payload?.passed ?? 0;
  const tested = payload?.tested ?? 0;
  if (title) title.textContent = `${payload.symbol || ""} sonuçları`;
  if (hint) {
    hint.textContent = `${payload.bars || 0} bar · ${payload.from || ""} → ${payload.to || ""} · ${tested} kombinasyon · ${passed} eşik geçti`;
  }
  if (!rows.length) {
    body.innerHTML = `<tr class="empty"><td colspan="19">Eşikleri geçen (veya yakın) set yok.</td></tr>`;
    return;
  }
  body.innerHTML = rows
    .map((r) => {
      const p = r.params || {};
      const cls = r.passed ? "opt-row-pass" : "opt-row-fail";
      const json = optEsc(JSON.stringify(pineOverridesFromRow(p)));
      return `<tr class="${cls}">
        <td>${r.rank}</td>
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

function collectOptBody() {
  return {
    symbol: optCsv("#optSymbol"),
    timeframe: document.querySelector("#optTimeframe")?.value || "15m",
    period: document.querySelector("#optPeriod")?.value || "60d",
    mode: document.querySelector("#optMode")?.value || "quick",
    side: document.querySelector("#optSide")?.value || "both",
    max_combos: Math.round(optNum("#optMaxCombos", 180)),
    min_win_rate: optNum("#optMinWinRate", 45),
    max_drawdown: optNum("#optMaxDd", 18),
    min_profit_factor: optNum("#optMinPf", 1.3),
    min_profit: optNum("#optMinProfit", 8),
    min_trades: Math.round(optNum("#optMinTrades", 10)),
    ha_len: optCsv("#optHaLen"),
    ha_len2: optCsv("#optHaLen2"),
    osc_len: optCsv("#optOscLen"),
    ha_htf: optCsv("#optHaHtf"),
    exit_mode: document.querySelector("#optExitMode")?.value || "Swing RR",
    rr_mult: optCsv("#optRr"),
    swing_bars: optCsv("#optSwing"),
    tp_pct: optCsv("#optTpPct"),
    sl_pct: optCsv("#optSlPct"),
    max_same: optCsv("#optMaxSame"),
    reverse_exit: document.querySelector("#optReverse")?.value || "true",
    require_bar: document.querySelector("#optRequireBar")?.value || "false",
  };
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
  optStatus(
    passed
      ? `${passed} set eşikleri geçti.`
      : "Eşik geçen set yok; tabloda en yakın sonuçlar var.",
    passed ? "ok" : "error"
  );
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

function onOptTabShown() {
  loadOptContracts();
}

function initOptimize() {
  document.querySelector("#optForm")?.addEventListener("submit", startOptRun);
  document.querySelector("#optExitMode")?.addEventListener("change", syncOptExitFields);
  syncOptExitFields();
  document.querySelector("#optMode")?.addEventListener("change", (ev) => {
    const full = ev.target.value === "full";
    const maxEl = document.querySelector("#optMaxCombos");
    if (maxEl) maxEl.value = full ? "400" : "180";
    const set = (id, val) => {
      const el = document.querySelector(id);
      if (el) el.value = val;
    };
    if (full) {
      set("#optHaLen", "40, 52, 64, 76, 88");
      set("#optHaLen2", "60, 76, 92, 108");
      set("#optOscLen", "5, 7, 9, 11");
      set("#optHaHtf", "15, 30");
      set("#optRr", "1.0, 1.2, 1.6, 2.0");
      set("#optSwing", "6, 11, 13");
      set("#optMaxSame", "1, 2, 3");
      set("#optTpPct", "1.5, 2.5");
      set("#optSlPct", "1.0, 1.5");
      set("#optExitMode", "Swing RR, Percent");
      set("#optReverse", "true, false");
      set("#optRequireBar", "true, false");
    } else {
      set("#optHaLen", "48, 64, 80");
      set("#optHaLen2", "72, 96");
      set("#optOscLen", "7, 11");
      set("#optHaHtf", "30");
      set("#optRr", "1.2, 1.6, 2.0");
      set("#optSwing", "8, 11");
      set("#optTpPct", "1.5, 2.0, 2.5");
      set("#optSlPct", "0.8, 1.0, 1.5");
      set("#optMaxSame", "1, 2");
      set("#optExitMode", "Swing RR");
      set("#optReverse", "true");
      set("#optRequireBar", "false");
    }
    syncOptExitFields();
  });
}

initOptimize();
window.onOptTabShown = onOptTabShown;
