/** Session-aware fetch and auth UI for main app. */

let currentUser = null;

const qs = (sel) => document.querySelector(sel);

async function apiFetch(url, options = {}) {
  const headers = { ...(options.headers || {}) };
  if (options.body && !(options.body instanceof FormData)) {
    headers["Content-Type"] = headers["Content-Type"] || "application/json";
  }
  const res = await fetch(url, {
    ...options,
    credentials: "include",
    headers,
  });
  if (res.status === 401) {
    window.location.href = "/login";
    throw new Error("Oturum sona erdi");
  }
  return res;
}

function validatePasswordClient(password) {
  if (password.length < 8) {
    return "Şifre en az 8 karakter olmalıdır.";
  }
  if (!/[A-Z]/.test(password)) {
    return "En az bir büyük harf gerekli.";
  }
  if (!/[a-z]/.test(password)) {
    return "En az bir küçük harf gerekli.";
  }
  if (!/\d/.test(password)) {
    return "En az bir rakam gerekli.";
  }
  if (!/[^A-Za-z0-9]/.test(password)) {
    return "En az bir özel karakter gerekli.";
  }
  return null;
}

function showChangePasswordModal(show) {
  const el = qs("#changePasswordModal");
  if (el) el.hidden = !show;
}

async function loadSession() {
  const res = await apiFetch("/api/auth/me");
  const data = await res.json();
  currentUser = data.user;
  return currentUser;
}

function updateHeaderUser() {
  const nameEl = qs("#headerUsername");
  const tabAdmin = qs("#tabAdmin");
  if (nameEl && currentUser) {
    nameEl.textContent =
      currentUser.role === "admin"
        ? `${currentUser.username} (admin)`
        : currentUser.username;
  }
  if (tabAdmin) {
    tabAdmin.hidden = currentUser?.role !== "admin";
  }
}

async function logout() {
  await fetch("/api/auth/logout", { method: "POST", credentials: "include" });
  window.location.href = "/login";
}

async function submitChangePassword(e) {
  e.preventDefault();
  const newPw = qs("#newPassword")?.value || "";
  const confirmPw = qs("#newPasswordConfirm")?.value || "";
  const status = qs("#changePasswordStatus");

  const err = validatePasswordClient(newPw);
  if (err) {
    if (status) status.textContent = err;
    return;
  }
  if (newPw !== confirmPw) {
    if (status) status.textContent = "Yeni şifreler eşleşmiyor.";
    return;
  }

  const body = {
    new_password: newPw,
    current_password: currentUser?.must_change_password
      ? null
      : qs("#currentPassword")?.value || null,
  };

  try {
    const res = await apiFetch("/api/auth/change-password", {
      method: "POST",
      body: JSON.stringify(body),
    });
    const data = await res.json();
    if (!res.ok) {
      if (status) status.textContent = data.detail || "Hata";
      return;
    }
    currentUser = data.user;
    showChangePasswordModal(false);
    updateHeaderUser();
    if (status) status.textContent = "";
  } catch (e) {
    if (status) status.textContent = e.message;
  }
}

function switchAppTab(tab) {
  const scan = qs("#scanPanel");
  const track = qs("#trackPanel");
  const admin = qs("#adminPanel");
  const tabScan = qs("#tabScan");
  const tabTrack = qs("#tabTrack");
  const tabAdmin = qs("#tabAdmin");
  const isAdmin = tab === "admin";
  const isTrack = tab === "track";
  if (scan) scan.classList.toggle("hidden", isAdmin || isTrack);
  if (track) track.classList.toggle("hidden", !isTrack);
  if (admin) admin.classList.toggle("active", isAdmin);
  if (tabScan) tabScan.classList.toggle("active", tab === "scan");
  if (tabTrack) tabTrack.classList.toggle("active", isTrack);
  if (tabAdmin) tabAdmin.classList.toggle("active", isAdmin);
  if (isAdmin) loadAdminUsers();
  if (isTrack && typeof onTrackTabShown === "function") onTrackTabShown();
}

