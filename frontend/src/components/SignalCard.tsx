import { ChevronDown, Hourglass } from "lucide-react";
import Link from "next/link";
import Countdown from "@/components/Countdown";
import MarketIcon from "@/components/MarketIcon";
import { Badge, Chip, type Tone } from "@/components/ui";
import type { Plan, Ticker } from "@/lib/api";
import { modelName, price, r, utc } from "@/lib/format";
import { href, t, type Lang } from "@/lib/i18n";

const assetClass = (symbol: string) => (/BTC|ETH|SOL|USDT$/.test(symbol) ? "crypto" : /^XAU|^XAG|OIL/.test(symbol) ? "metals" : "forex");

export function Direction({ direction }: { direction: "BUY" | "SELL" }) {
  return <Badge tone={direction === "BUY" ? "green" : "red"} dot>{direction}</Badge>;
}

// State pill: colour plus the word, never colour alone.
export function Outcome({ plan, lang }: { plan: Plan; lang: Lang }) {
  const d = t(lang);
  if (plan.status === "open") return <Badge tone="yellow" dot>{plan.events.length ? d.card.openFilled : d.card.openWaiting}</Badge>;
  if (plan.status === "not_filled") return <Badge tone="neutral">{d.card.notFilled} · {plan.result?.reason?.replaceAll("_", " ")}</Badge>;
  const win = (plan.result?.r_tp1 ?? 0) > 0;
  return (
    <Badge tone={win ? "green" : "red"}>
      {d.exits[plan.result?.exit ?? ""] ?? plan.result?.exit} · {r(plan.result?.r_tp1)}{plan.result?.ambiguous ? ` · ${d.card.ambiguous}` : ""}
    </Badge>
  );
}

function Row({ label, value, tone }: { label: string; value: string; tone?: Tone }) {
  const color = tone === "green" ? "text-green" : tone === "red" ? "text-red" : "text-text";
  return (
    <div className="flex items-baseline justify-between border-t border-border py-2 first:border-t-0">
      <span className="label">{label}</span>
      <span className={`price ${color}`}>{value}</span>
    </div>
  );
}

// Compact card (§4): asset row → centred badges → limit notice → three levels → ≤3 chips → expiry → state pills → one action.
export default function SignalCard({ plan, lang, ticker }: { plan: Plan; lang: Lang; ticker?: Ticker }) {
  const d = t(lang);
  const buy = plan.direction === "BUY";
  const limit = plan.entry_type === "limit";
  const chips = plan.cautions.slice(0, 3);
  const hidden = plan.cautions.length - chips.length;
  const live = ticker?.price;
  const finished = plan.status !== "open";
  const closedAt = plan.events.find((event) => event.kind === "closed" || event.kind === "not_filled")?.time;
  return (
    <article className={`flex flex-col rounded-2xl border bg-gradient-to-b p-5 ${buy ? "border-green/25 from-green/[0.05]" : "border-red/25 from-red/[0.05]"} to-surface`}>
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-3">
          <MarketIcon symbol={plan.symbol} size={44} />
          <div>
            <div className="text-lg font-bold leading-tight">{plan.symbol}</div>
            <div className="text-xs text-muted">{d.card[assetClass(plan.symbol)]} · {plan.timeframe} · {modelName[plan.model] ?? plan.model}</div>
          </div>
        </div>
        <span className="label whitespace-nowrap">{d.card.intraday} ({plan.timeframe})</span>
      </div>

      <div className="mt-3 flex flex-wrap justify-center gap-2">
        <Direction direction={plan.direction} />
        <Badge tone="neutral">{limit ? d.card.limit : d.card.market}</Badge>
        <Badge tone="gold">{plan.session ?? d.card.auto}</Badge>
      </div>

      {limit && plan.status === "open" && (
        <div className="tint tone-blue mt-3 text-xs leading-relaxed">
          <div className="flex items-start gap-2 text-blue"><Hourglass size={14} className="mt-0.5 shrink-0" /><span>{d.card.limitNotice}</span></div>
          <div className="mt-1 text-muted">{d.card.validUntil} {utc(plan.expires_at)} · {d.card.cancelledIf}</div>
        </div>
      )}

      <div className="mt-3">
        {plan.levels_public && plan.levels ? (
          <>
            <Row label={d.card.entry} value={price(plan.levels.entry)} />
            <Row label={`${d.card.target} · ${plan.levels.targets[0]?.[2] || "TP1"}`} value={price(plan.levels.targets[0]?.[1] ?? 0)} tone="green" />
            <Row label={d.card.stop} value={price(plan.levels.stop)} tone="red" />
          </>
        ) : (
          <div className="tint tone-blue text-xs text-text">
            {d.card.hidden}
            {live !== undefined && <span className="mt-1 block text-muted">{d.card.livePrice} {price(live)}</span>}
          </div>
        )}
      </div>

      {chips.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {chips.map((item) => <Chip key={item} tone="yellow" title={item}>{item.length > 44 ? item.slice(0, 42) + "…" : item}</Chip>)}
          {hidden > 0 && <Link href={href(lang, `/app/signals/${plan.seq}`)} className="chip text-muted">+{hidden} <ChevronDown size={12} /></Link>}
        </div>
      )}

      <div className="mt-3 flex items-center justify-between text-xs text-muted">
        {finished ? (
          <span>{d.card.opened} {utc(plan.published_at)}{closedAt ? ` · ${d.card.closed} ${utc(closedAt)}` : ""}</span>
        ) : (
          <>
            <span>{limit ? d.card.expires : d.card.holdsUntil}</span>
            <span className="font-semibold text-text"><Countdown until={limit ? plan.expires_at : plan.hold_until} expired={d.card.expired} /></span>
          </>
        )}
      </div>

      <div className="mt-2 flex flex-wrap items-center gap-1.5">
        <Outcome plan={plan} lang={lang} />
        <span className="pill">{d.card.ledger} #{plan.seq}</span>
      </div>

      <Link href={href(lang, `/app/signals/${plan.seq}`)} className="btn-primary mt-4 w-full">{d.card.view}</Link>
    </article>
  );
}
