"use client";

import { CandlestickSeries, ColorType, createChart, createSeriesMarkers, createTextWatermark, LineSeries, LineStyle, type IChartApi, type ISeriesApi, type SeriesMarker, type UTCTimestamp } from "lightweight-charts";
import { useEffect, useRef, useState } from "react";
import type { Candle } from "@/lib/api";
import { liveBars, useLiveQuote, type LiveBar } from "@/lib/live";

type Level = { label: string; price: number; tone: "red" | "green" | "white" | "gold"; dashed?: boolean; dotted?: boolean };
type Props = { candles: Candle[]; levels: Level[]; markerTime?: number; markers?: { time: number; direction: "BUY" | "SELL" }[]; direction: "BUY" | "SELL"; decimals: number; watermark?: string; height?: number; fill?: boolean; labels: { ema20: string; ema50: string; ema200: string; rsi: string; setups?: string; trend?: string };
  // ATR Trend Confluence System (web/trend.py): yellow EMA baseline, green/red trailing stop, a label on each flip that passed
  // every filter and a small grey dot on each one that did not. All on closed bars of the chart's own timeframe.
  trend?: { baseline: { t: number; v: number }[]; trail: { t: number; v: number; dir: "up" | "down" }[]; flips: { t: number; direction: "BUY" | "SELL"; passed: boolean }[] };
  // Our own indicator (web/setups.py): a dot on each 15m setup bar and, for a recent one, its entry/SL/TP lines. One toggle shows or hides both.
  setups?: { time: number; direction: "BUY" | "SELL" }[]; setupLevels?: Level[];
  // Follow the broker live: each tick moves the last candle, a tick past it starts the next one. `period` is the bar length in seconds.
  live?: { symbol: string; period: number } };
type Bar = { time: number; open: number; high: number; low: number; close: number };

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

// Fold a live minute bar into the chart's last candle. Buckets are epoch-aligned, like web/indicators.py aggregate().
// A minute inside the last candle's period merges into it; a later one starts a new candle; an older one is ignored.
const foldBar = (series: ISeriesApi<"Candlestick">, last: Bar | null, minute: LiveBar, period: number): Bar | null => {
  if (!last) return last;
  const start = minute.t - (minute.t % period);
  if (start < last.time) return last;
  const next = start === last.time
    ? { time: last.time, open: last.open, high: Math.max(last.high, minute.h), low: Math.min(last.low, minute.l), close: minute.c }
    : { time: start, open: minute.o, high: minute.h, low: minute.l, close: minute.c };
  series.update({ ...next, time: next.time as UTCTimestamp });
  return next;
};