async function loadAdminUsers() {
  const tbody = qs("#adminUsersBody");
  if (!tbody) return;
  try {
    const res = await apiFetch("/api/admin/users");
    const data = await res.json();
    tbody.innerHTML = (data.users || [])
      .map(
        (u) => `
      <tr>
        <td>${u.username}</td>
        <td>${u.role}</td>
        <td>${u.must_change_password ? "Evet" : "Hayır"}</td>
        <td class="admin-actions">
          <button type="button" class="btn secondary btn-sm" data-reset="${u.id}" data-name="${u.username}">Şifre sıfırla</button>
          ${
            u.id !== currentUser?.id
              ? `<button type="button" class="btn danger btn-sm" data-delete="${u.id}" data-name="${u.username}">Sil</button>`
              : ""
          }
        </td>
      </tr>`
      )
      .join("");

    tbody.querySelectorAll("[data-delete]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const id = btn.dataset.delete;
        const name = btn.dataset.name;
        if (!confirm(`"${name}" kullanıcısı silinsin mi?`)) return;
        const r = await apiFetch(`/api/admin/users/${id}`, { method: "DELETE" });
        if (r.ok) loadAdminUsers();
      });
    });

    tbody.querySelectorAll("[data-reset]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const id = btn.dataset.reset;
        const name = btn.dataset.name;
        const pw = prompt(`${name} için yeni geçici şifre (min 4 karakter):`);
        if (!pw || pw.length < 4) return;
        const r = await apiFetch(`/api/admin/users/${id}/reset-password`, {
          method: "POST",
          body: JSON.stringify({ password: pw }),
        });
        const d = await r.json().catch(() => ({}));
        if (r.ok) {
          alert(d.message || "Şifre sıfırlandı");
          loadAdminUsers();
        } else {
          alert(d.detail || "Hata");
        }
      });
    });
  } catch {
    tbody.innerHTML = '<tr><td colspan="4">Liste yüklenemedi</td></tr>';
  }
}

async function createAdminUser(e) {
  e.preventDefault();
  const status = qs("#adminCreateStatus");
  const username = qs("#newAdminUsername")?.value.trim();
  const password = qs("#newAdminPassword")?.value;
  if (!username || !password) {
    if (status) status.textContent = "Kullanıcı adı ve geçici şifre gerekli.";
    return;
  }
  try {
    const res = await apiFetch("/api/admin/users", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    });
    const data = await res.json();
    if (!res.ok) {
      if (status) status.textContent = data.detail || "Hata";
      return;
    }
    if (status) status.textContent = data.message || "Oluşturuldu";
    qs("#adminCreateUserForm")?.reset();
    loadAdminUsers();
  } catch (err) {
    if (status) status.textContent = err.message;
  }
}

function initAuth() {
  qs("#btnLogout")?.addEventListener("click", logout);
  qs("#changePasswordForm")?.addEventListener("submit", submitChangePassword);
  qs("#tabScan")?.addEventListener("click", () => switchAppTab("scan"));
  qs("#tabTrack")?.addEventListener("click", () => switchAppTab("track"));
  qs("#tabAdmin")?.addEventListener("click", () => switchAppTab("admin"));
  qs("#adminCreateUserForm")?.addEventListener("submit", createAdminUser);

  const currentWrap = qs("#currentPasswordWrap");
  if (currentWrap && currentUser?.must_change_password) {
    currentWrap.hidden = true;
  }
}

async function bootstrapAuth() {
  try {
    await loadSession();
    updateHeaderUser();
    initAuth();
    if (currentUser?.must_change_password) {
      showChangePasswordModal(true);
      qs("#currentPasswordWrap").hidden = true;
    }
  } catch {
    window.location.href = "/login";
  }
}

window.apiFetch = apiFetch;
window.bootstrapAuth = bootstrapAuth;
