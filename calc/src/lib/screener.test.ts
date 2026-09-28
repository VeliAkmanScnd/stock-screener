import assert from "node:assert/strict";
import { test } from "node:test";
import {
  HYPE_IMPACT_LABELS,
  SCREENER_SORT_LABELS,
  hypeFromPercentiles,
  rankForTickers,
  rankStats,
  rankingMetric,
  sortByScreener,
  splitScreenerRows,
  statsFromBars,
} from "./screener";
import listings from "../../data/us-listings.json";

test("hacim+vol and hacim+vol+değer stay separate sort labels", () => {
  assert.equal(SCREENER_SORT_LABELS.score, "Hacim + vol");
  assert.equal(SCREENER_SORT_LABELS.scoreValue, "Hacim + vol + değer");
  assert.notEqual(SCREENER_SORT_LABELS.score, SCREENER_SORT_LABELS.scoreValue);
});

test("hype chips are extra labels and do not replace existing ones", () => {
  assert.equal(SCREENER_SORT_LABELS.hype, "Hype");
  assert.equal(SCREENER_SORT_LABELS.scoreHype, "Hacim + vol + hype");
  assert.equal(SCREENER_SORT_LABELS.default, "Liste");
  assert.equal(SCREENER_SORT_LABELS.volume, "Hacim");
  assert.equal(SCREENER_SORT_LABELS.relativeVolume, "Göreli hacim");
  assert.notEqual(SCREENER_SORT_LABELS.volume, SCREENER_SORT_LABELS.relativeVolume);
  assert.equal(SCREENER_SORT_LABELS.volatility, "Volatilite");
  assert.equal(SCREENER_SORT_LABELS.marketCap, "Değer");
  assert.equal(HYPE_IMPACT_LABELS.ongoing, "Hype sürüyor");
  assert.equal(HYPE_IMPACT_LABELS.faded, "Hype soldu");
  assert.equal(HYPE_IMPACT_LABELS.unknown, "Belirsiz");
});

test("statsFromBars uses TL notional volume and realized vol", () => {
  const bars = [];
  let price = 100;
  for (let i = 0; i < 21; i++) {
    price *= i % 2 === 0 ? 1.02 : 0.99;
    bars.push({ close: price, volume: 1000 + i * 10 });
  }
  const stats = statsFromBars("THYAO", bars);
  assert.ok(stats);
  assert.ok(stats.avgVolumeTl > 100_000);
  assert.ok(stats.volatility > 0);
  assert.ok(stats.dailyMove > 0);
  assert.ok(stats.lastPrice != null && stats.lastPrice > 0);
});

test("hacim+vol score favors names high on both liquidity and movement", () => {
  const ranked = rankStats([
    { ticker: "A", avgVolumeTl: 100, lastVolumeTl: 100, volatility: 10, dailyMove: 1, marketCap: 50 },
    { ticker: "B", avgVolumeTl: 50, lastVolumeTl: 50, volatility: 40, dailyMove: 2, marketCap: 40 },
    { ticker: "C", avgVolumeTl: 90, lastVolumeTl: 90, volatility: 35, dailyMove: 2, marketCap: 90 },
  ]);
  const byTicker = Object.fromEntries(ranked.map((row) => [row.ticker, row]));
  assert.equal(byTicker.A.volumeRank, 1);
  assert.equal(byTicker.B.volatilityRank, 1);
  assert.ok(byTicker.C.score > byTicker.A.score);
  assert.ok(byTicker.C.score > byTicker.B.score);
});

test("hacim+vol+değer is a separate score that rewards market cap", () => {
  const ranked = rankStats([
    { ticker: "A", avgVolumeTl: 100, lastVolumeTl: 100, volatility: 10, dailyMove: 1, marketCap: 50 },
    { ticker: "B", avgVolumeTl: 50, lastVolumeTl: 50, volatility: 40, dailyMove: 2, marketCap: 40 },
    { ticker: "C", avgVolumeTl: 90, lastVolumeTl: 90, volatility: 35, dailyMove: 2, marketCap: 90 },
    { ticker: "D", avgVolumeTl: 5, lastVolumeTl: 5, volatility: 8, dailyMove: 1, marketCap: 10_000 },
  ]);
  const byTicker = Object.fromEntries(ranked.map((row) => [row.ticker, row]));
  assert.equal(byTicker.D.marketCapRank, 1);
  assert.ok(byTicker.C.scoreValue > byTicker.A.scoreValue);
  assert.ok(byTicker.C.scoreValue > byTicker.B.scoreValue);
  assert.ok(byTicker.C.scoreValue > byTicker.D.scoreValue);
  const valueScoreOrder = sortByScreener(
    ranked.map((row) => ({ ticker: row.ticker })),
    new Map(ranked.map((row) => [row.ticker, row])),
    "scoreValue",
  ).map((row) => row.ticker);
  assert.equal(valueScoreOrder[0], "C");
});

