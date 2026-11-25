"use client";

import { Ago, fxSession, useNow } from "@/components/terminal/Clocks";
import { price } from "@/lib/format";
import { change24h, useLiveQuote } from "@/lib/live";

const STALE_SECONDS = 30;
const pct = (value: number | null) => (value === null ? "—" : `${value >= 0 ? "+" : ""}${value.toFixed(2)}%`);

type Initial = { price: number; time: number; change: number | null; price24h: number | null } | null;
type Labels = { paused: string; closed: string; noQuote: string };

// Header price for the Terminal: the broker's live bid, its 24 h change and age, updated on every tick.
// Falls back to the last stored M1 close until the first live quote arrives. "Market closed" replaces the age when an
// FX/metals market is shut (never for 24/7 markets); "Feed paused" shows when it is open but no tick came for 30 s.
export default function LivePrice({ symbol, hours, initial, showEmpty, labels }: { symbol: string; hours: "fx" | "always"; initial: Initial; showEmpty: boolean; labels: Labels }) {
  const live = useLiveQuote(symbol);
  const now = useNow(1000);
  const value = live?.bid ?? initial?.price;
  if (value === undefined) return showEmpty ? <span className="text-xs text-muted">{labels.noQuote}</span> : null;
  const time = live ? live.time_ms / 1000 : (initial?.time ?? 0);
  const change = live ? change24h(live.bid, initial?.price24h) ?? initial?.change ?? null : (initial?.change ?? null);
  const closed = hours === "fx" && now !== null && !fxSession(now).open;
  const paused = !closed && now !== null && now - time > STALE_SECONDS;
  return (
    <span className="flex items-center gap-2.5">
      <span className="price !text-[22px]">{price(value)}</span>
      <span className={`num rounded-md px-2 py-0.5 text-sm font-semibold ${change === null ? "bg-surface-2 text-muted" : change >= 0 ? "bg-green/15 text-green" : "bg-red/15 text-red"}`}>{pct(change)}</span>
      {closed ? (
        <span className="rounded-md border border-red/40 bg-red/[0.08] px-2 py-0.5 text-xs font-semibold text-red">{labels.closed}</span>
      ) : (
        <>
          <Ago since={time} suffix="" />
          {paused && <span className="rounded-md border border-gold/40 bg-gold/[0.08] px-2 py-0.5 text-xs font-semibold text-gold">{labels.paused}</span>}
        </>
      )}
    </span>
  );
}
