import { connection } from "next/server";
import { API_URL } from "@/lib/api";

// Older candles for a chart scrolling back in time: /api/candles?symbol=XAUUSD&tf=15m&to=<unix>&bars=1500, passed
// through from the private API (web/api.py /candles). The browser only talks to this site; the API stays unpublished.
const TFS = new Set(["1m", "5m", "15m", "30m", "1h", "4h", "1d", "1M"]);

export async function GET(request: Request) {
  await connection();   // request-time only: never prerendered or cached
  const query = new URL(request.url).searchParams;
  const symbol = (query.get("symbol") ?? "").toUpperCase();
  const tf = query.get("tf") ?? "";
  const to = Number(query.get("to"));
  const bars = Math.min(5000, Math.max(20, Number(query.get("bars")) || 1000));
  if (!/^[A-Z0-9]{3,20}$/.test(symbol) || !TFS.has(tf) || !Number.isInteger(to) || to <= 0) {
    return Response.json({ error: "symbol, tf and to are required" }, { status: 400 });
  }
  try {
    const response = await fetch(`${API_URL}/candles/${symbol}?tf=${encodeURIComponent(tf)}&to=${to}&bars=${bars}`, { cache: "no-store" });
    return new Response(await response.text(), { status: response.status, headers: { "Content-Type": "application/json" } });
  } catch {
    return Response.json({ error: "API unavailable" }, { status: 503 });
  }
}
