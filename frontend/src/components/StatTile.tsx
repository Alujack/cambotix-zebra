export default function StatTile({ label, value, hint, tone }: { label: string; value: string; hint?: string; tone?: "win" | "loss" | "muted" }) {
  const color = tone === "win" ? "text-win" : tone === "loss" ? "text-loss" : tone === "muted" ? "text-muted" : "text-fg";
  return (
    <div className="card p-4">
      <div className="label">{label}</div>
      <div className={`mt-1 text-2xl font-extrabold tabular-nums ${color}`}>{value}</div>
      {hint && <div className="mt-1 text-xs text-muted">{hint}</div>}
    </div>
  );
}
