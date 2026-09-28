import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.dirname(fileURLToPath(import.meta.url));
const seedPath = path.join(root, "data/hype-seed.json");
const cachePath = path.join(root, "data/.hype-cache.json");

const NEWS_TIMEOUT_MS = 5_000;
const KAP_TIMEOUT_MS = 6_000;
const REDDIT_TIMEOUT_MS = 6_000;
const TRENDS_TIMEOUT_MS = 4_000;
const REDDIT_GAP_MS = 1_600;
const NEWS_CONCURRENCY = 4;
const WEEK_MS = 7 * 24 * 60 * 60 * 1000;
const HYPE_CACHE_MS = 6 * 60 * 60 * 1000;
const UA = "Mozilla/5.0 (compatible; viop-hesaplayici/0.1; +local)";

const seed = fs.existsSync(seedPath)
  ? JSON.parse(fs.readFileSync(seedPath, "utf8"))
  : { kap: {}, news: {}, reddit: {} };

let disk = readDisk();
let redditNextAt = 0;
let redditLiveOk = disk?.redditLiveOk === true;
let redditBlocked = false;
let trendsBlocked = false;
let newsBlocked = false;

function readDisk() {
  try {
    if (!fs.existsSync(cachePath)) return { news: {}, reddit: {}, kap: {}, trends: {} };
    const parsed = JSON.parse(fs.readFileSync(cachePath, "utf8"));
    return {
      news: parsed.news ?? {},
      reddit: parsed.reddit ?? {},
      kap: parsed.kap ?? {},
      trends: parsed.trends ?? {},
      redditLiveOk: Boolean(parsed.redditLiveOk),
      updatedAt: parsed.updatedAt,
    };
  } catch {
    return { news: {}, reddit: {}, kap: {}, trends: {} };
  }
}

function writeDisk() {
  try {
    fs.writeFileSync(
      cachePath,
      JSON.stringify({
        ...disk,
        redditLiveOk,
        updatedAt: new Date().toISOString(),
      }),
    );
  } catch {
    // cache is optional
  }
}

function wait(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function fresh(entry, ttl = HYPE_CACHE_MS) {
  if (!entry || entry.at == null) return false;
  return Date.now() - entry.at < ttl;
}

function hostOf(url) {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return "";
  }
}

function normalizeTitle(title) {
  return String(title ?? "")
    .toLocaleLowerCase("tr-TR")
    .replace(/\s+/g, " ")
    .trim();
}

function withinWeek(unixSeconds) {
  if (!Number.isFinite(unixSeconds) || unixSeconds <= 0) return false;
  const ms = unixSeconds > 10_000_000_000 ? unixSeconds : unixSeconds * 1000;
  return Date.now() - ms <= WEEK_MS;
}

async function fetchJson(url, timeoutMs, headers = {}) {
  const response = await fetch(url, {
    headers: { "User-Agent": UA, Accept: "application/json", ...headers },
    signal: AbortSignal.timeout(timeoutMs),
  });
  if (response.status === 401 || response.status === 403 || response.status === 429) {
    const error = new Error(`HTTP ${response.status}`);
    error.status = response.status;
    throw error;
  }
  if (!response.ok) {
    const error = new Error(`HTTP ${response.status}`);
    error.status = response.status;
    throw error;
  }
  return response.json();
}

export function dedupeNews(items) {
  const seen = new Set();
  const out = [];
  for (const item of items) {
    const title = normalizeTitle(item.title);
    const domain = hostOf(item.link ?? item.url ?? "");
    const key = `${title}|${domain}`;
    if (!title || seen.has(key)) continue;
    seen.add(key);
    out.push(item);
  }
  return out;
}

async function yahooNews(yahooSymbol) {
  if (newsBlocked) return null;
  const cached = disk.news[yahooSymbol];
  if (fresh(cached)) return cached.count;
  const url =
    `https://query1.finance.yahoo.com/v1/finance/search?q=${encodeURIComponent(yahooSymbol)}` +
    `&quotesCount=0&newsCount=25&enableFuzzyQuery=false`;
  try {
    const json = await fetchJson(url, NEWS_TIMEOUT_MS);
    const raw = Array.isArray(json?.news) ? json.news : [];
    const week = raw.filter((item) =>
      withinWeek(Number(item.providerPublishTime ?? item.published_at ?? 0)),
    );
    const count = dedupeNews(
      week.map((item) => ({
        title: item.title,
        link: item.link ?? item.url,
      })),
    ).length;
    disk.news[yahooSymbol] = { count, at: Date.now() };
    return count;
  } catch (error) {
    if (error?.status === 401 || error?.status === 403) newsBlocked = true;
    if (cached?.count != null) return cached.count;
    return null;
  }
}

