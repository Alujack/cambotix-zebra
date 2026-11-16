planBro, here's the complete implementation roadmap for **Zebra AI Agent — Ollama \+ OpenAI Astra \+ Telegram \+ MT5**.

My recommendation is to build this as a production feature inside your existing Zebra system, not as a separate chatbot project.

The goal is a reliable AI assistant that understands your trading records, explains signals, analyzes performance, and generates weekly reports — without ever controlling trades.

# **Zebra AI Agent — Complete Implementation Plan**

Target architecture

# **Zebra AI Agent**

Local intelligence \+ cloud reasoning \+ deterministic trading infrastructure

**Telegram Personal Assistant**

Commands · Questions · Reports · Notifications

**Ollama**

Local / Free

Classification, simple answers, commentary

**OpenAI Astra**

Paid

Deep analysis, strategy research, weekly reports

**Read-only Data Layer**

PostgreSQL · MT5 records · Signals · Candles · News

**Trading execution remains completely separate**

Existing deterministic trading rules retain full authority.

## **Phase 1 — Foundation and architecture**

**Goal:** Prepare the existing system for AI without breaking current trading functionality.

Tasks:

1. Create branch `feat/ai-agent`.  
2. Inspect existing repository structure and current trading pipeline.  
3. Identify existing database tables and MT5 integration.  
4. Identify existing Ollama integration, if any.  
5. Document current signal approval and rejection logic.  
6. Document trade grading and notification lifecycle.  
7. Define strict interfaces between AI and trading modules.

Proposed structure:

```
app/
├── ai/
│   ├── llm.py
│   ├── ollama.py
│   ├── openai_client.py
│   ├── classifier.py
│   ├── prompts.py
│   ├── schemas.py
│   └── usage.py
│
├── agent/
│   ├── telegram.py
│   ├── router.py
│   ├── commands.py
│   ├── handlers.py
│   ├── memory.py
│   ├── tools.py
│   ├── weekly_report.py
│   └── queue.py
│
├── services/
│   ├── trading_service.py
│   ├── analytics_service.py
│   └── news_service.py
│
├── main.py
├── ledger.py
└── domain.py
```

Do not blindly create these files before inspecting the existing project. Reuse existing services and avoid duplicate abstractions.

**Acceptance criteria:**

* Existing tests still pass.  
* No changes to trading decisions.  
* AI modules can be disabled independently.

## **Phase 2 — Ollama integration**

**Goal:** Run frequent AI operations locally without paying API fees.

### **2.1 Install and configure Ollama**

Recommended initial configuration:

| Setting | Value |
| ----- | ----- |
| Runtime | Ollama |
| Initial model | `qwen2.5:3b` |
| Upgrade model | `qwen2.5:7b` |
| Temperature | 0.1–0.3 |
| Output | JSON or short text |
| Timeout | Configurable |
| Fallback | Skip AI commentary |

Model selection must be based on actual VPS RAM and inference performance.

### **2.2 Implement Ollama services**

Create:

* `ollama.py`: Local model communication.  
* `classifier.py`: Classify Telegram questions.  
* `prompts.py`: Centralized prompts.  
* `schemas.py`: Validate structured outputs.

Ollama handles:

| Task | Output |
| ----- | ----- |
| Signal commentary | Short explanation |
| Trade closing commentary | 1–2 lines |
| Question classification | SIMPLE / DEEP / COMMAND |
| Simple questions | Answer using supplied data |
| Message summarization | Short summaries |

### **2.3 Signal commentary**

The workflow:

```
MT5 signal
    ↓
Existing trading rules
    ↓
APPROVED / REJECTED
    ↓
Save decision in database
    ↓
Ollama receives decision + evidence
    ↓
Validate commentary
    ↓
Telegram notification
```

Example:

```
🦓 ZEBRA SIGNAL REVIEW

Symbol: XAUUSD
Session: London
Decision: APPROVED

Reason:
Price swept the previous range low.
Bullish displacement confirmed.
Entry conditions satisfied.

AI Commentary:
The setup has a valid liquidity sweep,
followed by bullish confirmation.

⚠️ AI commentary only.
```

Important: If Ollama fails, the original signal notification must still be delivered.

### **2.4 Testing**

