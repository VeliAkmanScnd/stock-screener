"use client";

import * as React from "react";
import {
  ArrowDownRightIcon,
  ArrowUpRightIcon,
  CoinsIcon,
  LayersIcon,
  MinusIcon,
  PlusIcon,
  TrendingDownIcon,
  TrendingUpIcon,
  WalletIcon,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
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
  InputGroupAddon,
  InputGroupButton,
  InputGroupText,
} from "@/components/ui/input-group";
import { PlainInput } from "@/components/ui/plain-input";
import { Label } from "@/components/ui/label";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { StockCombobox } from "@/components/stock-combobox";
import {
  buildPosition,
  endingEquity,
  pnlForPriceMove,
  priceAfterMove,
  returnOnMargin,
  type Side,
} from "@/lib/calc";
import {
  GROUP_LABELS,
  GROUP_ORDER,
  findContract,
  marginTl,
  searchContracts,
  unitLabel,
  type Contract,
  type ContractGroup,
} from "@/lib/contracts";
import {
  formatCompactTL,
  formatCurrencyAmount,
  formatLeverage,
  formatLots,
  formatMoney,
  formatPercent,
  formatPrice,
  formatSignedTL,
  formatTL,
  parseTrNumber,
} from "@/lib/format";
import {
  rankForTickers,
  sortByScreener,
  type ScreenerSort,
} from "@/lib/screener";
import { RankingSortChips } from "@/components/ranking-sort-chips";
import { ScreenerPanel } from "@/components/screener-panel";
import { ViopStatsTable } from "@/components/viop-stats-table";
import { useScreener } from "@/components/use-screener";
import { useViopContracts } from "@/components/use-viop-contracts";
import {
  HYPE_EXTRA_COLUMNS,
  HypeScoreCell,
  NewsRedditCell,
  RelativeVolumeCell,
} from "@/components/hype-cells";
import { cn } from "@/lib/utils";

const PERCENT_CHIPS = [0.25, 0.5, 1, 2, 3, 5, 10];
const SCENARIO_PERCENTS = [0.25, 0.5, 1, 2, 3, 5, 10];

function pnlClass(value: number) {
  if (value > 0) return "text-gain";
  if (value < 0) return "text-loss";
  return "text-muted-foreground";
}

function leverageClass(value: number) {
  if (value >= 6) return "text-gain";
  if (value >= 5) return "text-ticker";
  if (value >= 4) return "text-warn";
  return "text-loss";
}

function TickerMark({ children }: { children: string }) {
  return (
    <span className="rounded bg-ticker-muted px-1.5 py-0.5 font-mono text-xs font-semibold tracking-wide text-ticker">
      {children}
    </span>
  );
}

function formatPercentInput(value: number): string {
  return new Intl.NumberFormat("tr-TR", {
    minimumFractionDigits: 0,
    maximumFractionDigits: 4,
  }).format(value);
}

function marginLabel(contract: Contract): string {
  if (contract.currency === "USD") {
    return `${formatCurrencyAmount(contract.margin, "USD", 0)} · ${formatTL(marginTl(contract), 0)}`;
  }
  return formatTL(contract.margin, 0);
}

