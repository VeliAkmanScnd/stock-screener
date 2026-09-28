import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { fetchUsListings } from "./scripts/us-listings.mjs";
import { applyHypeSeed, enrichHype } from "./hype-api.mjs";

const root = path.dirname(fileURLToPath(import.meta.url));
const listingsFallback = path.join(root, "data/us-listings.json");
const seedPath = path.join(root, "data/us-screener.json");
const cachePath = path.join(root, "data/.screener-cache.json");

const bistTickers = JSON.parse(
  fs.readFileSync(path.join(root, "data/screener-tickers.json"), "utf8"),
);
const seedUs = fs.existsSync(seedPath)
  ? JSON.parse(fs.readFileSync(seedPath, "utf8"))
  : [];

const CACHE_MS = 10 * 60 * 1000;
const CACHE_VERSION = 4;
const BIST_CONCURRENCY = 12;
const US_CONCURRENCY = 16;
const CHART_TIMEOUT_MS = 8_000;

let snapshot = readDiskCache();
let refresh = null;

function readDiskCache() {
  try {
    if (!fs.existsSync(cachePath)) return null;
    const parsed = JSON.parse(fs.readFileSync(cachePath, "utf8"));
    if (!parsed?.names || !Array.isArray(parsed.rows)) return null;
    if (parsed.version !== CACHE_VERSION) return null;
    return parsed;
  } catch {
    return null;
  }
}

function writeDiskCache(payload) {
  try {
    fs.writeFileSync(cachePath, JSON.stringify(payload));
  } catch {
    // cache is optional
  }
}

function mean(values) {
  return values.reduce((sum, value) => sum + value, 0) / values.length;
}

function sampleStdev(values) {
  if (values.length < 2) return 0;
  const avg = mean(values);
  const variance =
    values.reduce((sum, value) => sum + (value - avg) ** 2, 0) / (values.length - 1);
  return Math.sqrt(variance);
}

function postHypeForwardReturns(usable) {
  if (usable.length < 12) return { d1: null, d5: null };
  const n = usable.length;
  const earliest = Math.max(6, n - 31);
  let spike = -1;
  for (let i = n - 2; i >= earliest; i--) {
    const lookback = usable.slice(Math.max(0, i - 20), i);
    if (lookback.length < 5 || !(usable[i - 1].close > 0)) continue;
    const avgVol = mean(lookback.map((bar) => bar.close * Math.max(0, bar.volume)));
    const dayVol = usable[i].close * Math.max(0, usable[i].volume);
    const relative = avgVol > 0 ? dayVol / avgVol : 0;
    const absReturns = [];
    for (let j = 1; j < lookback.length; j++) {
      absReturns.push(Math.abs(Math.log(lookback[j].close / lookback[j - 1].close)));
    }
    const meanAbs = absReturns.length > 0 ? mean(absReturns) : 0;
    const dayRet = Math.abs(Math.log(usable[i].close / usable[i - 1].close));
    if (relative >= 2 || (meanAbs > 0 && dayRet >= 2 * meanAbs)) {
      spike = i;
      break;
    }
  }
  if (spike < 0) return { d1: null, d5: null };
  const px = usable[spike].close;
  if (!(px > 0)) return { d1: null, d5: null };
  return {
    d1: spike + 1 < n ? (usable[spike + 1].close / px - 1) * 100 : null,
    d5: spike + 5 < n ? (usable[spike + 5].close / px - 1) * 100 : null,
  };
}

function statsFromBars(item, bars) {
  const usable = bars.filter(
    (bar) => Number.isFinite(bar.close) && bar.close > 0 && Number.isFinite(bar.volume),
  );
  if (usable.length < 6) return null;
  const window = usable.slice(-21);
  const notionals = window.map((bar) => bar.close * Math.max(0, bar.volume));
  const returns = [];
  for (let i = 1; i < window.length; i++) {
    returns.push(Math.log(window[i].close / window[i - 1].close));
  }
  if (returns.length < 5) return null;
  const last = window[window.length - 1];
  const avgVolumeTl = mean(notionals);
  const lastVolumeTl = last.close * Math.max(0, last.volume);
  const shortAbs = mean(returns.slice(-5).map((value) => Math.abs(value)));
  const longAbs = mean(returns.map((value) => Math.abs(value)));
  const fwd = postHypeForwardReturns(usable);
  return {
    ticker: item.ticker,
    avgVolumeTl,
    lastVolumeTl,
    volatility: sampleStdev(returns) * Math.sqrt(252) * 100,
    dailyMove: longAbs * 100,
    lastPrice: last.close,
    marketCap: 0,
    exchange: item.exchange,
    currency: item.currency,
    relativeVolume: avgVolumeTl > 0 ? lastVolumeTl / avgVolumeTl : null,
    shock: longAbs > 0 ? shortAbs / longAbs : null,
    postHypeReturn1d: fwd.d1,
    postHypeReturn5d: fwd.d5,
    newsCount: null,
    kapCount: null,
    redditCount: null,
    redditStatus: "unavailable",
    trendsScore: null,
  };
}

