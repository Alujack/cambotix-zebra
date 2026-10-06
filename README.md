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
python3 scripts/demo.py BTCUSD smc    # same for the SMC/ICT model
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

   Docker Desktop only runs inside a signed-in session, so either configure automatic sign-in (`netplwiz` or Sysinternals Autologon) and protect the disk with BitLocker, or run Docker Engine inside WSL2 with systemd and a boot-time scheduled task instead of Docker Desktop. Set Windows Update active hours so restarts fall outside the London and New York sessions. Containers return on their own (`restart: unless-stopped`); the Ollama app and the tunnel service below start with Windows.
5. Install the tunnel as a Windows service so it survives reboots without a shell: a named Cloudflare Tunnel (`cloudflared service install <token>`) or `ngrok service install`, both pointing at `http://localhost:8787`. Docker Desktop publishes the loopback ports on the Windows side, so a Windows service reaches the gateway at that address. Set `PUBLIC_WEBHOOK_URL` and rerun `bash scripts/start.sh`.
6. From an earlier `.env`, copy only `TELEGRAM_*`, `SYMBOLS`, and rule settings. Let `scripts/setup.py` generate fresh secrets and a new webhook path, create the n8n owner account, then create the TradingView alert with the URL in `.local/webhook-url.txt`.

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

Two detection models share the same pipeline, journal, AI gate, and message format. The payload's `model` field selects which fields are mandatory and which rules run.

**classic** (`tradingview/gold_setups.pine`): complete price/EMA20/50/200 alignment, RSI band, MACD histogram sign, ADX minimum, ATR band, and the London/New York session filter evaluated on the bar open. Levels come from ATR and the prior swing.

**smc** (`tradingview/smc_setups.pine`): ICT / Smart Money Concepts, detected mechanically on the 15m chart:

1. **HTF bias, top-down**: structure on the Daily and the 4H (direction of the last break of a confirmed swing); by default both must agree, otherwise the indicator stands aside. The payload carries `htf_bias` plus `daily_bias` and `h4_bias`.
2. **Liquidity map and sweep**: previous day high/low (`pdh`/`pdl`), previous week high/low (`pwh`/`pwl`), the completed Asian range (`asia_high`/`asia_low`, default 20:00-00:00 New York), equal highs/lows within a tolerance, and confirmed swings are plotted and watched. A sweep is a candle trading through one of these pools and closing back inside; the pool's name travels as `swept_name`.
3. **Market structure shift**: within `waitBars`, a displacement candle (body at least 1 ATR) closes through the last confirmed swing high (for a buy) or swing low (for a sell), frozen at the sweep. A candle that sweeps both sides cancels the sequence.
4. **Fair value gap**: the three-candle imbalance left by that displacement; its consequent encroachment (midpoint) is the required retest. The last opposing candle before the displacement is reported as the order block.
5. **Premium/discount**: the entry must sit below the equilibrium of the dealing range (swept low to the `rangeBars` high) for longs, above it for shorts.
6. **Draw on liquidity**: TP1 is the nearest opposing pool (swing, PDH/PDL, PWH/PWL, Asian range, equal highs/lows) that is still untouched and offers at least `minRr` reward per unit of risk; its name travels as `target_name`. A pool that price has already touched is marked *taken* and is never reused as a sweep or a target. With no qualifying pool there is no setup; the indicator never invents a target. The panel shows the nearest untouched pool above and below price.
7. **Time**: the setup bar must open inside an enabled ICT killzone in New York time (London open, New York open, optional New York PM); crypto tickers use all seven days.
8. **News**: the analyzer checks the free ForexFactory weekly calendar and rejects any setup (both models) inside `NEWS_WINDOW_BEFORE_MIN` before or `NEWS_WINDOW_AFTER_MIN` after a high-impact event for `NEWS_CURRENCIES` (`high_impact_news_window`). If the feed is unreachable nothing is blocked and the message says news was not checked.
9. **Risk**: every message states 1R, its percent of price, and the reward-to-risk to TP1. With `ACCOUNT_SIZE` set, it also converts `RISK_PERCENT` into units and lots using `CONTRACT_SIZES`. Position sizing is server-side only; the chart shows levels and R multiples.

