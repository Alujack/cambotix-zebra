export default function Footer({ headHash, headSeq }: { headHash?: string; headSeq?: number }) {
  return (
    <footer className="mt-16 border-t border-line">
      <div className="mx-auto max-w-6xl space-y-3 px-4 py-8 text-xs text-muted">
        {headHash && (
          <p>
            Ledger chain head #{headSeq}: <code className="break-all">{headHash}</code>
          </p>
        )}
        <p>
          Signals are published analysis for education, graded on broker candles after the fact. Not financial advice.
          Trading leveraged products carries a high risk of loss. No order is ever placed by this system.
        </p>
        <p>© {new Date().getFullYear()} Cambotix Solutions · Zebra. Nothing in the record is ever removed.</p>
      </div>
    </footer>
  );
}
