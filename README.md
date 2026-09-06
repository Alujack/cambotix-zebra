# Cambotix Zebra

Local XAUUSD 15-minute signal analysis using TradingView, n8n, PostgreSQL, and Ollama. Telegram delivery is optional. This implements the V1 manual-review MVP: **no broker connection, paper fills, or live orders**.

```text
TradingView Pine alert
  → HTTPS tunnel (configure your endpoint)
  → restricted webhook gateway :8787
  → n8n intake workflow :5680
  → analyzer: validate, normalize, atomically save to PostgreSQL
  ← HTTP 202 after commit (duplicates: HTTP 200)

n8n schedule every 15 seconds
  → claim a saved signal
  → technical rules and session checks
  → Ollama JSON classification
  → final quality gate and PostgreSQL journal

n8n notification schedule
  → PostgreSQL outbox → Telegram when explicitly enabled
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
docker compose logs --tail=100 analyzer n8n
docker compose stop
docker compose start
```

On macOS, native Ollama is a separate background process; its log and PID are in `.local/ollama/server.log` and `.local/ollama/server.pid`. It does not automatically start at login. Run `bash scripts/start.sh` after a reboot. `docker compose stop` stops the containers only; to stop this project's native model server, run `kill "$(cat .local/ollama/server.pid)"` after verifying that PID still belongs to this Ollama process.

The smoke test sends a clearly labeled weak-trend sample through the gateway and n8n, verifies deduplication and validation errors, and waits for a scheduled rejection. It requires Telegram disabled. Tests use the separate `zebra_tests` database and mocked AI; the main journal is preserved.

The stack uses named volumes. `docker compose down` preserves them. **`docker compose down -v` deletes the database, workflows, and Docker model weights.** Native macOS model files in `.local/ollama` are separate. Back up `.env` with the volumes: the encryption key is required to decrypt n8n credentials. Deleting volumes also requires removing `.local/workflows-installed` before the next start.

## Connect TradingView

1. Give `http://localhost:8787` a public HTTPS tunnel, using a stable hostname for ongoing use. Only the exact generated webhook path is proxied; other paths return 404. Do not tunnel the n8n editor or analyzer ports.
2. Set `PUBLIC_WEBHOOK_URL=https://your-hostname/` in `.env`, then run `bash scripts/start.sh` to update local configuration. Your complete webhook URL is in `.local/webhook-url.txt`. The random path acts as a bearer secret: keep it private. The gateway rate-limits requests and caps the body at 16 KB. For an Internet deployment, add origin restrictions / source validation at your tunnel provider; path secrecy alone does not prove a request came from TradingView.
3. In TradingView, open an **XAUUSD 15-minute** chart, paste `tradingview/gold_setups.pine` into Pine Editor, save it, and add it to the chart.
4. Create an alert with condition **Cambotix Zebra → Any alert() function call**, then enter the generated HTTPS webhook URL. The script supplies JSON itself. Enable TradingView 2FA and use an account plan that supports webhook alerts.
5. Recreate the TradingView alert whenever you change Pine inputs or script code. TradingView alerts use the saved script snapshot.

Example development tunnel if `cloudflared` is already installed:

```bash
cloudflared tunnel --url http://localhost:8787
```

This creates a public endpoint. Copy its HTTPS hostname into `.env` and update TradingView if the hostname changes. A public tunnel is **not** launched by the setup script.

Pine emits on confirmed bar close when a setup first becomes valid. It uses EMA20/50/200, RSI14, MACD histogram, ADX through `ta.dmi`, ATR, and prior swing extremes. EMA/RSI/MACD/ADX/ATR gate the setup; swing levels are context only. Multi-timeframe confirmation, economic-calendar data, spread checks, and account risk checks are not implemented. The Pine source must be compiled in TradingView; no local Pine compiler is included.

## Telegram

Create a bot with Telegram's BotFather, start a private chat with the bot, and obtain your chat ID. Set these values in `.env` locally:

```dotenv
TELEGRAM_ENABLED=true
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
```

Then apply with `docker compose up -d analyzer`. Subsequent completed analyses will send messages to that chat. Old notifications marked `disabled` are not replayed. Bot tokens stay in the analyzer environment, never in Pine payloads or exported n8n workflows. Message formatting is plain text, so model text cannot inject Telegram HTML.

Delivery is deliberately conservative: an ambiguous network result becomes `unknown` and is not automatically resent. `failed` and `unknown` entries are visible in the journal and need manual inspection. This avoids duplicate notifications after a timeout; it cannot promise exactly-once delivery to Telegram.