The chart first draws a **SETUP** plan and sends nothing to the server. A later **BUY / SELL confirmed** candle must touch the FVG midpoint, close back beyond the gap, remain inside the frozen range and correct premium/discount half, and still pass direction, session, volatility and reward/risk filters. Only then does *Any alert() function call* post JSON. `entry` is that confirmed close; `setup_entry` is the original FVG midpoint and `setup_bar_time` identifies its formation bar. The payload also carries the stop, liquidity target, FVG, order block, range, sweep/MSS, HTF bias, killzone and **rule score**. The analyzer independently revalidates formation and confirmation killzones, FVG midpoint, stop/sweep geometry, structure direction, confirmed-entry location/risk/reward, HTF bias, ATR and minimum score before the model sees it. Legacy payloads without `entry_mode` remain midpoint-limit plans for backward compatibility. `hit_rate` and `samples` are the chart's simulated confirmed-entry memory; expired, cancelled, missed and ambiguous plans are excluded. `tradingview/SMC_GUIDE.md` explains every label. Pine cannot run a language model; Ollama remains server-side. `python3 scripts/demo.py BTCUSD smc` exercises the legacy synthetic compatibility path. Neither model has established performance; both remain manual-review tools.

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

Graded results (fill, each target, stop, break-even, time limit, close) arrive as `RESULT` messages after signal alerts. The daily record arrives once per day at `DIGEST_HOUR` in `DIGEST_TIMEZONE`, to `TELEGRAM_DIGEST_CHAT_ID` when set (for example a public channel) and otherwise to `TELEGRAM_CHAT_ID`.

## Configuration and behavior

Edit `.env`, then run `docker compose up -d analyzer` for filter/model/Telegram changes. Defaults:

| Setting | Default | Purpose |
|---|---|---|
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
| `KILLZONES` | London,NY AM | SMC model: ICT killzones (New York time) a setup must open inside |
| `REQUIRE_HTF_BIAS` | true | SMC model: higher-timeframe structure must agree with the direction |
| `REQUIRE_DISCOUNT` | true | SMC model: longs only below range equilibrium, shorts only above |
| `MIN_RR` | 1.5 | SMC model: minimum reward to TP1 (liquidity) per unit of risk |
| `MIN_SMC_SCORE` | 70 | Server-side minimum for a supplied Pine confluence score (not a win probability) |
| `NEWS_FILTER` | true | Reject setups near high-impact calendar events (both models) |
| `NEWS_WINDOW_BEFORE_MIN` / `NEWS_WINDOW_AFTER_MIN` | 30 / 15 | Blocked minutes around an event |
| `NEWS_CURRENCIES` | USD | Currencies whose high-impact events count |
| `NEWS_MAX_STALE_SECONDS` | 7200 | Maximum calendar-cache age during an outage; older data is reported unknown |
| `ACCOUNT_SIZE` | 0 | Account size for position sizing in messages; 0 hides it |
| `RISK_PERCENT` | 0.5 | Risk per trade used for sizing |
| `CONTRACT_SIZES` | XAUUSD=100 | Units per lot per symbol for the lots figure |
| `MAX_SIGNAL_AGE_SECONDS` | 300 | Maximum age from confirmed bar close |
| `OLLAMA_MODEL` | qwen2.5:1.5b | Local model with schema-constrained JSON |
| `MAX_OPEN_SAME_DIRECTION` | 1 | Reject a setup while this many plans on the same symbol and side are still open (`0` = no limit) |
| `NEWS_CAUTION_MIN` | 120 | Caution when a high-impact event is due within this many minutes (beyond the blocking window) |
| `HISTORY_MIN_SAMPLES` / `HISTORY_DAYS` | 30 / 60 | History warning once the record has this many closed trades for the same symbol, side, model and session |
| `ENTRY_EXPIRY_MINUTES` | 120 | Legacy SMC midpoint-limit entries not filled within this time are recorded as not filled |
| `MAX_HOLD_MINUTES` | 1440 | Open trades are closed at market after this time |
| `GO_MIN_TRADES` / `GO_MAX_DRAWDOWN_R` | 150 / 10 | Forward-test verdict thresholds |
| `DIGEST_HOUR` / `DIGEST_TIMEZONE` | 7 / Asia/Phnom_Penh | When the daily record is sent |
| `AI_TIMEOUT_SECONDS` | 120 | Maximum wait per AI attempt |