test("identical volume and vol keep hacim+vol tied while değer score follows market cap", () => {
  const ranked = rankStats([
    { ticker: "SMALL", avgVolumeTl: 80, lastVolumeTl: 80, volatility: 30, dailyMove: 2, marketCap: 10 },
    { ticker: "LARGE", avgVolumeTl: 80, lastVolumeTl: 80, volatility: 30, dailyMove: 2, marketCap: 1000 },
  ]);
  const byTicker = Object.fromEntries(ranked.map((row) => [row.ticker, row]));
  assert.equal(byTicker.LARGE.score, byTicker.SMALL.score);
  assert.ok(byTicker.LARGE.scoreValue > byTicker.SMALL.scoreValue);
  const valueOrder = sortByScreener(
    [{ ticker: "SMALL" }, { ticker: "LARGE" }],
    new Map(ranked.map((row) => [row.ticker, row])),
    "marketCap",
  ).map((row) => row.ticker);
  assert.deepEqual(valueOrder, ["LARGE", "SMALL"]);
});

test("rankForTickers scores only inside the given universe", () => {
  const stats = new Map(
    rankStats([
      { ticker: "THYAO", avgVolumeTl: 100, lastVolumeTl: 100, volatility: 20, dailyMove: 1 },
      { ticker: "SASA", avgVolumeTl: 10, lastVolumeTl: 10, volatility: 80, dailyMove: 3 },
      { ticker: "PENNY", avgVolumeTl: 1, lastVolumeTl: 1, volatility: 200, dailyMove: 8 },
    ]).map((row) => [row.ticker, row]),
  );
  const raw = new Map(
    [...stats.values()].map((row) => [
      row.ticker,
      {
        ticker: row.ticker,
        avgVolumeTl: row.avgVolumeTl,
        lastVolumeTl: row.lastVolumeTl,
        volatility: row.volatility,
        dailyMove: row.dailyMove,
      },
    ]),
  );
  const viop = rankForTickers(["THYAO", "SASA"], raw);
  assert.equal(viop.get("SASA")?.volatilityRank, 1);
  assert.equal(viop.has("PENNY"), false);
});

test("sortByScreener puts missing stats last", () => {
  const ranked = new Map(
    rankStats([
      { ticker: "THYAO", avgVolumeTl: 10, lastVolumeTl: 10, volatility: 20, dailyMove: 1 },
      { ticker: "SASA", avgVolumeTl: 3, lastVolumeTl: 3, volatility: 50, dailyMove: 2 },
    ]).map((row) => [row.ticker, row]),
  );
  const volumeOrder = sortByScreener(
    [{ ticker: "EURTRY" }, { ticker: "SASA" }, { ticker: "THYAO" }],
    ranked,
    "volume",
  ).map((row) => row.ticker);
  assert.deepEqual(volumeOrder, ["THYAO", "SASA", "EURTRY"]);
  const volOrder = sortByScreener(
    [{ ticker: "EURTRY" }, { ticker: "SASA" }, { ticker: "THYAO" }],
    ranked,
    "volatility",
  ).map((row) => row.ticker);
  assert.deepEqual(volOrder, ["SASA", "THYAO", "EURTRY"]);
});

test("splitScreenerRows keeps BIST and US tickers in separate maps", () => {
  const split = splitScreenerRows([
    {
      ticker: "C",
      avgVolumeTl: 10,
      lastVolumeTl: 10,
      volatility: 20,
      dailyMove: 1,
      exchange: "nyse",
      currency: "USD",
    },
    {
      ticker: "THYAO",
      avgVolumeTl: 100,
      lastVolumeTl: 100,
      volatility: 25,
      dailyMove: 1,
      exchange: "bist",
      currency: "TL",
    },
    {
      ticker: "NVDA",
      avgVolumeTl: 80,
      lastVolumeTl: 80,
      volatility: 40,
      dailyMove: 2,
      exchange: "nasdaq",
      currency: "USD",
    },
  ]);
  assert.equal(split.bist.get("THYAO")?.currency, "TL");
  assert.equal(split.nasdaq.get("NVDA")?.exchange, "nasdaq");
  assert.equal(split.nyse.get("C")?.exchange, "nyse");
  assert.equal(split.bist.has("C"), false);
  assert.equal(split.nasdaq.has("THYAO"), false);
});

