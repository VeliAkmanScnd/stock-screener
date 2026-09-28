export type ContractCurrency = "TL" | "USD";
export type ContractGroup = "pay" | "endeks" | "doviz" | "emtia";

export type Contract = {
  ticker: string;
  name: string;
  margin: number;
  price: number;
  leverage: number;
  multiplier: number;
  currency: ContractCurrency;
  group: ContractGroup;
};

export const GROUP_LABELS: Record<ContractGroup, string> = {
  pay: "Pay",
  endeks: "Endeks",
  doviz: "Döviz",
  emtia: "Emtia",
};

export const GROUP_ORDER: ContractGroup[] = ["endeks", "doviz", "emtia", "pay"];

const PAY: [string, string, number, number, number][] = [
  ["AEFES", "Anadolu Efes", 331, 19.48, 5.89],
  ["AKBNK", "Akbank", 1440, 71.7, 4.98],
  ["AKSEN", "Aksa Enerji", 1849, 75.05, 4.06],
  ["ALARK", "Alarko Holding", 1914, 111.7, 5.84],
  ["ARCLK", "Arçelik", 1520, 92.57, 6.09],
  ["ASELS", "Aselsan", 8463, 380.05, 4.49],
  ["ASTOR", "Astor Enerji", 7286, 276.7, 3.8],
  ["BIMAS", "BİM", 6674, 421.65, 6.32],
  ["BRSAN", "Borusan", 16975, 658.6, 3.88],
  ["CIMSA", "Çimsa", 772, 44.16, 5.72],
  ["DOAS", "Doğuş Otomotiv", 3138, 163.15, 5.2],
  ["DOHOL", "Doğan Holding", 385, 21.57, 5.6],
  ["EKGYO", "Emlak Konut GYO", 399, 20.37, 5.11],
  ["ENKAI", "Enka İnşaat", 1538, 87.53, 5.69],
  ["ENJSA", "Enerjisa Enerji", 2054, 113.2, 5.51],
  ["EREGL", "Ereğli Demir Çelik", 665, 39.6, 5.95],
  ["FROTO", "Ford Otosan", 1418, 80.55, 5.68],
  ["GARAN", "Garanti BBVA", 2418, 131.1, 5.42],
  ["GUBRF", "Gübre Fabrikaları", 9967, 470.65, 4.72],
  ["HALKB", "Halkbank", 1349, 45.22, 3.35],
  ["HEKTS", "Hektaş", 63, 2.77, 4.4],
  ["ISCTR", "İş Bankası (C)", 224, 13.67, 6.1],
  ["KCHOL", "Koç Holding", 3517, 222.55, 6.33],
  ["TRMET", "TRMET", 2953, 135.5, 4.59],
  ["TRALT", "TRALT", 1255, 51.71, 4.12],
  ["KRDMD", "Kardemir (D)", 744, 45.12, 6.06],
  ["MGROS", "Migros", 9488, 527.9, 5.56],
  ["ODAS", "Odaş Elektrik", 168, 7.22, 4.3],
  ["OYAKC", "OYAK Çimento", 397, 21.6, 5.44],
  ["PETKM", "Petkim", 365, 23.2, 6.36],
  ["PGSUS", "Pegasus", 3041, 152.75, 5.02],
  ["SAHOL", "Sabancı Holding", 1560, 93.33, 5.98],
  ["SASA", "Sasa Polyester", 52, 2.94, 5.65],
  ["SISE", "Şişecam", 658, 43.64, 6.63],
  ["SOKM", "Şok Marketler", 986, 59.11, 5.99],
  ["TAVHL", "TAV Havalimanları", 5193, 261, 5.03],
  ["TCELL", "Turkcell", 1676, 101.4, 6.05],
  ["THYAO", "Türk Hava Yolları", 5068, 295.3, 5.83],
  ["TKFEN", "Tekfen Holding", 4871, 234.9, 4.82],
  ["TOASO", "Tofaş", 5342, 290.3, 5.43],
  ["TSKB", "TSKB", 198, 11.36, 5.74],
  ["TTKOM", "Türk Telekom", 953, 56.26, 5.9],
  ["TUPRS", "Tüpraş", 6978, 407.85, 5.84],
  ["ULKER", "Ülker", 1585, 91, 5.74],
  ["VAKBN", "VakıfBank", 606, 35, 5.78],
  ["VESTL", "Vestel", 689, 27.2, 3.95],
  ["YKBNK", "Yapı Kredi", 724, 35.83, 4.95],
];

