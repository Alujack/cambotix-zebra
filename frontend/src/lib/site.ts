// Brand and people. Edit here; nothing else needs to change.

export const site = {
  name: "Zebra Empire",
  shortName: "Zebra",
  tagline: "by Cambotix Solutions",
  telegram: process.env.NEXT_PUBLIC_TELEGRAM_URL ?? "#",
  markets: ["XAUUSD", "EURUSD", "BTCUSD"],
};

// Watchlist metadata. `hours` drives the open/closed clock: fx = Sunday 22:00 to Friday 21:00 UTC (approximate; DST and broker breaks ignored).
export type MarketCategory = "metals" | "forex" | "crypto";
export const marketInfo: { [symbol: string]: { name: string; category: MarketCategory; hours: "fx" | "always" } } = {
  XAUUSD: { name: "Gold", category: "metals", hours: "fx" },
  EURUSD: { name: "Euro / US Dollar", category: "forex", hours: "fx" },
  GBPUSD: { name: "Pound / US Dollar", category: "forex", hours: "fx" },
  BTCUSD: { name: "Bitcoin", category: "crypto", hours: "always" },
  BTCUSDT: { name: "Bitcoin", category: "crypto", hours: "always" },
};
export const market = (symbol: string) => marketInfo[symbol] ?? { name: symbol, category: "forex" as MarketCategory, hours: "fx" as const };

// TradingView feeds for the free embed widget on the Terminal's Live view. These are the vendor's prices, not the broker's.
const tvSymbols: { [symbol: string]: string } = { XAUUSD: "OANDA:XAUUSD", EURUSD: "FX:EURUSD", GBPUSD: "FX:GBPUSD", BTCUSD: "BITSTAMP:BTCUSD", BTCUSDT: "BINANCE:BTCUSDT" };
export const tvSymbol = (symbol: string) => tvSymbols[symbol] ?? `FX:${symbol}`;
export const tvSource = (symbol: string) => tvSymbol(symbol).split(":")[0];
const tvIntervals: { [tf: string]: string } = { "1m": "1", "5m": "5", "15m": "15", "30m": "30", "1h": "60", "4h": "240", "1d": "D" };
export const tvInterval = (tf: string) => tvIntervals[tf] ?? "15";

// Units per standard lot, for the position-size calculator on a plan's detail page.
export const contractSize: { [symbol: string]: number } = { XAUUSD: 100, EURUSD: 100000, GBPUSD: 100000, BTCUSD: 1, BTCUSDT: 1 };

export type Member = { name: string; role: string; blurb?: string; links?: { label: string; href: string }[] };

// Placeholder until real names, photos and follower counts are supplied.
export const team: Member[] = [
  { name: "Cambotix desk", role: "Founder · rules and models", blurb: "Designs the detection rules and reviews every published plan by hand." },
  { name: "Zebra engine", role: "Grader · ledger", blurb: "Replays broker candles and writes the append-only, hash-chained record." },
];
