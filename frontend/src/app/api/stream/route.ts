import { connection } from "next/server";
import { API_URL } from "@/lib/api";

// Live broker quotes as Server-Sent Events, passed through unchanged from the private API (web/api.py /stream).
// The browser only talks to this site; the API stays unpublished. When the visitor leaves, the upstream request
// is aborted, so the API drops its listener too.
export async function GET(request: Request) {
  await connection();   // request-time only: never prerendered or cached
  const upstream = new AbortController();
  request.signal.addEventListener("abort", () => upstream.abort(), { once: true });
  let response: Response;
  try {
    response = await fetch(`${API_URL}/stream`, { cache: "no-store", signal: upstream.signal, headers: { Accept: "text/event-stream" } });
  } catch {
    return new Response("Live feed unavailable", { status: 503 });
  }
  if (!response.ok || !response.body) {
    upstream.abort();
    return new Response("Live feed unavailable", { status: 503 });
  }
  return new Response(response.body, {
    headers: {
      "Content-Type": "text/event-stream; charset=utf-8",
      // no-transform: Next's gzip (and any proxy) would otherwise buffer the stream.
      "Cache-Control": "no-cache, no-transform",
      "X-Accel-Buffering": "no",
    },
  });
}
