"use client";

import { memo, useEffect, useRef } from "react";
import { tvInterval, tvSymbol } from "@/lib/site";

// TradingView's free "Advanced Real-Time Chart" embed: their price feed, tick by tick, with their drawing tools.
// Display only. Its price is the data vendor's, not the broker's, so plan levels and grading stay on SignalChart.
// The script reads its JSON config from its own text, so the widget is rebuilt only when symbol, timeframe or language change.
function TradingViewWidget({ symbol, tf, locale, height = 520 }: { symbol: string; tf: string; locale: string; height?: number | string }) {
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const host = box.current;
    if (!host) return;
    host.innerHTML = '<div class="tradingview-widget-container__widget" style="height:100%;width:100%"></div>';
    const script = document.createElement("script");
    script.src = "https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js";
    script.type = "text/javascript";
    script.async = true;
    script.innerHTML = JSON.stringify({
      autosize: true,
      symbol: tvSymbol(symbol),
      interval: tvInterval(tf),
      timezone: "Etc/UTC",
      theme: "dark",
      style: "1",
      locale,
      backgroundColor: "#060707",
      gridColor: "rgba(36, 38, 45, 0.6)",
      withdateranges: true,
      hide_side_toolbar: false,
      allow_symbol_change: false,
      save_image: true,
      calendar: false,
      support_host: "https://www.tradingview.com",
    });
    host.appendChild(script);
    return () => { host.innerHTML = ""; };
  }, [symbol, tf, locale]);
  // The embed script rewrites its container's style to 100% x 100%, so the height lives on a wrapper it never touches.
  return (
    <div className="w-full overflow-hidden" style={{ height }}>
      <div ref={box} className="tradingview-widget-container" style={{ height: "100%", width: "100%" }} />
    </div>
  );
}

export default memo(TradingViewWidget);
