import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const SKIP_NAME =
  /\b(Warrant|Warrants|Right|Rights|Unit|Units|Preferred|Preference|Note|Notes|Bond|Bonds|Debenture|When[- ]Issued|Test Issue|NextShares)\b/i;

function yahooSymbol(symbol) {
  return symbol.replace(/\./g, "-").trim().toUpperCase();
}

function displayName(name) {
  return name
    .replace(/\s*-\s*American Depository Shares.*$/i, "")
    .replace(/\s*-\s*American Depositary Shares.*$/i, "")
    .replace(/\s*-\s*Common Stock.*$/i, "")
    .replace(/\s*-\s*Ordinary Shares?.*$/i, "")
    .replace(/\s*-\s*Class [A-Z][A-Z0-9 ]*$/i, "")
    .replace(/\s+Common Stock\s*$/i, "")
    .replace(/\s+Ordinary Shares?\s*$/i, "")
    .replace(/\s+Common Shares?\s*$/i, "")
    .trim();
}

function skipSymbol(symbol) {
  if (!symbol || symbol.length > 8) return true;
  if (/[/$^+=\s]/.test(symbol)) return true;
  return false;
}

export function parseNasdaqListed(text) {
  const rows = [];
  for (const line of text.split(/\r?\n/)) {
    if (!line || line.startsWith("Symbol") || line.startsWith("File Creation")) continue;
    const parts = line.split("|");
    if (parts.length < 8) continue;
    const [symbol, name, , testIssue, , , etf, nextShares] = parts;
    if (testIssue === "Y" || etf === "Y" || nextShares === "Y") continue;
    if (skipSymbol(symbol) || SKIP_NAME.test(name)) continue;
    rows.push({
      ticker: yahooSymbol(symbol),
      name: displayName(name) || name.trim(),
      exchange: "nasdaq",
      yahoo: yahooSymbol(symbol),
      currency: "USD",
    });
  }
  return rows;
}

export function parseNyseListed(text) {
  const rows = [];
  for (const line of text.split(/\r?\n/)) {
    if (!line || line.startsWith("ACT Symbol") || line.startsWith("File Creation")) continue;
    const parts = line.split("|");
    if (parts.length < 8) continue;
    const [symbol, name, exchange, , etf, , testIssue] = parts;
    if (exchange !== "N") continue;
    if (testIssue === "Y" || etf === "Y") continue;
    if (skipSymbol(symbol) || SKIP_NAME.test(name)) continue;
    rows.push({
      ticker: yahooSymbol(symbol),
      name: displayName(name) || name.trim(),
      exchange: "nyse",
      yahoo: yahooSymbol(symbol),
      currency: "USD",
    });
  }
  return rows;
}

export function mergeUsListings(nasdaqRows, nyseRows) {
  const seen = new Set();
  const out = [];
  for (const row of [...nasdaqRows, ...nyseRows]) {
    if (seen.has(row.ticker)) continue;
    seen.add(row.ticker);
    out.push(row);
  }
  return out;
}

const NASDAQ_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt";
const OTHER_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt";

export async function fetchUsListings(fallbackPath) {
  try {
    const [nasdaqText, otherText] = await Promise.all([
      fetchText(NASDAQ_URL),
      fetchText(OTHER_URL),
    ]);
    const merged = mergeUsListings(
      parseNasdaqListed(nasdaqText),
      parseNyseListed(otherText),
    );
    if (merged.length < 500) throw new Error("short listing");
    return merged;
  } catch (error) {
    if (!fallbackPath || !fs.existsSync(fallbackPath)) throw error;
    return JSON.parse(fs.readFileSync(fallbackPath, "utf8"));
  }
}

async function fetchText(url) {
  const response = await fetch(url, {
    headers: { "User-Agent": "Mozilla/5.0" },
    signal: AbortSignal.timeout(20_000),
  });
  if (!response.ok) throw new Error(`HTTP ${response.status} ${url}`);
  return response.text();
}

const isMain = process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url);
if (isMain) {
  const root = path.join(path.dirname(fileURLToPath(import.meta.url)), "..");
  const outPath = path.join(root, "data/us-listings.json");
  const listings = await fetchUsListings(outPath);
  fs.writeFileSync(outPath, `${JSON.stringify(listings)}\n`);
  const nasdaq = listings.filter((row) => row.exchange === "nasdaq").length;
  const nyse = listings.filter((row) => row.exchange === "nyse").length;
  console.log(`Yazıldı ${outPath}: Nasdaq ${nasdaq}, NYSE ${nyse}, toplam ${listings.length}`);
}
