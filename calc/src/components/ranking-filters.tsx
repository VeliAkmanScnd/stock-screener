"use client";

import * as React from "react";
import { Button } from "@/components/ui/button";
import { InputGroup, InputGroupAddon, InputGroupText } from "@/components/ui/input-group";
import { PlainInput } from "@/components/ui/plain-input";
import { formatCompactMoney, parseTrNumber } from "@/lib/format";
import {
  DEFAULT_RANKING_FILTER,
  RANKING_TOP_PRESETS,
  parseVolumeThreshold,
  type RankingFilter,
} from "@/lib/ranking-filter";

type RankingFiltersProps = {
  filter: RankingFilter;
  onChange: (next: RankingFilter) => void;
  currency: "TL" | "USD";
  shown: number;
  universe: number;
};

export function RankingFilters({
  filter,
  onChange,
  currency,
  shown,
  universe,
}: RankingFiltersProps) {
  const [volumeInput, setVolumeInput] = React.useState(
    filter.minVolume > 0 ? formatCompactMoney(filter.minVolume, currency) : "",
  );
  const [volInput, setVolInput] = React.useState(
    filter.minVolatility > 0 ? String(filter.minVolatility) : "",
  );
  const [scoreInput, setScoreInput] = React.useState(
    filter.minScore > 0 ? String(filter.minScore) : "",
  );

  function commitVolume(raw: string) {
    setVolumeInput(raw);
    if (!raw.trim()) {
      onChange({ ...filter, minVolume: 0 });
      return;
    }
    const value = parseVolumeThreshold(raw);
    if (value == null || value < 0) return;
    onChange({ ...filter, minVolume: value });
  }

  function commitVolatility(raw: string) {
    setVolInput(raw);
    if (!raw.trim()) {
      onChange({ ...filter, minVolatility: 0 });
      return;
    }
    const value = parseTrNumber(raw);
    if (value == null || value < 0) return;
    onChange({ ...filter, minVolatility: value });
  }

  function commitScore(raw: string) {
    setScoreInput(raw);
    if (!raw.trim()) {
      onChange({ ...filter, minScore: 0 });
      return;
    }
    const value = parseTrNumber(raw);
    if (value == null || value < 0) return;
    onChange({ ...filter, minScore: value });
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-1.5">
        {RANKING_TOP_PRESETS.map((count) => (
          <Button
            key={count}
            type="button"
            size="xs"
            variant={filter.topN === count ? "default" : "outline"}
            className={
              filter.topN === count
                ? undefined
                : "border-ticker/20 text-ticker hover:bg-ticker-muted"
            }
            onClick={() => onChange({ ...filter, topN: count })}
          >
            İlk {count}
          </Button>
        ))}
        <Button
          type="button"
          size="xs"
          variant={filter.topN == null ? "default" : "outline"}
          className={
            filter.topN == null
              ? undefined
              : "border-ticker/20 text-ticker hover:bg-ticker-muted"
          }
          onClick={() => onChange({ ...filter, topN: null })}
        >
          Tümü
        </Button>
        <span className="text-xs text-muted-foreground">
          {shown.toLocaleString("tr-TR")} / {universe.toLocaleString("tr-TR")} hisse
        </span>
      </div>
      <div className="grid gap-2 sm:grid-cols-3">
        <label className="grid gap-1">
          <span className="text-[11px] tracking-wide text-muted-foreground uppercase">
            Min hacim 20g
          </span>
          <InputGroup className="h-9">
            <PlainInput
              inputMode="decimal"
              placeholder="20 Mn"
              value={volumeInput}
              onChange={(event) => commitVolume(event.target.value)}
            />
            <InputGroupAddon align="inline-end">
              <InputGroupText>{currency}</InputGroupText>
            </InputGroupAddon>
          </InputGroup>
        </label>
        <label className="grid gap-1">
          <span className="text-[11px] tracking-wide text-muted-foreground uppercase">
            Min volatilite
          </span>
          <InputGroup className="h-9">
            <InputGroupAddon align="inline-start">
              <InputGroupText>%</InputGroupText>
            </InputGroupAddon>
            <PlainInput
              inputMode="decimal"
              placeholder="30"
              value={volInput}
              onChange={(event) => commitVolatility(event.target.value)}
            />
          </InputGroup>
        </label>
        <label className="grid gap-1">
          <span className="text-[11px] tracking-wide text-muted-foreground uppercase">
            Min skor
          </span>
          <InputGroup className="h-9">
            <PlainInput
              inputMode="decimal"
              placeholder="60"
              value={scoreInput}
              onChange={(event) => commitScore(event.target.value)}
            />
          </InputGroup>
        </label>
      </div>
      {filter.topN !== DEFAULT_RANKING_FILTER.topN ||
      filter.minVolume > 0 ||
      filter.minVolatility > 0 ||
      filter.minScore > 0 ? (
        <button
          type="button"
          className="w-fit text-xs text-muted-foreground underline-offset-2 hover:text-foreground hover:underline"
          onClick={() => {
            setVolumeInput("");
            setVolInput("");
            setScoreInput("");
            onChange({ ...DEFAULT_RANKING_FILTER });
          }}
        >
          Varsayılana dön (ilk 100, hacim + vol)
        </button>
      ) : null}
    </div>
  );
}
