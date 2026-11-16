"""Tables of the AI layer and the Telegram agent. None of them is read by the technical rules or the grader."""

SCHEMA = '''
CREATE TABLE IF NOT EXISTS ai_usage (
    id bigserial PRIMARY KEY,
    job_id text NOT NULL,
    provider text NOT NULL CHECK (provider IN ('ollama', 'openai')),
    model text NOT NULL,
    job text NOT NULL,
    input_tokens integer NOT NULL DEFAULT 0,
    output_tokens integer NOT NULL DEFAULT 0,
    reserved_usd numeric(12, 6) NOT NULL DEFAULT 0,
    estimated_cost numeric(12, 6),
    actual_cost numeric(12, 6),
    status text NOT NULL CHECK (status IN ('reserved', 'ok', 'failed')),
    error_code text,
    latency_ms integer,
    created_at timestamptz NOT NULL DEFAULT now(),
    settled_at timestamptz
);
CREATE INDEX IF NOT EXISTS ai_usage_provider_created_idx ON ai_usage (provider, created_at);
CREATE TABLE IF NOT EXISTS ai_jobs (
    id bigserial PRIMARY KEY,
    kind text NOT NULL CHECK (kind IN ('signal_note', 'trade_note')),
    ref text NOT NULL,
    status text NOT NULL DEFAULT 'queued' CHECK (status IN ('queued', 'running', 'done', 'failed', 'skipped')),
    attempts integer NOT NULL DEFAULT 0,
    next_attempt_at timestamptz NOT NULL DEFAULT now(),
    error_code text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (kind, ref)
);
CREATE INDEX IF NOT EXISTS ai_jobs_queue_idx ON ai_jobs (next_attempt_at) WHERE status = 'queued';
CREATE TABLE IF NOT EXISTS ai_reports (
    ref text PRIMARY KEY,
    period_start bigint NOT NULL,
    period_end bigint NOT NULL,
    stats jsonb NOT NULL,
    analysis text,
    status text NOT NULL CHECK (status IN ('generating', 'queued')),
    error_code text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS agent_state (
    bot text PRIMARY KEY,
    last_update_id bigint NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS agent_updates (
    update_id bigint PRIMARY KEY,
    chat_id text,
    user_id text,
    chat_type text,
    text text,
    status text NOT NULL DEFAULT 'received'
      CHECK (status IN ('received', 'processing', 'replying', 'answered', 'ignored', 'failed', 'unknown')),
    attempts integer NOT NULL DEFAULT 0,
    route text,
    reply text,
    error_code text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS agent_updates_pending_idx ON agent_updates (update_id) WHERE status = 'received';
CREATE TABLE IF NOT EXISTS agent_messages (
    id bigserial PRIMARY KEY,
    chat_id text NOT NULL,
    role text NOT NULL CHECK (role IN ('user', 'assistant')),
    message text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS agent_messages_chat_idx ON agent_messages (chat_id, id);
'''


def migrate(conn) -> None:
    conn.execute(SCHEMA)
