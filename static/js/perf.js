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

function perfEsc(s) {
  return String(s ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/"/g, "&quot;");
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
      return `<div class="tf-bench-chip${feat}">
        <strong>${perfEsc(b.label)}</strong>
        <span>+${b.target_pct}% / −${b.stop_pct}%</span>
        <span>${b.r_multiple != null ? `${b.r_multiple}R` : ""}</span>
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
    renderPerfBenchmarks(data.level_benchmarks || []);
    renderPerfGroups(data.groups || [], data.min_sample || 20);
    renderPerfHistory(data.positions || []);
    if (status) {
      const ready = (data.groups || []).filter((g) => g.rank_ready).length;
      status.textContent = `${data.total || 0} kayıt · ${ready} sıralanan grup · min ${data.min_sample || 20} kapanmış`;
    }
  } catch (err) {
    if (status) status.textContent = err.message;
  }
}

function renderPerfGroups(groups, minSample) {
  const body = document.querySelector("#perfReportBody");
  if (!body) return;
  if (!groups.length) {
    body.innerHTML = '<tr class="empty"><td colspan="14">Bu aralıkta kayıt yok.</td></tr>';
    return;
  }
  body.innerHTML = groups
    .map((g) => {
      const badge = g.insufficient
        ? `<span class="perf-badge">yetersiz (&lt;${minSample})</span>`
        : "";
      const rCls =
        g.expected_r == null ? "" : Number(g.expected_r) >= 0 ? "track-pct-up" : "track-pct-down";
      return `<tr>
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
        <td class="${Number(g.avg_mfe_pct) >= 0 ? "track-pct-up" : "track-pct-down"}">${fmtPerfPct(g.avg_mfe_pct)}</td>
        <td>${fmtHours(g.avg_hours_to_tp)}</td>
        <td>${fmtHours(g.avg_hours_to_sl)}</td>
      </tr>`;
    })
    .join("");
}

function renderPerfHistory(rows) {
  const body = document.querySelector("#perfHistoryBody");
  if (!body) return;
  if (!rows.length) {
    body.innerHTML = '<tr class="empty"><td colspan="11">Kayıt yok.</td></tr>';
    return;
  }
  body.innerHTML = rows
    .map((r) => {
      const rCls = r.realized_r == null ? "" : Number(r.realized_r) >= 0 ? "track-pct-up" : "track-pct-down";
      return `<tr>
        <td><strong>${perfEsc(r.symbol)}</strong><br><span class="hint">${perfEsc(r.universe)}</span></td>
        <td>${perfEsc(r.direction || "AL")}</td>
        <td>${perfEsc(r.timeframe || "—")}</td>
        <td>${perfEsc(r.source_label || "—")}</td>
        <td>${perfEsc(r.indicator_label || "—")}</td>
        <td>${r.entry_at ? String(r.entry_at).slice(0, 16).replace("T", " ") : "—"}</td>
        <td class="${Number(r.mfe_pct) >= 0 ? "track-pct-up" : "track-pct-down"}">${fmtPerfPct(r.mfe_pct)}</td>
        <td class="${rCls}">${fmtR(r.realized_r)}</td>
        <td>${fmtHours(r.hours_to_tp)}</td>
        <td>${fmtHours(r.hours_to_sl)}</td>
        <td>${PERF_STATUS_LABELS[r.status] || r.status}</td>
      </tr>`;
    })
    .join("");
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

function initPerfPanel() {
  document.querySelector("#perfReportForm")?.addEventListener("submit", (e) => {
    e.preventDefault();
    loadPerfReport();
  });
  document.querySelector("#btnPerfHistoryReset")?.addEventListener("click", resetPerfHistory);
}

document.addEventListener("DOMContentLoaded", initPerfPanel);