test("Nasdaq and NYSE universes cover the full common-stock lists", () => {
  const nasdaq = listings.filter((row) => row.exchange === "nasdaq");
  const nyse = listings.filter((row) => row.exchange === "nyse");
  const nasdaqTickers = new Set(nasdaq.map((row) => row.ticker));
  const overlap = nyse.filter((row) => nasdaqTickers.has(row.ticker));
  assert.deepEqual(overlap.map((row) => row.ticker), []);
  assert.ok(nasdaq.length >= 2500);
  assert.ok(nyse.length >= 1500);
  assert.ok(nasdaq.some((row) => row.ticker === "AAPL"));
  assert.ok(nyse.some((row) => row.ticker === "JPM"));
});

test("2-factor hacim+vol score ignores hype inputs and market cap", () => {
  const base = rankStats([
    { ticker: "A", avgVolumeTl: 100, lastVolumeTl: 100, volatility: 10, dailyMove: 1 },
    { ticker: "B", avgVolumeTl: 50, lastVolumeTl: 50, volatility: 40, dailyMove: 2 },
    { ticker: "C", avgVolumeTl: 90, lastVolumeTl: 90, volatility: 35, dailyMove: 2 },
  ]);
  const withHype = rankStats([
    {
      ticker: "A",
      avgVolumeTl: 100,
      lastVolumeTl: 100,
      volatility: 10,
      dailyMove: 1,
      marketCap: 9_000,
      relativeVolume: 0.4,
      shock: 0.5,
      newsCount: 20,
      redditCount: 50,
      redditStatus: "ok",
    },
    {
      ticker: "B",
      avgVolumeTl: 50,
      lastVolumeTl: 50,
      volatility: 40,
      dailyMove: 2,
      marketCap: 10,
      relativeVolume: 4,
      shock: 3,
      newsCount: 1,
      redditCount: 2,
      redditStatus: "ok",
    },
    {
      ticker: "C",
      avgVolumeTl: 90,
      lastVolumeTl: 90,
      volatility: 35,
      dailyMove: 2,
      marketCap: 500,
      relativeVolume: 1.2,
      shock: 1.1,
      newsCount: 8,
      redditCount: 9,
      redditStatus: "ok",
    },
  ]);
  const byBase = Object.fromEntries(base.map((row) => [row.ticker, row]));
  const byHype = Object.fromEntries(withHype.map((row) => [row.ticker, row]));
  assert.equal(byHype.A.score, byBase.A.score);
  assert.equal(byHype.B.score, byBase.B.score);
  assert.equal(byHype.C.score, byBase.C.score);
});

test("hype is independent of market cap", () => {
  const ranked = rankStats([
    {
      ticker: "SMALL",
      avgVolumeTl: 80,
      lastVolumeTl: 160,
      volatility: 30,
      dailyMove: 2,
      marketCap: 10,
      relativeVolume: 3,
      shock: 2,
      newsCount: 10,
      redditCount: 20,
      redditStatus: "ok",
    },
    {
      ticker: "LARGE",
      avgVolumeTl: 80,
      lastVolumeTl: 160,
      volatility: 30,
      dailyMove: 2,
      marketCap: 50_000,
      relativeVolume: 3,
      shock: 2,
      newsCount: 10,
      redditCount: 20,
      redditStatus: "ok",
    },
  ]);
  const byTicker = Object.fromEntries(ranked.map((row) => [row.ticker, row]));
  assert.equal(byTicker.SMALL.hype, byTicker.LARGE.hype);
  assert.ok(byTicker.LARGE.scoreValue > byTicker.SMALL.scoreValue);
});

test("hacim+vol+hype does not mix in değer / market cap", () => {
  const ranked = rankStats([
    {
      ticker: "SMALL",
      avgVolumeTl: 80,
      lastVolumeTl: 200,
      volatility: 30,
      dailyMove: 2,
      marketCap: 10,
      relativeVolume: 4,
      shock: 3,
      newsCount: 12,
      redditCount: 30,
      redditStatus: "ok",
    },
    {
      ticker: "LARGE",
      avgVolumeTl: 80,
      lastVolumeTl: 200,
      volatility: 30,
      dailyMove: 2,
      marketCap: 80_000,
      relativeVolume: 4,
      shock: 3,
      newsCount: 12,
      redditCount: 30,
      redditStatus: "ok",
    },
  ]);
  const byTicker = Object.fromEntries(ranked.map((row) => [row.ticker, row]));
  assert.equal(byTicker.SMALL.scoreHype, byTicker.LARGE.scoreHype);
  assert.equal(byTicker.SMALL.score, byTicker.LARGE.score);
  assert.ok(byTicker.LARGE.scoreValue > byTicker.SMALL.scoreValue);
});

