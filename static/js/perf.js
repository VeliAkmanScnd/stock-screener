const PERF_STATUS_LABELS = {
  active: "Aktif",
  after_tp: "TP sonrası",
  hit_target: "Hedef",
  hit_stop: "Stop",
  expired: "Süre doldu",
  manual_close: "Manuel",
  opposite_signal: "Ters sinyal",
  archived: "Arşiv",
};

let perfGroups = [];
let perfPositions = [];
let perfMinSample = 20;
let perfSelectedGroupKeys = new Set();
let perfSelectedIds = new Set();

function fmtHours(v) {
  if (v == null || Number.isNaN(Number(v))) return "—";
  const n = Number(v);
  if (n < 24) return `${n.toFixed(1)} sa`;
  return `${(n / 24).toFixed(1)} gün`;
}

function fmtPerfPct(v) {
  if (v == null || Number.isNaN(Number(v))) return "—";
  return `${Number(v).toFixed(2)}%`;
}

function fmtR(v) {
  if (v == null || Number.isNaN(Number(v))) return "—";
  const n = Number(v);
  const sign = n > 0 ? "+" : "";
  return `${sign}${n.toFixed(2)}R`;
}

function fmtMaxMove(pct, r) {
  const pctText = fmtPerfPct(pct);
  if (r == null || Number.isNaN(Number(r))) return pctText;
  return `${pctText} · ${fmtR(r)}`;
}