async function fetchKapBulk() {
  const cached = disk.kap.__bulk;
  if (fresh(cached, 3 * 60 * 60 * 1000) && cached.map) return cached.map;
  const since = Date.now() - WEEK_MS;
  const attempts = [
    "https://www.kap.org.tr/tr/api/disclosures",
    "https://www.kap.org.tr/en/api/disclosures",
  ];
  for (const url of attempts) {
    try {
      const json = await fetchJson(url, KAP_TIMEOUT_MS);
      const rows = Array.isArray(json) ? json : json?.disclosures ?? json?.data ?? [];
      if (!Array.isArray(rows) || rows.length === 0) continue;
      const map = {};
      for (const row of rows) {
        const ticker = String(
          row.stockCode ?? row.ticker ?? row.kod ?? row.memberCode ?? "",
        )
          .replace(/\.IS$/i, "")
          .toUpperCase();
        const published =
          Date.parse(row.publishDate ?? row.disclosureDate ?? row.date ?? "") ||
          Number(row.publishTime ?? 0) * 1000;
        if (!ticker || (published && published < since)) continue;
        map[ticker] = (map[ticker] ?? 0) + 1;
      }
      if (Object.keys(map).length > 0) {
        disk.kap.__bulk = { map, at: Date.now() };
        writeDisk();
        return map;
      }
    } catch {
      // KAP is optional; never block the screener.
    }
  }
  return null;
}

async function mapPool(pool, limit, worker) {
  const out = new Array(pool.length);
  let next = 0;
  async function run() {
    while (next < pool.length) {
      const index = next++;
      out[index] = await worker(pool[index], index);
    }
  }
  await Promise.all(Array.from({ length: Math.min(limit, pool.length) }, () => run()));
  return out;
}

const REDDIT_SUBS = [
  "wallstreetbets",
  "stocks",
  "investing",
  "options",
  "borsaistanbul",
  "yatirim",
];

const REDDIT_SKIP = new Set([
  "THE",
  "AND",
  "FOR",
  "ARE",
  "YOU",
  "ALL",
  "NOW",
  "NEW",
  "DAY",
  "CEO",
  "IPO",
  "ETF",
  "GDP",
  "USA",
  "NOT",
  "BUT",
  "OUT",
  "CAN",
  "ANY",
  "BIG",
  "LOW",
  "TOP",
  "ONE",
  "PUT",
  "BUY",
  "HOLD",
  "CALL",
  "LONG",
  "OPEN",
  "REAL",
  "BEST",
  "HAS",
  "WWW",
  "NEXT",
  "HERE",
  "CASH",
  "GOOD",
  "POST",
  "MOVE",
  "PAY",
  "LOT",
  "PARA",
  "WAY",
  "HAVE",
  "WITH",
  "THIS",
  "THAT",
  "FROM",
  "YOUR",
  "MORE",
  "JUST",
  "LIKE",
  "WILL",
  "BEEN",
  "WERE",
  "THEM",
  "THEN",
  "WHEN",
  "WHAT",
  "MAKE",
  "TAKE",
  "WEEK",
  "YEAR",
  "TIME",
  "HIGH",
  "DOWN",
  "BACK",
  "OVER",
  "ONLY",
  "ALSO",
  "INTO",
  "COST",
  "FREE",
  "LAST",
  "MUCH",
  "WELL",
  "SUCH",
  "BOTH",
  "SAME",
  "EACH",
  "MOST",
  "MUST",
  "NEED",
  "KEEP",
  "GIVE",
  "FIND",
  "SHOW",
  "HELP",
  "PART",
  "CASE",
  "AREA",
  "FACT",
  "VERY",
  "EVEN",
  "STILL",
  "BEING",
  "DOING",
  "GOING",
  "AFTER",
  "BEFORE",
  "ABOUT",
  "THEIR",
  "THERE",
  "WHICH",
  "WOULD",
  "COULD",
  "SHOULD",
  "OTHER",
  "FIRST",
  "THAN",
  "THEN",
  "SOME",
  "THESE",
  "THOSE",
  "TECH",
  "LINE",
  "EVER",
  "MIND",
  "PLAY",
  "FUND",
  "LIFE",
  "LIVE",
  "GAME",
  "GROW",
  "HOUR",
  "SAFE",
  "LOVE",
  "HOPE",
  "RISK",
  "TRUE",
  "PLAN",
  "RATE",
  "GAIN",
  "LOSS",
  "BULL",
  "BEAR",
]);

