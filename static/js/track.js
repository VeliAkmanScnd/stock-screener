/** Performance tracking UI */

const track$ = (sel) => document.querySelector(sel);

let trackView = "active";
let trackUniverse = "all";
let trackBenchmarks = {};
let trackAllRows = [];
let trackOpenFilterCol = null;
const trackSelectedIds = new Set();

const trackTableState = {
  sort: { key: null, dir: "asc" },
  filters: {},
};

function getTrackSourceText(r) {
  return `${r.source_label || "—"} · ${r.timeframe || ""}${r.schedule_type ? ` (${r.schedule_type})` : ""}`;
}

function formatTrackEntryPlain(iso) {
  const d = parseUtcIso(iso);
  if (!d || Number.isNaN(d.getTime())) return "—";
  const datePart = d.toLocaleDateString("tr-TR", {
    timeZone: TRACK_TZ,
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  });
  const weekday = d.toLocaleDateString("tr-TR", { timeZone: TRACK_TZ, weekday: "long" });
  const timePart = d.toLocaleTimeString("tr-TR", {
    timeZone: TRACK_TZ,
    hour: "2-digit",
    minute: "2-digit",
  });
  return `${datePart} ${weekday} ${timePart}`;
}

const TRACK_COLUMNS = [
  { key: "symbol", label: "Sembol", type: "text", getValue: (r) => r.symbol || "", getDisplay: (r) => `${r.symbol} (${r.universe})` },
  { key: "source", label: "Kaynak", type: "text", getValue: (r) => getTrackSourceText(r) },
  { key: "entry_at", label: "Eklenme", type: "text", getValue: (r) => formatTrackEntryPlain(r.entry_at) },
  { key: "entry_price", label: "Giriş", type: "number", getValue: (r) => r.entry_price },
  { key: "current_price", label: "Güncel", type: "number", getValue: (r) => r.current_price },
  { key: "change_pct", label: "%", type: "number", getValue: (r) => r.change_pct },
  {
    key: "benchmark",
    label: "Endeks",
    type: "number",
    getValue: (r) => r.benchmark_current_price,
    getDisplay: (r) => `${fmtBenchmarkPrice(r.benchmark_current_price)} (${r.benchmark_symbol || "—"})`,
  },
  { key: "benchmark_pct", label: "Endeks %", type: "number", getValue: (r) => r.benchmark_change_pct },
  { key: "target_price", label: "Hedef", type: "number", getValue: (r) => r.target_price },
  { key: "stop_price", label: "Stop", type: "number", getValue: (r) => r.stop_price },
];

const TRACK_STATUS_LABELS = {
  hit_target: "Hedef",
  hit_stop: "Stop",
  expired: "Süre doldu",
  manual_close: "Manuel",
  active: "Aktif",
};

const TRACK_TZ = "Europe/Istanbul";

