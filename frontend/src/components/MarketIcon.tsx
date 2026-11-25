import { useId } from "react";

// Standard market icons, the way trading platforms show them: a gold-bar coin for XAU, the orange ₿ mark for
// Bitcoin, and two overlapping country flags for a forex pair (base top-left, quote bottom-right).
// Plain inline SVG: no image requests, crisp at every size. Flags are simplified to read at 20-48 px.

type FlagProps = { cx: number; cy: number; r: number; clip: string };

const EU = ({ cx, cy, r, clip }: FlagProps) => (
  <g clipPath={`url(#${clip})`}>
    <circle cx={cx} cy={cy} r={r} fill="#003399" />
    {Array.from({ length: 12 }, (_, i) => {
      const a = (i / 12) * Math.PI * 2;
      return <circle key={i} cx={cx + Math.cos(a) * r * 0.58} cy={cy + Math.sin(a) * r * 0.58} r={r * 0.09} fill="#ffcc00" />;
    })}
  </g>
);

const US = ({ cx, cy, r, clip }: FlagProps) => {
  const top = cy - r, h = (2 * r) / 7;
  return (
    <g clipPath={`url(#${clip})`}>
      <circle cx={cx} cy={cy} r={r} fill="#ffffff" />
      {[0, 2, 4, 6].map((i) => <rect key={i} x={cx - r} y={top + i * h} width={2 * r} height={h} fill="#b22234" />)}
      <rect x={cx - r} y={top} width={r * 1.05} height={h * 4} fill="#3c3b6e" />
      {[[0.3, 0.45], [0.62, 0.45], [0.46, 0.85], [0.3, 1.25], [0.62, 1.25]].map(([x, y], i) => <circle key={i} cx={cx - r + x * r} cy={top + y * h} r={r * 0.06} fill="#ffffff" />)}
    </g>
  );
};

const GB = ({ cx, cy, r, clip }: FlagProps) => (
  <g clipPath={`url(#${clip})`}>
    <circle cx={cx} cy={cy} r={r} fill="#012169" />
    <path d={`M${cx - r} ${cy - r}L${cx + r} ${cy + r}M${cx + r} ${cy - r}L${cx - r} ${cy + r}`} stroke="#ffffff" strokeWidth={r * 0.36} />
    <path d={`M${cx - r} ${cy - r}L${cx + r} ${cy + r}M${cx + r} ${cy - r}L${cx - r} ${cy + r}`} stroke="#c8102e" strokeWidth={r * 0.12} />
    <path d={`M${cx} ${cy - r}V${cy + r}M${cx - r} ${cy}H${cx + r}`} stroke="#ffffff" strokeWidth={r * 0.56} />
    <path d={`M${cx} ${cy - r}V${cy + r}M${cx - r} ${cy}H${cx + r}`} stroke="#c8102e" strokeWidth={r * 0.32} />
  </g>
);

const FLAGS: { [currency: string]: (props: FlagProps) => React.ReactElement } = { EUR: EU, USD: US, GBP: GB };

function Gold({ id }: { id: string }) {
  return (
    <svg viewBox="0 0 48 48" width="100%" height="100%" aria-hidden>
      <defs>
        <linearGradient id={`${id}-coin`} x1="0" x2="0" y1="0" y2="1"><stop offset="0" stopColor="#5a4616" /><stop offset="1" stopColor="#2a200b" /></linearGradient>
        <linearGradient id={`${id}-bar`} x1="0" x2="0" y1="0" y2="1"><stop offset="0" stopColor="#ffe49a" /><stop offset="0.55" stopColor="#e8b93a" /><stop offset="1" stopColor="#b8861b" /></linearGradient>
      </defs>
      <circle cx="24" cy="24" r="24" fill={`url(#${id}-coin)`} />
      <circle cx="24" cy="24" r="22.5" fill="none" stroke="#e8c964" strokeOpacity="0.45" />
      {/* three stacked bullion bars, scaled up around the coin centre */}
      <g transform="translate(24 27) scale(1.3) translate(-24 -27)">
      <path d="M12.5 33.5 L15 27.5 H22.5 L25 33.5 Z" fill={`url(#${id}-bar)`} />
      <path d="M23 33.5 L25.5 27.5 H33 L35.5 33.5 Z" fill={`url(#${id}-bar)`} />
      <path d="M17.8 26.5 L20.3 20.5 H27.7 L30.2 26.5 Z" fill={`url(#${id}-bar)`} />
      <path d="M15.4 28.3 H22.1 M25.9 28.3 H32.6 M20.7 21.3 H27.3" stroke="#fff6d5" strokeOpacity="0.8" strokeWidth="0.9" />
      </g>
    </svg>
  );
}

function Bitcoin() {
  return (
    <svg viewBox="0 0 48 48" width="100%" height="100%" aria-hidden>
      <circle cx="24" cy="24" r="24" fill="#f7931a" />
      {/* the ₿ mark, tilted like the original logo */}
      <g transform="rotate(14 24 24)" fill="none" stroke="#ffffff" strokeWidth="3.2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M18.5 13.5 H26.2 a4.6 4.6 0 0 1 0 9.2 H19.8" />
        <path d="M19.8 22.7 H27.2 a5 5 0 0 1 0 10 H18.5" />
        <path d="M19.8 13.5 V32.7" />
        <path d="M21.6 10.2 V13.5 M25.8 10.2 V13.5 M21.6 32.7 V36 M25.8 32.7 V36" strokeWidth="2.6" />
      </g>
    </svg>
  );
}

function Pair({ base, quote, id }: { base: string; quote: string; id: string }) {
  const Base = FLAGS[base], Quote = FLAGS[quote];
  if (!Base || !Quote) return null;
  return (
    <svg viewBox="0 0 48 48" width="100%" height="100%" aria-hidden>
      <defs>
        <clipPath id={`${id}-a`}><circle cx="17" cy="17" r="15" /></clipPath>
        <clipPath id={`${id}-b`}><circle cx="31" cy="31" r="15" /></clipPath>
      </defs>
      <Base cx={17} cy={17} r={15} clip={`${id}-a`} />
      <circle cx="31" cy="31" r="16.5" fill="#060707" />
      <Quote cx={31} cy={31} r={15} clip={`${id}-b`} />
    </svg>
  );
}

export default function MarketIcon({ symbol, size = 36 }: { symbol: string; size?: number }) {
  const id = useId().replace(/[^a-zA-Z0-9-]/g, "");
  const s = symbol.toUpperCase();
  let art: React.ReactNode = null;
  if (s.startsWith("XAU")) art = <Gold id={id} />;
  else if (s.startsWith("BTC")) art = <Bitcoin />;
  else if (/^[A-Z]{6}$/.test(s)) art = <Pair base={s.slice(0, 3)} quote={s.slice(3)} id={id} />;
  return (
    <span className="grid flex-none place-items-center overflow-hidden rounded-full" style={{ width: size, height: size }} title={symbol}>
      {art ?? <span className="grid h-full w-full place-items-center rounded-full bg-surface-2 text-[11px] font-bold text-muted">{s.slice(0, 3)}</span>}
    </span>
  );
}
