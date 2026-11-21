import Sidebar from "@/components/shell/Sidebar";
import { t, type Lang } from "@/lib/i18n";

// Rail + content column. The content is a 1100px centred column with 24px padding; pages render their own TopBar.
export default function AppShell({ lang, children }: { lang: Lang; children: React.ReactNode }) {
  const d = t(lang);
  return (
    <div className={`min-h-full ${lang === "km" ? "font-khmer" : ""}`}>
      <Sidebar lang={lang} labels={d.nav} />
      <div className="md:pl-16">
        <div className="mx-auto w-full max-w-[1100px] px-6 pb-10">
          {children}
          <p className="mt-12 border-t border-border pt-4 text-xs text-muted">{d.shell.disclaimer}</p>
        </div>
      </div>
    </div>
  );
}