function fmtPrice(v, universe) {
  if (v == null || Number.isNaN(v)) return "—";
  const u = (universe || "").toLowerCase();
  if (u === "bist") {
    return Number(v).toLocaleString("tr-TR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }
  if (u === "binance") {
    const n = Number(v);
    if (n >= 1) return n.toFixed(4);
    return n.toFixed(6);
  }
  return Number(v).toFixed(2);
}

function fmtBenchmarkPrice(v) {
  if (v == null || Number.isNaN(v)) return "—";
  const n = Number(v);
  if (n >= 1000) {
    return n.toLocaleString("tr-TR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }
  if (n >= 1) return n.toFixed(2);
  return n.toFixed(4);
}

function fmtPct(v) {
  if (v == null || Number.isNaN(v)) return "—";
  const sign = v > 0 ? "+" : "";
  return `${sign}${v}%`;
}

function pctClass(v) {
  if (v == null) return "";
  if (v > 0) return "track-pct-up";
  if (v < 0) return "track-pct-down";
  return "";
}

function formatTrackEntryAt(iso) {
  const d = parseUtcIso(iso);
  if (!d || Number.isNaN(d.getTime())) return "—";
  const datePart = d.toLocaleDateString("tr-TR", {
    timeZone: TRACK_TZ,
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  });
  const weekday = d.toLocaleDateString("tr-TR", { timeZone: TRACK_TZ, weekday: "long" });
  const timePart = d.toLocaleTimeString("tr-TR", {
    timeZone: TRACK_TZ,
    hour: "2-digit",
    minute: "2-digit",
  });
  return `${datePart}<br><span class="hint">${weekday} · ${timePart}</span>`;
}

function formatChartAxisTime(iso) {
  const d = parseUtcIso(iso);
  if (!d || Number.isNaN(d.getTime())) return "";
  return d.toLocaleString("tr-TR", {
    timeZone: TRACK_TZ,
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

async function loadTrackSettings() {
  try {
    const res = await apiFetch("/api/track/settings");
    const s = await res.json();
    if (track$("#trackTargetPct")) track$("#trackTargetPct").value = s.target_pct;
    if (track$("#trackStopPct")) track$("#trackStopPct").value = s.stop_pct;
    if (track$("#trackAutoTrack")) track$("#trackAutoTrack").checked = !!s.auto_track_enabled;
    if (track$("#trackAutoCloseTpSl")) track$("#trackAutoCloseTpSl").checked = !!s.auto_close_on_tp_sl;
    if (track$("#trackAutoWeekend")) track$("#trackAutoWeekend").checked = !!s.auto_close_weekend_intraday;
    if (track$("#trackWeekendHour")) track$("#trackWeekendHour").value = s.weekend_close_hour ?? 23;
  } catch {
    /* ignore */
  }
}

async function saveTrackSettings(e) {
  e.preventDefault();
  const status = track$("#trackSettingsStatus");
  const payload = {
    target_pct: parseFloat(track$("#trackTargetPct").value) || 8,
    stop_pct: parseFloat(track$("#trackStopPct").value) || 5,
    auto_track_enabled: track$("#trackAutoTrack").checked,
    auto_close_on_tp_sl: track$("#trackAutoCloseTpSl").checked,
    auto_close_weekend_intraday: track$("#trackAutoWeekend").checked,
    weekend_close_hour: parseInt(track$("#trackWeekendHour").value, 10) || 23,
  };
  try {
    const res = await apiFetch("/api/track/settings", {
      method: "PATCH",
      body: JSON.stringify(payload),
    });
    const { data, text } = await parseJsonResponse(res);
    if (!res.ok) {
      if (status) status.textContent = data?.detail || text?.slice(0, 200) || "Hata";
      return;
    }
    if (status) status.textContent = "Ayarlar kaydedildi.";
  } catch (err) {
    if (status) status.textContent = err.message;
  }
}

function buildTrackRowActions(row, isActive) {
  const chartBtn = `<button type="button" class="btn secondary btn-sm" data-track-chart="${row.id}">Grafik</button>`;
  if (!isActive) {
    return `<div class="track-action-col">
      <span class="hint">${TRACK_STATUS_LABELS[row.status] || row.status}</span>
      ${chartBtn}
    </div>`;
  }
  return `<div class="track-action-col">
    <button type="button" class="btn secondary btn-sm" data-track-edit="${row.id}">TP/SL</button>
    <button type="button" class="btn secondary btn-sm" data-track-close="${row.id}">Kaldır</button>
    ${chartBtn}
  </div>`;
}

function formatBenchmarkPill(benchmark) {
  if (!benchmark || benchmark.change_pct == null) return "";
  const cls = pctClass(benchmark.change_pct);
  return `<span class="track-benchmark-pill ${cls}">${benchmark.label} ${fmtPct(benchmark.change_pct)}</span>`;
}

function renderTrackBenchmarkBar() {
  const bar = track$("#trackBenchmarkBar");
  if (!bar) return;

  const entries = Object.entries(trackBenchmarks).filter(([, b]) => b && b.change_pct != null);
  if (!entries.length) {
    bar.hidden = true;
    bar.innerHTML = "";
    return;
  }

  if (trackUniverse !== "all") {
    const bm = trackBenchmarks[trackUniverse];
    if (!bm || bm.change_pct == null) {
      bar.hidden = true;
      return;
    }
    bar.hidden = false;
    bar.innerHTML = `<span class="track-benchmark-bar-label">Endeks karşılaştırması</span>
      <span class="track-benchmark-bar-value ${pctClass(bm.change_pct)}">
        <strong>${bm.label}</strong> ${fmtPct(bm.change_pct)}
        <span class="hint">· eklenme tarihinden beri</span>
      </span>`;
    return;
  }

  bar.hidden = false;
  bar.innerHTML = `<span class="track-benchmark-bar-label">Endeksler</span>
    ${entries
      .map(
        ([id, bm]) =>
          `<span class="track-benchmark-chip ${pctClass(bm.change_pct)}" data-track-universe="${id}"><strong>${bm.label}</strong> ${fmtPct(bm.change_pct)}</span>`,
      )
      .join("")}`;
}

function escHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/"/g, "&quot;");
}

function getTrackColumn(key) {
  return TRACK_COLUMNS.find((c) => c.key === key);
}

function getTrackNumeric(col, row) {
  const v = col.getValue(row);
  if (v == null || v === "") return null;
  const n = Number(v);
  return Number.isNaN(n) ? null : n;
}

function isTrackFilterActive(colKey) {
  const f = trackTableState.filters[colKey];
  if (!f) return false;
  const col = getTrackColumn(colKey);
  if (!col) return false;
  if (col.type === "number") {
    return (f.min !== "" && f.min != null) || (f.max !== "" && f.max != null);
  }
  return f.selected !== null;
}

function hasAnyTrackFilter() {
  return TRACK_COLUMNS.some((c) => isTrackFilterActive(c.key));
}

function rowMatchesColumnFilter(row, colKey) {
  const col = getTrackColumn(colKey);
  const f = trackTableState.filters[colKey];
  if (!col || !f) return true;

  if (col.type === "number") {
    const n = getTrackNumeric(col, row);
    if (n == null) return false;
    if (f.min !== "" && f.min != null && n < parseFloat(f.min)) return false;
    if (f.max !== "" && f.max != null && n > parseFloat(f.max)) return false;
    return true;
  }

  if (f.selected === null) return true;
  if (f.selected.size === 0) return false;
  return f.selected.has(String(col.getValue(row)));
}

function getRowsForColumnOptions(colKey) {
  return trackAllRows.filter((row) =>
    TRACK_COLUMNS.every((col) => {
      if (col.key === colKey) return true;
      return rowMatchesColumnFilter(row, col.key);
    }),
  );
}

function getFilteredTrackRows() {
  return trackAllRows.filter((row) => TRACK_COLUMNS.every((col) => rowMatchesColumnFilter(row, col.key)));
}

function getSortedTrackRows(rows) {
  const { key, dir } = trackTableState.sort;
  if (!key) return rows;
  const col = getTrackColumn(key);
  if (!col) return rows;
  const mult = dir === "desc" ? -1 : 1;
  return [...rows].sort((a, b) => {
    if (col.type === "number") {
      const na = getTrackNumeric(col, a);
      const nb = getTrackNumeric(col, b);
      if (na == null && nb == null) return 0;
      if (na == null) return 1;
      if (nb == null) return -1;
      return (na - nb) * mult;
    }
    const sa = String(col.getValue(a) || "").toLocaleLowerCase("tr");
    const sb = String(col.getValue(b) || "").toLocaleLowerCase("tr");
    return sa.localeCompare(sb, "tr") * mult;
  });
}

function resetTrackTableFilters() {
  trackTableState.filters = {};
  trackTableState.sort = { key: null, dir: "asc" };
  closeTrackColFilterMenu();
  clearTrackSelection();
  updateTrackFilterToolbar();
  updateTrackHeaderFilterStates();
}

function updateTrackFilterToolbar() {
  const toolbar = track$("#trackTableToolbar");
  const summary = track$("#trackFilterSummary");
  if (!toolbar || !summary) return;
  const total = trackAllRows.length;
  const shown = getFilteredTrackRows().length;
  const active = hasAnyTrackFilter() || trackTableState.sort.key;
  toolbar.hidden = !total;
  const clearBtn = track$("#btnTrackClearFilters");
  if (clearBtn) clearBtn.hidden = !active;
  if (!active) {
    summary.textContent = total ? `${total} kayıt` : "";
    return;
  }
  summary.textContent =
    shown === total ? `${total} kayıt (sıralı)` : `${shown} / ${total} kayıt gösteriliyor`;
}

function updateTrackHeaderFilterStates() {
  document.querySelectorAll(".track-col-filter-btn").forEach((btn) => {
    const colKey = btn.dataset.trackCol;
    const sorted = trackTableState.sort.key === colKey;
    btn.classList.toggle("active", isTrackFilterActive(colKey));
    btn.classList.toggle("sorted", sorted);
    btn.textContent = sorted ? (trackTableState.sort.dir === "asc" ? "▲" : "▼") : "▾";
  });
}

function closeTrackColFilterMenu() {
  const menu = track$("#trackColFilterMenu");
  if (menu) menu.hidden = true;
  trackOpenFilterCol = null;
}

function positionTrackColFilterMenu(anchor) {
  const menu = track$("#trackColFilterMenu");
  if (!menu || !anchor) return;
  const rect = anchor.getBoundingClientRect();
  menu.style.left = `${Math.max(8, rect.left)}px`;
  menu.style.top = `${rect.bottom + 4}px`;
  const menuRect = menu.getBoundingClientRect();
  if (menuRect.right > window.innerWidth - 8) {
    menu.style.left = `${Math.max(8, window.innerWidth - menuRect.width - 8)}px`;
  }
  if (menuRect.bottom > window.innerHeight - 8) {
    menu.style.top = `${Math.max(8, rect.top - menuRect.height - 4)}px`;
  }
}

function openTrackColFilter(colKey, anchor) {
  const col = getTrackColumn(colKey);
  const menu = track$("#trackColFilterMenu");
  const title = track$("#trackColFilterTitle");
  const sortWrap = track$("#trackColFilterSort");
  const body = track$("#trackColFilterBody");
  if (!col || !menu || !sortWrap || !body) return;

  if (trackOpenFilterCol === colKey && !menu.hidden) {
    closeTrackColFilterMenu();
    return;
  }

  trackOpenFilterCol = colKey;
  if (title) title.textContent = col.label;

  const ascLabel = col.type === "number" ? "Küçükten büyüğe" : "A → Z";
  const descLabel = col.type === "number" ? "Büyükten küçüğe" : "Z → A";
  sortWrap.innerHTML = `
    <button type="button" class="track-col-sort-btn${trackTableState.sort.key === colKey && trackTableState.sort.dir === "asc" ? " active" : ""}" data-sort="asc">${ascLabel}</button>
    <button type="button" class="track-col-sort-btn${trackTableState.sort.key === colKey && trackTableState.sort.dir === "desc" ? " active" : ""}" data-sort="desc">${descLabel}</button>`;

  sortWrap.querySelectorAll("[data-sort]").forEach((btn) => {
    btn.addEventListener("click", () => {
      trackTableState.sort = { key: colKey, dir: btn.dataset.sort };
      closeTrackColFilterMenu();
      renderTrackTable();
    });
  });

  if (col.type === "number") {
    const f = trackTableState.filters[colKey] || { min: "", max: "" };
    body.innerHTML = `
      <label class="track-col-filter-field">
        <span>Min</span>
        <input type="number" step="any" id="trackFilterMin" value="${f.min ?? ""}" placeholder="—" />
      </label>
      <label class="track-col-filter-field">
        <span>Max</span>
        <input type="number" step="any" id="trackFilterMax" value="${f.max ?? ""}" placeholder="—" />
      </label>`;
  } else {
    const rows = getRowsForColumnOptions(colKey);
    const values = [...new Set(rows.map((r) => String(col.getValue(r))))].sort((a, b) =>
      a.localeCompare(b, "tr"),
    );
    const current = trackTableState.filters[colKey]?.selected;
    const checked = (val) => current === null || current?.has(val);
    body.innerHTML = `
      <input type="search" class="track-col-filter-search" id="trackFilterSearch" placeholder="Ara…" />
      <div class="track-col-filter-check-actions">
        <button type="button" class="linkish" id="trackFilterSelectAll">Tümünü seç</button>
        <button type="button" class="linkish" id="trackFilterSelectNone">Temizle</button>
      </div>
      <div class="track-col-filter-checks" id="trackFilterChecks">
        ${values
          .map(
            (val) =>
              `<label class="track-col-filter-check"><input type="checkbox" value="${escHtml(val)}" ${checked(val) ? "checked" : ""} /><span>${escHtml(val)}</span></label>`,
          )
          .join("")}
      </div>`;

    const search = body.querySelector("#trackFilterSearch");
    search?.addEventListener("input", () => {
      const q = search.value.trim().toLocaleLowerCase("tr");
      body.querySelectorAll(".track-col-filter-check").forEach((label) => {
        const text = label.textContent.trim().toLocaleLowerCase("tr");
        label.hidden = q && !text.includes(q);
      });
    });

    body.querySelector("#trackFilterSelectAll")?.addEventListener("click", () => {
      body.querySelectorAll("#trackFilterChecks input[type=checkbox]").forEach((cb) => {
        if (!cb.closest(".track-col-filter-check")?.hidden) cb.checked = true;
      });
    });
    body.querySelector("#trackFilterSelectNone")?.addEventListener("click", () => {
      body.querySelectorAll("#trackFilterChecks input[type=checkbox]").forEach((cb) => {
        if (!cb.closest(".track-col-filter-check")?.hidden) cb.checked = false;
      });
    });
  }

  menu.hidden = false;
  positionTrackColFilterMenu(anchor);
  requestAnimationFrame(() => positionTrackColFilterMenu(anchor));
}

function applyTrackColFilter() {
  const colKey = trackOpenFilterCol;
  const col = getTrackColumn(colKey);
  const body = track$("#trackColFilterBody");
  if (!col || !body) return;

  if (col.type === "number") {
    const min = body.querySelector("#trackFilterMin")?.value ?? "";
    const max = body.querySelector("#trackFilterMax")?.value ?? "";
    if (min === "" && max === "") {
      delete trackTableState.filters[colKey];
    } else {
      trackTableState.filters[colKey] = { min, max };
    }
  } else {
    const checks = [...body.querySelectorAll("#trackFilterChecks input[type=checkbox]:checked")];
    const allChecks = [...body.querySelectorAll("#trackFilterChecks input[type=checkbox]")];
    if (!checks.length) {
      trackTableState.filters[colKey] = { selected: new Set() };
    } else if (checks.length === allChecks.length) {
      delete trackTableState.filters[colKey];
    } else {
      trackTableState.filters[colKey] = {
        selected: new Set(checks.map((cb) => cb.value)),
      };
    }
  }

  closeTrackColFilterMenu();
  renderTrackTable();
}

function clearTrackColFilter() {
  if (trackOpenFilterCol) {
    delete trackTableState.filters[trackOpenFilterCol];
  }
  closeTrackColFilterMenu();
  renderTrackTable();
}

function getVisibleTrackRows() {
  return getSortedTrackRows(getFilteredTrackRows());
}

function getBulkActionIds() {
  const visible = getVisibleTrackRows();
  if (!visible.length) return [];
  const visibleIdSet = new Set(visible.map((r) => r.id));
  const selectedVisible = [...trackSelectedIds].filter((id) => visibleIdSet.has(id));
  if (selectedVisible.length) return selectedVisible;
  return visible.map((r) => r.id);
}

function clearTrackSelection() {
  trackSelectedIds.clear();
}

function syncSelectAllCheckbox() {
  const selectAll = track$("#trackSelectAll");
  if (!selectAll) return;
  const visible = getVisibleTrackRows();
  if (!visible.length) {
    selectAll.checked = false;
    selectAll.indeterminate = false;
    return;
  }
  const selectedCount = visible.filter((r) => trackSelectedIds.has(r.id)).length;
  selectAll.checked = selectedCount === visible.length;
  selectAll.indeterminate = selectedCount > 0 && selectedCount < visible.length;
}

function updateTrackBulkActions() {
  const closeBtn = track$("#btnTrackClearActive");
  const reopenBtn = track$("#btnTrackReopenSelected");
  const deleteBtn = track$("#btnTrackDeleteSelected");
  const refreshBtn = track$("#btnTrackRefresh");
  const isActive = trackView === "active";
  if (closeBtn) closeBtn.hidden = !isActive;
  if (reopenBtn) reopenBtn.hidden = isActive;
  if (deleteBtn) deleteBtn.hidden = isActive;
  if (refreshBtn) refreshBtn.hidden = !isActive;
  syncSelectAllCheckbox();
}

function initTrackTableHeaders() {
  const headRow = track$("#trackTableHeadRow");
  if (!headRow || headRow.dataset.ready) return;
  headRow.dataset.ready = "1";
  headRow.innerHTML =
    `<th class="track-th-check"><input type="checkbox" id="trackSelectAll" title="Ekrandakilerin tümünü seç" /></th>` +
    TRACK_COLUMNS.map(
      (col) => `<th class="track-th-filterable" data-track-col="${col.key}">
      <div class="track-th-inner">
        <span>${col.label}</span>
        <button type="button" class="track-col-filter-btn" data-track-col="${col.key}" aria-label="${col.label} filtrele" title="Filtrele ve sırala">▾</button>
      </div>
    </th>`,
    ).join("") +
    "<th>İşlem</th>";

  track$("#trackSelectAll")?.addEventListener("change", (e) => {
    const visible = getVisibleTrackRows();
    if (e.target.checked) {
      visible.forEach((r) => trackSelectedIds.add(r.id));
    } else {
      visible.forEach((r) => trackSelectedIds.delete(r.id));
    }
    renderTrackTable();
  });

  headRow.querySelectorAll(".track-col-filter-btn").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      openTrackColFilter(btn.dataset.trackCol, btn);
    });
  });
}

function renderTrackTableBody(rows, isActive) {
  const tbody = track$("#trackPositionsBody");
  if (!tbody) return;

  if (!trackAllRows.length) {
    tbody.innerHTML =
      trackView === "active"
        ? '<tr class="empty"><td colspan="12">Henüz izlenen pozisyon yok. Zamanlanmış tarama veya «İzlemeye ekle» kullanın.</td></tr>'
        : '<tr class="empty"><td colspan="12">Kapalı kayıt yok.</td></tr>';
    updateTrackFilterToolbar();
    updateTrackHeaderFilterStates();
    updateTrackBulkActions();
    return;
  }

  if (!rows.length) {
    tbody.innerHTML = '<tr class="empty"><td colspan="12">Filtreye uygun kayıt yok.</td></tr>';
    updateTrackFilterToolbar();
    updateTrackHeaderFilterStates();
    updateTrackBulkActions();
    return;
  }

  tbody.innerHTML = rows
    .map((r) => {
      const src = getTrackSourceText(r);
      const chg = fmtPct(r.change_pct);
      const bmLabel = r.benchmark_symbol || "—";
      const bmChg = fmtPct(r.benchmark_change_pct);
      const checked = trackSelectedIds.has(r.id) ? "checked" : "";
      return `<tr>
          <td class="track-check-cell"><input type="checkbox" class="track-row-select" data-track-select="${r.id}" ${checked} /></td>
          <td><strong>${r.symbol}</strong><br><span class="hint">${r.universe}</span></td>
          <td class="track-source-cell">${src}</td>
          <td class="track-entry-cell">${formatTrackEntryAt(r.entry_at)}</td>
          <td>${fmtPrice(r.entry_price, r.universe)}</td>
          <td>${fmtPrice(r.current_price, r.universe)}</td>
          <td class="${pctClass(r.change_pct)}">${chg}</td>
          <td>${fmtBenchmarkPrice(r.benchmark_current_price)}<br><span class="hint">${bmLabel}</span></td>
          <td class="${pctClass(r.benchmark_change_pct)}">${bmChg}</td>
          <td>${fmtPrice(r.target_price, r.universe)}<br><span class="hint">+${r.target_pct}%</span></td>
          <td>${fmtPrice(r.stop_price, r.universe)}<br><span class="hint">−${r.stop_pct}%</span></td>
          <td class="scheduled-actions">${buildTrackRowActions(r, isActive)}</td>
        </tr>`;
    })
    .join("");

  tbody.querySelectorAll("[data-track-select]").forEach((cb) => {
    cb.addEventListener("change", () => {
      const id = parseInt(cb.dataset.trackSelect, 10);
      if (Number.isNaN(id)) return;
      if (cb.checked) trackSelectedIds.add(id);
      else trackSelectedIds.delete(id);
      updateTrackBulkActions();
    });
  });

  tbody.querySelectorAll("[data-track-close]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      if (!confirm("Bu pozisyon izlemeden kaldırılsın mı?")) return;
      await apiFetch(`/api/track/positions/${btn.dataset.trackClose}/close`, { method: "POST" });
      loadTrackPositions();
    });
  });

  tbody.querySelectorAll("[data-track-edit]").forEach((btn) => {
    btn.addEventListener("click", () => editTrackLevels(btn.dataset.trackEdit, rows));
  });

  tbody.querySelectorAll("[data-track-chart]").forEach((btn) => {
    btn.addEventListener("click", () => openTrackChart(btn.dataset.trackChart));
  });

  updateTrackFilterToolbar();
  updateTrackHeaderFilterStates();
  updateTrackBulkActions();
}

