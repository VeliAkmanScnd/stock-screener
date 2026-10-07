export type MarketExchange = "bist" | "nasdaq" | "nyse";

export type HypeImpact = "ongoing" | "faded" | "unknown";

export const HYPE_IMPACT_LABELS: Record<HypeImpact, string> = {
  ongoing: "Hype sürüyor",
  faded: "Hype soldu",
  unknown: "Belirsiz",
};

export type MarketStat = {
  ticker: string;
  avgVolumeTl: number;
  lastVolumeTl: number;
  /** Annualized realized volatility, percent. */
  volatility: number;
  /** Mean absolute daily return, percent. */
  dailyMove: number;
  /** Market cap in the row currency (TL or USD). */
  marketCap?: number;
  lastPrice?: number;
  exchange?: MarketExchange;
  currency?: "TL" | "USD";
  /** Last session notional / 20d average notional. */
  relativeVolume?: number | null;
  /** Last ~5 sessions |return| vs 20d |return|. */
  shock?: number | null;
  /** Yahoo (and similar) headlines in the last ~7 days. */
  newsCount?: number | null;
  /** KAP disclosures in the last ~7 days (BIST). */
  kapCount?: number | null;
  /** Reddit mentions in the last ~7 days. Null = missing, not zero. */
  redditCount?: number | null;
  redditStatus?: "ok" | "unavailable";
  newsStatus?: "ok" | "unavailable";
  /** Google Trends 7d interest; null when the stub/API is unavailable. */
  trendsScore?: number | null;
  /** X/Twitter posts in last ~24h matching #/$ticker (Basic recent search). */
  twitterCount?: number | null;
  /** today / avg(prior 7d). Null when history/API missing. */
  twitterGrowth?: number | null;
  twitterStatus?: "ok" | "unavailable";
  /** Mentions across configured TR Telegram channels (~24h). */
  telegramCount?: number | null;
  telegramGrowth?: number | null;
  telegramStatus?: "ok" | "unavailable";
  /** Percent return +1 session after the latest hype spike. */
  postHypeReturn1d?: number | null;
  /** Percent return +5 sessions after the latest hype spike. */
  postHypeReturn5d?: number | null;
};

export type ScreenerSort =
  | "default"
  | "volume"
  | "relativeVolume"
  | "volatility"
  | "marketCap"
  | "score"
  | "scoreValue"
  | "hype"
  | "scoreHype";

export const SCREENER_SORT_LABELS: Record<ScreenerSort, string> = {
  default: "Liste",
  volume: "Hacim",
  relativeVolume: "Göreli hacim",
  volatility: "Volatilite",
  marketCap: "Değer",
  score: "Hacim + vol",
  scoreValue: "Hacim + vol + değer",
  hype: "Hype",
  scoreHype: "Hacim + vol + hype",
};

export type Bar = {
  close: number;
  volume: number;
};

function mean(values: number[]): number {
  return values.reduce((sum, value) => sum + value, 0) / values.length;
}

function sampleStdev(values: number[]): number {
  if (values.length < 2) return 0;
  const avg = mean(values);
  const variance =
    values.reduce((sum, value) => sum + (value - avg) ** 2, 0) /
    (values.length - 1);
  return Math.sqrt(variance);
}

function finiteOrNull(value: number | null | undefined): number | null {
  if (value == null || !Number.isFinite(value)) return null;
  return value;
}

/**
 * Most recent volume/return spike in the last ~30 sessions, then +1d/+5d
 * close-to-close percent returns. Missing forwards stay null (Belirsiz).
 */
