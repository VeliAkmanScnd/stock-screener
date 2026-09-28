"use client";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { RankingSortChips } from "@/components/ranking-sort-chips";
import { HypeImpactBadge } from "@/components/hype-cells";
import { formatCompactTL, formatMoney, formatPercent, formatRelativeVolume } from "@/lib/format";
import {
  SCREENER_SORT_LABELS,
  rankingMetric,
  type RankedStat,
  type ScreenerSort,
} from "@/lib/screener";
import { cn } from "@/lib/utils";

type Leader = {
  ticker: string;
  stats: RankedStat;
};

type ScreenerPanelProps = {
  status: "loading" | "ok" | "error";
  updatedAt?: string;
  sortKey: ScreenerSort;
  onSortKey: (key: ScreenerSort) => void;
  leaders: Leader[];
  selectedTicker?: string;
  onSelect: (ticker: string) => void;
  loadingHint: string;
};

export function ScreenerPanel({
  status,
  updatedAt,
  sortKey,
  onSortKey,
  leaders,
  selectedTicker,
  onSelect,
  loadingHint,
}: ScreenerPanelProps) {
  return (
    <Card className="ring-ticker/25">
      <CardHeader className="border-b border-ticker/15">
        <CardTitle className="text-ticker">Hacim, volatilite, değer ve hype</CardTitle>
        <CardDescription>
          20 günlük ortalama TL hacmi, gerçekleşen volatilite, piyasa değeri ve
          7 günlük hype (göreli hacim, şok, haber/KAP, Trends, Reddit).
          Hacim + vol, Hacim + vol + değer ve Hacim + vol + hype ayrı sıralamalardır.
          {status === "ok" && updatedAt
            ? ` Yahoo · ${new Date(updatedAt).toLocaleTimeString("tr-TR", { hour: "2-digit", minute: "2-digit" })}`
            : null}
          {status === "loading" ? " Veriler yükleniyor…" : null}
          {status === "error" ? " Veri alınamadı; sıralama listede kalır." : null}
        </CardDescription>
        <RankingSortChips
          sortKey={sortKey}
          onSortKey={onSortKey}
          size="sm"
        />
      </CardHeader>
      <CardContent>
        {leaders.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            {status === "loading" ? loadingHint : "Sıralama için henüz hacim verisi yok."}
          </p>
        ) : (
          <div className="grid gap-2 sm:grid-cols-5">
            {leaders.map((row, index) => {
              const selected = selectedTicker === row.ticker;
              return (
                <button
                  key={row.ticker}
                  type="button"
                  className={cn(
                    "flex flex-col gap-1 rounded-lg px-3 py-2 text-left ring-1 ring-ticker/20 hover:bg-ticker-muted",
                    selected && "bg-ticker-muted ring-ticker/50",
                  )}
                  onClick={() => onSelect(row.ticker)}
                >
                  <span className="text-[11px] text-muted-foreground">
                    #{index + 1}{" "}
                    {SCREENER_SORT_LABELS[sortKey === "default" ? "score" : sortKey]}
                  </span>
                  <span className="font-mono text-sm font-semibold text-ticker">
                    {row.ticker}
                  </span>
                  <span className="font-mono text-xs text-warn">
                    {sortKey === "marketCap"
                      ? row.stats.marketCap
                        ? formatCompactTL(row.stats.marketCap)
                        : "—"
                      : sortKey === "relativeVolume" ||
                          sortKey === "hype" ||
                          sortKey === "scoreHype"
                        ? row.stats.relativeVolume != null
                          ? `göreli ${formatRelativeVolume(row.stats.relativeVolume)}`
                          : formatCompactTL(row.stats.avgVolumeTl)
                        : formatCompactTL(row.stats.avgVolumeTl)}
                  </span>
                  <span className="font-mono text-xs text-gain">
                    vol {formatPercent(row.stats.volatility, 0)} ·{" "}
                    {sortKey === "relativeVolume"
                      ? formatRelativeVolume(row.stats.relativeVolume)
                      : `${
                          sortKey === "hype"
                            ? "hype"
                            : sortKey === "scoreHype"
                              ? "h+v+h"
                              : "skor"
                        } ${formatMoney(
                          rankingMetric(
                            row.stats,
                            sortKey === "default" ? "score" : sortKey,
                          ),
                          0,
                        )}`}
                  </span>
                  <HypeImpactBadge impact={row.stats.hypeImpact} />
                </button>
              );
            })}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