function mentionTickers(text, known) {
  const counts = {};
  const upper = String(text ?? "").toUpperCase();
  if (!upper) return counts;
  for (const match of upper.matchAll(/\$([A-Z]{1,6})\b/g)) {
    const ticker = match[1];
    if (!known.has(ticker) || REDDIT_SKIP.has(ticker)) continue;
    counts[ticker] = (counts[ticker] ?? 0) + 1;
  }
  for (const match of upper.matchAll(/(^|[^A-Z0-9])([A-Z]{4,6})(?=[^A-Z0-9]|$)/g)) {
    const ticker = match[2];
    if (!known.has(ticker) || REDDIT_SKIP.has(ticker)) continue;
    counts[ticker] = (counts[ticker] ?? 0) + 1;
  }
  return counts;
}

async function fetchSubredditPosts(subreddit) {
  const cached = disk.reddit[`__sub_${subreddit}`];
  if (fresh(cached, 3 * 60 * 60 * 1000) && Array.isArray(cached.posts)) {
    return cached.posts;
  }
  const waitFor = redditNextAt - Date.now();
  if (waitFor > 0) await wait(waitFor);
  redditNextAt = Date.now() + REDDIT_GAP_MS;
  const url =
    `https://arctic-shift.photon-reddit.com/api/posts/search?subreddit=${encodeURIComponent(subreddit)}` +
    `&limit=100`;
  const json = await fetchJson(url, REDDIT_TIMEOUT_MS);
  const rows = Array.isArray(json?.data) ? json.data : [];
  const posts = rows
    .filter((row) => withinWeek(Number(row.created_utc ?? row.created ?? 0)))
    .map((row) => `${row.title ?? ""}\n${row.selftext ?? ""}`);
  disk.reddit[`__sub_${subreddit}`] = { posts, at: Date.now() };
  return posts;
}

async function redditBulkCounts(tickers) {
  const known = new Set(
    tickers.filter((ticker) => ticker && !REDDIT_SKIP.has(ticker)),
  );
  const counts = {};
  let gotAny = false;
  for (const subreddit of REDDIT_SUBS) {
    try {
      const posts = await fetchSubredditPosts(subreddit);
      if (posts.length === 0) continue;
      gotAny = true;
      for (const text of posts) {
        const found = mentionTickers(text, known);
        for (const [ticker, n] of Object.entries(found)) {
          counts[ticker] = (counts[ticker] ?? 0) + n;
        }
      }
    } catch {
      // try the next subreddit; one 403/timeout must not freeze Reddit
    }
  }
  if (!gotAny) {
    redditBlocked = true;
    return null;
  }
  redditBlocked = false;
  redditLiveOk = true;
  writeDisk();
  return counts;
}

async function trendsScoreFor(ticker) {
  if (trendsBlocked) return null;
  const cached = disk.trends[ticker];
  if (fresh(cached)) return cached.score ?? null;
  const key = process.env.SERPAPI_KEY || process.env.GOOGLE_TRENDS_API_KEY;
  if (key) {
    try {
      const url =
        `https://serpapi.com/search.json?engine=google_trends&q=${encodeURIComponent(ticker)}` +
        `&data_type=TIMESERIES&api_key=${encodeURIComponent(key)}`;
      const json = await fetchJson(url, TRENDS_TIMEOUT_MS);
      const timeline = json?.interest_over_time?.timeline_data ?? [];
      const last7 = timeline.slice(-7);
      const values = last7
        .map((row) => Number(row.values?.[0]?.extracted_value ?? row.value ?? 0))
        .filter((value) => Number.isFinite(value));
      const score = values.length ? values.reduce((a, b) => a + b, 0) / values.length : 0;
      disk.trends[ticker] = { score, at: Date.now() };
      writeDisk();
      return score;
    } catch {
      trendsBlocked = true;
      return null;
    }
  }
  try {
    const url =
      `https://trends.google.com/trends/api/explore?hl=tr&tz=-180&req=${encodeURIComponent(
        JSON.stringify({
          comparisonItem: [{ keyword: ticker, geo: "", time: "now 7-d" }],
          category: 0,
          property: "",
        }),
      )}`;
    const response = await fetch(url, {
      headers: { "User-Agent": UA },
      signal: AbortSignal.timeout(TRENDS_TIMEOUT_MS),
    });
    if (!response.ok) {
      trendsBlocked = true;
      disk.trends[ticker] = { score: null, at: Date.now() };
      return null;
    }
    // Unofficial explore payload is widget metadata, not a usable 7d series here.
    trendsBlocked = true;
    disk.trends[ticker] = { score: null, at: Date.now() };
    return null;
  } catch {
    trendsBlocked = true;
    return null;
  }
}