* Ollama available.  
* Ollama unavailable.  
* Timeout.  
* Invalid JSON.  
* Empty response.  
* Unexpected model output.  
* Slow inference.  
* Incorrect signal commentary.

**Acceptance criteria:** Ollama must never alter trading decisions or block trading notifications.

## **Phase 3 — AI usage tracking and cost control**

**Goal:** Know exactly how much your AI assistant costs.

Create the `ai_usage` table.

Suggested fields:

| Field | Purpose |
| ----- | ----- |
| id | Unique ID |
| provider | ollama / openai |
| model | Model identifier |
| job | Classification / deep analysis / report |
| input\_tokens | Input usage |
| output\_tokens | Output usage |
| estimated\_cost | Estimated USD |
| actual\_cost | Actual billed cost when available |
| status | Success / failed |
| created\_at | Timestamp |

### **Budget management**

Configuration:

```
OPENAI_DAILY_LIMIT=20
OPENAI_MONTHLY_BUDGET_USD=10
OPENAI_SAFETY_RESERVE_USD=1
```

Implement:

1. Daily request counting.  
2. Monthly cost tracking.  
3. Atomic budget reservation.  
4. Token usage recording.  
5. Retry accounting.  
6. Tool-loop call accounting.  
7. Budget rejection before API requests.  
8. Cost reporting.

A failed request may still consume API tokens, so never assume failures are free.

### **`/cost` command**

Example:

```
💰 ZEBRA AI USAGE

TODAY
OpenAI calls: 3
Estimated cost: $0.24

THIS MONTH
OpenAI calls: 47
Estimated cost: $4.20

Monthly budget: $10.00
Safety reserve: $1.00
Available budget: $4.80

OLLAMA
Requests: 1,245
API cost: $0.00
```

The example values are illustrative, not actual usage.

**Acceptance criteria:** Concurrent requests cannot bypass the monthly budget.

## **Phase 4 — Telegram agent and commands**

**Goal:** Create a personal trading assistant accessible through Telegram.

### **Commands**

| Command | Function | Handler |
| ----- | ----- | ----- |
| `/start` | Initialize assistant | Code |
| `/help` | Show commands | Code |
| `/open` | Show open trades | Code |
| `/price XAUUSDm` | Latest available price | Code |
| `/record 30` | Trading performance | Code |
| `/signals 5` | Recent signals | Code |
| `/news` | Today's economic news | Code |
| `/cost` | AI expenditure | Code |
| `/deep question` | Deep analysis | Astra |
| `/status` | System health | Code |

I recommend adding `/status` because you need to know whether Ollama, OpenAI, PostgreSQL and the MT5 data pipeline are working.

### **Telegram architecture**

```
Telegram
    ↓
Update receiver
    ↓
Validate chat + sender
    ↓
Deduplicate update
    ↓
Command router
    ├── Commands → Database
    ├── Simple → Ollama
    └── Deep → Astra
    ↓
Telegram response
```

### **Database tables**

`agent_state`

* chat\_id  
* last\_processed\_update\_id  
* updated\_at

`agent_messages`

* id  
* chat\_id  
* role  
* message  
* created\_at

**Important:** Process Telegram updates idempotently. Persist the update ID and message processing status safely so restarts or overlapping n8n executions cannot cause duplicate responses.

You can keep your existing n8n workflow if it works, but I recommend a dedicated Telegram polling worker with a single active polling owner. If you retain the 10-second n8n schedule, enforce a lock and deduplication.

### **Simple question example**

User:

> How many trades did we win this week?

Process:

1. Code fetches trading statistics.  
2. Code prepares a compact data snapshot.  
3. Ollama receives the snapshot.  
4. Ollama generates a natural-language response.  
5. Telegram sends the response.

Ollama does not need database access.

## **Phase 5 — Astra deep reasoning integration**

**Goal:** Give the assistant the ability to investigate trading performance using controlled tools.

This is the most important AI engineering phase.

### **5.1 Build read-only tools**

| Tool | Function |
| ----- | ----- |
| `get_track_record` | Historical performance |
| `get_signals` | Recent signals |
| `get_signal` | Individual signal details |
| `get_open_trades` | Active trades |
| `get_closed_trades` | Closed trades |
| `get_candles` | Market candle summaries |
| `get_news` | Economic news |

Each tool must call a predefined service function with validated arguments.

