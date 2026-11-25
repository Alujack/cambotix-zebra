import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";
import StatTile from "@/components/StatTile";
import { getRecord, getSignals, type Summary } from "@/lib/api";
import { modelName, percent, price, r, utc } from "@/lib/format";
import { href, t, type Dict, type Lang } from "@/lib/i18n";

export const metadata: Metadata = { title: "Track record", description: "The complete graded record: every plan, every outcome, verifiable hash chain." };

function Breakdown({ title, rows, labels, d }: { title: string; rows: { [name: string]: Summary }; labels?: { [key: string]: string }; d: Dict }) {
  const entries = Object.entries(rows);
  return (
    <div className="overflow-x-auto rounded-xl border border-line bg-card">
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
      <p className="mt-4 text-sm text-muted">{record.basis}</p>

      <div className="mt-10 grid gap-6 lg:grid-cols-2">
        <Breakdown title={d.record.month} rows={record.by_month} d={d} />
        <Breakdown title={d.record.market} rows={record.by_symbol} d={d} />
        <Breakdown title={d.record.model} rows={record.by_model} labels={modelName} d={d} />
        <Breakdown title={d.record.session} rows={record.by_session} d={d} />
        <Breakdown title={d.record.cautions} rows={record.by_caution} d={d} />
        <div className="rounded-xl border border-line bg-card p-4 text-sm">
          <div className="text-xs uppercase tracking-wide text-muted">{d.record.neverFilled}</div>
          {Object.keys(record.not_filled_reasons).length === 0 ? <p className="mt-2 text-muted">{d.record.none}</p> : (
            <ul className="mt-2 space-y-1">{Object.entries(record.not_filled_reasons).map(([reason, n]) => <li key={reason} className="flex justify-between"><span>{reason.replaceAll("_", " ")}</span><span>{n}</span></li>)}</ul>
          )}
        </div>
      </div>

      <h2 className="mt-12 text-2xl font-semibold">{d.record.everyPlan}</h2>
      <p className="mt-1 text-sm text-muted">{d.record.latestOf} {plans.length} {d.record.of} {record.published}. {d.record.levelsLater}</p>
      <div className="mt-4 overflow-x-auto rounded-xl border border-line bg-card">
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
                  <td className="px-3 py-2 text-right"><Link href={href(lang, `/app/signals/${plan.seq}`)} className="text-accent underline">{plan.seq}</Link></td>
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

      <section className="mt-12 rounded-2xl border border-line bg-card p-6">
        <h2 className="text-xl font-semibold">{d.record.checkTitle}</h2>
        <p className="mt-2 text-sm text-muted">{d.record.checkText.replace("/ledger.json", "")}<a className="text-accent underline" href="/ledger.json">/ledger.json</a></p>
        <p className="mt-2 break-all font-mono text-xs">#{record.chain.head_seq} {record.chain.head_hash}</p>
        <p className="mt-2 text-sm text-muted">{d.record.checkMatch}</p>
      </section>
    </>
  );
}

export default async function TrackRecordPage() {
  const lang: Lang = "en";
  const d = t(lang);
  return (
    <>
      <section className="py-10">
        <h1 className="text-3xl font-semibold">{d.record.title}</h1>
        <p className="mt-2 max-w-2xl text-muted">{d.record.intro}</p>
      </section>
      <Suspense fallback={<div className="h-64 animate-pulse rounded-xl border border-line bg-card" />}>
        <Record lang={lang} />
      </Suspense>
    </>
  );
}
