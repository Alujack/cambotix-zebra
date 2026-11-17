"""OpenAI Responses API client for deep analysis only. Every request reserves its worst-case cost first
(app.ai.usage) and is refused before any network call once the daily limit or monthly budget is reached.

The model id is configuration (OPENAI_MODEL), never assumed: verify the id your account can use before enabling."""
import json
import os
import time

import httpx

from app.ai import usage


class CloudAIError(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


# Rejected before the model ran: nothing billed.
NOT_BILLED = {400, 401, 403, 404, 409, 413, 422, 429}


def model() -> str:
    return os.getenv('OPENAI_MODEL', '').strip()


def configured() -> tuple[bool, str]:
    if not os.getenv('OPENAI_API_KEY', '').strip():
        return False, 'OPENAI_API_KEY is not set'
    if not model():
        return False, 'OPENAI_MODEL is not set'
    return True, model()


def respond(job_id: str, job: str, instructions: str, items: list, tools: list | None = None,
            tool_choice: str = 'auto', max_output_tokens: int | None = None, timeout: float | None = None) -> dict:
    """One Responses API request. Raises usage.BudgetRefused (no request sent) or CloudAIError."""
    ready, detail = configured()
    if not ready:
        raise CloudAIError('not_configured')
    max_output_tokens = max_output_tokens or int(os.getenv('OPENAI_MAX_OUTPUT_TOKENS', '4000'))
    body = {'model': model(), 'instructions': instructions, 'input': items, 'max_output_tokens': max_output_tokens,
            'store': False}
    effort = os.getenv('OPENAI_REASONING_EFFORT', 'low').strip().lower()
    if effort and effort != 'none':
        # Stateless tool loops must carry the encrypted reasoning items forward themselves.
        body.update(reasoning={'effort': effort}, include=['reasoning.encrypted_content'])
    if tools:
        body.update(tools=tools, tool_choice=tool_choice)
    amount = usage.reservation(len(instructions) + len(json.dumps(items)) + len(json.dumps(tools or [])),
                               max_output_tokens)
    usage_id = usage.reserve(job_id, job, model(), amount)
    timeout = float(os.getenv('OPENAI_TIMEOUT_SECONDS', '90')) if timeout is None else timeout
    started = time.monotonic()

    def elapsed():
        return int((time.monotonic() - started) * 1000)
    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.post(os.getenv('OPENAI_BASE_URL', 'https://api.openai.com/v1').rstrip('/') + '/responses',
                                   headers={'Authorization': 'Bearer ' + os.environ['OPENAI_API_KEY'].strip()}, json=body)
    except httpx.TimeoutException:
        usage.settle(usage_id, False, latency_ms=elapsed(), error_code='timeout', billed_unknown=True)
        raise CloudAIError('timeout')
    except httpx.HTTPError:
        # The request may have reached the API: keep the reservation charged.
        usage.settle(usage_id, False, latency_ms=elapsed(), error_code='connection', billed_unknown=True)
        raise CloudAIError('unavailable')
    if response.status_code >= 400:
        code = f'http_{response.status_code}'
        usage.settle(usage_id, False, latency_ms=elapsed(), error_code=code,
                     billed_unknown=response.status_code not in NOT_BILLED)
        raise CloudAIError(code)
    try:
        data = response.json()
        spent = data.get('usage') or {}
        tokens_in, tokens_out = int(spent.get('input_tokens') or 0), int(spent.get('output_tokens') or 0)
        cached = int((spent.get('input_tokens_details') or {}).get('cached_tokens') or 0)
    except (ValueError, TypeError, AttributeError):
        usage.settle(usage_id, False, latency_ms=elapsed(), error_code='invalid_json', billed_unknown=True)
        raise CloudAIError('invalid_response')
    ok = data.get('status') in ('completed', 'incomplete')
    usage.settle(usage_id, ok, tokens_in, tokens_out, cached, elapsed(), None if ok else 'status_' + str(data.get('status')),
                 billed_unknown=not ok)
    if not ok:
        raise CloudAIError('response_' + str(data.get('status')))
    return data


def output_text(data: dict) -> str:
    parts = []
    for item in data.get('output') or []:
        if item.get('type') == 'message':
            parts += [part.get('text', '') for part in item.get('content') or [] if part.get('type') == 'output_text']
    return '\n'.join(part for part in parts if part).strip()


def function_calls(data: dict) -> list[dict]:
    return [item for item in data.get('output') or [] if item.get('type') == 'function_call']
