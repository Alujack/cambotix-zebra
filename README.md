# Cambotix Zebra

Local XAUUSD 15-minute signal analysis using TradingView, n8n, PostgreSQL, and Ollama. Telegram delivery is optional. This implements the V1 manual-review MVP: **no broker connection, paper fills, or live orders**.

```text
TradingView Pine alert (or scripts/mt5_feeder.py → analyzer /signals directly)
  → HTTPS tunnel (configure your endpoint)
  → restricted webhook gateway :8787
  → n8n intake workflow :5680
  → analyzer: validate, normalize, atomically save to PostgreSQL
  ← HTTP 202 after commit (duplicates: HTTP 200)

n8n schedule every 15 seconds
  → claim a saved signal
  → technical rules and session checks (these decide: GATE_MODE=rules)
  → Ollama JSON commentary
  → PostgreSQL journal; an approved plan is appended to the ledger

scripts/mt5_feeder.py every minute
  → broker M1 candles with spread → analyzer /candles

n8n grader schedule every minute
  → grade every open plan on stored candles → append fills, targets, stops, closes to the ledger
  → daily record with the ledger chain hash

n8n notification schedule
  → PostgreSQL outboxes (signals, results, daily record) → Telegram when explicitly enabled
```

## Start locally

Requires Docker with Compose and Python 3.12 or newer. No Python packages need to be installed on the host.

```bash
bash scripts/start.sh
```

This generates `.env` secrets, starts isolated project containers, imports and publishes three n8n workflows, and downloads `qwen2.5:1.5b`. On macOS it installs checksum-verified native Ollama under `.local/ollama`, using Apple Silicon acceleration and loopback port 11435. Other platforms use the Docker Ollama profile and a persistent volume. First start downloads images and about 1 GB of model weights. The small model is a functional starting point; its analysis quality has not been established for trading.

Open **http://localhost:5680** and create your local n8n owner account. Existing n8n installations on ports 5678/5679 are unaffected. This editor stays on loopback. Local HTTP uses `N8N_SECURE_COOKIE=false`; do not expose the editor directly to the Internet.

```bash
python3 scripts/status.py
python3 scripts/history.py
bash scripts/test.sh
python3 scripts/smoke.py
bash scripts/check-ai.sh
python3 scripts/demo.py BTCUSD        # synthetic classic BUY+SELL through rules, AI and Telegram; IDs start with DEMO-SYNTHETIC
python3 scripts/demo.py XAUUSD crt    # same for the Candle Range Theory model
docker compose logs --tail=100 analyzer n8n
docker compose stop
docker compose start
```

On macOS, native Ollama is a separate background process; its log and PID are in `.local/ollama/server.log` and `.local/ollama/server.pid`. Ollama also creates its standard identity key under `~/.ollama`. It does not automatically start at login. Run `bash scripts/start.sh` after a reboot. `docker compose stop` stops the containers only; to stop this project's native model server, run `kill "$(cat .local/ollama/server.pid)"` after verifying that PID still belongs to this Ollama process.

The smoke test sends a clearly labeled weak-trend sample through the gateway and n8n, verifies deduplication and validation errors, and waits for a scheduled rejection. It requires Telegram disabled. `scripts/demo.py` is the opposite: it sends one coherent synthetic BUY and one SELL setup that pass every rule, so they are approved with the local model's commentary (or judged by it with `GATE_MODE=ai`), and it will message Telegram if enabled; event IDs begin with `DEMO-SYNTHETIC`. Synthetic IDs (`DEMO-SYNTHETIC`, `smoke-`, `synthetic-`) are journaled but never added to the graded ledger. Tests use the separate `zebra_tests` database and mocked AI; the main journal is preserved.

The stack uses named volumes. `docker compose down` preserves them. **`docker compose down -v` deletes the database, workflows, and Docker model weights.** Native macOS model files in `.local/ollama` are separate. Back up `.env` with the volumes: the encryption key is required to decrypt n8n credentials. Deleting volumes also requires removing `.local/workflows-installed` before the next start.

## Windows laptop as a server

The stack runs unchanged on Windows through WSL2; every pinned image is multi-arch (amd64 and arm64).

1. Install WSL2 with Ubuntu and Docker Desktop with the WSL2 backend. In Docker Desktop enable *Start Docker Desktop when you sign in* and, under Resources, WSL integration, enable the Ubuntu distro.
2. Clone this repository **inside the WSL filesystem** (for example `~/cambotix-zebra`), not under `/mnt/c`: bind mounts are faster there and `.env` keeps its 0600 mode. Run `bash scripts/start.sh` from the Ubuntu shell exactly as on macOS.
3. Choose the model runtime in `.env` before the first start:
   - `OLLAMA_RUNTIME=docker` (the default outside macOS): CPU inference in the `ollama` container. With an NVIDIA GPU and a current driver, add `COMPOSE_FILE=compose.yaml:compose.gpu.yaml` to `.env` to pass the GPU through.
   - `OLLAMA_RUNTIME=external`: install the Ollama for Windows app (it starts at sign-in and uses NVIDIA or AMD GPUs), then set `COMPOSE_PROFILES=` and `OLLAMA_BASE_URL=http://host.docker.internal:11434`. The start script pulls the model through the analyzer container, which proves the address works from Docker.

   `qwen2.5:1.5b` runs on any CPU. A 7B model needs a GPU with about 6 GB of VRAM; on CPU it approaches `AI_TIMEOUT_SECONDS`. WSL2 gives Docker half the host RAM by default; raise `memory=` in `%UserProfile%\.wslconfig` if Docker Ollama needs more.
