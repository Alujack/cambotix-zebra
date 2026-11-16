import pytest

from app.agent import deep
from app.ai import openai_client, usage


def call(name, call_id, arguments='{}'):
    return {'type': 'function_call', 'call_id': call_id, 'name': name, 'arguments': arguments}


def text(value, status='completed'):
    return {'status': status, 'output': [{'type': 'message', 'content': [{'type': 'output_text', 'text': value}]}]}


@pytest.fixture
def astra(monkeypatch):
    """Scripted Responses API: each request pops the next reply and is recorded."""
    state = {'replies': [], 'requests': [], 'tools_run': []}

    def respond(job_id, job, instructions, items, tools=None, tool_choice='auto', **kwargs):
        state['requests'].append({'job_id': job_id, 'items': list(items), 'tool_choice': tool_choice, 'tools': tools})
        reply = state['replies'].pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply

    monkeypatch.setattr(openai_client, 'respond', respond)
    monkeypatch.setattr(openai_client, 'configured', lambda: (True, 'gpt-6-astra'))
    monkeypatch.setattr(deep.tools, 'run', lambda name, arguments: state['tools_run'].append(name) or '{"ok":1}')
    monkeypatch.setenv('AGENT_MAX_TOOL_CALLS', '5')
    return state


def test_tool_results_are_fed_back_until_an_answer(astra):
    astra['replies'] = [{'status': 'completed', 'output': [{'type': 'reasoning', 'id': 'r'}, call('get_track_record', 'c1')]},
                        text('London lost 3R over 12 trades (small sample).')]
    answer = deep.answer('why is London losing?', [{'role': 'user', 'content': 'earlier'}])
    assert answer == 'London lost 3R over 12 trades (small sample).'
    assert astra['tools_run'] == ['get_track_record']
    second = astra['requests'][1]['items']
    assert second[-1] == {'type': 'function_call_output', 'call_id': 'c1', 'output': '{"ok":1}'}
    assert {'type': 'reasoning', 'id': 'r'} in second           # reasoning carried forward (stateless requests)
    assert len({item['job_id'] for item in astra['requests']}) == 1   # one job, counted once against the daily limit


def test_tool_calls_are_capped_and_the_model_must_conclude(astra):
    astra['replies'] = [{'status': 'completed', 'output': [call('get_signals', f'c{i}a'), call('get_news', f'c{i}b')]}
                        for i in range(3)] + [text('Done with what I had.')]
    assert deep.answer('dig deep', []) == 'Done with what I had.'
    assert len(astra['tools_run']) == 5
    refused = [item for item in astra['requests'][-1]['items']
               if item.get('type') == 'function_call_output' and 'tool limit' in item['output']]
    assert len(refused) == 1 and astra['requests'][-1]['tool_choice'] == 'none'


def test_a_model_that_never_stops_calling_tools_is_cut_off(astra):
    astra['replies'] = [{'status': 'completed', 'output': [call('get_news', f'c{i}')]} for i in range(20)]
    with pytest.raises(openai_client.CloudAIError, match='tool_loop_limit'):
        deep.answer('loop', [])
    assert len(astra['requests']) == 7 and len(astra['tools_run']) == 5


def test_budget_refusal_stops_the_loop(astra):
    astra['replies'] = [{'status': 'completed', 'output': [call('get_news', 'c1')]}, usage.BudgetRefused('monthly_budget')]
    with pytest.raises(usage.BudgetRefused):
        deep.answer('q', [])


def test_empty_and_cut_short_answers(astra):
    astra['replies'] = [text('')]
    with pytest.raises(openai_client.CloudAIError, match='empty_answer'):
        deep.answer('q', [])
    astra['replies'] = [text('Partial', status='incomplete')]
    assert deep.answer('q', []).endswith('(answer cut short by the output limit)')


def test_not_configured(monkeypatch):
    monkeypatch.setattr(openai_client, 'configured', lambda: (False, 'OPENAI_MODEL is not set'))
    with pytest.raises(openai_client.CloudAIError, match='not_configured'):
        deep.answer('q', [])
