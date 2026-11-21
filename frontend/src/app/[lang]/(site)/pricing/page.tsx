import type { Metadata } from "next";
import { Suspense } from "react";
import PlanCards from "@/components/PlanCards";
import { site } from "@/lib/site";
import { getRecord } from "@/lib/api";
import { isLang, t, type Lang } from "@/lib/i18n";

export const metadata: Metadata = { title: "Pricing", description: "Free public record now; live Telegram delivery opens when the forward test reads GO." };

async function Gate({ lang }: { lang: Lang }) {
  const d = t(lang);
  const h = (await getRecord()).headline;
  return (
    <p className="mt-4 rounded-xl border border-line bg-card p-4 text-sm text-muted">
      {d.pricing.gate1} <b className="text-fg">{d.verdict[h.verdict] ?? h.verdict}</b> — {h.closed} {d.pricing.gate2} {h.min_trades} {d.pricing.gate3}
      <b className="text-fg"> GO</b>: {d.pricing.gate4} {h.max_drawdown_limit_r}R. {d.pricing.gate5}
    </p>
  );
}

export default async function PricingPage({ params }: PageProps<"/[lang]/pricing">) {
  const { lang } = await params;
  if (!isLang(lang)) return null;
  const d = t(lang);
  const tiers = [d.pricing.free, d.pricing.pro];
  return (
    <>
      <section className="py-10">
        <h1 className="text-3xl font-semibold">{d.pricing.title}</h1>
        <p className="mt-2 max-w-2xl text-muted">{d.pricing.intro}</p>
        <Suspense fallback={null}>
          <Gate lang={lang} />
        </Suspense>
      </section>
      <PlanCards tiers={tiers} labels={d.pricing2} markets={site.markets.join(", ")} />
    </>
  );
}