## Configuration and behavior

Edit `.env`, then run `docker compose up -d analyzer` for filter/model/Telegram changes. Defaults:

| Setting | Default | Purpose |
|---|---|---|
| `MIN_CONFIDENCE` | 75 | Subjective AI score threshold, not win probability |
| `MIN_ADX` | 20 | Minimum trend strength |
| `MIN_ATR_PERCENT` / `MAX_ATR_PERCENT` | 0.02 / 0.5 | ATR divided by price, expressed as percent |
| `FILTER_SESSIONS` | true | London 08–17 or New York 08–17, weekdays, local DST |
| `MAX_SIGNAL_AGE_SECONDS` | 300 | Maximum age from confirmed bar close |
| `OLLAMA_MODEL` | qwen2.5:1.5b | Local model with schema-constrained JSON |
| `AI_TIMEOUT_SECONDS` | 120 | Maximum wait per AI attempt |

Use matching Pine indicator thresholds when adjusting rules. Only XAUUSD and 15m are accepted by this version. Incoming `bar_time` is the bar-close timestamp in **Unix seconds**, not milliseconds. Numeric fields must be finite JSON numbers. `macd_hist` means histogram, not the MACD line.

All rules and the AI gate must pass before a candidate is labeled `approved`. The AI must approve the existing direction, report a matching market regime and good/excellent quality, and meet the configured score threshold. `approved` means ready for **manual review**, never permission to place an order. No calibrated performance or profitability claim is made.

Signal identity is protected by both the primary event ID and a unique `(symbol, timeframe, bar_time, signal)` key. Concurrent inserts are atomic. A duplicate with changed values returns HTTP 409. Stale/invalid input returns 422, and database failures return 503 for retry. No successful acknowledgment is sent before database commit.

The processor holds a PostgreSQL advisory lock, recovers interrupted claims, and retries failed/invalid AI responses up to three times with 30-second backoff. Age is checked again after inference. Expired signals are rejected, including after downtime. The accepted-signal journal and notification outbox are committed together. Invalid incoming requests are not stored; accepted signal history is available via `scripts/history.py` (latest 100) or PostgreSQL.

macOS setup uses `OLLAMA_RUNTIME=native`, an empty `COMPOSE_PROFILES`, and `OLLAMA_BASE_URL=http://host.docker.internal:11435`. To use Docker Ollama instead, set `OLLAMA_RUNTIME=docker`, `COMPOSE_PROFILES=docker-ai`, and `OLLAMA_BASE_URL=http://ollama:11434`, then run the start script. Docker inference on this Mac uses CPU. For a different model, change `OLLAMA_MODEL` and rerun `bash scripts/start.sh` to pull it and update the analyzer. Changing the timeout also requires regenerating and reimporting the analysis workflow.

## Workflows and maintenance

The three JSON templates in `n8n/` contain no secrets. `scripts/setup.py` renders the actual webhook and header credential into ignored `.local/import/`. The start script imports them once, publishes them, restarts n8n, and removes the plaintext credential import. Repeated starts preserve workflow edits.

To deliberately replace the three project workflows after editing the generator, remove `.local/workflows-installed` and run `bash scripts/start.sh`. This overwrites these three workflow IDs. Export any UI edits you want to keep first. Rotate `WEBHOOK_PATH` using the same reimport procedure and update TradingView. Keep `N8N_ENCRYPTION_KEY` unchanged after initialization unless performing an n8n credential migration.

The pinned n8n image is version 2.26.9. Other service versions are fixed in `compose.yaml`; review updates periodically. No subscription or cloud AI key is required by this implementation. TradingView plan access, tunnel/domain arrangements, Docker licensing eligibility, electricity, and connectivity remain separate from the local software setup.

## References

- [TradingView webhook requirements](https://www.tradingview.com/support/solutions/43000529348-how-to-configure-webhook-alerts/) — public endpoint, JSON, response deadline, 2FA.
- [TradingView webhook retries](https://www.tradingview.com/support/solutions/43000735201-webhook-resubmission/) — retryable server responses.
- [Pine alerts](https://www.tradingview.com/pine-script-docs/concepts/alerts/) — bar-close alerts and saved snapshots.
- [Ollama structured outputs](https://docs.ollama.com/capabilities/structured-outputs) — JSON schema generation and validation.
- [n8n CLI](https://docs.n8n.io/hosting/cli-commands/) — import and publish workflows.
