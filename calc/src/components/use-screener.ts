"use client";

import * as React from "react";
import { splitScreenerRows, type MarketStat } from "@/lib/screener";

export type ListingName = { ticker: string; name: string };

type Maps = {
  stats: Map<string, MarketStat>;
  nasdaq: Map<string, MarketStat>;
  nyse: Map<string, MarketStat>;
  nasdaqNames: ListingName[];
  nyseNames: ListingName[];
  complete: boolean;
};

type ScreenerState =
  | ({ status: "loading"; updatedAt?: undefined } & Maps)
  | ({ status: "ok"; updatedAt: string } & Maps)
  | ({ status: "error"; updatedAt?: undefined } & Maps);

function emptyMaps(): Maps {
  return {
    stats: new Map(),
    nasdaq: new Map(),
    nyse: new Map(),
    nasdaqNames: [],
    nyseNames: [],
    complete: false,
  };
}

export function useScreener(): ScreenerState {
  const [state, setState] = React.useState<ScreenerState>({
    status: "loading",
    ...emptyMaps(),
  });

  React.useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;

    function load() {
      fetch("/api/screener")
        .then((response) => {
          if (!response.ok) throw new Error(String(response.status));
          return response.json();
        })
        .then(
          (payload: {
            rows?: MarketStat[];
            updatedAt?: string;
            complete?: boolean;
            names?: { nasdaq?: ListingName[]; nyse?: ListingName[] };
          }) => {
            if (cancelled) return;
            const rows = Array.isArray(payload.rows) ? payload.rows : [];
            const split = splitScreenerRows(rows);
            const nasdaqNames = Array.isArray(payload.names?.nasdaq)
              ? payload.names.nasdaq
              : [];
            const nyseNames = Array.isArray(payload.names?.nyse)
              ? payload.names.nyse
              : [];
            const complete = Boolean(payload.complete);
            const hasData = rows.length > 0 || nasdaqNames.length > 0;
            if (!hasData) throw new Error("empty");
            setState({
              status: "ok",
              stats: split.bist,
              nasdaq: split.nasdaq,
              nyse: split.nyse,
              nasdaqNames,
              nyseNames,
              complete,
              updatedAt: payload.updatedAt ?? "",
            });
            if (!complete) {
              timer = setTimeout(load, 4000);
            }
          },
        )
        .catch(() => {
          if (cancelled) return;
          setState((current) =>
            current.status === "ok"
              ? current
              : { status: "error", ...emptyMaps() },
          );
        });
    }

    load();
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, []);

  return state;
}
