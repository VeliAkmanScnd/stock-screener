import assert from "node:assert/strict";
import { test } from "node:test";
import {
  applyRankingFilter,
  parseVolumeThreshold,
  rankAndFilter,
} from "./ranking-filter";
import { rankStats } from "./screener";

const ranked = new Map(
  rankStats([
    { ticker: "A", avgVolumeTl: 100, lastVolumeTl: 100, volatility: 10, dailyMove: 1 },
    { ticker: "B", avgVolumeTl: 50, lastVolumeTl: 50, volatility: 40, dailyMove: 2 },
    { ticker: "C", avgVolumeTl: 90, lastVolumeTl: 90, volatility: 35, dailyMove: 2 },
    { ticker: "D", avgVolumeTl: 20, lastVolumeTl: 20, volatility: 80, dailyMove: 4 },
  ]).map((row) => [row.ticker, row]),
);

test("parseVolumeThreshold understands Mn / Mr suffixes", () => {
  assert.equal(parseVolumeThreshold("20 Mn"), 20_000_000);
  assert.equal(parseVolumeThreshold("1,5 Mr"), 1_500_000_000);
  assert.equal(parseVolumeThreshold("25000000"), 25_000_000);
  assert.equal(parseVolumeThreshold(""), 0);
});

test("default top N keeps the highest combined scores", () => {
  const rows = [{ ticker: "A" }, { ticker: "B" }, { ticker: "C" }, { ticker: "D" }, { ticker: "NONE" }];
  const top2 = applyRankingFilter(rows, ranked, {
    topN: 2,
    minVolume: 0,
    minVolatility: 0,
    minScore: 0,
  }).map((row) => row.ticker);
  assert.equal(top2.length, 2);
  assert.ok(top2.includes("B") && top2.includes("C"));
  assert.equal(top2.includes("NONE"), false);
});

test("volume and volatility floors hide names below the threshold", () => {
  const rows = [{ ticker: "A" }, { ticker: "B" }, { ticker: "C" }, { ticker: "D" }];
  const filtered = applyRankingFilter(rows, ranked, {
    topN: null,
    minVolume: 60,
    minVolatility: 30,
    minScore: 0,
  }).map((row) => row.ticker);
  assert.deepEqual(filtered, ["C"]);
});

test("searching ignores the top-N cap so every listing is reachable", () => {
  const rows = [{ ticker: "A" }, { ticker: "B" }, { ticker: "C" }, { ticker: "D" }];
  const visible = applyRankingFilter(
    rows,
    ranked,
    { topN: 1, minVolume: 0, minVolatility: 0, minScore: 0 },
    { searching: true },
  ).map((row) => row.ticker);
  assert.deepEqual(visible, ["A", "B", "C", "D"]);
});

test("ilk N follows hacim+vol+değer when that sort is active", () => {
  const rows = [{ ticker: "A" }, { ticker: "B" }, { ticker: "C" }, { ticker: "D" }];
  const byVolScore = applyRankingFilter(
    rows,
    ranked,
    { topN: 1, minVolume: 0, minVolatility: 0, minScore: 0 },
    { sortKey: "score" },
  ).map((row) => row.ticker);
  const byValueScore = applyRankingFilter(
    rows,
    ranked,
    { topN: 1, minVolume: 0, minVolatility: 0, minScore: 0 },
    { sortKey: "scoreValue" },
  ).map((row) => row.ticker);
  assert.equal(byVolScore.length, 1);
  assert.equal(byValueScore.length, 1);
  assert.ok(["B", "C"].includes(byVolScore[0]));
});

