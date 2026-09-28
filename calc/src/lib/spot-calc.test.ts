import assert from "node:assert/strict";
import { test } from "node:test";
import { pnlForPriceMove } from "./calc";
import { parseTrNumber } from "./format";
import { buildSpotPosition } from "./spot-calc";
import {
  ANA_PAZAR_TICKERS,
  BIST100_TICKERS,
  searchSpotStocks,
  SPOT_STOCKS,
  YILDIZ_TICKERS,
} from "./spot-stocks";

test("spot lots is floor of amount / price", () => {
  const position = buildSpotPosition(25000, 318.9);
  assert.equal(position.lots, 78);
  assert.equal(position.maxLots, 78);
  assert.ok(Math.abs(position.usedCost - 78 * 318.9) < 1e-9);
  assert.ok(Math.abs(position.remaining - (25000 - 78 * 318.9)) < 1e-9);
  assert.equal(position.notional, position.usedCost);
});

test("spot position clamps typed lots to max", () => {
  const position = buildSpotPosition(1000, 300, 10);
  assert.equal(position.lots, 3);
  assert.equal(position.maxLots, 3);
});

test("insufficient cash yields zero lots", () => {
  const position = buildSpotPosition(100, 318.9);
  assert.equal(position.lots, 0);
  assert.equal(position.notional, 0);
});

test("spot P&L is shares times price times percent", () => {
  const position = buildSpotPosition(25000, 318.9);
  const pnl = pnlForPriceMove(position.notional, 1, "long");
  assert.ok(Math.abs(pnl - position.lots * 318.9 * 0.01) < 1e-9);
  assert.equal(pnlForPriceMove(position.notional, 1, "short"), -pnl);
});

test("lists load unique tickers across markets", () => {
  assert.equal(new Set(BIST100_TICKERS).size, BIST100_TICKERS.length);
  assert.equal(new Set(YILDIZ_TICKERS).size, YILDIZ_TICKERS.length);
  assert.equal(new Set(ANA_PAZAR_TICKERS).size, ANA_PAZAR_TICKERS.length);
  assert.equal(SPOT_STOCKS.length, new Set(SPOT_STOCKS.map((s) => s.ticker)).size);
  assert.ok(SPOT_STOCKS.length > 250);
});

test("THYAO is in BIST 100 and Yıldız with a VIOP reference price", () => {
  const thyao = SPOT_STOCKS.find((s) => s.ticker === "THYAO");
  assert.ok(thyao);
  assert.ok(thyao.markets.includes("bist100"));
  assert.ok(thyao.markets.includes("yildiz"));
  assert.ok((thyao.referencePrice ?? 0) > 0);
});

test("searchSpotStocks filters by market and query", () => {
  const bist = searchSpotStocks("", "bist100");
  assert.equal(bist.length, new Set(BIST100_TICKERS).size);
  const thy = searchSpotStocks("thy", "all");
  assert.ok(thy.some((s) => s.ticker === "THYAO"));
  assert.equal(parseTrNumber("1"), 1);
});
