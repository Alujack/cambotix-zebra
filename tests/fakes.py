"""Stand-ins for httpx.Client so no test reaches Ollama, OpenAI or Telegram."""
import httpx


class FakeClient:
    """Answers each request with the next item of `replies`: an httpx.Response, a dict (200 JSON) or an exception."""

    def __init__(self, replies, calls):
        self.replies, self.calls = replies, calls

    def __call__(self, **kwargs):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def _next(self, method, url, body):
        self.calls.append({'method': method, 'url': url, 'json': body})
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        if isinstance(reply, httpx.Response):
            reply.request = httpx.Request(method, url)
            return reply
        return httpx.Response(200, json=reply, request=httpx.Request(method, url))

    def post(self, url, json=None, headers=None, **kwargs):
        return self._next('POST', url, json)

    def get(self, url, **kwargs):
        return self._next('GET', url, None)


def install(monkeypatch, module, replies):
    """Patch `module.httpx.Client`; returns the list of recorded calls."""
    calls = []
    monkeypatch.setattr(module.httpx, 'Client', FakeClient(list(replies), calls))
    return calls
