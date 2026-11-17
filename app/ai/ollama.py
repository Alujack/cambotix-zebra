"""Local model client (Ollama native /api/chat). Free, private, and used for every frequent job."""
import os
import time

import httpx

from app.ai import usage


class LocalAIError(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def model() -> str:
    return os.getenv('OLLAMA_MODEL', 'qwen2.5:3b')


def base_url() -> str:
    return os.getenv('OLLAMA_BASE_URL', 'http://ollama:11434').rstrip('/')


def chat(job: str, messages: list[dict], schema: dict | None = None, timeout: float | None = None,
         max_tokens: int = 600, temperature: float = 0.1, context: int | None = None) -> str:
    """The model's reply text (JSON text when `schema` is given). Raises LocalAIError; never returns empty."""
    timeout = float(os.getenv('OLLAMA_TIMEOUT_SECONDS', '60')) if timeout is None else timeout
    body = {'model': model(), 'stream': False, 'messages': messages,
            'options': {'temperature': temperature, 'num_predict': max_tokens,
                        'num_ctx': context or int(os.getenv('OLLAMA_NUM_CTX', '8192'))}}
    if schema is not None:
        body['format'] = schema
    started = time.monotonic()
    tokens_in = tokens_out = 0
    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.post(base_url() + '/api/chat', json=body)
            response.raise_for_status()
            data = response.json()
        tokens_in, tokens_out = int(data.get('prompt_eval_count') or 0), int(data.get('eval_count') or 0)
        text = data['message']['content']
        if not isinstance(text, str) or not text.strip():
            raise LocalAIError('empty_response')
    except LocalAIError as error:
        usage.record_local(job, model(), False, tokens_in, tokens_out, int((time.monotonic() - started) * 1000), error.code)
        raise
    except httpx.TimeoutException:
        usage.record_local(job, model(), False, latency_ms=int((time.monotonic() - started) * 1000), error_code='timeout')
        raise LocalAIError('timeout')
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        # No raw provider errors are logged or stored: URLs may contain credentials.
        usage.record_local(job, model(), False, latency_ms=int((time.monotonic() - started) * 1000), error_code='unavailable')
        raise LocalAIError('unavailable')
    usage.record_local(job, model(), True, tokens_in, tokens_out, int((time.monotonic() - started) * 1000))
    return text.strip()


def available(timeout: float = 3) -> tuple[bool, str]:
    """(reachable with the configured model pulled, short detail) for /status. Free: no inference."""
    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.get(base_url() + '/api/tags')
            response.raise_for_status()
            names = {item.get('name', '') for item in response.json().get('models', [])}
    except (httpx.HTTPError, ValueError, AttributeError):
        return False, 'not reachable'
    wanted = model()
    if wanted in names or f'{wanted}:latest' in names:
        return True, f'{wanted} ready'
    return False, f'{wanted} not pulled'
