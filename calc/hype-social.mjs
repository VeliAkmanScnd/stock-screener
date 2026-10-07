/**
 * Social hype for BIST: X (Twitter) Basic recent-search + Telegram public channels.
 * Growth = today_count / max(avg_prior_7d, 1). Missing sources stay null (not 0).
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.dirname(fileURLToPath(import.meta.url));
const historyPath = path.join(root, "data/.social-hype-history.json");
const channelsPath = path.join(root, "data/telegram-hype-channels.json");

const DAY_MS = 24 * 60 * 60 * 1000;
const X_GAP_MS = 1_200;
const X_TIMEOUT_MS = 12_000;
const TG_TIMEOUT_MS = 10_000;
const TG_GAP_MS = 400;
const UA =
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36";

/** Basic ~10k reads/mo — keep daily BIST budget modest. */
const DEFAULT_X_LIMIT = 80;
const SHORT_TICKER_MAX = 3;

let xBlocked = false;
let xLiveOk = false;
let tgLiveOk = false;
let xNextAt = 0;

function wait(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function dayKey(d = new Date()) {
  return d.toISOString().slice(0, 10);
}

function readJson(file, fallback) {
  try {
    if (!fs.existsSync(file)) return fallback;
    return JSON.parse(fs.readFileSync(file, "utf8"));
  } catch {
    return fallback;
  }
}

function writeJson(file, value) {
  try {
    fs.writeFileSync(file, `${JSON.stringify(value, null, 2)}\n`);
  } catch {
    // optional cache
  }
}

function loadHistory() {
  const raw = readJson(historyPath, { twitter: {}, telegram: {} });
  return {
    twitter: raw.twitter ?? {},
    telegram: raw.telegram ?? {},
  };
}

function saveHistory(history) {
  writeJson(historyPath, {
    ...history,
    updatedAt: new Date().toISOString(),
  });
}

function pushDayCount(series, day, count) {
  const list = Array.isArray(series) ? [...series] : [];
  const idx = list.findIndex((row) => row.day === day);
  const row = { day, count: Number(count) || 0 };
  if (idx >= 0) list[idx] = row;
  else list.push(row);
  list.sort((a, b) => a.day.localeCompare(b.day));
  return list.slice(-14);
}

function growthFromSeries(series, today) {
  const list = Array.isArray(series) ? series : [];
  const todayRow = list.find((row) => row.day === today);
  const todayCount = todayRow ? Number(todayRow.count) || 0 : null;
  if (todayCount == null) return { count: null, growth: null };
  const prior = list
    .filter((row) => row.day < today)
    .slice(-7)
    .map((row) => Number(row.count) || 0);
  if (prior.length === 0) {
    // First observation: treat raw count as weak signal (growth = count, capped later via percentile).
    return { count: todayCount, growth: todayCount > 0 ? todayCount : null };
  }
  const avg = prior.reduce((a, b) => a + b, 0) / prior.length;
  const growth = todayCount / Math.max(avg, 1);
  return { count: todayCount, growth };
}

function xBearer() {
  return String(process.env.X_BEARER_TOKEN || process.env.TWITTER_BEARER_TOKEN || "").trim();
}

function xQueryFor(ticker) {
  const t = String(ticker || "")
    .trim()
    .toUpperCase();
  if (!t) return "";
  // Short tickers are noisy as bare hashtags — prefer cashtag + hashtag with word context.
  if (t.length <= SHORT_TICKER_MAX) {
    return `($${t} OR #${t}) (hisse OR borsa OR bist OR viop) lang:tr -is:retweet`;
  }
  return `(#${t} OR $${t}) lang:tr -is:retweet`;
}

async function xRecentCount(ticker) {
  const token = xBearer();
  if (!token || xBlocked) return null;
  const waitFor = xNextAt - Date.now();
  if (waitFor > 0) await wait(waitFor);
  xNextAt = Date.now() + X_GAP_MS;

  const end = new Date();
  const start = new Date(end.getTime() - DAY_MS);
  const query = xQueryFor(ticker);
  const url =
    `https://api.twitter.com/2/tweets/search/recent?` +
    `query=${encodeURIComponent(query)}` +
    `&max_results=100` +
    `&start_time=${encodeURIComponent(start.toISOString())}` +
    `&end_time=${encodeURIComponent(end.toISOString())}`;

  try {
    const response = await fetch(url, {
      headers: {
        Authorization: `Bearer ${token}`,
        "User-Agent": UA,
      },
      signal: AbortSignal.timeout(X_TIMEOUT_MS),
    });
    if (response.status === 401 || response.status === 403) {
      xBlocked = true;
      return null;
    }
    if (response.status === 429) {
      xBlocked = true;
      return null;
    }
    if (!response.ok) return null;
    const json = await response.json();
    let count = Array.isArray(json?.data) ? json.data.length : 0;
    // One page is enough for Basic budget; meta.result_count is page-local.
    // If next_token exists and page is full, treat as 100+ (cap signal).
    if (json?.meta?.next_token && count >= 100) count = 100;
    xLiveOk = true;
    return count;
  } catch {
    return null;
  }
}

function loadTelegramChannels() {
  const raw = readJson(channelsPath, { channels: [] });
  const list = Array.isArray(raw.channels) ? raw.channels : [];
  return [
    ...new Set(
      list
        .map((c) => String(c || "").trim().replace(/^@/, ""))
        .filter((c) => /^[A-Za-z0-9_]{3,64}$/.test(c)),
    ),
  ];
}

function extractTelegramMessages(html) {
  const out = [];
  const blocks = String(html).split('class="tgme_widget_message');
  for (let i = 1; i < blocks.length; i++) {
    const block = blocks[i];
    const timeMatch = block.match(/datetime="([^"]+)"/);
    const textMatch = block.match(
      /tgme_widget_message_text[^>]*>([\s\S]*?)<\/div>/i,
    );
    if (!timeMatch) continue;
    const at = Date.parse(timeMatch[1]);
    if (!Number.isFinite(at)) continue;
    const text = String(textMatch?.[1] ?? "")
      .replace(/<[^>]+>/g, " ")
      .replace(/&nbsp;/g, " ")
      .replace(/\s+/g, " ")
      .trim();
    out.push({ at, text });
  }
  return out;
}

