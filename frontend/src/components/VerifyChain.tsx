"use client";

import { CheckCircle2, Loader2, ShieldCheck, XCircle } from "lucide-react";
import { useState } from "react";

type Row = { seq: number; body: string; hash: string };
type Result =
  | { state: "idle" }
  | { state: "running"; checked: number }
  | { state: "valid"; rows: number; head: string; matches: boolean | null }
  | { state: "broken"; at: number; reason: string }
  | { state: "error"; message: string };

const GENESIS = "0".repeat(64);
const hex = (buffer: ArrayBuffer) => [...new Uint8Array(buffer)].map((b) => b.toString(16).padStart(2, "0")).join("");

// Re-checks the ledger in the visitor's own browser, with the same rule as app/ledger.py verify():
// row n's body carries seq = n and prev = row n-1's hash, and its hash is SHA-256 of the body text exactly as stored.
// Nothing is trusted from the server except the raw rows; `publishedHead` is only compared at the end.
export default function VerifyChain({ publishedHead }: { publishedHead?: string }) {
  const [result, setResult] = useState<Result>({ state: "idle" });

  const run = async () => {
    if (!globalThis.crypto?.subtle) {
      setResult({ state: "error", message: "This browser blocks SHA-256 on insecure (http) pages. Open the site over https, or use the Python check below." });
      return;
    }
    setResult({ state: "running", checked: 0 });
    let prev = GENESIS, expected = 1, after = 0;
    try {
      for (;;) {
        const response = await fetch(`/ledger.json?after=${after}`, { cache: "no-store" });
        if (!response.ok) throw new Error(`ledger.json answered ${response.status}`);
        const rows = (await response.json()) as Row[];
        if (rows.length === 0) break;
        for (const row of rows) {
          const body = JSON.parse(row.body) as { seq?: number; prev?: string };
          const digest = hex(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(row.body)));
          const reason = row.seq !== expected || body.seq !== expected ? "row number out of order"
            : body.prev !== prev ? "does not point at the previous row's hash"
            : digest !== row.hash ? "hash does not match its body" : null;
          if (reason) { setResult({ state: "broken", at: expected, reason }); return; }
          prev = row.hash;
          expected += 1;
        }
        after = rows[rows.length - 1].seq;
        setResult({ state: "running", checked: expected - 1 });
      }
      setResult({ state: "valid", rows: expected - 1, head: prev, matches: publishedHead ? publishedHead === prev : null });
    } catch (error) {
      setResult({ state: "error", message: error instanceof Error ? error.message : String(error) });
    }
  };

  return (
    <div className="rounded-3xl border border-white/10 bg-surface p-6">
      <button type="button" onClick={run} disabled={result.state === "running"} className="inline-flex h-12 items-center gap-2.5 rounded-2xl bg-white px-6 font-semibold text-black hover:bg-white/90 disabled:opacity-60">
        {result.state === "running" ? <Loader2 size={18} className="animate-spin" /> : <ShieldCheck size={18} />}
        {result.state === "running" ? `Checking… ${result.checked} rows` : "Verify the whole chain now"}
      </button>
      <div className="mt-5 text-sm" aria-live="polite">
        {result.state === "idle" && <p className="text-muted">Downloads every ledger row and recomputes each hash in your browser. Nothing is sent back.</p>}
        {result.state === "valid" && (
          <div className="rounded-2xl border border-green/30 bg-green/[0.06] p-4">
            <p className="flex items-center gap-2 font-semibold text-green"><CheckCircle2 size={18} /> Chain intact: {result.rows} rows, every hash recomputed and linked.</p>
            <p className="mt-2 text-muted">Head hash you just computed:</p>
            <code className="mt-1 block break-all text-xs text-text">{result.head}</code>
            {result.matches === true && <p className="mt-2 text-green">Matches the head the site publishes.</p>}
            {result.matches === false && <p className="mt-2 text-gold">Differs from the head shown above — new rows may have arrived since the page loaded. Reload and check again.</p>}
            {result.rows === 0 && <p className="mt-2 text-muted">No rows yet: the chain starts at the genesis hash (64 zeros).</p>}
          </div>
        )}
        {result.state === "broken" && (
          <p className="flex items-center gap-2 rounded-2xl border border-red/30 bg-red/[0.06] p-4 font-semibold text-red"><XCircle size={18} /> Broken at row #{result.at}: {result.reason}.</p>
        )}
        {result.state === "error" && <p className="rounded-2xl border border-border bg-surface-2 p-4 text-muted">Could not finish the check: {result.message}</p>}
      </div>
    </div>
  );
}
