"use client";

import { useSyncExternalStore } from "react";

// Live broker quotes over one EventSource per tab (/api/stream, passed through from web/api.py /stream).
// Every component that calls the hooks shares the connection; it opens with the first one and closes shortly after
// the last one unmounts. Bars are built from bid prices, like the stored candles the charts load.

export type LiveBar = { t: number; o: number; h: number; l: number; c: number };
export type LiveQuote = { symbol: string; bid: number; ask: number; time_ms: number; bar: LiveBar };
type Quotes = Readonly<{ [symbol: string]: LiveQuote }>;

const KEEP_BARS = 240;          // completed minute bars remembered per symbol, to fill a chart rebuilt after a refresh
const RETRY_MS = 5000;
const CLOSE_GRACE_MS = 2000;    // a page change unmounts and remounts the hooks; keep the stream open across it

let quotes: Quotes = {};
const finished: { [symbol: string]: LiveBar[] } = {};
const listeners = new Set<() => void>();
let source: EventSource | null = null;
let retry: number | undefined;
let closing: number | undefined;

function receive(event: MessageEvent<string>) {
  let quote: LiveQuote;
  try {
    quote = JSON.parse(event.data) as LiveQuote;
  } catch {
    return;
  }
  const previous = quotes[quote.symbol];
  // A reconnect replays the current quote; never step back to an older tick.
  if (previous && previous.time_ms > quote.time_ms) return;
  if (previous && quote.bar.t > previous.bar.t) {
    const list = (finished[quote.symbol] ??= []);
    list.push(previous.bar);
    if (list.length > KEEP_BARS) list.splice(0, list.length - KEEP_BARS);
  }
  quotes = { ...quotes, [quote.symbol]: quote };
  listeners.forEach((listener) => listener());
}

function open() {
  const stream = new EventSource("/api/stream");
  stream.onmessage = receive;
  stream.onerror = () => {
    // EventSource retries a dropped connection by itself; an HTTP error (API down: 503) closes it for good.
    if (stream.readyState !== EventSource.CLOSED || source !== stream) return;
    source = null;
    retry = window.setTimeout(() => {
      retry = undefined;
      if (listeners.size > 0) open();
    }, RETRY_MS);
  };
  source = stream;
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  window.clearTimeout(closing);
  closing = undefined;
  if (!source && retry === undefined) open();
  return () => {
    listeners.delete(listener);
    if (listeners.size > 0) return;
    closing = window.setTimeout(() => {
      if (listeners.size > 0) return;
      source?.close();
      source = null;
      window.clearTimeout(retry);
      retry = undefined;
    }, CLOSE_GRACE_MS);
  };
}

const none = () => () => {};
const empty: Quotes = {};

/** Every symbol's latest quote; re-renders on each tick. */
export function useLiveQuotes(enabled = true): Quotes {
  return useSyncExternalStore(enabled ? subscribe : none, () => (enabled ? quotes : empty), () => empty);
}

/** One symbol's latest quote, or undefined. Without a symbol nothing is opened. */
export function useLiveQuote(symbol?: string): LiveQuote | undefined {
  const all = useLiveQuotes(Boolean(symbol));
  return symbol ? all[symbol] : undefined;
}

/** Minute bars seen live for a symbol, oldest first, ending with the one still forming. Not reactive. */
export function liveBars(symbol: string): LiveBar[] {
  const current = quotes[symbol];
  return [...(finished[symbol] ?? []), ...(current ? [current.bar] : [])];
}

/** 24 h change in percent from the live bid and the close 24 h earlier. */
export const change24h = (bid: number, price24h: number | null | undefined) =>
  price24h ? (bid / price24h - 1) * 100 : null;
