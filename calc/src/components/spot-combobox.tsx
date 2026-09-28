"use client";

import * as React from "react";
import {
  MARKET_LABELS,
  MARKET_ORDER,
  searchSpotStocks,
  SPOT_STOCKS,
  type SpotMarket,
  type SpotStock,
} from "@/lib/spot-stocks";
import { formatPrice } from "@/lib/format";
import { cn } from "@/lib/utils";

type SpotComboboxProps = {
  value?: SpotStock;
  onChange: (stock: SpotStock) => void;
  market?: SpotMarket | "all";
};

export function SpotCombobox({
  value,
  onChange,
  market = "all",
}: SpotComboboxProps) {
  const [query, setQuery] = React.useState("");
  const results = searchSpotStocks(query, market);
  const selectPool =
    !market || market === "all"
      ? SPOT_STOCKS
      : SPOT_STOCKS.filter((stock) => stock.markets.includes(market));

  function selectTicker(ticker: string) {
    const next = SPOT_STOCKS.find((stock) => stock.ticker === ticker);
    if (next) {
      onChange(next);
      setQuery("");
    }
  }

  return (
    <div className="flex flex-col gap-2">
      <select
        id="spot-stock"
        value={value?.ticker ?? ""}
        onChange={(event) => selectTicker(event.target.value)}
        className="stock-select h-11 w-full rounded-lg border border-input px-3 font-mono text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
      >
        <option value="">Hisse seçin</option>
        {selectPool.map((stock) => (
          <option key={stock.ticker} value={stock.ticker}>
            {stock.ticker} — {stock.name}
          </option>
        ))}
      </select>

      <input
        type="search"
        value={query}
        autoComplete="off"
        placeholder="THYAO, GARAN, çimento..."
        onChange={(event) => setQuery(event.target.value)}
        className="h-9 w-full rounded-lg border border-input bg-transparent px-3 text-sm outline-none placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 dark:bg-input/30"
      />

      <div
        role="listbox"
        className="max-h-72 overflow-y-auto rounded-lg ring-1 ring-ticker/25"
      >
        {results.length === 0 ? (
          <p className="px-3 py-6 text-center text-sm text-muted-foreground">
            Eşleşen hisse bulunamadı.
          </p>
        ) : (
          results.map((stock) => {
            const selected = value?.ticker === stock.ticker;
            return (
              <button
                key={stock.ticker}
                type="button"
                role="option"
                aria-selected={selected}
                className={cn(
                  "grid w-full grid-cols-[6.5rem_minmax(0,1fr)_auto] items-center gap-x-3 px-3 py-2 text-left text-sm hover:bg-ticker-muted",
                  selected && "bg-ticker-muted",
                )}
                onClick={() => selectTicker(stock.ticker)}
              >
                <span className="row-span-2 font-mono text-xs font-semibold tracking-wide text-ticker">
                  {stock.ticker}
                </span>
                <span className="min-w-0 truncate text-foreground">
                  {stock.name}
                </span>
                <span className="row-span-2 shrink-0 text-right font-mono text-xs tabular-nums text-warn">
                  {stock.referencePrice != null
                    ? formatPrice(stock.referencePrice)
                    : "—"}
                </span>
                <span className="col-start-2 text-[11px] text-muted-foreground">
                  {stock.markets.map((item) => MARKET_LABELS[item]).join(" · ")}
                </span>
              </button>
            );
          })
        )}
      </div>
      <p className="text-[11px] text-muted-foreground">
        {MARKET_ORDER.map((item) => MARKET_LABELS[item]).join(" · ")} ·{" "}
        {selectPool.length} hisse
      </p>
    </div>
  );
}
