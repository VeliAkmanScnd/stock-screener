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
import { SpotCombobox } from "@/components/spot-combobox";
import {
  endingEquity,
  pnlForPriceMove,
  priceAfterMove,
  returnOnMargin,
  type Side,
} from "@/lib/calc";
import { buildSpotPosition } from "@/lib/spot-calc";
import {
  MARKET_LABELS,
  MARKET_ORDER,
  searchSpotStocks,
  type SpotMarket,
  type SpotStock,
} from "@/lib/spot-stocks";
import {
  formatCompactTL,
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
import { MarketRankingTable } from "@/components/market-ranking-table";
import {
  ColumnFilterHead,
  compareColumnValues,
  matchesColumnFilter,
  type ColumnFilter,
  type ColumnSort,
} from "@/components/column-filter-head";
import { RankingFilters } from "@/components/ranking-filters";
import { RankingSortChips } from "@/components/ranking-sort-chips";
import { ScreenerPanel } from "@/components/screener-panel";
import { useScreener } from "@/components/use-screener";
import {
  HYPE_EXTRA_COLUMNS,
  HypeScoreCell,
  NewsRedditCell,
  RelativeVolumeCell,
} from "@/components/hype-cells";
import {
  DEFAULT_RANKING_FILTER,
  rankAndFilter,
  type RankingFilter,
} from "@/lib/ranking-filter";
import { cn } from "@/lib/utils";

const PERCENT_CHIPS = [1, 2, 3, 4, 5, 10, 20];
const SCENARIO_PERCENTS = [1, 2, 3, 4, 5, 10, 20];

function pnlClass(value: number) {
  if (value > 0) return "text-gain";
  if (value < 0) return "text-loss";
  return "text-muted-foreground";
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

function formatPriceInput(value: number): string {
  return new Intl.NumberFormat("tr-TR", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 4,
  }).format(value);
}

export function SpotCalculator() {
  const [stock, setStock] = React.useState<SpotStock | undefined>();
  const [amountInput, setAmountInput] = React.useState("");
  const [priceInput, setPriceInput] = React.useState("");
  const [percentInput, setPercentInput] = React.useState("1");
  const [lotsInput, setLotsInput] = React.useState("");
  const [lotsTouched, setLotsTouched] = React.useState(false);
  const [side, setSide] = React.useState<Side>("long");
  const [tableQuery, setTableQuery] = React.useState("");
  const [marketFilter, setMarketFilter] = React.useState<SpotMarket | "all">(
    "all",
  );
  const [sortKey, setSortKey] = React.useState<ScreenerSort>("score");
  const [colSort, setColSort] = React.useState<ColumnSort | null>(null);
  const [colFilters, setColFilters] = React.useState<Record<string, ColumnFilter>>({});
  const [rankingFilter, setRankingFilter] = React.useState<RankingFilter>(
    DEFAULT_RANKING_FILTER,
  );
  const screener = useScreener();

  const amount = parseTrNumber(amountInput);
  const price = parseTrNumber(priceInput);
  const percentMagnitude = Math.abs(parseTrNumber(percentInput) ?? 0);
  const typedLots = parseTrNumber(lotsInput);
  const priceReady = price != null && price > 0;

  const position =
    stock && amount != null && amount > 0 && priceReady
      ? buildSpotPosition(
          amount,
          price,
          lotsTouched ? (typedLots ?? 0) : undefined,
        )
      : null;

  const displayedLots = lotsTouched
    ? lotsInput
    : position && position.maxLots > 0
      ? String(position.maxLots)
      : "";

  function applyStock(next: SpotStock) {
    setStock(next);
    setLotsTouched(false);
    setLotsInput("");
    setPriceInput(
      next.referencePrice != null ? formatPriceInput(next.referencePrice) : "",
    );
  }

  function handleAmountChange(value: string) {
    setAmountInput(value);
    setLotsTouched(false);
    setLotsInput("");
  }

  function handlePriceChange(value: string) {
    setPriceInput(value);
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

  const marketPool = searchSpotStocks("", marketFilter);
  const ranked = rankForTickers(
    marketPool.map((row) => row.ticker),
    screener.stats,
  );
  const searchedStocks = searchSpotStocks(tableQuery, marketFilter);

  function stockCell(row: SpotStock, key: string): number | string | null {
    const stats = ranked.get(row.ticker);
    const rowPrice =
      stock?.ticker === row.ticker && priceReady ? price : row.referencePrice;
    switch (key) {
      case "ticker":
        return row.ticker;
      case "name":
        return row.name;
      case "market":
        return row.markets.map((item) => MARKET_LABELS[item]).join(" · ");
      case "score":
        return stats?.score ?? null;
      case "scoreValue":
        return stats?.scoreValue ?? null;
      case "hype":
        return stats?.hype ?? null;
      case "price":
        return rowPrice ?? null;
      case "volume":
        return stats?.avgVolumeTl ?? null;
      case "relativeVolume":
        return stats?.relativeVolume ?? null;
      case "volatility":
        return stats?.volatility ?? null;
      case "marketCap":
        return stats?.marketCap && stats.marketCap > 0 ? stats.marketCap : null;
      case "news":
        if (!stats || (stats.newsCount == null && stats.kapCount == null)) return null;
        return (stats.newsCount ?? 0) + (stats.kapCount ?? 0);
      case "maxLots":
        if (amount == null || amount <= 0 || rowPrice == null || rowPrice <= 0) return null;
        return Math.floor(amount / rowPrice);
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

  const textOptions = (key: "ticker" | "name" | "market") =>
    [...new Set(searchedStocks.map((row) => String(stockCell(row, key))))].sort((a, b) =>
      a.localeCompare(b, "tr"),
    );
  const headerSort: ColumnSort | null =
    colSort ??
    (sortKey === "default"
      ? null
      : { key: sortKey === "scoreHype" ? "hype" : sortKey, dir: "desc" });
  const columnMatched = searchedStocks.filter((row) =>
    Object.entries(colFilters).every(([key, columnFilter]) =>
      matchesColumnFilter(columnFilter, stockCell(row, key)),
    ),
  );
  const rankedRows = rankAndFilter(
    columnMatched,
    ranked,
    rankingFilter,
    sortKey,
    tableQuery.trim().length > 0,
  );
  const filteredStocks = colSort
    ? [...rankedRows].sort((left, right) =>
        compareColumnValues(stockCell(left, colSort.key), stockCell(right, colSort.key), colSort.dir),
      )
    : rankedRows;
  const rankedLeaders = sortByScreener(
    marketPool,
    ranked,
    sortKey === "default" ? "score" : sortKey,
  )
    .filter((row) => ranked.has(row.ticker))
    .slice(0, 5)
    .map((row) => ({ ticker: row.ticker, stats: ranked.get(row.ticker)! }));
  const amountError =
    amountInput.trim() !== "" && (amount == null || amount <= 0);
  const priceError =
    priceInput.trim() !== "" && (price == null || price <= 0);
  const percentError =
    percentInput.trim() !== "" && parseTrNumber(percentInput) == null;

  return (
    <div className="flex flex-col gap-6">
      <ScreenerPanel
        status={screener.status}
        updatedAt={screener.status === "ok" ? screener.updatedAt : undefined}
        sortKey={sortKey}
        onSortKey={setSortKey}
        leaders={rankedLeaders}
        selectedTicker={stock?.ticker}
        onSelect={(ticker) => {
          const next = marketPool.find((row) => row.ticker === ticker);
          if (next) applyStock(next);
        }}
        loadingHint="BIST, Nasdaq ve NYSE hacimleri sıralanıyor…"
      />

      <div className="grid gap-6 lg:grid-cols-[minmax(28rem,34rem)_minmax(0,1fr)]">
        <Card className="h-fit overflow-visible! ring-ticker/20">
          <CardHeader className="border-b border-ticker/15">
            <CardTitle className="text-ticker">Pozisyon</CardTitle>
            <CardDescription>
              Alım tutarını ve hisseyi girin. 1 lot = 1 pay; lot sayısı tutarın
              fiyata bölümünün tam kısmıdır. Fiyat VIOP listesinde varsa
              doldurulur, yoksa siz yazarsınız.
            </CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-5">
            <div className="grid gap-2">
              <Label htmlFor="spot-stock">Hisse</Label>
              <div className="flex flex-wrap gap-1.5">
                <Button
                  type="button"
                  size="xs"
                  variant={marketFilter === "all" ? "default" : "outline"}
                  onClick={() => setMarketFilter("all")}
                >
                  Tümü
                </Button>
                {MARKET_ORDER.map((market) => (
                  <Button
                    key={market}
                    type="button"
                    size="xs"
                    variant={marketFilter === market ? "default" : "outline"}
                    className={
                      marketFilter === market
                        ? undefined
                        : "border-ticker/20 text-ticker hover:bg-ticker-muted"
                    }
                    onClick={() => setMarketFilter(market)}
                  >
                    {MARKET_LABELS[market]}
                  </Button>
                ))}
              </div>
              <SpotCombobox
                value={stock}
                onChange={applyStock}
                market={marketFilter}
              />
            </div>

            {stock ? (
              <div className="grid grid-cols-2 gap-2 rounded-lg bg-ticker-muted/40 p-3 ring-1 ring-ticker/20 sm:grid-cols-3">
                <Metric
                  label="Pazar"
                  value={stock.markets.map((m) => MARKET_LABELS[m]).join(" · ")}
                  tone="text-ticker"
                />
                <Metric
                  label="Referans fiyat"
                  value={
                    stock.referencePrice != null
                      ? formatPrice(stock.referencePrice)
                      : "Elle girin"
                  }
                  tone="text-warn"
                />
                <Metric label="Çarpan" value="1 pay / lot" tone="text-gain" />
              </div>
            ) : null}

            <div className="grid gap-2">
              <Label htmlFor="spot-amount">Alım tutarı</Label>
              <InputGroup className="h-11">
                <PlainInput
                  id="spot-amount"
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
              <Label htmlFor="spot-price">Hisse fiyatı</Label>
              <InputGroup className="h-11">
                <PlainInput
                  id="spot-price"
                  inputMode="decimal"
                  placeholder={stock ? "Örn. 295,30" : "Önce hisse seçin"}
                  value={priceInput}
                  disabled={!stock}
                  aria-invalid={priceError || undefined}
                  onChange={(event) => handlePriceChange(event.target.value)}
                />
                <InputGroupAddon align="inline-end">
                  <InputGroupText>TL</InputGroupText>
                </InputGroupAddon>
              </InputGroup>
              {priceError ? (
                <p className="text-xs text-destructive">
                  Geçerli bir fiyat girin. 295,30 gibi yazabilirsiniz.
                </p>
              ) : stock && !stock.referencePrice && !priceInput.trim() ? (
                <p className="text-xs text-warn">
                  Bu hisse VIOP listesinde yok; güncel fiyatı kendiniz girin.
                </p>
              ) : null}
            </div>

            <div className="grid gap-2">
              <div className="flex items-center justify-between gap-2">
                <Label htmlFor="spot-lots">Lot adedi</Label>
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
                  id="spot-lots"
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
              <Label htmlFor="spot-percent">Fiyat hareketi</Label>
              <InputGroup className="h-11">
                <InputGroupAddon align="inline-start">
                  <InputGroupText>%</InputGroupText>
                </InputGroupAddon>
                <PlainInput
                  id="spot-percent"
                  inputMode="decimal"
                  placeholder="1"
                  value={percentInput}
                  aria-invalid={percentError || undefined}
                  onChange={(event) => setPercentInput(event.target.value)}
                />
              </InputGroup>
              {percentError ? (
                <p className="text-xs text-destructive">
                  Yüzde 1 veya 2,5 gibi ondalıklı girilebilir.
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
                    {formatPercent(chip, 0)}
                  </Button>
                ))}
              </div>
            </div>
          </CardContent>
        </Card>

        <div className="flex flex-col gap-6">
          <Results
            stock={stock}
            amount={amount}
            amountInput={amountInput}
            price={price}
            priceInput={priceInput}
            position={position}
            percent={percentMagnitude}
            side={side}
            pnlUp={pnlUp}
            pnlDown={pnlDown}
          />
        </div>
      </div>

      {position && stock && priceReady && position.lots > 0 && percentMagnitude > 0 ? (
        <ScenarioTable
          stock={stock}
          price={price}
          position={position}
          side={side}
          customPercent={percentMagnitude}
        />
      ) : null}

      <Card className="ring-ticker/20">
        <CardHeader className="border-b border-ticker/15">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
            <div>
              <CardTitle className="text-ticker">BIST sıralaması</CardTitle>
              <CardDescription>
                BIST 100, Yıldız ve Ana Pazar. Varsayılan görünüm hacim +
                volatilite skoruna göre ilk 100. Hype ve Hacim + vol + hype ayrı
                filtrelerdir; Hacim + vol + değer ayrı bir skordur. Eşikleri
                değiştirerek veya Tümü’ne geçerek listenin tamamı açılır. Satıra
                basınca hesaplayıcıya aktarılır.
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
          <RankingSortChips
            sortKey={sortKey}
            onSortKey={(key) => {
              setSortKey(key);
              setColSort(null);
            }}
          />
          <RankingFilters
            filter={rankingFilter}
            onChange={setRankingFilter}
            currency="TL"
            shown={filteredStocks.length}
            universe={marketPool.length}
          />
        </CardHeader>
        <CardContent className="px-0">
          <Table className="min-w-[76rem]">
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <ColumnFilterHead columnKey="ticker" label="Kod" type="text" className="text-ticker" sort={headerSort} filter={colFilters.ticker} options={textOptions("ticker")} onSort={setColSort} onFilter={(next) => setColumnFilter("ticker", next)} />
                <ColumnFilterHead columnKey="name" label="Şirket" type="text" className="text-muted-foreground" sort={headerSort} filter={colFilters.name} options={textOptions("name")} onSort={setColSort} onFilter={(next) => setColumnFilter("name", next)} />
                <ColumnFilterHead columnKey="market" label="Pazar" type="text" className="text-ticker" sort={headerSort} filter={colFilters.market} options={textOptions("market")} onSort={setColSort} onFilter={(next) => setColumnFilter("market", next)} />
                <ColumnFilterHead columnKey="score" label="Skor" type="number" align="right" className="text-gain" sort={headerSort} filter={colFilters.score} onSort={setColSort} onFilter={(next) => setColumnFilter("score", next)} />
                <ColumnFilterHead columnKey="scoreValue" label="Skor+değer" type="number" align="right" className="text-gain" sort={headerSort} filter={colFilters.scoreValue} onSort={setColSort} onFilter={(next) => setColumnFilter("scoreValue", next)} />
                <ColumnFilterHead columnKey="hype" label="Hype" type="number" align="right" className="text-gain" sort={headerSort} filter={colFilters.hype} onSort={setColSort} onFilter={(next) => setColumnFilter("hype", next)} />
                <ColumnFilterHead columnKey="price" label="Fiyat" type="number" align="right" className="text-warn" sort={headerSort} filter={colFilters.price} onSort={setColSort} onFilter={(next) => setColumnFilter("price", next)} />
                <ColumnFilterHead columnKey="volume" label="Hacim 20g" type="number" align="right" className="text-ticker" sort={headerSort} filter={colFilters.volume} onSort={setColSort} onFilter={(next) => setColumnFilter("volume", next)} />
                <ColumnFilterHead columnKey="relativeVolume" label="Göreli hacim" type="number" align="right" className="text-ticker" sort={headerSort} filter={colFilters.relativeVolume} onSort={setColSort} onFilter={(next) => setColumnFilter("relativeVolume", next)} />
                <ColumnFilterHead columnKey="volatility" label="Volatilite" type="number" align="right" className="text-warn" sort={headerSort} filter={colFilters.volatility} onSort={setColSort} onFilter={(next) => setColumnFilter("volatility", next)} />
                <ColumnFilterHead columnKey="marketCap" label="Piyasa değeri" type="number" align="right" className="text-ticker" sort={headerSort} filter={colFilters.marketCap} onSort={setColSort} onFilter={(next) => setColumnFilter("marketCap", next)} />
                <ColumnFilterHead columnKey="news" label="Haber/KAP" type="number" align="right" className="text-muted-foreground" sort={headerSort} filter={colFilters.news} onSort={setColSort} onFilter={(next) => setColumnFilter("news", next)} />
                {amount != null && amount > 0 ? (
                  <ColumnFilterHead columnKey="maxLots" label="Max lot" type="number" align="right" className="text-ticker" sort={headerSort} filter={colFilters.maxLots} onSort={setColSort} onFilter={(next) => setColumnFilter("maxLots", next)} />
                ) : null}
              </TableRow>
            </TableHeader>
            <TableBody>
              {screener.status === "loading" && ranked.size === 0 ? (
                <TableRow>
                  <TableCell
                    colSpan={
                      (amount != null && amount > 0 ? 10 : 9) + HYPE_EXTRA_COLUMNS
                    }
                    className="py-8 text-center text-muted-foreground"
                  >
                    Hacim ve volatilite yükleniyor…
                  </TableCell>
                </TableRow>
              ) : filteredStocks.length === 0 ? (
                <TableRow>
                  <TableCell
                    colSpan={
                      (amount != null && amount > 0 ? 10 : 9) + HYPE_EXTRA_COLUMNS
                    }
                    className="py-8 text-center text-muted-foreground"
                  >
                    Eşiği geçen hisse yok. Filtreleri gevşetin, arayın veya Tümü’ne geçin.
                  </TableCell>
                </TableRow>
              ) : (
                filteredStocks.map((row) => {
                  const rowPrice =
                    stock?.ticker === row.ticker && priceReady
                      ? price
                      : row.referencePrice;
                  const max =
                    amount != null && amount > 0 && rowPrice != null && rowPrice > 0
                      ? Math.floor(amount / rowPrice)
                      : null;
                  const selected = stock?.ticker === row.ticker;
                  const stats = ranked.get(row.ticker);
                  return (
                    <TableRow
                      key={row.ticker}
                      data-state={selected ? "selected" : undefined}
                      tabIndex={0}
                      className={cn(
                        "rank-row cursor-pointer",
                        selected && "bg-ticker-muted/50",
                      )}
                      onClick={() => applyStock(row)}
                      onKeyDown={(event) => {
                        if (event.key === "Enter" || event.key === " ") {
                          event.preventDefault();
                          applyStock(row);
                        }
                      }}
                    >
                      <TableCell>
                        <TickerMark>{row.ticker}</TickerMark>
                      </TableCell>
                      <TableCell>{row.name}</TableCell>
                      <TableCell className="text-xs text-muted-foreground">
                        {row.markets.map((m) => MARKET_LABELS[m]).join(" · ")}
                      </TableCell>
                      <TableCell className="text-right font-mono text-gain">
                        {stats ? formatMoney(stats.score, 0) : "—"}
                      </TableCell>
                      <TableCell className="text-right font-mono text-gain">
                        {stats ? formatMoney(stats.scoreValue, 0) : "—"}
                      </TableCell>
                      <TableCell className="text-right font-mono text-gain">
                        <HypeScoreCell item={stats} />
                      </TableCell>
                      <TableCell className="text-right font-mono text-warn">
                        {rowPrice != null ? formatPrice(rowPrice) : "—"}
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
                      {amount != null && amount > 0 ? (
                        <TableCell className="text-right font-mono text-ticker">
                          {max != null ? max : "—"}
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

      <MarketRankingTable
        title="NASDAQ sıralaması"
        description="Nasdaq’taki ortak hisselerin tamamı listelenebilir. Varsayılan görünüm hacim + vol skoruna göre ilk 100; Hype ve Hacim + vol + hype ayrı filtrelerdir. ABD hisseleri TL hesaplayıcıya aktarılmaz."
        names={screener.nasdaqNames}
        stats={screener.nasdaq}
        status={screener.status}
        complete={screener.complete}
        currency="USD"
      />

      <MarketRankingTable
        title="NYSE sıralaması"
        description="NYSE’deki ortak hisselerin tamamı listelenebilir. Varsayılan görünüm hacim + vol skoruna göre ilk 100; Hype ve Hacim + vol + hype ayrı filtrelerdir. ABD hisseleri TL hesaplayıcıya aktarılmaz."
        names={screener.nyseNames}
        stats={screener.nyse}
        status={screener.status}
        complete={screener.complete}
        currency="USD"
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
  stock,
  amount,
  amountInput,
  price,
  priceInput,
  position,
  percent,
  side,
  pnlUp,
  pnlDown,
}: {
  stock?: SpotStock;
  amount: number | null;
  amountInput: string;
  price: number | null;
  priceInput: string;
  position: ReturnType<typeof buildSpotPosition> | null;
  percent: number;
  side: Side;
  pnlUp: number;
  pnlDown: number;
}) {
  if (!stock) {
    return (
      <EmptyState
        title="Hisse seçin"
        description="Soldan BIST 100, Yıldız veya Ana Pazar hissesini seçin. Kod veya adla arayabilirsiniz."
      />
    );
  }

  if (!priceInput.trim() || price == null || price <= 0) {
    return (
      <EmptyState
        title="Hisse fiyatını girin"
        description={
          stock.referencePrice != null
            ? `${stock.ticker} referans fiyatı ${formatPrice(stock.referencePrice)} TL. İsterseniz güncel fiyatı yazın.`
            : `${stock.ticker} için listede fiyat yok. Güncel pay fiyatını TL olarak girin.`
        }
      />
    );
  }

  if (!amountInput.trim()) {
    return (
      <EmptyState
        title="Alım tutarını girin"
        description={`${stock.ticker} ${formatPrice(price)} TL. Bu fiyatla kaç lot alınabileceğini hesaplarız.`}
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
        title="Bu tutarla lot alınamıyor"
        description={`${stock.ticker} için 1 lot ${formatPrice(price)} TL. Girdiğiniz ${formatTL(amount, 0)} 1 lota yetmiyor.`}
      />
    );
  }

  if (position.lots === 0) {
    return (
      <EmptyState
        title="Lot adedini girin"
        description={`Bu tutarla en fazla ${formatLots(position.maxLots)} alabilirsiniz.`}
      />
    );
  }

  const upLabel = side === "long" ? "Kazanç" : "Kayıp";
  const downLabel = side === "long" ? "Kayıp" : "Kazanç";
  const upPrice = priceAfterMove(price, percent);
  const downPrice = priceAfterMove(price, -percent);

  return (
    <>
      <div className="grid gap-3 sm:grid-cols-3">
        <StatCard
          icon={<LayersIcon />}
          label="Alınabilir lot"
          value={formatLots(position.lots)}
          hint={`${position.lots.toLocaleString("tr-TR")} pay · max ${position.maxLots}`}
          tone="ticker"
        />
        <StatCard
          icon={<WalletIcon />}
          label="Kullanılan tutar"
          value={formatTL(position.usedCost, 2)}
          hint={`Kalan ${formatTL(position.remaining, 2)}`}
          tone="warn"
        />
        <StatCard
          icon={<CoinsIcon />}
          label="Pozisyon değeri"
          value={formatTL(position.notional, 2)}
          hint="Kaldıraçsız · 1 lot = 1 pay"
          tone="gain"
        />
      </div>

      <div className="grid gap-3 md:grid-cols-2">
        <PnlCard
          direction="up"
          title={`Fiyat ${formatPercent(percent)} yükselirse`}
          priceFrom={price}
          priceTo={upPrice}
          pnl={pnlUp}
          usedCost={position.usedCost}
          label={upLabel}
        />
        <PnlCard
          direction="down"
          title={`Fiyat ${formatPercent(percent)} düşerse`}
          priceFrom={price}
          priceTo={downPrice}
          pnl={pnlDown}
          usedCost={position.usedCost}
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
            <TickerMark>{stock.ticker}</TickerMark> · {formatLots(position.lots)}{" "}
            · {formatPercent(percent)} hareket
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-3 sm:grid-cols-2">
          <SummaryRow
            label="Hareket sonrası değer (yükseliş)"
            value={formatTL(endingEquity(position.usedCost, pnlUp))}
            tone={pnlClass(pnlUp)}
          />
          <SummaryRow
            label="Hareket sonrası değer (düşüş)"
            value={formatTL(endingEquity(position.usedCost, pnlDown))}
            tone={pnlClass(pnlDown)}
          />
          <SummaryRow
            label="Sermayeye göre getiri (yükseliş)"
            value={formatPercent(returnOnMargin(pnlUp, position.usedCost))}
            tone={pnlClass(pnlUp)}
          />
          <SummaryRow
            label="Sermayeye göre getiri (düşüş)"
            value={formatPercent(returnOnMargin(pnlDown, position.usedCost))}
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
          Hisse
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
  usedCost,
  label,
}: {
  direction: "up" | "down";
  title: string;
  priceFrom: number;
  priceTo: number;
  pnl: number;
  usedCost: number;
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
          Sermayeye göre{" "}
          <span className={pnlClass(pnl)}>
            {formatPercent(returnOnMargin(pnl, usedCost))}
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
  stock,
  price,
  position,
  side,
  customPercent,
}: {
  stock: SpotStock;
  price: number;
  position: ReturnType<typeof buildSpotPosition>;
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
          {stock.ticker} · {side === "long" ? "Alış" : "Satış"} pozisyonunda
          fiyatın yüzde kaç gitmesi halinde kar veya zarar.
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
              <TableHead className="text-right text-warn">Sermaye getirisi</TableHead>
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
                    {formatPrice(priceAfterMove(price, pct))}
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
                    {formatPrice(priceAfterMove(price, -pct))}
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
                    {formatPercent(Math.abs(returnOnMargin(up, position.usedCost)))}
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
