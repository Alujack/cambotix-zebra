import LiveTickerValues from "@/components/LiveTickerValues";
import type { Ticker } from "@/lib/api";
import { t, type Lang } from "@/lib/i18n";
import TickerTape from "./TickerTape";

// Endless marquee of the broker's prices, live while the feeder runs (LiveTickerValues), else the last M1 close. The list is rendered twice and slid by half its width, so it loops seamlessly.
// Pauses on hover; stands still under prefers-reduced-motion (see .marquee in globals.css).
export default function TickerStrip({ tickers, lang }: { tickers: Ticker[]; lang: Lang }) {
  const d = t(lang);
  // No broker candles yet: show TradingView's live vendor prices instead of an empty strip.
  if (tickers.length === 0) return <TickerTape />;
  // Repeat short lists so one copy is wider than the screen.
  const row = Array.from({ length: Math.max(1, Math.ceil(8 / tickers.length)) }, () => tickers).flat();
  const items = (copy: number) => row.map((item, index) => (
    <span key={`${copy}-${index}`} className="flex items-baseline gap-2.5 px-7" aria-hidden={copy === 1 || undefined}>
      <span className="font-semibold">{item.symbol}</span>
      <LiveTickerValues symbol={item.symbol} price={item.price} change={item.change_24h_pct} price24h={item.price_24h ?? null} labels={{ live: d.ticker.live, delayed: d.ticker.delayed }} />
    </span>
  ));
  return (
    <div className="group relative overflow-hidden border-b border-border bg-black/60 text-sm whitespace-nowrap" title={d.ticker.source}>
      <div className="marquee flex w-max py-2.5 group-hover:[animation-play-state:paused]">
        {items(0)}
        {items(1)}
      </div>
      <div className="pointer-events-none absolute inset-y-0 left-0 w-16 bg-gradient-to-r from-bg to-transparent" />
      <div className="pointer-events-none absolute inset-y-0 right-0 w-16 bg-gradient-to-l from-bg to-transparent" />
    </div>
  );
}
