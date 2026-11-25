import { ChevronDown, ShieldAlert, ShieldCheck, Trophy } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";
import MarketIcon from "@/components/MarketIcon";
import StatTile from "@/components/StatTile";
import { getRecord, getSignals, type Summary } from "@/lib/api";
import { modelName, percent, price, r, utc } from "@/lib/format";
import { href, t, type Dict, type Lang } from "@/lib/i18n";

export const metadata: Metadata = { title: "Track record", description: "The complete graded record: every plan, every outcome, verifiable hash chain." };

function Breakdown({ title, rows, labels, d }: { title: string; rows: { [name: string]: Summary }; labels?: { [key: string]: string }; d: Dict }) {
  const entries = Object.entries(rows);
  return (
    <div className="overflow-x-auto rounded-2xl border border-border bg-surface">
      <table className="w-full text-sm">
        <thead className="text-xs uppercase tracking-wide text-muted">
          <tr><th className="px-3 py-2 text-left">{title}</th><th className="px-3 py-2 text-right">{d.record.closed}</th><th className="px-3 py-2 text-right">{d.record.wins}</th><th className="px-3 py-2 text-right">{d.record.winRate}</th><th className="px-3 py-2 text-right">{d.record.totalR}</th><th className="px-3 py-2 text-right">{d.record.scaleOutR}</th></tr>
        </thead>
        <tbody>
          {entries.length === 0 && <tr><td colSpan={6} className="px-3 py-3 text-muted">{d.record.noClosed}</td></tr>}
          {entries.map(([name, s]) => (
            <tr key={name} className="border-t border-line">
              <td className="px-3 py-2">{labels?.[name] ?? name}</td>
              <td className="px-3 py-2 text-right">{s.closed}</td>
              <td className="px-3 py-2 text-right">{s.wins}</td>
              <td className="px-3 py-2 text-right">{percent(s.win_rate)}</td>
              <td className={`px-3 py-2 text-right ${s.total_r_tp1 > 0 ? "text-win" : s.total_r_tp1 < 0 ? "text-loss" : ""}`}>{r(s.total_r_tp1)}</td>
              <td className="px-3 py-2 text-right">{r(s.total_r_scaled)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

async function Record({ lang }: { lang: Lang }) {
  const d = t(lang);
  const [record, plans] = await Promise.all([getRecord(), getSignals(200)]);
  const h = record.headline;
  // Newest first, losses included: the list is never filtered by outcome.
  const latest = plans.filter((plan) => plan.status === "closed").slice(0, 5);
  const verdictTone = h.verdict === "GO" ? "win" : h.verdict === "NO-GO" ? "loss" : "muted";
  return (
    <>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <StatTile label={d.record.closed} value={String(h.closed)} hint={`${record.open} ${d.tiles.open} · ${record.not_filled} ${d.tiles.neverFilled}`} />
        <StatTile label={d.tiles.winRate} value={percent(h.win_rate)} hint={`${h.wins} ${d.tiles.wins}`} />
        <StatTile label={`${d.tiles.total} (TP1)`} value={r(h.total_r_tp1)} hint={`${d.tiles.scaleOut} ${r(h.total_r_scaled)}`} tone={h.total_r_tp1 > 0 ? "win" : h.total_r_tp1 < 0 ? "loss" : undefined} />
        <StatTile label={d.tiles.expectancy} value={r(h.expectancy_r, 3)} hint={`${d.tiles.profitFactor} ${h.profit_factor ?? "n/a"}`} />
        <StatTile label={d.tiles.drawdown} value={`${h.max_drawdown_r.toFixed(2)}R`} hint={`${d.tiles.limit} ${h.max_drawdown_limit_r}R`} />
        <StatTile label={d.tiles.ambiguous} value={String(h.ambiguous)} hint={d.tiles.ambiguousHint} />
        <StatTile label={d.tiles.verdict} value={d.verdict[h.verdict] ?? h.verdict} hint={`${h.min_trades} ${d.tiles.verdictHint}`} tone={verdictTone} />
        <StatTile label={d.tiles.chain} value={record.chain.valid ? d.tiles.chainValid : d.tiles.broken} hint={record.chain.valid ? `${record.chain.rows} ${d.tiles.rows} · ${d.tiles.head} #${record.chain.head_seq}` : `${d.tiles.chainBroken} ${record.chain.broken_at}`} tone={record.chain.valid ? "win" : "loss"} />
      </div>
      {record.basis && <p className="mt-4 text-sm text-muted">{record.basis}</p>}

      <section className="mt-10 overflow-hidden rounded-3xl border border-border bg-surface">
        <h2 className="px-6 pt-5 pb-4 text-lg font-semibold">Latest closed trades <span className="font-normal text-muted">(the newest 5 · wins and losses as they came)</span></h2>
        {latest.length === 0 ? <p className="border-t border-border px-6 py-5 text-sm text-muted">{d.record.noClosed}</p> : (
          <ul>
            {latest.map((plan) => {
              const won = (plan.result?.r_tp1 ?? 0) > 0;
              const exit = d.exits[plan.result?.exit ?? ""] ?? plan.result?.exit ?? "Closed";
              return (
                <li key={plan.event_id} className="border-t border-border">
                  <Link href={href(lang, `/app/signals/${plan.seq}`)} className="flex flex-wrap items-center gap-x-4 gap-y-2 px-6 py-3.5 hover:bg-white/[0.02]">
                    <MarketIcon symbol={plan.symbol} size={34} />
                    <span className="font-semibold">{plan.symbol}</span>
                    <span className={`font-bold ${plan.direction === "BUY" ? "text-green" : "text-red"}`}>{plan.direction}</span>
                    <span className="text-muted">{plan.timeframe}</span>
                    <span className="ml-auto flex items-center gap-3">
                      <span className={`rounded-md px-2.5 py-1 text-sm font-semibold ${won ? "bg-green/10 text-green" : "bg-red/10 text-red"}`}>{exit} · {r(plan.result?.r_tp1)}</span>
                      <span className="w-24 text-right text-sm text-muted">{utc(plan.published_at, false)}</span>
                    </span>
                  </Link>
                </li>
              );
            })}
          </ul>
        )}
      </section>

      <div className="mt-10 grid gap-6 lg:grid-cols-2">
        <Breakdown title={d.record.month} rows={record.by_month} d={d} />
        <Breakdown title={d.record.market} rows={record.by_symbol} d={d} />
        <Breakdown title={d.record.model} rows={record.by_model} labels={modelName} d={d} />
        <Breakdown title={d.record.session} rows={record.by_session} d={d} />
        <Breakdown title={d.record.cautions} rows={record.by_caution} d={d} />
        <div className="rounded-2xl border border-border bg-surface p-4 text-sm">
          <div className="text-xs uppercase tracking-wide text-muted">{d.record.neverFilled}</div>
          {Object.keys(record.not_filled_reasons).length === 0 ? <p className="mt-2 text-muted">{d.record.none}</p> : (
            <ul className="mt-2 space-y-1">{Object.entries(record.not_filled_reasons).map(([reason, n]) => <li key={reason} className="flex justify-between"><span>{reason.replaceAll("_", " ")}</span><span>{n}</span></li>)}</ul>
          )}
        </div>
      </div>

      <h2 className="mt-12 text-2xl font-semibold">{d.record.everyPlan}</h2>
      <p className="mt-1 text-sm text-muted">{d.record.latestOf} {plans.length} {d.record.of} {record.published}. {d.record.levelsLater}</p>
      <div className="mt-4 overflow-x-auto rounded-2xl border border-border bg-surface">
        <table className="w-full text-sm">
          <thead className="text-xs uppercase tracking-wide text-muted">
            <tr>{d.record.cols.map((col, i) => <th key={col} className={`px-3 py-2 ${[1, 2, 3, 4, 9].includes(i) ? "text-left" : "text-right"}`}>{col}</th>)}</tr>
          </thead>
          <tbody>
            {plans.length === 0 && <tr><td colSpan={12} className="px-3 py-3 text-muted">{d.record.noPlans}</td></tr>}
            {plans.map((plan) => {
              const won = (plan.result?.r_tp1 ?? 0) > 0;
              const tone = plan.status === "closed" ? (won ? "text-win" : "text-loss") : "text-muted";
              const result = plan.status === "open" ? d.record.openWord : plan.status === "not_filled" ? `${d.record.notFilledWord} · ${plan.result?.reason?.replaceAll("_", " ")}` : `${d.exits[plan.result?.exit ?? ""] ?? plan.result?.exit}${plan.result?.ambiguous ? " *" : ""}`;
              return (
                <tr key={plan.event_id} className="border-t border-line">
                  <td className="px-3 py-2 text-right"><Link href={href(lang, `/app/signals/${plan.seq}`)} className="text-gold underline">{plan.seq}</Link></td>
                  <td className="px-3 py-2 whitespace-nowrap">{utc(plan.published_at)}</td>
                  <td className="px-3 py-2">{plan.symbol}</td>
                  <td className={`px-3 py-2 ${plan.direction === "BUY" ? "text-win" : "text-loss"}`}>{plan.direction}</td>
                  <td className="px-3 py-2">{modelName[plan.model] ?? plan.model}</td>
                  <td className="px-3 py-2 text-right">{plan.levels ? price(plan.levels.entry) : "·"}</td>
                  <td className="px-3 py-2 text-right">{plan.levels ? price(plan.levels.stop) : "·"}</td>
                  <td className="px-3 py-2 text-right">{plan.levels ? price(plan.levels.targets[0]?.[1] ?? 0) : "·"}</td>
                  <td className="px-3 py-2 text-right" title={plan.cautions.join("; ")}>{plan.cautions.length || ""}</td>
                  <td className={`px-3 py-2 ${tone}`}>{result}</td>
                  <td className={`px-3 py-2 text-right ${tone}`}>{plan.status === "closed" ? r(plan.result?.r_tp1) : ""}</td>
                  <td className={`px-3 py-2 text-right ${tone}`}>{plan.status === "closed" ? r(plan.result?.r_scaled) : ""}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="mt-2 text-xs text-muted">{d.record.ambiguousNote}</p>

      <section className="mt-12 rounded-3xl border border-gold/25 bg-gradient-to-br from-gold/[0.06] to-transparent p-6">
        <h2 className="flex items-center gap-2 text-xl font-semibold"><ShieldCheck size={20} className="text-gold" /> {d.record.checkTitle}</h2>
        <p className="mt-2 text-sm text-muted">{d.record.checkText.split("/ledger.json")[0]}<a className="text-gold underline" href="/ledger.json">/ledger.json</a>{d.record.checkText.split("/ledger.json")[1]}</p>
        <p className="mt-2 break-all font-mono text-xs">#{record.chain.head_seq} {record.chain.head_hash}</p>
        <p className="mt-2 text-sm text-muted">{d.record.checkMatch}</p>
        <Link href={href(lang, "/verify")} className="mt-4 inline-flex h-11 items-center gap-2 rounded-xl bg-white px-5 font-semibold text-black hover:bg-white/90"><ShieldCheck size={16} /> Verify the chain in your browser</Link>
      </section>
    </>
  );
}

export default async function TrackRecordPage() {
  const lang: Lang = "en";
  const d = t(lang);
  return (
    <>
      <section className="py-14 pb-8">
        <span className="inline-flex items-center gap-2 rounded-full border border-white/12 bg-white/[0.03] px-3.5 py-1.5 text-[11px] font-semibold tracking-[0.2em] text-gold uppercase"><Trophy size={13} /> Transparency</span>
        <div className="mt-4 flex flex-wrap items-end justify-between gap-4">
          <div>
            <h1 className="font-display text-4xl font-bold tracking-tight md:text-5xl">Official track record</h1>
            <p className="mt-4 max-w-2xl text-lg text-muted">{d.record.intro}</p>
          </div>
          <span className="rounded-full border border-green/40 bg-green/10 px-4 py-2 text-sm font-semibold text-green">No cherry-picking</span>
        </div>
        <div className="mt-6 flex items-start gap-3 rounded-2xl border border-gold/25 bg-gold/[0.05] px-5 py-3.5 text-sm text-gold">
          <ShieldAlert size={18} className="mt-0.5 flex-none" />
          <span>Signals are published analysis for education. Not financial advice. Past results do not guarantee future results.</span>
        </div>
        <details className="group mt-4 rounded-2xl border border-border bg-surface">
          <summary className="flex cursor-pointer list-none items-center justify-between px-5 py-4 font-semibold">How we count <ChevronDown size={18} className="text-muted transition-transform group-open:rotate-180" /></summary>
          <ul className="space-y-2 border-t border-border px-5 py-4 text-sm leading-relaxed text-muted">
            <li><b className="text-text">Every plan counts.</b> A plan is written to the ledger the moment it publishes; wins, losses and never-filled plans all stay.</li>
            <li><b className="text-text">Graded on the broker&apos;s candles.</b> Each plan is replayed on 1-minute broker candles with the spread included.</li>
            <li><b className="text-text">Win rate is on TP1.</b> A trade wins if TP1 is reached before the stop. Scale-out R is shown next to it.</li>
            <li><b className="text-text">Unclear candles count as losses.</b> If one candle touched both a target and the stop, the worse outcome is recorded.</li>
            <li><b className="text-text">No daily reset.</b> Totals run from the first plan. Never-filled plans are listed separately, not hidden.</li>
          </ul>
        </details>
      </section>
      <Suspense fallback={<div className="h-64 animate-pulse rounded-2xl border border-border bg-surface" />}>
        <Record lang={lang} />
      </Suspense>
    </>
  );
}
