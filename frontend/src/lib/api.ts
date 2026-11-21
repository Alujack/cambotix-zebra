// Typed client for the read-only record API (web/api.py). Server-side only: API_URL points at the
// internal `api` container, which is never published. Reads are uncached here (Cache Components keep
// them out of the static shell) because the API itself caches every answer for 60 seconds.

const API_URL = process.env.API_URL ?? "http://127.0.0.1:8090";

export type Summary = {
  closed: number;
  wins: number;
  win_rate: number | null;
  total_r_tp1: number;
  expectancy_r: number;
  profit_factor?: number | null;
  total_r_scaled: number;
  max_drawdown_r?: number;
  ambiguous?: number;
  verdict?: "GO" | "NO-GO" | "NOT ENOUGH DATA";
  min_trades?: number;
  max_drawdown_limit_r?: number;
};

export type Record = {
  published: number;
  open: number;
  not_filled: number;
  not_filled_reasons: { [reason: string]: number };
  headline: Required<Summary>;
  by_model: { [name: string]: Summary };
  by_symbol: { [name: string]: Summary };
  by_month: { [name: string]: Summary };
  by_session: { [name: string]: Summary };
  by_caution: { [name: string]: Summary };
  chain: { valid: boolean; broken_at: number | null; rows: number; head_seq?: number; head_hash?: string };
  basis: string;
  journal: { evaluated: number; approved: number; rejected: number; pending: number };
  generated_at: string;
};

export type LedgerEvent = {
  kind: string;
  time: number;
  price?: number;
  r?: number;
  reason?: string;
  exit?: string;
  targets_hit?: number;
  ambiguous?: boolean;
  r_tp1?: number;
  r_scaled?: number;
};

export type Plan = {
  seq: number;
  event_id: string;
  symbol: string;
  model: string;
  timeframe: string;
  direction: "BUY" | "SELL";
  session: string | null;
  cautions: string[];
  published_at: number;
  status: "open" | "closed" | "not_filled";
  entry_type: string | null;
  levels_public: boolean;
  entry_expiry_minutes: number;
  max_hold_minutes: number;
  expires_at: number;
  hold_until: number;
  levels?: { entry: number; stop: number; targets: [number, number, string][] };
  result?: { exit?: string; targets_hit?: number; ambiguous?: boolean; r_tp1?: number; r_scaled?: number; reason?: string };
  events: LedgerEvent[];
};

export type Ticker = {
  symbol: string;
  price: number;
  time: number;
  change_24h_pct: number | null;
  source: string;
};

export type NewsItem = { time: number; title: string; country: string; severity: "HIGH" | "MEDIUM" | "LOW"; affects: string[]; blocks_setups: boolean };

export type Candle = { t: number; o: number; h: number; l: number; c: number; n: number };
export type Reading = { value?: number; verdict: string; tone: "green" | "red" | "gold" | "neutral"; percent: number; k?: number; d?: number; plus_di?: number; minus_di?: number; percent_of_price?: number; ema20?: number; ema50?: number; ema200?: number };
export type Indicators = { symbol: string; tf: string; close: number; bars: number; at: number; rsi: Reading; stoch: Reading; macd_hist: Reading; adx: Reading; bollinger_b: Reading; atr: Reading; ema: Reading };

export type LedgerRow = { seq: number; event_id: string; kind: string; body: string; hash: string };

async function get<T>(path: string, fallback: T): Promise<T> {
  try {
    const response = await fetch(`${API_URL}${path}`, { cache: "no-store" });
    if (!response.ok) return fallback;
    return (await response.json()) as T;
  } catch {
    // The site stays up with empty sections when the API is restarting; nothing is invented.
    return fallback;
  }
}

export const emptyRecord: Record = {
  published: 0,
  open: 0,
  not_filled: 0,
  not_filled_reasons: {},
  headline: {
    closed: 0, wins: 0, win_rate: null, total_r_tp1: 0, expectancy_r: 0, profit_factor: null, total_r_scaled: 0,
    max_drawdown_r: 0, ambiguous: 0, verdict: "NOT ENOUGH DATA", min_trades: 150, max_drawdown_limit_r: 10,
  },
  by_model: {}, by_symbol: {}, by_month: {}, by_session: {}, by_caution: {},
  chain: { valid: true, broken_at: null, rows: 0, head_seq: 0, head_hash: "0".repeat(64) },
  basis: "",
  journal: { evaluated: 0, approved: 0, rejected: 0, pending: 0 },
  generated_at: "",
};

export const getRecord = () => get<Record>("/record", emptyRecord);
export const getSignals = (limit = 60) => get<Plan[]>(`/signals?limit=${limit}`, []);
export const getPlan = (seq: number) => get<Plan | null>(`/signals/${seq}`, null);
export const getTickers = () => get<Ticker[]>("/tickers", []);
export const getCandles = (symbol: string, tf = "15m", to?: number, bars = 200) =>
  get<{ symbol: string; tf: string; candles: Candle[] }>(`/candles/${symbol}?tf=${tf}&bars=${bars}${to ? `&to=${to}` : ""}`, { symbol, tf, candles: [] });
export const getIndicators = (symbol: string, tf = "15m", at?: number) =>
  get<Indicators | null>(`/indicators/${symbol}?tf=${tf}${at ? `&at=${at}` : ""}`, null);
export const getNews = () => get<NewsItem[]>("/news", []);
export const getLedger = (after = 0) => get<LedgerRow[]>(`/ledger?after=${after}`, []);