Use matching Pine indicator thresholds when adjusting rules. Only the 15m timeframe is accepted. `SYMBOLS` lists accepted tickers; tickers in `SESSION_EXEMPT_SYMBOLS` skip the session filter on the server, and the Pine script skips it for any `crypto` symbol. Thresholds are shared across symbols, so review the ATR band before enabling a new market. Incoming `bar_time` is the bar-close timestamp in **Unix seconds**, not milliseconds. Numeric fields must be finite JSON numbers. `macd_hist` means histogram, not the MACD line.

With the default `GATE_MODE=rules`, a candidate is `approved` when every technical rule passes. When `AI_COMMENTARY=true`, the model gets only the remaining freshness window minus a transaction reserve; its failure or latency cannot veto the deterministic result. Set it false for the fastest path. With `GATE_MODE=ai` the model must also approve the existing direction, report a matching market regime and good/excellent quality, and meet the configured confidence threshold; failures retry up to three times. `approved` means ready for **manual review**, never permission to place an order. Performance is established only by the graded ledger below, never claimed in advance.

**One idea, one plan.** While a plan on the same symbol and side is still open, a new setup in that direction is rejected with `open_plan_same_direction` (`MAX_OPEN_SAME_DIRECTION`). Stacking near-identical entries turns one idea into several losses when it fails. A plan counts as open until it closes, is not filled, or passes its own entry-expiry plus hold limit, so a stopped feeder cannot block a symbol forever. Synthetic test signals skip this check.

**Cautions** never block. An approved setup lists what is weak about it: RSI at the edge of its band, ADX just above the minimum, price extended from EMA20, a stop without a prior swing (classic); thin reward to TP1, a wide or tight stop, entry near equilibrium, Daily and 4H disagreeing, weak chart history (SMC); volatility near either ATR limit and high-impact news within `NEWS_CAUTION_MIN` (both). Once the record holds `HISTORY_MIN_SAMPLES` closed trades for the same symbol, side, model and session within `HISTORY_DAYS`, a losing group (negative expectancy or under 40% wins) adds a `History:` warning from the ledger itself. Cautions are stored with the published plan, and the track record splits results into *with cautions* and *no cautions* so their value can be measured.

Signal identity is protected by both the primary event ID and a unique `(symbol, timeframe, bar_time, signal)` key. Concurrent inserts are atomic. A duplicate with changed values returns HTTP 409. Stale/invalid input returns 422, and database failures return 503 for retry. No successful acknowledgment is sent before database commit.

The processor holds a PostgreSQL advisory lock, recovers interrupted claims, and (with `GATE_MODE=ai`) retries failed/invalid AI responses up to three times with 30-second backoff. AI-gated age is checked again after inference; optional rules-mode commentary cannot expire an otherwise valid rules decision. The accepted-signal journal and notification outbox are committed together. Invalid incoming requests are not stored; accepted signal history is available via `scripts/history.py` (latest 100) or PostgreSQL.

macOS setup uses `OLLAMA_RUNTIME=native`, an empty `COMPOSE_PROFILES`, and `OLLAMA_BASE_URL=http://host.docker.internal:11435`. To use Docker Ollama instead, set `OLLAMA_RUNTIME=docker`, `COMPOSE_PROFILES=docker-ai`, and `OLLAMA_BASE_URL=http://ollama:11434`, then run the start script. Docker inference on this Mac uses CPU. For a different model, change `OLLAMA_MODEL` and rerun `bash scripts/start.sh` to pull it and update the analyzer. Changing the timeout also requires regenerating and reimporting the analysis workflow.

## MetaTrader 5 feeder