function renderTrackTable() {
  const isActive = trackView === "active";
  const rows = getVisibleTrackRows();
  renderTrackTableBody(rows, isActive);
}

async function loadTrackUniverses() {
  const container = track$("#trackUniverseTabs");
  if (!container) return;
  try {
    const res = await apiFetch(`/api/track/universes?status=${trackView}`);
    const universes = await res.json();
    trackBenchmarks = {};
    universes.forEach((u) => {
      if (u.benchmark) trackBenchmarks[u.id] = u.benchmark;
    });
    renderTrackBenchmarkBar();

    if (!universes.length) {
      container.hidden = true;
      container.innerHTML = "";
      trackUniverse = "all";
      return;
    }
    container.hidden = false;
    const tabs = [{ id: "all", label: "Tümü" }, ...universes];
    if (!tabs.some((t) => t.id === trackUniverse)) {
      trackUniverse = "all";
    }
    container.innerHTML = tabs
      .map((t) => {
        const pill = t.id !== "all" ? formatBenchmarkPill(t.benchmark) : "";
        return `<button type="button" class="track-universe-tab${t.id === trackUniverse ? " active" : ""}" data-track-universe="${t.id}">${t.label}${pill ? `<span class="track-universe-tab-meta">${pill}</span>` : ""}</button>`;
      })
      .join("");
    container.querySelectorAll("[data-track-universe]").forEach((btn) => {
      btn.addEventListener("click", () => {
        trackUniverse = btn.dataset.trackUniverse || "all";
        container.querySelectorAll(".track-universe-tab").forEach((b) => {
          b.classList.toggle("active", b === btn);
        });
        resetTrackTableFilters();
        clearTrackSelection();
        renderTrackBenchmarkBar();
        loadTrackPositions();
      });
    });
  } catch {
    container.hidden = true;
  }
}