// Candles with the plan's levels drawn on the price axis, a BUY/SELL marker on the signal candle, EMA overlays and an RSI pane.
// `fill` sizes the chart to its parent (the Terminal workspace) instead of a fixed height.
export default function SignalChart({ candles, levels, markerTime, markers = [], direction, decimals, watermark, height = 340, fill = false, labels, live, setups, setupLevels, trend }: Props) {
  const box = useRef<HTMLDivElement>(null);
  // With the trend indicator on the chart its baseline is the EMA50, so the plain EMA lines start hidden to keep the chart readable.
  const [overlays, setOverlays] = useState(() => ({ ema20: !trend, ema50: !trend, ema200: false, rsi: true, setups: true, trend: true }));
  // Visible window measured in bars from the right edge, so a refresh with a new candle keeps the user's zoom and scroll.
  const view = useRef<{ fromEnd: number; toEnd: number } | null>(null);
  const liveSymbol = live?.symbol;
  const period = live?.period ?? 0;
  const quote = useLiveQuote(liveSymbol);
  const series = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const lastBar = useRef<Bar | null>(null);

  useEffect(() => {
    if (!box.current || candles.length === 0) return;
    const css = getComputedStyle(document.documentElement);
    const chart: IChartApi = createChart(box.current, {
      height: fill ? Math.max(200, box.current.clientHeight) : overlays.rsi ? height + 100 : height,
      layout: { background: { type: ColorType.Solid, color: "transparent" }, textColor: css.getPropertyValue("--text-muted").trim() || "#8a8f98", fontFamily: "Inter, system-ui, sans-serif", panes: { separatorColor: css.getPropertyValue("--border").trim() } },
      grid: { vertLines: { color: "rgba(255,255,255,0.04)" }, horzLines: { color: "rgba(255,255,255,0.04)" } },
      rightPriceScale: { borderColor: css.getPropertyValue("--border").trim() },
      timeScale: { borderColor: css.getPropertyValue("--border").trim(), timeVisible: true, secondsVisible: false },
      crosshair: { mode: 0 },
      localization: { priceFormatter: (p: number) => p.toFixed(decimals) },
    });
    const candleSeries = chart.addSeries(CandlestickSeries, { upColor: "#34f08d", downColor: "#ff6b7a", borderVisible: false, wickUpColor: "#34f08d", wickDownColor: "#ff6b7a" });
    const data = candles.map((c) => ({ time: c.t as UTCTimestamp, open: c.o, high: c.h, low: c.l, close: c.c }));
    candleSeries.setData(data);
    const tail = candles[candles.length - 1];
    lastBar.current = { time: tail.t, open: tail.o, high: tail.h, low: tail.l, close: tail.c };
    // A rebuilt chart (refresh, new overlay) replays the minutes already seen live, so the live candles stay.
    if (liveSymbol && period > 0) for (const minute of liveBars(liveSymbol)) lastBar.current = foldBar(candleSeries, lastBar.current, minute, period);
    series.current = candleSeries;
    for (const level of [...levels, ...(overlays.setups && setupLevels ? setupLevels : [])]) {
      candleSeries.createPriceLine({ price: level.price, color: colour(level.tone), lineWidth: 1, lineStyle: level.dashed ? LineStyle.Dashed : level.dotted ? LineStyle.Dotted : LineStyle.Solid, axisLabelVisible: true, title: level.label });
    }
    const flags = markerTime ? [{ time: markerTime, direction }, ...markers] : markers;
    const barFor = (time: number) => candles.reduce((best, c) => (c.t <= time && c.t > best ? c.t : best), candles[0].t);
    const planMarks: SeriesMarker<UTCTimestamp>[] = flags
      .filter((flag) => flag.time >= candles[0].t)
      .map((flag) => ({ time: barFor(flag.time) as UTCTimestamp, position: flag.direction === "BUY" ? "belowBar" : "aboveBar", color: flag.direction === "BUY" ? "#34f08d" : "#ff6b7a", shape: flag.direction === "BUY" ? "arrowUp" : "arrowDown", text: flag.direction }));
    // Indicator setups are dots, so they never read as a published plan's arrow.
    const setupMarks: SeriesMarker<UTCTimestamp>[] = (overlays.setups && setups ? setups : [])
      .filter((flag) => flag.time >= candles[0].t)
      .map((flag) => ({ time: barFor(flag.time) as UTCTimestamp, position: flag.direction === "BUY" ? "belowBar" : "aboveBar", color: flag.direction === "BUY" ? "#a3f7c9" : "#ffb3bb", shape: "circle", text: `Z ${flag.direction}` }));
    const trendMarks: SeriesMarker<UTCTimestamp>[] = (overlays.trend && trend ? trend.flips : [])
      .filter((flip) => flip.t >= candles[0].t)
      .map((flip) => flip.passed
        ? { time: barFor(flip.t) as UTCTimestamp, position: flip.direction === "BUY" ? "belowBar" : "aboveBar", color: flip.direction === "BUY" ? "#34f08d" : "#ff6b7a", shape: "square", text: `ATR ${flip.direction}` }
        : { time: barFor(flip.t) as UTCTimestamp, position: flip.direction === "BUY" ? "belowBar" : "aboveBar", color: "#8a8f98", shape: "circle", size: 0.6 });
    const marks = [...planMarks, ...setupMarks, ...trendMarks].sort((a, b) => a.time - b.time);
    if (overlays.trend && trend) {
      const from = candles[0].t;
      const style = { lineWidth: 2, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false } as const;
      chart.addSeries(LineSeries, { ...style, color: "#facc15" }).setData(trend.baseline.filter((p) => p.t >= from).map((p) => ({ time: p.t as UTCTimestamp, value: p.v })));
      // One line, green under an uptrend and red over a downtrend. A point's colour paints the segment that starts at it, so the
      // last point before a flip is transparent: the stop breaks there instead of drawing a jump from one side of price to the other.
      const trail = trend.trail.filter((p) => p.t >= from);
      chart.addSeries(LineSeries, { ...style, color: "#34f08d" }).setData(trail.map((p, i) => ({
        time: p.t as UTCTimestamp, value: p.v,
        color: i + 1 < trail.length && trail[i + 1].dir !== p.dir ? "transparent" : p.dir === "up" ? "#34f08d" : "#ff6b7a",
      })));
    }
    if (marks.length) createSeriesMarkers(candleSeries, marks);
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
    const resize = () => chart.applyOptions(fill && box.current ? { width: box.current.clientWidth, height: Math.max(200, box.current.clientHeight) } : { width: box.current?.clientWidth ?? 600 });
    resize();
    const observer = new ResizeObserver(resize);
    observer.observe(box.current);
    const last = candles.length - 1;
    if (view.current) chart.timeScale().setVisibleLogicalRange({ from: last - view.current.fromEnd, to: last - view.current.toEnd });
    else chart.timeScale().fitContent();
    window.addEventListener("resize", resize);
    return () => {
      const range = chart.timeScale().getVisibleLogicalRange();
      if (range) view.current = { fromEnd: last - range.from, toEnd: last - range.to };
      window.removeEventListener("resize", resize);
      observer.disconnect();
      series.current = null;
      chart.remove();
    };
  }, [candles, levels, markerTime, markers, direction, decimals, overlays, watermark, height, fill, liveSymbol, period, setups, setupLevels, trend]);

  // Each tick: move the last candle in place. The EMA and RSI lines follow on the next data refresh.
  useEffect(() => {
    if (quote && series.current && period > 0) lastBar.current = foldBar(series.current, lastBar.current, quote.bar, period);
  }, [quote, period]);

  const toggle = (key: keyof typeof overlays) => setOverlays((value) => ({ ...value, [key]: !value[key] }));
  const keys = [...(trend && labels.trend ? (["trend"] as const) : []), ...(setups && labels.setups ? (["setups"] as const) : []), ...(["ema20", "ema50", "ema200", "rsi"] as const)];
  return (
    <div className={fill ? "flex h-full flex-col" : ""}>
      <div className={`flex flex-wrap gap-1.5 ${fill ? "px-3 pt-2 pb-1" : "mb-2"}`}>
        {keys.map((key) => (
          <button key={key} type="button" onClick={() => toggle(key)} className={`pill ${overlays[key] ? "pill-active" : ""}`} aria-pressed={overlays[key]}>
            {labels[key]}
          </button>
        ))}
      </div>
      <div ref={box} className={fill ? "min-h-0 w-full flex-1 overflow-hidden" : "w-full"} />
    </div>
  );
}
