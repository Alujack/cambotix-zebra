"use client";

import { useEffect, useState } from "react";

// Live "3h 50m" countdown to an epoch; shows the expired label once it passes. Renders "—" until hydrated.
export default function Countdown({ until, expired }: { until: number; expired: string }) {
  const [now, setNow] = useState<number | null>(null);
  useEffect(() => {
    const tick = () => setNow(Math.floor(Date.now() / 1000));
    tick();
    const id = setInterval(tick, 30000);
    return () => clearInterval(id);
  }, []);
  if (now === null) return <span className="num">—</span>;
  const left = until - now;
  if (left <= 0) return <span>{expired}</span>;
  const h = Math.floor(left / 3600);
  const m = Math.floor((left % 3600) / 60);
  return <span className="num">{h > 0 ? `${h}h ${m}m` : `${m}m`}</span>;
}