async function loadTrackPositions() {
  const tbody = track$("#trackPositionsBody");
  if (!tbody) return;
  initTrackTableHeaders();
  await loadTrackUniverses();
  const universeParam = trackUniverse !== "all" ? `&universe=${encodeURIComponent(trackUniverse)}` : "";
  try {
    const res = await apiFetch(`/api/track/positions?status=${trackView}${universeParam}`);
    trackAllRows = await res.json();
    renderTrackTable();
  } catch {
    trackAllRows = [];
    tbody.innerHTML = '<tr class="empty"><td colspan="12">Liste yüklenemedi.</td></tr>';
    updateTrackFilterToolbar();
  }
}

function editTrackLevels(id, rows) {
  const row = (rows || trackAllRows).find((r) => String(r.id) === String(id));
  if (!row) return;
  const tp = prompt(
    `Hedef fiyat (${row.symbol}, giriş ${fmtPrice(row.entry_price, row.universe)}):`,
    String(row.target_price),
  );
  if (tp === null) return;
  const sl = prompt(`Stop fiyat:`, String(row.stop_price));
  if (sl === null) return;
  const target = parseFloat(tp);
  const stop = parseFloat(sl);
  if (Number.isNaN(target) || Number.isNaN(stop) || target <= 0 || stop <= 0) {
    alert("Geçersiz fiyat.");
    return;
  }
  apiFetch(`/api/track/positions/${id}`, {
    method: "PATCH",
    body: JSON.stringify({ target_price: target, stop_price: stop }),
  }).then(() => loadTrackPositions());
}

