import type { Metadata } from "next";

export const metadata: Metadata = { title: "Risk disclosure", description: "What the signals are, what they are not, and the risks of trading leveraged products." };

const sections: [string, string][] = [
  ["Education, not advice", "Every plan on this site and on Telegram is published analysis produced by fixed rules. It is not personal financial advice and does not take your goals, experience or finances into account."],
  ["Leveraged products can lose more than you expect", "Gold, forex and crypto CFDs are traded on margin. Small price moves create large gains or losses, and most retail accounts that trade CFDs lose money. Only trade money you can afford to lose."],
  ["Past results do not guarantee future results", "The track record shows how published plans played out on the broker's own candles, spread included. Your fills, spread, slippage and timing can differ, so your results can differ."],
  ["No orders are placed for you", "This system never connects to your account and never opens a trade. Every decision to trade, and its size, is yours."],
  ["How results are recorded", "Plans are written to an append-only, hash-chained ledger the moment they publish. Wins, losses and plans that never filled all stay on the record; nothing is removed."],
];

export default function RiskPage() {
  return (
    <article className="mx-auto max-w-3xl py-14">
      <span className="inline-block rounded-full border border-white/12 bg-white/[0.03] px-3.5 py-1.5 text-[11px] font-semibold tracking-[0.2em] text-gold uppercase">Legal</span>
      <h1 className="font-display mt-4 text-4xl font-bold tracking-tight">Risk disclosure</h1>
      <p className="mt-4 text-muted">Read this before acting on any plan.</p>
      <div className="mt-10 space-y-8">
        {sections.map(([title, text]) => (
          <section key={title}>
            <h2 className="text-lg font-semibold">{title}</h2>
            <p className="mt-2 leading-relaxed text-muted">{text}</p>
          </section>
        ))}
      </div>
    </article>
  );
}
