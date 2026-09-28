import { marginTl, notionalTl, type Contract } from "./contracts";

export type Side = "long" | "short";

export type Position = {
  lots: number;
  maxLots: number;
  usedMargin: number;
  remaining: number;
  notional: number;
  leverage: number;
  units: number;
  marginPerLotTl: number;
};

export function maxLotsForAmount(amount: number, margin: number): number {
  if (!(amount > 0) || !(margin > 0)) return 0;
  return Math.floor(amount / margin);
}

export function clampLots(lots: number, max: number): number {
  if (!Number.isFinite(lots) || lots <= 0) return 0;
  return Math.min(Math.floor(lots), Math.max(0, max));
}

export function buildPosition(
  amount: number,
  contract: Contract,
  lots?: number,
): Position {
  const marginPerLotTl = marginTl(contract);
  const max = maxLotsForAmount(amount, marginPerLotTl);
  const n = lots == null ? max : clampLots(lots, max);
  const usedMargin = n * marginPerLotTl;
  const notional = notionalTl(n, contract);
  const leverage =
    contract.margin > 0
      ? (contract.price * contract.multiplier) / contract.margin
      : 0;

  return {
    lots: n,
    maxLots: max,
    usedMargin,
    remaining: Math.max(0, amount - usedMargin),
    notional,
    leverage,
    units: n * contract.multiplier,
    marginPerLotTl,
  };
}

export function priceAfterMove(price: number, percent: number): number {
  return price * (1 + percent / 100);
}

/** P&L for a price move. `percent` is signed: +1.5 means price up 1.5%. */
export function pnlForPriceMove(
  notional: number,
  percent: number,
  side: Side,
): number {
  const raw = notional * (percent / 100);
  return side === "long" ? raw : -raw;
}

export function returnOnMargin(pnl: number, usedMargin: number): number {
  if (!(usedMargin > 0)) return 0;
  return (pnl / usedMargin) * 100;
}

export function endingEquity(usedMargin: number, pnl: number): number {
  return usedMargin + pnl;
}