export function Calculator() {
  const [contract, setContract] = React.useState<Contract | undefined>();
  const [amountInput, setAmountInput] = React.useState("");
  const [percentInput, setPercentInput] = React.useState("0,50");
  const [lotsInput, setLotsInput] = React.useState("");
  const [lotsTouched, setLotsTouched] = React.useState(false);
  const [side, setSide] = React.useState<Side>("long");
  const [tableQuery, setTableQuery] = React.useState("");
  const [groupFilter, setGroupFilter] = React.useState<ContractGroup | "all">(
    "all",
  );
  const [sortKey, setSortKey] = React.useState<ScreenerSort>("score");
  const screener = useScreener();
  const liveContracts = useViopContracts();

  React.useEffect(() => {
    if (!contract) return;
    const fresh = findContract(contract.ticker);
    if (
      fresh &&
      (fresh.price !== contract.price ||
        fresh.margin !== contract.margin ||
        fresh.leverage !== contract.leverage)
    ) {
      setContract(fresh);
    }
  }, [liveContracts.contracts, contract]);

  const amount = parseTrNumber(amountInput);
  const percentMagnitude = Math.abs(parseTrNumber(percentInput) ?? 0);
  const typedLots = parseTrNumber(lotsInput);

  const position =
    contract && amount != null && amount > 0
      ? buildPosition(
          amount,
          contract,
          lotsTouched ? (typedLots ?? 0) : undefined,
        )
      : null;

  const displayedLots = lotsTouched
    ? lotsInput
    : position && position.maxLots > 0
      ? String(position.maxLots)
      : "";

  function handleContractChange(next: Contract) {
    setContract(next);
    setLotsTouched(false);
    setLotsInput("");
  }

  function handleAmountChange(value: string) {
    setAmountInput(value);
    setLotsTouched(false);
    setLotsInput("");
  }

  function adjustLots(delta: number) {
    if (!position) return;
    const current = lotsTouched ? position.lots : position.maxLots;
    const next = Math.max(0, Math.min(position.maxLots, current + delta));
    setLotsTouched(true);
    setLotsInput(next > 0 ? String(next) : "");
  }

  const pnlUp = position
    ? pnlForPriceMove(position.notional, percentMagnitude, side)
    : 0;
  const pnlDown = position
    ? pnlForPriceMove(position.notional, -percentMagnitude, side)
    : 0;

  const ranked = rankForTickers(
    searchContracts("", "pay").map((row) => row.ticker),
    screener.stats,
  );
  const filteredContracts = sortByScreener(
    searchContracts(tableQuery, groupFilter),
    ranked,
    sortKey,
  );
  const amountError =
    amountInput.trim() !== "" && (amount == null || amount <= 0);
  const percentError =
    percentInput.trim() !== "" && parseTrNumber(percentInput) == null;

  const rankedLeaders = sortByScreener(
    searchContracts("", "pay"),
    ranked,
    sortKey === "default" ? "score" : sortKey,
  )
    .filter((row) => ranked.has(row.ticker))
    .slice(0, 5)
    .map((row) => ({ ticker: row.ticker, stats: ranked.get(row.ticker)! }));

  return (
    <div className="flex flex-col gap-6">
      <ScreenerPanel
        status={screener.status}
        updatedAt={screener.status === "ok" ? screener.updatedAt : undefined}
        sortKey={sortKey}
        onSortKey={(key) => {
          setSortKey(key);
          setGroupFilter("pay");
        }}
        leaders={rankedLeaders}
        selectedTicker={contract?.ticker}
        onSelect={(ticker) => {
          const next = findContract(ticker);
          if (next) {
            handleContractChange(next);
            setGroupFilter("pay");
          }
        }}
        loadingHint="THYAO, bankalar ve diğer paylar sıralanıyor…"
      />

      <div className="grid gap-6 lg:grid-cols-[minmax(28rem,34rem)_minmax(0,1fr)]">
        <Card className="h-fit overflow-visible! ring-ticker/20">
          <CardHeader className="border-b border-ticker/15">
            <CardTitle className="text-ticker">Pozisyon</CardTitle>
            <CardDescription>
              TL teminat girin; pay, endeks, döviz ve emtia sözleşmelerinde lot
              ve kar/zarar hesaplanır. USD teminatlı kontratlar USDTRY ile TL’ye
              çevrilir.
              {liveContracts.updatedAt
                ? ` Fiyat/teminat: ${new Date(liveContracts.updatedAt).toLocaleString("tr-TR", { timeZone: "Europe/Istanbul" })}.`
                : liveContracts.status === "loading"
                  ? " Fiyat/teminat güncelleniyor…"
                  : ""}
            </CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-5">
            <div className="grid gap-2">
              <Label htmlFor="stock">Dayanak varlık</Label>
              <div className="flex flex-wrap gap-1.5">
                <Button
                  type="button"
                  size="xs"
                  variant={groupFilter === "all" ? "default" : "outline"}
                  onClick={() => setGroupFilter("all")}
                >
                  Tümü
                </Button>
                {GROUP_ORDER.map((group) => (
                  <Button
                    key={group}
                    type="button"
                    size="xs"
                    variant={groupFilter === group ? "default" : "outline"}
                    className={
                      groupFilter === group
                        ? undefined
                        : "border-ticker/20 text-ticker hover:bg-ticker-muted"
                    }
                    onClick={() => setGroupFilter(group)}
                  >
                    {GROUP_LABELS[group]}
                  </Button>
                ))}
              </div>
              <StockCombobox
                value={contract}
                onChange={handleContractChange}
                group={groupFilter}
              />
            </div>

            {contract ? (
              <div className="grid grid-cols-2 gap-2 rounded-lg bg-ticker-muted/40 p-3 ring-1 ring-ticker/20 sm:grid-cols-4">
                <Metric
                  label="Fiyat"
                  value={formatPrice(contract.price)}
                  tone="text-warn"
                />
                <Metric
                  label="Teminat / lot"
                  value={marginLabel(contract)}
                  tone="text-ticker"
                />
                <Metric
                  label="Kaldıraç"
                  value={formatLeverage(contract.leverage)}
                  tone={leverageClass(contract.leverage)}
                />
                <Metric
                  label="Çarpan"
                  value={unitLabel(contract)}
                  tone="text-gain"
                />
              </div>
            ) : null}

            <div className="grid gap-2">
              <Label htmlFor="amount">Alım tutarı</Label>
              <InputGroup className="h-11">
                <PlainInput
                  id="amount"
                  inputMode="decimal"
                  placeholder="25.000"
                  value={amountInput}
                  aria-invalid={amountError || undefined}
                  onChange={(event) => handleAmountChange(event.target.value)}
                />
                <InputGroupAddon align="inline-end">
                  <InputGroupText>TL</InputGroupText>
                </InputGroupAddon>
              </InputGroup>
              {amountError ? (
                <p className="text-xs text-destructive">
                  Geçerli bir tutar girin. 25.000 veya 0,54 gibi yazabilirsiniz.
                </p>
              ) : null}
            </div>

            <div className="grid gap-2">
              <div className="flex items-center justify-between gap-2">
                <Label htmlFor="lots">Lot adedi</Label>
                {position && lotsTouched && position.lots !== position.maxLots ? (
                  <button
                    type="button"
                    className="text-xs text-muted-foreground underline-offset-2 hover:text-foreground hover:underline"
                    onClick={() => {
                      setLotsTouched(false);
                      setLotsInput("");
                    }}
                  >
                    Maksimumu kullan ({position.maxLots})
                  </button>
                ) : null}
              </div>
              <InputGroup className="h-11">
                <InputGroupAddon align="inline-start">
                  <InputGroupButton
                    size="icon-xs"
                    aria-label="Lot azalt"
                    disabled={!position || position.lots <= 0}
                    onClick={() => adjustLots(-1)}
                  >
                    <MinusIcon />
                  </InputGroupButton>
                </InputGroupAddon>
                <PlainInput
                  id="lots"
                  inputMode="numeric"
                  placeholder="—"
                  className="text-center"
                  value={displayedLots}
                  disabled={!position}
                  onChange={(event) => {
                    setLotsTouched(true);
                    setLotsInput(event.target.value);
                  }}
                  onBlur={() => {
                    if (!position || !lotsTouched) return;
                    if (typedLots == null || typedLots <= 0) {
                      setLotsInput("");
                      return;
                    }
                    const clamped = Math.min(
                      Math.floor(typedLots),
                      position.maxLots,
                    );
                    setLotsInput(clamped > 0 ? String(clamped) : "");
                  }}
                />
                <InputGroupAddon align="inline-end">
                  <InputGroupButton
                    size="icon-xs"
                    aria-label="Lot artır"
                    disabled={!position || position.lots >= position.maxLots}
                    onClick={() => adjustLots(1)}
                  >
                    <PlusIcon />
                  </InputGroupButton>
                </InputGroupAddon>
              </InputGroup>
            </div>

            <div className="grid gap-2">
              <Label>Yön</Label>
              <div className="grid grid-cols-2 gap-2">
                <Button
                  type="button"
                  variant="outline"
                  className={
                    side === "long"
                      ? "border-gain/40 bg-gain-muted text-gain hover:bg-gain/20 hover:text-gain"
                      : "hover:border-gain/30 hover:text-gain"
                  }
                  onClick={() => setSide("long")}
                >
                  <TrendingUpIcon />
                  Alış (uzun)
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  className={
                    side === "short"
                      ? "border-loss/40 bg-loss-muted text-loss hover:bg-loss/20 hover:text-loss"
                      : "hover:border-loss/30 hover:text-loss"
                  }
                  onClick={() => setSide("short")}
                >
                  <TrendingDownIcon />
                  Satış (kısa)
                </Button>
              </div>
            </div>

            <div className="grid gap-2">
              <Label htmlFor="percent">Fiyat hareketi</Label>
              <InputGroup className="h-11">
                <InputGroupAddon align="inline-start">
                  <InputGroupText>%</InputGroupText>
                </InputGroupAddon>
                <PlainInput
                  id="percent"
                  inputMode="decimal"
                  placeholder="0,50"
                  value={percentInput}
                  aria-invalid={percentError || undefined}
                  onChange={(event) => setPercentInput(event.target.value)}
                />
              </InputGroup>
              {percentError ? (
                <p className="text-xs text-destructive">
                  Yüzde 0,50 veya 1,25 gibi ondalıklı girilebilir.
                </p>
              ) : null}
              <div className="flex flex-wrap gap-1.5">
                {PERCENT_CHIPS.map((chip) => (
                  <Button
                    key={chip}
                    type="button"
                    size="xs"
                    variant={percentMagnitude === chip ? "default" : "outline"}
                    className={
                      percentMagnitude === chip
                        ? undefined
                        : "border-ticker/20 text-ticker hover:bg-ticker-muted"
                    }
                    onClick={() => setPercentInput(formatPercentInput(chip))}
                  >
                    {formatPercent(chip, chip % 1 === 0 ? 0 : 2)}
                  </Button>
                ))}
              </div>
            </div>
          </CardContent>
        </Card>

        <div className="flex flex-col gap-6">
          <Results
            contract={contract}
            amount={amount}
            amountInput={amountInput}
            position={position}
            percent={percentMagnitude}
            side={side}
            pnlUp={pnlUp}
            pnlDown={pnlDown}
          />
        </div>
      </div>

      {position && contract && position.lots > 0 && percentMagnitude > 0 ? (
        <ScenarioTable
          contract={contract}
          position={position}
          side={side}
          customPercent={percentMagnitude}
        />
      ) : null}

      <Card className="ring-ticker/20">
        <CardHeader className="border-b border-ticker/15">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
            <div>
              <CardTitle className="text-ticker">Sözleşme tablosu</CardTitle>
              <CardDescription>
                Pay dayanakları 20 günlük ortalama TL hacmi, gerçekleşen
                volatilite, piyasa değeri ve 7 günlük hype’a göre sıralanır.{" "}
                <span className="text-foreground">Hacim + vol</span>,{" "}
                <span className="text-foreground">Hacim + vol + değer</span> ve{" "}
                <span className="text-foreground">Hacim + vol + hype</span> ayrı
                skorlardır.
                {screener.status === "ok" && screener.updatedAt
                  ? ` Yahoo · ${new Date(screener.updatedAt).toLocaleTimeString("tr-TR", { hour: "2-digit", minute: "2-digit" })}`
                  : null}
                {screener.status === "loading" ? " Hacim yükleniyor…" : null}
                {screener.status === "error"
                  ? " Hacim alınamadı; sıralama listede kalır."
                  : null}
              </CardDescription>
            </div>
            <InputGroup className="h-9 sm:max-w-64">
              <PlainInput
                placeholder="Tabloda ara"
                value={tableQuery}
                onChange={(event) => setTableQuery(event.target.value)}
              />
            </InputGroup>
          </div>
          <RankingSortChips sortKey={sortKey} onSortKey={setSortKey} />
        </CardHeader>
        <CardContent className="px-0">
          <Table className="min-w-[76rem]">
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead className="text-ticker">Kod</TableHead>
                <TableHead className="text-muted-foreground">Dayanak varlık</TableHead>
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
                <TableHead className="text-ticker">Grup</TableHead>
                <TableHead className="text-right text-muted-foreground">Teminat</TableHead>
                <TableHead className="text-right text-warn">Fiyat</TableHead>
                <TableHead className="text-right text-gain">Kaldıraç</TableHead>
                <TableHead
                  aria-sort={
                    sortKey === "volume" ? "descending" : "none"
                  }
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
                  aria-sort={
                    sortKey === "volatility" ? "descending" : "none"
                  }
                  className="text-right text-warn"
                >
                  Volatilite
                </TableHead>
                <TableHead
                  aria-sort={
                    sortKey === "marketCap" ? "descending" : "none"
                  }
                  className="text-right text-ticker"
                >
                  Piyasa değeri
                </TableHead>
                <TableHead className="text-right text-muted-foreground">
                  Haber/KAP
                </TableHead>
                {amount != null && amount > 0 ? (
                  <TableHead className="text-right text-ticker">Max lot</TableHead>
                ) : null}
              </TableRow>
            </TableHeader>
            <TableBody>
              {filteredContracts.length === 0 ? (
                <TableRow>
                  <TableCell
                    colSpan={
                      (amount != null && amount > 0 ? 12 : 11) + HYPE_EXTRA_COLUMNS
                    }
                    className="py-8 text-center text-muted-foreground"
                  >
                    Tabloda eşleşen sözleşme yok.
                  </TableCell>
                </TableRow>
              ) : (
                filteredContracts.map((row) => {
                  const max =
                    amount != null && amount > 0
                      ? Math.floor(amount / marginTl(row))
                      : null;
                  const selected = contract?.ticker === row.ticker;
                  const stats = ranked.get(row.ticker);
                  return (
                    <TableRow
                      key={row.ticker}
                      data-state={selected ? "selected" : undefined}
                      tabIndex={0}
                      className={cn(
                        "cursor-pointer",
                        selected && "bg-ticker-muted/50",
                      )}
                      onClick={() => handleContractChange(row)}
                      onKeyDown={(event) => {
                        if (event.key === "Enter" || event.key === " ") {
                          event.preventDefault();
                          handleContractChange(row);
                        }
                      }}
                    >
                      <TableCell>
                        <TickerMark>{row.ticker}</TickerMark>
                      </TableCell>
                      <TableCell>{row.name}</TableCell>
                      <TableCell className="text-right font-mono text-gain">
                        {stats ? formatMoney(stats.score, 0) : "—"}
                      </TableCell>
                      <TableCell className="text-right font-mono text-gain">
                        {stats ? formatMoney(stats.scoreValue, 0) : "—"}
                      </TableCell>
                      <TableCell className="text-right font-mono text-gain">
                        <HypeScoreCell item={stats} />
                      </TableCell>
                      <TableCell className="text-xs text-muted-foreground">
                        {GROUP_LABELS[row.group]}
                      </TableCell>
                      <TableCell className="text-right font-mono text-muted-foreground">
                        {marginLabel(row)}
                      </TableCell>
                      <TableCell className="text-right font-mono text-warn">
                        {formatPrice(row.price)}
                      </TableCell>
                      <TableCell
                        className={cn(
                          "text-right font-mono font-semibold",
                          leverageClass(row.leverage),
                        )}
                      >
                        {formatLeverage(row.leverage)}
                      </TableCell>
                      <TableCell className="text-right font-mono text-ticker">
                        {stats
                          ? formatCompactTL(stats.avgVolumeTl)
                          : screener.status === "loading"
                            ? "…"
                            : "—"}
                      </TableCell>
                      <TableCell className="text-right font-mono text-ticker">
                        <RelativeVolumeCell
                          item={stats}
                          loading={screener.status === "loading"}
                        />
                      </TableCell>
                      <TableCell className="text-right font-mono text-warn">
                        {stats ? (
                          <span title={`Günlük ortalama |hareket| ${formatPercent(stats.dailyMove)}`}>
                            {formatPercent(stats.volatility, 1)}
                          </span>
                        ) : screener.status === "loading" ? (
                          "…"
                        ) : (
                          "—"
                        )}
                      </TableCell>
                      <TableCell className="text-right font-mono text-ticker">
                        {stats?.marketCap
                          ? formatCompactTL(stats.marketCap)
                          : screener.status === "loading"
                            ? "…"
                            : "—"}
                      </TableCell>
                      <TableCell className="text-right font-mono text-xs text-muted-foreground">
                        <NewsRedditCell
                          item={stats}
                          loading={screener.status === "loading"}
                          kap
                        />
                      </TableCell>
                      {max != null ? (
                        <TableCell className="text-right font-mono text-ticker">
                          {max}
                        </TableCell>
                      ) : null}
                    </TableRow>
                  );
                })
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <ViopStatsTable
        selectedTicker={contract?.ticker}
        onSelect={(ticker) => {
          const next = findContract(ticker);
          if (next) {
            handleContractChange(next);
            setGroupFilter("pay");
          }
        }}
      />
    </div>
  );
}

function Metric({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone?: string;
}) {
  return (
    <div className="min-w-0">
      <p className="text-[11px] tracking-wide text-muted-foreground uppercase">
        {label}
      </p>
      <p className={cn("truncate font-mono text-sm font-medium", tone)}>
        {value}
      </p>
    </div>
  );
}

function Results({
  contract,
  amount,
  amountInput,
  position,
  percent,
  side,
  pnlUp,
  pnlDown,
}: {
  contract?: Contract;
  amount: number | null;
  amountInput: string;
  position: ReturnType<typeof buildPosition> | null;
  percent: number;
  side: Side;
  pnlUp: number;
  pnlDown: number;
}) {
  if (!contract) {
    return (
      <EmptyState
        title="Dayanak varlık seçin"
        description="Soldan pay, endeks, döviz veya emtia sözleşmesi seçin. Kod veya adla arayabilirsiniz."
      />
    );
  }

  if (!amountInput.trim()) {
    return (
      <EmptyState
        title="Alım tutarını girin"
        description={`${contract.ticker} için 1 lot teminatı ${marginLabel(contract)}. Bu tutarla kaç lot açabileceğinizi hesaplarız.`}
      />
    );
  }

  if (amount == null || amount <= 0) {
    return (
      <EmptyState
        title="Tutar okunamadı"
        description="25.000 veya 10000 gibi bir sayı girin. Ondalık için virgül de kullanabilirsiniz."
      />
    );
  }

  if (!position || position.maxLots === 0) {
    return (
      <EmptyState
        title="Bu tutarla lot açılamıyor"
        description={`${contract.ticker} için minimum teminat ${marginLabel(contract)}. Girdiğiniz ${formatTL(amount, 0)} 1 lota yetmiyor.`}
      />
    );
  }

  if (position.lots === 0) {
    return (
      <EmptyState
        title="Lot adedini girin"
        description={`Bu tutarla en fazla ${formatLots(position.maxLots)} açabilirsiniz.`}
      />
    );
  }

  const upLabel = side === "long" ? "Kazanç" : "Kayıp";
  const downLabel = side === "long" ? "Kayıp" : "Kazanç";
  const upPrice = priceAfterMove(contract.price, percent);
  const downPrice = priceAfterMove(contract.price, -percent);

  return (
    <>
      <div className="grid gap-3 sm:grid-cols-3">
        <StatCard
          icon={<LayersIcon />}
          label="Alınabilir lot"
          value={formatLots(position.lots)}
          hint={`${position.units.toLocaleString("tr-TR")} birim · ${unitLabel(contract)} · max ${position.maxLots}`}
          tone="ticker"
        />
        <StatCard
          icon={<WalletIcon />}
          label="Kullanılan teminat"
          value={formatTL(position.usedMargin, 0)}
          hint={
            contract.currency === "USD"
              ? `${formatCurrencyAmount(position.lots * contract.margin, "USD", 0)} · kalan ${formatTL(position.remaining, 2)}`
              : `Kalan ${formatTL(position.remaining, 2)}`
          }
          tone="warn"
        />
        <StatCard
          icon={<CoinsIcon />}
          label="Sözleşme değeri"
          value={formatTL(position.notional, 2)}
          hint={`${formatLeverage(position.leverage)} kaldıraç`}
          tone="gain"
        />
      </div>

      <div className="grid gap-3 md:grid-cols-2">
        <PnlCard
          direction="up"
          title={`Fiyat ${formatPercent(percent)} yükselirse`}
          priceFrom={contract.price}
          priceTo={upPrice}
          pnl={pnlUp}
          usedMargin={position.usedMargin}
          label={upLabel}
        />
        <PnlCard
          direction="down"
          title={`Fiyat ${formatPercent(percent)} düşerse`}
          priceFrom={contract.price}
          priceTo={downPrice}
          pnl={pnlDown}
          usedMargin={position.usedMargin}
          label={downLabel}
        />
      </div>

      <Card className="ring-ticker/20">
        <CardHeader className="border-b border-ticker/15">
          <CardTitle className="text-ticker">Özet</CardTitle>
          <CardDescription>
            {side === "long" ? (
              <span className="text-gain">Uzun</span>
            ) : (
              <span className="text-loss">Kısa</span>
            )}{" "}
            <TickerMark>{contract.ticker}</TickerMark> ·{" "}
            {formatLots(position.lots)} · {formatPercent(percent)} hareket
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-3 sm:grid-cols-2">
          <SummaryRow
            label="Hareket sonrası bakiye (yükseliş)"
            value={formatTL(endingEquity(position.usedMargin, pnlUp))}
            tone={pnlClass(pnlUp)}
          />
          <SummaryRow
            label="Hareket sonrası bakiye (düşüş)"
            value={formatTL(endingEquity(position.usedMargin, pnlDown))}
            tone={pnlClass(pnlDown)}
          />
          <SummaryRow
            label="Teminata göre getiri (yükseliş)"
            value={formatPercent(returnOnMargin(pnlUp, position.usedMargin))}
            tone={pnlClass(pnlUp)}
          />
          <SummaryRow
            label="Teminata göre getiri (düşüş)"
            value={formatPercent(returnOnMargin(pnlDown, position.usedMargin))}
            tone={pnlClass(pnlDown)}
          />
        </CardContent>
      </Card>
    </>
  );
}

function EmptyState({
  title,
  description,
}: {
  title: string;
  description: string;
}) {
  return (
    <Card className="flex min-h-72 items-center justify-center ring-ticker/20">
      <CardContent className="max-w-md py-10 text-center">
        <p className="mb-3 text-[11px] font-semibold tracking-[0.2em] text-ticker uppercase">
          VIOP
        </p>
        <CardTitle className="text-lg">{title}</CardTitle>
        <CardDescription className="mt-2 text-pretty">
          {description}
        </CardDescription>
      </CardContent>
    </Card>
  );
}

function StatCard({
  icon,
  label,
  value,
  hint,
  tone,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  hint: string;
  tone: "ticker" | "warn" | "gain";
}) {
  const tones = {
    ticker: "bg-ticker-muted/50 ring-ticker/25 text-ticker",
    warn: "bg-warn-muted/50 ring-warn/25 text-warn",
    gain: "bg-gain-muted/50 ring-gain/25 text-gain",
  } as const;

  return (
    <Card className={cn("ring-1", tones[tone])}>
      <CardContent className="flex flex-col gap-2">
        <div className="flex items-center gap-2 opacity-80">
          <span className="[&_svg]:size-4">{icon}</span>
          <span className="text-xs tracking-wide uppercase">{label}</span>
        </div>
        <p className="font-heading text-2xl font-semibold tracking-tight">
          {value}
        </p>
        <p className="text-xs text-muted-foreground">{hint}</p>
      </CardContent>
    </Card>
  );
}

function PnlCard({
  direction,
  title,
  priceFrom,
  priceTo,
  pnl,
  usedMargin,
  label,
}: {
  direction: "up" | "down";
  title: string;
  priceFrom: number;
  priceTo: number;
  pnl: number;
  usedMargin: number;
  label: string;
}) {
  const positive = pnl > 0;
  const negative = pnl < 0;
  return (
    <Card
      className={cn(
        "ring-1",
        positive && "bg-gain-muted/60 ring-gain/35",
        negative && "bg-loss-muted/60 ring-loss/35",
      )}
    >
      <CardHeader>
        <div className="flex items-start justify-between gap-3">
          <div>
            <CardTitle className="text-sm">{title}</CardTitle>
            <CardDescription className="font-mono text-foreground/70">
              {formatPrice(priceFrom)} → {formatPrice(priceTo)}
            </CardDescription>
          </div>
          <Badge
            className={cn(
              positive && "bg-gain text-primary-foreground",
              negative && "bg-loss text-white",
            )}
          >
            {direction === "up" ? <ArrowUpRightIcon /> : <ArrowDownRightIcon />}
            {label}
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="flex flex-col gap-1">
        <p
          className={cn(
            "font-heading text-3xl font-semibold tracking-tight",
            pnlClass(pnl),
          )}
        >
          {formatSignedTL(pnl)}
        </p>
        <p className="text-sm text-muted-foreground">
          Teminata göre{" "}
          <span className={pnlClass(pnl)}>
            {formatPercent(returnOnMargin(pnl, usedMargin))}
          </span>
        </p>
      </CardContent>
    </Card>
  );
}

function SummaryRow({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone?: string;
}) {
  return (
    <div className="flex items-center justify-between gap-3 rounded-lg bg-muted/50 px-3 py-2 ring-1 ring-ticker/10">
      <span className="text-sm text-muted-foreground">{label}</span>
      <span className={cn("font-mono text-sm font-medium", tone)}>{value}</span>
    </div>
  );
}

function ScenarioTable({
  contract,
  position,
  side,
  customPercent,
}: {
  contract: Contract;
  position: ReturnType<typeof buildPosition>;
  side: Side;
  customPercent: number;
}) {
  const percents = Array.from(
    new Set(
      [...SCENARIO_PERCENTS, customPercent]
        .filter((value) => value > 0)
        .map((value) => Number(value.toFixed(4))),
    ),
  ).sort((a, b) => a - b);

  return (
    <Card className="ring-ticker/20">
      <CardHeader className="border-b border-ticker/15">
        <CardTitle className="text-ticker">Senaryo tablosu</CardTitle>
        <CardDescription>
          {side === "long" ? "Alış" : "Satış"} pozisyonunda fiyatın yüzde kaç
          gitmesi halinde kar veya zarar.
        </CardDescription>
      </CardHeader>
      <CardContent className="px-0">
        <Table className="min-w-[44rem]">
          <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead className="text-ticker">Hareket</TableHead>
                <TableHead className="text-right text-gain">Yeni fiyat ↑</TableHead>
                <TableHead className="text-right text-gain">Kar/Zarar ↑</TableHead>
                <TableHead className="text-right text-loss">Yeni fiyat ↓</TableHead>
                <TableHead className="text-right text-loss">Kar/Zarar ↓</TableHead>
                <TableHead className="text-right text-warn">Teminata getiri</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {percents.map((pct) => {
              const up = pnlForPriceMove(position.notional, pct, side);
              const down = pnlForPriceMove(position.notional, -pct, side);
              const highlight = pct === Number(customPercent.toFixed(4));
              return (
                <TableRow
                  key={pct}
                  data-state={highlight ? "selected" : undefined}
                  className={highlight ? "bg-ticker-muted/40" : undefined}
                >
                  <TableCell className="font-medium text-ticker">
                    {formatPercent(pct, pct % 1 === 0 ? 0 : 2)}
                  </TableCell>
                  <TableCell className="text-right font-mono text-gain">
                    {formatPrice(priceAfterMove(contract.price, pct))}
                  </TableCell>
                  <TableCell
                    className={cn(
                      "text-right font-mono font-semibold",
                      up > 0 && "bg-gain-muted text-gain",
                      up < 0 && "bg-loss-muted text-loss",
                    )}
                  >
                    {formatSignedTL(up)}
                  </TableCell>
                  <TableCell className="text-right font-mono text-loss">
                    {formatPrice(priceAfterMove(contract.price, -pct))}
                  </TableCell>
                  <TableCell
                    className={cn(
                      "text-right font-mono font-semibold",
                      down > 0 && "bg-gain-muted text-gain",
                      down < 0 && "bg-loss-muted text-loss",
                    )}
                  >
                    {formatSignedTL(down)}
                  </TableCell>
                  <TableCell className="text-right font-mono text-warn">
                    {formatPercent(Math.abs(returnOnMargin(up, position.usedMargin)))}
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}
