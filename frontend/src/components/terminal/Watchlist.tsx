"use client";

import { BarChart3, CandlestickChart, Eye, LayoutGrid, Trophy } from "lucide-react";
import MarketIcon from "@/components/MarketIcon";
import Link from "next/link";
import { useState } from "react";
import { price } from "@/lib/format";
import { change24h, useLiveQuotes } from "@/lib/live";
import type { MarketCategory } from "@/lib/site";

export type WatchRow = { symbol: string; name: string; category: MarketCategory; price: string | null; change: number | null; price24h: number | null; href: string; active: boolean };
type Labels = { mainList: string; mySignals: string; mySignalsNone: string; search: string; all: string; crypto: string; forex: string; metals: string; watchlist: string; freePlan: string; upgrade: string; deskTitle: string; deskEvery: string; deskNone: string; deskOpen: string; deskLink: string; noQuote: string };

// Left panel of the Terminal: plan badge, search, category tabs, the desk's markets with broker price and 24 h change, desk status.
// Prices and changes follow the live stream; the server's last M1 close shows until the first tick arrives.
export default function Watchlist({ rows: stored, labels, upgradeHref, signalsHref, openHere }: { rows: WatchRow[]; labels: Labels; upgradeHref: string; signalsHref: string; openHere: number }) {
  const quotes = useLiveQuotes();
  const rows = stored.map((row) => {
    const live = quotes[row.symbol];
    return live ? { ...row, price: price(live.bid), change: change24h(live.bid, row.price24h) ?? row.change } : row;
  });
  const [query, setQuery] = useState("");
  const [tab, setTab] = useState<"all" | MarketCategory>("all");
  const tabs = (["all", "crypto", "forex", "metals"] as const).filter((key) => key === "all" || rows.some((row) => row.category === key));
  const shown = rows.filter((row) => (tab === "all" || row.category === tab) && `${row.symbol} ${row.name}`.toLowerCase().includes(query.trim().toLowerCase()));
  return (
    <div className="flex h-full flex-col">
      <div className="flex h-14 flex-none items-center justify-between border-b border-border bg-gradient-to-r from-gold/[0.08] to-transparent px-4">
        <span className="flex items-center gap-2 text-sm font-semibold"><Trophy size={16} className="text-gold" /> {labels.freePlan}</span>
        <Link href={upgradeHref} className="rounded-md bg-gold/15 px-2.5 py-1 text-[11px] font-bold tracking-[0.12em] text-gold uppercase hover:bg-gold/25">{labels.upgrade}</Link>
      </div>
      <div className="px-3 pt-3">
        <div className="flex items-center gap-3 rounded-xl border border-border bg-surface px-3 py-3">
          <LayoutGrid size={18} className="text-gold" />
          <span className="flex-1 font-semibold">{labels.mainList}</span>
          <CandlestickChart size={16} className="text-muted" />
        </div>
        <label className="mt-2.5 flex items-center gap-2 rounded-xl border border-border bg-bg px-3 py-2.5 focus-within:border-muted">
          <BarChart3 size={14} className="text-muted" />
          <input id="terminal-search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder={labels.search} className="w-full bg-transparent text-sm outline-none placeholder:text-muted" />
        </label>
        <div className="mt-3 flex gap-1 border-b border-border pb-3">
          {tabs.map((key) => (
            <button key={key} type="button" onClick={() => setTab(key)} className={`rounded-lg px-3 py-1.5 text-sm ${tab === key ? "border border-border bg-surface text-text" : "text-muted hover:text-text"}`}>{labels[key]}</button>
          ))}
        </div>
      </div>
      <div className="flex items-center justify-between px-4 pt-4 pb-2">
        <span className="label">{labels.watchlist} · {rows.length}</span>
        <span className="label">24h%</span>
      </div>
      <ul className="min-h-0 flex-1 overflow-y-auto">
        {shown.map((row) => (
          <li key={row.symbol}>
            <Link href={row.href} aria-current={row.active ? "true" : undefined} className={`relative flex items-center gap-3 px-4 py-3.5 transition-colors ${row.active ? "bg-surface-2" : "hover:bg-surface"}`}>
              {row.active && <span className="absolute inset-y-0 left-0 w-0.5 bg-gold" aria-hidden />}
              <MarketIcon symbol={row.symbol} size={40} />
              <span className="min-w-0 flex-1">
                <span className="flex items-baseline justify-between gap-2">
                  <span className="text-[15px] font-semibold">{row.symbol}</span>
                  <span className="num text-[15px] font-semibold">{row.price ?? "—"}</span>
                </span>
                <span className="mt-0.5 flex items-baseline justify-between gap-2 text-[13px]">
                  <span className="truncate text-muted">{row.name}</span>
                  <span className={`num font-semibold ${row.change === null ? "text-muted" : row.change >= 0 ? "text-green" : "text-red"}`}>
                    {row.change === null ? (row.price ? "—" : labels.noQuote) : `${row.change >= 0 ? "+" : ""}${row.change.toFixed(2)}%`}
                  </span>
                </span>
                {row.change !== null && (
                  <span className="mt-2 block h-[3px] rounded-full bg-border/60">
                    <span className={`block h-[3px] rounded-full ${row.change >= 0 ? "bg-green" : "bg-red"}`} style={{ width: `${Math.max(6, Math.min(100, (Math.abs(row.change) / 3) * 100))}%` }} />
                  </span>
                )}
              </span>
            </Link>
          </li>
        ))}
      </ul>
      <div className="border-t border-border px-4 pt-3 pb-4">
        <div className="flex items-center justify-between">
          <span className="label flex items-center gap-1.5"><span className="dot bg-green" /> {labels.deskTitle}</span>
          <span className="text-xs text-muted">{labels.deskEvery}</span>
        </div>
        <p className="mt-4 text-center text-sm text-muted">
          {openHere > 0 ? <Link href={signalsHref} className="hover:text-text"><span className="font-semibold text-gold">{openHere}</span> {labels.deskOpen} →</Link> : labels.deskNone}
        </p>
      </div>
      <div className="flex h-10 flex-none items-center justify-between border-t border-border px-4 text-xs">
        <span className="label flex items-center gap-1.5"><Eye size={13} /> {labels.mySignals}</span>
        <span className="text-muted">{labels.mySignalsNone}</span>
      </div>
    </div>
  );
}
