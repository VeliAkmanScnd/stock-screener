"use client";

import * as React from "react";
import {
  GROUP_LABELS,
  GROUP_ORDER,
  searchContracts,
  type Contract,
  type ContractGroup,
} from "@/lib/contracts";
import { formatLeverage, formatPrice } from "@/lib/format";
import { cn } from "@/lib/utils";
import { useViopContracts } from "@/components/use-viop-contracts";

type StockComboboxProps = {
  value?: Contract;
  onChange: (contract: Contract) => void;
  group?: ContractGroup | "all";
};

export function StockCombobox({
  value,
  onChange,
  group = "all",
}: StockComboboxProps) {
  const { contracts } = useViopContracts();
  const [query, setQuery] = React.useState("");
  const results = searchContracts(query, group);

  function selectTicker(ticker: string) {
    const next = contracts.find((contract) => contract.ticker === ticker);
    if (next) {
      onChange(next);
      setQuery("");
    }
  }

  return (
    <div className="flex flex-col gap-2">
      <select
        id="stock"
        value={value?.ticker ?? ""}
        onChange={(event) => selectTicker(event.target.value)}
        className="stock-select h-11 w-full rounded-lg border border-input px-3 font-mono text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
      >
        <option value="">Dayanak varlık seçin</option>
        {GROUP_ORDER.map((item) => (
          <optgroup key={item} label={GROUP_LABELS[item]}>
            {contracts
              .filter((contract) => contract.group === item)
              .map((contract) => (
                <option key={contract.ticker} value={contract.ticker}>
                  {contract.ticker} — {contract.name}
                </option>
              ))}
          </optgroup>
        ))}
      </select>

      <input
        type="search"
        value={query}
        autoComplete="off"
        placeholder="THYAO, BIST30, altın, USDTRY..."
        onChange={(event) => setQuery(event.target.value)}
        className="h-9 w-full rounded-lg border border-input bg-transparent px-3 text-sm outline-none placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 dark:bg-input/30"
      />

      <div
        role="listbox"
        className="max-h-72 overflow-y-auto rounded-lg ring-1 ring-ticker/25"
      >
        {results.length === 0 ? (
          <p className="px-3 py-6 text-center text-sm text-muted-foreground">
            Eşleşen sözleşme bulunamadı.
          </p>
        ) : (
          results.map((contract) => {
            const selected = value?.ticker === contract.ticker;
            return (
              <button
                key={contract.ticker}
                type="button"
                role="option"
                aria-selected={selected}
                className={cn(
                  "grid w-full grid-cols-[6.5rem_minmax(0,1fr)_auto] items-center gap-x-3 px-3 py-2 text-left text-sm hover:bg-ticker-muted",
                  selected && "bg-ticker-muted",
                )}
                onClick={() => selectTicker(contract.ticker)}
              >
                <span className="row-span-2 font-mono text-xs font-semibold tracking-wide text-ticker">
                  {contract.ticker}
                </span>
                <span className="min-w-0 truncate text-foreground">
                  {contract.name}
                </span>
                <span className="row-span-2 shrink-0 text-right font-mono text-xs tabular-nums">
                  <span className="text-gain">{formatLeverage(contract.leverage)}</span>
                  <span className="ml-3 text-warn">{formatPrice(contract.price)}</span>
                </span>
                <span className="col-start-2 text-[11px] text-muted-foreground">
                  {GROUP_LABELS[contract.group]}
                </span>
              </button>
            );
          })
        )}
      </div>
    </div>
  );
}
