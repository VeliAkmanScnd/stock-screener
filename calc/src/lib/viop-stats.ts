export type ViopBiasStat = {
  ticker: string;
  longWin: number;
  longLoss: number;
  longWinPct: number;
  longLossPct: number;
  shortWin: number;
  shortLoss: number;
  shortWinPct: number;
  shortLossPct: number;
  trades: number;
  longResult: number;
  shortResult: number;
  result: number;
};

export const VIOP_BIAS_STRATEGY = "15mn Bias + TS [60-233-233-7-60_max5]";

export const VIOP_BIAS_STATS: ViopBiasStat[] = [
  {"ticker": "AEFES", "longWin": 6, "longLoss": 1, "longWinPct": 24.0, "longLossPct": -2.5, "shortWin": 6, "shortLoss": 3, "shortWinPct": 24.0, "shortLossPct": -7.1, "trades": 16, "longResult": 21.5, "shortResult": 16.9, "result": 38.4},
  {"ticker": "AKBNK", "longWin": 4, "longLoss": 5, "longWinPct": 16.0, "longLossPct": -12.1, "shortWin": 5, "shortLoss": 6, "shortWinPct": 20.0, "shortLossPct": -16.95, "trades": 20, "longResult": 3.9, "shortResult": 3.05, "result": 6.95},
  {"ticker": "AKSEN", "longWin": 6, "longLoss": 4, "longWinPct": 24.0, "longLossPct": -12.7, "shortWin": 2, "shortLoss": 6, "shortWinPct": 8.0, "shortLossPct": -19.2, "trades": 18, "longResult": 11.3, "shortResult": -11.2, "result": 0.1},
  {"ticker": "ALARK", "longWin": 5, "longLoss": 3, "longWinPct": 20.0, "longLossPct": -8.14, "shortWin": 5, "shortLoss": 4, "shortWinPct": 20.0, "shortLossPct": -10.61, "trades": 17, "longResult": 11.86, "shortResult": 9.39, "result": 21.25},
  {"ticker": "ARCLK", "longWin": 2, "longLoss": 10, "longWinPct": 8.0, "longLossPct": -30.6, "shortWin": 8, "shortLoss": 3, "shortWinPct": 32.0, "shortLossPct": -8.3, "trades": 23, "longResult": -22.6, "shortResult": 23.7, "result": 1.1},
  {"ticker": "ASELS", "longWin": 5, "longLoss": 5, "longWinPct": 20.0, "longLossPct": -19.5, "shortWin": 6, "shortLoss": 3, "shortWinPct": 24.0, "shortLossPct": -9.8, "trades": 19, "longResult": 0.5, "shortResult": 14.2, "result": 14.7},
  {"ticker": "ASTOR", "longWin": 6, "longLoss": 1, "longWinPct": 24.0, "longLossPct": -4.8, "shortWin": 2, "shortLoss": 2, "shortWinPct": 8.0, "shortLossPct": -9.5, "trades": 11, "longResult": 19.2, "shortResult": -1.5, "result": 17.7},
  {"ticker": "BIMAS", "longWin": 6, "longLoss": 5, "longWinPct": 24.0, "longLossPct": -12.0, "shortWin": 3, "shortLoss": 9, "shortWinPct": 12.0, "shortLossPct": -22.8, "trades": 23, "longResult": 12.0, "shortResult": -10.8, "result": 1.2},
  {"ticker": "BRSAN", "longWin": 4, "longLoss": 4, "longWinPct": 16.0, "longLossPct": -11.5, "shortWin": 5, "shortLoss": 1, "shortWinPct": 20.0, "shortLossPct": -2.16, "trades": 14, "longResult": 4.5, "shortResult": 17.84, "result": 22.34},
  {"ticker": "CIMSA", "longWin": 2, "longLoss": 7, "longWinPct": 8.0, "longLossPct": -17.6, "shortWin": 4, "shortLoss": 9, "shortWinPct": 6.0, "shortLossPct": -20.8, "trades": 22, "longResult": -9.6, "shortResult": -14.8, "result": -24.4},
  {"ticker": "DOAS", "longWin": 4, "longLoss": 4, "longWinPct": 16.0, "longLossPct": -10.2, "shortWin": 7, "shortLoss": 4, "shortWinPct": 28.0, "shortLossPct": -5.22, "trades": 19, "longResult": 5.8, "shortResult": 22.78, "result": 28.58},
  {"ticker": "DOHOL", "longWin": 5, "longLoss": 8, "longWinPct": 20.0, "longLossPct": -22.32, "shortWin": 5, "shortLoss": 8, "shortWinPct": 20.0, "shortLossPct": -13.8, "trades": 26, "longResult": -2.32, "shortResult": 6.2, "result": 3.88},
  {"ticker": "EKGYO", "longWin": 7, "longLoss": 3, "longWinPct": 28.0, "longLossPct": -9.5, "shortWin": 4, "shortLoss": 6, "shortWinPct": 16.0, "shortLossPct": -17.1, "trades": 20, "longResult": 18.5, "shortResult": -1.1, "result": 17.4},
  {"ticker": "ENKAI", "longWin": 6, "longLoss": 3, "longWinPct": 24.0, "longLossPct": -9.2, "shortWin": 3, "shortLoss": 4, "shortWinPct": 12.0, "shortLossPct": -16.0, "trades": 16, "longResult": 14.8, "shortResult": -4.0, "result": 10.8},
  {"ticker": "ENJSA", "longWin": 4, "longLoss": 5, "longWinPct": 16.0, "longLossPct": -26.55, "shortWin": 4, "shortLoss": 5, "shortWinPct": 16.0, "shortLossPct": -18.3, "trades": 18, "longResult": -10.55, "shortResult": -2.3, "result": -12.85},
  {"ticker": "EREGL", "longWin": 7, "longLoss": 4, "longWinPct": 28.0, "longLossPct": -10.6, "shortWin": 5, "shortLoss": 4, "shortWinPct": 20.0, "shortLossPct": -9.8, "trades": 20, "longResult": 17.4, "shortResult": 10.2, "result": 27.6},
  {"ticker": "FROTO", "longWin": 4, "longLoss": 6, "longWinPct": 16.0, "longLossPct": -16.02, "shortWin": 6, "shortLoss": 3, "shortWinPct": 24.0, "shortLossPct": -6.4, "trades": 19, "longResult": -0.02, "shortResult": 17.6, "result": 17.58},
  {"ticker": "GARAN", "longWin": 5, "longLoss": 7, "longWinPct": 20.0, "longLossPct": -17.1, "shortWin": 3, "shortLoss": 6, "shortWinPct": 12.0, "shortLossPct": -19.75, "trades": 21, "longResult": 2.9, "shortResult": -7.75, "result": -4.85},
  {"ticker": "GUBRF", "longWin": 4, "longLoss": 5, "longWinPct": 16.0, "longLossPct": -11.0, "shortWin": 4, "shortLoss": 5, "shortWinPct": 16.0, "shortLossPct": -16.85, "trades": 18, "longResult": 5.0, "shortResult": -0.85, "result": 4.15},
  {"ticker": "HALKB", "longWin": 4, "longLoss": 3, "longWinPct": 16.0, "longLossPct": -7.6, "shortWin": 4, "shortLoss": 3, "shortWinPct": 16.0, "shortLossPct": -11.63, "trades": 14, "longResult": 8.4, "shortResult": 4.37, "result": 12.77},
  {"ticker": "HEKTS", "longWin": 3, "longLoss": 1, "longWinPct": 12.0, "longLossPct": -2.1, "shortWin": 5, "shortLoss": 1, "shortWinPct": 20.0, "shortLossPct": -4.5, "trades": 10, "longResult": 9.9, "shortResult": 15.5, "result": 25.4},
  {"ticker": "ISCTR", "longWin": 4, "longLoss": 3, "longWinPct": 16.0, "longLossPct": -7.9, "shortWin": 2, "shortLoss": 6, "shortWinPct": 8.0, "shortLossPct": -19.6, "trades": 15, "longResult": 8.1, "shortResult": -11.6, "result": -3.5},
  {"ticker": "KCHOL", "longWin": 8, "longLoss": 3, "longWinPct": 32.0, "longLossPct": -8.5, "shortWin": 4, "shortLoss": 6, "shortWinPct": 16.0, "shortLossPct": -12.0, "trades": 21, "longResult": 23.5, "shortResult": 4.0, "result": 27.5},
  {"ticker": "TRMET", "longWin": 7, "longLoss": 5, "longWinPct": 28.0, "longLossPct": -14.35, "shortWin": 3, "shortLoss": 8, "shortWinPct": 12.0, "shortLossPct": -32.5, "trades": 23, "longResult": 13.65, "shortResult": -20.5, "result": -6.85},
  {"ticker": "TRALT", "longWin": 5, "longLoss": 3, "longWinPct": 20.0, "longLossPct": -13.2, "shortWin": 3, "shortLoss": 8, "shortWinPct": 12.0, "shortLossPct": -27.55, "trades": 19, "longResult": 6.8, "shortResult": -15.55, "result": -8.75},
  {"ticker": "KRDMD", "longWin": 5, "longLoss": 3, "longWinPct": 20.0, "longLossPct": -10.5, "shortWin": 4, "shortLoss": 5, "shortWinPct": 16.0, "shortLossPct": -20.4, "trades": 17, "longResult": 9.5, "shortResult": -4.4, "result": 5.1},
  {"ticker": "MGROS", "longWin": 3, "longLoss": 4, "longWinPct": 12.0, "longLossPct": -16.2, "shortWin": 5, "shortLoss": 5, "shortWinPct": 20.0, "shortLossPct": -11.05, "trades": 17, "longResult": -4.2, "shortResult": 8.95, "result": 4.75},
  {"ticker": "ODAS", "longWin": 4, "longLoss": 6, "longWinPct": 16.0, "longLossPct": -18.8, "shortWin": 5, "shortLoss": 8, "shortWinPct": 20.0, "shortLossPct": -27.7, "trades": 23, "longResult": -2.8, "shortResult": -7.7, "result": -10.5},
  {"ticker": "OYAKC", "longWin": 2, "longLoss": 9, "longWinPct": 8.0, "longLossPct": -28.6, "shortWin": 5, "shortLoss": 8, "shortWinPct": 20.0, "shortLossPct": -19.2, "trades": 24, "longResult": -20.6, "shortResult": 0.8, "result": -19.8},
  {"ticker": "PETKM", "longWin": 7, "longLoss": 2, "longWinPct": 28.0, "longLossPct": -3.65, "shortWin": 4, "shortLoss": 2, "shortWinPct": 16.0, "shortLossPct": -6.95, "trades": 15, "longResult": 24.35, "shortResult": 9.05, "result": 33.4},
  {"ticker": "PGSUS", "longWin": 4, "longLoss": 3, "longWinPct": 16.0, "longLossPct": -10.0, "shortWin": 4, "shortLoss": 2, "shortWinPct": 16.0, "shortLossPct": -5.4, "trades": 13, "longResult": 6.0, "shortResult": 10.6, "result": 16.6},
  {"ticker": "SAHOL", "longWin": 5, "longLoss": 4, "longWinPct": 20.0, "longLossPct": -7.3, "shortWin": 6, "shortLoss": 1, "shortWinPct": 24.0, "shortLossPct": -2.63, "trades": 16, "longResult": 12.7, "shortResult": 21.37, "result": 34.07},
  {"ticker": "SASA", "longWin": 0, "longLoss": 1, "longWinPct": 0.0, "longLossPct": -3.8, "shortWin": 3, "shortLoss": 1, "shortWinPct": 12.0, "shortLossPct": -2.23, "trades": 5, "longResult": -3.8, "shortResult": 9.77, "result": 5.97},
  {"ticker": "SISE", "longWin": 6, "longLoss": 4, "longWinPct": 24.0, "longLossPct": -11.4, "shortWin": 6, "shortLoss": 5, "shortWinPct": 24.0, "shortLossPct": -13.55, "trades": 21, "longResult": 12.6, "shortResult": 10.45, "result": 23.05},
  {"ticker": "SOKM", "longWin": 5, "longLoss": 4, "longWinPct": 20.0, "longLossPct": -11.4, "shortWin": 5, "shortLoss": 3, "shortWinPct": 20.0, "shortLossPct": -11.05, "trades": 17, "longResult": 8.6, "shortResult": 8.95, "result": 17.55},
  {"ticker": "TAVHL", "longWin": 3, "longLoss": 5, "longWinPct": 12.0, "longLossPct": -12.0, "shortWin": 4, "shortLoss": 8, "shortWinPct": 16.0, "shortLossPct": -21.3, "trades": 20, "longResult": 0.0, "shortResult": -5.3, "result": -5.3},
  {"ticker": "TCELL", "longWin": 7, "longLoss": 5, "longWinPct": 28.0, "longLossPct": -13.3, "shortWin": 5, "shortLoss": 6, "shortWinPct": 20.0, "shortLossPct": -21.15, "trades": 23, "longResult": 14.7, "shortResult": -1.15, "result": 13.55},
  {"ticker": "THYAO", "longWin": 3, "longLoss": 5, "longWinPct": 12.0, "longLossPct": -9.15, "shortWin": 5, "shortLoss": 5, "shortWinPct": 20.0, "shortLossPct": -9.2, "trades": 18, "longResult": 2.85, "shortResult": 10.8, "result": 13.65},
  {"ticker": "TKFEN", "longWin": 6, "longLoss": 4, "longWinPct": 24.0, "longLossPct": -12.95, "shortWin": 5, "shortLoss": 2, "shortWinPct": 20.0, "shortLossPct": -4.75, "trades": 17, "longResult": 11.05, "shortResult": 15.25, "result": 26.3},
  {"ticker": "TOASO", "longWin": 5, "longLoss": 3, "longWinPct": 20.0, "longLossPct": -5.5, "shortWin": 3, "shortLoss": 6, "shortWinPct": 12.0, "shortLossPct": -15.75, "trades": 17, "longResult": 14.5, "shortResult": -3.75, "result": 10.75},
  {"ticker": "TSKB", "longWin": 5, "longLoss": 9, "longWinPct": 20.0, "longLossPct": -35.8, "shortWin": 4, "shortLoss": 9, "shortWinPct": 16.0, "shortLossPct": -25.15, "trades": 27, "longResult": -15.8, "shortResult": -9.15, "result": -24.95},
  {"ticker": "TTKOM", "longWin": 4, "longLoss": 6, "longWinPct": 16.0, "longLossPct": -17.0, "shortWin": 5, "shortLoss": 6, "shortWinPct": 20.0, "shortLossPct": -14.1, "trades": 21, "longResult": -1.0, "shortResult": 5.9, "result": 4.9},
  {"ticker": "TUPRS", "longWin": 5, "longLoss": 6, "longWinPct": 20.0, "longLossPct": -19.2, "shortWin": 3, "shortLoss": 5, "shortWinPct": 12.0, "shortLossPct": -15.65, "trades": 19, "longResult": 0.8, "shortResult": -3.65, "result": -2.85},
  {"ticker": "ULKER", "longWin": 6, "longLoss": 2, "longWinPct": 24.0, "longLossPct": -5.6, "shortWin": 4, "shortLoss": 4, "shortWinPct": 16.0, "shortLossPct": -9.12, "trades": 16, "longResult": 18.4, "shortResult": 6.88, "result": 25.28},
  {"ticker": "VAKBN", "longWin": 4, "longLoss": 7, "longWinPct": 16.0, "longLossPct": -23.4, "shortWin": 4, "shortLoss": 6, "shortWinPct": 16.0, "shortLossPct": -19.97, "trades": 21, "longResult": -7.4, "shortResult": -3.97, "result": -11.37},
  {"ticker": "VESTL", "longWin": 5, "longLoss": 6, "longWinPct": 20.0, "longLossPct": -18.5, "shortWin": 6, "shortLoss": 6, "shortWinPct": 24.0, "shortLossPct": -20.35, "trades": 23, "longResult": 1.5, "shortResult": 3.65, "result": 5.15},
  {"ticker": "YKBNK", "longWin": 2, "longLoss": 9, "longWinPct": 8.0, "longLossPct": -26.8, "shortWin": 4, "shortLoss": 7, "shortWinPct": 16.0, "shortLossPct": -20.6, "trades": 22, "longResult": -18.8, "shortResult": -4.6, "result": -23.4},
];
