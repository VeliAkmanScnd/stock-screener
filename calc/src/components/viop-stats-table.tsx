"use client";

import * as React from "react";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  InputGroup,
} from "@/components/ui/input-group";
import { PlainInput } from "@/components/ui/plain-input";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { formatPercent } from "@/lib/format";
import {
  VIOP_BIAS_STATS,
  VIOP_BIAS_STRATEGY,
  type ViopBiasStat,
} from "@/lib/viop-stats";
import { cn } from "@/lib/utils";

type SortKey =
  | "ticker"
  | "trades"
  | "longResult"
  | "shortResult"
  | "result";

function signedPercent(value: number, digits = 1) {
  if (value > 0) return `+${formatPercent(value, digits)}`;
  if (value < 0) return `−${formatPercent(Math.abs(value), digits)}`;
  return formatPercent(0, digits);
}

function tone(value: number) {
  if (value > 0) return "text-gain";
  if (value < 0) return "text-loss";
  return "text-muted-foreground";
}

function cellTone(value: number) {
  return cn(
    "text-right font-mono tabular-nums",
    value > 0 && "bg-gain-muted/50 text-gain",
    value < 0 && "bg-loss-muted/50 text-loss",
  );
}

export function ViopStatsTable({
  selectedTicker,
  onSelect,
}: {
  selectedTicker?: string;
  onSelect: (ticker: string) => void;
}) {
  const [query, setQuery] = React.useState("");
  const [sortKey, setSortKey] = React.useState<SortKey>("result");
  const [sortDir, setSortDir] = React.useState<"desc" | "asc">("desc");

  function toggleSort(key: SortKey) {
    if (sortKey === key) {
      setSortDir((dir) => (dir === "desc" ? "asc" : "desc"));
      return;
    }
    setSortKey(key);
    setSortDir(key === "ticker" ? "asc" : "desc");
  }

  const rows = React.useMemo(() => {
    const q = query.trim().toLocaleLowerCase("tr-TR");
    const filtered = q
      ? VIOP_BIAS_STATS.filter((row) =>
          row.ticker.toLocaleLowerCase("tr-TR").includes(q),
        )
      : VIOP_BIAS_STATS;
    const copy = [...filtered];
    copy.sort((a, b) => {
      const left = a[sortKey];
      const right = b[sortKey];
      if (typeof left === "string" && typeof right === "string") {
        const cmp = left.localeCompare(right, "tr");
        return sortDir === "asc" ? cmp : -cmp;
      }
      const cmp = Number(left) - Number(right);
      return sortDir === "asc" ? cmp : -cmp;
    });
    return copy;
  }, [query, sortKey, sortDir]);

  const arrow = (key: SortKey) =>
    sortKey === key ? (sortDir === "desc" ? " ↓" : " ↑") : "";

  return (
    <Card className="ring-ticker/20">
      <CardHeader className="border-b border-ticker/15">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <CardTitle className="text-ticker">İstatistik</CardTitle>
            <CardDescription>
              {VIOP_BIAS_STRATEGY} · long/short işlem sayısı, oran ve net sonuç.
              Satıra tıklayınca dayanak seçilir. Varsayılan sıra sonuç yüzdesidir.
            </CardDescription>
          </div>
          <InputGroup className="h-9 sm:max-w-64">
            <PlainInput
              placeholder="Kod ara"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
            />
          </InputGroup>
        </div>
        <div className="flex flex-wrap gap-1.5">
          {(
            [
              ["result", "Sonuç %"],
              ["longResult", "Long sonuç"],
              ["shortResult", "Short sonuç"],
              ["trades", "İşlem"],
              ["ticker", "Kod"],
            ] as const
          ).map(([key, label]) => (
            <Button
              key={key}
              type="button"
              size="xs"
              variant={sortKey === key ? "default" : "outline"}
              className={
                sortKey === key
                  ? undefined
                  : "border-ticker/20 text-ticker hover:bg-ticker-muted"
              }
              onClick={() => toggleSort(key)}
            >
              {label}
              {arrow(key)}
            </Button>
          ))}
        </div>
      </CardHeader>
      <CardContent className="px-0">
        <Table className="min-w-[64rem]">
          <TableHeader>
            <TableRow className="hover:bg-transparent">
              <TableHead className="text-ticker">Kod</TableHead>
              <TableHead className="text-right text-gain">L+</TableHead>
              <TableHead className="text-right text-loss">L−</TableHead>
              <TableHead className="text-right text-gain">L oran+</TableHead>
              <TableHead className="text-right text-loss">L oran−</TableHead>
              <TableHead className="text-right text-gain">S+</TableHead>
              <TableHead className="text-right text-loss">S−</TableHead>
              <TableHead className="text-right text-gain">S oran+</TableHead>
              <TableHead className="text-right text-loss">S oran−</TableHead>
              <TableHead className="text-right text-ticker">İşlem</TableHead>
              <TableHead className="text-right text-gain">Long %</TableHead>
              <TableHead className="text-right text-loss">Short %</TableHead>
              <TableHead className="text-right text-ticker">Sonuç %</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.length === 0 ? (
              <TableRow>
                <TableCell
                  colSpan={13}
                  className="py-8 text-center text-muted-foreground"
                >
                  Eşleşen kod yok.
                </TableCell>
              </TableRow>
            ) : (
              rows.map((row) => (
                <StatRow
                  key={row.ticker}
                  row={row}
                  selected={selectedTicker === row.ticker}
                  onSelect={onSelect}
                />
              ))
            )}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}