export const CONTRACTS: Contract[] = [
  { ticker: "BIST30", name: "BIST 30", margin: 22353, price: 17800, leverage: 7.96, multiplier: 10, currency: "TL", group: "endeks" },
  { ticker: "XLBNK", name: "BIST Banka", margin: 26677, price: 15938, leverage: 5.97, multiplier: 10, currency: "TL", group: "endeks" },
  { ticker: "X10XB", name: "BIST 10 Banka", margin: 31003, price: 22141, leverage: 7.14, multiplier: 10, currency: "TL", group: "endeks" },
  { ticker: "EURTRY", name: "EUR/TRY", margin: 8947, price: 56.7, leverage: 6.34, multiplier: 1000, currency: "TL", group: "doviz" },
  { ticker: "USDTRY", name: "USD/TRY", margin: 8137, price: 56.89, leverage: 6.99, multiplier: 1000, currency: "TL", group: "doviz" },
  { ticker: "CNHTRY", name: "CNH/TRY", margin: 9896, price: 7.4, leverage: 7.48, multiplier: 10000, currency: "TL", group: "doviz" },
  { ticker: "RUBTRY", name: "RUB/TRY", margin: 12610, price: 0.57, leverage: 4.52, multiplier: 100000, currency: "TL", group: "doviz" },
  { ticker: "EURUSD", name: "EUR/USD", margin: 73, price: 1.16, leverage: 15.83, multiplier: 1000, currency: "USD", group: "doviz" },
  { ticker: "GBPUSD", name: "GBP/USD", margin: 84, price: 1.35, leverage: 16.07, multiplier: 1000, currency: "USD", group: "doviz" },
  { ticker: "XAUUSD", name: "Altın (USD)", margin: 557, price: 4429.7, leverage: 7.95, multiplier: 1, currency: "USD", group: "emtia" },
  { ticker: "XAGUSD", name: "Gümüş (USD)", margin: 180, price: 66.18, leverage: 3.68, multiplier: 10, currency: "USD", group: "emtia" },
  { ticker: "XAUTRY", name: "Altın (TL)", margin: 1268, price: 7944.8, leverage: 6.27, multiplier: 1, currency: "TL", group: "emtia" },
  { ticker: "XPDUSD", name: "Paladyum", margin: 383, price: 1330, leverage: 3.47, multiplier: 1, currency: "USD", group: "emtia" },
  { ticker: "XPTUSD", name: "Platin", margin: 410, price: 1797.9, leverage: 4.39, multiplier: 1, currency: "USD", group: "emtia" },
  ...PAY.map(([ticker, name, margin, price, leverage]) => ({
    ticker,
    name,
    margin,
    price,
    leverage,
    multiplier: 100,
    currency: "TL" as const,
    group: "pay" as const,
  })),
];

export function usdTryRate(): number {
  return CONTRACTS.find((c) => c.ticker === "USDTRY")?.price ?? 56.89;
}

export function marginTl(contract: Contract, fx = usdTryRate()): number {
  return contract.currency === "USD" ? contract.margin * fx : contract.margin;
}

export function notionalTl(
  lots: number,
  contract: Contract,
  fx = usdTryRate(),
): number {
  const native = lots * contract.price * contract.multiplier;
  return contract.currency === "USD" ? native * fx : native;
}

export function unitLabel(contract: Contract): string {
  if (contract.group === "pay") return `${contract.multiplier} pay`;
  if (contract.group === "endeks") return `çarpan ${contract.multiplier}`;
  if (contract.group === "doviz") return `çarpan ${contract.multiplier}`;
  return `çarpan ${contract.multiplier}`;
}

export function findContract(ticker: string): Contract | undefined {
  return CONTRACTS.find((c) => c.ticker === ticker);
}

export function contractsInGroup(group?: ContractGroup | "all"): Contract[] {
  if (!group || group === "all") return CONTRACTS;
  return CONTRACTS.filter((c) => c.group === group);
}

export function searchContracts(
  query: string,
  group?: ContractGroup | "all",
): Contract[] {
  const pool = contractsInGroup(group);
  const q = query.trim().toLocaleLowerCase("tr-TR");
  if (!q) return pool;
  return pool.filter((c) => {
    return (
      c.ticker.toLocaleLowerCase("tr-TR").includes(q) ||
      c.name.toLocaleLowerCase("tr-TR").includes(q) ||
      GROUP_LABELS[c.group].toLocaleLowerCase("tr-TR").includes(q)
    );
  });
}
