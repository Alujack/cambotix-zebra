"use client";

import { useState } from "react";
import { contractSize } from "@/lib/site";

type Labels = { calc: string; account: string; riskPct: string; riskMoney: string; units: string; lots: string; rewardTp1: string; notional: string; calcNote: string };

// Arithmetic on the published levels: risk in money, units, lots, reward at TP1. Runs in the browser only.
export default function PositionSizer({ symbol, entry, stop, tp1, labels }: { symbol: string; entry: number; stop: number; tp1: number; labels: Labels }) {
  const [account, setAccount] = useState(1000);
  const [riskPct, setRiskPct] = useState(1);
  const risk = Math.abs(entry - stop);
  const money = (account * riskPct) / 100;
  const units = risk > 0 ? money / risk : 0;
  const contract = contractSize[symbol] ?? 1;
  const money2 = (value: number) => value.toLocaleString("en-US", { maximumFractionDigits: 2, minimumFractionDigits: 2 });
  return (
    <div className="card p-4">
      <div className="label">{labels.calc}</div>
      <div className="mt-3 grid gap-3 sm:grid-cols-2">
        <label className="text-sm">
          <span className="label">{labels.account} (USD)</span>
          <input type="number" min={1} value={account} onChange={(e) => setAccount(Number(e.target.value) || 0)}
                 className="mt-1 w-full rounded-lg border border-line bg-bg px-3 py-2 tabular-nums" />
        </label>
        <div className="text-sm">
          <span className="label">{labels.riskPct}</span>
          <div className="mt-1 flex gap-1.5">
            {[0.5, 1, 2, 3].map((value) => (
              <button key={value} type="button" onClick={() => setRiskPct(value)}
                      className={`flex-1 rounded-lg border px-2 py-2 text-sm ${riskPct === value ? "border-accent bg-accent text-black font-semibold" : "border-line bg-card"}`}>
                {value}%
              </button>
            ))}
          </div>
        </div>
      </div>
      <dl className="mt-4 grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
        <div><dt className="label">{labels.riskMoney}</dt><dd className="price text-loss">${money2(money)}</dd></div>
        <div><dt className="label">{labels.units}</dt><dd className="price">{units.toLocaleString("en-US", { maximumFractionDigits: 3 })}</dd></div>
        <div><dt className="label">{labels.lots}</dt><dd className="price">{(units / contract).toLocaleString("en-US", { maximumFractionDigits: 3 })}</dd></div>
        <div><dt className="label">{labels.rewardTp1}</dt><dd className="price text-win">${money2(units * Math.abs(tp1 - entry))}</dd></div>
      </dl>
      <p className="mt-3 text-xs text-muted">{labels.notional}: ${money2(units * entry)}. {labels.calcNote}</p>
    </div>
  );
}
