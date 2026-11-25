import { Zap } from "lucide-react";
import HelpModal from "@/components/shell/HelpModal";
import { t, type Lang } from "@/lib/i18n";

// Sticky 56px bar: page title left; help, language and the primary action right.
export default function TopBar({ lang, title, help, action }: { lang: Lang; title: string; help: string; action?: React.ReactNode }) {
  const d = t(lang);
  return (
    <header className="sticky top-0 z-10 -mx-6 mb-6 flex h-14 items-center justify-between border-b border-border bg-bg/90 px-6 pl-16 backdrop-blur md:pl-6">
      <h1 className="page-title truncate">{title}</h1>
      <div className="flex items-center gap-2">
        <HelpModal title={title} text={help} label={d.shell.help} close={d.shell.close} />
        {action ?? (
          <button type="button" className="btn-primary !min-h-9 !py-1.5" disabled title={d.shell.scanTodo}>
            <Zap size={16} /> <span className="hidden sm:inline">{d.shell.scan}</span>
          </button>
        )}
      </div>
    </header>
  );
}
