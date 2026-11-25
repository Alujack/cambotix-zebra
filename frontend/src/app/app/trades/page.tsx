import Link from "next/link";
import { Suspense } from "react";
import { Outcome } from "@/components/SignalCard";
import TopBar from "@/components/shell/TopBar";
import { Badge, EmptyState, Skeleton, StatCard } from "@/components/ui";
import { getRecord, getSignals } from "@/lib/api";
import { modelName, percent, price, r, utc } from "@/lib/format";
import { href, t, type Lang } from "@/lib/i18n";

const TABS = ["record", "history", "journal", "performance"] as const;
type Tab = (typeof TABS)[number];

async function Trades({ lang, searchParams }: { lang: Lang; searchParams: Promise<{ tab?: string; symbol?: string; status?: string }> }) {
  const d = t(lang);
  const query = await searchParams;
  const tab: Tab = TABS.includes(query.tab as Tab) ? (query.tab as Tab) : "record";
  const [record, plans] = await Promise.all([getRecord(), getSignals(200)]);
  const symbols = [...new Set(plans.map((plan) => plan.symbol))];
  const statuses = ["open", "closed", "not_filled"];
  const rows = plans.filter((plan) => (!query.symbol || plan.symbol === query.symbol) && (!query.status || plan.status === query.status));
  const h = record.headline;
  const link = (changes: { [key: string]: string | undefined }) => {
    const q = new URLSearchParams();
    for (const [key, value] of Object.entries({ tab, symbol: query.symbol, status: query.status, ...changes })) if (value) q.set(key, value);
    return href(lang, `/app/trades?${q.toString()}`);
  };
  return (
    <>
      <div className="mb-4 flex flex-wrap gap-1.5">
        {TABS.map((item) => <Link key={item} href={link({ tab: item })} className={`pill ${item === tab ? "pill-active" : ""}`}>{d.trades[item]}</Link>)}
      </div>

      {tab === "record" && (
        <>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-6">
            <StatCard label={d.record.closed} value={String(h.closed)} />
            <StatCard label={d.tiles.winRate} value={h.closed ? percent(h.win_rate) : "—"} caption={h.closed ? undefined : d.overview.noHistory} />
            <StatCard label={d.record.wins} value={String(h.wins)} tone="green" />
            <StatCard label={d.exits.sl} value={String(h.closed - h.wins)} tone="red" />
            <StatCard label={d.record.totalR} value={r(h.total_r_tp1)} tone={h.total_r_tp1 > 0 ? "green" : h.total_r_tp1 < 0 ? "red" : undefined} />
            <StatCard label={d.tiles.profitFactor} value={h.profit_factor === null || h.profit_factor === undefined ? "—" : String(h.profit_factor)} />
          </div>
          <p className="mt-3 text-xs text-muted">{d.record.intro}</p>
          <Link href={href(lang, "/track-record")} className="btn-secondary mt-3">{d.nav.record} →</Link>
        </>
      )}

      {tab === "history" && (
        <>
          <div className="mb-3 flex flex-wrap items-center gap-1.5 text-xs">
            <span className="label mr-1">{d.trades.status}</span>
            <Link href={link({ status: undefined })} className={`pill ${!query.status ? "pill-active" : ""}`}>{d.trades.all}</Link>
            {statuses.map((item) => <Link key={item} href={link({ status: item })} className={`pill ${query.status === item ? "pill-active" : ""}`}>{item.replace("_", " ")}</Link>)}
            <span className="label mx-1 ml-3">{d.trades.symbol}</span>
            <Link href={link({ symbol: undefined })} className={`pill ${!query.symbol ? "pill-active" : ""}`}>{d.trades.all}</Link>
            {symbols.map((item) => <Link key={item} href={link({ symbol: item })} className={`pill ${query.symbol === item ? "pill-active" : ""}`}>{item}</Link>)}
          </div>
          {rows.length === 0 ? <EmptyState title={d.signals.empty} /> : (
            <div className="card overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="label"><tr>{d.trades.cols.map((col, i) => <th key={col} className={`px-3 py-2 font-normal ${i >= 3 && i <= 4 ? "text-right" : "text-left"}`}>{col}</th>)}</tr></thead>
                <tbody>
                  {rows.map((plan) => (
                    <tr key={plan.event_id} className="border-t border-border">
                      <td className="px-3 py-2"><Link href={href(lang, `/app/signals/${plan.seq}`)} className="font-semibold hover:text-gold">{plan.symbol}</Link><div className="text-xs text-muted">{modelName[plan.model] ?? plan.model}</div></td>
                      <td className="px-3 py-2">{plan.timeframe}</td>
                      <td className="px-3 py-2"><Badge tone={plan.direction === "BUY" ? "green" : "red"} dot>{plan.direction}</Badge></td>
                      <td className="px-3 py-2 text-right num">{plan.levels ? price(plan.levels.entry) : "·"}</td>
                      <td className="px-3 py-2 text-right num">{plan.levels ? `1:${plan.levels.targets[0]?.[0] ?? "—"}` : "·"}</td>
                      <td className="px-3 py-2"><Outcome plan={plan} lang={lang} /></td>
                      <td className="px-3 py-2 whitespace-nowrap text-xs text-muted">{utc(plan.published_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}

      {tab === "journal" && <EmptyState title={d.shell.comingSoon} text={d.trades.journalTodo} />}

      {tab === "performance" && (
        <div className="grid gap-4 lg:grid-cols-2">
          {([["by_month", d.record.month], ["by_symbol", d.record.market], ["by_model", d.record.model], ["by_session", d.record.session]] as const).map(([key, title]) => (
            <div key={key} className="card overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="label"><tr><th className="px-3 py-2 text-left font-normal">{title}</th><th className="px-3 py-2 text-right font-normal">{d.record.closed}</th><th className="px-3 py-2 text-right font-normal">{d.record.winRate}</th><th className="px-3 py-2 text-right font-normal">{d.record.totalR}</th></tr></thead>
                <tbody>
                  {Object.entries(record[key]).length === 0 && <tr><td colSpan={4} className="px-3 py-3 text-muted">{d.record.noClosed}</td></tr>}
                  {Object.entries(record[key]).map(([name, s]) => (
                    <tr key={name} className="border-t border-border"><td className="px-3 py-2">{key === "by_model" ? modelName[name] ?? name : name}</td><td className="px-3 py-2 text-right">{s.closed}</td><td className="px-3 py-2 text-right">{percent(s.win_rate)}</td><td className={`px-3 py-2 text-right ${s.total_r_tp1 > 0 ? "text-green" : s.total_r_tp1 < 0 ? "text-red" : ""}`}>{r(s.total_r_tp1)}</td></tr>
                  ))}
                </tbody>
              </table>
            </div>
          ))}
        </div>
      )}
    </>
  );
}

export default async function TradesPage({ searchParams }: PageProps<"/app/trades">) {
  const lang: Lang = "en";
  const d = t(lang);
  return (
    <>
      <TopBar lang={lang} title={d.nav.trades} help={d.trades.help} />
      <p className="mb-4 text-xs text-muted">{d.shell.guestNote}</p>
      <Suspense fallback={<Skeleton className="h-64" />}>
        <Trades lang={lang} searchParams={searchParams as Promise<{ tab?: string; symbol?: string; status?: string }>} />
      </Suspense>
    </>
  );
}
