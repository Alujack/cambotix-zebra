"use client";

import { useEffect, useState } from "react";

// "mm:ss" until the next 15-minute candle close (UTC), the moment the rules run again. Renders "--:--" until hydrated.
export default function NextClose() {
  const [left, setLeft] = useState<number | null>(null);
  useEffect(() => {
    const tick = () => setLeft(900 - (Math.floor(Date.now() / 1000) % 900));
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, []);
  if (left === null) return <span className="num">--:--</span>;
  return <span className="num">{String(Math.floor(left / 60)).padStart(2, "0")}:{String(left % 60).padStart(2, "0")}</span>;
}
