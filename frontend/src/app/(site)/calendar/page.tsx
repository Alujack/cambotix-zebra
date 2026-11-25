import { CalendarClock, ShieldAlert } from "lucide-react";
import type { Metadata } from "next";
import { Suspense } from "react";
import NextRelease from "@/components/NextRelease";
import { Until } from "@/components/terminal/Clocks";
import { getNews, getRecord, type NewsItem } from "@/lib/api";

export const metadata: Metadata = {
  title: "Economic calendar",
  description: "High- and medium-impact releases for the next seven days, and which ones block new setups.",
};

const day = (epoch: number) => new Date(epoch * 1000).toLocaleDateString("en-GB", { weekday: "long", day: "numeric", month: "long", timeZone: "UTC" });
const clock = (epoch: number) => new Date(epoch * 1000).toISOString().slice(11, 16);

// The same calendar the rules use (web/api.py /news): high and medium impact only, nothing invented.
async function Events() {
  const [items, record] = await Promise.all([getNews(), getRecord()]);
  // Server components may not read the clock (react-hooks/purity); the API stamps every answer with its own time.
  const now = record.generated_at ? Date.parse(record.generated_at) / 1000 : 0;
  if (items.length === 0) {
    return <p className="rounded-2xl border border-border bg-surface p-8 text-center text-muted">The calendar is empty right now. Events appear here as soon as the feed has them.</p>;
  }
  // The API already sorts by time; the first high-impact event still ahead is the hero.
  const next = items.find((item) => item.severity === "HIGH" && item.time > now - 15 * 60);
  const groups = new Map<string, NewsItem[]>();
  for (const item of items) groups.set(day(item.time), [...(groups.get(day(item.time)) ?? []), item]);
  return (
    <div className="space-y-8">
      {next && <NextRelease event={next} />}
      {[...groups].map(([label, rows]) => (
        <section key={label}>
          <h2 className="mb-3 text-sm font-semibold tracking-[0.14em] text-muted uppercase">{label}</h2>
          <ul className="divide-y divide-border overflow-hidden rounded-2xl border border-border bg-surface">
            {rows.map((item) => (
              <li key={item.time + item.title} className="flex flex-wrap items-center gap-x-4 gap-y-2 px-4 py-3.5 sm:flex-nowrap">
                <span className="num w-14 flex-none text-[15px] font-semibold">{clock(item.time)}</span>
                <span className="w-12 flex-none rounded-md bg-surface-2 px-2 py-0.5 text-center text-xs font-bold text-muted">{item.country}</span>
                <span className="min-w-0 flex-1 font-medium">{item.title}</span>
                <span className="flex flex-none items-center gap-2">
                  {item.blocks_setups && <span className="flex items-center gap-1 rounded-full border border-gold/40 bg-gold/10 px-2.5 py-1 text-xs font-semibold text-gold"><ShieldAlert size={13} /> Blocks setups</span>}
                  <span className={`rounded-full px-2.5 py-1 text-xs font-bold ${item.severity === "HIGH" ? "bg-red/15 text-red" : "bg-yellow/15 text-yellow"}`}>{item.severity === "HIGH" ? "High" : "Medium"}</span>
                  <span className="w-16 text-right text-xs text-muted"><Until at={item.time} /></span>
                </span>
              </li>
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}

export default function CalendarPage() {
  return (
    <div className="mx-auto max-w-4xl py-14">
      <span className="inline-flex items-center gap-2 rounded-full border border-white/12 bg-white/[0.03] px-3.5 py-1.5 text-[11px] font-semibold tracking-[0.2em] text-gold uppercase"><CalendarClock size={13} /> Market news</span>
      <h1 className="font-display mt-4 text-4xl font-bold tracking-tight">Economic calendar</h1>
      <p className="mt-4 max-w-2xl text-muted">
        High- and medium-impact releases for the next seven days, in UTC. The rules use this same calendar: a high-impact release for a watched currency blocks new setups in the window around it.
      </p>
      <div className="mt-10">
        <Suspense fallback={<div className="space-y-3">{Array.from({ length: 5 }).map((_, i) => <div key={i} className="skeleton h-14" />)}</div>}>
          <Events />
        </Suspense>
      </div>
    </div>
  );
}
