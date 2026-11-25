"use client";

import { memo, useEffect, useRef } from "react";
import { tvSymbol } from "@/lib/site";

// TradingView's free "Ticker Tape" embed: a live scrolling price strip from their data vendors.
// Used only when the broker feed has no candles, so the site never shows an empty strip. These are the vendor's
// prices, not the broker's; plans are always graded on broker candles.
const symbols = ["XAUUSD", "EURUSD", "GBPUSD", "BTCUSD", "XAGUSD", "USDJPY", "ETHUSD"];
const extra: { [symbol: string]: string } = { XAGUSD: "OANDA:XAGUSD", USDJPY: "FX:USDJPY", ETHUSD: "BITSTAMP:ETHUSD" };

function TickerTape() {
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const host = box.current;
    if (!host) return;
    host.innerHTML = '<div class="tradingview-widget-container__widget"></div>';
    const script = document.createElement("script");
    script.src = "https://s3.tradingview.com/external-embedding/embed-widget-ticker-tape.js";
    script.type = "text/javascript";
    script.async = true;
    script.innerHTML = JSON.stringify({
      symbols: symbols.map((symbol) => ({ proName: extra[symbol] ?? tvSymbol(symbol), title: symbol })),
      showSymbolLogo: true,
      isTransparent: false,
      displayMode: "adaptive",
      colorTheme: "dark",
      locale: "en",
    });
    host.appendChild(script);
    return () => { host.innerHTML = ""; };
  }, []);
  // Fixed height so the page does not jump while the script loads.
  return (
    <div className="h-[46px] overflow-hidden border-b border-border bg-black/60">
      <div ref={box} className="tradingview-widget-container" />
    </div>
  );
}

export default memo(TickerTape);
