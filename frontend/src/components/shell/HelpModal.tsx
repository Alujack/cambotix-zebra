"use client";

import { HelpCircle, X } from "lucide-react";
import { useRef } from "react";

// "? How this page works": a native dialog with a short explainer.
// `compact` shows the icon only (the label becomes the accessible name).
export default function HelpModal({ title, text, label, close, compact = false, buttonClass = "pill hover:text-text" }: { title: string; text: string; label: string; close: string; compact?: boolean; buttonClass?: string }) {
  const ref = useRef<HTMLDialogElement>(null);
  return (
    <>
      <button type="button" onClick={() => ref.current?.showModal()} className={buttonClass} aria-haspopup="dialog" aria-label={compact ? label : undefined} title={compact ? label : undefined}>
        <HelpCircle size={13} /> {!compact && <span className="hidden sm:inline">{label}</span>}
      </button>
      <dialog ref={ref} className="m-auto w-[min(92vw,480px)] rounded-2xl border border-border bg-surface p-6 text-text backdrop:bg-black/70" onClick={(e) => e.target === ref.current && ref.current.close()}>
        <div className="flex items-start justify-between gap-3">
          <h2 className="text-lg font-semibold">{title}</h2>
          <button type="button" onClick={() => ref.current?.close()} className="btn-icon !h-8 !w-8" aria-label={close}><X size={14} /></button>
        </div>
        <p className="mt-3 text-sm leading-relaxed text-muted">{text}</p>
        <button type="button" onClick={() => ref.current?.close()} className="btn-secondary mt-5 w-full">{close}</button>
      </dialog>
    </>
  );
}
