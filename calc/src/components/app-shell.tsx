"use client";

import * as React from "react";
import { Calculator } from "@/components/calculator";
import { SpotCalculator } from "@/components/spot-calculator";
import { cn } from "@/lib/utils";

type Tab = "viop" | "hisse";

function readEmbedQuery(): { tab: Tab; embed: boolean } {
  if (typeof window === "undefined") return { tab: "viop", embed: false };
  const params = new URLSearchParams(window.location.search);
  const tab = params.get("tab") === "hisse" ? "hisse" : "viop";
  return { tab, embed: params.get("embed") === "1" };
}

export function AppShell() {
  const [booted, setBooted] = React.useState(false);
  const [tab, setTab] = React.useState<Tab>("viop");
  const [embed, setEmbed] = React.useState(false);
  const isViop = tab === "viop";

  React.useEffect(() => {
    const query = readEmbedQuery();
    setTab(query.tab);
    setEmbed(query.embed);
    setBooted(true);
  }, []);

  if (!booted) {
    return <div className="flex flex-1 bg-background" />;
  }

  return (
    <div className="flex flex-1 flex-col">
      {embed ? null : (
        <div className="h-1 bg-gradient-to-r from-ticker via-primary to-gain" />
      )}
      {embed ? null : (
        <header className="border-b border-ticker/20 bg-card/40 backdrop-blur-md">
          <div className="mx-auto flex w-full max-w-7xl flex-col gap-3 px-4 py-6 sm:flex-row sm:items-end sm:justify-between sm:px-6">
            <div className="space-y-2">
              <p className="flex items-center gap-2 text-[11px] font-semibold tracking-[0.22em] text-ticker uppercase">
                <span className="inline-block size-1.5 rounded-full bg-gain shadow-[0_0_12px_var(--gain)]" />
                BIST · Screener
              </p>
              <h1 className="font-heading text-2xl font-semibold tracking-tight sm:text-3xl">
                {isViop ? "VIOP hesaplayıcı" : "Hisse hesaplayıcı"}
              </h1>
              <p className="max-w-2xl text-sm text-pretty text-muted-foreground">
                {isViop
                  ? "Teminat tutarını ve dayanak varlığı girin; pay, endeks, döviz ve emtiada kaç lot açabileceğinizi ve yüzde hareketin kar/zararını görün."
                  : "Alım tutarını ve hisseyi girin; BIST 100, Yıldız ve Ana Pazar’da kaç lot alınabileceğini görün. Altta BIST, Nasdaq ve NYSE hacim + volatilite sıralamaları vardır."}
              </p>
            </div>
            <div className="flex flex-wrap gap-2 text-[11px] sm:justify-end">
              {isViop ? (
                <>
                  <span className="rounded-full bg-ticker-muted px-2.5 py-1 font-mono text-ticker">
                    Çarpan sözleşmeye göre
                  </span>
                  <span className="rounded-full bg-warn-muted px-2.5 py-1 font-mono text-warn">
                    K/Z = lot × çarpan × fiyat × %
                  </span>
                </>
              ) : (
                <>
                  <span className="rounded-full bg-ticker-muted px-2.5 py-1 font-mono text-ticker">
                    1 lot = 1 pay
                  </span>
                  <span className="rounded-full bg-warn-muted px-2.5 py-1 font-mono text-warn">
                    K/Z = lot × fiyat × %
                  </span>
                </>
              )}
            </div>
          </div>
          <div className="mx-auto w-full max-w-7xl px-4 sm:px-6">
            <div
              role="tablist"
              aria-label="Hesaplayıcı"
              className="flex gap-1 border-b border-ticker/15"
            >
              <TabButton
                active={isViop}
                onClick={() => setTab("viop")}
                label="VIOP"
              />
              <TabButton
                active={!isViop}
                onClick={() => setTab("hisse")}
                label="Hisse"
              />
            </div>
          </div>
        </header>
      )}

      <main
        className={cn(
          "mx-auto w-full max-w-7xl flex-1",
          embed ? "px-3 py-4 sm:px-4" : "px-4 py-6 sm:px-6 sm:py-8",
        )}
      >
        {isViop ? <Calculator /> : <SpotCalculator />}
      </main>

      {embed ? null : (
        <footer className="border-t border-ticker/15 bg-card/30">
          <div className="mx-auto max-w-7xl px-4 py-4 text-xs text-muted-foreground sm:px-6">
            {isViop
              ? "Teminat, fiyat ve kaldıraç her iş günü otomatik yenilenir (VIOP kapanış sonrası); aracı kurum oranlarıyla küçük fark olabilir."
              : "Hisse fiyatları VIOP referans listesinden gelir veya elle girilir; Nasdaq ve NYSE tabloları bilgi amaçlıdır. Güncel borsa fiyatlarıyla fark gösterebilir."}{" "}
            Bu araç yatırım tavsiyesi değildir.
          </div>
        </footer>
      )}
    </div>
  );
}

function TabButton({
  active,
  onClick,
  label,
}: {
  active: boolean;
  onClick: () => void;
  label: string;
}) {
  return (
    <button
      type="button"
      role="tab"
      aria-selected={active}
      onClick={onClick}
      className={cn(
        "-mb-px border-b-2 px-4 py-2.5 text-sm font-medium transition-colors",
        active
          ? "border-ticker text-ticker"
          : "border-transparent text-muted-foreground hover:text-foreground",
      )}
    >
      {label}
    </button>
  );
}
