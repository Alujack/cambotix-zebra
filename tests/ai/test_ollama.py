import httpx
import pytest

from app.ai import ollama
from tests.fakes import install


@pytest.fixture(autouse=True)
def recorded(monkeypatch):
    calls = []
    monkeypatch.setattr(ollama.usage, 'record_local', lambda *args, **kwargs: calls.append((args, kwargs)))
    return calls


def test_reply_text_and_usage_are_recorded(monkeypatch, recorded):
    calls = install(monkeypatch, ollama, [{'message': {'content': ' hello '}, 'prompt_eval_count': 12, 'eval_count': 3}])
    assert ollama.chat('route', [{'role': 'user', 'content': 'hi'}], schema={'type': 'object'}) == 'hello'
    body = calls[0]['json']
    assert calls[0]['url'].endswith('/api/chat') and body['format'] == {'type': 'object'} and body['stream'] is False
    (job, model, ok, tokens_in, tokens_out, _), _ = recorded[0]
    assert (job, ok, tokens_in, tokens_out) == ('route', True, 12, 3)


@pytest.mark.parametrize('reply,code', [
    (httpx.ReadTimeout('slow'), 'timeout'),
    (httpx.ConnectError('offline'), 'unavailable'),
    (httpx.Response(500, json={}), 'unavailable'),
    ({'message': {'content': '   '}}, 'empty_response'),
    ({'unexpected': True}, 'unavailable'),
    (httpx.Response(200, content=b'not json'), 'unavailable'),
])
def test_failures_raise_a_short_code_and_are_recorded(monkeypatch, recorded, reply, code):
    install(monkeypatch, ollama, [reply])
    with pytest.raises(ollama.LocalAIError) as error:
        ollama.chat('trade_note', [])
    assert error.value.code == code
    (_, _, ok, *_), kwargs = recorded[0]
    assert ok is False


def test_availability_needs_the_configured_model(monkeypatch):
    monkeypatch.setenv('OLLAMA_MODEL', 'qwen2.5:3b')
    install(monkeypatch, ollama, [{'models': [{'name': 'qwen2.5:3b'}]}, {'models': [{'name': 'other:1b'}]},
                                  httpx.ConnectError('down')])
    assert ollama.available() == (True, 'qwen2.5:3b ready')
    assert ollama.available() == (False, 'qwen2.5:3b not pulled')
    assert ollama.available() == (False, 'not reachable')
