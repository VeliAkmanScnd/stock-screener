function dashEsc(s) {
  return String(s ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function dashFmt(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleString("tr-TR", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function dashStatus(status) {
  const s = String(status || "");
  if (s === "error") return '<span class="status-pill err">hata</span>';
  if (s === "success_no_email") return '<span class="status-pill warn">e-posta yok</span>';
  if (s === "success_no_telegram") return '<span class="status-pill warn">telegram yok</span>';
  if (s.startsWith("success")) return '<span class="status-pill ok">tamam</span>';
  if (s === "running") return '<span class="status-pill">çalışıyor</span>';
  return s ? dashEsc(s) : "—";
}

function kpiCard(label, value, hint) {
  return `<article class="dash-kpi">
    <span>${dashEsc(label)}</span>
    <strong>${dashEsc(value)}</strong>
    ${hint ? `<em>${dashEsc(hint)}</em>` : ""}
  </article>`;
}

function renderDashKpis(kpis) {
  const el = document.getElementById("dashKpis");
  if (!el) return;
  const peak =
    kpis.peak_hour == null || kpis.peak_hour === ""
      ? "—"
      : `${kpis.peak_hour}:00`;
  el.innerHTML = [
    kpiCard("Çalışma", kpis.runs_today ?? 0, `${kpis.enabled_scans ?? 0} açık tarama`),
    kpiCard("Eşleşme", kpis.hits ?? 0, `AL ${kpis.al ?? 0} · SAT ${kpis.sat ?? 0}`),
    kpiCard("Tekil hisse", kpis.unique_symbols ?? 0, `${kpis.repeat_symbols ?? 0} tekrarlayan`),
    kpiCard("Aynı fiyat gizlendi", kpis.skipped_repeat_price ?? 0, "önceki sinyal ile aynı"),
    kpiCard("Hata", kpis.error_runs ?? 0, `${kpis.success_runs ?? 0} başarılı`),
    kpiCard(
      "Bildirim",
      `${kpis.telegram_sent ?? 0} TG`,
      `e-posta ${kpis.email_sent ?? 0}`
    ),
    kpiCard("Yoğun saat", peak, `${kpis.peak_hour_hits ?? 0} eşleşme`),
    kpiCard(
      "En çok periyot",
      kpis.top_timeframe || "—",
      `${kpis.top_timeframe_hits ?? 0} eşleşme`
    ),
  ].join("");
}

function renderDashScans(rows) {
  const tbody = document.getElementById("dashScansBody");
  if (!tbody) return;
  if (!rows?.length) {
    tbody.innerHTML = '<tr class="empty"><td colspan="7">Kayıtlı zamanlanmış tarama yok.</td></tr>';
    return;
  }
  tbody.innerHTML = rows
    .map((r) => {
      const idle = r.enabled && !r.runs;
      return `<tr class="dash-row-link" data-goto="schedules">
        <td><strong>${dashEsc(r.name)}</strong>${r.enabled ? "" : ' <span class="status-pill">durdu</span>'}</td>
        <td>${dashEsc(r.timeframe_label)}</td>
        <td>${dashEsc(r.universe_label)}</td>
        <td>${r.runs || 0}${idle ? ' <span class="dash-muted">bugün yok</span>' : ""}</td>
        <td>${r.hits || 0}</td>
        <td>${r.unique_symbols || 0}</td>
        <td>${dashStatus(r.last_status)} ${dashFmt(r.last_run_at)}</td>
      </tr>`;
    })
    .join("");
}

function renderDashRepeats(rows) {
  const tbody = document.getElementById("dashRepeatsBody");
  if (!tbody) return;
  const repeats = (rows || []).filter((r) => r.count >= 2);
  if (!repeats.length) {
    tbody.innerHTML =
      '<tr class="empty"><td colspan="5">Bugün aynı hisse birden fazla gelmedi.</td></tr>';
    return;
  }
  tbody.innerHTML = repeats
    .map(
      (r) => `<tr>
        <td><strong>${dashEsc(r.symbol)}</strong></td>
        <td>${r.count}</td>
        <td>${dashEsc(r.direction)}</td>
        <td>${dashEsc((r.timeframes || []).join(", "))}</td>
        <td>${dashEsc((r.scans || []).join(" · "))}</td>
      </tr>`
    )
    .join("");
}

function renderDashHours(hours) {
  const el = document.getElementById("dashHours");
  if (!el) return;
  const max = Math.max(0, ...((hours || []).map((h) => h.hits || 0)));
  el.innerHTML = (hours || [])
    .map((h) => {
      const height = h.hits ? Math.max(6, Math.round((h.hits / max) * 72)) : 3;
      return `<div class="dash-hour" title="${h.hour}:00 — ${h.hits} eşleşme">
        <i style="block-size:${height}px"></i>
        <span>${h.hour}</span>
      </div>`;
    })
    .join("");
}

function renderDashUpcoming(rows) {
  const el = document.getElementById("dashUpcoming");
  if (!el) return;
  if (!rows?.length) {
    el.innerHTML = "<li>Sırada açık tarama yok.</li>";
    return;
  }
  el.innerHTML = rows
    .map(
      (r) => `<li>
        <strong>${dashEsc(r.name)}</strong>
        <span>${dashEsc(r.universe_label)} · ${dashEsc(r.timeframe_label)}</span>
        <em>${dashFmt(r.next_run_at)}</em>
      </li>`
    )
    .join("");
}

async function loadDashboard() {
  const hint = document.getElementById("dashDateHint");
  try {
    const res = await apiFetch("/api/dashboard/today");
    const data = await res.json();
    if (!res.ok) {
      if (hint) hint.textContent = data.detail || "Özet yüklenemedi.";
      return;
    }
    if (hint) {
      hint.textContent = `${data.date} · ${data.timezone} (bugünün zamanlanmış taramaları)`;
    }
    renderDashKpis(data.kpis || {});
    renderDashScans(data.scans || []);
    renderDashRepeats(data.repeats || []);
    renderDashHours(data.hours || []);
    renderDashUpcoming(data.upcoming || []);
  } catch (err) {
    if (hint) hint.textContent = err.message || "Özet yüklenemedi.";
  }
}

function onDashTabShown() {
  loadDashboard();
}

function goToScanTab(scrollToSchedules) {
  if (typeof switchAppTab === "function") switchAppTab("scan");
  if (scrollToSchedules) {
    requestAnimationFrame(() => {
      document.getElementById("scheduledScansSection")?.scrollIntoView({
        behavior: "smooth",
        block: "start",
      });
    });
  }
}

document.addEventListener("DOMContentLoaded", () => {
  document.getElementById("btnDashRefresh")?.addEventListener("click", loadDashboard);
  document.getElementById("btnDashToScan")?.addEventListener("click", () => goToScanTab(false));
  document.getElementById("btnDashToSchedules")?.addEventListener("click", () => goToScanTab(true));
  document.getElementById("dashScansBody")?.addEventListener("click", (ev) => {
    const row = ev.target.closest("tr[data-goto='schedules']");
    if (row) goToScanTab(true);
  });
  const panel = document.getElementById("dashPanel");
  if (panel && !panel.classList.contains("hidden")) {
    loadDashboard();
  }
});

window.onDashTabShown = onDashTabShown;
window.loadDashboard = loadDashboard;
