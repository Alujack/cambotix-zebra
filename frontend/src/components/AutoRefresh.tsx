"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

// Re-fetches the page's server data on an interval so live candles and tickers appear without a manual reload.
// Skips hidden tabs and refreshes once when the tab becomes visible again. The api caches answers for 60 s.
export default function AutoRefresh({ seconds = 60 }: { seconds?: number }) {
  const router = useRouter();
  useEffect(() => {
    const tick = () => { if (document.visibilityState === "visible") router.refresh(); };
    const timer = window.setInterval(tick, seconds * 1000);
    document.addEventListener("visibilitychange", tick);
    return () => { window.clearInterval(timer); document.removeEventListener("visibilitychange", tick); };
  }, [router, seconds]);
  return null;
}