function renderTrackChartSvg(data) {
  const points = data.points || [];
  if (!points.length) {
    return '<p class="hint">Henüz fiyat geçmişi yok.</p>';
  }

  const benchmarkAligned = data.benchmark_aligned || [];
  const hasBenchmark = benchmarkAligned.some((v) => v != null);

  const width = 1700;
  const height = 800;
  const pad = { top: 48, right: 40, bottom: 64, left: 64 };
  const innerW = width - pad.left - pad.right;
  const innerH = height - pad.top - pad.bottom;

  const pctValues = points.map((p) => p.change_pct ?? 0);
  if (hasBenchmark) {
    benchmarkAligned.forEach((v) => {
      if (v != null) pctValues.push(v);
    });
  }
  const targetPct = data.target_pct ?? 0;
  const stopPct = data.stop_pct ?? 0;
  let yMin = Math.min(...pctValues, stopPct, 0);
  let yMax = Math.max(...pctValues, targetPct, 0);
  const yPad = Math.max(2, (yMax - yMin) * 0.12 || 4);
  yMin -= yPad;
  yMax += yPad;

  const xScale = (i) => pad.left + (points.length === 1 ? innerW / 2 : (i / (points.length - 1)) * innerW);
  const yScale = (pct) => pad.top + innerH - ((pct - yMin) / (yMax - yMin)) * innerH;

  const linePath = points
    .map((p, i) => `${i === 0 ? "M" : "L"} ${xScale(i).toFixed(1)} ${yScale(p.change_pct ?? 0).toFixed(1)}`)
    .join(" ");

  const benchmarkPath = hasBenchmark
    ? benchmarkAligned
        .map((v, i) => ({ v, i }))
        .filter(({ v }) => v != null)
        .map(({ v, i }, idx) => `${idx === 0 ? "M" : "L"} ${xScale(i).toFixed(1)} ${yScale(v).toFixed(1)}`)
        .join(" ")
    : "";

  const zeroY = yScale(0).toFixed(1);
  const targetY = yScale(targetPct).toFixed(1);
  const stopY = yScale(stopPct).toFixed(1);

  const yTicks = [];
  const tickStep = yMax - yMin <= 12 ? 2 : yMax - yMin <= 30 ? 5 : 10;
  for (let t = Math.ceil(yMin / tickStep) * tickStep; t <= yMax; t += tickStep) {
    yTicks.push(t);
  }

  const gridLines = yTicks
    .map((t) => {
      const y = yScale(t).toFixed(1);
      return `<line x1="${pad.left}" y1="${y}" x2="${width - pad.right}" y2="${y}" class="track-chart-grid"/>`;
    })
    .join("");

  const yLabels = yTicks
    .map((t) => {
      const y = yScale(t).toFixed(1);
      const sign = t > 0 ? "+" : "";
      return `<text x="${pad.left - 8}" y="${y}" class="track-chart-axis" text-anchor="end" dominant-baseline="middle">${sign}${t.toFixed(0)}%</text>`;
    })
    .join("");

  const xLabels = points
    .map((p, i) => {
      const show = points.length <= 8 || i === 0 || i === points.length - 1 || i % Math.ceil(points.length / 6) === 0;
      if (!show) return "";
      const x = xScale(i).toFixed(1);
      return `<text x="${x}" y="${height - 12}" class="track-chart-axis" text-anchor="middle">${formatChartAxisTime(p.recorded_at)}</text>`;
    })
    .join("");

  const dots = points
    .map((p, i) => {
      const cx = xScale(i).toFixed(1);
      const cy = yScale(p.change_pct ?? 0).toFixed(1);
      return `<circle cx="${cx}" cy="${cy}" r="6" class="track-chart-dot"/>`;
    })
    .join("");

  const benchmarkDots = hasBenchmark
    ? benchmarkAligned
        .map((v, i) => {
          if (v == null) return "";
          const cx = xScale(i).toFixed(1);
          const cy = yScale(v).toFixed(1);
          return `<circle cx="${cx}" cy="${cy}" r="5.5" class="track-chart-benchmark-dot"/>`;
        })
        .join("")
    : "";

  return `<svg viewBox="0 0 ${width} ${height}" class="track-chart-svg" role="img" aria-label="Fiyat performans grafiği">
    <defs>
      <pattern id="trackChartDots" width="8" height="8" patternUnits="userSpaceOnUse">
        <circle cx="1" cy="1" r="0.75" class="track-chart-bg-dot"/>
      </pattern>
    </defs>
    <rect x="${pad.left}" y="${pad.top}" width="${innerW}" height="${innerH}" class="track-chart-plot" fill="url(#trackChartDots)"/>
    ${gridLines}
    <line x1="${pad.left}" y1="${zeroY}" x2="${width - pad.right}" y2="${zeroY}" class="track-chart-zero"/>
    <line x1="${pad.left}" y1="${targetY}" x2="${width - pad.right}" y2="${targetY}" class="track-chart-target-line"/>
    <line x1="${pad.left}" y1="${stopY}" x2="${width - pad.right}" y2="${stopY}" class="track-chart-stop-line"/>
    ${benchmarkPath ? `<path d="${benchmarkPath}" class="track-chart-benchmark-line"/>` : ""}
    <path d="${linePath}" class="track-chart-line"/>
    ${benchmarkDots}
    ${dots}
    ${yLabels}
    ${xLabels}
  </svg>`;
}

