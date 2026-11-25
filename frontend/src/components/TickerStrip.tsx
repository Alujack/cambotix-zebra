import type { Ticker } from "@/lib/api";
import { price } from "@/lib/format";
import { t, type Lang } from "@/lib/i18n";

// Endless marquee of the broker's last prices. The list is rendered twice and slid by half its width, so it loops seamlessly.
// Pauses on hover; stands still under prefers-reduced-motion (see .marquee in globals.css).
export default function TickerStrip({ tickers, lang }: { tickers: Ticker[]; lang: Lang }) {
  const d = t(lang);
  if (tickers.length === 0) {
    return <div className="border-b border-border bg-black/60 px-4 py-2.5 text-center text-xs text-muted">{d.ticker.empty}</div>;
  }
  // Repeat short lists so one copy is wider than the screen.
  const row = Array.from({ length: Math.max(1, Math.ceil(8 / tickers.length)) }, () => tickers).flat();
  const items = (copy: number) => row.map((item, index) => {
    const change = item.change_24h_pct;
    const tone = change === null ? "text-muted" : change >= 0 ? "text-green" : "text-red";
    return (
      <span key={`${copy}-${index}`} className="flex items-baseline gap-2.5 px-7" aria-hidden={copy === 1 || undefined}>
        <span className="font-semibold">{item.symbol}</span>
        <span className="num text-text/90">{price(item.price)}</span>
        <span className={`num ${tone}`}>{change === null ? "—" : `${change >= 0 ? "+" : ""}${change.toFixed(2)}%`}</span>
        <span className="rounded bg-surface-2 px-1.5 py-0.5 text-[10px] text-muted">~1 min</span>
      </span>
    );
  });
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