async function fetchTelegramChannelMessages(channel) {
  const url = `https://t.me/s/${encodeURIComponent(channel)}`;
  const response = await fetch(url, {
    headers: { "User-Agent": UA, Accept: "text/html" },
    signal: AbortSignal.timeout(TG_TIMEOUT_MS),
  });
  if (!response.ok) return [];
  const html = await response.text();
  return extractTelegramMessages(html);
}

function countTickersInText(text, tickers) {
  const upper = String(text || "").toLocaleUpperCase("tr-TR");
  const hits = {};
  for (const ticker of tickers) {
    const t = ticker.toUpperCase();
    // Word-ish boundary: avoid matching inside longer tokens.
    const re = new RegExp(`(?:^|[^A-Z0-9])#?${t}(?:[^A-Z0-9]|$)`);
    if (re.test(upper) || upper.includes(`$${t}`)) {
      hits[t] = (hits[t] ?? 0) + 1;
    }
  }
  return hits;
}

async function telegramBulkCounts(tickers) {
  const channels = loadTelegramChannels();
  if (channels.length === 0) return null;
  const since = Date.now() - DAY_MS;
  const wanted = new Set(tickers.map((t) => String(t).toUpperCase()));
  const totals = {};
  let any = false;
  for (const channel of channels) {
    try {
      const messages = await fetchTelegramChannelMessages(channel);
      await wait(TG_GAP_MS);
      const recent = messages.filter((m) => m.at >= since);
      if (recent.length === 0) continue;
      any = true;
      for (const msg of recent) {
        const hits = countTickersInText(msg.text, wanted);
        for (const [ticker, n] of Object.entries(hits)) {
          totals[ticker] = (totals[ticker] ?? 0) + n;
        }
      }
    } catch {
      // keep going; one channel must not kill the batch
    }
  }
  if (!any) return null;
  tgLiveOk = true;
  // Ensure every requested ticker has a key (0 = scanned, no mention).
  for (const t of wanted) {
    if (totals[t] == null) totals[t] = 0;
  }
  return totals;
}