function perfEsc(s) {
  return String(s ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/"/g, "&quot;");
}

function perfTitleQuery() {
  return (document.querySelector("#perfTitleFilter")?.value || "").trim().toLocaleLowerCase("tr");
}

function perfTitleMatches(...parts) {
  const q = perfTitleQuery();
  if (!q) return true;
  return parts.some((part) => String(part || "").toLocaleLowerCase("tr").includes(q));
}

function visiblePerfGroups() {
  return perfGroups.filter((g) => perfTitleMatches(g.label, g.key));
}

function visiblePerfHistory() {
  return perfPositions.filter((r) =>
    perfTitleMatches(r.group_label, r.source_label, r.indicator_label, r.timeframe, r.symbol)
  );
}

function renderPerfBenchmarks(rows) {
  const host = document.querySelector("#perfLevelBenchmarks");
  if (!host) return;
  if (typeof renderLevelBenchmarks === "function") {
    renderLevelBenchmarks("#perfLevelBenchmarks", rows || []);
    return;
  }
  host.innerHTML = (rows || [])
    .map((b) => {
      const feat = b.featured ? " featured" : "";
      const target = typeof benchTargetPct === "function" ? benchTargetPct(b.stop_pct) : b.target_pct;
      return `<div class="tf-bench-chip${feat}">
        <strong>${perfEsc(b.label)}</strong>
        <span>+${target}% / −${b.stop_pct}%</span>
        <span>1.7R</span>
      </div>`;
    })
    .join("");
}

async function loadPerfReport() {
  const status = document.querySelector("#perfReportStatus");
  const groupBy = document.querySelector("#perfGroupBy")?.value || "timeframe";
  const dateFrom = document.querySelector("#perfDateFrom")?.value || "";
  const dateTo = document.querySelector("#perfDateTo")?.value || "";
  const dedupe = document.querySelector("#perfDedupeSymbol")?.checked ? "symbol" : "";
  const params = new URLSearchParams({ group_by: groupBy, include_positions: "true" });
  if (dateFrom) params.set("date_from", dateFrom);
  if (dateTo) params.set("date_to", dateTo);
  if (dedupe) params.set("dedupe", dedupe);
  if (status) status.textContent = "Yükleniyor…";
  try {
    const res = await apiFetch(`/api/track/report?${params.toString()}`);
    const data = await res.json();
    if (!res.ok) {
      if (status) status.textContent = data.detail || "Rapor alınamadı";
      return;
    }
    perfGroups = data.groups || [];
    perfPositions = data.positions || [];
    perfMinSample = data.min_sample || 20;
    perfSelectedGroupKeys.clear();
    perfSelectedIds.clear();
    renderPerfBenchmarks(data.level_benchmarks || []);
    renderPerfTables();
    updatePerfReportStatus(status, data.total || 0);
  } catch (err) {
    if (status) status.textContent = err.message;
  }
}

function updatePerfReportStatus(status, total) {
  if (!status) status = document.querySelector("#perfReportStatus");
  if (!status) return;
  const groups = visiblePerfGroups();
  const rows = visiblePerfHistory();
  const ready = groups.filter((g) => g.rank_ready).length;
  const q = perfTitleQuery();
  const titleNote = q ? ` · başlık «${q}»` : "";
  status.textContent = `${total} kayıt · ${rows.length} satır · ${ready} sıralanan grup · min ${perfMinSample} kapanmış${titleNote}`;
}

function renderPerfTables() {
  renderPerfGroups(visiblePerfGroups(), perfMinSample);
  renderPerfHistory(visiblePerfHistory());
  syncPerfSelectAll();
}

function syncPerfSelectAll() {
  const groupAll = document.querySelector("#perfGroupSelectAll");
  const histAll = document.querySelector("#perfHistorySelectAll");
  const groups = visiblePerfGroups();
  const rows = visiblePerfHistory();
  if (groupAll) {
    const n = groups.filter((g) => perfSelectedGroupKeys.has(g.key)).length;
    groupAll.checked = groups.length > 0 && n === groups.length;
    groupAll.indeterminate = n > 0 && n < groups.length;
  }
  if (histAll) {
    const n = rows.filter((r) => perfSelectedIds.has(r.id)).length;
    histAll.checked = rows.length > 0 && n === rows.length;
    histAll.indeterminate = n > 0 && n < rows.length;
  }
}

function renderPerfGroups(groups, minSample) {
  const body = document.querySelector("#perfReportBody");
  if (!body) return;
  if (!groups.length) {
    const empty = perfTitleQuery()
      ? "Bu başlığa uyan grup yok."
      : "Bu aralıkta kayıt yok.";
    body.innerHTML = `<tr class="empty"><td colspan="15">${empty}</td></tr>`;
    return;
  }
  body.innerHTML = groups
    .map((g) => {
      const badge = g.insufficient
        ? `<span class="perf-badge">yetersiz (&lt;${minSample})</span>`
        : "";
      const rCls =
        g.expected_r == null ? "" : Number(g.expected_r) >= 0 ? "track-pct-up" : "track-pct-down";
      const checked = perfSelectedGroupKeys.has(g.key) ? "checked" : "";
      return `<tr>
        <td class="track-check-cell"><input type="checkbox" class="perf-group-select" data-perf-group="${perfEsc(g.key)}" ${checked} /></td>
        <td>${g.rank ?? "—"}</td>
        <td><strong>${perfEsc(g.label)}</strong>${badge}</td>
        <td>${g.settled_count}</td>
        <td>${g.open_count}</td>
        <td class="${rCls}">${fmtR(g.expected_r)}</td>
        <td>${fmtR(g.avg_win_r)}</td>
        <td>${fmtR(g.avg_loss_r)}</td>
        <td>${g.tp_count}</td>
        <td>${g.sl_count}</td>
        <td>${g.opposite_count}</td>
        <td class="${Number(g.win_rate) >= 50 ? "track-pct-up" : ""}">${fmtPerfPct(g.win_rate)}</td>
        <td class="${Number(g.avg_mfe_pct) >= 0 ? "track-pct-up" : "track-pct-down"}">${fmtMaxMove(g.avg_mfe_pct, g.avg_mfe_r)}</td>
        <td>${fmtHours(g.avg_hours_to_tp)}</td>
        <td>${fmtHours(g.avg_hours_to_sl)}</td>
      </tr>`;
    })
    .join("");

  body.querySelectorAll("[data-perf-group]").forEach((cb) => {
    cb.addEventListener("change", () => {
      const key = cb.dataset.perfGroup;
      if (cb.checked) perfSelectedGroupKeys.add(key);
      else perfSelectedGroupKeys.delete(key);
      syncPerfSelectAll();
    });
  });
}

function renderPerfHistory(rows) {
  const body = document.querySelector("#perfHistoryBody");
  if (!body) return;
  if (!rows.length) {
    const empty = perfTitleQuery() ? "Bu başlığa uyan kayıt yok." : "Kayıt yok.";
    body.innerHTML = `<tr class="empty"><td colspan="12">${empty}</td></tr>`;
    return;
  }
  body.innerHTML = rows
    .map((r) => {
      const rCls = r.realized_r == null ? "" : Number(r.realized_r) >= 0 ? "track-pct-up" : "track-pct-down";
      const checked = perfSelectedIds.has(r.id) ? "checked" : "";
      return `<tr>
        <td class="track-check-cell"><input type="checkbox" class="perf-row-select" data-perf-select="${r.id}" ${checked} /></td>
        <td><strong>${perfEsc(r.symbol)}</strong><br><span class="hint">${perfEsc(r.universe)}</span></td>
        <td>${perfEsc(r.direction || "AL")}</td>
        <td>${perfEsc(r.timeframe || "—")}</td>
        <td>${perfEsc(r.source_label || "—")}</td>
        <td>${perfEsc(r.indicator_label || "—")}</td>
        <td>${r.entry_at ? String(r.entry_at).slice(0, 16).replace("T", " ") : "—"}</td>
        <td class="${Number(r.mfe_pct) >= 0 ? "track-pct-up" : "track-pct-down"}">${fmtMaxMove(r.mfe_pct, r.mfe_r)}</td>
        <td class="${rCls}">${fmtR(r.realized_r)}</td>
        <td>${fmtHours(r.hours_to_tp)}</td>
        <td>${fmtHours(r.hours_to_sl)}</td>
        <td>${PERF_STATUS_LABELS[r.status] || r.status}</td>
      </tr>`;
    })
    .join("");

  body.querySelectorAll("[data-perf-select]").forEach((cb) => {
    cb.addEventListener("change", () => {
      const id = parseInt(cb.dataset.perfSelect, 10);
      if (Number.isNaN(id)) return;
      if (cb.checked) perfSelectedIds.add(id);
      else perfSelectedIds.delete(id);
      syncPerfSelectAll();
    });
  });
}

function selectedPerfPositionIds() {
  const ids = new Set();
  visiblePerfHistory().forEach((r) => {
    if (perfSelectedIds.has(r.id)) ids.add(r.id);
  });
  visiblePerfGroups().forEach((g) => {
    if (!perfSelectedGroupKeys.has(g.key)) return;
    (g.position_ids || []).forEach((id) => ids.add(id));
  });
  return [...ids];
}

function onPerfTabShown() {
  loadPerfReport();
}

async function resetPerfHistory() {
  if (
    !confirm(
      "Rapor satırları sıfırlansın mı? Aktif ve geçmiş tüm pozisyon kayıtları silinir; R raporu da boşalır."
    )
  ) {
    return;
  }
  const status = document.querySelector("#perfReportStatus");
  if (status) status.textContent = "Rapor satırları siliniyor…";
  try {
    const res = await apiFetch("/api/track/positions/reset", { method: "POST" });
    const data = await res.json();
    if (!res.ok) {
      if (status) status.textContent = data.detail || "Sıfırlanamadı";
      return;
    }
    if (typeof window.reloadTrackPositions === "function") {
      window.reloadTrackPositions();
    }
    await loadPerfReport();
    if (status) {
      status.textContent = `Rapor satırları sıfırlandı (${data.deleted ?? 0} kayıt silindi).`;
    }
  } catch (err) {
    if (status) status.textContent = err.message;
  }
}

async function deleteSelectedPerfRows() {
  const ids = selectedPerfPositionIds();
  if (!ids.length) {
    const status = document.querySelector("#perfReportStatus");
    if (status) status.textContent = "Silmek için grup veya satır seçin.";
    return;
  }
  if (!confirm(`${ids.length} seçili kayıt silinsin mi? R raporu da güncellenir.`)) {
    return;
  }
  const status = document.querySelector("#perfReportStatus");
  if (status) status.textContent = "Seçilenler siliniyor…";
  try {
    const res = await apiFetch("/api/track/positions/bulk-delete", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ position_ids: ids, include_active: true }),
    });
    const data = await res.json();
    if (!res.ok) {
      if (status) status.textContent = data.detail || "Silinemedi";
      return;
    }
    if (typeof window.reloadTrackPositions === "function") {
      window.reloadTrackPositions();
    }
    await loadPerfReport();
    if (status) {
      status.textContent = `${data.deleted ?? 0} kayıt silindi.`;
    }
  } catch (err) {
    if (status) status.textContent = err.message;
  }
}

