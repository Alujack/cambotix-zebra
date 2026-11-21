// Brand and people. Edit here; nothing else needs to change.

export const site = {
  name: "Zebra Empire",
  shortName: "Zebra",
  tagline: "by Cambotix Solutions",
  telegram: process.env.NEXT_PUBLIC_TELEGRAM_URL ?? "#",
  markets: ["XAUUSD", "EURUSD", "BTCUSD"],
};

export type Member = { name: string; role: string; blurb?: string; links?: { label: string; href: string }[] };

// Placeholder until real names, photos and follower counts are supplied.
export const team: Member[] = [
  { name: "Cambotix desk", role: "Founder · rules and models", blurb: "Designs the detection rules and reviews every published plan by hand." },
  { name: "Zebra engine", role: "Grader · ledger", blurb: "Replays broker candles and writes the append-only, hash-chained record." },
];
