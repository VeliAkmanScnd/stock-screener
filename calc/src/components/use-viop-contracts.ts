"use client";

import * as React from "react";
import {
  getContracts,
  getContractsUpdatedAt,
  setLiveContracts,
  subscribeContracts,
  type Contract,
} from "@/lib/contracts";

type LiveContract = Contract & { margin_rate_pct?: number };

function normalize(row: LiveContract): Contract | null {
  const ticker = String(row.ticker || "").trim().toUpperCase();
  if (!ticker) return null;
  const price = Number(row.price);
  const margin = Number(row.margin);
  const leverage = Number(row.leverage);
  const multiplier = Number(row.multiplier);
  if (!(price > 0) || !(margin > 0) || !(multiplier > 0)) return null;
  return {
    ticker,
    name: String(row.name || ticker),
    margin,
    price,
    leverage: leverage > 0 ? leverage : (price * multiplier) / margin,
    multiplier,
    currency: row.currency === "USD" ? "USD" : "TL",
    group: row.group as Contract["group"],
  };
}

export function useViopContracts(): {
  contracts: Contract[];
  updatedAt: string | null;
  status: "loading" | "ok" | "error";
} {
  const [contracts, setContracts] = React.useState<Contract[]>(() =>
    getContracts(),
  );
  const [updatedAt, setUpdatedAt] = React.useState<string | null>(() =>
    getContractsUpdatedAt(),
  );
  const [status, setStatus] = React.useState<"loading" | "ok" | "error">(
    "loading",
  );

  React.useEffect(() => {
    return subscribeContracts(() => {
      setContracts(getContracts());
      setUpdatedAt(getContractsUpdatedAt());
    });
  }, []);

  React.useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch("/api/viop-contracts", { cache: "no-store" });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        const rows = Array.isArray(data.contracts) ? data.contracts : [];
        const next = rows
          .map((row: LiveContract) => normalize(row))
          .filter((row: Contract | null): row is Contract => row != null);
        if (!cancelled && next.length) {
          setLiveContracts(next, data.updated_at ?? null);
          setStatus("ok");
        } else if (!cancelled) {
          setStatus("error");
        }
      } catch {
        if (!cancelled) setStatus("error");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  return { contracts, updatedAt, status };
}