No unrestricted SQL.

No write operations.

No settings changes.

### **5.2 Astra tool loop**

```
User asks deep question
        ↓
Check budget
        ↓
Send question + available tools to Astra
        ↓
Astra requests tool
        ↓
Validate tool name + arguments
        ↓
Execute read-only function
        ↓
Return tool result
        ↓
Astra analyzes information
        ↓
Validate final answer
        ↓
Telegram response
```

Limits:

* Maximum 5 tool calls per question.  
* Maximum 8,000 characters of tool output.  
* Maximum execution time.  
* Maximum input/output token limits.  
* Restricted tool allowlist.  
* No recursive unlimited tool execution.

Also, distinguish tool-call count from HTTP/API request count. One reasoning request can involve several API round trips.

### **5.3 Deep question examples**

* Why are we losing on gold during London?  
* Which session has the highest expectancy?  
* Are our rejected signals better than approved signals?  
* Does our CRT strategy perform better during New York?  
* What patterns appear before consecutive losses?  
* Is our performance deteriorating compared with last month?

Astra must explain the evidence behind its conclusions and disclose insufficient sample sizes.

### **5.4 Model configuration**

```
OPENAI_API_KEY=
OPENAI_MODEL=
OPENAI_REASONING_EFFORT=low
OPENAI_DAILY_LIMIT=20
OPENAI_MONTHLY_BUDGET_USD=10
```

One correction: don't assume `gpt-6-astra` is an API model ID just because Astra is the name used in your plan. Verify the actual model identifier and Responses API compatibility against the current API documentation and your account before deployment.

**Acceptance criteria:** Astra can investigate records but cannot modify them.

## **Phase 6 — Trade closing commentary**

**Goal:** Generate an AI explanation after every completed trade.

Workflow:

```
Trade closes
    ↓
Grader calculates result
    ↓
Database saves result
    ↓
Telegram sends result immediately
    ↓
Queue AI commentary
    ↓
Ollama analyzes trade
    ↓
Validate response
    ↓
Send additional commentary
```

Example:

```
🦓 TRADE CLOSED

Symbol: XAUUSD
Result: WIN
Exit: TP1
Duration: 2 candles
R: +1.5R

📝 AI REVIEW
Price swept the range low before
reversing and reaching TP1.
```

The actual trade details must come from your grader, not Ollama.

### **Additional information for analysis**

Provide Ollama with:

* Entry price.  
* Exit price.  
* SL and TP.  
* Trade direction.  
* Session.  
* Candle summaries.  
* Signal reason.  
* Actual exit reason.  
* Duration.  
* Result in R.

Keep commentary short. Do not let AI invent candle events that aren't present in the data.

**Acceptance criteria:** Trade grading and notification delivery work even when Ollama is completely offline.

## **Phase 7 — Weekly performance report**

**Goal:** Let Astra act as your weekly trading analyst.

**Every Sunday — 09:00 Phnom Penh time**

### **Report generation pipeline**

```
Sunday scheduler
      ↓
Fetch weekly trading data
      ↓
SQL/Python calculates statistics
      ↓
Compare with previous weeks
      ↓
Prepare structured report
      ↓
Astra interprets results
      ↓
Validate report
      ↓
Send Telegram digest
```

### **Report contents**

| Section | Information |
| ----- | ----- |
| Weekly summary | Total trades, wins, losses |
| Performance | Win rate, total R, profit factor |
| Session analysis | London vs New York |
| Symbol analysis | Gold performance |
| Setup analysis | Which setup performed best |
| Losing patterns | Repeated conditions |
| Caution analysis | Performance with/without cautions |
| Recommendations | 1–3 backtesting suggestions |

Example:

```
🦓 ZEBRA WEEKLY REPORT

Period: Nov 9 – Nov 15

PERFORMANCE
Total trades: 18
Wins: 11
Losses: 7
Win rate: 61.1%
Net result: +5.2R

SESSION ANALYSIS
London: +3.5R
New York: +1.7R

OBSERVATIONS
• London performed better this week.
• Two consecutive losses occurred during
  low-volatility conditions.
• Results with caution labels were weaker.

AI RECOMMENDATIONS
1. Investigate low-volatility setups.
2. Compare session performance over
   the last 8 weeks.
3. Backtest the caution filter.

⚠️ Suggestions are not trading instructions.
```

