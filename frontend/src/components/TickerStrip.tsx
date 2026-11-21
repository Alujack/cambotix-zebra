import type { Ticker } from "@/lib/api";
import { price } from "@/lib/format";

export default function TickerStrip({ tickers }: { tickers: Ticker[] }) {
  if (tickers.length === 0) {
    return (
      <div className="border-b border-line bg-card/60 px-4 py-2 text-center text-xs text-muted">
        Broker prices appear here once the feeder is sending candles.
      </div>
    );
  }
  return (
    <div className="border-b border-line bg-card/60">
      <div className="mx-auto flex max-w-6xl gap-6 overflow-x-auto px-4 py-2 text-sm whitespace-nowrap">
        {tickers.map((item) => {
          const change = item.change_24h_pct;
          const tone = change === null ? "text-muted" : change >= 0 ? "text-win" : "text-loss";
          return (
            <span key={item.symbol} className="flex items-baseline gap-2">
              <span className="font-medium">{item.symbol}</span>
              <span className="tabular-nums">{price(item.price)}</span>
              <span className={`tabular-nums text-xs ${tone}`}>
                {change === null ? "—" : `${change >= 0 ? "+" : ""}${change.toFixed(2)}%`}
              </span>
            </span>
          );
        })}
        <span className="ml-auto text-xs text-muted">broker feed · ~1 min delay</span>
      </div>
    </div>
  );
}
