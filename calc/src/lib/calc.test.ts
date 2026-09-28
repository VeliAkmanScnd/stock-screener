import assert from "node:assert/strict";
import { test } from "node:test";
import { buildPosition, pnlForPriceMove, returnOnMargin } from "./calc";
import { CONTRACTS } from "./contracts";
import { parseTrNumber } from "./format";

test("parseTrNumber accepts decimal percent with comma or dot", () => {
  assert.equal(parseTrNumber("0,54"), 0.54);
  assert.equal(parseTrNumber("0.54"), 0.54);
  assert.equal(parseTrNumber("%0,54"), 0.54);
  assert.equal(parseTrNumber("1,5"), 1.5);
});

test("parseTrNumber accepts Turkish thousands", () => {
  assert.equal(parseTrNumber("25.000"), 25000);
  assert.equal(parseTrNumber("25.000,50"), 25000.5);
  assert.equal(parseTrNumber("25000"), 25000);
});

test("AEFES leverage matches 100-share contract", () => {
  const aefes = CONTRACTS.find((c) => c.ticker === "AEFES");
  assert.ok(aefes);
  const computed = (aefes.price * 100) / aefes.margin;
  assert.ok(Math.abs(computed - aefes.leverage) < 0.01);
});

test("lot count is floor of amount / margin", () => {
  const aefes = CONTRACTS.find((c) => c.ticker === "AEFES")!;
  const position = buildPosition(1000, aefes);
  assert.equal(position.lots, 3);
  assert.equal(position.usedMargin, 993);
  assert.equal(position.remaining, 7);
  assert.equal(position.notional, 3 * 19.48 * 100);
});

test("insufficient margin yields zero lots", () => {
  const aefes = CONTRACTS.find((c) => c.ticker === "AEFES")!;
  const position = buildPosition(300, aefes);
  assert.equal(position.lots, 0);
  assert.equal(position.notional, 0);
});

test("P&L uses notional times percent", () => {
  const notional = 1948;
  const pnlUp = pnlForPriceMove(notional, 0.54, "long");
  const pnlDown = pnlForPriceMove(notional, -0.54, "long");
  assert.equal(Number(pnlUp.toFixed(4)), Number((1948 * 0.0054).toFixed(4)));
  assert.equal(Number(pnlDown.toFixed(4)), Number((-1948 * 0.0054).toFixed(4)));
  assert.equal(pnlForPriceMove(notional, 0.54, "short"), -pnlUp);
});

test("return on margin reflects leverage", () => {
  const used = 331;
  const pnl = 1948 * 0.0054;
  const rom = returnOnMargin(pnl, used);
  assert.ok(Math.abs(rom - 5.89 * 0.54) < 0.02);
});

test("BIST30 uses multiplier 10", () => {
  const bist = CONTRACTS.find((c) => c.ticker === "BIST30")!;
  const computed = (bist.price * bist.multiplier) / bist.margin;
  assert.ok(Math.abs(computed - bist.leverage) < 0.02);
  const position = buildPosition(50000, bist);
  assert.equal(position.lots, 2);
  assert.equal(position.notional, 2 * 17800 * 10);
});

test("EURTRY uses multiplier 1000", () => {
  const fx = CONTRACTS.find((c) => c.ticker === "EURTRY")!;
  const computed = (fx.price * fx.multiplier) / fx.margin;
  assert.ok(Math.abs(computed - fx.leverage) < 0.02);
});

test("XAUUSD converts USD margin to TL via USDTRY", () => {
  const gold = CONTRACTS.find((c) => c.ticker === "XAUUSD")!;
  const usdtry = CONTRACTS.find((c) => c.ticker === "USDTRY")!;
  const marginTl = gold.margin * usdtry.price;
  const position = buildPosition(marginTl * 2.5, gold);
  assert.equal(position.lots, 2);
  const notionalTl = 2 * gold.price * gold.multiplier * usdtry.price;
  assert.ok(Math.abs(position.notional - notionalTl) < 0.01);
});
