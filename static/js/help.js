function helpEsc(s) {
  return String(s ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function helpInline(text) {
  let out = helpEsc(text);
  out = out.replace(/`([^`]+)`/g, "<code>$1</code>");
  out = out.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  return out;
}

function renderHelpMarkdown(md) {
  const lines = String(md || "").replace(/\r\n/g, "\n").split("\n");
  const html = [];
  let i = 0;
  const flushList = (items, tag) => {
    if (!items.length) return;
    html.push(`<${tag}>${items.join("")}</${tag}>`);
    items.length = 0;
  };
  const ul = [];
  const ol = [];

  while (i < lines.length) {
    const line = lines[i];
    if (line.startsWith("```")) {
      flushList(ul, "ul");
      flushList(ol, "ol");
      const buf = [];
      i += 1;
      while (i < lines.length && !lines[i].startsWith("```")) {
        buf.push(helpEsc(lines[i]));
        i += 1;
      }
      html.push(`<pre><code>${buf.join("\n")}</code></pre>`);
      i += 1;
      continue;
    }
    if (line.startsWith("|")) {
      flushList(ul, "ul");
      flushList(ol, "ol");
      const rows = [];
      while (i < lines.length && lines[i].startsWith("|")) {
        rows.push(lines[i]);
        i += 1;
      }
      const parsed = rows
        .filter((r) => !/^\|\s*:?-{3,}/.test(r.replace(/\|/g, "|")))
        .filter((r) => !r.split("|").every((c) => /^[\s:-]*$/.test(c)));
      if (parsed.length) {
        const cells = (row) =>
          row
            .split("|")
            .slice(1, -1)
            .map((c) => c.trim());
        const head = cells(parsed[0]);
        const body = parsed.slice(1);
        html.push("<table class=\"help-table\"><thead><tr>");
        head.forEach((c) => html.push(`<th>${helpInline(c)}</th>`));
        html.push("</tr></thead><tbody>");
        body.forEach((row) => {
          html.push("<tr>");
          cells(row).forEach((c) => html.push(`<td>${helpInline(c)}</td>`));
          html.push("</tr>");
        });
        html.push("</tbody></table>");
      }
      continue;
    }
    const ulMatch = line.match(/^[-*] (.+)$/);
    if (ulMatch) {
      flushList(ol, "ol");
      ul.push(`<li>${helpInline(ulMatch[1])}</li>`);
      i += 1;
      continue;
    }
    const olMatch = line.match(/^\d+\. (.+)$/);
    if (olMatch) {
      flushList(ul, "ul");
      ol.push(`<li>${helpInline(olMatch[1])}</li>`);
      i += 1;
      continue;
    }
    flushList(ul, "ul");
    flushList(ol, "ol");
    if (!line.trim()) {
      i += 1;
      continue;
    }
    if (line.startsWith("### ")) {
      html.push(`<h3>${helpInline(line.slice(4))}</h3>`);
    } else if (line.startsWith("## ")) {
      html.push(`<h2>${helpInline(line.slice(3))}</h2>`);
    } else if (line.startsWith("# ")) {
      html.push(`<h1>${helpInline(line.slice(2))}</h1>`);
    } else if (/^---+$/.test(line.trim())) {
      html.push("<hr />");
    } else {
      html.push(`<p>${helpInline(line)}</p>`);
    }
    i += 1;
  }
  flushList(ul, "ul");
  flushList(ol, "ol");
  return html.join("\n");
}

let helpTopics = [];
let helpActiveId = "";

function renderHelpNav() {
  const nav = document.querySelector("#helpTopicList");
  if (!nav) return;
  nav.innerHTML = helpTopics
    .map((t) => {
      const active = t.id === helpActiveId ? " active" : "";
      return `<button type="button" class="help-topic-btn${active}" data-help-id="${t.id}">
        <strong>${helpEsc(t.title)}</strong>
        <span>${helpEsc(t.summary || "")}</span>
      </button>`;
    })
    .join("");
  nav.querySelectorAll("[data-help-id]").forEach((btn) => {
    btn.addEventListener("click", () => loadHelpTopic(btn.dataset.helpId));
  });
}

async function loadHelpTopic(id) {
  const article = document.querySelector("#helpArticle");
  const title = document.querySelector("#helpArticleTitle");
  const dl = document.querySelector("#helpDownloadOne");
  helpActiveId = id;
  renderHelpNav();
  if (article) article.innerHTML = "<p class=\"hint\">Yükleniyor…</p>";
  try {
    const res = await apiFetch(`/api/help/topics/${id}`);
    const data = await res.json();
    if (!res.ok) {
      if (article) article.innerHTML = `<p class="hint">${helpEsc(data.detail || "Yüklenemedi")}</p>`;
      return;
    }
    if (title) title.textContent = data.title || "Döküman";
    if (dl) {
      dl.href = data.download_url || `/api/help/topics/${id}/download`;
      dl.setAttribute("download", `tradelabtr-${id}.md`);
    }
    if (article) article.innerHTML = renderHelpMarkdown(data.markdown || "");
  } catch (err) {
    if (article) article.innerHTML = `<p class="hint">${helpEsc(err.message)}</p>`;
  }
}

async function loadHelpTopics() {
  const nav = document.querySelector("#helpTopicList");
  try {
    const res = await apiFetch("/api/help/topics");
    const data = await res.json();
    helpTopics = data.topics || [];
    renderHelpNav();
    const start = helpActiveId || helpTopics[0]?.id;
    if (start) await loadHelpTopic(start);
  } catch (err) {
    if (nav) nav.innerHTML = `<p class="hint">${helpEsc(err.message)}</p>`;
  }
}

function onHelpTabShown() {
  if (!helpTopics.length) loadHelpTopics();
}

function initHelpPanel() {
  document.querySelector("#helpDownloadAll")?.addEventListener("click", (e) => {
    e.preventDefault();
    window.location.href = "/api/help/download.zip";
  });
}

document.addEventListener("DOMContentLoaded", initHelpPanel);
