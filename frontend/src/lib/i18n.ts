// Two languages, one dictionary. English lives at the clean URL, Khmer under /km (see src/proxy.ts).

export const languages = ["en", "km"] as const;
export type Lang = (typeof languages)[number];

export const isLang = (value: string): value is Lang => (languages as readonly string[]).includes(value);

export const href = (lang: Lang, path: string) => (lang === "en" ? path : `/km${path === "/" ? "" : path}` || "/km");

const en = {
  nav: { home: "Home", signals: "Signals", record: "Track record", pricing: "Pricing", method: "Method", telegram: "Daily record on Telegram", other: "ខ្មែរ",
    overview: "Overview", terminal: "Terminal", chart: "Chart", indicators: "Indicators", trades: "My Trades", alerts: "Alerts", more: "More",
    aiChat: "AI Chat", backtest: "Backtest", refer: "Refer", upgrade: "Upgrade", settings: "Settings", support: "Support", soon: "soon" },
  shell: {
    help: "How this page works", close: "Close", scan: "Scan now", scanTodo: "On-demand scans are not available yet; setups are detected on each 15-minute close.",
    disclaimer: "Signals are for educational purposes only. Not financial advice. Trading involves risk.",
    comingSoon: "Not built yet", comingSoonText: "This screen needs an account. It will open once Telegram sign-in exists.", guestNote: "Guest mode — nothing here is saved.",
  },
  ticker: { empty: "Broker prices appear here once the feeder is sending candles.", source: "broker feed · ~1 min delay" },
  hero: {
    kicker: "Rule-based desk · broker-graded · nothing deleted",
    title: "Trade gold with a plan you can verify.",
    text: "Every setup is published with its entry, stop and targets, then graded on the broker's own candles. Wins and losses stay on the record forever — the chain hash proves it.",
    cta1: "See the track record", cta2: "Latest signals",
  },
  tiles: {
    closed: "Closed trades", open: "open", neverFilled: "never filled", winRate: "Win rate", winHint: "wins ÷ closed, TP1 basis",
    total: "Total result", expectancy: "expectancy", perTrade: "per trade", drawdown: "Max drawdown", limit: "limit",
    verdict: "Forward test", needs: "needs", closedTrades: "closed trades", evaluated: "Setups evaluated", rejected: "rejected by the rules",
    published: "Published plans", publishedHint: "every one is on the ledger", chain: "Ledger chain", chainOk: "verified on every page load",
    chainBroken: "altered at row", broken: "BROKEN", wins: "wins", scaleOut: "scale-out", profitFactor: "profit factor",
    ambiguous: "Ambiguous candles", ambiguousHint: "worst outcome counted", verdictHint: "trades, positive expectancy, drawdown within limit",
    chainValid: "valid", rows: "rows", head: "head",
  },
  verdict: { GO: "GO", "NO-GO": "NO-GO", "NOT ENOUGH DATA": "NOT ENOUGH DATA" } as { [key: string]: string },
  how: {
    title: "How a signal is made",
    steps: [
      ["Detect", "Rule-based models scan the broker's own 15m candles: classic trend, SMC / ICT structure, CRT, MSS and an EMA scalp."],
      ["Gate", "Every rule is re-checked server-side: session, volatility, structure, news window, one open plan per side."],
      ["Publish", "The plan — entry, stop, TP1-TP4, 1R — is frozen into an append-only ledger and sent to Telegram."],
      ["Grade", "A grader replays the broker's 1-minute candles, spread included, and records fill, targets, stop or time-out."],
      ["Prove", "Every row carries the previous row's hash. The chain head is posted daily, so history cannot be rewritten."],
    ],
  },
  models: {
    title: "Models on the desk",
    items: [
      ["Classic trend", "EMA20/50/200 stack, RSI band, MACD sign, ADX strength, ATR band, London / New York sessions."],
      ["SMC / ICT", "Liquidity sweep → market structure shift with displacement → fair value gap → confirmed retest, inside ICT killzones."],
      ["CRT · MSS · EMA scalp", "Candle range theory at key times, structure-shift swings, and a short EMA pullback scalp — each graded on its own line."],
    ],
    note: "Markets: XAUUSD (gold), EURUSD, BTCUSD. Timeframe: 15 minutes. The AI writes commentary only; it never decides.",
  },
  why: {
    title: "Why this record can't be edited",
    items: [
      ["Append-only database.", "Triggers refuse any update, delete or truncate on the ledger and on the candles it was graded with."],
      ["Hash chain.", "Each row includes the previous row's SHA-256. Change one old result and every later hash changes."],
      ["Daily public head.", "The chain head is posted to Telegram every morning. Compare it with the one in the footer."],
    ],
  },
  team: { title: "The desk", text: "Small team, public record. Every plan is reviewed by a person before it goes out; nothing is traded automatically." },
  cta: { title: "Follow the daily record", text: "Results, the forward-test verdict and the chain hash, every morning Phnom Penh time.", button: "Open Telegram" },
  signals: {
    title: "Signals",
    intro: "Every plan the rules approved, newest first. Levels of open plans go out live on Telegram and are shown here once the plan closes — together with what happened to it.",
    empty: "No plan has been published yet. The first one appears here the moment the rules approve it.",
    open: "Open", graded: "Graded · latest",
  },
  card: {
    open: "OPEN · being graded", notFilled: "NOT FILLED", ambiguous: "ambiguous, worst case",
    hidden: "Entry, stop and targets are delivered live on Telegram. They appear here once the plan closes, with its result.",
    entry: "Entry", stop: "Stop", tp1: "TP1", target: "Target", published: "Published", ledger: "Ledger",
    limit: "Resting order", market: "Market entry", intraday: "Intraday", view: "View details", graded: "Graded", more: "more",
  },
  detail: {
    back: "All signals", summary: "Summary", direction: "Direction", model: "Model", session: "Session", order: "Order type",
    rr: "R / R to TP1", risk: "1R", status: "Status", levels: "Trade levels", fromEntry: "from entry", result: "Result",
    timeline: "What happened", cautions: "Quality warnings", noCautions: "No warnings on this plan.",
    openNote: "This plan is still open. Its levels went out live on Telegram and will appear here, with the outcome, when it closes.",
    calc: "Position size", account: "Account size", riskPct: "Risk per trade", riskMoney: "Risk", units: "Units", lots: "Lots",
    rewardTp1: "Reward at TP1", notional: "Notional at entry", calcNote: "Arithmetic on the published levels. Not advice; check your broker's contract size.",
    notFilledWhy: "Never filled", closedAt: "Closed", tp1Basis: "TP1 basis", scaleOut: "scale-out",
  },
  record: {
    title: "Track record",
    intro: "All-time, every published plan, graded on broker candles including spread. No daily reset, no exclusions, no edits.",
    month: "Month", market: "Market", model: "Model", session: "Side · session", cautions: "Cautions", neverFilled: "Never filled", none: "None",
    closed: "Closed", wins: "Wins", winRate: "Win rate", totalR: "Total R", scaleOutR: "Scale-out R", noClosed: "No closed trades yet",
    everyPlan: "Every plan", latestOf: "Latest", of: "of", levelsLater: "Levels of open plans are shown after they close.",
    cols: ["#", "Published (UTC)", "Market", "Side", "Model", "Entry", "Stop", "TP1", "⚠", "Result", "R (TP1)", "R (scale-out)"],
    noPlans: "No published plans yet", openWord: "open", notFilledWord: "not filled",
    ambiguousNote: "* a candle where the order of hits was unknown; the worse outcome is counted.",
    checkTitle: "Check it yourself",
    checkText: "Download the raw chain at /ledger.json and recompute it: each row's hash is the SHA-256 of its body, and each body names the previous hash. The head today is",
    checkMatch: "It must match the head posted in the daily Telegram record. If it ever doesn't, the record was altered.",
  },
  pricing: {
    title: "Pricing",
    intro: "Watch the record for free. Live delivery is paid, and only once the record proves it is worth paying for.",
    gate1: "Forward test today:", gate2: "of", gate3: "required closed trades. Pro opens only when this reads",
    gate4: "enough trades, positive expectancy and drawdown within", gate5: "We will not sell signals before the record earns it.",
    free: { name: "Free", price: "$0", items: ["Every graded signal with its result", "Full track record and raw ledger", "Daily record with the chain hash on Telegram", "Method notes in Khmer and English"], cta: "Available now" },
    pro: { name: "Pro", price: "opens after GO", items: ["Live Telegram DMs: entry, stop, TP1-TP4 as they publish", "Cautions and history warnings on every plan", "Result message when each plan closes", "Pay with Bakong or USDT"], cta: "Not for sale yet" },
  },
  method: { title: "Method", intro: "The ideas behind the rules, in plain words. The Khmer edition is a complete beginner's book.", images: "Diagrams are being redrawn and will appear here soon." },
  footer: {
    head: "Ledger chain head",
    disclaimer: "Signals are published analysis for education, graded on broker candles after the fact. Not financial advice. Trading leveraged products carries a high risk of loss. No order is ever placed by this system.",
    copyright: "© 2026 Cambotix Solutions · Zebra Empire. Nothing in the record is ever removed.",
  },
  exits: { sl: "Stop loss", be: "Break-even", timeout: "Time limit", final_target: "Final target", tp1: "TP1", tp2: "TP2", tp3: "TP3", tp4: "TP4", filled: "Filled", not_filled: "Not filled", closed: "Closed" } as { [key: string]: string },
};

