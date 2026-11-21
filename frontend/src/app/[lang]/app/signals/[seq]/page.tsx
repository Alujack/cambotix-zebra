import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { connection } from "next/server";
import TopBar from "@/components/shell/TopBar";
import PositionSizer from "@/components/PositionSizer";
import { Direction, Outcome } from "@/components/SignalCard";
import { getPlan, type Plan } from "@/lib/api";
import { modelName, price, r, utc } from "@/lib/format";
import { href, isLang, t, type Lang } from "@/lib/i18n";
import { site } from "@/lib/site";

export const metadata: Metadata = { title: "Signal" };

function Level({ label, value, entry, tone, extra }: { label: string; value: number; entry?: number; tone: "win" | "loss" | "gold" | "neutral"; extra?: string }) {
  const distance = entry !== undefined && entry !== value ? `${value > entry ? "+" : ""}${(value - entry).toFixed(value >= 100 ? 2 : 5)} (${(((value - entry) / entry) * 100).toFixed(2)}%)` : extra;
  const color = tone === "win" ? "text-win" : tone === "loss" ? "text-loss" : tone === "gold" ? "text-accent" : "text-fg";
  return (
    <div className={`level tone-${tone}`}>
      <div className="label">{label}</div>
      <div className={`price mt-1 ${color}`}>{price(value)}</div>
      {distance && <div className="mt-0.5 text-xs text-muted">{distance}</div>}
    </div>
  );
}

function Summary({ plan, lang }: { plan: Plan; lang: Lang }) {
  const d = t(lang);
  const levels = plan.levels;
  const risk = levels ? Math.abs(levels.entry - levels.stop) : null;
  const rr = levels ? levels.targets[0]?.[0] : null;
  const items: [string, string][] = [
    [d.detail.direction, plan.direction],
    [d.detail.model, modelName[plan.model] ?? plan.model],
    [d.detail.session, plan.session ?? "—"],
    [d.detail.order, plan.entry_type === "limit" ? d.card.limit : d.card.market],
    [d.detail.rr, rr !== null && rr !== undefined ? `1 : ${rr}` : "—"],
    [d.detail.risk, risk !== null ? price(risk) : "—"],
  ];
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
      {items.map(([label, value]) => (
        <div key={label} className="card p-3"><div className="label">{label}</div><div className="mt-1 font-semibold">{value}</div></div>
      ))}
    </div>
  );
}

async function Detail({ params }: { params: Promise<{ lang: string; seq: string }> }) {
  await connection();   // no prerendered shell for this route: a missing plan must be a real 404
  const { lang, seq } = await params;
  if (!isLang(lang)) notFound();
  const number = Number(seq);
  const plan = Number.isInteger(number) && number > 0 ? await getPlan(number) : null;
  if (!plan) notFound();
  const d = t(lang);
  const levels = plan.levels;
  const sizerLabels = { calc: d.detail.calc, account: d.detail.account, riskPct: d.detail.riskPct, riskMoney: d.detail.riskMoney, units: d.detail.units, lots: d.detail.lots, rewardTp1: d.detail.rewardTp1, notional: d.detail.notional, calcNote: d.detail.calcNote };
  return (
    <>
      <TopBar lang={lang} title={`${plan.symbol} · ${plan.direction}`} help={d.signals.intro} />
      <section className="py-6">
        <Link href={href(lang, "/app/signals")} className="text-sm text-muted hover:text-fg">← {d.detail.back}</Link>
        <div className="mt-3 flex flex-wrap items-center gap-3">
          <h1 className="text-3xl font-bold">{plan.symbol}</h1>
          <Direction direction={plan.direction} />
          <Outcome plan={plan} lang={lang} />
          <span className="pill">{d.card.published} {utc(plan.published_at)}</span>
          <span className="pill">{d.card.ledger} #{plan.seq}</span>
        </div>
      </section>

      <h2 className="label mb-2">{d.detail.summary}</h2>
      <Summary plan={plan} lang={lang} />

      <h2 className="label mt-8 mb-2">{d.detail.levels}</h2>
      {levels ? (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          <Level label={d.card.entry} value={levels.entry} tone="neutral" extra={plan.entry_type === "limit" ? d.card.limit : d.card.market} />
          <Level label={d.card.stop} value={levels.stop} entry={levels.entry} tone="loss" />
          <div className="level tone-gold">
            <div className="label">{d.detail.rr}</div>
            <div className="price mt-1 text-accent">1 : {levels.targets[0]?.[0] ?? "—"}</div>
            <div className="mt-0.5 text-xs text-muted">{d.detail.risk} = {price(Math.abs(levels.entry - levels.stop))}</div>
          </div>
          {levels.targets.map(([multiple, level, note], index) => (
            <Level key={index} label={`TP${index + 1} · +${multiple}R${note ? ` · ${note}` : ""}`} value={level} entry={levels.entry} tone="win" />
          ))}
        </div>
      ) : (
        <div className="level tone-info text-sm">⏳ {d.detail.openNote}</div>
      )}

      <div className="mt-8 grid gap-6 lg:grid-cols-2">
        <div>
          <h2 className="label mb-2">{d.detail.cautions}</h2>
          {plan.cautions.length === 0 ? <p className="text-sm text-muted">{d.detail.noCautions}</p> : (
            <ul className="space-y-1.5">{plan.cautions.map((item) => <li key={item} className="chip w-full justify-start"><span className="chip-dot bg-wait" />{item}</li>)}</ul>
          )}
        </div>
        <div>
          <h2 className="label mb-2">{d.detail.timeline}</h2>
          {plan.events.length === 0 ? <p className="text-sm text-muted">—</p> : (
            <ol className="card divide-y divide-line text-sm">
              {plan.events.map((event, index) => (
                <li key={index} className="flex items-center justify-between gap-3 px-3 py-2">
                  <span className={event.kind === "sl" ? "text-loss" : event.kind.startsWith("tp") ? "text-win" : event.kind === "closed" ? "font-semibold" : ""}>
                    {d.exits[event.kind] ?? event.kind}
                    {event.price !== undefined ? ` ${price(event.price)}` : ""}
                    {event.r !== undefined && event.kind !== "filled" ? ` (${r(event.r)})` : ""}
                    {event.kind === "closed" ? ` · ${d.detail.tp1Basis} ${r(event.r_tp1)} · ${d.detail.scaleOut} ${r(event.r_scaled)}` : ""}
                    {event.reason ? ` · ${event.reason.replaceAll("_", " ")}` : ""}
                  </span>
                  <span className="whitespace-nowrap text-xs text-muted">{utc(event.time)}</span>
                </li>
              ))}
            </ol>
          )}
        </div>
      </div>

      {levels && (
        <div className="mt-8">
          <PositionSizer symbol={plan.symbol} entry={levels.entry} stop={levels.stop} tp1={levels.targets[0]?.[1] ?? levels.entry} labels={sizerLabels} />
        </div>
      )}

      <div className="mt-8 flex flex-wrap gap-3">
        <Link href={href(lang, "/app/signals")} className="btn-secondary">{d.detail.back}</Link>
        <a href={site.telegram} className="btn-primary">{d.nav.telegram}</a>
      </div>
    </>
  );
}

// Blocking on purpose: the plan lookup is a cached 1 ms call, and a missing plan must answer with a real 404.
export const instant = false;

export default function SignalDetailPage({ params }: PageProps<"/[lang]/app/signals/[seq]">) {
  return <Detail params={params} />;
}
