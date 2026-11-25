import TopBar from "@/components/shell/TopBar";
import { KeyValue, SectionCard } from "@/components/ui";
import { guest } from "@/lib/guest";
import { href, t, type Lang } from "@/lib/i18n";
import { site } from "@/lib/site";

// Guest mode: there is nothing to save yet. TODO(accounts): preferences, Telegram link, plan.
export default async function SettingsPage() {
  const lang: Lang = "en";
  const d = t(lang);
  return (
    <>
      <TopBar lang={lang} title={d.nav.settings} help={d.settings.help} />
      <div className="grid gap-4 lg:grid-cols-2">
        <SectionCard label={d.settings.account}>
          <KeyValue rows={[[d.settings.account, d.settings.guest], [d.overview.plan, guest.plan], [d.settings.telegram, d.settings.notLinked]]} />
          <a href={site.telegram} className="btn-gold mt-4">{d.terminal.link}</a>
        </SectionCard>
        <SectionCard label={d.settings.theme}>
          <p className="text-sm text-muted">{d.settings.themeNote}</p>
        </SectionCard>
      </div>
      <p className="mt-4 text-xs text-muted">{href(lang, "/app/settings")} · {d.shell.guestNote}</p>
    </>
  );
}