async function openTrackChart(positionId) {
  const modal = track$("#trackChartModal");
  const wrap = track$("#trackChartWrap");
  const title = track$("#trackChartTitle");
  const meta = track$("#trackChartMeta");
  const legend = track$("#trackChartLegend");
  if (!modal || !wrap) return;

  wrap.innerHTML = '<p class="hint">Grafik yükleniyor…</p>';
  modal.hidden = false;

  try {
    const res = await apiFetch(`/api/track/positions/${positionId}/history`);
    const data = await res.json();
    if (!res.ok) {
      wrap.innerHTML = `<p class="hint">${data?.detail || "Grafik yüklenemedi."}</p>`;
      return;
    }
    if (title) {
      title.textContent = `${data.symbol} — performans grafiği`;
    }
    if (meta) {
      meta.textContent = `${data.source_label || "—"} · ${data.timeframe || ""} · Giriş ${fmtPrice(data.entry_price, data.universe)} (${formatTrackEntryAt(data.entry_at).replace(/<[^>]+>/g, " ")})`;
    }
    wrap.innerHTML = renderTrackChartSvg(data);
    if (legend) {
      const benchLabel = data.benchmark_label || "Endeks";
      const hasBenchmark = (data.benchmark_aligned || []).some((v) => v != null);
      const benchLegend = hasBenchmark
        ? `<span class="track-legend-item"><i class="track-legend-line benchmark"></i> ${benchLabel}</span>`
        : "";
      legend.innerHTML = `
        <span class="track-legend-item"><i class="track-legend-line price"></i> Hisse</span>
        ${benchLegend}
        <span class="track-legend-item"><i class="track-legend-line target"></i> Hedef (+${fmtPct(data.target_pct)})</span>
        <span class="track-legend-item"><i class="track-legend-line stop"></i> Stop (${fmtPct(data.stop_pct)})</span>`;
    }
  } catch (e) {
    wrap.innerHTML = `<p class="hint">${e.message}</p>`;
  }
}

