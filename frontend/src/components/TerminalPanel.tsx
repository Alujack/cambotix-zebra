"use client";

import { ChevronDown, ChevronUp, Zap } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import type { NewsItem } from "@/lib/api";
import { r, utc } from "@/lib/format";
import type { Lang } from "@/lib/i18n";

type Labels = { analysis: string; bot: string; history: string; news: string; ready: string; analyze: string; best: string; advanced: string; hint: string; todo: string; noHistory: string; newsEmpty: string };
type Row = { seq: number; direction: "BUY" | "SELL"; status: string; published_at: number; r: number | null; href: string };

// Floating, collapsible panel under the chart: Analysis / Bot / History / News.
export default function TerminalPanel({ symbol, tf, labels, history, news }: { symbol: string; tf: string; lang: Lang; labels: Labels; history: Row[]; news: NewsItem[] }) {
  const [tab, setTab] = useState<"analysis" | "bot" | "history" | "news">("analysis");
  const [open, setOpen] = useState(true);
  const [advanced, setAdvanced] = useState(false);
  const tabs = [["analysis", labels.analysis], ["bot", labels.bot], ["history", labels.history], ["news", labels.news]] as const;
  return (
    <div className="card mt-3 w-full lg:sticky lg:top-16 lg:mt-0">
      <div className="flex items-center justify-between border-b border-border px-3 py-2">
        <div className="flex gap-1">
          {tabs.map(([key, label]) => (
            <button key={key} type="button" onClick={() => setTab(key)} className={`pill ${tab === key ? "pill-active" : ""}`}>{label}</button>
          ))}
        </div>
        <button type="button" onClick={() => setOpen((v) => !v)} className="btn-icon !h-7 !w-7" aria-label={open ? "Collapse" : "Expand"}>{open ? <ChevronDown size={14} /> : <ChevronUp size={14} />}</button>
      </div>
      {open && (
        <div className="p-3 text-sm">
          {tab === "analysis" && (
            <>
              <div className="flex items-center justify-between">
                <span className="font-semibold">{symbol} · {tf}</span>
                <span className="badge border-green/50 bg-green/10 text-green"><span className="dot bg-green" /> {labels.ready}</span>
              </div>
              <div className="mt-3 grid grid-cols-2 gap-2">
                <button type="button" className="btn-secondary" disabled title={labels.todo}>{labels.analyze}</button>
                <button type="button" className="btn-primary" disabled title={labels.todo}><Zap size={14} /> {labels.best}</button>
              </div>
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
