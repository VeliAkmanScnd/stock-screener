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

function perfEsc(s) {
  return String(s ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/"/g, "&quot;");
}

async function loadPerfReport() {
  const status = document.querySelector("#perfReportStatus");
  const groupBy = document.querySelector("#perfGroupBy")?.value || "timeframe";
  const dateFrom = document.querySelector("#perfDateFrom")?.value || "";
  const dateTo = document.querySelector("#perfDateTo")?.value || "";
  const params = new URLSearchParams({ group_by: groupBy, include_positions: "true" });
  if (dateFrom) params.set("date_from", dateFrom);
  if (dateTo) params.set("date_to", dateTo);
  if (status) status.textContent = "Yükleniyor…";
  try {
    const res = await apiFetch(`/api/track/report?${params.toString()}`);
    const data = await res.json();
    if (!res.ok) {
      if (status) status.textContent = data.detail || "Rapor alınamadı";
      return;
    }
    renderPerfGroups(data.groups || []);
    renderPerfHistory(data.positions || []);
    if (status) {
      status.textContent = `${data.total || 0} kayıt · ${data.groups?.length || 0} grup`;
    }
  } catch (err) {
    if (status) status.textContent = err.message;
  }
}

function renderPerfGroups(groups) {
  const body = document.querySelector("#perfReportBody");
  if (!body) return;
  if (!groups.length) {
    body.innerHTML = '<tr class="empty"><td colspan="12">Bu aralıkta kayıt yok.</td></tr>';
    return;
  }
  body.innerHTML = groups
    .map(
      (g) => `<tr>
        <td>${g.rank}</td>
        <td><strong>${perfEsc(g.label)}</strong></td>
        <td>${g.count}</td>
        <td>${g.open_count}</td>
        <td>${g.tp_count}</td>
        <td>${g.sl_count}</td>
        <td>${g.opposite_count}</td>
        <td class="${Number(g.win_rate) >= 50 ? "track-pct-up" : ""}">${fmtPerfPct(g.win_rate)}</td>
        <td class="${Number(g.avg_mfe_pct) >= 0 ? "track-pct-up" : "track-pct-down"}">${fmtPerfPct(g.avg_mfe_pct)}</td>
        <td>${fmtHours(g.avg_hours_to_tp)}</td>
        <td>${fmtHours(g.avg_hours_to_sl)}</td>
        <td>${fmtHours(g.avg_hold_hours)}</td>
      </tr>`,
    )
    .join("");
}

function renderPerfHistory(rows) {
  const body = document.querySelector("#perfHistoryBody");
  if (!body) return;
  if (!rows.length) {
    body.innerHTML = '<tr class="empty"><td colspan="10">Kayıt yok.</td></tr>';
    return;
  }
  body.innerHTML = rows
    .map(
      (r) => `<tr>
        <td><strong>${perfEsc(r.symbol)}</strong><br><span class="hint">${perfEsc(r.universe)}</span></td>
        <td>${perfEsc(r.direction || "AL")}</td>
        <td>${perfEsc(r.timeframe || "—")}</td>
        <td>${perfEsc(r.source_label || "—")}</td>
        <td>${perfEsc(r.indicator_label || "—")}</td>
        <td>${r.entry_at ? String(r.entry_at).slice(0, 16).replace("T", " ") : "—"}</td>
        <td class="${Number(r.mfe_pct) >= 0 ? "track-pct-up" : "track-pct-down"}">${fmtPerfPct(r.mfe_pct)}</td>
        <td>${fmtHours(r.hours_to_tp)}</td>
        <td>${fmtHours(r.hours_to_sl)}</td>
        <td>${PERF_STATUS_LABELS[r.status] || r.status}</td>
      </tr>`,
    )
    .join("");
}

function onPerfTabShown() {
  loadPerfReport();
}

function initPerfPanel() {
  document.querySelector("#perfReportForm")?.addEventListener("submit", (e) => {
    e.preventDefault();
    loadPerfReport();
  });
}

document.addEventListener("DOMContentLoaded", initPerfPanel);
