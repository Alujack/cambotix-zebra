"use client";

import { BarChart3, ChevronDown, ChevronUp, Zap } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import type { NewsItem } from "@/lib/api";
import { r, utc } from "@/lib/format";
import type { Lang } from "@/lib/i18n";

type Labels = { analysis: string; bot: string; history: string; news: string; ready: string; analyze: string; best: string; advanced: string; hint: string; todo: string; noHistory: string; newsEmpty: string };
type Row = { seq: number; direction: "BUY" | "SELL"; status: string; published_at: number; r: number | null; href: string };

// Floating, collapsible panel under the chart: Analysis / Bot / History / News.
export default function TerminalPanel({ symbol, tf, labels, history, news, className = "card w-full" }: { symbol: string; tf: string; lang: Lang; labels: Labels; history: Row[]; news: NewsItem[]; className?: string }) {
  const [tab, setTab] = useState<"analysis" | "bot" | "history" | "news">("analysis");
  const [open, setOpen] = useState(true);
  const [advanced, setAdvanced] = useState(false);
  // Scans run on each 15-minute close; the buttons explain that instead of pretending to scan on demand.
  const [note, setNote] = useState(false);
  const tabs = [["analysis", labels.analysis], ["bot", labels.bot], ["history", labels.history], ["news", labels.news]] as const;
  return (
    <div className={className}>
      <div className="flex items-center justify-between border-b border-border px-2 py-2">
        <div className="flex gap-0.5">
          {tabs.map(([key, label]) => (
            <button key={key} type="button" onClick={() => setTab(key)} className={`rounded-lg px-3 py-1.5 text-sm ${tab === key ? "bg-surface-2 font-medium text-text" : "text-muted hover:text-text"}`}>{label}</button>
          ))}
        </div>
        <button type="button" onClick={() => setOpen((v) => !v)} className="grid h-7 w-7 place-items-center text-muted hover:text-text" aria-label={open ? "Collapse" : "Expand"}>{open ? <ChevronDown size={16} /> : <ChevronUp size={16} />}</button>
      </div>
      {open && (
        <div className="p-3 text-sm">
          {tab === "analysis" && (
            <>
              <div className="flex items-center justify-between">
                <span className="text-[15px] font-semibold">{symbol} · {tf}</span>
                <span className="flex items-center gap-1.5 text-xs font-semibold tracking-wide text-green"><span className="dot bg-green" /> {labels.ready}</span>
              </div>
              <div className="mt-3 grid grid-cols-2 gap-2">
                <button type="button" className="btn-secondary !bg-bg" onClick={() => setNote(true)}><BarChart3 size={15} className="text-blue" /> {labels.analyze}</button>
                <button type="button" className="btn-primary" onClick={() => setNote(true)}><Zap size={15} /> {labels.best}</button>
              </div>
              {note && <p className="mt-2 rounded-lg border border-gold/30 bg-gold/[0.06] px-3 py-2 text-xs text-gold">{labels.todo}</p>}
              <button type="button" onClick={() => setAdvanced((v) => !v)} className="mt-3 flex items-center gap-1 text-xs text-muted">{labels.advanced} {advanced ? <ChevronUp size={12} /> : <ChevronDown size={12} />}</button>
              {advanced && <p className="mt-1 text-xs text-muted">TODO(scan): risk level and analysis mode will live here once on-demand scans exist.</p>}
              <div className="mt-3 rounded-lg border border-dashed border-border p-3 text-xs text-muted">{labels.hint}</div>
            </>
          )}
          {tab === "bot" && <p className="text-xs text-muted">{labels.todo}</p>}
          {tab === "history" && (history.length === 0 ? <p className="text-xs text-muted">{labels.noHistory}</p> : (
            <ul className="divide-y divide-border">
              {history.map((row) => (
                <li key={row.seq} className="flex items-center justify-between py-1.5 text-xs">
                  <Link href={row.href} className="flex items-center gap-2">
                    <span className={row.direction === "BUY" ? "text-green" : "text-red"}>{row.direction}</span>
                    <span className="text-muted">#{row.seq} · {utc(row.published_at)}</span>
                  </Link>
                  <span className={row.r === null ? "text-muted" : row.r > 0 ? "text-green" : "text-red"}>{row.status === "open" ? "open" : r(row.r)}</span>
                </li>
              ))}
            </ul>
          ))}
          {tab === "news" && (news.length === 0 ? <p className="text-xs text-muted">{labels.newsEmpty}</p> : (
            <ul className="divide-y divide-border">
              {news.map((item) => (
                <li key={item.time + item.title} className="py-1.5 text-xs">
                  <span className={`badge mr-2 ${item.severity === "HIGH" ? "border-red/50 bg-red/10 text-red" : "border-gold/50 bg-gold/10 text-gold"}`}>{item.severity}</span>
                  {item.title} <span className="text-muted">· {item.country} · {utc(item.time)}</span>
                </li>
              ))}
            </ul>
          ))}
        </div>
      )}
    </div>
  );
}