/**
 * Enrich BIST (and limited) rows with twitter/telegram counts + growth.
 */
export async function enrichSocialHype(rows, options = {}) {
  const xLimit = options.xLimit ?? DEFAULT_X_LIMIT;
  const today = dayKey();
  const history = loadHistory();

  const bistRows = rows.filter(
    (row) => row.exchange === "bist" || !row.exchange,
  );
  const xTargets = bistRows.slice(0, xLimit);

  // --- Telegram first (cheap, bulk) ---
  const tgCounts = await telegramBulkCounts(bistRows.map((r) => r.ticker));
  if (tgCounts) {
    for (const row of bistRows) {
      const count = tgCounts[row.ticker] ?? 0;
      history.telegram[row.ticker] = pushDayCount(
        history.telegram[row.ticker],
        today,
        count,
      );
      const { count: c, growth } = growthFromSeries(
        history.telegram[row.ticker],
        today,
      );
      row.telegramCount = c;
      row.telegramGrowth = growth;
      row.telegramStatus = "ok";
    }
  } else {
    for (const row of bistRows) {
      const series = history.telegram[row.ticker];
      const { count, growth } = growthFromSeries(series, today);
      if (count != null) {
        row.telegramCount = count;
        row.telegramGrowth = growth;
        row.telegramStatus = "ok";
      } else {
        row.telegramCount = null;
        row.telegramGrowth = null;
        row.telegramStatus = "unavailable";
      }
    }
  }

  // --- X Basic recent search (rate-limited) ---
  const token = xBearer();
  if (!token) {
    for (const row of rows) {
      row.twitterCount = null;
      row.twitterGrowth = null;
      row.twitterStatus = "unavailable";
    }
  } else {
    for (const row of xTargets) {
      if (xBlocked) break;
      const count = await xRecentCount(row.ticker);
      if (count == null) {
        const series = history.twitter[row.ticker];
        const g = growthFromSeries(series, today);
        row.twitterCount = g.count;
        row.twitterGrowth = g.growth;
        row.twitterStatus = g.count != null ? "ok" : "unavailable";
        continue;
      }
      history.twitter[row.ticker] = pushDayCount(
        history.twitter[row.ticker],
        today,
        count,
      );
      const g = growthFromSeries(history.twitter[row.ticker], today);
      row.twitterCount = g.count;
      row.twitterGrowth = g.growth;
      row.twitterStatus = "ok";
    }
    for (const row of rows) {
      if (row.twitterStatus != null) continue;
      const g = growthFromSeries(history.twitter[row.ticker], today);
      if (g.count != null) {
        row.twitterCount = g.count;
        row.twitterGrowth = g.growth;
        row.twitterStatus = "ok";
      } else {
        row.twitterCount = null;
        row.twitterGrowth = null;
        row.twitterStatus = "unavailable";
      }
    }
  }

  // Non-BIST: leave telegram null; twitter only if already set.
  for (const row of rows) {
    if (row.exchange && row.exchange !== "bist") {
      if (row.telegramStatus == null) {
        row.telegramCount = null;
        row.telegramGrowth = null;
        row.telegramStatus = "unavailable";
      }
      if (row.twitterStatus == null) {
        row.twitterCount = null;
        row.twitterGrowth = null;
        row.twitterStatus = "unavailable";
      }
    }
  }

  saveHistory(history);
  return {
    twitter: !token
      ? "unavailable"
      : xBlocked && !xLiveOk
        ? "unavailable"
        : xLiveOk
          ? "ok"
          : "unavailable",
    telegram: tgLiveOk
      ? "ok"
      : loadTelegramChannels().length === 0
        ? "unavailable"
        : "unavailable",
    xLimit: xTargets.length,
    telegramChannels: loadTelegramChannels().length,
  };
}

export function socialHypeStatus() {
  return {
    twitter: !xBearer()
      ? "unavailable"
      : xBlocked && !xLiveOk
        ? "unavailable"
        : xLiveOk
          ? "ok"
          : "pending",
    telegram: tgLiveOk
      ? "ok"
      : loadTelegramChannels().length === 0
        ? "unavailable"
        : "pending",
  };
}