test("ilk N follows hype when that chip is active, otherwise stays hacim+vol", () => {
  const hypeRanked = new Map(
    rankStats([
      {
        ticker: "A",
        avgVolumeTl: 100,
        lastVolumeTl: 100,
        volatility: 10,
        dailyMove: 1,
        relativeVolume: 0.5,
        shock: 0.4,
        newsCount: 0,
        redditCount: 1,
        redditStatus: "ok",
      },
      {
        ticker: "B",
        avgVolumeTl: 50,
        lastVolumeTl: 50,
        volatility: 40,
        dailyMove: 2,
        relativeVolume: 1.1,
        shock: 1,
        newsCount: 2,
        redditCount: 3,
        redditStatus: "ok",
      },
      {
        ticker: "C",
        avgVolumeTl: 90,
        lastVolumeTl: 90,
        volatility: 35,
        dailyMove: 2,
        relativeVolume: 1.2,
        shock: 1.1,
        newsCount: 3,
        redditCount: 4,
        redditStatus: "ok",
      },
      {
        ticker: "HYPE",
        avgVolumeTl: 5,
        lastVolumeTl: 80,
        volatility: 8,
        dailyMove: 1,
        relativeVolume: 12,
        shock: 6,
        newsCount: 40,
        redditCount: 90,
        redditStatus: "ok",
      },
    ]).map((row) => [row.ticker, row]),
  );
  const rows = [
    { ticker: "A" },
    { ticker: "B" },
    { ticker: "C" },
    { ticker: "HYPE" },
  ];
  const defaultTop = applyRankingFilter(rows, hypeRanked, {
    topN: 1,
    minVolume: 0,
    minVolatility: 0,
    minScore: 0,
  }).map((row) => row.ticker);
  const hypeTop = applyRankingFilter(
    rows,
    hypeRanked,
    { topN: 1, minVolume: 0, minVolatility: 0, minScore: 0 },
    { sortKey: "hype" },
  ).map((row) => row.ticker);
  const comboTop = applyRankingFilter(
    rows,
    hypeRanked,
    { topN: 1, minVolume: 0, minVolatility: 0, minScore: 0 },
    { sortKey: "scoreHype" },
  ).map((row) => row.ticker);
  assert.equal(defaultTop.length, 1);
  assert.notEqual(defaultTop[0], "HYPE");
  assert.deepEqual(hypeTop, ["HYPE"]);
  assert.equal(comboTop.length, 1);
});

test("ilk N follows göreli hacim when that chip is active", () => {
  const spikeRanked = new Map(
    rankStats([
      {
        ticker: "LIQUID",
        avgVolumeTl: 400,
        lastVolumeTl: 350,
        volatility: 20,
        dailyMove: 1,
        relativeVolume: 0.9,
      },
      {
        ticker: "SPIKE",
        avgVolumeTl: 10,
        lastVolumeTl: 80,
        volatility: 15,
        dailyMove: 1,
        relativeVolume: 8,
      },
    ]).map((row) => [row.ticker, row]),
  );
  const rows = [{ ticker: "LIQUID" }, { ticker: "SPIKE" }];
  const defaultTop = applyRankingFilter(rows, spikeRanked, {
    topN: 1,
    minVolume: 0,
    minVolatility: 0,
    minScore: 0,
  }).map((row) => row.ticker);
  const relTop = applyRankingFilter(
    rows,
    spikeRanked,
    { topN: 1, minVolume: 0, minVolatility: 0, minScore: 0 },
    { sortKey: "relativeVolume" },
  ).map((row) => row.ticker);
  assert.deepEqual(defaultTop, ["LIQUID"]);
  assert.deepEqual(relTop, ["SPIKE"]);
});

test("rankAndFilter still sorts the remaining names by the selected metric", () => {
  const rows = [{ ticker: "A" }, { ticker: "B" }, { ticker: "C" }, { ticker: "D" }];
  const byVolume = rankAndFilter(
    rows,
    ranked,
    { topN: null, minVolume: 0, minVolatility: 0, minScore: 0 },
    "volume",
  ).map((row) => row.ticker);
  assert.deepEqual(byVolume, ["A", "C", "B", "D"]);
});
