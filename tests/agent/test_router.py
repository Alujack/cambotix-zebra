from contextlib import contextmanager

import pytest

from app.agent import router
from app.ai import ollama, usage
from app.ai.openai_client import CloudAIError
from app.ai.schemas import Route


@pytest.fixture
def wiring(monkeypatch):
    """No database: memory and commands are replaced, every model call is recorded."""
    state = {'remembered': [], 'deep': [], 'simple': [], 'route': None}

    @contextmanager
    def fake():
        yield object()
    monkeypatch.setattr(router, 'readonly', fake)
    monkeypatch.setattr(router, 'database', fake)
    monkeypatch.setattr(router.memory, 'recent', lambda conn, chat: [{'role': 'user', 'content': 'before'}])
    monkeypatch.setattr(router.memory, 'remember', lambda conn, chat, q, a: state['remembered'].append((q, a)))
    monkeypatch.setattr(router.memory, 'forget', lambda conn, chat: state.update(forgot=chat))
    monkeypatch.setitem(router.commands.COMMANDS, 'open', lambda conn, arg: 'OPEN TRADES')
    monkeypatch.setitem(router.commands.COMMANDS, 'price', lambda conn, arg: f'PRICE {arg}')

    def route_question(text, history):
        if isinstance(state['route'], Exception):
            raise state['route']
        return state['route']
    monkeypatch.setattr(router, 'route_question', route_question)

    def answer(question, history):
        state['deep'].append(question)
        if isinstance(state.get('deep_result'), Exception):
            raise state['deep_result']
        return 'deep answer'
    monkeypatch.setattr(router.deep, 'answer', answer)

    def simple(question, history):
        state['simple'].append(question)
        if isinstance(state.get('simple_result'), Exception):
            raise state['simple_result']
        return 'simple answer'
    monkeypatch.setattr(router, 'simple', simple)
    return state


def test_commands_are_answered_by_code(wiring):
    assert router.handle('1', '/open') == ('OPEN TRADES', 'command')
    assert router.handle('1', '/price@ZebraBot xauusd') == ('PRICE xauusd', 'command')
    assert router.handle('1', '/help')[0].startswith('🦓 Zebra assistant')
    assert router.handle('1', '/nonsense')[0].startswith('Unknown command')
    assert router.handle('1', '/forget')[0].startswith('🧹') and wiring['forgot'] == '1'
    assert wiring['deep'] == wiring['simple'] == []


def test_natural_language_command_routes_to_code(wiring):
    wiring['route'] = (Route(route='COMMAND', command='open', confidence=90), False)
    assert router.handle('1', 'any open trades?') == ('OPEN TRADES', 'command')


def test_simple_questions_stay_local_and_are_remembered(wiring):
    wiring['route'] = (Route(route='SIMPLE', confidence=90), False)
    assert router.handle('1', 'how many trades this week?') == ('simple answer', 'simple')
    assert wiring['deep'] == [] and wiring['remembered'] == [('how many trades this week?', 'simple answer')]


def test_uncertain_deep_question_gets_a_hint_not_a_paid_call(wiring):
    wiring['route'] = (Route(route='SIMPLE', confidence=40), True)
    reply, route = router.handle('1', 'is the strategy ok?')
    assert route == 'simple' and '/deep' in reply and wiring['deep'] == []


def test_deep_question_and_explicit_deep(wiring):
    wiring['route'] = (Route(route='DEEP', confidence=90), False)
    reply, route = router.handle('1', 'why is London losing?')
    assert route == 'deep' and 'deep answer' in reply and 'not a trading instruction' in reply
    reply, _ = router.handle('1', '/deep compare sessions')
    assert wiring['deep'] == ['why is London losing?', 'compare sessions']
    assert router.handle('1', '/deep')[0].startswith('Usage')


def test_local_model_down_never_moves_work_to_openai(wiring):
    wiring['route'] = ollama.LocalAIError('unavailable')
    reply, route = router.handle('1', 'how are we doing?')
    assert route == 'local_down' and 'offline' in reply and wiring['deep'] == [] and wiring['remembered'] == []


def test_openai_unavailable_never_moves_work_to_the_local_model(wiring):
    wiring['route'] = (Route(route='DEEP', confidence=90), False)
    for error, words in [(usage.BudgetRefused('daily_limit'), 'Daily deep-analysis limit'),
                         (usage.BudgetRefused('monthly_budget'), 'budget is used up'),
                         (CloudAIError('not_configured'), 'not configured'),
                         (CloudAIError('timeout'), 'unavailable right now (timeout)')]:
        wiring['deep_result'] = error
        reply, route = router.handle('1', 'why?')
        assert words in reply and route == 'deep'
    assert wiring['simple'] == [] and wiring['remembered'] == []


def test_empty_message(wiring):
    assert router.handle('1', '   ')[1] == 'none'