export type Dict = typeof en;

const km: Dict = {
  nav: { home: "ទំព័រដើម", signals: "សញ្ញា", record: "កំណត់ត្រាលទ្ធផល", pricing: "តម្លៃ", method: "វិធីសាស្ត្រ", telegram: "របាយការណ៍ប្រចាំថ្ងៃលើ Telegram", other: "English",
    overview: "ទិដ្ឋភាពរួម", terminal: "Terminal", chart: "ក្រាហ្វ", indicators: "សូចនាករ", trades: "Trade របស់ខ្ញុំ", alerts: "ការជូនដំណឹង", more: "ផ្សេងទៀត",
    aiChat: "AI Chat", backtest: "Backtest", refer: "ណែនាំមិត្ត", upgrade: "ដំឡើង", settings: "ការកំណត់", support: "ជំនួយ", soon: "ឆាប់ៗ" },
  shell: {
    help: "ទំព័រនេះដំណើរការយ៉ាងណា", close: "បិទ", scan: "ស្កេនឥឡូវ", scanTodo: "ការស្កេនតាមតម្រូវការមិនទាន់មានទេ; setup ត្រូវរកឃើញរាល់ពេលបិទ candle 15 នាទី។",
    disclaimer: "សញ្ញាគឺសម្រាប់ការសិក្សាតែប៉ុណ្ណោះ។ មិនមែនជាការណែនាំហិរញ្ញវត្ថុទេ។ ការជួញដូរមានហានិភ័យ។",
    comingSoon: "មិនទាន់បានបង្កើត", comingSoonText: "អេក្រង់នេះត្រូវការគណនី។ វានឹងបើកនៅពេលមានការចូលតាម Telegram។", guestNote: "របៀបភ្ញៀវ — គ្មានអ្វីត្រូវរក្សាទុកទេ។",
  },
  ticker: { empty: "តម្លៃពី broker នឹងបង្ហាញនៅទីនេះ នៅពេល feeder ផ្ញើ candle មក។", source: "ទិន្នន័យ broker · យឺត ~1 នាទី" },
  hero: {
    kicker: "ផ្អែកលើច្បាប់ · ដាក់ពិន្ទុតាម candle របស់ broker · មិនលុបអ្វីទាំងអស់",
    title: "Trade មាស ដោយមានផែនការដែលអ្នកអាចផ្ទៀងផ្ទាត់បាន។",
    text: "គ្រប់ setup ត្រូវបានផ្សព្វផ្សាយជាមួយ entry, stop និង target រួចដាក់ពិន្ទុតាម candle របស់ broker ផ្ទាល់។ ឈ្នះក៏ដោយ ចាញ់ក៏ដោយ នៅក្នុងកំណត់ត្រាជារៀងរហូត — hash chain ជាភស្តុតាង។",
    cta1: "មើលកំណត់ត្រាលទ្ធផល", cta2: "សញ្ញាចុងក្រោយ",
  },
  tiles: {
    closed: "ការជួញដូរបានបិទ", open: "កំពុងបើក", neverFilled: "មិនបានចូល", winRate: "អត្រាឈ្នះ", winHint: "ឈ្នះ ÷ បានបិទ (គិតតាម TP1)",
    total: "លទ្ធផលសរុប", expectancy: "មធ្យម", perTrade: "ក្នុងមួយ trade", drawdown: "ការធ្លាក់ចុះអតិបរមា", limit: "កំណត់",
    verdict: "ការសាកល្បង", needs: "ត្រូវការ", closedTrades: "trade បានបិទ", evaluated: "Setup បានពិនិត្យ", rejected: "ត្រូវច្បាប់បដិសេធ",
    published: "ផែនការបានផ្សាយ", publishedHint: "ទាំងអស់នៅក្នុង ledger", chain: "Ledger chain", chainOk: "ផ្ទៀងផ្ទាត់រាល់ពេលបើកទំព័រ",
    chainBroken: "ត្រូវបានកែនៅជួរ", broken: "ខូច", wins: "ឈ្នះ", scaleOut: "scale-out", profitFactor: "profit factor",
    ambiguous: "Candle មិនច្បាស់", ambiguousHint: "គិតលទ្ធផលអាក្រក់ជាង", verdictHint: "trade, មធ្យមវិជ្ជមាន, ការធ្លាក់ចុះក្នុងកំណត់",
    chainValid: "ត្រឹមត្រូវ", rows: "ជួរ", head: "ក្បាល",
  },
  verdict: { GO: "ឆ្លង (GO)", "NO-GO": "មិនឆ្លង (NO-GO)", "NOT ENOUGH DATA": "ទិន្នន័យមិនទាន់គ្រប់" },
  how: {
    title: "សញ្ញាមួយកើតឡើងយ៉ាងដូចម្តេច",
    steps: [
      ["រកឃើញ", "ម៉ូដែលផ្អែកលើច្បាប់ស្កេន candle 15 នាទីរបស់ broker៖ classic trend, SMC / ICT structure, CRT, MSS និង EMA scalp។"],
      ["ពិនិត្យ", "គ្រប់ច្បាប់ត្រូវពិនិត្យម្តងទៀតនៅ server៖ session, volatility, structure, ពេលព័ត៌មាន, ផែនការបើកតែមួយក្នុងមួយទិស។"],
      ["ផ្សាយ", "ផែនការ — entry, stop, TP1-TP4, 1R — ត្រូវបានចាក់សោក្នុង ledger ដែលបន្ថែមបានតែប៉ុណ្ណោះ រួចផ្ញើទៅ Telegram។"],
      ["ដាក់ពិន្ទុ", "Grader ចាក់ candle 1 នាទីរបស់ broker ឡើងវិញ រួមទាំង spread រួចកត់ត្រាការចូល, target, stop ឬអស់ពេល។"],
      ["បញ្ជាក់", "គ្រប់ជួរមាន hash របស់ជួរមុន។ ក្បាល chain ត្រូវផ្សាយរាល់ថ្ងៃ ដូច្នេះប្រវត្តិមិនអាចសរសេរឡើងវិញបានទេ។"],
    ],
  },
  models: {
    title: "ម៉ូដែលនៅលើតុ",
    items: [
      ["Classic trend", "EMA20/50/200 ជាលំដាប់, RSI ក្នុងជួរ, សញ្ញា MACD, កម្លាំង ADX, ជួរ ATR, session London / New York។"],
      ["SMC / ICT", "Liquidity sweep → market structure shift ជាមួយ displacement → fair value gap → retest បញ្ជាក់ ក្នុង ICT killzone។"],
      ["CRT · MSS · EMA scalp", "Candle range theory នៅម៉ោងសំខាន់, swing បំបែក structure និង EMA pullback scalp ខ្លី — នីមួយៗដាក់ពិន្ទុដោយឡែក។"],
    ],
    note: "ទីផ្សារ៖ XAUUSD (មាស), EURUSD, BTCUSD។ Timeframe៖ 15 នាទី។ AI សរសេរតែមតិ; វាមិនដែលសម្រេចទេ។",
  },
  why: {
    title: "ហេតុអ្វីកំណត់ត្រានេះកែមិនបាន",
    items: [
      ["មូលដ្ឋានទិន្នន័យបន្ថែមបានតែប៉ុណ្ណោះ។", "Trigger បដិសេធការកែ លុប ឬសម្អាតលើ ledger និងលើ candle ដែលបានប្រើដាក់ពិន្ទុ។"],
      ["Hash chain។", "គ្រប់ជួរមាន SHA-256 របស់ជួរមុន។ កែលទ្ធផលចាស់មួយ hash ក្រោយៗទាំងអស់ប្រែប្រួល។"],
      ["ក្បាល chain ផ្សាយរាល់ថ្ងៃ។", "ក្បាល chain ត្រូវផ្ញើទៅ Telegram រាល់ព្រឹក។ ប្រៀបធៀបជាមួយអ្វីដែលនៅបាតទំព័រ។"],
    ],
  },
  team: { title: "ក្រុមការងារ", text: "ក្រុមតូច កំណត់ត្រាសាធារណៈ។ គ្រប់ផែនការត្រូវមនុស្សពិនិត្យមុនផ្ញើចេញ; គ្មានអ្វី trade ដោយស្វ័យប្រវត្តិទេ។" },
  cta: { title: "តាមដានរបាយការណ៍ប្រចាំថ្ងៃ", text: "លទ្ធផល, លទ្ធផលការសាកល្បង និង hash របស់ chain រាល់ព្រឹកម៉ោងភ្នំពេញ។", button: "បើក Telegram" },
  signals: {
    title: "សញ្ញា",
    intro: "គ្រប់ផែនការដែលច្បាប់បានអនុម័ត ថ្មីបំផុតមុន។ កម្រិតតម្លៃនៃផែនការកំពុងបើក ត្រូវផ្ញើផ្ទាល់តាម Telegram ហើយបង្ហាញនៅទីនេះនៅពេលផែនការបិទ — ជាមួយលទ្ធផលរបស់វា។",
    empty: "មិនទាន់មានផែនការផ្សាយទេ។ ផែនការដំបូងនឹងបង្ហាញភ្លាមនៅពេលច្បាប់អនុម័ត។",
    open: "កំពុងបើក", graded: "បានដាក់ពិន្ទុ · ចុងក្រោយ",
  },
  card: {
    open: "កំពុងបើក · កំពុងដាក់ពិន្ទុ", notFilled: "មិនបានចូល", ambiguous: "candle មិនច្បាស់ គិតករណីអាក្រក់",
    hidden: "Entry, stop និង target ត្រូវផ្ញើផ្ទាល់តាម Telegram។ វានឹងបង្ហាញនៅទីនេះនៅពេលផែនការបិទ ជាមួយលទ្ធផល។",
    entry: "Entry", stop: "Stop", tp1: "TP1", target: "Target", published: "ផ្សាយ", ledger: "Ledger",
    limit: "Order រង់ចាំ", market: "ចូលតាមទីផ្សារ", intraday: "Intraday", view: "មើលលម្អិត", graded: "បានដាក់ពិន្ទុ", more: "ទៀត",
  },
  detail: {
    back: "សញ្ញាទាំងអស់", summary: "សង្ខេប", direction: "ទិស", model: "ម៉ូដែល", session: "Session", order: "ប្រភេទ order",
    rr: "R / R ដល់ TP1", risk: "1R", status: "ស្ថានភាព", levels: "កម្រិតតម្លៃ", fromEntry: "ពី entry", result: "លទ្ធផល",
    timeline: "អ្វីបានកើតឡើង", cautions: "ការព្រមានគុណភាព", noCautions: "គ្មានការព្រមានលើផែនការនេះ។",
    openNote: "ផែនការនេះនៅបើក។ កម្រិតតម្លៃបានផ្ញើផ្ទាល់តាម Telegram ហើយនឹងបង្ហាញនៅទីនេះ ជាមួយលទ្ធផល នៅពេលបិទ។",
    calc: "ទំហំ position", account: "ទំហំគណនី", riskPct: "ហានិភ័យក្នុងមួយ trade", riskMoney: "ហានិភ័យ", units: "ឯកតា", lots: "Lot",
    rewardTp1: "ចំណេញនៅ TP1", notional: "តម្លៃសរុបនៅ entry", calcNote: "គណនាពីកម្រិតតម្លៃដែលបានផ្សាយ។ មិនមែនការណែនាំទេ; ពិនិត្យ contract size របស់ broker អ្នក។",
    notFilledWhy: "មិនបានចូល", closedAt: "បានបិទ", tp1Basis: "គិតតាម TP1", scaleOut: "scale-out",
  },
  record: {
    title: "កំណត់ត្រាលទ្ធផល",
    intro: "គ្រប់ពេលវេលា គ្រប់ផែនការដែលបានផ្សាយ ដាក់ពិន្ទុតាម candle របស់ broker រួមទាំង spread។ គ្មានការកំណត់ឡើងវិញ គ្មានការដកចេញ គ្មានការកែ។",
    month: "ខែ", market: "ទីផ្សារ", model: "ម៉ូដែល", session: "ទិស · session", cautions: "ការប្រុងប្រយ័ត្ន", neverFilled: "មិនបានចូល", none: "គ្មាន",
    closed: "បានបិទ", wins: "ឈ្នះ", winRate: "អត្រាឈ្នះ", totalR: "R សរុប", scaleOutR: "R scale-out", noClosed: "មិនទាន់មាន trade បានបិទ",
    everyPlan: "គ្រប់ផែនការ", latestOf: "ចុងក្រោយ", of: "ក្នុងចំណោម", levelsLater: "កម្រិតតម្លៃនៃផែនការកំពុងបើក បង្ហាញក្រោយពេលបិទ។",
    cols: ["#", "ផ្សាយ (UTC)", "ទីផ្សារ", "ទិស", "ម៉ូដែល", "Entry", "Stop", "TP1", "⚠", "លទ្ធផល", "R (TP1)", "R (scale-out)"],
    noPlans: "មិនទាន់មានផែនការផ្សាយ", openWord: "កំពុងបើក", notFilledWord: "មិនបានចូល",
    ambiguousNote: "* candle ដែលមិនដឹងលំដាប់នៃការប៉ះ; គិតលទ្ធផលអាក្រក់ជាង។",
    checkTitle: "ផ្ទៀងផ្ទាត់ដោយខ្លួនឯង",
    checkText: "ទាញយក chain ដើមនៅ /ledger.json រួចគណនាឡើងវិញ៖ hash របស់ជួរនីមួយៗគឺ SHA-256 នៃ body របស់វា ហើយ body នីមួយៗបញ្ជាក់ hash មុន។ ក្បាលថ្ងៃនេះគឺ",
    checkMatch: "វាត្រូវតែដូចក្បាលដែលផ្សាយក្នុងរបាយការណ៍ Telegram ប្រចាំថ្ងៃ។ បើមិនដូច មានន័យថាកំណត់ត្រាត្រូវបានកែ។",
  },
  pricing: {
    title: "តម្លៃ",
    intro: "មើលកំណត់ត្រាដោយឥតគិតថ្លៃ។ ការផ្ញើផ្ទាល់គឺបង់ប្រាក់ ហើយតែនៅពេលកំណត់ត្រាបង្ហាញថាសមនឹងបង់ប៉ុណ្ណោះ។",
    gate1: "ការសាកល្បងថ្ងៃនេះ៖", gate2: "ក្នុងចំណោម", gate3: "trade បានបិទដែលត្រូវការ។ Pro បើកតែនៅពេលនេះអាន",
    gate4: "trade គ្រប់, មធ្យមវិជ្ជមាន និងការធ្លាក់ចុះក្នុង", gate5: "យើងនឹងមិនលក់សញ្ញាមុនកំណត់ត្រាសមនឹងវាទេ។",
    free: { name: "ឥតគិតថ្លៃ", price: "$0", items: ["គ្រប់សញ្ញាដែលបានដាក់ពិន្ទុ ជាមួយលទ្ធផល", "កំណត់ត្រាពេញលេញ និង ledger ដើម", "របាយការណ៍ប្រចាំថ្ងៃជាមួយ hash chain លើ Telegram", "កំណត់ចំណាំវិធីសាស្ត្រ ខ្មែរ និងអង់គ្លេស"], cta: "មានឥឡូវនេះ" },
    pro: { name: "Pro", price: "បើកក្រោយ GO", items: ["Telegram DM ផ្ទាល់៖ entry, stop, TP1-TP4 ពេលផ្សាយ", "ការប្រុងប្រយ័ត្ន និងការព្រមានពីប្រវត្តិ លើគ្រប់ផែនការ", "សារលទ្ធផលពេលផែនការនីមួយៗបិទ", "បង់តាម Bakong ឬ USDT"], cta: "មិនទាន់លក់ទេ" },
  },
  method: { title: "វិធីសាស្ត្រ", intro: "សៀវភៅ ICT សម្រាប់អ្នកចាប់ផ្តើមពីសូន្យ — គំនិតនៅពីក្រោយច្បាប់ ពន្យល់ដោយពាក្យសាមញ្ញ។", images: "រូបភាពកំពុងគូរឡើងវិញ ហើយនឹងបង្ហាញនៅទីនេះឆាប់ៗ។" },
  footer: {
    head: "ក្បាល ledger chain",
    disclaimer: "សញ្ញាគឺជាការវិភាគសម្រាប់ការសិក្សា ដាក់ពិន្ទុតាម candle របស់ broker ក្រោយពេលកើតឡើង។ មិនមែនជាការណែនាំហិរញ្ញវត្ថុទេ។ ការជួញដូរផលិតផល leverage មានហានិភ័យខ្ពស់នៃការខាតបង់។ ប្រព័ន្ធនេះមិនដែលដាក់ order ទេ។",
    copyright: "© 2026 Cambotix Solutions · Zebra Empire។ គ្មានអ្វីក្នុងកំណត់ត្រាត្រូវបានដកចេញឡើយ។",
  },
  exits: { sl: "ប៉ះ stop loss", be: "ត្រឡប់មក entry (break-even)", timeout: "អស់ពេល", final_target: "target ចុងក្រោយ", tp1: "TP1", tp2: "TP2", tp3: "TP3", tp4: "TP4", filled: "បានចូល", not_filled: "មិនបានចូល", closed: "បានបិទ" },
};

export const dict: { [key in Lang]: Dict } = { en, km };
export const t = (lang: Lang): Dict => dict[lang];
