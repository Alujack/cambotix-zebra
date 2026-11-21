"use client";

import { CandlestickSeries, ColorType, createChart, createSeriesMarkers, createTextWatermark, LineSeries, LineStyle, type IChartApi, type SeriesMarker, type UTCTimestamp } from "lightweight-charts";
import { useEffect, useRef, useState } from "react";
import type { Candle } from "@/lib/api";

type Level = { label: string; price: number; tone: "red" | "green" | "white" | "gold"; dashed?: boolean; dotted?: boolean };
type Props = { candles: Candle[]; levels: Level[]; markerTime?: number; markers?: { time: number; direction: "BUY" | "SELL" }[]; direction: "BUY" | "SELL"; decimals: number; watermark?: string; height?: number; labels: { ema20: string; ema50: string; ema200: string; rsi: string } };

const ema = (values: number[], length: number) => {
  const k = 2 / (length + 1);
  return values.map((v, i, arr) => (i === 0 ? v : arr[i - 1] = (arr[i - 1] as number) + k * (v - (arr[i - 1] as number))));
};
const rsi = (closes: number[], length = 14) => {
  let gain = 0, loss = 0;
  return closes.map((c, i) => {
    if (i === 0) return 50;
    const change = c - closes[i - 1];
    gain = gain + (Math.max(change, 0) - gain) / length;
    loss = loss + (Math.max(-change, 0) - loss) / length;
    return loss === 0 ? 100 : 100 - 100 / (1 + gain / loss);
  });
};
const colour = (tone: Level["tone"]) => ({ red: "#ff6b7a", green: "#34f08d", white: "#f5f7fa", gold: "#e8c964" })[tone];

// Candles with the plan's levels drawn on the price axis, a BUY/SELL marker on the signal candle, EMA overlays and an RSI pane.
export default function SignalChart({ candles, levels, markerTime, markers = [], direction, decimals, watermark, height = 340, labels }: Props) {
  const box = useRef<HTMLDivElement>(null);
  const [overlays, setOverlays] = useState({ ema20: true, ema50: true, ema200: false, rsi: true });
  // Visible window measured in bars from the right edge, so a refresh with a new candle keeps the user's zoom and scroll.
  const view = useRef<{ fromEnd: number; toEnd: number } | null>(null);

  useEffect(() => {
    if (!box.current || candles.length === 0) return;
    const css = getComputedStyle(document.documentElement);
    const chart: IChartApi = createChart(box.current, {
      height: overlays.rsi ? height + 100 : height,
      layout: { background: { type: ColorType.Solid, color: "transparent" }, textColor: css.getPropertyValue("--text-muted").trim() || "#8a8f98", fontFamily: "Inter, system-ui, sans-serif", panes: { separatorColor: css.getPropertyValue("--border").trim() } },
      grid: { vertLines: { color: "rgba(255,255,255,0.04)" }, horzLines: { color: "rgba(255,255,255,0.04)" } },
      rightPriceScale: { borderColor: css.getPropertyValue("--border").trim() },
      timeScale: { borderColor: css.getPropertyValue("--border").trim(), timeVisible: true, secondsVisible: false },
      crosshair: { mode: 0 },
      localization: { priceFormatter: (p: number) => p.toFixed(decimals) },
    });
    const series = chart.addSeries(CandlestickSeries, { upColor: "#34f08d", downColor: "#ff6b7a", borderVisible: false, wickUpColor: "#34f08d", wickDownColor: "#ff6b7a" });
    const data = candles.map((c) => ({ time: c.t as UTCTimestamp, open: c.o, high: c.h, low: c.l, close: c.c }));
    series.setData(data);
    for (const level of levels) {
      series.createPriceLine({ price: level.price, color: colour(level.tone), lineWidth: 1, lineStyle: level.dashed ? LineStyle.Dashed : level.dotted ? LineStyle.Dotted : LineStyle.Solid, axisLabelVisible: true, title: level.label });
    }
    const flags = markerTime ? [{ time: markerTime, direction }, ...markers] : markers;
    const barFor = (time: number) => candles.reduce((best, c) => (c.t <= time && c.t > best ? c.t : best), candles[0].t);
    const marks: SeriesMarker<UTCTimestamp>[] = flags
      .filter((flag) => flag.time >= candles[0].t)
      .map((flag) => ({ time: barFor(flag.time) as UTCTimestamp, position: flag.direction === "BUY" ? "belowBar" : "aboveBar", color: flag.direction === "BUY" ? "#34f08d" : "#ff6b7a", shape: flag.direction === "BUY" ? "arrowUp" : "arrowDown", text: flag.direction }));
    if (marks.length) createSeriesMarkers(series, marks);
    if (watermark) createTextWatermark(chart.panes()[0], { horzAlign: "center", vertAlign: "center", lines: [{ text: watermark, color: "rgba(232,201,100,0.08)", fontSize: 48, fontStyle: "bold" }] });
    const closes = candles.map((c) => c.c);
    const line = (length: number, color: string) => {
      const values = ema([...closes], length);
      chart.addSeries(LineSeries, { color, lineWidth: 1, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false }).setData(candles.map((c, i) => ({ time: c.t as UTCTimestamp, value: values[i] })));
    };
    if (overlays.ema20) line(20, "#e8c964");
    if (overlays.ema50) line(50, "#5ab0ff");
    if (overlays.ema200) line(200, "#f5f7fa");
    if (overlays.rsi) {
      const values = rsi(closes);
      const pane = chart.addSeries(LineSeries, { color: "#e8c964", lineWidth: 1, priceLineVisible: false, lastValueVisible: true, priceFormat: { type: "price", precision: 0, minMove: 1 } }, 1);
      pane.setData(candles.map((c, i) => ({ time: c.t as UTCTimestamp, value: values[i] })));
      pane.createPriceLine({ price: 70, color: "rgba(255,107,122,0.6)", lineWidth: 1, lineStyle: LineStyle.Dotted, axisLabelVisible: false, title: "" });
      pane.createPriceLine({ price: 30, color: "rgba(52,240,141,0.6)", lineWidth: 1, lineStyle: LineStyle.Dotted, axisLabelVisible: false, title: "" });
      chart.panes()[1]?.setHeight(100);
    }
    const resize = () => chart.applyOptions({ width: box.current?.clientWidth ?? 600 });
    resize();
    const last = candles.length - 1;
    if (view.current) chart.timeScale().setVisibleLogicalRange({ from: last - view.current.fromEnd, to: last - view.current.toEnd });
    else chart.timeScale().fitContent();
    window.addEventListener("resize", resize);
    return () => {
      const range = chart.timeScale().getVisibleLogicalRange();
      if (range) view.current = { fromEnd: last - range.from, toEnd: last - range.to };
      window.removeEventListener("resize", resize);
      chart.remove();
    };
  }, [candles, levels, markerTime, markers, direction, decimals, overlays, watermark, height]);

  const toggle = (key: keyof typeof overlays) => setOverlays((value) => ({ ...value, [key]: !value[key] }));
  return (
    <div>
      <div className="mb-2 flex flex-wrap gap-1.5">
        {(["ema20", "ema50", "ema200", "rsi"] as const).map((key) => (
          <button key={key} type="button" onClick={() => toggle(key)} className={`pill ${overlays[key] ? "pill-active" : ""}`} aria-pressed={overlays[key]}>
            {labels[key]}
          </button>
        ))}
      </div>
      <div ref={box} className="w-full" />
    </div>
  );
}
