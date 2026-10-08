"use client";

import * as React from "react";
import { Button } from "@/components/ui/button";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { cn } from "@/lib/utils";

export type ColumnFilter =
  | { kind: "number"; min: string; max: string }
  | { kind: "text"; selected: string[] | null };

export type ColumnSort = { key: string; dir: "asc" | "desc" };

type ColumnFilterHeadProps = {
  columnKey: string;
  label: string;
  type: "number" | "text";
  align?: "left" | "right";
  className?: string;
  sort: ColumnSort | null;
  filter?: ColumnFilter;
  options?: string[];
  onSort: (sort: ColumnSort) => void;
  onFilter: (filter: ColumnFilter | null) => void;
};

function filterActive(filter?: ColumnFilter) {
  if (!filter) return false;
  if (filter.kind === "number") return filter.min !== "" || filter.max !== "";
  return filter.selected != null;
}

export function ColumnFilterHead({
  columnKey,
  label,
  type,
  align = "left",
  className,
  sort,
  filter,
  options = [],
  onSort,
  onFilter,
}: ColumnFilterHeadProps) {
  const [open, setOpen] = React.useState(false);
  const [min, setMin] = React.useState("");
  const [max, setMax] = React.useState("");
  const [picked, setPicked] = React.useState<string[] | null>(null);
  const [optionQuery, setOptionQuery] = React.useState("");
  const sorted = sort?.key === columnKey;
  const active = filterActive(filter);

  React.useEffect(() => {
    if (!open) return;
    if (filter?.kind === "number") {
      setMin(filter.min);
      setMax(filter.max);
    } else {
      setMin("");
      setMax("");
    }
    if (filter?.kind === "text") setPicked(filter.selected);
    else setPicked(null);
    setOptionQuery("");
  }, [open, filter]);

  function applyNumber() {
    if (min.trim() === "" && max.trim() === "") onFilter(null);
    else onFilter({ kind: "number", min: min.trim(), max: max.trim() });
    setOpen(false);
  }

  function applyText() {
    if (picked == null || picked.length === options.length) onFilter(null);
    else onFilter({ kind: "text", selected: picked });
    setOpen(false);
  }

  const mark = sorted ? (sort?.dir === "asc" ? " ↑" : " ↓") : "";

  return (
    <th
      className={cn(
        "h-10 px-2 align-middle text-xs font-medium whitespace-nowrap",
        align === "right" ? "text-right" : "text-left",
        className,
      )}
      aria-sort={
        sorted ? (sort?.dir === "asc" ? "ascending" : "descending") : "none"
      }
    >
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger
          className={cn(
            "inline-flex items-center gap-1 rounded-md px-1 py-0.5 hover:bg-muted",
            (sorted || active) && "text-foreground",
            align === "right" && "ml-auto",
          )}
          aria-label={`${label} sırala ve filtrele`}
        >
          <span>
            {label}
            {mark}
          </span>
          <span className={cn("text-[10px]", active ? "text-ticker" : "opacity-50")}>
            ▾
          </span>
        </PopoverTrigger>
        <PopoverContent align={align === "right" ? "end" : "start"} className="w-64 gap-2">
          <p className="text-xs font-medium">{label}</p>
          <div className="grid grid-cols-1 gap-1">
            <Button
              type="button"
              size="sm"
              variant={sorted && sort?.dir === "desc" ? "default" : "outline"}
              onClick={() => {
                onSort({ key: columnKey, dir: "desc" });
                setOpen(false);
              }}
            >
              {type === "number" ? "Büyükten küçüğe" : "Z → A"}
            </Button>
            <Button
              type="button"
              size="sm"
              variant={sorted && sort?.dir === "asc" ? "default" : "outline"}
              onClick={() => {
                onSort({ key: columnKey, dir: "asc" });
                setOpen(false);
              }}
            >
              {type === "number" ? "Küçükten büyüğe" : "A → Z"}
            </Button>
          </div>
          {type === "number" ? (
            <div className="flex flex-col gap-2 border-t border-border pt-2">
              <label className="flex items-center justify-between gap-2 text-xs">
                <span>En az</span>
                <input
                  type="number"
                  step="any"
                  value={min}
                  onChange={(event) => setMin(event.target.value)}
                  className="h-8 w-28 rounded-md border border-input bg-transparent px-2 text-right"
                  placeholder="—"
                />
              </label>
              <label className="flex items-center justify-between gap-2 text-xs">
                <span>En çok</span>
                <input
                  type="number"
                  step="any"
                  value={max}
                  onChange={(event) => setMax(event.target.value)}
                  className="h-8 w-28 rounded-md border border-input bg-transparent px-2 text-right"
                  placeholder="—"
                />
              </label>
              <p className="text-[11px] text-muted-foreground">
                Yalnızca en az: bu değer ve üstü. Yalnızca en çok: bu değer ve altı. İkisi birden: aralık.
              </p>
              <div className="flex justify-end gap-1">
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  onClick={() => {
                    setMin("");
                    setMax("");
                    onFilter(null);
                    setOpen(false);
                  }}
                >
                  Temizle
                </Button>
                <Button type="button" size="sm" onClick={applyNumber}>
                  Uygula
                </Button>
              </div>
            </div>
          ) : (
            <div className="flex max-h-48 flex-col gap-1 overflow-auto border-t border-border pt-2">
              {options.length > 12 ? (
                <input
                  value={optionQuery}
                  onChange={(event) => setOptionQuery(event.target.value)}
                  placeholder="Listede ara"
                  className="mb-1 h-8 rounded-md border border-input bg-transparent px-2 text-xs"
                />
              ) : null}
              {options
                .filter((option) =>
                  option.toLocaleLowerCase("tr-TR").includes(optionQuery.trim().toLocaleLowerCase("tr-TR")),
                )
                .slice(0, 80)
                .map((option) => {
                const checked = picked == null || picked.includes(option);
                return (
                  <label key={option} className="flex items-center gap-2 text-xs">
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={(event) => {
                        const base = picked ?? options;
                        const next = event.target.checked
                          ? [...new Set([...base, option])]
                          : base.filter((item) => item !== option);
                        setPicked(next);
                      }}
                    />
                    <span>{option}</span>
                  </label>
                );
              })}
              <div className="mt-1 flex justify-end gap-1">
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  onClick={() => {
                    setPicked(null);
                    onFilter(null);
                    setOpen(false);
                  }}
                >
                  Temizle
                </Button>
                <Button type="button" size="sm" onClick={applyText}>
                  Uygula
                </Button>
              </div>
            </div>
          )}
        </PopoverContent>
      </Popover>
    </th>
  );
}

export function compareColumnValues(
  left: number | string | null,
  right: number | string | null,
  dir: "asc" | "desc",
): number {
  const leftMissing = left == null || left === "";
  const rightMissing = right == null || right === "";
  if (leftMissing && rightMissing) return 0;
  if (leftMissing) return 1;
  if (rightMissing) return -1;
  const cmp =
    typeof left === "number" && typeof right === "number"
      ? left - right
      : String(left).localeCompare(String(right), "tr");
  return dir === "asc" ? cmp : -cmp;
}

export function matchesColumnFilter(
  filter: ColumnFilter | undefined,
  value: number | string | null,
): boolean {
  if (!filter) return true;
  if (filter.kind === "number") {
    if (typeof value !== "number" || !Number.isFinite(value)) return false;
    if (filter.min !== "") {
      const min = Number(filter.min);
      if (Number.isFinite(min) && value < min) return false;
    }
    if (filter.max !== "") {
      const max = Number(filter.max);
      if (Number.isFinite(max) && value > max) return false;
    }
    return true;
  }
  if (filter.selected == null) return true;
  return filter.selected.includes(String(value ?? ""));
}
