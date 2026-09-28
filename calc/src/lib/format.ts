const tr = new Intl.NumberFormat("tr-TR", {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

const trInt = new Intl.NumberFormat("tr-TR", {
  maximumFractionDigits: 0,
});

const trFlexible = new Intl.NumberFormat("tr-TR", {
  minimumFractionDigits: 0,
  maximumFractionDigits: 4,
});

export function formatMoney(value: number, digits = 2): string {
  return new Intl.NumberFormat("tr-TR", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(value);
}

export function formatCurrencyAmount(
  value: number,
  currency: "TL" | "USD",
  digits = 2,
): string {
  const amount = formatMoney(value, digits);
  return currency === "USD" ? `${amount} USD` : `${amount} TL`;
}

export function formatTL(value: number, digits = 2): string {
  return formatCurrencyAmount(value, "TL", digits);
}

export function formatPrice(value: number): string {
  return tr.format(value);
}

export function formatLots(value: number): string {
  return `${trInt.format(value)} lot`;
}

export function formatPercent(value: number, digits = 2): string {
  return `%${new Intl.NumberFormat("tr-TR", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(value)}`;
}

export function formatLeverage(value: number): string {
  return `${tr.format(value)}x`;
}

export function formatSignedTL(value: number): string {
  const abs = formatTL(Math.abs(value));
  if (value > 0) return `+${abs}`;
  if (value < 0) return `−${abs}`;
  return abs;
}

export function formatCompactNumber(value: number): string {
  return trFlexible.format(value);
}

/** Compact notional volume, e.g. 1,2 Mr TL or 3,4 Mr USD. */
export function formatCompactMoney(
  value: number,
  currency: "TL" | "USD" = "TL",
): string {
  const unit = currency === "USD" ? "USD" : "TL";
  const abs = Math.abs(value);
  if (abs >= 1_000_000_000) {
    return `${formatMoney(value / 1_000_000_000, 1)} Mr ${unit}`;
  }
  if (abs >= 1_000_000) {
    return `${formatMoney(value / 1_000_000, 1)} Mn ${unit}`;
  }
  if (abs >= 1_000) {
    return `${formatMoney(value / 1_000, 0)} B ${unit}`;
  }
  return currency === "USD"
    ? `${formatMoney(value, 0)} USD`
    : formatTL(value, 0);
}

export function formatCompactTL(value: number): string {
  return formatCompactMoney(value, "TL");
}

/** Last session vs 20d average, e.g. 2,4×. */
export function formatRelativeVolume(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return "—";
  return `${formatMoney(value, 1)}×`;
}

/**
 * Parses Turkish or English numeric input.
 * Accepts 0,54 / 0.54 / %0,54 / 25.000 / 25.000,50 / 25000
 */
export function parseTrNumber(raw: string): number | null {
  let cleaned = raw.trim();
  if (!cleaned) return null;

  cleaned = cleaned
    .replace(/%/g, "")
    .replace(/₺/g, "")
    .replace(/tl/gi, "")
    .replace(/\s/g, "")
    .replace(/−/g, "-");

  if (!cleaned || cleaned === "-" || cleaned === "+" || cleaned === ".") return null;

  const negative = cleaned.startsWith("-");
  const positive = cleaned.startsWith("+");
  if (negative || positive) cleaned = cleaned.slice(1);
  if (!cleaned) return null;

  if (!/^\d+[.,]?\d*$|^\d{1,3}([.]\d{3})+(,\d+)?$|^\d{1,3}([,]\d{3})+([.]\d+)?$/.test(cleaned)) {
    if (!/^[\d.,]+$/.test(cleaned)) return null;
  }

  const lastComma = cleaned.lastIndexOf(",");
  const lastDot = cleaned.lastIndexOf(".");
  let normalized: string;

  if (lastComma !== -1 && lastDot !== -1) {
    if (lastComma > lastDot) {
      normalized = cleaned.replace(/\./g, "").replace(",", ".");
    } else {
      normalized = cleaned.replace(/,/g, "");
    }
  } else if (lastComma !== -1) {
    const parts = cleaned.split(",");
    if (parts.length === 2 && parts[1].length > 0 && parts[1].length <= 4) {
      normalized = `${parts[0]}.${parts[1]}`;
    } else {
      normalized = cleaned.replace(/,/g, "");
    }
  } else if (lastDot !== -1) {
    const parts = cleaned.split(".");
    if (parts.length === 2 && parts[1].length > 0 && parts[1].length <= 2) {
      normalized = cleaned;
    } else {
      normalized = cleaned.replace(/\./g, "");
    }
  } else {
    normalized = cleaned;
  }

  const value = Number(normalized);
  if (!Number.isFinite(value)) return null;
  return negative ? -value : value;
}
