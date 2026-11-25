import { Activity, CandlestickChart } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";
import MarketIcon from "@/components/MarketIcon";
import { getIndicators } from "@/lib/api";
import { bias } from "@/lib/bias";
import { price, utc } from "@/lib/format";
import { market, site } from "@/lib/site";

export const metadata: Metadata = {
  title: "Market analysis",
  description: "Gold, EUR/USD and Bitcoin read from the broker's own candles: four trend factors per market, computed in code.",
};

const TFS = ["15m", "1h", "4h"];
const toneText = { green: "text-green", red: "text-red", neutral: "text-muted" };
const toneBadge = { green: "border-green/40 bg-green/10 text-green", red: "border-red/40 bg-red/10 text-red", neutral: "border-white/15 bg-white/[0.04] text-muted" };
const voteBar = { bull: "bg-green", bear: "bg-red", flat: "bg-white/15" };

// The timeframe is URL data (?tf=1h), read inside Suspense so the page shell stays instant.
async function Board({ searchParams }: { searchParams: Promise<{ tf?: string }> }) {
  const query = await searchParams;
  const tf = TFS.includes(query.tf ?? "") ? (query.tf as string) : "15m";
  const readings = await Promise.all(site.markets.map(async (symbol) => ({ symbol, reading: await getIndicators(symbol, tf) })));
  const read = readings.filter((row) => row.reading !== null).map((row) => ({ ...row, bias: bias(row.reading!) }));
  const count = (label: string) => read.filter((row) => row.bias.label === label).length;
  const latest = Math.max(0, ...read.map((row) => row.reading!.at));

  return (
    <>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex gap-1.5">
          {TFS.map((item) => (
            <Link key={item} href={`/markets?tf=${item}`} className={`rounded-xl border px-4 py-2 text-[15px] ${item === tf ? "border-gold/50 bg-gold/10 font-semibold" : "border-white/10 text-text/75 hover:border-white/25"}`}>{item}</Link>
          ))}
        </div>
        {latest > 0 && <span className="text-sm text-muted">Last closed bar {utc(latest)}</span>}
      </div>

      <section className="mt-6 rounded-3xl border border-gold/30 bg-gradient-to-br from-gold/[0.07] to-transparent p-6">
        <h2 className="flex items-center gap-2.5 text-xl font-bold"><span className="relative flex h-2.5 w-2.5"><span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-green opacity-60" /><span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-green" /></span> Market pulse · {tf}</h2>
        <p className="mt-3 text-[17px] leading-relaxed text-text/85">
          {read.length === 0
            ? "No broker candles stored yet, so there is nothing to read. Readings appear once the MT5 feeder is sending candles."
            : `${count("Bullish")} of ${read.length} markets lean bullish, ${count("Bearish")} bearish and ${count("Mixed")} mixed on the ${tf} chart. ` +
              read.map((row) => `${row.symbol} is ${row.bias.label.toLowerCase()} (${row.bias.agree} of 4 factors)`).join(", ") + "."}
        </p>
        <p className="mt-2 text-xs text-muted">Every word here is filled in from the numbers below by fixed rules. A reading is context, not a signal: only the rules publish plans.</p>
      </section>

      <div className="mt-6 grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {readings.map(({ symbol, reading }) => {
          const b = reading ? bias(reading) : null;
          return (
            <article key={symbol} className="flex flex-col rounded-2xl border border-border bg-surface p-5">
              <div className="flex items-center gap-3">
                <MarketIcon symbol={symbol} size={36} />
                <div className="min-w-0 flex-1">
                  <div className="text-lg font-bold">{symbol}</div>
                  <div className="text-xs text-muted">{market(symbol).name}</div>
                </div>
                {b && <span className={`rounded-lg border px-2.5 py-1 text-xs font-bold tracking-wider uppercase ${toneBadge[b.tone]}`}>{b.label}</span>}
              </div>
              {b && reading ? (
                <>
                  <div className="mt-5 grid grid-cols-4 gap-1.5">{b.factors.map((f) => <span key={f.name} className={`h-1.5 rounded-full ${voteBar[f.vote]}`} title={`${f.name}: ${f.detail}`} />)}</div>
                  <div className={`mt-2 text-sm ${toneText[b.tone]}`}>{b.agree} of 4 factors agree</div>
                  <p className="mt-3 text-[15px] leading-relaxed text-text/80">{b.summary}</p>
                  <ul className="mt-4 space-y-1.5 border-t border-border pt-4 text-sm">
                    {b.factors.map((f) => (
                      <li key={f.name} className="flex items-center justify-between gap-3">
                        <span className="text-muted">{f.name}</span>
                        <span className={f.vote === "bull" ? "text-green" : f.vote === "bear" ? "text-red" : "text-muted"}>{f.detail}</span>
                      </li>
                    ))}
                  </ul>
                  <div className="mt-4 flex items-center justify-between text-sm">
                    <span className="text-muted">EMA200 <b className="num text-text">{reading.ema.ema200 !== undefined ? price(reading.ema.ema200, reading.close) : "—"}</b></span>
                    <span className="text-muted">ATR <b className="num text-text">{reading.atr.percent_of_price?.toFixed(2)}%</b></span>
                  </div>
                </>
              ) : (
                <p className="mt-5 text-sm text-muted">Not enough broker candles for {symbol} on {tf} yet.</p>
              )}
              <Link href={`/app/terminal?symbol=${symbol}&tf=${tf}`} className="mt-5 inline-flex items-center gap-2 text-sm font-semibold text-gold hover:underline"><CandlestickChart size={15} /> Open live chart</Link>
            </article>
          );
        })}
      </div>
    </>
  );
}

export default function MarketsPage({ searchParams }: PageProps<"/markets">) {
  return (
    <div className="py-14">
      <span className="inline-flex items-center gap-2 rounded-full border border-white/12 bg-white/[0.03] px-3.5 py-1.5 text-[11px] font-semibold tracking-[0.2em] text-gold uppercase"><Activity size={13} /> Market analysis</span>
      <h1 className="font-display mt-4 text-4xl font-bold tracking-tight md:text-5xl">Read the markets</h1>
      <p className="mt-4 max-w-2xl text-lg text-muted">
        Each market the desk covers, read from the broker&apos;s own candles: four trend factors, how many agree, and the levels that matter. Computed in code, refreshed every minute.
      </p>
      <div className="mt-8">
        <Suspense fallback={<div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">{Array.from({ length: 3 }).map((_, i) => <div key={i} className="skeleton h-96" />)}</div>}>
          <Board searchParams={searchParams as Promise<{ tf?: string }>} />
        </Suspense>
      </div>
    </div>
  );
}