function closeTrackChartModal() {
  const modal = track$("#trackChartModal");
  if (modal) modal.hidden = true;
}

async function refreshTrackPrices() {
  const status = track$("#trackListStatus");
  if (status) status.textContent = "Fiyatlar güncelleniyor…";
  try {
    const res = await apiFetch("/api/track/refresh-prices", { method: "POST" });
    const data = await res.json();
    if (status) {
      status.textContent = `Güncellendi: ${data.checked ?? 0} pozisyon, ${data.closed ?? 0} TP/SL ile kapandı.`;
    }
    loadTrackPositions();
  } catch (e) {
    if (status) status.textContent = e.message;
  }
}

async function clearActiveTrack() {
  if (trackView !== "active") return;
  const ids = getBulkActionIds();
  if (!ids.length) {
    alert("Kapatılacak kayıt yok.");
    return;
  }
  const visible = getVisibleTrackRows();
  const visibleIdSet = new Set(visible.map((r) => r.id));
  const hasSelection = [...trackSelectedIds].some((id) => visibleIdSet.has(id));
  const msg = hasSelection
    ? `${ids.length} seçili pozisyon kapatılsın mı?`
    : `Ekrandaki ${ids.length} pozisyon kapatılsın mı?`;
  if (!confirm(msg)) return;
  const status = track$("#trackListStatus");
  try {
    const res = await apiFetch("/api/track/positions/bulk-close", {
      method: "POST",
      body: JSON.stringify({ position_ids: ids }),
    });
    const data = await res.json();
    if (status) status.textContent = `${data.closed ?? 0} pozisyon kapatıldı.`;
    clearTrackSelection();
    loadTrackPositions();
  } catch (e) {
    if (status) status.textContent = e.message;
  }
}

