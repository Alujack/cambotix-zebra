import os


def telegram_enabled() -> bool:
    return os.getenv('TELEGRAM_ENABLED', 'false').lower() == 'true'


def queue_message(conn, ref: str, kind: str, chat: str, text: str):
    """Add one message to the Telegram outbox (sent by /notify). A ref is queued at most once."""
    conn.execute('''INSERT INTO messages(ref, kind, chat, message, status) VALUES (%s,%s,%s,%s,%s)
        ON CONFLICT DO NOTHING''', (ref, kind, chat, text, 'pending' if telegram_enabled() else 'disabled'))
