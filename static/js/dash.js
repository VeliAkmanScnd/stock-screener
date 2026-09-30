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

function dashUptime(sec) {
  const n = Number(sec) || 0;
  if (n < 60) return `${n} sn`;
  if (n < 3600) return `${Math.floor(n / 60)} dk`;
  const h = Math.floor(n / 3600);
  const m = Math.floor((n % 3600) / 60);
  return m ? `${h} sa ${m} dk` : `${h} sa`;
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

let _dashPeriod = "day";

function setDashPeriodUI(period) {
  document.querySelectorAll("#dashPeriod .dash-period-btn").forEach((btn) => {
    const on = btn.dataset.period === period;
    btn.classList.toggle("is-active", on);
    btn.setAttribute("aria-selected", on ? "true" : "false");
  });
}

function setDashServiceUI(state, pillText, detail) {
  const box = document.getElementById("dashService");
  const pill = document.getElementById("dashServicePill");
  const det = document.getElementById("dashServiceDetail");
  if (!box || !pill || !det) return;
  box.classList.remove("is-ok", "is-warn", "is-down");
  if (state) box.classList.add(state);
  pill.textContent = pillText;
  det.textContent = detail;
}

function renderDashService(svc) {
  if (!svc || svc.server !== "up") {
    setDashServiceUI(
      "is-down",
      "Sunucu kapalı",
      "ERR_CONNECTION_REFUSED = süreç yok. VPS: git pull → .\\install-windows-task.ps1 veya start-tradelab.bat"
    );
    return;
  }
  const schedOk = !!svc.scheduler_running;
  const jobs = svc.scheduler_jobs ?? 0;
  const parts = [
    `çalışma süresi ${dashUptime(svc.uptime_seconds)}`,
    schedOk ? `zamanlayıcı açık (${jobs} iş)` : "zamanlayıcı kapalı",
    svc.next_job_at ? `sonraki iş ${dashFmt(svc.next_job_at)}` : "planlı iş yok",
  ];
  if (svc.watchdog_last) {
    parts.push(`watchdog: ${String(svc.watchdog_last).slice(0, 80)}`);
  }
  setDashServiceUI(
    schedOk ? "is-ok" : "is-warn",
    schedOk ? "Servis ayakta" : "Servis kısmi",
    parts.join(" · ")
  );
}

function kpiCard(label, value, hint) {
  return `<article class="dash-kpi">
    <span>${dashEsc(label)}</span>
    <strong>${dashEsc(value)}</strong>
    ${hint ? `<em>${dashEsc(hint)}</em>` : ""}
  </article>`;
}

function renderDashKpis(kpis, period) {
  const el = document.getElementById("dashKpis");
  if (!el) return;
  const peak =
    kpis.peak_hour == null || kpis.peak_hour === ""
      ? "—"
      : String(kpis.peak_hour);
  const peakLabel = period === "week" ? "Yoğun gün" : "Yoğun saat";
  const runs = kpis.runs ?? kpis.runs_today ?? 0;
  el.innerHTML = [
    kpiCard("Çalışma", runs, `${kpis.enabled_scans ?? 0} açık tarama`),
    kpiCard("Eşleşme", kpis.hits ?? 0, `AL ${kpis.al ?? 0} · SAT ${kpis.sat ?? 0}`),
    kpiCard("Tekil hisse", kpis.unique_symbols ?? 0, `${kpis.repeat_symbols ?? 0} tekrarlayan`),
    kpiCard("Aynı fiyat gizlendi", kpis.skipped_repeat_price ?? 0, "önceki sinyal ile aynı"),
    kpiCard("Hata", kpis.error_runs ?? 0, `${kpis.success_runs ?? 0} başarılı`),
    kpiCard(
      "Bildirim",
      `${kpis.telegram_sent ?? 0} TG`,
      `gönderilen mesaj · e-posta ${kpis.email_sent ?? 0}`
    ),
    kpiCard(peakLabel, peak, `${kpis.peak_hour_hits ?? 0} eşleşme`),
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
        <td>${r.runs || 0}${idle ? ' <span class="dash-muted">dönemde yok</span>' : ""}</td>
        <td>${r.hits || 0}</td>
        <td>${r.unique_symbols || 0}</td>
        <td>${dashStatus(r.last_status)} ${dashFmt(r.last_run_at)}</td>
      </tr>`;
    })
    .join("");
}

function renderDashRepeats(rows, period) {
  const tbody = document.getElementById("dashRepeatsBody");
  if (!tbody) return;
  const repeats = (rows || []).filter((r) => r.count >= 2);
  if (!repeats.length) {
    const empty =
      period === "all"
        ? "Seçili dönemde tekrarlayan hisse yok."
        : period === "week"
          ? "Bu hafta aynı hisse birden fazla gelmedi."
          : "Bugün aynı hisse birden fazla gelmedi.";
    tbody.innerHTML = `<tr class="empty"><td colspan="5">${empty}</td></tr>`;
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

function renderDashHours(hours, chartMode) {
  const el = document.getElementById("dashHours");
  if (!el) return;
  const max = Math.max(0, ...((hours || []).map((h) => h.hits || 0)));
  el.innerHTML = (hours || [])
    .map((h) => {
      const height = h.hits ? Math.max(6, Math.round((h.hits / max) * 72)) : 3;
      const label = h.label != null ? h.label : h.hour;
      const tip =
        chartMode === "weekday"
          ? `${label} — ${h.hits} eşleşme`
          : `${h.hour}:00 — ${h.hits} eşleşme`;
      return `<div class="dash-hour" title="${dashEsc(tip)}">
        <i style="block-size:${height}px"></i>
        <span>${dashEsc(label)}</span>
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

function applyDashPeriodCopy(data) {
  const period = data.period || "day";
  const title = document.getElementById("dashTitle");
  const hint = document.getElementById("dashDateHint");
  const scansHint = document.getElementById("dashScansHint");
  const repeatsHint = document.getElementById("dashRepeatsHint");
  const chartTitle = document.getElementById("dashChartTitle");
  const chartHint = document.getElementById("dashChartHint");
  if (title) title.textContent = data.period_label || "Özet";
  const tz = data.timezone || "Europe/Istanbul";
  if (hint) {
    if (period === "week") {
      hint.textContent = `${data.date} · ${tz} (Pazartesi → bugün)`;
    } else if (period === "all") {
      hint.textContent = `${tz} · tüm kayıtlı zamanlanmış taramalar`;
    } else {
      hint.textContent = `${data.date} · ${tz} (bugünün zamanlanmış taramaları)`;
    }
  }
  if (scansHint) {
    scansHint.textContent =
      period === "all"
        ? "Tüm dönemde kaç kez çalıştı, kaç eşleşme bulundu."
        : period === "week"
          ? "Bu hafta kaç kez çalıştı, kaç eşleşme bulundu."
          : "Bugün kaç kez çalıştı, kaç eşleşme bulundu.";
  }
  if (repeatsHint) {
    repeatsHint.textContent =
      period === "all"
        ? "Aynı hisse tüm dönemde kaç kez geldi."
        : period === "week"
          ? "Aynı hisse bu hafta kaç kez geldi."
          : "Aynı hisse bugün kaç kez geldi.";
  }
  if (chartTitle) {
    chartTitle.textContent =
      period === "week" ? "Haftalık eşleşmeler" : "Saatlik eşleşmeler";
  }
  if (chartHint) {
    chartHint.textContent =
      period === "week"
        ? "İstanbul takvimine göre haftanın günleri."
        : "İstanbul saatiyle bulunan hisse adedi.";
  }
}

let _dashPollTimer = null;

async function pingHealthz() {
  try {
    const res = await fetch("/healthz", { credentials: "omit", cache: "no-store" });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error("healthz hata");
    renderDashService(data);
    return data;
  } catch {
    renderDashService(null);
    return null;
  }
}

async function loadDashboard() {
  const hint = document.getElementById("dashDateHint");
  setDashPeriodUI(_dashPeriod);
  const health = await pingHealthz();
  if (!health) {
    if (hint) {
      hint.textContent =
        "Sunucu yanıt vermiyor (CONNECTION_REFUSED). VPS'te start-tradelab.bat veya install-windows-task.ps1 çalıştırın.";
    }
    return;
  }
  try {
    const res = await apiFetch(`/api/dashboard/today?period=${encodeURIComponent(_dashPeriod)}`);
    const data = await res.json();
    if (!res.ok) {
      if (hint) hint.textContent = data.detail || "Özet yüklenemedi.";
      return;
    }
    applyDashPeriodCopy(data);
    if (data.service) renderDashService(data.service);
    renderDashKpis(data.kpis || {}, data.period || _dashPeriod);
    renderDashScans(data.scans || []);
    renderDashRepeats(data.repeats || [], data.period || _dashPeriod);
    renderDashHours(data.hours || [], data.chart_mode || "hour");
    renderDashUpcoming(data.upcoming || []);
  } catch (err) {
    if (hint) hint.textContent = err.message || "Özet yüklenemedi.";
    await pingHealthz();
  }
}

function onDashTabShown() {
  loadDashboard();
  if (_dashPollTimer) clearInterval(_dashPollTimer);
  _dashPollTimer = setInterval(() => {
    const panel = document.getElementById("dashPanel");
    if (panel && !panel.classList.contains("hidden")) pingHealthz();
  }, 30000);
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
  document.getElementById("dashPeriod")?.addEventListener("click", (ev) => {
    const btn = ev.target.closest(".dash-period-btn");
    if (!btn || !btn.dataset.period) return;
    if (btn.dataset.period === _dashPeriod) return;
    _dashPeriod = btn.dataset.period;
    setDashPeriodUI(_dashPeriod);
    loadDashboard();
  });
  document.getElementById("dashScansBody")?.addEventListener("click", (ev) => {
    const row = ev.target.closest("tr[data-goto='schedules']");
    if (row) goToScanTab(true);
  });
  const panel = document.getElementById("dashPanel");
  if (panel && !panel.classList.contains("hidden")) {
    onDashTabShown();
  }
});

window.onDashTabShown = onDashTabShown;
window.loadDashboard = loadDashboard;
