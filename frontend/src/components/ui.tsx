import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

export type Tone = "green" | "red" | "gold" | "blue" | "yellow" | "neutral";
const textTone: { [key in Tone]: string } = { green: "text-green", red: "text-red", gold: "text-gold", blue: "text-blue", yellow: "text-yellow", neutral: "text-muted" };
const badgeTone: { [key in Tone]: string } = {
  green: "border-green/50 bg-green/10 text-green", red: "border-red/50 bg-red/10 text-red", gold: "border-gold/50 bg-gold/10 text-gold",
  blue: "border-blue/50 bg-blue/10 text-blue", yellow: "border-yellow/50 bg-yellow/10 text-yellow", neutral: "border-border bg-surface text-muted",
};
const dotTone: { [key in Tone]: string } = { green: "bg-green", red: "bg-red", gold: "bg-gold", blue: "bg-blue", yellow: "bg-yellow", neutral: "bg-muted" };

export function Badge({ tone = "neutral", dot, children }: { tone?: Tone; dot?: boolean; children: ReactNode }) {
  return <span className={`badge ${badgeTone[tone]}`}>{dot && <span className={`dot ${dotTone[tone]}`} />}{children}</span>;
}

export function Chip({ tone = "yellow", children, title }: { tone?: Tone; children: ReactNode; title?: string }) {
  return <span className="chip" title={title}><span className={`dot ${dotTone[tone]}`} />{children}</span>;
}

export function SectionLabel({ children }: { children: ReactNode }) {
  return <div className="label mb-2">{children}</div>;
}

export function SectionCard({ label, children, className = "" }: { label?: string; children: ReactNode; className?: string }) {
  return (
    <section className={`card-lg p-4 md:p-5 ${className}`}>
      {label && <div className="label mb-3">{label}</div>}
      {children}
    </section>
  );
}

// Stat card: uppercase label, big number, caption, small icon button top-right, ghost icon bottom-right at ~6%.
export function StatCard({ label, value, caption, icon: Icon, tone }: { label: string; value: string; caption?: string; icon?: LucideIcon; tone?: Tone }) {
  return (
    <div className="card relative overflow-hidden p-4">
      <div className="flex items-start justify-between">
        <div className="label">{label}</div>
        {Icon && <span className="btn-icon !h-7 !w-7"><Icon size={14} /></span>}
      </div>
      <div className={`mt-2 text-[26px] font-extrabold leading-none num ${tone ? textTone[tone] : "text-text"}`}>{value}</div>
      {caption && <div className="mt-2 text-xs text-muted">{caption}</div>}
      {Icon && <Icon className="pointer-events-none absolute -right-3 -bottom-3 opacity-[0.06]" size={96} strokeWidth={1.2} aria-hidden />}
    </div>
  );
}

// Tinted level card: 7% tint, 40% border, value at 20px/800, muted distance line.
export function LevelCard({ label, value, caption, tone }: { label: string; value: string; caption?: string; tone: Tone }) {
  return (
    <div className={`tint tone-${tone}`}>
      <div className="label">{label}</div>
      <div className={`price mt-1 ${tone === "neutral" ? "text-text" : "tint-text"}`}>{value}</div>
      {caption && <div className="mt-0.5 text-xs text-muted">{caption}</div>}
    </div>
  );
}

export function IndicatorTile({ label, value, verdict, tone, percent }: { label: string; value: string; verdict: string; tone: Tone; percent: number }) {
  const width = Math.max(0, Math.min(100, percent));
  return (
    <div className="card p-4">
      <div className="label">{label}</div>
      <div className="price mt-1">{value}</div>
      <div className={`mt-1 text-xs font-semibold ${textTone[tone]}`}>{verdict}</div>
      <div className="mt-2 h-1 w-full overflow-hidden rounded-full bg-surface-2"><div className={`h-full ${dotTone[tone]}`} style={{ width: `${width}%` }} /></div>
    </div>
  );
}

export function Skeleton({ className = "" }: { className?: string }) {
  return <div className={`skeleton ${className}`} aria-hidden />;
}

export function EmptyState({ title, text, action }: { title: string; text?: string; action?: ReactNode }) {
  return (
    <div className="card flex flex-col items-center gap-3 p-8 text-center">
      <div className="font-semibold">{title}</div>
      {text && <p className="max-w-md text-sm text-muted">{text}</p>}
      {action}
    </div>
  );
}

export function KeyValue({ rows }: { rows: [string, ReactNode, Tone?][] }) {
  return (
    <dl className="divide-y divide-border text-sm">
      {rows.map(([key, value, tone]) => (
        <div key={key} className="flex items-center justify-between gap-3 py-2">
          <dt className="text-muted">{key}</dt>
          <dd className={`num font-semibold ${tone ? textTone[tone] : ""}`}>{value}</dd>
        </div>
      ))}
    </dl>
  );
}