function StatRow({
  row,
  selected,
  onSelect,
}: {
  row: ViopBiasStat;
  selected: boolean;
  onSelect: (ticker: string) => void;
}) {
  return (
    <TableRow
      data-state={selected ? "selected" : undefined}
      tabIndex={0}
      className={cn("cursor-pointer", selected && "bg-ticker-muted/50")}
      onClick={() => onSelect(row.ticker)}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          onSelect(row.ticker);
        }
      }}
    >
      <TableCell className="font-mono text-xs font-semibold text-ticker">
        {row.ticker}
      </TableCell>
      <TableCell className="text-right font-mono tabular-nums text-gain">
        {row.longWin}
      </TableCell>
      <TableCell className="text-right font-mono tabular-nums text-loss">
        {row.longLoss}
      </TableCell>
      <TableCell className={cn("text-right font-mono tabular-nums", tone(row.longWinPct))}>
        {signedPercent(row.longWinPct, 1)}
      </TableCell>
      <TableCell className={cn("text-right font-mono tabular-nums", tone(row.longLossPct))}>
        {signedPercent(row.longLossPct, 1)}
      </TableCell>
      <TableCell className="text-right font-mono tabular-nums text-gain">
        {row.shortWin}
      </TableCell>
      <TableCell className="text-right font-mono tabular-nums text-loss">
        {row.shortLoss}
      </TableCell>
      <TableCell className={cn("text-right font-mono tabular-nums", tone(row.shortWinPct))}>
        {signedPercent(row.shortWinPct, 1)}
      </TableCell>
      <TableCell className={cn("text-right font-mono tabular-nums", tone(row.shortLossPct))}>
        {signedPercent(row.shortLossPct, 1)}
      </TableCell>
      <TableCell className="text-right font-mono tabular-nums text-ticker">
        {row.trades}
      </TableCell>
      <TableCell className={cellTone(row.longResult)}>
        {signedPercent(row.longResult, 1)}
      </TableCell>
      <TableCell className={cellTone(row.shortResult)}>
        {signedPercent(row.shortResult, 1)}
      </TableCell>
      <TableCell
        className={cn(cellTone(row.result), "font-semibold")}
      >
        {signedPercent(row.result, 1)}
      </TableCell>
    </TableRow>
  );
}