test("missing reddit or news does not produce NaN hype", () => {
  const ranked = rankStats([
    {
      ticker: "A",
      avgVolumeTl: 10,
      lastVolumeTl: 30,
      volatility: 20,
      dailyMove: 1,
      relativeVolume: 3,
      shock: 2,
      newsCount: null,
      redditCount: null,
      redditStatus: "unavailable",
      trendsScore: null,
    },
    {
      ticker: "B",
      avgVolumeTl: 8,
      lastVolumeTl: 8,
      volatility: 15,
      dailyMove: 1,
      relativeVolume: 1,
      shock: 1,
    },
  ]);
  for (const row of ranked) {
    assert.equal(Number.isFinite(row.hype), true);
    assert.equal(Number.isNaN(row.hype), false);
    assert.equal(Number.isFinite(row.scoreHype), true);
    assert.ok(row.hype >= 0);
  }
});

test("missing reddit is skipped instead of treated as zero that crushes small names", () => {
  assert.equal(hypeFromPercentiles([0.9, null, undefined]), 90);
  assert.equal(hypeFromPercentiles([]), 0);
  assert.equal(hypeFromPercentiles([null, undefined]), 0);
  const ranked = rankStats([
    {
      ticker: "NO_REDDIT",
      avgVolumeTl: 50,
      lastVolumeTl: 150,
      volatility: 25,
      dailyMove: 2,
      relativeVolume: 5,
      shock: 4,
      newsCount: 8,
      redditCount: null,
      redditStatus: "unavailable",
    },
    {
      ticker: "ZERO_REDDIT",
      avgVolumeTl: 50,
      lastVolumeTl: 150,
      volatility: 25,
      dailyMove: 2,
      relativeVolume: 5,
      shock: 4,
      newsCount: 8,
      redditCount: 0,
      redditStatus: "ok",
    },
    {
      ticker: "HOT_REDDIT",
      avgVolumeTl: 50,
      lastVolumeTl: 150,
      volatility: 25,
      dailyMove: 2,
      relativeVolume: 5,
      shock: 4,
      newsCount: 8,
      redditCount: 40,
      redditStatus: "ok",
    },
  ]);
  const byTicker = Object.fromEntries(ranked.map((row) => [row.ticker, row]));
  assert.ok(byTicker.NO_REDDIT.hype > byTicker.ZERO_REDDIT.hype);
  assert.ok(byTicker.HOT_REDDIT.hype >= byTicker.NO_REDDIT.hype);
});

test("statsFromBars fills relative volume from last session vs 20d", () => {
  const bars = [];
  let price = 100;
  for (let i = 0; i < 21; i++) {
    price *= i % 2 === 0 ? 1.02 : 0.99;
    bars.push({ close: price, volume: i === 20 ? 50_000 : 1000 });
  }
  const stats = statsFromBars("THYAO", bars);
  assert.ok(stats);
  assert.ok(stats.relativeVolume != null && stats.relativeVolume > 5);
  assert.ok(stats.shock != null && Number.isFinite(stats.shock));
});

test("göreli hacim sorts independently of 20g hacim", () => {
  const ranked = rankStats([
    {
      ticker: "LIQUID",
      avgVolumeTl: 500,
      lastVolumeTl: 400,
      volatility: 10,
      dailyMove: 1,
      relativeVolume: 0.8,
    },
    {
      ticker: "SPIKE",
      avgVolumeTl: 20,
      lastVolumeTl: 200,
      volatility: 12,
      dailyMove: 1,
      relativeVolume: 10,
    },
  ]);
  const map = new Map(ranked.map((row) => [row.ticker, row]));
  const byVolume = sortByScreener(
    [{ ticker: "LIQUID" }, { ticker: "SPIKE" }],
    map,
    "volume",
  ).map((row) => row.ticker);
  const byRel = sortByScreener(
    [{ ticker: "LIQUID" }, { ticker: "SPIKE" }],
    map,
    "relativeVolume",
  ).map((row) => row.ticker);
  assert.deepEqual(byVolume, ["LIQUID", "SPIKE"]);
  assert.deepEqual(byRel, ["SPIKE", "LIQUID"]);
  assert.ok(rankingMetric(map.get("SPIKE")!, "relativeVolume") >
    rankingMetric(map.get("LIQUID")!, "relativeVolume"));
});

test("rankingMetric follows hype sorts without using the impact badge", () => {
  const ranked = rankStats([
    {
      ticker: "A",
      avgVolumeTl: 10,
      lastVolumeTl: 10,
      volatility: 10,
      dailyMove: 1,
      relativeVolume: 1,
    },
    {
      ticker: "B",
      avgVolumeTl: 10,
      lastVolumeTl: 10,
      volatility: 10,
      dailyMove: 1,
      relativeVolume: 8,
    },
  ]);
  const byTicker = Object.fromEntries(ranked.map((row) => [row.ticker, row]));
  assert.ok(rankingMetric(byTicker.B, "hype") > rankingMetric(byTicker.A, "hype"));
  assert.ok(byTicker.A.hypeImpact);
  assert.notEqual(SCREENER_SORT_LABELS.hype, byTicker.A.hypeImpact);
});