async function reopenSelectedTrack() {
  if (trackView !== "closed") return;
  const ids = getBulkActionIds();
  if (!ids.length) {
    alert("Aktife alınacak kayıt yok.");
    return;
  }
  const visible = getVisibleTrackRows();
  const visibleIdSet = new Set(visible.map((r) => r.id));
  const hasSelection = [...trackSelectedIds].some((id) => visibleIdSet.has(id));
  const msg = hasSelection
    ? `${ids.length} seçili pozisyon aktife alınsın mı?`
    : `Ekrandaki ${ids.length} pozisyon aktife alınsın mı?`;
  if (!confirm(msg)) return;
  const status = track$("#trackListStatus");
  try {
    const res = await apiFetch("/api/track/positions/bulk-reopen", {
      method: "POST",
      body: JSON.stringify({ position_ids: ids }),
    });
    const data = await res.json();
    if (status) status.textContent = `${data.reopened ?? 0} pozisyon aktife alındı.`;
    clearTrackSelection();
    loadTrackPositions();
  } catch (e) {
    if (status) status.textContent = e.message;
  }
}

async function deleteSelectedFromList() {
  if (trackView !== "closed") return;
  const ids = getBulkActionIds();
  if (!ids.length) {
    alert("Kaldırılacak kayıt yok.");
    return;
  }
  const visible = getVisibleTrackRows();
  const visibleIdSet = new Set(visible.map((r) => r.id));
  const hasSelection = [...trackSelectedIds].some((id) => visibleIdSet.has(id));
  const msg = hasSelection
    ? `${ids.length} seçili kayıt listeden kalıcı olarak silinsin mi?`
    : `Ekrandaki ${ids.length} kayıt listeden kalıcı olarak silinsin mi?`;
  if (!confirm(msg)) return;
  const status = track$("#trackListStatus");
  try {
    const res = await apiFetch("/api/track/positions/bulk-delete", {
      method: "POST",
      body: JSON.stringify({ position_ids: ids }),
    });
    const data = await res.json();
    if (status) status.textContent = `${data.deleted ?? 0} kayıt listeden kaldırıldı.`;
    clearTrackSelection();
    loadTrackPositions();
  } catch (e) {
    if (status) status.textContent = e.message;
  }
}

async function ingestLastScanToTrack() {
  if (!lastScanData?.results?.length) {
    setStatus("Önce tarama yapın.", "error");
    return;
  }
  const payload = {
    universe: lastScanData.universe || $("#universe").value,
    timeframe: lastScanData.timeframe || $("#timeframe").value,
    source_label: "Manuel tarama",
    results: lastScanData.results,
  };
  try {
    const res = await apiFetch("/api/track/positions/ingest", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    setStatus(`${data.added ?? 0} sembol izlemeye eklendi.`, "ok");
  } catch (e) {
    setStatus("İzleme hatası: " + e.message, "error");
  }
}

function initTrackPanel() {
  initTrackTableHeaders();
  track$("#trackSettingsForm")?.addEventListener("submit", saveTrackSettings);
  track$("#btnTrackRefresh")?.addEventListener("click", refreshTrackPrices);
  track$("#btnTrackClearActive")?.addEventListener("click", clearActiveTrack);
  track$("#btnTrackReopenSelected")?.addEventListener("click", reopenSelectedTrack);
  track$("#btnTrackDeleteSelected")?.addEventListener("click", deleteSelectedFromList);
  track$("#btnTrackResults")?.addEventListener("click", ingestLastScanToTrack);
  track$("#btnTrackClearFilters")?.addEventListener("click", resetTrackTableFilters);
  track$("#trackColFilterApply")?.addEventListener("click", applyTrackColFilter);
  track$("#trackColFilterClear")?.addEventListener("click", clearTrackColFilter);
  track$("#trackChartClose")?.addEventListener("click", closeTrackChartModal);
  track$("#trackChartModal")?.addEventListener("click", (e) => {
    if (e.target.id === "trackChartModal") closeTrackChartModal();
  });

  document.addEventListener("click", (e) => {
    const menu = track$("#trackColFilterMenu");
    if (!menu || menu.hidden) return;
    if (menu.contains(e.target) || e.target.closest(".track-col-filter-btn")) return;
    closeTrackColFilterMenu();
  });

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") closeTrackColFilterMenu();
  });

  document.querySelectorAll(".track-view-tab").forEach((btn) => {
    btn.addEventListener("click", () => {
      trackView = btn.dataset.trackView || "active";
      trackUniverse = "all";
      resetTrackTableFilters();
      document.querySelectorAll(".track-view-tab").forEach((b) => {
        b.classList.toggle("active", b === btn);
      });
      renderTrackBenchmarkBar();
      updateTrackBulkActions();
      loadTrackPositions();
    });
  });
}

function onTrackTabShown() {
  loadTrackSettings();
  updateTrackBulkActions();
  loadTrackPositions();
}

document.addEventListener("DOMContentLoaded", () => {
  initTrackPanel();
});
