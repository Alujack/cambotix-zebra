import type { Plan } from "@/lib/api";
import { modelName, price, r, utc } from "@/lib/format";
import { t, type Lang } from "@/lib/i18n";

function Outcome({ plan, lang }: { plan: Plan; lang: Lang }) {
  const d = t(lang);
  if (plan.status === "open") return <span className="rounded-full bg-wait/15 px-2 py-0.5 text-xs text-wait">{d.card.open}</span>;
  if (plan.status === "not_filled") {
    return <span className="rounded-full bg-muted/15 px-2 py-0.5 text-xs text-muted">{d.card.notFilled} · {plan.result?.reason?.replaceAll("_", " ")}</span>;
  }
  const win = (plan.result?.r_tp1 ?? 0) > 0;
  return (
    <span className={`rounded-full px-2 py-0.5 text-xs ${win ? "bg-win/15 text-win" : "bg-loss/15 text-loss"}`}>
      {d.exits[plan.result?.exit ?? ""] ?? plan.result?.exit} · {r(plan.result?.r_tp1)}
      {plan.result?.ambiguous ? ` · ${d.card.ambiguous}` : ""}
    </span>
  );
}

export default function SignalCard({ plan, lang }: { plan: Plan; lang: Lang }) {
  const d = t(lang);
  const buy = plan.direction === "BUY";
  return (
    <article className="rounded-xl border border-line bg-card p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <span className={`rounded-md px-2 py-0.5 text-sm font-semibold ${buy ? "bg-win/15 text-win" : "bg-loss/15 text-loss"}`}>{plan.direction}</span>
          <span className="font-semibold">{plan.symbol}</span>
          <span className="text-sm text-muted">{plan.timeframe} · {modelName[plan.model] ?? plan.model}</span>
        </div>
        <Outcome plan={plan} lang={lang} />
      </div>
      <div className="mt-3 grid grid-cols-3 gap-3 text-sm">
        {plan.levels_public && plan.levels ? (
          <>
            <div><div className="text-xs text-muted">{d.card.entry}</div><div className="tabular-nums">{price(plan.levels.entry)}</div></div>
            <div><div className="text-xs text-muted">{d.card.stop}</div><div className="tabular-nums">{price(plan.levels.stop)}</div></div>
            <div><div className="text-xs text-muted">{d.card.tp1}{plan.levels.targets[0]?.[2] ? ` · ${plan.levels.targets[0][2]}` : ""}</div><div className="tabular-nums">{price(plan.levels.targets[0]?.[1] ?? 0)}</div></div>
          </>
        ) : (
          <div className="col-span-3 rounded-lg border border-dashed border-line px-3 py-2 text-xs text-muted">{d.card.hidden}</div>
        )}
      </div>
      {plan.cautions.length > 0 && (
        <ul className="mt-3 space-y-1 text-xs text-wait">{plan.cautions.map((item) => <li key={item}>⚠ {item}</li>)}</ul>
      )}
      <div className="mt-3 flex flex-wrap items-center justify-between gap-2 text-xs text-muted">
        <span>{d.card.published} {utc(plan.published_at)} · {plan.session ?? ""}</span>
        <span>{d.card.ledger} #{plan.seq}</span>
      </div>
      {plan.events.length > 0 && (
        <ol className="mt-2 space-y-0.5 border-t border-line pt-2 text-xs text-muted">
          {plan.events.filter((event) => event.kind !== "closed").map((event, index) => (
            <li key={index} className="flex justify-between tabular-nums">
              <span>{d.exits[event.kind] ?? event.kind}{event.price !== undefined ? ` ${price(event.price)}` : ""}{event.r !== undefined && event.kind !== "filled" ? ` (${r(event.r)})` : ""}</span>
              <span>{utc(event.time)}</span>
            </li>
          ))}
        </ol>
      )}
    </article>
  );
}
