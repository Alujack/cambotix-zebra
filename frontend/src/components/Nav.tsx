import Link from "next/link";

const links = [
  { href: "/", label: "Home" },
  { href: "/signals", label: "Signals" },
  { href: "/track-record", label: "Track record" },
  { href: "/pricing", label: "Pricing" },
];

export default function Nav() {
  return (
    <header className="sticky top-0 z-20 border-b border-line bg-bg/90 backdrop-blur">
      <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-4 py-3">
        <Link href="/" className="flex items-center gap-2 font-semibold tracking-tight">
          <span className="grid h-8 w-8 place-items-center rounded-lg bg-accent text-bg">Z</span>
          <span>Zebra</span>
          <span className="hidden text-muted sm:inline">by Cambotix</span>
        </Link>
        <nav className="flex items-center gap-1 text-sm">
          {links.map((link) => (
            <Link key={link.href} href={link.href} className="rounded-md px-3 py-1.5 text-muted hover:bg-card hover:text-fg">
              {link.label}
            </Link>
          ))}
          <a
            href={process.env.NEXT_PUBLIC_TELEGRAM_URL ?? "#telegram"}
            className="ml-2 hidden rounded-md bg-accent px-3 py-1.5 font-medium text-bg hover:opacity-90 sm:inline"
          >
            Daily record on Telegram
          </a>
        </nav>
      </div>
    </header>
  );
}
