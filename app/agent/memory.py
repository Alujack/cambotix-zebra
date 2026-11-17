"""Short conversation memory per authorized chat. It only provides context: it is passed as ordinary user/assistant
turns (never as instructions) and database facts always override it."""
import os


def turns() -> int:
    return max(0, int(os.getenv('AGENT_MEMORY_TURNS', '10')))


def recent(conn, chat_id: str) -> list[dict]:
    """The last AGENT_MEMORY_TURNS question/answer pairs of this chat, oldest first."""
    rows = conn.execute('''SELECT role, message FROM agent_messages WHERE chat_id=%s
        AND created_at >= now() - make_interval(days => %s) ORDER BY id DESC LIMIT %s''',
        (chat_id, retention_days(), turns() * 2)).fetchall()
    return [{'role': row['role'], 'content': row['message']} for row in reversed(rows)]


def remember(conn, chat_id: str, question: str, answer: str):
    if turns():
        conn.execute("INSERT INTO agent_messages(chat_id, role, message) VALUES (%s,'user',%s), (%s,'assistant',%s)",
                     (chat_id, question[:2000], chat_id, answer[:4000]))


def retention_days() -> int:
    return max(1, int(os.getenv('AGENT_MEMORY_RETENTION_DAYS', '30')))


def prune(conn) -> int:
    """Delete conversation turns and processed updates older than the retention period."""
    days = retention_days()
    removed = conn.execute('DELETE FROM agent_messages WHERE created_at < now() - make_interval(days => %s)', (days,)).rowcount
    conn.execute("""DELETE FROM agent_updates WHERE created_at < now() - make_interval(days => %s)
        AND status IN ('answered', 'ignored', 'failed', 'unknown')""", (days,))
    return removed


def forget(conn, chat_id: str):
    conn.execute('DELETE FROM agent_messages WHERE chat_id=%s', (chat_id,))