function kapFallback(ticker) {
  const n = seed.kap?.[ticker];
  return Number.isFinite(n) ? n : 0;
}

function newsFallback(ticker) {
  const n = seed.news?.[ticker];
  return Number.isFinite(n) ? n : null;
}

function applyKap(row, kapMap, kapOk) {
  if (row.exchange === "bist" || !row.exchange) {
    row.kapCount = kapOk ? (kapMap[row.ticker] ?? 0) : kapFallback(row.ticker);
  } else {
    row.kapCount = null;
  }
}

function markRedditUnavailable(row) {
  const cached = disk.reddit[row.ticker];
  if (cached?.live && cached.count != null) {
    row.redditCount = cached.count;
    row.redditStatus = "ok";
    return;
  }
  row.redditCount = null;
  row.redditStatus = "unavailable";
}

/**
 * Enrich already-fetched chart rows with 7d attention fields.
 * Charts stay first: this is called on a snapshot copy and must not throw.
 * Reddit is filled from a bulk 7d subreddit scan so ~5600 names never wait on per-ticker search.
 */
export async function enrichHype(rows, namesByTicker, options = {}) {
  const newsLimit = options.newsLimit ?? 250;
  const redditLimit = options.redditLimit ?? 36;
  const kapMap = (await fetchKapBulk()) ?? null;
  const kapOk = Boolean(kapMap);

  for (const row of rows) applyKap(row, kapMap, kapOk);

  const redditCounts = await redditBulkCounts(rows.map((row) => row.ticker));
  if (redditCounts) {
    for (const row of rows) {
      const count = redditCounts[row.ticker];
      if (count != null && count > 0) {
        row.redditCount = count;
        row.redditStatus = "ok";
        disk.reddit[row.ticker] = { count, at: Date.now(), live: true };
      } else {
        row.redditCount = null;
        row.redditStatus = "ok";
      }
    }
  } else {
    for (const row of rows) markRedditUnavailable(row);
  }

  const trendTargets = rows.slice(0, Math.min(24, redditLimit));
  for (const row of trendTargets) {
    if (trendsBlocked) break;
    row.trendsScore = await trendsScoreFor(row.ticker);
  }
  for (const row of rows) {
    if (row.redditStatus == null) markRedditUnavailable(row);
    if (row.trendsScore === undefined) row.trendsScore = null;
  }

  const newsTargets = rows.slice(0, newsLimit);
  await mapPool(newsTargets, NEWS_CONCURRENCY, async (row) => {
    const yahoo =
      row.exchange === "bist" || !row.exchange ? `${row.ticker}.IS` : row.ticker;
    const news = await yahooNews(yahoo);
    row.newsCount = news != null ? news : newsFallback(row.ticker);
    row.newsStatus = newsBlocked && row.newsCount == null ? "unavailable" : "ok";
  });

  for (const row of rows) {
    if (row.newsCount == null) {
      const seeded = newsFallback(row.ticker);
      if (seeded != null) {
        row.newsCount = seeded;
        row.newsStatus = "ok";
      }
    }
  }

  writeDisk();
  return {
    reddit: redditBlocked && !redditLiveOk ? "unavailable" : redditLiveOk ? "ok" : "unavailable",
    news: newsBlocked ? "unavailable" : "ok",
    kap: kapOk ? "ok" : "seed",
    trends: trendsBlocked ? "unavailable" : "ok",
  };
}

export function applyHypeSeed(row) {
  if (row.newsCount == null && seed.news?.[row.ticker] != null) {
    row.newsCount = seed.news[row.ticker];
    row.newsStatus = "ok";
  }
  if ((row.exchange === "bist" || !row.exchange) && row.kapCount == null) {
    row.kapCount = kapFallback(row.ticker);
  }
  if (row.redditCount == null) {
    row.redditStatus = row.redditStatus ?? "unavailable";
  }
  return row;
}

export function hypeStatus() {
  return {
    reddit: redditBlocked && !redditLiveOk ? "unavailable" : redditLiveOk ? "ok" : "pending",
    news: newsBlocked ? "unavailable" : "ok",
    trends: trendsBlocked ? "unavailable" : "pending",
  };
}
