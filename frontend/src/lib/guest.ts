// Guest mode: there are no accounts yet. Everything user-specific on the shell and the Overview comes from here.
// TODO(accounts): replace with the signed-in user once Telegram login exists (post-GO phase).

export const guest = {
  name: "Guest",
  initials: "G",
  plan: "Free",
  signalsLeftToday: 1,
  resetsAt: "00:00 UTC",
  telegramLinked: false,
};

export const greeting = (hour: number) => (hour < 12 ? "Good morning" : hour < 18 ? "Good afternoon" : "Good evening");
