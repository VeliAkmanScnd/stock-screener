import { clampLots, maxLotsForAmount } from "./calc";

export type SpotPosition = {
  lots: number;
  maxLots: number;
  usedCost: number;
  remaining: number;
  notional: number;
  price: number;
};

/** Cash equity: 1 lot = 1 pay. Lots = floor(TL / fiyat). */
export function buildSpotPosition(
  amount: number,
  price: number,
  lots?: number,
): SpotPosition {
  const max = maxLotsForAmount(amount, price);
  const n = lots == null ? max : clampLots(lots, max);
  const usedCost = n * price;

  return {
    lots: n,
    maxLots: max,
    usedCost,
    remaining: Math.max(0, amount - usedCost),
    notional: usedCost,
    price,
  };
}
