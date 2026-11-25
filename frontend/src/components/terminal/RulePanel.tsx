export type RuleRow = { name: string; reading: string; status: string; ok: boolean };
type Tone = "green" | "red" | "neutral";

// A folded indicator table on the chart: title and verdict in the summary, one row per rule when opened.
// A <details> element that starts folded, so it never hides the newest candles and needs no client script.
export default function RulePanel({ title, badge, badgeTone, rows, footer, note, labels }: {
  title: string; badge: string; badgeTone: Tone; rows: RuleRow[]; footer: React.ReactNode; note: string; labels: { reading: string; status: string };
}) {
  const tone = (ok: boolean) => (ok ? "bg-green/20 text-green" : "bg-red/20 text-red");
  return (
    <details className="w-[340px] rounded-xl border border-border bg-surface/95 text-xs backdrop-blur">
      <summary className="flex cursor-pointer items-center justify-between gap-2 px-3 py-2 font-semibold">
        <span>{title}</span>
        <span className={`rounded-md px-2 py-0.5 ${badgeTone === "green" ? "bg-green/20 text-green" : badgeTone === "red" ? "bg-red/20 text-red" : "bg-surface-2 text-muted"}`}>{badge}</span>
      </summary>
      <table className="w-full border-t border-border">
        <thead><tr className="text-muted"><th className="px-3 py-1 text-left font-normal" /><th className="px-1 py-1 text-left font-normal">{labels.reading}</th><th className="px-3 py-1 text-right font-normal">{labels.status}</th></tr></thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.name} className="border-t border-border/50">
              <td className="px-3 py-1 whitespace-nowrap text-muted">{row.name}</td>
              <td className="num px-1 py-1">{row.reading}</td>
              <td className="px-3 py-1 text-right"><span className={`rounded px-1.5 py-0.5 whitespace-nowrap ${tone(row.ok)}`}>{row.status}</span></td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="border-t border-border px-3 py-1.5">{footer}</p>
      <p className="border-t border-border px-3 py-1.5 text-[11px] text-muted">{note}</p>
    </details>
  );
}
