let alarmContracts = [];
let alarmPineParams = [];
let alarmEditingId = null;
let alarmSelected = new Set();

function alarmEsc(s) {
  return String(s ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/"/g, "&quot;");
}

function alarmStatus(msg, kind) {
  const el = document.querySelector("#alarmFormStatus");
  if (!el) return;
  el.textContent = msg || "";
  el.classList.toggle("ok", kind === "ok");
  el.classList.toggle("error", kind === "error");
}

function collectAlarmPineInputs() {
  const host = document.querySelector("#alarmPineForm");
  if (!host) return {};
  const out = {};
  host.querySelectorAll("[data-pine-input]").forEach((el) => {
    const name = el.dataset.pineInput;
    const type = el.dataset.pineType;
    if (type === "bool") out[name] = el.checked;
    else if (type === "int") {
      const v = parseInt(el.value, 10);
      if (!Number.isNaN(v)) out[name] = v;
    } else if (type === "float") {
      const v = parseFloat(el.value);
      if (!Number.isNaN(v)) out[name] = v;
    } else out[name] = el.value;
  });
  return out;
}

function renderAlarmPineParams(parameters, overrides) {
  const box = document.querySelector("#alarmPineBox");
  const form = document.querySelector("#alarmPineForm");
  if (!box || !form) return;
  alarmPineParams = parameters || [];
  const editable = alarmPineParams.filter(
    (p) => p.group !== "Visual" && p.group !== "Display Settings" && p.type !== "color"
  );
  if (!editable.length) {
    box.hidden = true;
    form.innerHTML = "";
    return;
  }
  box.hidden = false;
  const ov = overrides || {};
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
  const fieldFn =
    typeof renderPineInputField === "function"
      ? renderPineInputField
      : (p, value) =>
          `<input type="text" data-pine-input="${p.name}" data-pine-type="string" value="${alarmEsc(value)}" />`;
  form.innerHTML = groups
    .map((group) => {
      const rows = byGroup
        .get(group)
        .map((p) => {
          const val = ov[p.name] !== undefined ? ov[p.name] : p.value ?? p.default;
          return `<div class="pine-input-row">
            <label>
              <span class="pine-input-label">${alarmEsc(p.label)}</span>
              <span class="pine-input-name">${alarmEsc(p.name)}</span>
            </label>
            ${fieldFn(p, val)}
          </div>`;
        })
        .join("");
      return `<div class="pine-input-group-title">${alarmEsc(group)}</div>${rows}`;
    })
    .join("");
}

async function loadAlarmPineOptions() {
  const sel = document.querySelector("#alarmPine");
  if (!sel) return;
  const prev = sel.value;
  try {
    const res = await apiFetch("/api/pine/scripts");
    const scripts = await res.json();
    sel.innerHTML = '<option value="">— Seçin —</option>';
    (scripts || []).forEach((s) => {
      if (!s.available) return;
      const opt = document.createElement("option");
      opt.value = s.id;
      opt.textContent = s.name;
      sel.appendChild(opt);
    });
    if (prev) sel.value = prev;
  } catch {
    sel.innerHTML = '<option value="">Pine listesi alınamadı</option>';
  }
}

async function loadAlarmPineParams(id, overrides) {
  if (!id) {
    renderAlarmPineParams([], {});
    return;
  }
  try {
    const res = await apiFetch(`/api/pine/scripts/${id}`);
    const data = await res.json();
    renderAlarmPineParams(data.parameters || [], overrides || {});
  } catch {
    renderAlarmPineParams([], overrides || {});
  }
}

function selectedAlarmContracts() {
  return [...alarmSelected];
}

function setAlarmSaveMode(editing) {
  const btn = document.querySelector("#btnAlarmSave");
  if (btn) btn.textContent = editing ? "Güncelle" : "Kaydet";
}

function updateAlarmContractHint() {
  const hint = document.querySelector("#alarmContractHint");
  if (hint) hint.textContent = `Seçilen ${alarmSelected.size} / ${alarmContracts.length}`;
}

function renderAlarmContracts(selected) {
  const grid = document.querySelector("#alarmContractGrid");
  if (!grid) return;
  if (Array.isArray(selected)) {
    alarmSelected = new Set(selected);
  }
  const q = (document.querySelector("#alarmContractFilter")?.value || "")
    .trim()
    .toLocaleLowerCase("tr");
  const rows = alarmContracts.filter((c) => {
    if (!q) return true;
    return `${c.ticker} ${c.contract} ${c.name}`.toLocaleLowerCase("tr").includes(q);
  });
  updateAlarmContractHint();
  if (!rows.length) {
    grid.innerHTML = '<p class="hint">Eşleşen pay yok.</p>';
    return;
  }
  grid.innerHTML = rows
    .map((c) => {
      const on = alarmSelected.has(c.contract) ? "checked" : "";
      return `<label class="alarm-contract">
        <input type="checkbox" value="${alarmEsc(c.contract)}" ${on} />
        <span><strong>${alarmEsc(c.ticker)}</strong> ${alarmEsc(c.name)}</span>
      </label>`;
    })
    .join("");
  grid.querySelectorAll("input").forEach((cb) => {
    cb.addEventListener("change", () => {
      if (cb.checked) alarmSelected.add(cb.value);
      else alarmSelected.delete(cb.value);
      updateAlarmContractHint();
    });
  });
}

async function loadAlarmContracts() {
  const res = await apiFetch("/api/alarms/contracts");
  const data = await res.json();
  alarmContracts = data.contracts || [];
  renderAlarmContracts([]);
}

function alarmWeekdays() {
  return [...document.querySelectorAll("#alarmWeekdays input:checked")].map((el) =>
    parseInt(el.value, 10)
  );
}

function setAlarmWeekdays(days) {
  const set = new Set((days || [0, 1, 2, 3, 4]).map(Number));
  document.querySelectorAll("#alarmWeekdays input").forEach((el) => {
    el.checked = set.has(parseInt(el.value, 10));
  });
}

function resetAlarmForm() {
  alarmEditingId = null;
  document.querySelector("#alarmId").value = "";
  document.querySelector("#alarmName").value = "";
  document.querySelector("#alarmPine").value = "";
  document.querySelector("#alarmTimeframe").value = "15m";
  document.querySelector("#alarmStartHour").value = "9";
  document.querySelector("#alarmEndHour").value = "18";
  document.querySelector("#alarmMinute").value = "35";
  document.querySelector("#alarmTelegram").value = "";
  document.querySelector("#alarmTelegramToken").value = "";
  document.querySelector("#alarmNotifyTelegram").checked = true;
  document.querySelector("#alarmEnabled").checked = true;
  setAlarmWeekdays([0, 1, 2, 3, 4]);
  renderAlarmPineParams([], {});
  const filter = document.querySelector("#alarmContractFilter");
  if (filter) filter.value = "";
  renderAlarmContracts([]);
  setAlarmSaveMode(false);
  alarmStatus("Yeni alarm.");
}

function readyForNextAlarm(savedName) {
  alarmEditingId = null;
  document.querySelector("#alarmId").value = "";
  document.querySelector("#alarmName").value = "";
  const filter = document.querySelector("#alarmContractFilter");
  if (filter) filter.value = "";
  renderAlarmContracts([]);
  setAlarmSaveMode(false);
  alarmStatus(
    `Kaydedildi: ${savedName}. Ad ve pay seçip tekrar Kaydet — alarm sayısı sınırsız.`,
    "ok"
  );
}

function collectAlarmBody() {
  const pineId = parseInt(document.querySelector("#alarmPine").value, 10);
  const contracts = selectedAlarmContracts();
  return {
    name: document.querySelector("#alarmName").value.trim(),
    pine_script_id: pineId,
    pine_input_overrides: collectAlarmPineInputs(),
    contracts,
    timeframe: document.querySelector("#alarmTimeframe").value,
    hour: parseInt(document.querySelector("#alarmStartHour").value, 10),
    minute: parseInt(document.querySelector("#alarmMinute").value, 10),
    end_hour: parseInt(document.querySelector("#alarmEndHour").value, 10),
    weekdays: alarmWeekdays(),
    telegram_to: document.querySelector("#alarmTelegram").value.trim() || null,
    telegram_bot_token: document.querySelector("#alarmTelegramToken").value.trim() || null,
    notify_telegram: document.querySelector("#alarmNotifyTelegram").checked,
    enabled: document.querySelector("#alarmEnabled").checked,
  };
}

async function fillAlarmForm(row) {
  alarmEditingId = row.id;
  document.querySelector("#alarmId").value = String(row.id);
  document.querySelector("#alarmName").value = row.name || "";
  document.querySelector("#alarmPine").value = row.pine_script_id || "";
  document.querySelector("#alarmTimeframe").value = row.timeframe || "15m";
  document.querySelector("#alarmStartHour").value = row.hour ?? 9;
  document.querySelector("#alarmEndHour").value = row.end_hour ?? 18;
  document.querySelector("#alarmMinute").value = row.minute ?? 35;
  document.querySelector("#alarmTelegram").value = row.telegram_to || "";
  document.querySelector("#alarmNotifyTelegram").checked = row.notify_telegram !== false;
  document.querySelector("#alarmEnabled").checked = row.enabled !== false;
  setAlarmWeekdays(row.weekdays);
  await loadAlarmPineParams(row.pine_script_id, row.pine_input_overrides || {});
  renderAlarmContracts(row.contracts || []);
  setAlarmSaveMode(true);
  alarmStatus(`Düzenleniyor: ${row.name}`);
}

function tfLabel(tf) {
  return (
    { "3m": "3 dk", "5m": "5 dk", "15m": "15 dk", "30m": "30 dk", "1h": "1 saat" }[tf] || tf
  );
}

async function loadAlarmList() {
  const body = document.querySelector("#alarmListBody");
  if (!body) return;
  try {
    const res = await apiFetch("/api/alarms");
    const rows = await res.json();
    const title = document.querySelector("#alarmListTitle");
    if (title) {
      title.textContent = rows.length ? `Kayıtlı alarmlar (${rows.length})` : "Kayıtlı alarmlar";
    }
    if (!rows.length) {
      body.innerHTML = '<tr class="empty"><td colspan="5">Henüz alarm yok.</td></tr>';
      return;
    }
    body.innerHTML = rows
      .map((r) => {
        const n = (r.contracts || []).length;
        const names = (r.contracts || []).slice(0, 4).join(", ");
        const extra = n > 4 ? ` +${n - 4}` : "";
        const last = r.last_run_istanbul
          ? `${r.last_run_istanbul} · ${r.last_match_count ?? 0}`
          : "—";
        const next = r.enabled ? r.next_run_istanbul || "—" : "kapalı";
        return `<tr>
          <td><strong>${alarmEsc(r.name)}</strong>${r.enabled ? "" : ' <span class="hint">kapalı</span>'}</td>
          <td>${alarmEsc(tfLabel(r.timeframe))}</td>
          <td>${alarmEsc(names)}${extra} <span class="hint">(${n})</span></td>
          <td>${alarmEsc(last)}<br><span class="hint">${alarmEsc(next)}</span></td>
          <td class="scheduled-actions">
            <button type="button" class="btn secondary btn-sm" data-alarm-edit="${r.id}">Düzenle</button>
            <button type="button" class="btn secondary btn-sm" data-alarm-run="${r.id}">Çalıştır</button>
            <button type="button" class="btn danger btn-sm" data-alarm-del="${r.id}">Sil</button>
          </td>
        </tr>`;
      })
      .join("");
    body.querySelectorAll("[data-alarm-edit]").forEach((btn) => {
      btn.addEventListener("click", () => editAlarm(parseInt(btn.dataset.alarmEdit, 10)));
    });
    body.querySelectorAll("[data-alarm-run]").forEach((btn) => {
      btn.addEventListener("click", () => runAlarm(parseInt(btn.dataset.alarmRun, 10)));
    });
    body.querySelectorAll("[data-alarm-del]").forEach((btn) => {
      btn.addEventListener("click", () => deleteAlarm(parseInt(btn.dataset.alarmDel, 10)));
    });
  } catch (err) {
    body.innerHTML = `<tr class="empty"><td colspan="5">${alarmEsc(err.message)}</td></tr>`;
  }
}

async function editAlarm(id) {
  const res = await apiFetch(`/api/alarms/${id}`);
  const data = await res.json();
  if (!res.ok) {
    alarmStatus(data.detail || "Yüklenemedi", "error");
    return;
  }
  await fillAlarmForm(data);
}

async function runAlarm(id) {
  const alarmId = id || alarmEditingId;
  if (!alarmId) {
    alarmStatus("Önce kaydedin.", "error");
    return;
  }
  alarmStatus("Başlatılıyor…");
  try {
    const res = await apiFetch(`/api/alarms/${alarmId}/run-now`, { method: "POST" });
    const data = await res.json();
    if (!res.ok) {
      alarmStatus(data.detail || "Başlatılamadı", "error");
      return;
    }
    alarmStatus(data.message || "Arka planda çalışıyor.", "ok");
    loadAlarmList();
  } catch (err) {
    alarmStatus(err.message, "error");
  }
}

async function deleteAlarm(id) {
  if (!confirm("Bu alarm silinsin mi?")) return;
  const res = await apiFetch(`/api/alarms/${id}`, { method: "DELETE" });
  if (res.ok) {
    if (alarmEditingId === id) resetAlarmForm();
    loadAlarmList();
    alarmStatus("Silindi.", "ok");
  }
}

async function saveAlarm(e) {
  e.preventDefault();
  const body = collectAlarmBody();
  if (!body.name) {
    alarmStatus("Ad girin.", "error");
    return;
  }
  if (!body.pine_script_id) {
    alarmStatus("Pine seçin.", "error");
    return;
  }
  if (!body.contracts.length) {
    alarmStatus("En az bir pay seçin.", "error");
    return;
  }
  if (!body.weekdays.length) {
    alarmStatus("En az bir gün seçin.", "error");
    return;
  }
  alarmStatus("Kaydediliyor…");
  const editing = alarmEditingId;
  try {
    const res = await apiFetch(editing ? `/api/alarms/${editing}` : "/api/alarms", {
      method: editing ? "PATCH" : "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await res.json();
    if (!res.ok) {
      alarmStatus(data.detail || "Kayıt hatası", "error");
      return;
    }
    await loadAlarmList();
    readyForNextAlarm(data.name || body.name);
  } catch (err) {
    alarmStatus(err.message, "error");
  }
}

async function onAlarmTabShown() {
  await Promise.all([loadAlarmPineOptions(), loadAlarmContracts()]);
  await loadAlarmList();
}

function initAlarmPanel() {
  document.querySelector("#alarmForm")?.addEventListener("submit", saveAlarm);
  document.querySelector("#btnAlarmNew")?.addEventListener("click", resetAlarmForm);
  document.querySelector("#btnAlarmRunNow")?.addEventListener("click", () => runAlarm());
  document.querySelector("#alarmPine")?.addEventListener("change", (e) => {
    loadAlarmPineParams(e.target.value, {});
  });
  document.querySelector("#alarmContractFilter")?.addEventListener("input", () => {
    renderAlarmContracts();
  });
  document.querySelector("#btnAlarmSelectAllPay")?.addEventListener("click", () => {
    renderAlarmContracts(alarmContracts.map((c) => c.contract));
  });
  document.querySelector("#btnAlarmClearPay")?.addEventListener("click", () => {
    renderAlarmContracts([]);
  });
}

document.addEventListener("DOMContentLoaded", initAlarmPanel);