export function postHypeForwardReturns(bars: Bar[]): {
  d1: number | null;
  d5: number | null;
} {
  const usable = bars.filter(
    (bar) => Number.isFinite(bar.close) && bar.close > 0 && Number.isFinite(bar.volume),
  );
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
    const absReturns: number[] = [];
    for (let j = 1; j < lookback.length; j++) {
      absReturns.push(Math.abs(Math.log(lookback[j].close / lookback[j - 1].close)));
    }
    const meanAbs = absReturns.length > 0 ? mean(absReturns) : 0;
    const dayRet = Math.abs(Math.log(usable[i].close / usable[i - 1].close));
    const spiked =
      relative >= 2 || (meanAbs > 0 && dayRet >= 2 * meanAbs);
    if (spiked) {
      spike = i;
      break;
    }
  }
  if (spike < 0) return { d1: null, d5: null };
  const px = usable[spike].close;
  if (!(px > 0)) return { d1: null, d5: null };
  const d1 =
    spike + 1 < n ? ((usable[spike + 1].close / px) - 1) * 100 : null;
  const d5 =
    spike + 5 < n ? ((usable[spike + 5].close / px) - 1) * 100 : null;
  return { d1, d5 };
}

/** Last ~20 sessions: TL volume and realized volatility from daily bars. */
export function statsFromBars(ticker: string, bars: Bar[]): MarketStat | null {
  const usable = bars.filter(
    (bar) => Number.isFinite(bar.close) && bar.close > 0 && Number.isFinite(bar.volume),
  );
  if (usable.length < 6) return null;
  const window = usable.slice(-21);
  const notionals = window.map((bar) => bar.close * Math.max(0, bar.volume));
  const returns: number[] = [];
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
    ticker,
    avgVolumeTl,
    lastVolumeTl,
    volatility: sampleStdev(returns) * Math.sqrt(252) * 100,
    dailyMove: longAbs * 100,
    lastPrice: last.close,
    relativeVolume: avgVolumeTl > 0 ? lastVolumeTl / avgVolumeTl : null,
    shock: longAbs > 0 ? shortAbs / longAbs : null,
    postHypeReturn1d: fwd.d1,
    postHypeReturn5d: fwd.d5,
  };
}

export type RankedStat = MarketStat & {
  volumeRank: number;
  volatilityRank: number;
  marketCapRank: number;
  hypeRank: number;
  /** Geometric mean of volume and volatility percentiles. */
  score: number;
  /** Geometric mean of volume, volatility, and market-cap percentiles. */
  scoreValue: number;
  /**
   * 0–100 attention score: equal-weight geometric mean of available
   * sub-signal percentiles (relative volume, shock, news/KAP, Trends, Reddit).
   */
  hype: number;
  /** Geometric mean of volume, volatility, and hype percentiles. No market cap. */
  scoreHype: number;
  /** Diagnostic only — never used as a sort key. */
  hypeImpact: HypeImpact;
};

/** Competition ranking: ties share a rank so equal values get equal percentiles. */
function rankDesc(values: number[]): number[] {
  const order = values
    .map((value, index) => ({ value, index }))
    .sort((a, b) => b.value - a.value);
  const ranks = Array(values.length).fill(values.length);
  let i = 0;
  while (i < order.length) {
    let j = i + 1;
    while (j < order.length && order[j].value === order[i].value) j++;
    const rank = i + 1;
    for (let k = i; k < j; k++) ranks[order[k].index] = rank;
    i = j;
  }
  return ranks;
}

function percentile(rank: number, n: number): number {
  return (n - rank + 1) / n;
}

function median(values: number[]): number | null {
  if (values.length === 0) return null;
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 === 1
    ? sorted[mid]
    : (sorted[mid - 1] + sorted[mid]) / 2;
}

/**
 * Percentiles among names that actually have the signal.
 * Missing inputs stay null so they are skipped later — they are not treated
 * as 0, which would crush small names that simply lack Reddit/news/Trends.
 */
export function percentilesSkippingMissing(
  values: Array<number | null | undefined>,
): Array<number | null> {
  const presentIndex: number[] = [];
  const presentValues: number[] = [];
  for (let i = 0; i < values.length; i++) {
    const value = finiteOrNull(values[i]);
    if (value == null) continue;
    presentIndex.push(i);
    presentValues.push(value);
  }
  const out: Array<number | null> = Array(values.length).fill(null);
  if (presentValues.length === 0) return out;
  const ranks = rankDesc(presentValues);
  const n = presentValues.length;
  for (let i = 0; i < presentIndex.length; i++) {
    out[presentIndex[i]] = percentile(ranks[i], n);
  }
  return out;
}

