import { Sparkles } from "lucide-react";
import type { Plan } from "@/lib/api";

// "AI explains this plan": the local model's plain-language note, written from facts the code hands it.
// The plan note never contains prices (the model is not shown any), so it can be public while levels are hidden.
// Always labelled as commentary: the rules decided the plan and the grader decides the result.
export default function AiNote({ plan }: { plan: Plan }) {
  const ai = plan.ai;
  return (
    <section className="mt-6 rounded-2xl border border-[#a78bfa]/30 bg-gradient-to-br from-[#a78bfa]/[0.07] to-transparent p-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="flex items-center gap-2 font-semibold"><Sparkles size={17} className="text-[#c4b5fd]" /> AI explains this plan</h2>
        <span className="rounded-full border border-white/10 bg-white/[0.04] px-2.5 py-1 text-[11px] text-muted">Commentary only · the rules decide</span>
      </div>
      {ai?.plan ? (
        <p className="mt-3 text-[15px] leading-relaxed text-text/90">{ai.plan}</p>
      ) : (
        <p className="mt-3 text-sm text-muted">The explanation is written by the desk&apos;s AI shortly after a plan publishes. It isn&apos;t ready for this plan yet.</p>
      )}
      {ai?.result && (
        <div className="mt-4 border-t border-white/10 pt-4">
          <div className="label">After the close</div>
          <p className="mt-1.5 text-[15px] leading-relaxed text-text/90">{ai.result}</p>
        </div>
      )}
      {ai?.model && <p className="mt-3 text-xs text-muted">Written by {ai.model} from the plan&apos;s facts. It never sees prices before a plan closes, and numbers it makes up are rejected.</p>}
    </section>
  );
}

// One-line preview for signal cards.
export function AiPreview({ plan }: { plan: Plan }) {
  if (!plan.ai?.plan) return null;
  return (
    <p className="mt-3 flex gap-2 rounded-xl border border-[#a78bfa]/20 bg-[#a78bfa]/[0.05] px-3 py-2 text-xs leading-relaxed text-text/80">
      <Sparkles size={13} className="mt-0.5 flex-none text-[#c4b5fd]" />
      <span className="line-clamp-2">{plan.ai.plan}</span>
    </p>
  );
}
