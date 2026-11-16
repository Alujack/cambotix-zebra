import httpx
import pytest

from app.ai import openai_client, usage
from tests.fakes import install

DONE = {'status': 'completed', 'usage': {'input_tokens': 1000, 'output_tokens': 200,
                                          'input_tokens_details': {'cached_tokens': 100}},
        'output': [{'type': 'reasoning', 'id': 'r1'},
                   {'type': 'message', 'content': [{'type': 'output_text', 'text': 'Answer.'}]}]}


@pytest.fixture
def ledger(monkeypatch):
    """Budget calls recorded in memory instead of the database."""
    state = {'reserved': [], 'settled': [], 'refuse': None}

    def reserve(job_id, job, model, amount):
        if state['refuse']:
            raise usage.BudgetRefused(state['refuse'])
        state['reserved'].append((job_id, job, model, amount))
        return len(state['reserved'])

    monkeypatch.setattr(usage, 'reserve', reserve)
    monkeypatch.setattr(usage, 'settle', lambda usage_id, ok, *args, **kwargs: state['settled'].append((ok, args, kwargs)))
    monkeypatch.setenv('OPENAI_API_KEY', 'sk-test-not-real')
    monkeypatch.setenv('OPENAI_MODEL', 'gpt-6-astra')
    monkeypatch.setenv('OPENAI_REASONING_EFFORT', 'low')
    return state


def test_not_configured_sends_nothing(monkeypatch, ledger):
    monkeypatch.setenv('OPENAI_MODEL', '')
    calls = install(monkeypatch, openai_client, [])
    with pytest.raises(openai_client.CloudAIError, match='not_configured'):
        openai_client.respond('j', 'deep_question', 'x', [])
    assert calls == [] and ledger['reserved'] == []


def test_budget_refusal_happens_before_any_request(monkeypatch, ledger):
    ledger['refuse'] = 'monthly_budget'
    calls = install(monkeypatch, openai_client, [DONE])
    with pytest.raises(usage.BudgetRefused):
        openai_client.respond('j', 'deep_question', 'x', [{'role': 'user', 'content': 'q'}])
    assert calls == []


def test_success_reserves_then_settles_measured_tokens(monkeypatch, ledger):
    calls = install(monkeypatch, openai_client, [DONE])
    data = openai_client.respond('job-1', 'deep_question', 'be brief', [{'role': 'user', 'content': 'q'}],
                                 tools=[{'type': 'function', 'name': 'get_news'}])
    body = calls[0]['json']
    assert calls[0]['url'] == 'https://api.openai.com/v1/responses'
    assert body['model'] == 'gpt-6-astra' and body['store'] is False and body['reasoning'] == {'effort': 'low'}
    assert body['include'] == ['reasoning.encrypted_content'] and body['tool_choice'] == 'auto'
    assert ledger['reserved'][0][:3] == ('job-1', 'deep_question', 'gpt-6-astra') and ledger['reserved'][0][3] > 0
    ok, args, _ = ledger['settled'][0]
    assert ok is True and args[:3] == (1000, 200, 100)
    assert openai_client.output_text(data) == 'Answer.' and openai_client.function_calls(data) == []


@pytest.mark.parametrize('reply,code,billed', [
    (httpx.ReadTimeout('slow'), 'timeout', True),
    (httpx.ConnectError('down'), 'unavailable', True),
    (httpx.Response(429, json={}), 'http_429', False),
    (httpx.Response(401, json={}), 'http_401', False),
    (httpx.Response(503, json={}), 'http_503', True),
    (httpx.Response(200, content=b'oops'), 'invalid_response', True),
    ({'status': 'failed', 'usage': {}}, 'response_failed', True),
])
def test_failures_are_never_assumed_free_unless_rejected_upfront(monkeypatch, ledger, reply, code, billed):
    install(monkeypatch, openai_client, [reply])
    with pytest.raises(openai_client.CloudAIError) as error:
        openai_client.respond('j', 'deep_question', 'x', [])
    assert error.value.code == code
    ok, _, kwargs = ledger['settled'][0]
    assert ok is False and kwargs['billed_unknown'] is billed


def test_function_calls_are_extracted():
    data = {'output': [{'type': 'function_call', 'call_id': 'c1', 'name': 'get_news', 'arguments': '{}'},
                       {'type': 'message', 'content': [{'type': 'refusal', 'refusal': 'no'}]}]}
    assert [item['call_id'] for item in openai_client.function_calls(data)] == ['c1']
    assert openai_client.output_text(data) == ''
