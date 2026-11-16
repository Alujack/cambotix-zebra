"""Telegram Bot API calls. The bot token is part of every URL, so no URL or raw error is ever logged or stored."""
import os

import httpx


def deliver(token: str, chat_id: str, text: str) -> tuple[str, str | None]:
    """('sent' | 'failed' | 'unknown', error code). 'unknown' means it may have arrived: never resend it."""
    try:
        with httpx.Client(timeout=15) as client:
            result = client.post(f'https://api.telegram.org/bot{token}/sendMessage', json={'chat_id': chat_id, 'text': text})
            result.raise_for_status()
            if result.json().get('ok') is not True:
                return 'failed', 'telegram_rejected'
    except httpx.HTTPStatusError as exc:
        return ('failed' if 400 <= exc.response.status_code < 500 else 'unknown'), 'telegram_http_error'
    except (httpx.HTTPError, ValueError):
        return 'unknown', 'telegram_result_unknown'
    return 'sent', None


def updates(token: str, offset: int | None) -> list[dict]:
    """New message updates after `offset` (non-blocking). Raises httpx.HTTPError or ValueError on failure."""
    params = {'timeout': 0, 'limit': 20, 'allowed_updates': '["message"]'}
    if offset is not None:
        params['offset'] = offset
    with httpx.Client(timeout=15) as client:
        response = client.post(f'https://api.telegram.org/bot{token}/getUpdates', json=params)
        response.raise_for_status()
        data = response.json()
    if data.get('ok') is not True or not isinstance(data.get('result'), list):
        raise ValueError('telegram_rejected')
    return data['result']


def allowed(message: dict) -> bool:
    """Only the owner's private chat: TELEGRAM_CHAT_ID, and TELEGRAM_ALLOWED_USER_ID (default: the same id)."""
    chat_id = os.getenv('TELEGRAM_CHAT_ID', '').strip()
    user_id = os.getenv('TELEGRAM_ALLOWED_USER_ID', '').strip() or chat_id
    chat, sender = message.get('chat') or {}, message.get('from') or {}
    return (bool(chat_id) and chat.get('type') == 'private' and str(chat.get('id')) == chat_id
            and str(sender.get('id')) == user_id and not sender.get('is_bot'))
