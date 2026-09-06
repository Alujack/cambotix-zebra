CREATE DATABASE n8n;
CREATE TABLE IF NOT EXISTS signals (
    event_id text PRIMARY KEY,
    symbol text NOT NULL,
    timeframe text NOT NULL,
    bar_time bigint NOT NULL,
    signal text NOT NULL CHECK (signal IN ('BUY_SETUP', 'SELL_SETUP')),
    payload jsonb NOT NULL,
    status text NOT NULL DEFAULT 'queued'
      CHECK (status IN ('queued', 'processing', 'approved', 'rejected', 'error')),
    attempts integer NOT NULL DEFAULT 0,
    next_attempt_at timestamptz NOT NULL DEFAULT now(),
    received_at timestamptz NOT NULL DEFAULT now(),
    started_at timestamptz,
    completed_at timestamptz,
    analysis jsonb,
    rule_reasons jsonb,
    error_code text,
    UNIQUE (symbol, timeframe, bar_time, signal)
);
CREATE INDEX IF NOT EXISTS signals_queue_idx ON signals (next_attempt_at, received_at) WHERE status = 'queued';
CREATE TABLE IF NOT EXISTS notifications (
    event_id text PRIMARY KEY REFERENCES signals(event_id),
    message text NOT NULL,
    status text NOT NULL CHECK (status IN ('disabled', 'pending', 'sending', 'sent', 'failed', 'unknown')),
    error_code text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