async function fetchMarketCap(yahoo) {
  const url = `https://query1.finance.yahoo.com/ws/fundamentals-timeseries/v1/finance/timeseries/${encodeURIComponent(yahoo)}?type=trailingMarketCap&period1=1600000000&period2=2000000000`;
  try {
    const response = await fetch(url, {
      headers: { "User-Agent": "Mozilla/5.0" },
      signal: AbortSignal.timeout(CHART_TIMEOUT_MS),
    });
    if (!response.ok) return 0;
    const json = await response.json();
    const series = json?.timeseries?.result?.[0]?.trailingMarketCap;
    if (!Array.isArray(series) || series.length === 0) return 0;
    const raw = series[series.length - 1]?.reportedValue?.raw;
    return Number.isFinite(raw) && raw > 0 ? raw : 0;
  } catch {
    return 0;
  }
}

async function fetchChart(item) {
  const url = `https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(item.yahoo)}?range=3mo&interval=1d`;
  const [response, marketCap] = await Promise.all([
    fetch(url, {
      headers: { "User-Agent": "Mozilla/5.0" },
      signal: AbortSignal.timeout(CHART_TIMEOUT_MS),
    }),
    fetchMarketCap(item.yahoo),
  ]);
  if (response.status === 429) {
    await new Promise((resolve) => setTimeout(resolve, 1500));
    throw new Error("HTTP 429");
  }
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  const json = await response.json();
  const result = json?.chart?.result?.[0];
  const quote = result?.indicators?.quote?.[0];
  if (!quote?.close || !quote?.volume) throw new Error("empty chart");
  const bars = quote.close
    .map((close, index) => ({ close, volume: quote.volume[index] }))
    .filter((bar) => bar.close != null && bar.volume != null);
  const stats = statsFromBars(item, bars);
  if (!stats) return null;
  stats.marketCap = marketCap;
  return stats;
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

function prioritizeUs(listings) {
  const seedOrder = new Map(seedUs.map((row, index) => [row.ticker, index]));
  return [...listings].sort((a, b) => {
    const left = seedOrder.has(a.ticker) ? seedOrder.get(a.ticker) : Number.MAX_SAFE_INTEGER;
    const right = seedOrder.has(b.ticker) ? seedOrder.get(b.ticker) : Number.MAX_SAFE_INTEGER;
    if (left !== right) return left - right;
    return a.ticker.localeCompare(b.ticker);
  });
}

function payloadFrom(parts) {
  return {
    version: CACHE_VERSION,
    updatedAt: parts.updatedAt,
    source: "yahoo",
    window: "20g",
    complete: Boolean(parts.complete),
    names: parts.names ?? { nasdaq: [], nyse: [] },
    rows: parts.rows ?? [],
    hype: parts.hype ?? null,
  };
}

function publish(parts) {
  snapshot = payloadFrom({
    ...snapshot,
    ...parts,
    names: parts.names ?? snapshot?.names,
    rows: parts.rows ?? snapshot?.rows,
    hype: parts.hype ?? snapshot?.hype,
  });
  writeDiskCache(snapshot);
}

async function loadExchange(items, concurrency, onChunk) {
  const collected = [];
  const chunkSize = 64;
  for (let start = 0; start < items.length; start += chunkSize) {
    const slice = items.slice(start, start + chunkSize);
    const results = await mapPool(slice, concurrency, async (item) => {
      try {
        return await fetchChart(item);
      } catch {
        return null;
      }
    });
    collected.push(...results.filter(Boolean).map(applyHypeSeed));
    onChunk(collected);
  }
  return collected;
}

function namesByTicker(listings) {
  const map = new Map();
  for (const row of listings) map.set(row.ticker, row.name);
  for (const row of seedUs) {
    if (row.ticker && row.name) map.set(row.ticker, row.name);
  }
  return map;
}

function prioritizeHype(rows) {
  const seedOrder = new Set(seedUs.map((row) => row.ticker));
  return [...rows].sort((a, b) => {
    const aBist = a.exchange === "bist" || !a.exchange ? 0 : 1;
    const bBist = b.exchange === "bist" || !b.exchange ? 0 : 1;
    if (aBist !== bBist) return aBist - bBist;
    const aSeed = seedOrder.has(a.ticker) ? 0 : 1;
    const bSeed = seedOrder.has(b.ticker) ? 0 : 1;
    if (aSeed !== bSeed) return aSeed - bSeed;
    return (b.avgVolumeTl || 0) - (a.avgVolumeTl || 0);
  });
}

async function refreshAll() {
  const listings = await fetchUsListings(listingsFallback);
  const names = {
    nasdaq: listings
      .filter((row) => row.exchange === "nasdaq")
      .map((row) => ({ ticker: row.ticker, name: row.name })),
    nyse: listings
      .filter((row) => row.exchange === "nyse")
      .map((row) => ({ ticker: row.ticker, name: row.name })),
  };
  const nameLookup = namesByTicker(listings);
  publish({
    names,
    rows: snapshot?.rows ?? [],
    complete: false,
    updatedAt: snapshot?.updatedAt ?? new Date().toISOString(),
  });

  const bistItems = bistTickers.map((ticker) => ({
    ticker,
    yahoo: `${ticker}.IS`,
    exchange: "bist",
    currency: "TL",
  }));
  const usItems = prioritizeUs(listings);

  const bistRows = await loadExchange(bistItems, BIST_CONCURRENCY, (rows) => {
    const usExisting = (snapshot?.rows ?? []).filter((row) => row.exchange !== "bist");
    publish({
      names,
      rows: [...rows, ...usExisting],
      complete: false,
      updatedAt: new Date().toISOString(),
    });
  });

  const bistHype = enrichHype(prioritizeHype(bistRows), nameLookup, {
    newsLimit: 180,
    redditLimit: 20,
  })
    .then((hype) => {
      const usExisting = (snapshot?.rows ?? []).filter((row) => row.exchange !== "bist");
      publish({
        names,
        rows: [...bistRows, ...usExisting],
        complete: false,
        hype,
        updatedAt: new Date().toISOString(),
      });
    })
    .catch((error) => {
      console.error("Hype (BIST) hatası:", error?.message ?? error);
    });

  await loadExchange(usItems, US_CONCURRENCY, (usRows) => {
    publish({
      names,
      rows: [...bistRows, ...usRows],
      complete: false,
      updatedAt: new Date().toISOString(),
    });
  });

  await bistHype;

  const allRows = snapshot?.rows ?? bistRows;
  const hypeJob = enrichHype(prioritizeHype(allRows), nameLookup, {
    newsLimit: 280,
    redditLimit: 36,
  }).catch((error) => {
    console.error("Hype yenileme hatası:", error?.message ?? error);
    return {
      reddit: "unavailable",
      news: "unavailable",
      kap: "seed",
      trends: "unavailable",
    };
  });
  const hype = await Promise.race([
    hypeJob,
    wait(90_000).then(() => ({
      reddit: "pending",
      news: "pending",
      kap: "seed",
      trends: "pending",
      timedOut: true,
    })),
  ]);
  publish({
    names,
    rows: allRows,
    complete: true,
    hype,
    updatedAt: new Date().toISOString(),
  });
  if (hype?.timedOut) {
    hypeJob.then((done) => {
      publish({
        names,
        rows: snapshot?.rows ?? allRows,
        complete: true,
        hype: done,
        updatedAt: new Date().toISOString(),
      });
    });
  }
}

function startRefresh(force = false) {
  const fresh =
    snapshot?.complete &&
    snapshot.updatedAt &&
    Date.now() - Date.parse(snapshot.updatedAt) < CACHE_MS;
  if (!force && fresh) return;
  if (refresh) return;
  refresh = refreshAll()
    .catch((error) => {
      console.error("Screener yenileme hatası:", error?.message ?? error);
      if (snapshot) {
        publish({ ...snapshot, complete: true });
      }
    })
    .finally(() => {
      refresh = null;
    });
}

export function warmScreener() {
  if (snapshot?.rows?.length) {
    const lookup = new Map();
    for (const row of snapshot.names?.nasdaq ?? []) lookup.set(row.ticker, row.name);
    for (const row of snapshot.names?.nyse ?? []) lookup.set(row.ticker, row.name);
    enrichHype(prioritizeHype(snapshot.rows), lookup, {
      newsLimit: 80,
      redditLimit: 36,
    })
      .then((hype) => {
        publish({
          names: snapshot.names,
          rows: snapshot.rows,
          complete: snapshot.complete ?? true,
          hype,
          updatedAt: new Date().toISOString(),
        });
      })
      .catch((error) => {
        console.error("Hype (boot) hatası:", error?.message ?? error);
      });
  }
  startRefresh(false);
}

function wait(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export async function handleScreener(req, res) {
  res.setHeader("Connection", "close");
  res.setHeader("Content-Type", "application/json; charset=utf-8");
  res.setHeader("Cache-Control", "no-store");
  try {
    startRefresh(false);
    if (!snapshot || (!(snapshot.rows?.length > 0) && !(snapshot.names?.nasdaq?.length > 0))) {
      const until = Date.now() + 12_000;
      while (Date.now() < until && !snapshot?.names?.nasdaq?.length) {
        await wait(400);
      }
    }
    if (!snapshot || (!(snapshot.rows?.length > 0) && !(snapshot.names?.nasdaq?.length > 0))) {
      throw new Error("no rows");
    }
    res.writeHead(200);
    res.end(req.method === "HEAD" ? undefined : JSON.stringify(snapshot));
  } catch (error) {
    res.writeHead(502);
    res.end(
      JSON.stringify({
        error: "Hacim ve volatilite verisi alınamadı.",
        detail: String(error?.message ?? error),
      }),
    );
  }
}
