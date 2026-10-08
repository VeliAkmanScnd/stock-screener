"use client";

import * as React from "react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { InputGroup } from "@/components/ui/input-group";
import { PlainInput } from "@/components/ui/plain-input";
import {
  Table,
  TableBody,
  TableCell,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  ColumnFilterHead,
  compareColumnValues,
  matchesColumnFilter,
  type ColumnFilter,
  type ColumnSort,
} from "@/components/column-filter-head";
import { RankingFilters } from "@/components/ranking-filters";
import { RankingSortChips } from "@/components/ranking-sort-chips";
import {
  HYPE_EXTRA_COLUMNS,
  HypeScoreCell,
  NewsRedditCell,
  RelativeVolumeCell,
} from "@/components/hype-cells";
import { formatCompactMoney, formatMoney, formatPercent, formatPrice } from "@/lib/format";
import {
  DEFAULT_RANKING_FILTER,
  rankAndFilter,
  type RankingFilter,
} from "@/lib/ranking-filter";
import {
  rankForTickers,
  type MarketStat,
  type ScreenerSort,
} from "@/lib/screener";

export type RankingName = {
  ticker: string;
  name: string;
};

type MarketRankingTableProps = {
  title: string;
  description: string;
  names: RankingName[];
  stats: Map<string, MarketStat>;
  status: "loading" | "ok" | "error";
  complete?: boolean;
  currency: "TL" | "USD";
};

