"use client";

import { Button } from "@/components/ui/button";
import {
  SCREENER_SORT_LABELS,
  type ScreenerSort,
} from "@/lib/screener";

const METRIC_SORTS: ScreenerSort[] = [
  "default",
  "volume",
  "relativeVolume",
  "volatility",
  "marketCap",
];

const SCORE_SORTS: ScreenerSort[] = ["score", "scoreValue"];
const HYPE_SORTS: ScreenerSort[] = ["hype", "scoreHype"];

type RankingSortChipsProps = {
  sortKey: ScreenerSort;
  onSortKey: (key: ScreenerSort) => void;
  size?: "xs" | "sm";
};

function Chip({
  sortKey,
  onSortKey,
  size,
  keyName,
}: RankingSortChipsProps & { keyName: ScreenerSort }) {
  const active = sortKey === keyName;
  return (
    <Button
      type="button"
      size={size}
      variant={active ? "default" : "outline"}
      className={
        active ? undefined : "border-ticker/20 text-ticker hover:bg-ticker-muted"
      }
      onClick={() => onSortKey(keyName)}
    >
      {SCREENER_SORT_LABELS[keyName]}
    </Button>
  );
}

export function RankingSortChips({
  sortKey,
  onSortKey,
  size = "xs",
}: RankingSortChipsProps) {
  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex flex-wrap gap-1.5">
        {METRIC_SORTS.map((key) => (
          <Chip
            key={key}
            keyName={key}
            size={size}
            sortKey={sortKey}
            onSortKey={onSortKey}
          />
        ))}
      </div>
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="text-[11px] tracking-wide text-muted-foreground uppercase">
          Skor
        </span>
        {SCORE_SORTS.map((key) => (
          <Chip
            key={key}
            keyName={key}
            size={size}
            sortKey={sortKey}
            onSortKey={onSortKey}
          />
        ))}
      </div>
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="text-[11px] tracking-wide text-muted-foreground uppercase">
          Hype
        </span>
        {HYPE_SORTS.map((key) => (
          <Chip
            key={key}
            keyName={key}
            size={size}
            sortKey={sortKey}
            onSortKey={onSortKey}
          />
        ))}
      </div>
    </div>
  );
}
