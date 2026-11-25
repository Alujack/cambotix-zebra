"use client";

import { useEffect, useState } from "react";
import type { NewsItem } from "@/lib/api";

// How the rules treat a high-impact release (app/news.py, .env defaults): a caution on new plans from 120 min before,
// no new setups from 30 min before until 15 min after. Keep in step with NEWS_CAUTION_MIN / NEWS_WINDOW_*_MIN.
const CAUTION = 120 * 60, BEFORE = 30 * 60, AFTER = 15 * 60;

const span = (seconds: number) => {
  const s = Math.max(0, Math.floor(seconds));
  const d = Math.floor(s / 86400), h = Math.floor((s % 86400) / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60;
  return d > 0 ? `${d}d ${h}h ${m}m` : h > 0 ? `${h}h ${m}m ${sec}s` : `${m}m ${sec}s`;
};
const stamp = (epoch: number, timeZone?: string) =>
  new Date(epoch * 1000).toLocaleString("en-GB", { weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", timeZone });

// Hero card on the calendar: the next high-impact release, a live countdown, and where the desk's rules stand right now.
export default function NextRelease({ event }: { event: NewsItem }) {
  const [now, setNow] = useState<number | null>(null);
  useEffect(() => {
    const tick = () => setNow(Date.now() / 1000);
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, []);

  const t = event.time;
  const stages: [string, number, string][] = [
    ["Caution", t - CAUTION, "New plans carry a news caution"],
    ["Setups blocked", t - BEFORE, "No new setups for the currency"],
    ["Release", t, "The number prints"],
    ["Setups resume", t + AFTER, "Rules scan normally again"],
  ];
  const current = now === null ? -1 : stages.reduce((index, [, at], i) => (now >= at ? i : index), -1);
  const state = now === null ? "" : now < t - CAUTION ? "Watching" : now < t - BEFORE ? "Caution window" : now < t ? "Setups blocked" : now < t + AFTER ? "Just released · setups blocked" : "Setups resumed";

  return (
    <section className="rounded-3xl border border-white/10 bg-surface p-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="label">Next big release</div>
          <h2 className="font-display mt-2 text-3xl font-bold">{event.title}</h2>
          <p className="mt-1.5 text-muted">{event.country} · {now === null ? stamp(t, "UTC") + " UTC" : `${stamp(t)} your time · ${stamp(t, "UTC")} UTC`}</p>
        </div>
        <span className="rounded-xl border border-red/40 bg-red/10 px-4 py-2 font-semibold text-red">High impact</span>
      </div>

      <div className="mt-6 grid gap-3 sm:grid-cols-2">
        <div className="rounded-2xl border border-border bg-bg px-5 py-4 text-center">
          <div className="text-sm text-muted">{now !== null && now >= t ? "Released" : "Starts in"}</div>
          <div className="num mt-1 text-2xl font-bold">{now === null ? "—" : now >= t ? `${span(now - t)} ago` : span(t - now)}</div>
        </div>
        <div className="rounded-2xl border border-border bg-bg px-5 py-4 text-center">
          <div className="text-sm text-muted">Desk status</div>
          <div className={`mt-1 text-2xl font-bold ${state.includes("blocked") ? "text-gold" : state === "Caution window" ? "text-yellow" : "text-green"}`}>{state || "—"}</div>
        </div>
      </div>

      <ol className="mt-4 grid gap-2 sm:grid-cols-4">
        {stages.map(([label, at, text], index) => (
          <li key={label} className={`rounded-2xl border px-4 py-3 ${index === current ? "border-gold/60 bg-gold/[0.08]" : index < current ? "border-border opacity-60" : "border-border"}`}>
            <div className="text-sm font-semibold">{label}</div>
            <div className="num mt-0.5 text-sm text-muted">{now === null ? new Date(at * 1000).toISOString().slice(11, 16) + " UTC" : new Date(at * 1000).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" })}</div>
            <div className="mt-1 text-xs text-muted">{text}</div>
          </li>
        ))}
      </ol>
    </section>
  );
}
