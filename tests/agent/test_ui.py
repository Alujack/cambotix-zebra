from app.agent import ui, worker
from app.agent.commands import COMMANDS


def test_every_button_maps_to_something_the_router_handles():
    for label, command, _ in ui.BUTTONS:
        assert command in COMMANDS or command in ('help', 'ask_deep'), label
    rows = ui.KEYBOARD['keyboard']
    assert all(len(row) <= 2 for row in rows) and sum(len(row) for row in rows) == len(ui.BUTTONS)


def test_menu_commands_are_valid_for_telegram():
    for name, description in ui.MENU:
        assert name.islower() and name.isascii() and 1 <= len(name) <= 32 and 3 <= len(description) <= 256


def test_greetings_get_an_instant_reply_and_questions_do_not():
    for text in ['hi', 'Hi bro', 'hello!', 'hey', 'good morning', 'thanks', 'thank you bro', 'thx', 'ok', 'សួស្តី', 'អរគុណ']:
        assert ui.greeting_reply(text), text
    for text in ['hi, how many trades did we win?', 'hello why is London losing', 'okay show open trades', 'history']:
        assert ui.greeting_reply(text) is None, text
    assert ui.greeting_reply('thanks').startswith('🙏')


def test_a_reply_to_the_deep_prompt_becomes_a_deep_question():
    prompt = {'from': {'is_bot': True}, 'text': ui.DEEP_PROMPT + '\n\nExamples: ...'}
    assert worker.deep_reply({'text': 'why is London losing?', 'reply_to_message': prompt}) == '/deep why is London losing?'
    # Anything else stays as written: plain messages, commands, and replies to other messages.
    assert worker.deep_reply({'text': 'why?'}) == 'why?'
    assert worker.deep_reply({'text': '/open', 'reply_to_message': prompt}) == '/open'
    other = {'from': {'is_bot': True}, 'text': '📂 OPEN TRADES'}
    assert worker.deep_reply({'text': 'and this?', 'reply_to_message': other}) == 'and this?'
    forged = {'from': {'is_bot': False}, 'text': ui.DEEP_PROMPT}
    assert worker.deep_reply({'text': 'x', 'reply_to_message': forged}) == 'x'
