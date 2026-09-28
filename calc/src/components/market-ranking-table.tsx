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
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
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
  const rows = rankAndFilter(
    searched,
    ranked,
    filter,
    sortKey,
    query.trim().length > 0,
  );

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
        <RankingSortChips sortKey={sortKey} onSortKey={setSortKey} />
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
              <TableHead className="text-ticker">Kod</TableHead>
              <TableHead className="text-muted-foreground">Şirket</TableHead>
              <TableHead
                aria-sort={sortKey === "score" ? "descending" : "none"}
                className="text-right text-gain"
              >
                Skor
              </TableHead>
              <TableHead
                aria-sort={sortKey === "scoreValue" ? "descending" : "none"}
                className="text-right text-gain"
              >
                Skor+değer
              </TableHead>
              <TableHead
                aria-sort={
                  sortKey === "hype" || sortKey === "scoreHype"
                    ? "descending"
                    : "none"
                }
                className="text-right text-gain"
              >
                Hype
              </TableHead>
              <TableHead className="text-right text-warn">Fiyat</TableHead>
              <TableHead
                aria-sort={sortKey === "volume" ? "descending" : "none"}
                className="text-right text-ticker"
              >
                Hacim 20g
              </TableHead>
              <TableHead
                aria-sort={
                  sortKey === "relativeVolume" ? "descending" : "none"
                }
                className="text-right text-ticker"
              >
                Göreli hacim
              </TableHead>
              <TableHead
                aria-sort={sortKey === "volatility" ? "descending" : "none"}
                className="text-right text-warn"
              >
                Volatilite
              </TableHead>
              <TableHead
                aria-sort={sortKey === "marketCap" ? "descending" : "none"}
                className="text-right text-ticker"
              >
                Piyasa değeri
              </TableHead>
              <TableHead className="text-right text-muted-foreground">
                Haber / Reddit
              </TableHead>
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