function initPerfPanel() {
  document.querySelector("#perfReportForm")?.addEventListener("submit", (e) => {
    e.preventDefault();
    loadPerfReport();
  });
  document.querySelector("#perfTitleFilter")?.addEventListener("input", () => {
    renderPerfTables();
    updatePerfReportStatus();
  });
  document.querySelector("#perfGroupSelectAll")?.addEventListener("change", (e) => {
    const groups = visiblePerfGroups();
    if (e.target.checked) groups.forEach((g) => perfSelectedGroupKeys.add(g.key));
    else groups.forEach((g) => perfSelectedGroupKeys.delete(g.key));
    renderPerfTables();
  });
  document.querySelector("#perfHistorySelectAll")?.addEventListener("change", (e) => {
    const rows = visiblePerfHistory();
    if (e.target.checked) rows.forEach((r) => perfSelectedIds.add(r.id));
    else rows.forEach((r) => perfSelectedIds.delete(r.id));
    renderPerfTables();
  });
  document.querySelector("#btnPerfDeleteSelected")?.addEventListener("click", deleteSelectedPerfRows);
  document.querySelector("#btnPerfDeleteSelectedReport")?.addEventListener("click", deleteSelectedPerfRows);
  document.querySelector("#btnPerfHistoryReset")?.addEventListener("click", resetPerfHistory);
}

document.addEventListener("DOMContentLoaded", initPerfPanel);
