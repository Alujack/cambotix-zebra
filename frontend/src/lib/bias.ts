import type { Indicators } from "@/lib/api";
import { price } from "@/lib/format";

// Market bias for the public Markets page, derived from the indicator readings web/indicators.py computes on broker
// candles. Four directional factors, each a plain rule on a number; no model writes any of it.
export type Vote = "bull" | "bear" | "flat";
export type Factor = { name: string; vote: Vote; detail: string };
export type Bias = { label: "Bullish" | "Bearish" | "Mixed"; tone: "green" | "red" | "neutral"; agree: number; factors: Factor[]; summary: string };

const sign = (value: number, deadband = 0): Vote => (value > deadband ? "bull" : value < -deadband ? "bear" : "flat");

export function bias(x: Indicators): Bias {
  const ema20 = x.ema.ema20 ?? x.close;
  const rsi = x.rsi.value ?? 50;
  const hist = x.macd_hist.value ?? 0;
  const factors: Factor[] = [
    { name: "EMA stack", vote: x.ema.verdict === "UPTREND" ? "bull" : x.ema.verdict === "DOWNTREND" ? "bear" : "flat", detail: x.ema.verdict.toLowerCase() },
    { name: "Price vs EMA20", vote: sign(x.close - ema20), detail: `${x.close >= ema20 ? "above" : "below"} ${price(ema20, x.close)}` },
    { name: "MACD histogram", vote: sign(hist), detail: hist > 0 ? "positive" : hist < 0 ? "negative" : "flat" },
    { name: "RSI side", vote: sign(rsi - 50, 2), detail: `RSI ${rsi.toFixed(0)}` },
  ];
  const bulls = factors.filter((f) => f.vote === "bull").length;
  const bears = factors.filter((f) => f.vote === "bear").length;
  const label = bulls >= 3 ? "Bullish" : bears >= 3 ? "Bearish" : "Mixed";
  const tone = label === "Bullish" ? "green" : label === "Bearish" ? "red" : "neutral";
  const agree = label === "Bullish" ? bulls : label === "Bearish" ? bears : Math.max(bulls, bears);
  const strength = x.adx.value === undefined ? "" : x.adx.value < 20 ? ` ADX ${x.adx.value.toFixed(0)} says the move is weak, so treat it as a range.` : ` ADX ${x.adx.value.toFixed(0)} says the trend has strength.`;
  const summary = `Price ${price(x.close)} is ${x.close >= ema20 ? "above" : "below"} EMA20 ${price(ema20, x.close)} with MACD ${factors[2].detail} and RSI ${rsi.toFixed(0)}.${strength}`;
  return { label, tone, agree, factors, summary };
}
