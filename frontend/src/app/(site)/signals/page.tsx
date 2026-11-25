import { ShieldAlert, Signal } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";
import MarketIcon from "@/components/MarketIcon";
import SignalCard from "@/components/SignalCard";
import { getRecord, getSignals, getTickers } from "@/lib/api";
import { percent } from "@/lib/format";
import { t, type Lang } from "@/lib/i18n";
import { market, site } from "@/lib/site";

export const metadata: Metadata = {
  title: "Signals",
  description: "Every plan the rules published, open and closed, with its graded result. Nothing is removed.",
};

// Public signal feed: the same cards as the dashboard, filtered by market with ?market=XAUUSD.
// The filter is URL data, so it is read inside the Suspense boundary below (keeps the page shell instant).
async function Feed({ searchParams }: { searchParams: Promise<{ market?: string }> }) {
  const lang: Lang = "en";
  const d = t(lang);
  const query = await searchParams;
  const pick = site.markets.includes((query.market ?? "").toUpperCase()) ? (query.market as string).toUpperCase() : null;
  const [plans, tickers, record] = await Promise.all([getSignals(120), getTickers(), getRecord()]);
  const shown = pick ? plans.filter((plan) => plan.symbol === pick) : plans;
  const open = shown.filter((plan) => plan.status === "open");
  const done = shown.filter((plan) => plan.status !== "open");
  const quote = (symbol: string) => tickers.find((item) => item.symbol === symbol);
  const h = record.headline;

  return (
    <>
      <div className="flex flex-wrap gap-2.5">
        <Link href="/signals" className={`rounded-2xl border px-5 py-2.5 text-[15px] transition-colors ${pick === null ? "border-gold/50 bg-gold/10 text-text" : "border-white/10 text-text/80 hover:border-white/25"}`}>All signals</Link>
        {site.markets.map((symbol) => (
          <Link key={symbol} href={`/signals?market=${symbol}`} className={`flex items-center gap-2.5 rounded-2xl border px-4 py-2 text-[15px] transition-colors ${pick === symbol ? "border-gold/50 bg-gold/10 text-text" : "border-white/10 text-text/80 hover:border-white/25"}`}>
            <MarketIcon symbol={symbol} size={24} /> {market(symbol).name} signals
          </Link>
        ))}
      </div>

      <div className="mt-6 grid grid-cols-2 gap-3 md:grid-cols-4">
        {[["Open now", String(record.open)], ["Closed", String(h.closed)], ["Win rate (TP1)", percent(h.win_rate)], ["Never filled", String(record.not_filled)]].map(([label, value]) => (
          <div key={label} className="rounded-2xl border border-border bg-surface px-5 py-4">
            <div className="label">{label}</div>
            <div className="num mt-1.5 text-2xl font-bold">{value}</div>
          </div>
        ))}
      </div>

      {shown.length === 0 ? (
        <p className="mt-8 rounded-2xl border border-dashed border-border p-10 text-center text-muted">
          {pick ? `No ${market(pick).name} plan has been published yet.` : d.signals.empty}
        </p>
      ) : (
        <>
          {open.length > 0 && (
            <section className="mt-10">
              <h2 className="mb-4 flex items-center gap-2 text-sm font-semibold tracking-[0.14em] text-muted uppercase"><span className="dot bg-gold" /> Open · {open.length}</h2>
              <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">{open.map((plan) => <SignalCard key={plan.event_id} plan={plan} lang={lang} ticker={quote(plan.symbol)} />)}</div>
            </section>
          )}
          {done.length > 0 && (
            <section className="mt-10">
              <h2 className="mb-4 text-sm font-semibold tracking-[0.14em] text-muted uppercase">Graded · newest first · {done.length}</h2>
              <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">{done.map((plan) => <SignalCard key={plan.event_id} plan={plan} lang={lang} />)}</div>
            </section>
          )}
        </>
      )}
    </>
  );
}

export default function SignalsPage({ searchParams }: PageProps<"/signals">) {
  return (
    <div className="py-14">
      <span className="inline-flex items-center gap-2 rounded-full border border-white/12 bg-white/[0.03] px-3.5 py-1.5 text-[11px] font-semibold tracking-[0.2em] text-gold uppercase"><Signal size={13} /> Latest signals</span>
      <h1 className="font-display mt-4 text-4xl font-bold tracking-tight md:text-5xl">Signals</h1>
      <p className="mt-4 max-w-2xl text-lg text-muted">
        Every plan the rules published, newest first. Open plans send their entry, stop and targets live on Telegram; they show here once the plan closes, next to what happened.
      </p>
      <div className="mt-6 flex items-start gap-3 rounded-2xl border border-gold/25 bg-gold/[0.05] px-5 py-3.5 text-sm text-gold">
        <ShieldAlert size={18} className="mt-0.5 flex-none" />
        <span>Signals are published analysis for education. Not financial advice. Trading leveraged products can lose you money.</span>
      </div>
      <div className="mt-8">
        <Suspense fallback={<div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">{Array.from({ length: 6 }).map((_, i) => <div key={i} className="skeleton h-72" />)}</div>}>
          <Feed searchParams={searchParams as Promise<{ market?: string }>} />
        </Suspense>
      </div>
    </div>
  );
}
