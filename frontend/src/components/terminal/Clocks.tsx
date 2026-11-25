"use client";

import { useEffect, useState } from "react";

// Client clocks for the Terminal. Server components may not read the clock (react-hooks/purity), and the
// values have to keep moving between the 60 s data refreshes anyway.
export function useNow(everyMs: number) {
  const [now, setNow] = useState<number | null>(null);
  useEffect(() => {
    const tick = () => setNow(Date.now() / 1000);
    tick();
    const id = setInterval(tick, everyMs);
    return () => clearInterval(id);
  }, [everyMs]);
  return now;
}

const span = (seconds: number) => {
  const d = Math.floor(seconds / 86400), h = Math.floor((seconds % 86400) / 3600), m = Math.floor((seconds % 3600) / 60);
  return d > 0 ? `${d}d ${h}h` : h > 0 ? `${h}h ${m}m` : `${m}m`;
};

// FX and metals: open Sunday 22:00 UTC to Friday 21:00 UTC. Approximate on purpose: DST and broker breaks are ignored.
export function fxSession(now: number): { open: boolean; next: number } {
  const date = new Date(now * 1000);
  const weekStart = Date.UTC(date.getUTCFullYear(), date.getUTCMonth(), date.getUTCDate() - date.getUTCDay()) / 1000; // Sunday 00:00
  const opens = weekStart + 22 * 3600;
  const closes = weekStart + 5 * 86400 + 21 * 3600;
  if (now < opens) return { open: false, next: opens };
  if (now < closes) return { open: true, next: closes };
  return { open: false, next: opens + 7 * 86400 };
}

type ClockLabels = { open: string; closed: string; closesIn: string; opensIn: string; always: string };

export function MarketClock({ hours, labels }: { hours: "fx" | "always"; labels: ClockLabels }) {
  const now = useNow(30000);
  const box = "inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1 text-sm font-semibold whitespace-nowrap";
  const green = `${box} border-green/40 bg-green/[0.08] text-green`;
  if (hours === "always") return <span className={green}><span className="dot bg-green" /> {labels.open} <span className="font-normal opacity-80">· {labels.always}</span></span>;
  if (now === null) return <span className={`${box} border-border text-muted`}>—</span>;
  const session = fxSession(now);
  return session.open
    ? <span className={green}><span className="dot bg-green" /> {labels.open} <span className="font-normal opacity-80">· {labels.closesIn} {span(session.next - now)}</span></span>
    : <span className={`${box} border-red/40 bg-red/[0.08] text-red`}><span className="dot bg-red" /> {labels.closed} <span className="font-normal opacity-80">· {labels.opensIn} {span(session.next - now)}</span></span>;
}

// "12 s" / "4m" since an epoch, refreshed every second.
export function Ago({ since, suffix }: { since: number; suffix: string }) {
  const now = useNow(1000);
  if (now === null) return null;
  const age = Math.max(0, Math.floor(now - since));
  return <span className="num text-sm text-muted">{age < 60 ? `${age} s` : span(age)}{suffix && ` ${suffix}`}</span>;
}

// "6h 15m" until an epoch, refreshed every 30 s; hides itself once the time has passed.
export function Until({ at }: { at: number }) {
  const now = useNow(30000);
  if (now === null || at <= now) return null;
  return <span className="num">{span(at - now)}</span>;
}
