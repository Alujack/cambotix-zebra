import { Send } from "lucide-react";

// Floating "join the Telegram" button, bottom right on every marketing page.
export default function JoinTelegram({ href, title, sub }: { href: string; title: string; sub: string }) {
  return (
    <a href={href} aria-label={title} className="fixed right-4 bottom-4 z-30 flex items-center gap-3 rounded-full border border-[#2aabee]/40 bg-[#0b141c]/90 p-2 sm:pr-5 shadow-[0_0_40px_-10px_rgba(42,171,238,0.6)] backdrop-blur transition-transform hover:-translate-y-0.5 sm:right-6 sm:bottom-6">
      <span className="grid h-10 w-10 place-items-center rounded-full bg-[#2aabee] text-white"><Send size={18} className="-translate-x-px translate-y-px" /></span>
      <span className="hidden leading-tight sm:block">
        <span className="block text-sm font-semibold">{title}</span>
        <span className="block text-[10px] font-semibold tracking-[0.14em] text-[#7cc8f0] uppercase">{sub}</span>
      </span>
    </a>
  );
}
