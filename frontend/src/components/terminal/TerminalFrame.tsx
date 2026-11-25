"use client";

import { Bell, Keyboard, Send, X } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useState, useSyncExternalStore } from "react";

type Labels = { keys: { search: string; list: string; view: string; help: string }; terminalName: string; shortDisclaimer: string; banner: string; link: string; dismiss: string };

// Full-screen workspace on desktop (fixed beside the 64 px rail): watchlist | status strip, header, chart, shortcut bar.
// On phones it falls back to the normal page flow and hides the watchlist and the shortcut bar.
// Keyboard: Ctrl/Cmd+K search, Ctrl/Cmd+B watchlist, Ctrl/Cmd+L Live/Broker view, ? shortcut list.
export default function TerminalFrame({ watchlist, strip, header, chart, panel, mobileMarkets, labels, telegram, otherViewHref, live, panelLeft = 12 }: {
  watchlist: React.ReactNode; strip: React.ReactNode; header: React.ReactNode; chart: React.ReactNode; panel: React.ReactNode; mobileMarkets: React.ReactNode;
  labels: Labels; telegram: string; otherViewHref: string; live: boolean; panelLeft?: number;
}) {
  const router = useRouter();
  const [list, setList] = useState(true);
  const [help, setHelp] = useState(false);
  const [banner, setBanner] = useState(true);
  // Platform never changes after load; the server snapshot assumes a Mac so the first paint shows ⌘.
  const mac = useSyncExternalStore(() => () => {}, () => /Mac|iPhone|iPad/.test(navigator.userAgent), () => true);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const typing = event.target instanceof HTMLElement && ["INPUT", "TEXTAREA"].includes(event.target.tagName);
      const mod = event.metaKey || event.ctrlKey;
      if (mod && event.key.toLowerCase() === "k") { event.preventDefault(); setList(true); setTimeout(() => document.getElementById("terminal-search")?.focus(), 0); }
      else if (mod && event.key.toLowerCase() === "b") { event.preventDefault(); setList((value) => !value); }
      else if (mod && event.key.toLowerCase() === "l") { event.preventDefault(); router.push(otherViewHref); }
      else if (!typing && event.key === "?") setHelp((value) => !value);
      else if (event.key === "Escape") setHelp(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [router, otherViewHref]);

  const mod = mac ? "⌘" : "Ctrl";
  const shortcuts: [string, string][] = [[`${mod} K`, labels.keys.search], [`${mod} B`, labels.keys.list], [`${mod} L`, labels.keys.view], ["?", labels.keys.help]];

  return (
    <div className="-mx-6 -mt-6 bg-bg lg:fixed lg:inset-y-0 lg:right-0 lg:left-16 lg:z-10 lg:m-0 lg:flex">
      {list && <aside className="hidden w-[300px] flex-none border-r border-border lg:block">{watchlist}</aside>}
      <section className="flex min-w-0 flex-1 flex-col lg:h-full">
        {strip}
        {banner && (
          <div className="flex items-center gap-3 border-b border-gold/20 bg-gold/[0.06] px-4 py-2.5 text-xs sm:text-sm">
            <Send size={16} className="flex-none text-gold" /><Bell size={16} className="hidden flex-none text-muted sm:block" />
            <span className="min-w-0 flex-1">{labels.banner}</span>
            <a href={telegram} className="rounded-lg bg-gold/20 px-3.5 py-1.5 text-sm font-semibold whitespace-nowrap text-gold hover:bg-gold/30">{labels.link}</a>
            <button type="button" onClick={() => setBanner(false)} className="text-muted hover:text-text" aria-label={labels.dismiss}><X size={16} /></button>
          </div>
        )}
        {header}
        <div className="lg:hidden">{mobileMarkets}</div>
        <div className="relative h-[520px] border-t border-border lg:h-auto lg:min-h-0 lg:flex-1">
          {chart}
          {/* panelLeft clears TradingView's drawing toolbar on the Live view */}
          <div className="absolute bottom-3 z-[2] hidden w-[420px] max-w-[calc(100%-5rem)] lg:block" style={{ left: panelLeft }}>{panel}</div>
        </div>
        <div className="p-3 lg:hidden">{panel}</div>
        <footer className="hidden h-10 flex-none items-center gap-2 border-t border-border px-3 text-xs text-muted lg:flex">
          {shortcuts.map(([key, label]) => (
            <button key={key} type="button" onClick={() => key === "?" && setHelp(true)} className="flex items-center gap-1.5 rounded-md px-1.5 py-1 hover:bg-surface hover:text-text">
              <kbd className="rounded-md border border-border bg-surface px-1.5 py-0.5 font-sans text-[11px] font-semibold text-text">{key}</kbd> {label}
            </button>
          ))}
          <span className="ml-auto truncate">{labels.shortDisclaimer}</span>
          <span className="flex items-center gap-1.5 border-l border-border pl-3"><span className={`dot ${live ? "bg-green" : "bg-muted"}`} /> {labels.terminalName}</span>
        </footer>
      </section>
      {help && (
        <div className="fixed inset-0 z-50 grid place-items-center bg-black/60 p-4" onClick={() => setHelp(false)}>
          <div className="card w-full max-w-sm p-5" onClick={(event) => event.stopPropagation()}>
            <div className="flex items-center justify-between">
              <span className="flex items-center gap-2 font-semibold"><Keyboard size={16} /> {labels.keys.help}</span>
              <button type="button" onClick={() => setHelp(false)} className="text-muted hover:text-text" aria-label="Close"><X size={16} /></button>
            </div>
            <ul className="mt-4 space-y-2 text-sm">
              {shortcuts.map(([key, label]) => (
                <li key={key} className="flex items-center justify-between"><span className="text-muted">{label}</span><kbd className="rounded border border-border bg-surface-2 px-2 py-0.5 text-xs">{key}</kbd></li>
              ))}
            </ul>
          </div>
        </div>
      )}
    </div>
  );
}
