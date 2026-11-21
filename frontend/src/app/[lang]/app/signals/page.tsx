import type { Metadata } from "next";
import TopBar from "@/components/shell/TopBar";
import { Suspense } from "react";
import SignalCard from "@/components/SignalCard";
import { getSignals, getTickers } from "@/lib/api";
import { isLang, t, type Lang } from "@/lib/i18n";

export const metadata: Metadata = { title: "Signals", description: "Every published plan, open and closed, with its graded outcome." };

async function Cards({ lang }: { lang: Lang }) {
  const d = t(lang);
  const [plans, tickers] = await Promise.all([getSignals(60), getTickers()]);
  const quote = (symbol: string) => tickers.find((item) => item.symbol === symbol);
  if (plans.length === 0) {
    return <div className="rounded-xl border border-dashed border-line p-8 text-center text-muted">{d.signals.empty}</div>;
  }
  const open = plans.filter((plan) => plan.status === "open");
  const done = plans.filter((plan) => plan.status !== "open");
  return (
    <>
      {open.length > 0 && (
        <section>
          <h2 className="mb-3 text-sm uppercase tracking-wide text-muted">{d.signals.open} · {open.length}</h2>
          <div className="grid gap-4 md:grid-cols-2">{open.map((plan) => <SignalCard key={plan.event_id} plan={plan} lang={lang} ticker={quote(plan.symbol)} />)}</div>
        </section>
      )}
      <section className={open.length ? "mt-10" : ""}>
        <h2 className="mb-3 text-sm uppercase tracking-wide text-muted">{d.signals.graded} {done.length}</h2>
        <div className="grid gap-4 md:grid-cols-2">{done.map((plan) => <SignalCard key={plan.event_id} plan={plan} lang={lang} />)}</div>
      </section>
    </>
  );
}

export default async function SignalsPage({ params }: PageProps<"/[lang]/app/signals">) {
  const { lang } = await params;
  if (!isLang(lang)) return null;
  const d = t(lang);
  return (
    <>
      <TopBar lang={lang} title={d.signals.title} help={d.signals.intro} />
      <p className="mb-5 max-w-2xl text-sm text-muted">{d.signals.intro}</p>
      <Suspense fallback={<div className="grid gap-4 md:grid-cols-2">{Array.from({ length: 4 }).map((_, i) => <div key={i} className="h-40 animate-pulse rounded-xl border border-line bg-card" />)}</div>}>
        <Cards lang={lang} />
      </Suspense>
    </>
  );
}