Use actual database values, not fabricated examples.

### **Important additions**

* Compare at least 4 weeks when available.  
* Include sample sizes.  
* Identify missing or incomplete data.  
* Don't draw conclusions from tiny samples.  
* Store generated reports for future comparison.  
* Avoid duplicate reports if the scheduler runs twice.

**Acceptance criteria:** Every statistic is calculated independently and verified before Astra receives it.

## **Phase 8 — Memory and optional RAG**

This phase has two separate features.

### **8.1 Conversation memory**

Use `agent_messages` to preserve the last 10 turns.

Example:

```
User: Why is London losing?

Bot: London has a negative result over
the last 30 days...

User: What about New York?

Bot: New York has a positive result...
```

The bot understands that the second question refers to the same analysis period.

Recommended rules:

* Maximum 10 conversation turns.  
* Delete messages older than 30 days.  
* Separate memory by authorized chat/user.  
* Never treat previous user messages as system instructions.  
* Never store API keys or secrets.  
* Don't let conversational memory override actual database records.

### **8.2 RAG — Later release**

Post-MVP

RAG allows the assistant to answer questions about your own trading documentation.

Possible sources:

* ICT Khmer book.  
* CRT strategy documentation.  
* Your trading rules.  
* Previous weekly reports.  
* Strategy research notes.

Architecture:

**Knowledge ingestion**

Documents → Text extraction → Chunking  
Ollama embeddings → PostgreSQL \+ pgvector

**Question answering**

User question → Retrieve relevant chunks → Ollama → Answer with citations

Recommended initial embedding model: `nomic-embed-text`.

Don't upgrade your production PostgreSQL image to a pgvector image without checking existing database compatibility, extensions, volumes and backup/restore procedures.

## **Phase 9 — Security and reliability**

This phase should not be postponed until the end. Implement security controls throughout development and perform a dedicated security review here.

### **Security requirements**

| Area | Requirement |
| ----- | ----- |
| Telegram | Allowlisted private chat and sender |
| OpenAI key | VPS environment secret |
| Ollama | Private network access |
| Database | Read-only AI database role where possible |
| SQL | Parameterized fixed queries |
| AI tools | Explicit allowlist |
| Prompts | Untrusted input isolation |
| Logs | No secrets or sensitive tokens |
| Memory | Retention and access controls |
| API | Timeouts and request limits |
| Budget | Atomic reservation |
| Deployment | Backups and rollback |

### **Failure handling**

| Failure | Expected behavior |
| ----- | ----- |
| Ollama offline | Skip AI commentary |
| Astra offline | Return deep-analysis unavailable |
| PostgreSQL offline | Return data unavailable |
| Telegram unavailable | Retry safely without duplicate messages |
| Budget exhausted | Block Astra requests |
| Invalid AI response | Reject response |
| News unavailable | Clearly indicate missing news data |
| Worker crashes | Resume unprocessed jobs safely |

### **Observability**

Create structured logs and system health monitoring.

Track:

* Ollama response latency.  
* OpenAI response latency.  
* AI request success rate.  
* Tool-call failures.  
* Telegram delivery failures.  
* Queue depth.  
* Monthly spending.  
* Database query failures.

Add `/status` to expose a safe summary of service health.

## **Phase 10 — Testing and quality assurance**

This is not optional. A trading assistant that produces incorrect data is worse than having no assistant.

### **Test structure**

```
tests/
├── ai/
│   ├── test_ollama.py
│   ├── test_openai.py
│   ├── test_classifier.py
│   ├── test_usage.py
│   └── test_schemas.py
│
├── agent/
│   ├── test_commands.py
│   ├── test_router.py
│   ├── test_memory.py
│   ├── test_tools.py
│   └── test_telegram.py
│
├── trading/
│   ├── test_signal_unchanged.py
│   ├── test_trade_grading.py
│   └── test_notifications.py
│
├── reports/
│   └── test_weekly_report.py
│
└── integration/
    ├── test_agent_flow.py
    ├── test_failure_recovery.py
    └── test_budget_limits.py
```

### **Critical test scenarios**

