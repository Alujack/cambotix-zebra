import { FileJson, Fingerprint, Link2, ShieldCheck } from "lucide-react";
import type { Metadata } from "next";
import { Suspense } from "react";
import VerifyChain from "@/components/VerifyChain";
import { getRecord } from "@/lib/api";

export const metadata: Metadata = {
  title: "Verify the record",
  description: "Every plan and result is a row in a SHA-256 hash chain. Check the whole chain yourself, in your browser or with ten lines of Python.",
};

const steps: [typeof Fingerprint, string, string][] = [
  [Fingerprint, "Each row is hashed", "A plan, a fill, a target or a stop becomes one row of canonical JSON. Its SHA-256 hash is stored next to it."],
  [Link2, "Each row points back", "The JSON includes the previous row's hash. Change any old row and every hash after it changes."],
  [ShieldCheck, "The head is published daily", "The newest hash goes out on Telegram every morning. A rewritten history no longer matches what was posted."],
];

const python = `import hashlib, json, urllib.request

prev, n, after = "0" * 64, 1, 0
while rows := json.load(urllib.request.urlopen(f"https://<site>/ledger.json?after={after}")):
    for row in rows:
        body = json.loads(row["body"])
        assert row["seq"] == body["seq"] == n and body["prev"] == prev, f"broken at {n}"
        assert hashlib.sha256(row["body"].encode()).hexdigest() == row["hash"], f"bad hash at {n}"
        prev, n = row["hash"], n + 1
    after = rows[-1]["seq"]
print("chain intact:", n - 1, "rows, head", prev)`;

async function Head() {
  const record = await getRecord();
  const chain = record.chain;
  return (
    <>
      <div className="grid gap-3 sm:grid-cols-3">
        <div className="rounded-2xl border border-border bg-surface p-5">
          <div className="label">Status</div>
          <div className={`mt-2 text-2xl font-bold ${chain.valid ? "text-green" : "text-red"}`}>{chain.valid ? "Intact" : `Broken at #${chain.broken_at}`}</div>
        </div>
        <div className="rounded-2xl border border-border bg-surface p-5">
          <div className="label">Rows</div>
          <div className="num mt-2 text-2xl font-bold">{chain.rows}</div>
        </div>
        <div className="rounded-2xl border border-border bg-surface p-5">
          <div className="label">Head</div>
          <div className="num mt-2 text-2xl font-bold">#{chain.head_seq ?? 0}</div>
        </div>
      </div>
      <div className="mt-3 rounded-2xl border border-border bg-surface p-5">
        <div className="label">Head hash, as the site publishes it</div>
        <code className="mt-2 block break-all text-sm">{chain.head_hash ?? "0".repeat(64)}</code>
      </div>
      <div className="mt-6">
        <VerifyChain publishedHead={chain.head_hash} />
      </div>
    </>
  );
}

export default function VerifyPage() {
  return (
    <div className="mx-auto max-w-4xl py-14">
      <span className="inline-flex items-center gap-2 rounded-full border border-white/12 bg-white/[0.03] px-3.5 py-1.5 text-[11px] font-semibold tracking-[0.2em] text-gold uppercase"><ShieldCheck size={13} /> Proof</span>
      <h1 className="font-display mt-4 text-4xl font-bold tracking-tight">Verify the record yourself</h1>
      <p className="mt-4 max-w-2xl text-muted">
        Every published plan and every result is a row in an append-only, hash-chained ledger. You don&apos;t have to trust us: download the rows and recompute the chain.
      </p>

      <ol className="mt-10 grid gap-3 md:grid-cols-3">
        {steps.map(([Icon, title, text]) => (
          <li key={title} className="rounded-2xl border border-border bg-surface p-5">
            <span className="grid h-10 w-10 place-items-center rounded-xl border border-gold/30 bg-gold/10 text-gold"><Icon size={18} /></span>
            <div className="mt-4 font-semibold">{title}</div>
            <p className="mt-1.5 text-sm leading-relaxed text-muted">{text}</p>
          </li>
        ))}
      </ol>

      <section className="mt-12">
        <h2 className="text-2xl font-bold tracking-tight">Check it in your browser</h2>
        <div className="mt-5">
          <Suspense fallback={<div className="skeleton h-64" />}>
            <Head />
          </Suspense>
        </div>
      </section>

      <section className="mt-12">
        <h2 className="text-2xl font-bold tracking-tight">Or check it with Python</h2>
        <p className="mt-2 text-muted">The same rule, outside our website. Replace <code className="rounded bg-surface-2 px-1">&lt;site&gt;</code> with this site&apos;s address.</p>
        <pre className="mt-4 overflow-x-auto rounded-2xl border border-border bg-[#0b0c0f] p-5 text-[13px] leading-relaxed"><code>{python}</code></pre>
        <a href="/ledger.json" className="mt-4 inline-flex items-center gap-2 text-sm font-semibold text-gold hover:underline"><FileJson size={16} /> Open the raw ledger (JSON)</a>
      </section>
    </div>
  );
}
