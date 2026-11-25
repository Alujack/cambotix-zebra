// Hero backdrop: flowing zebra stripes drawn in gold light on black. Pure SVG + CSS (no JS, no image request).
// Paths are deterministic so server and client render the same markup. Motion stops under prefers-reduced-motion.

const W = 1600, H = 900;

// One sinuous band per row; small per-row offsets keep it organic instead of a regular wave pattern.
const stripes = Array.from({ length: 15 }, (_, i) => {
  const y = -40 + i * 68;
  const a = ((i * 37) % 11) - 5, b = ((i * 53) % 13) - 6, c = ((i * 29) % 9) - 4;
  const d = `M -200 ${y + a * 6} C 200 ${y - 90 + b * 8}, 520 ${y + 140 + c * 10}, 860 ${y + 20 + a * 5} S 1380 ${y - 120 + b * 6}, 1820 ${y + 40 + c * 8}`;
  const width = 14 + ((i * 7) % 5) * 6;
  return { d, width, delay: (i % 5) * -3 };
});

export default function HeroBackdrop() {
  return (
    <div className="pointer-events-none absolute inset-0 overflow-hidden" aria-hidden>
      <svg className="hero-drift absolute -inset-[6%] h-[112%] w-[112%]" viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="xMidYMid slice">
        <defs>
          <linearGradient id="hero-gold" x1="0" x2="1" y1="0" y2="0">
            <stop offset="0" stopColor="#e8c964" stopOpacity="0" />
            <stop offset="0.35" stopColor="#e8c964" stopOpacity="0.9" />
            <stop offset="0.65" stopColor="#f6dc8a" stopOpacity="0.75" />
            <stop offset="1" stopColor="#e8c964" stopOpacity="0" />
          </linearGradient>
          <linearGradient id="hero-teal" x1="0" x2="1" y1="1" y2="0">
            <stop offset="0" stopColor="#34f08d" stopOpacity="0" />
            <stop offset="0.5" stopColor="#5ab0ff" stopOpacity="0.35" />
            <stop offset="1" stopColor="#34f08d" stopOpacity="0" />
          </linearGradient>
          <filter id="hero-glow" x="-10%" y="-10%" width="120%" height="120%">
            <feGaussianBlur stdDeviation="14" />
          </filter>
        </defs>
        {/* soft wide glow under every stripe */}
        <g filter="url(#hero-glow)" opacity="0.8">
          {stripes.map((s) => <path key={`g${s.d}`} d={s.d} fill="none" stroke="url(#hero-gold)" strokeWidth={s.width * 1.6} strokeLinecap="round" />)}
        </g>
        {/* the stripes: dark bands with lit edges, like a zebra pelt catching light */}
        <g>
          {stripes.map((s) => <path key={`b${s.d}`} d={s.d} fill="none" stroke="#060707" strokeWidth={s.width} strokeLinecap="round" opacity="0.85" />)}
        </g>
        <g>
          {stripes.map((s) => (
            <path key={`l${s.d}`} className="hero-shimmer" style={{ animationDelay: `${s.delay}s` }} d={s.d} fill="none" stroke="url(#hero-gold)" strokeWidth="1.4" strokeDasharray="420 900" />
          ))}
        </g>
        <g opacity="0.6">
          {stripes.filter((_, i) => i % 3 === 1).map((s) => <path key={`t${s.d}`} d={s.d} fill="none" stroke="url(#hero-teal)" strokeWidth="1" transform="translate(0 26)" />)}
        </g>
      </svg>
      {/* vignette: keeps the headline side dark and readable */}
      <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_75%_40%,transparent_0%,rgba(6,7,7,0.55)_55%,#060707_100%)]" />
      <div className="absolute inset-0 bg-gradient-to-r from-[#060707]/90 via-[#060707]/45 to-transparent" />
      <div className="absolute inset-x-0 bottom-0 h-40 bg-gradient-to-t from-[#060707] to-transparent" />
    </div>
  );
}