| Test | Expected result |
| ----- | ----- |
| Ollama crashes during signal | Signal still sent |
| Ollama takes 30 seconds | No notification delay |
| Astra budget exhausted | No API call |
| Two Astra requests simultaneously | Budget remains protected |
| Telegram sends duplicate update | One response only |
| User from unauthorized chat | No access |
| AI attempts to modify trade | Operation rejected |
| Astra requests unrestricted SQL | Operation rejected |
| Invalid model response | Response discarded |
| Worker restarts | Pending jobs recover |
| Weekly report runs twice | One report delivered |
| Old memory exceeds retention | Deleted automatically |

### **Testing strategy**

1. Unit tests with mocked AI providers.  
2. Database integration tests using `zebra_tests`.  
3. Telegram integration tests.  
4. Docker testing.  
5. Failure simulation.  
6. Real local Ollama testing.  
7. Small controlled OpenAI API tests.  
8. Regression testing against existing trading behavior.

Do not test production trading decisions by placing live trades.

Release requirement  
All existing tests and new regression tests must pass before deployment.

## **Phase 11 — Docker and VPS deployment**

**Goal:** Run the complete agent reliably on your VPS.

### **Deployment architecture**

```
VPS
│
├── Zebra API
│
├── Telegram Agent Worker
│
├── AI Worker
│   ├── Ollama
│   └── OpenAI API Client
│
├── PostgreSQL
│
├── n8n
│
└── Scheduler
    └── Weekly Report
```

Keep Ollama, workers and the API logically separated, even if they initially run on the same VPS.

### **VPS preparation**

Before deploying:

```
free -h
df -h
docker stats
docker compose ps
```

Check:

* Available RAM.  
* CPU capacity.  
* Disk space.  
* Existing Docker workloads.  
* PostgreSQL resource usage.  
* Network connectivity.

Then download the chosen model:

```
ollama pull qwen2.5:3b
```

Test:

```
ollama run qwen2.5:3b
```

If resources permit, compare 7B before selecting the production model.

### **Deployment environment**

```
# AI
AI_COMMENTARY=true
TRADE_NOTES=true

OLLAMA_BASE_URL=http://ollama:11434
OLLAMA_MODEL=qwen2.5:3b

# OpenAI
OPENAI_API_KEY=
OPENAI_MODEL=
OPENAI_REASONING_EFFORT=low
OPENAI_DAILY_LIMIT=20
OPENAI_MONTHLY_BUDGET_USD=10

# Telegram
AGENT_ENABLED=false
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
TELEGRAM_ALLOWED_USER_ID=

# Memory
AGENT_MEMORY_TURNS=10
AGENT_MEMORY_RETENTION_DAYS=30

# Weekly report
WEEKLY_REPORT_ENABLED=true
WEEKLY_REPORT_DAY=sun
WEEKLY_REPORT_HOUR=9
WEEKLY_REPORT_TIMEZONE=Asia/Phnom_Penh
```

Use your existing environment variables where possible. Never commit real credentials.

### **Deployment sequence**

1. Back up PostgreSQL.  
2. Deploy database migrations.  
3. Deploy application changes.  
4. Start Ollama.  
5. Pull and test the model.  
6. Start Telegram worker.  
7. Verify OpenAI connectivity and budget enforcement.  
8. Test Telegram commands.  
9. Import or update the n8n workflow if retained.  
10. Enable the agent.  
11. Monitor logs and resource usage.

Use a rollback plan if anything breaks.

## **Phase 12 — Production launch and monitoring**

Don't enable everything at once.

Use three rollout stages.

1. **Stage 1 — Internal testing**  
   AGENT\_ENABLED=false  
   * Test mocked AI responses.  
   * Test real Ollama.  
   * Test OpenAI API.  
   * Test all Telegram commands.  
   * Test database permissions.  
2. **Stage 2 — Controlled production**  
   Limited rollout  
   * Enable personal Telegram access.  
   * Enable Ollama commentary.  
   * Enable simple questions.  
   * Enable Astra with a small request limit.  
   * Monitor failures and spending.  
3. **Stage 3 — Full production**  
   Production  
   * Enable weekly reports.  
   * Enable trade closing commentary.  
   * Enable full Astra tools.  
   * Enable monitoring and alerts.  
   * Review performance after 7 days.

## **13\. Complete project milestone tracker**

Here is the implementation checklist in execution order.

