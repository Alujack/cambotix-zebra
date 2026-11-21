import TopBar from "@/components/shell/TopBar";
import { EmptyState } from "@/components/ui";
import { isLang, t } from "@/lib/i18n";

// Placeholder until this screen is built; keeps the sidebar honest (no dead links).
export default async function Page({ params }: PageProps<"/[lang]/settings">) {
  const { lang } = await params;
  if (!isLang(lang)) return null;
  const d = t(lang);
  return (
    <>
      <TopBar lang={lang} title={d.nav.settings} help={d.shell.comingSoonText} />
      <EmptyState title={d.shell.comingSoon} text={d.shell.comingSoonText} />
    </>
  );
}
