import type { Metadata } from "next";
import { Suspense } from "react";
import SignalCard from "@/components/SignalCard";
import { getSignals } from "@/lib/api";
import { isLang, t, type Lang } from "@/lib/i18n";

export const metadata: Metadata = { title: "Signals", description: "Every published plan, open and closed, with its graded outcome." };

async function Cards({ lang }: { lang: Lang }) {
  const d = t(lang);
  const plans = await getSignals(60);
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
          <div className="grid gap-4 md:grid-cols-2">{open.map((plan) => <SignalCard key={plan.event_id} plan={plan} lang={lang} />)}</div>
        </section>
      )}
      <section className={open.length ? "mt-10" : ""}>
        <h2 className="mb-3 text-sm uppercase tracking-wide text-muted">{d.signals.graded} {done.length}</h2>
        <div className="grid gap-4 md:grid-cols-2">{done.map((plan) => <SignalCard key={plan.event_id} plan={plan} lang={lang} />)}</div>
      </section>
    </>
  );
}

export default async function SignalsPage({ params }: PageProps<"/[lang]/signals">) {
  const { lang } = await params;
  if (!isLang(lang)) return null;
  const d = t(lang);
  return (
    <>
      <section className="py-10">
        <h1 className="text-3xl font-semibold">{d.signals.title}</h1>
        <p className="mt-2 max-w-2xl text-muted">{d.signals.intro}</p>
      </section>
      <Suspense fallback={<div className="grid gap-4 md:grid-cols-2">{Array.from({ length: 4 }).map((_, i) => <div key={i} className="h-40 animate-pulse rounded-xl border border-line bg-card" />)}</div>}>
        <Cards lang={lang} />
      </Suspense>
    </>
  );
}