**Implementation progress**

# **0%**

0 / 45 tasks completed

**1\. Foundation and architecture**

0/4  
Inspect existing Zebra architecture  
Create feature branch  
Define AI/trading boundaries  
Design interfaces

**2\. Ollama integration**

0/5  
Configure Ollama  
Implement local LLM client  
Build classifier  
Implement signal commentary  
Test failure handling

**3\. Usage and budget**

0/4  
Create usage ledger  
Implement token tracking  
Implement atomic budget reservation  
Build /cost

**4\. Telegram agent**

0/4  
Build secure update receiver  
Implement commands  
Implement message deduplication  
Implement conversation memory

**5\. Astra integration**

0/4  
Build read-only tools  
Implement Responses API client  
Implement tool loop  
Implement budget and output validation

**6\. Trade commentary**

0/3  
Create asynchronous job queue  
Implement trade-close note  
Test immediate notifications

**7\. Weekly report**

0/4  
Calculate trading statistics  
Build comparison engine  
Generate Astra analysis  
Schedule Sunday report

**8\. Security and reliability**

0/4  
Security review  
Rate limiting  
Health checks  
Logging and recovery

**9\. Testing**

0/4  
Unit tests  
Integration tests  
Regression tests  
Docker failure simulations

**10\. Deployment**

0/5  
Check VPS resources  
Deploy migrations  
Deploy AI services  
Enable controlled production  
Monitor first 7 days

**11\. RAG (later)**

0/4  
Install pgvector safely  
Build document ingestion  
Generate embeddings  
Implement retrieval and citations  
Reset checklist

*This is an interactive planning checklist; it does not automatically update from your GitHub repository.*

## **14\. Final technical decisions**

These are the defaults I recommend adopting.

| Decision | Default |
| ----- | ----- |
| Architecture | Existing Zebra \+ modular AI services |
| Local AI | Ollama |
| Initial model | Qwen2.5 3B |
| Cloud AI | OpenAI Responses API |
| Deep reasoning | Astra, subject to API model verification |
| Telegram | Private authorized chat |
| Data access | Read-only |
| Signal approval | Existing rules only |
| Trade execution | No AI access |
| Daily OpenAI limit | 20 |
| Monthly budget | \$10 |
| Memory | 10 turns / 30 days |
| Weekly report | Sunday 09:00 Phnom Penh |
| RAG | Release 2 |
| Deployment | Docker on existing VPS |

## **15\. Estimated development timeline**

Assuming one developer working on the existing codebase:

| Milestone | Estimated duration |
| ----- | ----- |
| Foundation | 1–2 days |
| Ollama | 1–2 days |
| Usage and budget | 1 day |
| Telegram commands | 2 days |
| Astra tools | 2–3 days |
| Trade commentary | 1 day |
| Weekly report | 1–2 days |
| Security and testing | 2–3 days |
| Deployment | 1–2 days |
| **Total MVP** | **12–18 working days** |

RAG is additional. These estimates assume the existing Zebra codebase and database are reasonably stable. If the existing architecture needs significant refactoring, expect longer.

# **My final recommendation**

Build the project in this order:

1. Get Ollama working.  
2. Get Telegram commands working.  
3. Connect Astra with read-only tools.  
4. Implement reliable cost control.  
5. Add asynchronous trade commentary.  
6. Add weekly reporting.  
7. Test and deploy.  
8. Add RAG later.

Don't start with RAG, advanced agent frameworks, LangChain or multi-agent orchestration. They add complexity without solving your immediate problems.

**Keep the first release boring, reliable and measurable.**

## **What I need before implementation**

The one thing I don't want you to do is let Cursor or Claude start generating 30 files without understanding the existing Zebra project.

First, inspect the existing repository, database schema, trading pipeline, and deployment configuration. Then create the implementation tasks against the actual codebase.

My suggested first instruction to your coding agent:

> Inspect the entire Zebra repository. Do not modify any files. Map the current architecture, signal approval flow, MT5 integration, trade grading, Telegram notification system, PostgreSQL schema, n8n workflows, Docker deployment and existing Ollama integration. Identify reusable components and potential conflicts with the proposed AI agent. Produce a technical implementation report and phased file-by-file change plan. Wait for approval before coding.

That inspection is the real starting point.

