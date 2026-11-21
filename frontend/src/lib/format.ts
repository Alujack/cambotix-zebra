export const utc = (epoch: number, withTime = true) => {
  const date = new Date(epoch * 1000);
  const day = date.toISOString().slice(0, 10);
  return withTime ? `${day} ${date.toISOString().slice(11, 16)} UTC` : day;
};

export const price = (value: number) => value.toLocaleString("en-US", {
  minimumFractionDigits: value >= 100 ? 2 : 5,
  maximumFractionDigits: value >= 100 ? 2 : 5,
});

export const percent = (value: number | null | undefined) =>
  value === null || value === undefined ? "n/a" : `${Math.round(value * 100)}%`;

export const r = (value: number | null | undefined, digits = 2) =>
  value === null || value === undefined ? "—" : `${value > 0 ? "+" : ""}${value.toFixed(digits)}R`;

export const modelName: { [key: string]: string } = {
  classic: "Classic trend",
  smc: "SMC / ICT",
  ict: "ICT",
  crt: "CRT",
  ema: "EMA scalp",
  mss: "MSS",
};

export const exitLabel: { [key: string]: string } = {
  sl: "Stop loss",
  be: "Break-even",
  timeout: "Time limit",
  final_target: "Final target",
  tp1: "TP1",
  tp2: "TP2",
  tp3: "TP3",
  tp4: "TP4",
  filled: "Filled",
  not_filled: "Not filled",
  closed: "Closed",
};
