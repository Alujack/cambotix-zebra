"use client";

import { useNow } from "@/components/terminal/Clocks";
import { price as format } from "@/lib/format";
import { change24h, useLiveQuote } from "@/lib/live";

const FRESH_SECONDS = 30;

// Price, 24 h change and freshness tag for one ticker-strip item. Shows the server's last M1 close until a live
// quote arrives, then the live bid; the tag reads "live" only while ticks keep coming.
export default function LiveTickerValues({ symbol, price, change, price24h, labels }: { symbol: string; price: number; change: number | null; price24h: number | null; labels: { live: string; delayed: string } }) {
  const live = useLiveQuote(symbol);
  const now = useNow(5000);
  const value = live?.bid ?? price;
  const shown = live ? change24h(live.bid, price24h) ?? change : change;
  const fresh = live !== undefined && now !== null && now - live.time_ms / 1000 < FRESH_SECONDS;
  const tone = shown === null ? "text-muted" : shown >= 0 ? "text-green" : "text-red";
  return (
    <>
      <span className="num text-text/90">{format(value)}</span>
      <span className={`num ${tone}`}>{shown === null ? "—" : `${shown >= 0 ? "+" : ""}${shown.toFixed(2)}%`}</span>
      <span className={`rounded px-1.5 py-0.5 text-[10px] ${fresh ? "bg-green/15 text-green" : "bg-surface-2 text-muted"}`}>{fresh ? labels.live : labels.delayed}</span>
    </>
  );
}
