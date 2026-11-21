import { readFileSync } from "node:fs";
import path from "node:path";
import type { Metadata } from "next";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { isLang, t } from "@/lib/i18n";

export const metadata: Metadata = { title: "Method", description: "The ideas behind the rules: liquidity, sweeps, structure shifts, fair value gaps, sessions and risk." };

// The Khmer edition is the beginner's book from docs/; the English one is a short summary. Both ship with the image.
const content = (lang: string) => readFileSync(path.join(process.cwd(), "content", `method.${lang}.md`), "utf8");

export default async function MethodPage({ params }: PageProps<"/[lang]/method">) {
  const { lang } = await params;
  if (!isLang(lang)) return null;
  const d = t(lang);
  const markdown = content(lang).replace(/^<!--[\s\S]*?-->\n/, "");
  return (
    <>
      <section className="py-10">
        <h1 className="text-3xl font-semibold">{d.method.title}</h1>
        <p className="mt-2 max-w-2xl text-muted">{d.method.intro}</p>
        {lang === "km" && <p className="mt-2 text-xs text-muted">{d.method.images}</p>}
      </section>
      <article className="prose-zebra max-w-3xl">
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{markdown}</ReactMarkdown>
      </article>
    </>
  );
}
