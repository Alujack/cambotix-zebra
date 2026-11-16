"""Sorts a free-text Telegram question with the local model, so paid analysis runs only when it is needed."""
import json
import os

from pydantic import ValidationError

from app.ai import ollama, prompts
from app.ai.schemas import Route


def route_question(text: str, history: list[dict]) -> tuple[Route, bool]:
    """(route for `text`, whether deep analysis was suggested but not confident enough). An uncertain DEEP answer is
    downgraded to SIMPLE: paid analysis needs AGENT_DEEP_MIN_CONFIDENCE or an explicit /deep.
    Raises ollama.LocalAIError when the model is down or answers invalid JSON."""
    recent = [{'role': item['role'], 'content': item['content'][:300]} for item in history[-4:]]
    raw = ollama.chat('route', [{'role': 'system', 'content': prompts.ROUTER}, *recent,
                                {'role': 'user', 'content': json.dumps({'question': text[:1000]})}],
                      schema=Route.model_json_schema(), temperature=0, max_tokens=80, context=2048,
                      timeout=float(os.getenv('OLLAMA_ROUTE_TIMEOUT_SECONDS', '30')))
    try:
        route = Route.model_validate_json(raw)
    except ValidationError:
        raise ollama.LocalAIError('invalid_route')
    if route.route == 'COMMAND' and route.command == 'none':
        return Route(route='SIMPLE', confidence=route.confidence), False
    if route.route != 'COMMAND' and route.command != 'none':
        route = Route(route=route.route, confidence=route.confidence)
    if route.route == 'DEEP' and route.confidence < int(os.getenv('AGENT_DEEP_MIN_CONFIDENCE', '70')):
        return Route(route='SIMPLE', confidence=route.confidence), True
    return route, False
