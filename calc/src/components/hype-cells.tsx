"use client";

import { Badge } from "@/components/ui/badge";
import { formatMoney, formatRelativeVolume } from "@/lib/format";
import {
  HYPE_IMPACT_LABELS,
  type HypeImpact,
  type RankedStat,
} from "@/lib/screener";
import { cn } from "@/lib/utils";

export const HYPE_EXTRA_COLUMNS = 3;

export function HypeImpactBadge({
  impact,
}: {
  impact?: HypeImpact | null;
}) {
  const value: HypeImpact = impact ?? "unknown";
  return (
    <Badge
      variant="outline"
      title="Hype sonrası +1g/+5g getiri; sıralamayı değiştirmez."
      className={cn(
        "h-4 max-w-full px-1.5 text-[10px] font-medium",
        value === "ongoing" && "border-gain/40 bg-gain-muted text-gain",
        value === "faded" && "border-loss/40 bg-loss-muted text-loss",
        value === "unknown" && "border-ticker/20 text-muted-foreground",
      )}
    >
      {HYPE_IMPACT_LABELS[value]}
    </Badge>
  );
}

export function HypeScoreCell({ item }: { item?: RankedStat }) {
  if (!item) return "—";
  return (
    <div className="flex flex-col items-end gap-0.5">
      <span>{formatMoney(item.hype, 0)}</span>
      <HypeImpactBadge impact={item.hypeImpact} />
    </div>
  );
}

export function RelativeVolumeCell({
  item,
  loading,
}: {
  item?: RankedStat;
  loading?: boolean;
}) {
  if (item?.relativeVolume != null) {
    return formatRelativeVolume(item.relativeVolume);
  }
  return loading ? "…" : "—";
}

export function NewsRedditCell({
  item,
  loading,
  kap,
}: {
  item?: RankedStat;
  loading?: boolean;
  kap?: boolean;
}) {
  if (!item) return loading ? "…" : "—";
  const hasNews = item.newsCount != null || item.kapCount != null;
  const news = (item.newsCount ?? 0) + (item.kapCount ?? 0);
  const redditMissing = item.redditStatus === "unavailable";
  const newsLabel = hasNews ? String(news) : "—";
  const redditLabel = redditMissing
    ? "Reddit alınamadı"
    : String(item.redditCount ?? 0);
  const xMissing = item.twitterStatus === "unavailable";
  const tgMissing = item.telegramStatus === "unavailable";
  const xLabel = xMissing
    ? "X—"
    : item.twitterGrowth != null
      ? `X×${item.twitterGrowth.toFixed(1)}`
      : `X${item.twitterCount ?? 0}`;
  const tgLabel = tgMissing
    ? "TG—"
    : item.telegramGrowth != null
      ? `TG×${item.telegramGrowth.toFixed(1)}`
      : `TG${item.telegramCount ?? 0}`;
  return (
    <span
      className="whitespace-nowrap"
      title={
        kap
          ? "Haber+KAP / Reddit / X büyüme / Telegram"
          : "Haber / Reddit / X büyüme / Telegram"
      }
    >
      {newsLabel}
      {" / "}
      <span className={redditMissing ? "text-muted-foreground" : undefined}>
        {redditLabel}
      </span>
      {" / "}
      <span className={xMissing ? "text-muted-foreground" : undefined}>
        {xLabel}
      </span>
      {" / "}
      <span className={tgMissing ? "text-muted-foreground" : undefined}>
        {tgLabel}
      </span>
    </span>
  );
}
