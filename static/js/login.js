const $ = (sel) => document.querySelector(sel);

function setLoginStatus(msg, ok = false) {
  const el = $("#loginStatus");
  if (!el) return;
  el.textContent = msg;
  el.className = "auth-status" + (ok ? " ok" : msg ? "" : "");
}

document.getElementById("loginForm")?.addEventListener("submit", async (e) => {
  e.preventDefault();
  setLoginStatus("Giriş yapılıyor…");
  try {
    const res = await fetch("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify({
        username: $("#loginUsername").value.trim(),
        password: $("#loginPassword").value,
      }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      setLoginStatus(data.detail || "Giriş başarısız");
      return;
    }
    window.location.href = "/";
  } catch (err) {
    setLoginStatus("Bağlantı hatası: " + err.message);
  }
});