4. Keep the laptop awake and unattended (PowerShell as Administrator):

   ```powershell
   powercfg /change standby-timeout-ac 0
   powercfg /change hibernate-timeout-ac 0
   powercfg /h off
   powercfg /setacvalueindex SCHEME_CURRENT SUB_BUTTONS LIDACTION 0
   powercfg /setactive SCHEME_CURRENT
   ```

   Docker Desktop only runs inside a signed-in session, so either configure automatic sign-in (`netplwiz` or Sysinternals Autologon) and protect the disk with BitLocker, or run Docker Engine inside WSL2 with systemd and a boot-time scheduled task instead of Docker Desktop. Set Windows Update active hours so restarts fall outside the London and New York sessions. Containers return on their own (`restart: unless-stopped`); the Ollama app and the tunnel service below start with Windows. Run `scripts\install_autostart.ps1` once (see [MetaTrader 5 feeder](#metatrader-5-feeder)) so the feeder, and Docker Desktop with it, also come back after every sign-in with nothing to run by hand.
5. Install the tunnel as a Windows service so it survives reboots without a shell: a named Cloudflare Tunnel (`cloudflared service install <token>`) or `ngrok service install`, both pointing at `http://localhost:8787`. Docker Desktop publishes the loopback ports on the Windows side, so a Windows service reaches the gateway at that address. Set `PUBLIC_WEBHOOK_URL` and rerun `bash scripts/start.sh`.
6. From an earlier `.env`, copy only `TELEGRAM_*`, `SYMBOLS`, and rule settings. Let `scripts/setup.py` generate fresh secrets and a new webhook path, create the n8n owner account, then create the TradingView alert with the URL in `.local/webhook-url.txt`.

## Deploy to a Linux VPS

The Docker stack can run on an Ubuntu/Debian VPS (about 4 GB RAM; key-based SSH as root or a passwordless-sudo user) while the MT5 feeder stays on the Windows PC next to the terminal:

```bash
bash scripts/deploy_vps.sh user@vps-host            # add --gpu for an NVIDIA VPS, --test to run the suite there
```

It installs Docker if missing, ships the **committed** `HEAD` with `git archive` (commit first; uncommitted edits are not deployed), and on the first run creates the VPS `.env` from the local one with fresh secrets and Docker Ollama on CPU. It then runs `scripts/start.sh` on the VPS. Reruns ship new code and restart; the VPS `.env` and volumes are never overwritten. Every port stays on the VPS loopback. The analyzer address and token are written to `.local/vps.env`. Then, on the Windows PC with MT5 logged in, stop any local feeder and run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\vps_feeder.ps1        # extra arguments go to mt5_feeder.py
```

This keeps an SSH tunnel open (`127.0.0.1:18010` → VPS analyzer), reconnecting when it drops, and runs the feeder through it via `ZEBRA_ANALYZER_URL` / `ZEBRA_ANALYZER_TOKEN`. The feeder reads its rule filters from the **local** `.env`, so keep rule settings identical on both machines. Once the VPS is live, stop the local stack (`docker compose stop`) or disable Telegram locally, or the daily record is sent twice.

## Connect TradingView

1. Give `http://localhost:8787` a public HTTPS tunnel, using a stable hostname for ongoing use. Only the exact generated webhook path is proxied; other paths return 404. Do not tunnel the n8n editor or analyzer ports.
2. Set `PUBLIC_WEBHOOK_URL=https://your-hostname/` in `.env`, then run `bash scripts/start.sh` to update local configuration. Your complete webhook URL is in `.local/webhook-url.txt`. The random path acts as a bearer secret: keep it private. The gateway rate-limits requests and caps the body at 16 KB. For an Internet deployment, add origin restrictions / source validation at your tunnel provider; path secrecy alone does not prove a request came from TradingView.
3. In TradingView, open a **15-minute** chart of an accepted ticker (**XAUUSD** by default; see `SYMBOLS`), paste `tradingview/gold_setups.pine` into Pine Editor, save it, and add it to the chart. Set the script's "Allowed tickers" input to match `SYMBOLS`, and its Levels inputs to match `STOP_ATR_MULTIPLE` and `TP_R_MULTIPLES`.
4. Create an alert with condition **Cambotix Zebra → Any alert() function call**, then enter the generated HTTPS webhook URL. The script supplies JSON itself. Enable TradingView 2FA and use an account plan that supports webhook alerts.
5. Recreate the TradingView alert whenever you change Pine inputs or script code. TradingView alerts use the saved script snapshot.

Example development tunnel if `cloudflared` is already installed:

```bash
cloudflared tunnel --url http://localhost:8787
```

Or, with an ngrok account token configured, `ngrok http 8787`; the live address is shown at `http://127.0.0.1:4040`. Either creates a public endpoint whose hostname changes on every restart. Copy its HTTPS hostname into `.env` and update TradingView if the hostname changes. A public tunnel is **not** launched by the setup script.

Pine emits on confirmed bar close when a setup first becomes valid. It uses EMA20/50/200, RSI14, MACD histogram, ADX through `ta.dmi`, ATR, and prior swing extremes. Classic trend alignment is strict (`price > EMA20 > EMA50 > EMA200` for a buy, reversed for a sell); RSI/MACD/ADX/ATR and the bar-open session gate the setup, while swing levels are stop context. On the chart the indicator also draws the same plan the Telegram message carries (`BUY AT`/`SELL AT`, `SL`, `TP1`-`TP4`, computed with the identical swing/ATR arithmetic) and a top-right rule table with live readings and pass/fail status per rule, so a chart and its message always agree. The alert JSON contains indicator values only; levels are recomputed by the analyzer. Multi-timeframe confirmation, spread checks, and account risk checks are not implemented. The Pine source must be compiled in TradingView; no local Pine compiler is included.

## Strategy models

Five detection models share the same pipeline, journal, AI gate, and message format. The payload's `model` field selects which fields are mandatory and which rules run.

**classic** (`tradingview/gold_setups.pine`): complete price/EMA20/50/200 alignment, RSI band, MACD histogram sign, ADX minimum, ATR band, and the London/New York session filter evaluated on the bar open. Levels come from ATR and the prior swing.

**crt** (`scripts/crt_engine.py`, Candle Range Theory): the previous higher-timeframe candle's high and low are a range (C1). When the next candle (C2) trades beyond exactly one side of it, leaves the other side untouched, and **closes back inside**, the move is treated as a liquidity grab and the plan targets the **opposite side** of the range:

1. **Candles**: H4 by default (`CRT_HTF_HOURS`; 1 = H1, 24 = D1), rebuilt from M15 in New York time with the 17:00 roll, so H4 candles open at 17, 21, 1, 5, 9 and 13 New York. Broker H4 bars (UTC on Exness) do not line up with those times. Both candles must be weekday sessions (crypto excepted), so the thin Sunday-evening open is never a range.
2. **Signal**: posted at C2's close with `timeframe` = the range timeframe (`4h`). `range_high`/`range_low` are C1, `sweep_level` is C2's wick beyond the range, `price` is C2's close.
3. **Plan**: market entry at that close (the signal says BUY NOW / SELL NOW; a limit at the swept level lost money in every backtest), stop beyond C2's wick plus `CRT_STOP_BUFFER_ATR` x 15m ATR, TP1 at C1's opposite extreme (TP2-TP4 at `CRT_EXTRA_TARGETS_R` beyond it), at least `CRT_MIN_RR` reward per unit of risk. The trade closes at market after `CRT_MAX_HOLD_CANDLES` range candles. `CRT_KEY_TIMES` can restrict which New York candles may signal (empty = all).
4. **Analyzer checks** (`crt_rules`): weekday candle, key time, range swept on exactly the signalled side, close back inside, stop beyond the sweep, target at the opposite extreme, stop at least 0.3 ATR, minimum reward:risk.

**ict** (`scripts/ict_engine.py`, the ICT 2022 model from `docs/ICT_Trading_Khmer_Beginner_Book.md`, chapter 19): runs on M5 **next to CRT**, covering the hours when CRT is quiet. The analyzer accepts it only for `ICT_SYMBOLS` (default `EURUSD`), and every message is tagged *ICT · forward test*:

1. **Liquidity**: the previous day's high/low (New York 17:00 roll), the Asia high/low (20:00-24:00 New York) and the London high/low (02:00-05:00). Each pool counts once.
2. **Sweep**: inside a killzone (London 02:00-05:00 or NY AM 08:30-11:00 New York, weekdays), price trades beyond a fresh pool. A swept low arms a buy; a swept high arms a sell.
3. **Market structure shift**: within 3 hours, the first M5 close back through the last 2/2 swing that formed before the sweep extreme.
4. **Fair value gap and plan**: the latest 3-candle FVG (at least 0.1 ATR) in that leg. The signal is a **limit** at the gap's near edge (`timeframe` = `5m`, `entry`, `fvg_low`/`fvg_high`, `mss_level`, `sweep_level`). The stop goes beyond the sweep plus 0.1 x 5m ATR, with one target at `ICT_MIN_RR` (2R). The grader cancels an unfilled limit after `ICT_ENTRY_EXPIRY_MINUTES` (120) and closes at market after `ICT_MAX_HOLD_MINUTES` (360).
5. **Analyzer checks** (`ict_rules`): enabled symbol, weekday killzone candle, a valid FVG with the entry at its near edge, sweep beyond the entry, stop beyond the sweep, stop at least 0.3 ATR, and the minimum reward:risk. There is no 15m volatility band: 5m ATR sits far below it, and the backtest used none.

**ema** (`scripts/ema_engine.py`, EMA pullback scalp): runs on **M1** and can be added to the gold feeder (`--models crt,ema`). The analyzer accepts it only for `EMA_SYMBOLS` (default `XAUUSD`) and tags every message *EMA scalp · forward test*:

1. **Trend**: the trigger candle closes with `close > EMA20 > EMA50 > EMA200` on M1 (reversed for a sell). EMAs use the same recursion as the classic model; the first 600 candles of any window never signal, so the live feeder (1500 M1 bars) and the backtest see the same values.
2. **Pullback**: within the previous 5 candles at least one low touched or crossed EMA20, and the pullback low (the lowest low of those candles and the trigger) stayed above EMA200: a dip in a trend, not a reversal.
3. **Trigger and plan**: a bullish close above EMA20 that also breaks the previous candle's high. **Market** entry at that close (`timeframe` = `1m`, `entry` = `price`, `swing_low`/`swing_high` = the pullback extremes), stop beyond the pullback extreme plus 0.2 x 1m ATR, one target at `EMA_MIN_RR` (1.5R). The stop must be 1-4 ATR wide: tighter is spread noise, wider is not a scalp. London or New York hours only, and no second setup in the same direction for 10 candles. The grader closes at market after `EMA_MAX_HOLD_MINUTES` (45).
4. **Analyzer checks** (`ema_rules`): enabled symbol, London/New York hours, the EMA stack in the trade's direction, entry at the close, stop beyond the pullback extreme, stop 0.5-5 ATR, and the minimum reward:risk. No 15m volatility band, as for ICT.

**mss** (`scripts/mss_engine.py`, liquidity sweep + market structure shift): ICT's canonical reversal on **H1**, ported from the sibling `ai-trading-platform` project's `ict_sweep_mss` strategy, whose walk-forward found a gold-only, regime-local edge on this timeframe. It can be added to the gold feeder (`--models crt,mss`). The analyzer accepts it only for `MSS_SYMBOLS` (default `XAUUSD`) and tags every message *Sweep+MSS · forward test*:

1. **Candles and swings**: H1 built from M15 on the hour of the broker's clock (a forming hour never signals). A 2/2 fractal (a high above the two bars on each side, or a low below them) is a swing, known two bars after its pivot. Every decision sees only the last 80 H1 bars, so the feeder and the backtest find the same swings.
2. **Sweep**: within the last 5 H1 bars, a bar traded below the last known swing low but **closed back above it** (a buy; the mirror above a swing high is a sell). The wick is the sweep extreme (`sweep_level`), the raided swing is `swing_low`/`swing_high`.
3. **Shift**: the decision bar is a displacement candle (body at least `MSS_BODY_ATR` x H1 ATR and at least half its range) that closes through the last known opposing swing (`mss_level`). No session or killzone filter: the sweep and the shift set the bias; weekend candles are skipped.
4. **Plan**: **market** entry at that close (`timeframe` = `1h`, `entry` = `price`), stop beyond the sweep wick plus `MSS_STOP_BUFFER_ATR` (0.5) x ATR, one target at the nearest known swing beyond the entry when it is at least `MSS_MIN_RR` (2R) away, else a 2R projection. The grader closes at market after `MSS_MAX_HOLD_HOURS` (120).
5. **Analyzer checks** (`mss_rules`): enabled symbol, weekday candle, sweep wick beyond the swept swing, close through the broken swing, entry at the close, stop beyond the sweep wick, stop at least 0.3 ATR, and the minimum reward:risk. No 15m volatility band, as for ICT and EMA.

The open-plan limit (`MAX_OPEN_SAME_DIRECTION`) counts plans **per model**: a 1m scalp and an H4 CRT plan on the same symbol are different bets with different horizons, so neither blocks the other.

All models also pass the **news** check: the analyzer reads the free ForexFactory weekly calendar and rejects any setup inside `NEWS_WINDOW_BEFORE_MIN` before or `NEWS_WINDOW_AFTER_MIN` after a high-impact event for `NEWS_CURRENCIES` (`high_impact_news_window`). If the feed is unreachable nothing is blocked and the message says news was not checked. Every message states 1R, its percent of price, and the reward-to-risk to TP1; with `ACCOUNT_SIZE` set it also converts `RISK_PERCENT` into units and lots using `CONTRACT_SIZES`. Neither model has established live performance; both remain manual-review tools.

### Backtesting

`scripts/backtest.py` replays saved broker history through the analyzer's own code: the feeder's detection, `app.domain` rules, `app.ledger.plan_record`, and the M1 grader with spread. Pull history on Windows with MT5 open (set *Tools > Options > Charts > Max bars in chart* to Unlimited and restart MT5, or M1 stops at 100,000 bars), then run it in the analyzer image:

```powershell
py -3.13 scripts\pull_history.py --symbol XAUUSDm --days 1100
docker compose run --rm --no-deps -v "${PWD}:/work" -w /work analyzer python scripts/backtest.py --symbol XAUUSD --models crt
docker compose run --rm --no-deps -v "${PWD}:/work" -w /work analyzer python scripts/backtest.py --symbol XAUUSD --models crt --sweep "CRT_MIN_RR=1.0|2.0"
docker compose run --rm --no-deps -v "${PWD}:/work" -w /work analyzer python scripts/backtest.py --symbol XAUUSD --models mss
```

Without MT5, `scripts/pull_dukascopy.py` writes the same files from Dukascopy's free BID/ASK minute candles (plus `_m5` and `_h1`): `--days 365` for a recent slice, or `--from 2003-05-01 --out .local/history_dukascopy_full` for the full history, written year by year to `years/` and merged; a rerun skips finished years. `python ml/check_history.py --folder .local/history_dukascopy_full --compare .local/history` then validates the result (timestamps, prices, gaps, spread by year, frames vs M1, overlap with the broker pull) and writes `ml/reports/xauusd_history_check.md`. `python ml/check_candidates.py --folder .local/history_dukascopy_full` then runs the ICT detection engine (`ml/ict_features.py`) over it and writes candidates per year, with sanity checks, to `ml/reports/xauusd_ict_candidates.md`. The `ml/` scripts need `pip install -r requirements-ml.txt`.

**ML model on ICT gold setups (docs/ml-plan.md): tested and rejected.** `python -m ml.dataset` grades every candidate from 2008 with the live grader (labels match `scripts/backtest.py` trade for trade), `python -m ml.train` runs a LightGBM walk-forward over 2014-2026 against four baselines and a shuffled-label control and checks five go/no-go gates, and `ml/predict.py`, `ml/monitor.py` and `ml/retrain.py` cover live scoring, drift and monthly retraining. Result: the model ranks setups better than chance (AUC 0.57 vs 0.50) but no subset pays for spread; it lost 0.10R per trade out of sample, and all five pre-listed variants failed every gate too (`ml/reports/xauusd_variants.md`). `ml/predict.py` refuses the model, and nothing ML-based is wired into the feeder.

`--set KEY=VALUE` overrides a setting for one run; `--sweep` ranks settings on the first two thirds of the history and shows the unseen last third beside each. Evidence so far (Exness MT5, H4 defaults above):

| Market and period | Trades | Result | Note |
|---|---|---|---|
| XAUUSD Nov 2023 - Nov 2026 | 375 | +33.5R, PF 1.13, max drawdown 24R | Nov 2023 - Oct 2024 +19.7R and Nov 2024 - Oct 2025 -9.3R were never used for tuning |
| EURUSD, GBPUSD, USDJPY, USTEC, XAGUSD, BTCUSD, 1 year | 107-216 each | -15R to -44R each | the same settings lose on every one |
| US30, 1 year | 122 | +13.3R | all of it in the last third |

ICT evidence: the rules were written down before any result was seen and never tuned afterwards. `--models ict` replays them through this same path:

| Market and period | Trades | Result | Note |
|---|---|---|---|
| EURUSD Nov 2023 - Nov 2026 (Dukascopy M1) | 197 | +23.8R, PF 1.22, max drawdown 12.5R | +14.7R, -2.5R, +11.5R by year; London killzone +29R, NY AM -5R |
| XAUUSD Nov 2023 - Nov 2026 | 79-140 | -5R to -25R | negative in every variant and every year, so ICT stays off gold |
| GBPUSD, USDJPY, USTEC, US30, XAGUSD, BTCUSD, 1 year | 16-43 each | -8R to +10R | mixed; only GBPUSD was clearly positive |

EMA scalp evidence (`--models ema`, rules fixed before the first run): no edge on gold. Default settings (1.5R, 45-minute hold, 1-4 ATR stop) over Nov 2023 - Nov 2026 gave 14,065 scalps, **-1253R, PF 0.85, 39% wins**, losing in 33 of 37 months and in every session; the last year alone (`--from 2025-11-13`) was 4,675 scalps, -249R, PF 0.91. A sweep of the target (1R, 2R, 3R), the hold (45, 120 minutes) and the minimum stop (1, 2 ATR) lost in all 12 combinations, both on the first two thirds (PF 0.79-0.87) and on the unseen last third (PF 0.87-0.92). The win rate tracked the target exactly as a coin flip would (48% at 1R, 33-37% at 2R, 25-30% at 3R), which is the signature of a random entry paying the spread. The model stays in the code as a forward-test tool and is not run live.

MSS evidence (`--models mss`, the sibling project's `ict_sweep_mss` rules ported unchanged, fixed before the first run): no edge. Gold over Nov 2023 - Nov 2026 gave 103 trades, **+3.85R, PF 1.07, 39% wins**; by Nov-Oct year -4.3R / +6.0R / -0.8R, so only one year was positive and the latest year lost, with all the profit on the buy side (+11.6R) while sells lost 7.7R. The same rules on the other thirteen symbols (three years of EURUSD, GBPUSD, USDJPY, AUDUSD, USDCAD, USDCHF, NZDUSD, EURJPY, GBPJPY; one year of XAGUSD, BTCUSD, US30, USTEC) summed to **-133R**: only USDCHF (+6.8R, PF 1.14) and BTCUSD (+3.6R, PF 1.16) were positive, and seven pairs lost 10-21R each. The sibling project's own walk-forward found the same thing (+0.07R per trade over 5.5 years, positive only since mid-2024 on gold), and that era has now ended. Pushing the same geometry to smaller candles to reach one trade a day (the engine's `bar_minutes` research setting) made it worse: on gold, M15 gave 0.44 trades per trading day and -9R (PF 0.96), M5 gave 0.97 per day and -24R (PF 0.95), and a looser displacement (1.0 ATR) on M5 gave 2.2 per day and -116R; EURUSD and GBPUSD lost 10-334R on the same variants. The model stays in the code as a forward-test tool and is not run live.

Stricter versions did not help. Requiring H4+H1 trend alignment, or a D1+H4+H1 bias with premium/discount and a reclaim, left 1-21 trades in three years, and a silver SMT filter made gold worse. Without killzones the model gave about 1.2 setups a day with no edge (PF 1.0). With CRT on gold and ICT on EURUSD, expect roughly 0.7 setups per trading day.

So the CRT edge, if real, is gold-only and thin, with losing years. Treat CRT as a forward-test candidate on a demo account, judged by the graded ledger below. Judge any new variant on all of these symbols at once, never on gold alone. The `classic` model lost 9.75R on the same gold year.

## Telegram

Create a bot with Telegram's BotFather, start a private chat with the bot, and obtain your chat ID. Set these values in `.env` locally:

```dotenv
TELEGRAM_ENABLED=true
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
```

Then apply with `docker compose up -d analyzer`. Subsequent completed analyses will send messages to that chat. Old notifications marked `disabled` are not replayed. Bot tokens stay in the analyzer environment, never in Pine payloads or exported n8n workflows. Message formatting is plain text, so model text cannot inject Telegram HTML.

Each message has a fixed structure: direction and result header, the `Ledger: #n` line for an approved plan, then **reference levels**, a `CAUTIONS` block for an approved setup with weak points, (`BUY AT`/`SELL AT`, `STOP LOSS`, `TP1`-`TP4`), a `WHY (rules)` section with factual indicator readings, the `AI NOTE` block when the model ran (`AI VIEW` with `GATE_MODE=ai`), any `CHECKS FAILED` codes, and the manual-review footer. Levels are computed in Python from the payload, never by the model: the stop sits beyond the prior swing plus a 0.2 ATR buffer when that lies within 1 to 3 ATR of entry, otherwise at `STOP_ATR_MULTIPLE` x ATR, and targets are `TP_R_MULTIPLES` multiples of that distance. Levels appear only when every technical rule passed; an AI-rejected setup shows them marked *reference only*. They are arithmetic on indicator values, not advice, and no order is ever placed.

Delivery is deliberately conservative: an ambiguous network result becomes `unknown` and is not automatically resent. `failed` and `unknown` entries are visible in the journal and need manual inspection. This avoids duplicate notifications after a timeout; it cannot promise exactly-once delivery to Telegram.

Graded results (fill, each target, stop, break-even, time limit, close) arrive as `RESULT` messages after signal alerts. With `TELEGRAM_COMMUNITY_CHAT_ID` set (a group or channel the bot was added to), every real approved signal is also posted there without your lot size, followed by its results; synthetic tests and rejected setups stay in the private chat. The daily record arrives once per day at `DIGEST_HOUR` in `DIGEST_TIMEZONE`, to `TELEGRAM_DIGEST_CHAT_ID` when set (for example a public channel) and otherwise to `TELEGRAM_CHAT_ID`.

## Configuration and behavior

Edit `.env`, then run `docker compose up -d analyzer` for filter/model/Telegram changes. Defaults:

| Setting | Default | Purpose |
|---|---|---|
| `MESSAGE_STYLE` | compact | Telegram alert layout: `compact` (entry, stop, target, one-line reason) or `detailed` (every rule reading and the AI note) |
| `GATE_MODE` | rules | `rules`: the technical rules decide and the model only comments; `ai`: the model must also approve |
| `AI_COMMENTARY` | true | Run optional model commentary in `rules` mode; failures and latency never reject the signal |
| `MIN_CONFIDENCE` | 75 | Subjective AI score threshold, not win probability (`GATE_MODE=ai` only) |
| `MIN_ADX` | 20 | Minimum trend strength |
| `MIN_ATR_PERCENT` / `MAX_ATR_PERCENT` | 0.02 / 0.5 | ATR divided by price, expressed as percent |
| `FILTER_SESSIONS` | true | London 08–17 or New York 08–17, weekdays, local DST |
| `SYMBOLS` | XAUUSD | Comma-separated tickers the analyzer accepts; others return 422 |
| `SESSION_EXEMPT_SYMBOLS` | BTCUSD,BTCUSDT | Around-the-clock markets that skip the session filter |
| `STOP_ATR_MULTIPLE` | 1.5 | Stop distance in ATR when no usable prior swing exists |
| `TP_R_MULTIPLES` | 1,2,3,4 | Take-profit levels as multiples of the stop distance (R) |
| `CRT_HTF_HOURS` | 4 | CRT range candle in hours (4 = H4, 1 = H1, 24 = D1), New York 17:00 roll |
| `CRT_KEY_TIMES` | (all) | New York open hours of the sweep candle that may signal, e.g. `1,5,9` |
| `CRT_MIN_RR` | 2.0 | CRT minimum reward to the opposite range extreme per unit of risk |
| `CRT_STOP_BUFFER_ATR` | 0.1 | CRT stop distance beyond the sweep wick, in 15m ATR |
| `CRT_MAX_HOLD_CANDLES` | 3 | CRT trades close at market after this many range candles |
| `CRT_EXTRA_TARGETS_R` | 0.5,1,1.5 | CRT TP2-TP4 in R beyond TP1; stop to entry after TP1 (backtest: split result +37.8R vs +33.5R TP1-only on 3 years of gold; farther targets were worse) |
| `NEWS_FILTER` | true | Reject setups near high-impact calendar events (both models) |
| `NEWS_WINDOW_BEFORE_MIN` / `NEWS_WINDOW_AFTER_MIN` | 30 / 15 | Blocked minutes around an event |
| `NEWS_CURRENCIES` | USD | Currencies whose high-impact events count |
| `NEWS_MAX_STALE_SECONDS` | 7200 | Maximum calendar-cache age during an outage; older data is reported unknown |
| `ACCOUNT_SIZE` | 0 | Account size for position sizing in messages; 0 hides it |
| `RISK_PERCENT` | 0.5 | Risk per trade used for sizing |
| `CONTRACT_SIZES` | XAUUSD=100 | Units per lot per symbol for the lots figure |
| `MAX_SIGNAL_AGE_SECONDS` | 300 | Maximum age from confirmed bar close |
| `OLLAMA_MODEL` | qwen2.5:3b | Local model with schema-constrained JSON (signal reviews, trade notes, agent routing) |
| `MAX_OPEN_SAME_DIRECTION` | 1 | Reject a setup while this many plans from the same model on the same symbol and side are still open (`0` = no limit) |
| `NEWS_CAUTION_MIN` | 120 | Caution when a high-impact event is due within this many minutes (beyond the blocking window) |
| `HISTORY_MIN_SAMPLES` / `HISTORY_DAYS` | 30 / 60 | History warning once the record has this many closed trades for the same symbol, side, model and session |
| `ENTRY_EXPIRY_MINUTES` | 120 | Limit entries not filled within this time are recorded as not filled (both models currently enter at market) |
| `MAX_HOLD_MINUTES` | 1440 | Open classic trades are closed at market after this time |
| `GO_MIN_TRADES` / `GO_MAX_DRAWDOWN_R` | 150 / 10 | Forward-test verdict thresholds |
| `DIGEST_HOUR` / `DIGEST_TIMEZONE` | 7 / Asia/Phnom_Penh | When the daily record is sent |
| `AI_TIMEOUT_SECONDS` | 120 | Maximum wait per AI attempt |

Use matching Pine indicator thresholds when adjusting rules. Classic accepts only the 15m timeframe; CRT accepts its range timeframe (`1h`, `4h` or `1d`). `SYMBOLS` lists accepted tickers; tickers in `SESSION_EXEMPT_SYMBOLS` skip the session filter on the server, and the Pine script skips it for any `crypto` symbol. Thresholds are shared across symbols, so review the ATR band before enabling a new market. Incoming `bar_time` is the bar-close timestamp in **Unix seconds**, not milliseconds. Numeric fields must be finite JSON numbers. `macd_hist` means histogram, not the MACD line.

With the default `GATE_MODE=rules`, a candidate is `approved` when every technical rule passes. When `AI_COMMENTARY=true`, the local model's review is queued and sent as its own message right after the alert (see AI agent); its failure or latency can neither delay nor veto the deterministic result. With `GATE_MODE=ai` the model must also approve the existing direction, report a matching market regime and good/excellent quality, and meet the configured confidence threshold; failures retry up to three times. `approved` means ready for **manual review**, never permission to place an order. Performance is established only by the graded ledger below, never claimed in advance.

**One idea, one plan.** While a plan on the same symbol and side is still open, a new setup in that direction is rejected with `open_plan_same_direction` (`MAX_OPEN_SAME_DIRECTION`). Stacking near-identical entries turns one idea into several losses when it fails. A plan counts as open until it closes, is not filled, or passes its own entry-expiry plus hold limit, so a stopped feeder cannot block a symbol forever. Synthetic test signals skip this check.

**Cautions** never block. An approved setup lists what is weak about it: RSI at the edge of its band, ADX just above the minimum, price extended from EMA20, a stop without a prior swing (classic); a target under 2.5R away or a close already past the range midpoint (CRT); volatility near either ATR limit and high-impact news within `NEWS_CAUTION_MIN` (both). Once the record holds `HISTORY_MIN_SAMPLES` closed trades for the same symbol, side, model and session within `HISTORY_DAYS`, a losing group (negative expectancy or under 40% wins) adds a `History:` warning from the ledger itself. Cautions are stored with the published plan, and the track record splits results into *with cautions* and *no cautions* so their value can be measured.

Signal identity is protected by both the primary event ID and a unique `(symbol, timeframe, bar_time, signal)` key. Concurrent inserts are atomic. A duplicate with changed values returns HTTP 409. Stale/invalid input returns 422, and database failures return 503 for retry. No successful acknowledgment is sent before database commit.

The processor holds a PostgreSQL advisory lock, recovers interrupted claims, and (with `GATE_MODE=ai`) retries failed/invalid AI responses up to three times with 30-second backoff. AI-gated age is checked again after inference; rules-mode commentary runs after the decision and cannot expire it. The accepted-signal journal and notification outbox are committed together. Invalid incoming requests are not stored; accepted signal history is available via `scripts/history.py` (latest 100) or PostgreSQL.

macOS setup uses `OLLAMA_RUNTIME=native`, an empty `COMPOSE_PROFILES`, and `OLLAMA_BASE_URL=http://host.docker.internal:11435`. To use Docker Ollama instead, set `OLLAMA_RUNTIME=docker`, `COMPOSE_PROFILES=docker-ai`, and `OLLAMA_BASE_URL=http://ollama:11434`, then run the start script. Docker inference on this Mac uses CPU. For a different model, change `OLLAMA_MODEL` and rerun `bash scripts/start.sh` to pull it and update the analyzer. Changing the timeout also requires regenerating and reimporting the analysis workflow.

## AI agent

A read-only assistant on top of the record. **It never places, edits or closes a trade, and it never decides a signal**: the technical rules keep full authority, and every AI table is separate from the ledger. Two models split the work by difficulty, not as fallbacks for each other:

| Work | Who | Cost |
|---|---|---|
| `/open`, `/price`, `/record`, `/signals`, `/news`, `/cost`, `/status` | code, from the database | free |
| Review of each approved signal (sent right after the alert) | Ollama | free |
| 1–2 line review of each closed trade (sent right after the result) | Ollama | free |
| Sorting each free-text question: command, simple or deep | Ollama | free |
| Simple questions, answered from a code-computed snapshot | Ollama | free |
| Deep questions (`/deep ...` or confidently routed), with read-only tools | OpenAI | paid, budgeted |
| Weekly report: statistics by code, interpretation by OpenAI | OpenAI | paid, budgeted |

When Ollama is down, alerts and results still go out without the notes, and free-text questions get a "local AI offline" reply; nothing is moved to OpenAI. When OpenAI is down, unconfigured or out of budget, deep questions get a plain explanation and the weekly report goes out with its statistics only; nothing is moved to the small local model.

**How it runs.** The n8n workflow *Zebra 5 — AI agent* calls `POST /agent` every 10 seconds. One tick, under its own advisory lock: reads new Telegram messages (`getUpdates`, so the bot needs no webhook), answers up to `AGENT_MAX_UPDATES_PER_RUN`, runs up to three queued AI notes, and sends the weekly report when it is due. Telegram updates are stored before they are answered and the read position is persisted, so a restart or an overlapping run never answers twice; a reply whose delivery result was lost is marked `unknown` and never resent. Notes are an `ai_jobs` queue (three attempts with backoff); stale notes are skipped.

**Access.** Only `TELEGRAM_CHAT_ID` as a *private* chat, sent by `TELEGRAM_ALLOWED_USER_ID` (default: the same id), gets an answer. Everyone else, including the community group, is ignored and their text is not stored. Questions, memory and database rows travel to the models as data, never as instructions. The last `AGENT_MEMORY_TURNS` question/answer pairs per chat are kept for follow-ups and deleted after `AGENT_MEMORY_RETENTION_DAYS`; `/forget` clears them.

**Deep analysis tools** (`app/agent/tools.py`): `get_track_record`, `get_signals`, `get_signal`, `get_open_trades`, `get_closed_trades`, `get_candles`, `get_news`. Each validates its arguments and runs a fixed, parameterized query inside a `READ ONLY` transaction; there is no SQL tool and no write tool. Per question: at most `AGENT_MAX_TOOL_CALLS` tool executions (then the model must conclude), `AGENT_TOOL_OUTPUT_CHARS` per result, `AGENT_DEEP_TIMEOUT_SECONDS` overall. The instructions require cited numbers, sample sizes, and suggestions phrased as hypotheses to backtest.

**Cost control.** Before **every** OpenAI request (a question with tool rounds makes several), its worst-case cost (input estimate plus `OPENAI_MAX_OUTPUT_TOKENS`) is reserved inside one locked transaction, and the request is refused without being sent when either:
- the day already has `OPENAI_DAILY_LIMIT` deep jobs (a question or a report, with all its rounds), or
- the month's spending plus the reservation would exceed `OPENAI_MONTHLY_BUDGET_USD − OPENAI_SAFETY_RESERVE_USD`.

Concurrent requests cannot overspend. After the response, the reservation is replaced by the cost of the measured tokens (`OPENAI_PRICE_*`). A timeout or server error keeps the full reservation as cost: failures are never assumed free. Days and months follow `DIGEST_TIMEZONE`. These are estimates; OpenAI's billing page is the authority. `/cost` shows today, the month, the budget left and Ollama's request count; `/status` shows the database, Ollama (model pulled?), OpenAI configuration, provider success rates and latency, MT5 feed freshness, queue depths and Telegram failures.

**Weekly report.** On `WEEKLY_REPORT_DAY` from `WEEKLY_REPORT_HOUR` (`WEEKLY_REPORT_TIMEZONE`), covering the seven days that ended at midnight: totals, win rate, R, profit factor, expectancy, the four previous weeks, sessions, symbols, cautions and data-quality notes (small samples, stale feed, ambiguous candles), all computed by code. OpenAI adds observations and 1–3 backtest suggestions. The period is claimed before any work (`ai_reports`), so a second run never sends a second report. Reports go to the digest chat.

**Enable it** (stage 1 → 2 → 3):

1. Deploy with `AGENT_ENABLED=false`. Run `bash scripts/check-ai.sh` to test the local model, then check `/agent` runs in n8n.
2. Pull the local model (`OLLAMA_MODEL`, default `qwen2.5:3b`; try `qwen2.5:7b` if the VPS has 8 GB+ RAM and compare). Set `AGENT_ENABLED=true` and send `/status`, `/help` and `/open` to the bot.
3. Add `OPENAI_API_KEY` and `OPENAI_MODEL` to the server's `.env` only, after confirming the model id your account can use with the Responses API. Start with a small `OPENAI_DAILY_LIMIT`, set the same monthly limit in the OpenAI dashboard, and watch `/cost` for a week.

Settings: see the AI agent block at the end of `.env.example`. Changing `.env` needs `docker compose up -d analyzer` to take effect. Existing installations get the new workflow from `bash scripts/start.sh`, which imports only the missing one. A VPS keeps its own `.env`, so add the new keys there.

## MetaTrader 5 feeder

`scripts/mt5_feeder.py` replaces the TradingView webhook entirely, so no TradingView plan and no tunnel are needed. It runs the models from the broker's own candles and posts setups straight to the analyzer at `127.0.0.1:ANALYZER_PORT`: the classic model mirrors `gold_setups.pine` bar for bar, and on every M15 close that also closes a New York-aligned H4 candle it runs `scripts/crt_engine.py` over the last 600 closed M15 bars and posts a CRT setup if that candle swept the previous one and closed back inside. CRT settings are read from `.env` (`CRT_*`) so what it emits is what the analyzer accepts, and a payload is sent only for the candle that just closed, so a restart never re-sends history. `--models` takes a comma list of `classic`, `crt`, `ict` and `ema` (default `crt`; live runs `crt` on gold and `ict` on EURUSD). With `ict` it also scans every 5 minutes: it replays the last 1500 closed M5 bars through `scripts/ict_engine.py` and posts a setup only if the candle that just closed completed it. With `ema` it scans every minute: the last 1500 closed M1 bars go through `scripts/ema_engine.py` and only a setup triggered by the candle that just closed is posted (quiet minutes print nothing; a heartbeat line appears every 15 minutes). The feeder refuses to start ICT or EMA on a symbol outside `ICT_SYMBOLS` / `EMA_SYMBOLS`. It also sends the broker's closed M1 candles every minute; these are what the grader scores. It runs on **Windows Python** next to a logged-in MetaTrader 5 terminal (the `MetaTrader5` package is Windows-only). If `mt5.initialize()` reports `IPC timeout`, untick *Tools > Options > Expert Advisors > Disable algorithmic trading via external Python API*:

```powershell
py -m pip install MetaTrader5 pandas numpy
cd \\wsl.localhost\Ubuntu\home\<you>\cambotix-zebra
py scripts\mt5_feeder.py --symbol XAUUSDm --once --dry-run   # check readings, send nothing
py scripts\mt5_feeder.py --symbol XAUUSDm                    # watch: candles every minute, setups every 15m
```

To leave it running unattended, install it once as a sign-in task instead of keeping a window open:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\install_autostart.ps1                # add -Symbol XAUUSDm, -Vps; -Uninstall removes it
Get-Content .local\feeder.log -Tail 30 -Wait                                          # what it is doing
```

The task "Cambotix Zebra Feeder" runs `scripts\feeder_service.ps1` hidden 30 seconds after you sign in. It starts Docker Desktop if it is not running, waits for the analyzer, runs the feeder (MT5 launches the saved terminal itself), and restarts it 30 seconds after any exit. Task Scheduler also restarts the service if PowerShell dies. Output goes to `.local\feeder.log` (rotated at 10 MB). Close any feeder you started by hand first; reinstalling stops only the old feeders of that symbol. With `-Vps` it runs `scripts\vps_feeder.ps1` instead.

The ICT model runs as a second task next to the gold one, with its own log:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\install_autostart.ps1 -Symbol EURUSDm -Models ict -TaskName 'Cambotix Zebra Feeder EURUSD' -LogName feeder-eurusd.log
Get-Content .local\feeder-eurusd.log -Tail 30 -Wait
```

Use a demo account for the forward test. MT5 bar times must be UTC (Exness servers are); a terminal whose server clock runs ahead of UTC is refused loudly because its candles and signals would be in the future. If the feeder was offline, the analyzer answers with the earliest time it still needs and the feeder backfills it. `tests/test_crt_engine.py` builds H4 candles from hand-made M15 bars and checks that an emitted CRT payload passes the analyzer's own `crt_rules`; `tests/test_ict_engine.py` does the same for an Asia-low sweep in the London killzone and its mirror image.

## Outcome grading and track record

Every approved plan is appended to `ledger` in the same transaction as the approval, with its levels frozen. The grader (`POST /grade`, every minute) replays stored broker candles for each open plan and appends what happened: `filled`, `tp1`-`tp4`, `sl`, `be`, `timeout`, `not_filled`, and a final `closed` row with two scores:

- **TP1 basis** (the headline): the whole position closes at TP1, or at the stop for -1R.
- **Scale-out**: equal parts close at each target, with the stop moved to entry after TP1.

Grading is deliberately conservative. A BUY fills at the ask and exits at the bid, a SELL the reverse, using each bar's spread. Classic and CRT plans fill at the open of the first minute after publication. Limit plans (none are emitted today; the grader keeps the rules) expire after `ENTRY_EXPIRY_MINUTES` or are not filled if TP1 prints first, a gap through both a limit entry and its stop is `not_filled`, and a limit fill candle cannot credit targets. When one candle could have hit the stop and a target, the stop is counted and the trade is flagged ambiguous. R is measured against the actual fill. Plans without candle coverage stay open; they are never dropped.

The ledger cannot be edited by the service: triggers refuse `UPDATE`, `DELETE`, and `TRUNCATE` on `ledger` and `candles` and deletion of `signals`, and stored candles are first-write-wins. Each row carries the previous row's SHA-256, and the daily Telegram record posts the chain head. A database superuser can still bypass triggers, but any rewrite changes every later hash and no longer matches the posted head.

```bash
python3 scripts/track_record.py                       # stats, forward-test verdict, independent chain check
python3 scripts/track_record.py --expect 42:<hash>    # compare with a head posted in Telegram
python3 scripts/track_record.py --html record.html    # full public record as one static page
```

The forward-test verdict is `GO` only with at least `GO_MIN_TRADES` closed trades, positive expectancy on the TP1 basis, and a maximum drawdown within `GO_MAX_DRAWDOWN_R`. Until then it reads `NOT ENOUGH DATA`; do not publish or charge for signals before it reads `GO`.

## Public website

A Next.js site shows the record the way a visitor needs to see it: home with live broker tickers and the headline numbers, every published plan with its graded outcome, the full track record with breakdowns and the hash chain, and a pricing page that stays "not for sale" until the forward test reads GO. Two compose services carry it:

- `api` (`web/api.py`): the public record as JSON — `/record`, `/signals`, `/signals/{seq}`, `/tickers`, `/news` (the high-impact calendar the rules already use), `/candles/{symbol}?tf=` (stored broker M1 aggregated to 1m-1d), `/indicators/{symbol}?tf=&at=` (RSI, Stochastic, MACD histogram, ADX/DI, Bollinger %B, ATR, EMA stack with verdicts derived in code — `web/indicators.py`), `/ledger`, `/health`. No authentication, read-only transactions, answers cached for `WEB_CACHE_SECONDS` (60). It has no published port; only the frontend container reaches it. Open plans are served **without** their entry, stop and targets — the levels go out live on Telegram and appear on the site once the plan closes, together with the result. Synthetic test traffic never counts.
- `frontend` (`frontend/`, Next.js 16, TypeScript, Tailwind): server-rendered pages on `127.0.0.1:WEB_PORT` (3000). Two surfaces share one codebase: the **marketing site** at `/`, `/track-record`, `/method`, `/pricing` (top navigation, ticker strip, footer with the chain head) and the **dashboard** under `/app` (sidebar rail, top bar with the page explainer): Overview, Terminal (broker chart with plan flags, timeframe and symbol pills, Analysis / History / News panel), Signals and the plan detail page, Indicators, My Trades (Track record / History / Journal / Performance), Alerts, Settings. The dashboard runs in **guest mode** — there are no accounts yet, so the user name, plan, "signals left", journal and alert form are placeholders marked `TODO(accounts)` in `frontend/src/lib/guest.ts` and the pages; on-demand "Scan now" / "Analyze" buttons are disabled because setups are only detected on each 15-minute close. Design tokens live in `frontend/src/app/globals.css` (near-black surfaces, gold brand, green targets, red stops, tinted level cards). `node scripts/shots.mjs <baseUrl> <outDir>` screenshots every page at 1280 and 390 px with Playwright and flags horizontal overflow. Pages are a static shell with the data streamed in at request time, so nothing stale is ever baked into a build. Each plan has a detail page (`/signals/<ledger number>`, served by `api` `/signals/{seq}`) with the tinted levels grid, reward-to-risk, distances from entry, quality warnings, the graded timeline and a position-size calculator (`contractSize` in `frontend/src/lib/site.ts`). `/ledger.json` hands anyone the raw chain to verify.

```bash
bash scripts/start.sh                     # builds and starts both with the rest of the stack
open http://localhost:3000
cd frontend && npm install && npm run dev -- -p 3001 # local development on :3001 against the Docker api on 127.0.0.1:8091 (API_PORT)
```

English is served at the clean URLs and Khmer under `/km/...` (a `proxy.ts` rewrite; the toggle in the header keeps the current page). All strings live in `frontend/src/lib/i18n.ts`; the brand, markets, Telegram link and team cards in `frontend/src/lib/site.ts`; the logo is `frontend/public/logo.jpg` (also the favicon). The Method page renders `frontend/content/method.km.md` — a copy of `docs/ICT_Trading_Khmer_Beginner_Book.md` without its diagram images, which are not in the repository — and a short English summary, `method.en.md`; edit the book in `docs/` and re-copy. Set `NEXT_PUBLIC_TELEGRAM_URL` in the frontend environment to point the Telegram buttons at your channel. Publish the site through a tunnel (a named Cloudflare Tunnel to `http://localhost:3000`); never the analyzer, the api or n8n. The Pro tier stays "not for sale" until the forward test reads GO.

## Workflows and maintenance

The four JSON templates in `n8n/` contain no secrets. `scripts/setup.py` renders the actual webhook and header credential into ignored `.local/import/`. The start script imports them once, publishes them, restarts n8n, and removes the plaintext credential import. Repeated starts preserve workflow edits.

An installation made before the outcome grader existed gets only the new `zebraGradeV1` workflow on its next `bash scripts/start.sh`; the other three are left as edited. To deliberately replace all four project workflows after editing the generator, remove `.local/workflows-installed` and run `bash scripts/start.sh`. This overwrites these four workflow IDs. Export any UI edits you want to keep first. Rotate `WEBHOOK_PATH` using the same reimport procedure and update TradingView. Keep `N8N_ENCRYPTION_KEY` unchanged after initialization unless performing an n8n credential migration.

The pinned n8n image is version 2.37.10 (multi-arch index digest). An existing n8n database is migrated forward on first start; back up the `n8n_data` and `postgres_data` volumes first. Other service versions are fixed in `compose.yaml`; review updates periodically. No subscription or cloud AI key is required by this implementation. TradingView plan access, tunnel/domain arrangements, Docker licensing eligibility, electricity, and connectivity remain separate from the local software setup.

## References

- [TradingView webhook requirements](https://www.tradingview.com/support/solutions/43000529348-how-to-configure-webhook-alerts/) — public endpoint, JSON, response deadline, 2FA.
- [TradingView webhook retries](https://www.tradingview.com/support/solutions/43000735201-webhook-resubmission/) — retryable server responses.
- [Pine alerts](https://www.tradingview.com/pine-script-docs/concepts/alerts/) — bar-close alerts and saved snapshots.
- [Ollama structured outputs](https://docs.ollama.com/capabilities/structured-outputs) — JSON schema generation and validation.
- [n8n CLI](https://docs.n8n.io/hosting/cli-commands/) — import and publish workflows.
