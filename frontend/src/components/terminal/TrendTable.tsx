import RulePanel from "@/components/terminal/RulePanel";
import type { Trend } from "@/lib/api";
import { price, utc } from "@/lib/format";

type Labels = { title: string; note: string; reading: string; status: string; trail: string; baseline: string; htf: string; adx: string; chop: string; session: string; extension: string; structure: string; signal: string; up: string; down: string; last: string; none: string; flips: string; passed: string };

// The readings of the ATR Trend Confluence System (web/trend.py) on the last closed bar of the chart's timeframe:
// which way the trailing stop points, and which filters would let a flip through right now.
export default function TrendTable({ data, labels }: { data: Trend; labels: Labels }) {
  const table = data.table;
  if (!table) return null;
  const up = table.signal.trend === "up";
  const label = table.signal.status === "BUY" || table.signal.status === "SELL" ? table.signal.status : up ? labels.up : labels.down;
  const last = data.signals.at(-1);
  const row = (name: string, item: { reading: string | number; status: string; ok: boolean }) => ({ name, reading: String(item.reading), status: item.status, ok: item.ok });
  return (
    <RulePanel
      title={`${labels.title} · ${data.tf}`} badge={label} badgeTone={up ? "green" : "red"} note={labels.note} labels={labels}
      rows={[
        row(labels.trail, { ...table.trail, reading: price(Number(table.trail.reading)) }),
        row(labels.baseline, table.baseline), row(labels.htf, table.htf), row(labels.adx, table.adx), row(labels.chop, table.chop),
        row(labels.session, table.session), row(labels.extension, table.extension), row(labels.structure, table.structure),
      ]}
      footer={<>
        <span className="text-muted">{labels.last}: </span>
        {last ? <span className={last.direction === "BUY" ? "text-green" : "text-red"}>{last.direction} · {utc(last.bar_time)} · {price(last.price)}</span> : labels.none}
        <span className="text-muted"> · {data.flips.length} {labels.flips}, {data.signals.length} {labels.passed}</span>
      </>}
    />
  );
}
