import raw from "../../data/us-screener.json";

export type UsExchange = "nasdaq" | "nyse";

export type UsStock = {
  ticker: string;
  name: string;
  exchange: UsExchange;
  yahoo: string;
};

const stocks: UsStock[] = (raw as UsStock[]).map((row) => ({
  ticker: row.ticker,
  name: row.name,
  exchange: row.exchange,
  yahoo: row.yahoo,
}));

export const NASDAQ_STOCKS: UsStock[] = stocks.filter(
  (stock) => stock.exchange === "nasdaq",
);

export const NYSE_STOCKS: UsStock[] = stocks.filter(
  (stock) => stock.exchange === "nyse",
);

export const US_STOCKS: UsStock[] = [...NASDAQ_STOCKS, ...NYSE_STOCKS];
