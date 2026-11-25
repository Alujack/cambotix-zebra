import RulePanel from "@/components/terminal/RulePanel";
import type { Setups } from "@/lib/api";
import { price, utc } from "@/lib/format";

type Labels = { title: string; note: string; reading: string; status: string; trend: string; rsi: string; macd: string; adx: string; atr: string; session: string; setup: string; last: string; none: string };

// The rule table of our indicator (tradingview/gold_setups.pine), from web/setups.py on the last closed 15m broker bar.
export default function SetupTable({ data, labels }: { data: Setups; labels: Labels }) {
  const table = data.table;
  if (!table) return null;
  const now = table.setup.status;
  const last = data.candidates.at(-1);
  return (
    <RulePanel
      title={labels.title} badge={`${labels.setup}: ${now}`} badgeTone={now === "BUY" ? "green" : now === "SELL" ? "red" : "neutral"} note={labels.note} labels={labels}
      rows={[
        { name: labels.trend, reading: String(table.trend.reading), status: table.trend.status, ok: table.trend.ok },
        { name: labels.rsi, reading: String(table.rsi.reading), status: table.rsi.status, ok: table.rsi.ok },
        { name: labels.macd, reading: String(table.macd_hist.reading), status: table.macd_hist.status, ok: table.macd_hist.ok },
        { name: labels.adx, reading: `${table.adx.reading} (min ${data.rules.min_adx})`, status: table.adx.status, ok: table.adx.ok },
        { name: labels.atr, reading: `${table.atr_percent.reading}% (${data.rules.min_atr_percent}-${data.rules.max_atr_percent})`, status: table.atr_percent.status, ok: table.atr_percent.ok },
        { name: labels.session, reading: String(table.session.reading), status: table.session.status, ok: table.session.ok },
      ]}
      footer={<>
        <span className="text-muted">{labels.last}: </span>
        {last ? <span className={last.direction === "BUY" ? "text-green" : "text-red"}>{last.direction} · {utc(last.bar_time)} · {price(last.entry)} / SL {price(last.stop, last.entry)}</span> : labels.none}
      </>}
    />
  );
}
