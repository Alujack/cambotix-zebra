"""Local-model review of one signal that already passed every technical rule."""
import json
import os

from app.ai import ollama
from app.domain import Analysis, Signal, session_exempt_symbols, sessions, system_prompt
from app.news import news_status


def classify(signal: Signal, timeout: float | None = None) -> Analysis:
    """Structured review by the local model. Raises ollama.LocalAIError or pydantic.ValidationError."""
    schema = Analysis.model_json_schema()
    text = ollama.chat('signal_review', [
        {'role': 'system', 'content': system_prompt(signal) + '\nSchema: ' + json.dumps(schema)},
        {'role': 'user', 'content': json.dumps({'candidate': signal.model_dump(), 'sessions': sessions(signal.bar_time),
                                                'trades_continuously': signal.symbol in session_exempt_symbols(),
                                                'news': news_status(signal.bar_time)})}],
        schema=schema, temperature=0, max_tokens=600, context=4096,
        timeout=float(os.getenv('AI_TIMEOUT_SECONDS', '120')) if timeout is None else timeout)
    return Analysis.model_validate_json(text)
