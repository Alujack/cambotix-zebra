import { t, type Lang } from "@/lib/i18n";

export default function Footer({ lang, headHash, headSeq }: { lang: Lang; headHash?: string; headSeq?: number }) {
  const d = t(lang);
  return (
    <footer className="mt-16 border-t border-line">
      <div className="mx-auto max-w-6xl space-y-3 px-4 py-8 text-xs text-muted">
        {headHash && (
          <p>
            {d.footer.head} #{headSeq}: <code className="break-all">{headHash}</code>
          </p>
        )}
        <p>{d.footer.disclaimer}</p>
        <p>{d.footer.copyright}</p>
      </div>
    </footer>
  );
}
