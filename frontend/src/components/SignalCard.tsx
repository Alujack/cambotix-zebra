import Link from "next/link";
import type { Plan } from "@/lib/api";
import { modelName, price, r, utc } from "@/lib/format";
import { href, t, type Lang } from "@/lib/i18n";

export function Direction({ direction }: { direction: "BUY" | "SELL" }) {
  const buy = direction === "BUY";
  return (
    <span className={`badge ${buy ? "border-win/50 bg-win/10 text-win" : "border-loss/50 bg-loss/10 text-loss"}`}>
      <span className={`chip-dot ${buy ? "bg-win" : "bg-loss"}`} /> {direction}
    </span>
  );
}

export function Outcome({ plan, lang }: { plan: Plan; lang: Lang }) {
  const d = t(lang);
  if (plan.status === "open") return <span className="badge border-wait/50 bg-wait/10 text-wait">{d.card.open}</span>;
  if (plan.status === "not_filled") {
    return <span className="badge border-line bg-card text-muted">{d.card.notFilled} · {plan.result?.reason?.replaceAll("_", " ")}</span>;
  }
  const win = (plan.result?.r_tp1 ?? 0) > 0;
  return (
    <span className={`badge ${win ? "border-win/50 bg-win/10 text-win" : "border-loss/50 bg-loss/10 text-loss"}`}>
      {d.exits[plan.result?.exit ?? ""] ?? plan.result?.exit} · {r(plan.result?.r_tp1)}
      {plan.result?.ambiguous ? ` · ${d.card.ambiguous}` : ""}
    </span>
  );
}

function Row({ label, value, tone }: { label: string; value: string; tone?: "win" | "loss" }) {
  const color = tone === "win" ? "text-win" : tone === "loss" ? "text-loss" : "text-fg";
  return (
    <div className="flex items-baseline justify-between border-t border-line py-2 first:border-t-0">
      <span className="label">{label}</span>
      <span className={`price ${color}`}>{value}</span>
    </div>
  );
}

// The compact card: symbol and timeframe, two badges, the three levels, a couple of quality chips, status pills,
// then one full-width action. Everything else lives on the detail page.
export default function SignalCard({ plan, lang }: { plan: Plan; lang: Lang }) {
  const d = t(lang);
  const shown = plan.cautions.slice(0, 2);
  const hidden = plan.cautions.length - shown.length;
  return (
    <article className="card flex flex-col p-4">
      <div className="flex items-start justify-between gap-2">
        <div>
          <div className="text-lg font-bold">{plan.symbol}</div>
          <div className="text-xs text-muted">{modelName[plan.model] ?? plan.model} · {plan.timeframe}</div>
        </div>
        <span className="pill uppercase">{d.card.intraday} ({plan.timeframe})</span>
      </div>
      <div className="mt-3 flex flex-wrap gap-2">
        <Direction direction={plan.direction} />
        <span className="badge border-line bg-card text-muted">{plan.entry_type === "limit" ? d.card.limit : d.card.market}</span>
      </div>
      <div className="mt-3">
        {plan.levels_public && plan.levels ? (
          <>
            <Row label={d.card.entry} value={price(plan.levels.entry)} />
            <Row label={`${d.card.target} · ${plan.levels.targets[0]?.[2] || "TP1"}`} value={price(plan.levels.targets[0]?.[1] ?? 0)} tone="win" />
            <Row label={d.card.stop} value={price(plan.levels.stop)} tone="loss" />
          </>
        ) : (
          <div className="level tone-info text-xs text-fg">⏳ {d.card.hidden}</div>
        )}
      </div>
      {shown.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {shown.map((item) => (
            <span key={item} className="chip" title={item}><span className="chip-dot bg-wait" />{item.length > 42 ? item.slice(0, 40) + "…" : item}</span>
          ))}
          {hidden > 0 && <span className="chip text-muted">+{hidden} {d.card.more} ⌄</span>}
        </div>
      )}
      <div className="mt-3 flex flex-wrap items-center gap-1.5">
        <Outcome plan={plan} lang={lang} />
        {plan.session && <span className="pill">{plan.session}</span>}
        <span className="pill">{d.card.ledger} #{plan.seq}</span>
        <span className="ml-auto text-xs text-muted">{utc(plan.published_at)}</span>
      </div>
      <Link href={href(lang, `/signals/${plan.seq}`)} className="btn-primary mt-4 w-full">{d.card.view}</Link>
    </article>
  );
}