`scripts/mt5_feeder.py` replaces the TradingView webhook entirely, so no TradingView plan and no tunnel are needed. It runs **both models** from the broker's own candles and posts setups straight to the analyzer at `127.0.0.1:ANALYZER_PORT`: the classic model mirrors `gold_setups.pine` bar for bar, and the SMC model replays `scripts/smc_engine.py`, a pure-Python port of `smc_setups.pine` (sweep → MSS with displacement → FVG → retest → confirmed close), over the last 1,500 closed 15m bars with the broker's Daily, 4H and Weekly bars as context. Its filters are read from `.env` (`KILLZONES`, `REQUIRE_HTF_BIAS`, `REQUIRE_DISCOUNT`, `MIN_RR`, `MIN_SMC_SCORE`, ATR band) so what it emits is what the analyzer accepts; the Pine inputs it does not expose keep their chart defaults. The replay is deterministic and a payload is sent only when its confirmation bar is the bar that just closed, so a restart never re-sends history. `--models classic`, `--models smc` or the default `classic,smc` choose what runs. It also sends the broker's closed M1 candles every minute; these are what the grader scores. It runs on **Windows Python** next to a logged-in MetaTrader 5 terminal (the `MetaTrader5` package is Windows-only):

```powershell
py -m pip install MetaTrader5 pandas numpy
cd \\wsl.localhost\Ubuntu\home\<you>\cambotix-zebra
py scripts\mt5_feeder.py --symbol XAUUSDc --once --dry-run   # check readings, send nothing
py scripts\mt5_feeder.py --symbol XAUUSDc                    # watch: candles every minute, setups every 15m
```

Use a demo account for the forward test. MT5 bar times must be UTC (Exness servers are); a terminal whose server clock runs ahead of UTC is refused loudly because its candles and signals would be in the future. If the feeder was offline, the analyzer answers with the earliest time it still needs and the feeder backfills it. Two known differences from the TradingView chart: Daily, 4H and Weekly bars follow the broker's day and week boundaries rather than the exchange's, and a pivot requires a strict extreme (equal highs or lows are not a swing), where Pine's tie handling is undocumented. `tests/test_smc_engine.py` drives the engine through a hand-built sweep → MSS → FVG → retest → confirmed-close scenario and checks that the emitted payload passes the analyzer's own SMC rules.

## Outcome grading and track record

Every approved plan is appended to `ledger` in the same transaction as the approval, with its levels frozen. The grader (`POST /grade`, every minute) replays stored broker candles for each open plan and appends what happened: `filled`, `tp1`-`tp4`, `sl`, `be`, `timeout`, `not_filled`, and a final `closed` row with two scores:

- **TP1 basis** (the headline): the whole position closes at TP1, or at the stop for -1R.
- **Scale-out**: equal parts close at each target, with the stop moved to entry after TP1.

Grading is deliberately conservative. A BUY fills at the ask and exits at the bid, a SELL the reverse, using each bar's spread. Classic and confirmed-close SMC plans fill at the open of the first minute after publication; the SMC reference entry remains the confirmed 15m close shown in the alert. Legacy SMC midpoint-limit payloads expire after `ENTRY_EXPIRY_MINUTES`, or are recorded as not filled if TP1 prints first. A gap through both a legacy limit entry and its stop is `not_filled`, because OHLC cannot support a defensible -1R sequence. A limit fill candle cannot credit targets. When one candle could have hit the stop and a target, the stop is counted and the trade is flagged ambiguous. R is measured against the actual fill. Plans without candle coverage stay open; they are never dropped.

The ledger cannot be edited by the service: triggers refuse `UPDATE`, `DELETE`, and `TRUNCATE` on `ledger` and `candles` and deletion of `signals`, and stored candles are first-write-wins. Each row carries the previous row's SHA-256, and the daily Telegram record posts the chain head. A database superuser can still bypass triggers, but any rewrite changes every later hash and no longer matches the posted head.

```bash
python3 scripts/track_record.py                       # stats, forward-test verdict, independent chain check
python3 scripts/track_record.py --expect 42:<hash>    # compare with a head posted in Telegram
python3 scripts/track_record.py --html record.html    # full public record as one static page
```

The forward-test verdict is `GO` only with at least `GO_MIN_TRADES` closed trades, positive expectancy on the TP1 basis, and a maximum drawdown within `GO_MAX_DRAWDOWN_R`. Until then it reads `NOT ENOUGH DATA`; do not publish or charge for signals before it reads `GO`.

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
