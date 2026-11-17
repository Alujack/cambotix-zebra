"""Deep analysis: OpenAI investigates the records through the read-only tools, under hard limits.

Limits: AGENT_MAX_TOOL_CALLS tool executions per question (extra requests are answered with an error and the
model must conclude), AGENT_DEEP_TIMEOUT_SECONDS overall, AGENT_TOOL_OUTPUT_CHARS per tool result, and the
budget check before every API request (one question can need several requests: each one is reserved and counted)."""
import os
import time
import uuid

from app.agent import tools
from app.ai import openai_client, prompts
from app.ai.openai_client import CloudAIError
from app.domain import allowed_symbols


def limits() -> tuple[int, float]:
    return int(os.getenv('AGENT_MAX_TOOL_CALLS', '5')), float(os.getenv('AGENT_DEEP_TIMEOUT_SECONDS', '180'))


def answer(question: str, history: list[dict], job: str = 'deep_question') -> str:
    """Final answer text. Raises usage.BudgetRefused (nothing sent) or CloudAIError."""
    ready, _ = openai_client.configured()
    if not ready:
        raise CloudAIError('not_configured')
    max_calls, budget_seconds = limits()
    started, used = time.monotonic(), 0
    job_id = f'{job}-{uuid.uuid4().hex[:16]}'
    instructions = prompts.DEEP + (f'\nNow: {tools.iso(time.time())}. '
                                   f'Configured symbols: {", ".join(sorted(allowed_symbols()))}.')
    items = [{'role': item['role'], 'content': item['content']} for item in history]
    items.append({'role': 'user', 'content': question[:2000]})
    # One request per tool round, plus the forced final answer.
    for _ in range(max_calls + 2):
        remaining = budget_seconds - (time.monotonic() - started)
        if remaining < 5:
            raise CloudAIError('deadline')
        data = openai_client.respond(job_id, job, instructions, items, tools=tools.specs(),
                                     tool_choice='none' if used >= max_calls else 'auto',
                                     timeout=min(float(os.getenv('OPENAI_TIMEOUT_SECONDS', '90')), remaining))
        calls = openai_client.function_calls(data)
        if not calls:
            return final(data)
        items += data.get('output') or []
        for call in calls:
            if used < max_calls:
                output = tools.run(call.get('name', ''), call.get('arguments') or '{}')
                used += 1
            else:
                output = '{"error":"tool limit reached: answer now with the evidence already gathered"}'
            items.append({'type': 'function_call_output', 'call_id': call.get('call_id'), 'output': output})
    raise CloudAIError('tool_loop_limit')


def final(data: dict) -> str:
    text = openai_client.output_text(data)
    if not text:
        raise CloudAIError('empty_answer')
    if data.get('status') == 'incomplete':
        text += '\n\n(answer cut short by the output limit)'
    return text[:3900]
