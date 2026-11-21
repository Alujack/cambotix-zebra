"use client";

import { Check } from "lucide-react";
import { useState } from "react";

type Tier = { name: string; price: string; items: string[]; cta: string };
type Labels = { monthly: string; yearly: string; popular: string; perMonth: string; limits: string; signalsDay: string; markets: string; delivery: string };

// Pricing cards with a Monthly / Yearly toggle; the popular card wears a gold border. Nothing here is for sale yet.
export default function PlanCards({ tiers, labels, markets }: { tiers: Tier[]; labels: Labels; markets: string }) {
  const [yearly, setYearly] = useState(false);
  const limits = [
    [labels.signalsDay, "All graded, delayed", "All, live"],
    [labels.markets, markets, markets],
    [labels.delivery, "Website · daily record", "Telegram DM · result message"],
  ];
  return (
    <>
      <div className="mb-4 flex justify-center">
        <div className="inline-flex rounded-full border border-border bg-surface p-0.5">
          {[[false, labels.monthly], [true, labels.yearly]].map(([value, label]) => (
            <button key={String(label)} type="button" onClick={() => setYearly(Boolean(value))} className={`rounded-full px-4 py-1.5 text-sm ${yearly === value ? "bg-surface-2 text-text" : "text-muted"}`}>{String(label)}</button>
          ))}
        </div>
      </div>
      <div className="flex snap-x gap-4 overflow-x-auto pb-2 md:grid md:grid-cols-2 md:overflow-visible">
        {tiers.map((tier, index) => (
          <div key={tier.name} className={`card-lg relative min-w-[85%] snap-center p-6 md:min-w-0 ${index === 1 ? "border-gold/60" : ""}`}>
            {index === 1 && <span className="badge absolute -top-3 left-5 border-gold/50 bg-bg text-gold">{labels.popular}</span>}
            <div className="label">{tier.name}</div>
            <div className="mt-1 text-3xl font-bold">{tier.price}{tier.price.startsWith("$") && <span className="text-sm font-normal text-muted"> {yearly ? "/ year" : labels.perMonth}</span>}</div>
            <div className="mt-5 label">{labels.limits}</div>
            <dl className="mt-1 divide-y divide-border text-sm">
              {limits.map(([key, free, pro]) => <div key={key} className="flex justify-between gap-3 py-1.5"><dt className="text-muted">{key}</dt><dd className="text-right">{index === 0 ? free : pro}</dd></div>)}
            </dl>
            <ul className="mt-4 space-y-2 text-sm">{tier.items.map((item) => <li key={item} className="flex gap-2"><span className="grid h-5 w-5 shrink-0 place-items-center rounded-full bg-green/15 text-green"><Check size={12} /></span>{item}</li>)}</ul>
            <div className={`mt-6 ${index === 1 ? "btn-gold" : "btn-secondary"} w-full`}>{tier.cta}</div>
          </div>
        ))}
      </div>
    </>
  );
}