/**
 * Equal-weight geometric mean of available sub-signal percentiles, scaled 0–100.
 * Null / non-finite / non-positive inputs are skipped (missing ≠ 0).
 * If nothing remains, return 0 so callers never get NaN.
 */
export function hypeFromPercentiles(
  percentiles: Array<number | null | undefined>,
): number {
  const usable = percentiles.filter(
    (value): value is number =>
      value != null && Number.isFinite(value) && value > 0,
  );
  if (usable.length === 0) return 0;
  const product = usable.reduce((acc, value) => acc * value, 1);
  return Math.pow(product, 1 / usable.length) * 100;
}

function newsOrKap(item: MarketStat): number | null {
  if (item.newsCount == null && item.kapCount == null) return null;
  return (item.newsCount ?? 0) + (item.kapCount ?? 0);
}

function redditSignal(item: MarketStat): number | null {
  if (item.redditStatus === "unavailable") return null;
  return finiteOrNull(item.redditCount);
}

function twitterSignal(item: MarketStat): number | null {
  if (item.twitterStatus === "unavailable") return null;
  return finiteOrNull(item.twitterGrowth ?? item.twitterCount);
}

function telegramSignal(item: MarketStat): number | null {
  if (item.telegramStatus === "unavailable") return null;
  return finiteOrNull(item.telegramGrowth ?? item.telegramCount);
}

function impactFor(
  d1: number | null,
  d5: number | null,
  median1: number | null,
  median5: number | null,
): HypeImpact {
  if (d1 == null || d5 == null || median1 == null || median5 == null) {
    return "unknown";
  }
  if (d1 > median1 && d5 > median5) return "ongoing";
  if (d1 < median1 && d5 < median5) return "faded";
  return "unknown";
}

/**
 * Two combined scores 0–100:
 * - score: equal-weight geometric mean of volume and volatility
 * - scoreValue: equal-weight geometric mean of volume, volatility, and market cap
 *
 * Hype is a separate 0–100 score (sub-signal percentiles, skip missing).
 * scoreHype = ∛(volumePct × volPct × hypePct) × 100 — market cap is not mixed in.
 */
export function rankStats(stats: MarketStat[]): RankedStat[] {
  if (stats.length === 0) return [];
  const volumeRanks = rankDesc(stats.map((item) => item.avgVolumeTl));
  const volRanks = rankDesc(stats.map((item) => item.volatility));
  const mcapRanks = rankDesc(
    stats.map((item) =>
      item.marketCap != null && item.marketCap > 0 ? item.marketCap : 0,
    ),
  );
  const relVolPcts = percentilesSkippingMissing(
    stats.map((item) => item.relativeVolume),
  );
  const shockPcts = percentilesSkippingMissing(stats.map((item) => item.shock));
  const newsPcts = percentilesSkippingMissing(stats.map(newsOrKap));
  const redditPcts = percentilesSkippingMissing(stats.map(redditSignal));
  const trendsPcts = percentilesSkippingMissing(
    stats.map((item) => item.trendsScore),
  );
  const twitterPcts = percentilesSkippingMissing(stats.map(twitterSignal));
  const telegramPcts = percentilesSkippingMissing(stats.map(telegramSignal));
  const hypeScores = stats.map((_, index) =>
    hypeFromPercentiles([
      relVolPcts[index],
      shockPcts[index],
      newsPcts[index],
      redditPcts[index],
      trendsPcts[index],
      twitterPcts[index],
      telegramPcts[index],
    ]),
  );
  const hypeRanks = rankDesc(hypeScores);
  const n = stats.length;
  const fwd1 = stats.map((item) => finiteOrNull(item.postHypeReturn1d));
  const fwd5 = stats.map((item) => finiteOrNull(item.postHypeReturn5d));
  const paired1: number[] = [];
  const paired5: number[] = [];
  for (let i = 0; i < n; i++) {
    if (fwd1[i] != null && fwd5[i] != null) {
      paired1.push(fwd1[i]!);
      paired5.push(fwd5[i]!);
    }
  }
  const median1 = paired1.length >= 3 ? median(paired1) : null;
  const median5 = paired5.length >= 3 ? median(paired5) : null;

  return stats.map((item, index) => {
    const volumeRank = volumeRanks[index];
    const volatilityRank = volRanks[index];
    const marketCapRank = mcapRanks[index];
    const hypeRank = hypeRanks[index];
    const volumePct = percentile(volumeRank, n);
    const volPct = percentile(volatilityRank, n);
    const mcapPct = percentile(marketCapRank, n);
    const hypePct = percentile(hypeRank, n);
    const hype = hypeScores[index];
    return {
      ...item,
      volumeRank,
      volatilityRank,
      marketCapRank,
      hypeRank,
      score: Math.sqrt(volumePct * volPct) * 100,
      scoreValue: Math.cbrt(volumePct * volPct * mcapPct) * 100,
      hype,
      scoreHype: Math.cbrt(volumePct * volPct * hypePct) * 100,
      hypeImpact: impactFor(fwd1[index], fwd5[index], median1, median5),
    };
  });
}

