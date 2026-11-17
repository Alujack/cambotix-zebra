import pytest

from app.agent import telegram


def message(chat_id=111, chat_type='private', user_id=111, is_bot=False):
    return {'chat': {'id': chat_id, 'type': chat_type}, 'from': {'id': user_id, 'is_bot': is_bot}, 'text': 'hi'}


@pytest.fixture(autouse=True)
def owner(monkeypatch):
    monkeypatch.setenv('TELEGRAM_CHAT_ID', '111')
    monkeypatch.delenv('TELEGRAM_ALLOWED_USER_ID', raising=False)


def test_only_the_owner_private_chat_is_allowed(monkeypatch):
    assert telegram.allowed(message())
    assert not telegram.allowed(message(chat_id=222, user_id=222))              # a stranger
    assert not telegram.allowed(message(chat_id=111, chat_type='group'))         # a group with the same id
    assert not telegram.allowed(message(chat_id=-100111, chat_type='supergroup', user_id=111))  # owner in a group
    assert not telegram.allowed(message(is_bot=True))
    assert not telegram.allowed({})


def test_explicit_user_id_and_missing_configuration(monkeypatch):
    monkeypatch.setenv('TELEGRAM_ALLOWED_USER_ID', '999')
    assert not telegram.allowed(message())
    monkeypatch.setenv('TELEGRAM_CHAT_ID', '')
    monkeypatch.delenv('TELEGRAM_ALLOWED_USER_ID')
    assert not telegram.allowed(message(chat_id='', user_id=''))
