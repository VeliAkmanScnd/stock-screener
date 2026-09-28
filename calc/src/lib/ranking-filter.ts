import { parseTrNumber } from "./format";
import {
  rankingMetric,
  sortByScreener,
  type RankedStat,
  type ScreenerSort,
} from "./screener";

export const RANKING_TOP_PRESETS = [50, 100, 250] as const;

export type RankingFilter = {
  /** Keep the top N names by combined score. Null shows the full list. */
  topN: number | null;
  minVolume: number;
  minVolatility: number;
  minScore: number;
};

export const DEFAULT_RANKING_FILTER: RankingFilter = {
  topN: 100,
  minVolume: 0,
  minVolatility: 0,
  minScore: 0,
};

/** Parse volume thresholds: 20 Mn, 1,2 Mr, or an absolute amount. */
export function parseVolumeThreshold(raw: string): number | null {
  const cleaned = raw.trim().replace(/usd|tl|\$/gi, "").trim();
  if (!cleaned) return 0;
  const suffix = cleaned.match(/(milyar|milyon|bin|mr|mn|m|k|b)\s*$/i);
  let multiplier = 1;
  let amount = cleaned;
  if (suffix) {
    const token = suffix[1].toLocaleLowerCase("tr-TR");
    if (token === "mr" || token === "milyar") multiplier = 1_000_000_000;
    else if (token === "mn" || token === "milyon" || token === "m") multiplier = 1_000_000;
    else if (token === "b" || token === "bin" || token === "k") multiplier = 1_000;
    amount = cleaned.slice(0, suffix.index).trim();
  }
  const value = parseTrNumber(amount);
  if (value == null) return null;
  return value * multiplier;
}

export function applyRankingFilter<T extends { ticker: string }>(
  rows: T[],
  ranked: Map<string, RankedStat>,
  filter: RankingFilter,
  options: { searching?: boolean; sortKey?: ScreenerSort } = {},
): T[] {
  const searching = Boolean(options.searching);
  const scoreOf = (stats: RankedStat) => rankingMetric(stats, options.sortKey);
  const needsStats =
    !searching &&
    (filter.topN != null ||
      filter.minVolume > 0 ||
      filter.minVolatility > 0 ||
      filter.minScore > 0);

  const passed = rows.filter((row) => {
    const stats = ranked.get(row.ticker);
    if (!stats) return !needsStats;
    if (filter.minVolume > 0 && stats.avgVolumeTl < filter.minVolume) return false;
    if (filter.minVolatility > 0 && stats.volatility < filter.minVolatility) return false;
    if (filter.minScore > 0 && scoreOf(stats) < filter.minScore) return false;
    return true;
  });

  if (searching || filter.topN == null) return passed;

  const rankedOrder = [...passed]
    .filter((row) => ranked.has(row.ticker))
    .sort((a, b) => scoreOf(ranked.get(b.ticker)!) - scoreOf(ranked.get(a.ticker)!))
    .slice(0, filter.topN);
  const keep = new Set(rankedOrder.map((row) => row.ticker));
  return passed.filter((row) => keep.has(row.ticker));
}

export function rankAndFilter<T extends { ticker: string }>(
  rows: T[],
  ranked: Map<string, RankedStat>,
  filter: RankingFilter,
  sortKey: ScreenerSort,
  searching = false,
): T[] {
  return sortByScreener(
    applyRankingFilter(rows, ranked, filter, { searching, sortKey }),
    ranked,
    sortKey,
  );
}