export function rankedByTicker(stats: MarketStat[]): Map<string, RankedStat> {
  return new Map(rankStats(stats).map((item) => [item.ticker, item]));
}

/** Split Yahoo rows so BIST / Nasdaq / NYSE rankings never share a ticker map. */
export function splitScreenerRows(rows: MarketStat[]): {
  bist: Map<string, MarketStat>;
  nasdaq: Map<string, MarketStat>;
  nyse: Map<string, MarketStat>;
} {
  const bist = new Map<string, MarketStat>();
  const nasdaq = new Map<string, MarketStat>();
  const nyse = new Map<string, MarketStat>();
  for (const row of rows) {
    const exchange = row.exchange ?? "bist";
    if (exchange === "nasdaq") nasdaq.set(row.ticker, row);
    else if (exchange === "nyse") nyse.set(row.ticker, row);
    else bist.set(row.ticker, row);
  }
  return { bist, nasdaq, nyse };
}

/** Rank only the given tickers so VIOP and Hisse scores stay in-universe. */
export function rankForTickers(
  tickers: Iterable<string>,
  stats: Map<string, MarketStat>,
): Map<string, RankedStat> {
  const rows: MarketStat[] = [];
  const seen = new Set<string>();
  for (const ticker of tickers) {
    if (seen.has(ticker)) continue;
    seen.add(ticker);
    const row = stats.get(ticker);
    if (row) rows.push(row);
  }
  return rankedByTicker(rows);
}

type Sortable = { ticker: string };

/** Combined / hype metric used by top-N and min-skor. Default stays hacim+vol. */
export function rankingMetric(
  row: RankedStat,
  key: ScreenerSort | undefined,
): number {
  if (key === "scoreValue") return row.scoreValue;
  if (key === "hype") return row.hype;
  if (key === "scoreHype") return row.scoreHype;
  if (key === "relativeVolume") return row.relativeVolume ?? Number.NEGATIVE_INFINITY;
  return row.score;
}

export function sortByScreener<T extends Sortable>(
  rows: T[],
  ranked: Map<string, RankedStat>,
  key: ScreenerSort,
): T[] {
  if (key === "default") return rows;
  const metric = (ticker: string): number | null => {
    const row = ranked.get(ticker);
    if (!row) return null;
    if (key === "volume") return row.avgVolumeTl;
    if (key === "relativeVolume") {
      return row.relativeVolume != null && Number.isFinite(row.relativeVolume)
        ? row.relativeVolume
        : null;
    }
    if (key === "volatility") return row.volatility;
    if (key === "marketCap") {
      return row.marketCap != null && row.marketCap > 0 ? row.marketCap : null;
    }
    if (key === "scoreValue") return row.scoreValue;
    if (key === "hype") return row.hype;
    if (key === "scoreHype") return row.scoreHype;
    return row.score;
  };
  return [...rows].sort((a, b) => {
    const left = metric(a.ticker);
    const right = metric(b.ticker);
    if (left == null && right == null) return 0;
    if (left == null) return 1;
    if (right == null) return -1;
    return right - left;
  });
}
