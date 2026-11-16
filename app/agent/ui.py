"""How the assistant looks in Telegram: a keyboard of one-tap buttons, the "/" command menu, greetings and the
deep-question prompt. Every button maps to a code command, so tapping is instant and free."""
import re

# (label, command, argument). Rows are laid out two per line on a phone.
BUTTONS = [
    ('📂 Open trades', 'open', ''), ('💹 Price', 'price', ''),
    ('📊 This week', 'record', '7'), ('📊 Last 30 days', 'record', '30'),
    ('📡 Signals', 'signals', '5'), ('📰 News', 'news', ''),
    ('🩺 Status', 'status', ''), ('💰 AI cost', 'cost', ''),
    ('🧠 Deep analysis', 'ask_deep', ''), ('❓ Help', 'help', ''),
]
BY_LABEL = {label: (command, argument) for label, command, argument in BUTTONS}

KEYBOARD = {'keyboard': [[{'text': label} for label, _, _ in BUTTONS[index:index + 2]]
                         for index in range(0, len(BUTTONS), 2)],
            'resize_keyboard': True, 'is_persistent': True,
            'input_field_placeholder': 'Tap a button or ask about your trades…'}

MENU = [('help', 'What I can do'), ('open', 'Open trades'), ('price', 'Latest price, e.g. /price XAUUSD'),
        ('record', 'Performance, e.g. /record 30'), ('signals', 'Recent signals, e.g. /signals 5'),
        ('news', 'High-impact news, next 24 h'), ('status', 'System health'), ('cost', 'AI spending and budget'),
        ('deep', 'Deep analysis: /deep <question>'), ('forget', 'Clear chat memory')]

# The deep-question prompt. Telegram returns it as `reply_to_message`, which marks the answer as a deep question.
DEEP_PROMPT = '🧠 What should I investigate? Reply to this message with your question.'
DEEP_REPLY = {'force_reply': True, 'input_field_placeholder': 'e.g. why are London trades losing?'}
DEEP_EXAMPLES = ('Examples:\n• Why are London trades losing this month?\n• Compare New York and London results\n'
                 '• Do trades with cautions do worse?\n\nDeep analysis uses OpenAI (paid, counted in /cost).')

HELP = '''🦓 Hi! I'm your Zebra trading assistant.

Tap a button below, or just ask in your own words:
• "any trades open?"
• "how did we do this week?"
• "what is a liquidity sweep?"

📂 Open trades · 💹 Price · 📊 Results
📡 Signals · 📰 News · 🩺 Status · 💰 AI cost
🧠 Deep analysis: I investigate your records and explain why (paid, OpenAI)

Simple questions and all buttons are free (local AI). I only read your records: I never place, change or close trades.
Type / for the full command menu. /forget clears our chat memory.'''

GREETING = re.compile(r'^\s*(hi+|hey+|hello+|yo+|sup|good (morning|afternoon|evening)|thanks?( you)?|thx|ty|ok(ay)?'
                      r'|សួស្តី|អរគុណ)[\s!.,🙏👍😀-🙏]*(bro|bot|zebra|man)?[\s!.,]*$', re.IGNORECASE)


def greeting_reply(text: str) -> str | None:
    """A short instant reply to a greeting or thanks, without asking any model."""
    if not GREETING.match(text or ''):
        return None
    lowered = text.lower()
    if 'thank' in lowered or lowered.strip().startswith(('thx', 'ty')) or 'អរគុណ' in text:
        return '🙏 Anytime! Tap a button below whenever you need something.'
    if lowered.strip().startswith('ok'):
        return '👍'
    return '👋 Hi! Tap a button below, or ask me anything about your trades.'