export function MarketRankingTable({
  title,
  description,
  names,
  stats,
  status,
  complete = true,
  currency,
}: MarketRankingTableProps) {
  const [sortKey, setSortKey] = React.useState<ScreenerSort>("score");
  const [colSort, setColSort] = React.useState<ColumnSort | null>(null);
  const [colFilters, setColFilters] = React.useState<Record<string, ColumnFilter>>({});
  const [query, setQuery] = React.useState("");
  const [filter, setFilter] = React.useState<RankingFilter>(DEFAULT_RANKING_FILTER);

  const ranked = rankForTickers(
    names.map((row) => row.ticker),
    stats,
  );
  const searched = names.filter((row) => {
    const q = query.trim().toLocaleLowerCase("tr-TR");
    if (!q) return true;
    return (
      row.ticker.toLocaleLowerCase("tr-TR").includes(q) ||
      row.name.toLocaleLowerCase("tr-TR").includes(q)
    );
  });

  function cellValue(row: RankingName, key: string): number | string | null {
    const item = ranked.get(row.ticker);
    switch (key) {
      case "ticker":
        return row.ticker;
      case "name":
        return row.name;
      case "score":
        return item?.score ?? null;
      case "scoreValue":
        return item?.scoreValue ?? null;
      case "hype":
        return item?.hype ?? null;
      case "price":
        return item?.lastPrice ?? null;
      case "volume":
        return item?.avgVolumeTl ?? null;
      case "relativeVolume":
        return item?.relativeVolume ?? null;
      case "volatility":
        return item?.volatility ?? null;
      case "marketCap":
        return item?.marketCap && item.marketCap > 0 ? item.marketCap : null;
      case "news":
        if (!item || (item.newsCount == null && item.redditCount == null)) return null;
        return (item.newsCount ?? 0) + (item.redditCount ?? 0);
      default:
        return null;
    }
  }

  function setColumnFilter(key: string, next: ColumnFilter | null) {
    setColFilters((prev) => {
      const copy = { ...prev };
      if (!next) delete copy[key];
      else copy[key] = next;
      return copy;
    });
  }

  const textOptions = (key: "ticker" | "name") =>
    [...new Set(searched.map((row) => String(cellValue(row, key))))].sort((a, b) =>
      a.localeCompare(b, "tr"),
    );
  const headerSort: ColumnSort | null =
    colSort ??
    (sortKey === "default"
      ? null
      : { key: sortKey === "scoreHype" ? "hype" : sortKey, dir: "desc" });
  const columnMatched = searched.filter((row) =>
    Object.entries(colFilters).every(([key, columnFilter]) =>
      matchesColumnFilter(columnFilter, cellValue(row, key)),
    ),
  );
  const rankedRows = rankAndFilter(
    columnMatched,
    ranked,
    filter,
    sortKey,
    query.trim().length > 0,
  );
  const rows = colSort
    ? [...rankedRows].sort((left, right) =>
        compareColumnValues(cellValue(left, colSort.key), cellValue(right, colSort.key), colSort.dir),
      )
    : rankedRows;

  return (
    <Card className="ring-ticker/20">
      <CardHeader className="border-b border-ticker/15">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <CardTitle className="text-ticker">{title}</CardTitle>
            <CardDescription>
              {description}{" "}
              {status === "loading" ? "Hacim yükleniyor…" : null}
              {status === "ok" && !complete ? "Liste yenileniyor…" : null}
              {status === "error" ? "Hacim alınamadı." : null}
            </CardDescription>
          </div>
          <InputGroup className="h-9 sm:max-w-64">
            <PlainInput
              placeholder="Kod veya şirket ara"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
            />
          </InputGroup>
        </div>
        <RankingSortChips
          sortKey={sortKey}
          onSortKey={(key) => {
            setSortKey(key);
            setColSort(null);
          }}
        />
        <RankingFilters
          filter={filter}
          onChange={setFilter}
          currency={currency}
          shown={rows.length}
          universe={names.length}
        />
      </CardHeader>
      <CardContent className="px-0">
        <Table className="min-w-[64rem]">
          <TableHeader>
            <TableRow className="hover:bg-transparent">
              <ColumnFilterHead columnKey="ticker" label="Kod" type="text" className="text-ticker" sort={headerSort} filter={colFilters.ticker} options={textOptions("ticker")} onSort={setColSort} onFilter={(next) => setColumnFilter("ticker", next)} />
              <ColumnFilterHead columnKey="name" label="Şirket" type="text" className="text-muted-foreground" sort={headerSort} filter={colFilters.name} options={textOptions("name")} onSort={setColSort} onFilter={(next) => setColumnFilter("name", next)} />
              <ColumnFilterHead columnKey="score" label="Skor" type="number" align="right" className="text-gain" sort={headerSort} filter={colFilters.score} onSort={setColSort} onFilter={(next) => setColumnFilter("score", next)} />
              <ColumnFilterHead columnKey="scoreValue" label="Skor+değer" type="number" align="right" className="text-gain" sort={headerSort} filter={colFilters.scoreValue} onSort={setColSort} onFilter={(next) => setColumnFilter("scoreValue", next)} />
              <ColumnFilterHead columnKey="hype" label="Hype" type="number" align="right" className="text-gain" sort={headerSort} filter={colFilters.hype} onSort={setColSort} onFilter={(next) => setColumnFilter("hype", next)} />
              <ColumnFilterHead columnKey="price" label="Fiyat" type="number" align="right" className="text-warn" sort={headerSort} filter={colFilters.price} onSort={setColSort} onFilter={(next) => setColumnFilter("price", next)} />
              <ColumnFilterHead columnKey="volume" label="Hacim 20g" type="number" align="right" className="text-ticker" sort={headerSort} filter={colFilters.volume} onSort={setColSort} onFilter={(next) => setColumnFilter("volume", next)} />
              <ColumnFilterHead columnKey="relativeVolume" label="Göreli hacim" type="number" align="right" className="text-ticker" sort={headerSort} filter={colFilters.relativeVolume} onSort={setColSort} onFilter={(next) => setColumnFilter("relativeVolume", next)} />
              <ColumnFilterHead columnKey="volatility" label="Volatilite" type="number" align="right" className="text-warn" sort={headerSort} filter={colFilters.volatility} onSort={setColSort} onFilter={(next) => setColumnFilter("volatility", next)} />
              <ColumnFilterHead columnKey="marketCap" label="Piyasa değeri" type="number" align="right" className="text-ticker" sort={headerSort} filter={colFilters.marketCap} onSort={setColSort} onFilter={(next) => setColumnFilter("marketCap", next)} />
              <ColumnFilterHead columnKey="news" label="Haber / Reddit" type="number" align="right" className="text-muted-foreground" sort={headerSort} filter={colFilters.news} onSort={setColSort} onFilter={(next) => setColumnFilter("news", next)} />
            </TableRow>
          </TableHeader>
          <TableBody>
            {names.length === 0 ? (
              <TableRow>
                <TableCell colSpan={8 + HYPE_EXTRA_COLUMNS} className="py-8 text-center text-muted-foreground">
                  {status === "error"
                    ? "Liste alınamadı."
                    : "Nasdaq / NYSE listesi yükleniyor…"}
                </TableCell>
              </TableRow>
            ) : ranked.size === 0 && (status === "loading" || !complete) ? (
              <TableRow>
                <TableCell colSpan={8 + HYPE_EXTRA_COLUMNS} className="py-8 text-center text-muted-foreground">
                  Hacim ve volatilite yükleniyor…
                </TableCell>
              </TableRow>
            ) : rows.length === 0 ? (
              <TableRow>
                <TableCell
                  colSpan={8 + HYPE_EXTRA_COLUMNS}
                  className="py-8 text-center text-muted-foreground"
                >
                  Eşiği geçen hisse yok. Filtreleri gevşetin veya Tümü’ne geçin.
                </TableCell>
              </TableRow>
            ) : (
              rows.map((row) => {
                const item = ranked.get(row.ticker);
                const price = item?.lastPrice;
                return (
                  <TableRow key={row.ticker} className="rank-row">
                    <TableCell className="font-mono text-xs font-semibold text-ticker">
                      {row.ticker}
                    </TableCell>
                    <TableCell>{row.name}</TableCell>
                    <TableCell className="text-right font-mono text-gain">
                      {item ? formatMoney(item.score, 0) : "—"}
                    </TableCell>
                    <TableCell className="text-right font-mono text-gain">
                      {item ? formatMoney(item.scoreValue, 0) : "—"}
                    </TableCell>
                    <TableCell className="text-right font-mono text-gain">
                      <HypeScoreCell item={item} />
                    </TableCell>
                    <TableCell className="text-right font-mono text-warn">
                      {price != null
                        ? currency === "USD"
                          ? `${formatPrice(price)} $`
                          : formatPrice(price)
                        : "—"}
                    </TableCell>
                    <TableCell className="text-right font-mono text-ticker">
                      {item
                        ? formatCompactMoney(item.avgVolumeTl, currency)
                        : status === "loading"
                          ? "…"
                          : "—"}
                    </TableCell>
                    <TableCell className="text-right font-mono text-ticker">
                      <RelativeVolumeCell
                        item={item}
                        loading={status === "loading"}
                      />
                    </TableCell>
                    <TableCell className="text-right font-mono text-warn">
                      {item ? (
                        <span title={`Günlük ortalama |hareket| ${formatPercent(item.dailyMove)}`}>
                          {formatPercent(item.volatility, 1)}
                        </span>
                      ) : status === "loading" ? (
                        "…"
                      ) : (
                        "—"
                      )}
                    </TableCell>
                    <TableCell className="text-right font-mono text-ticker">
                      {item?.marketCap
                        ? formatCompactMoney(item.marketCap, currency)
                        : status === "loading"
                          ? "…"
                          : "—"}
                    </TableCell>
                    <TableCell className="text-right font-mono text-xs text-muted-foreground">
                      <NewsRedditCell item={item} loading={status === "loading"} />
                    </TableCell>
                  </TableRow>
                );
              })
            )}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}
