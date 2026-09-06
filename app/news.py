"""High-impact economic calendar check using the free ForexFactory weekly JSON feed.
Fails open: if the feed is unavailable the state is 'unknown' and nothing is blocked, but the message says so."""
import os
import threading
import time
from datetime import datetime

import httpx

FEED = 'https://nfs.faireconomy.media/ff_calendar_thisweek.json'
_cache = {'fetched': 0.0, 'events': None}
_lock = threading.Lock()


def _load():
    with _lock:
        if _cache['events'] is not None and time.time() - _cache['fetched'] < 3600:
            return _cache['events']
        try:
            response = httpx.get(FEED, headers={'User-Agent': 'cambotix-zebra/1.0'}, timeout=10)
            response.raise_for_status()
            events = []
            for item in response.json():
                try:
                    stamp = datetime.fromisoformat(item['date']).timestamp()
                except (KeyError, ValueError, TypeError):
                    continue
                events.append({'time': stamp, 'title': str(item.get('title', ''))[:80],
                               'country': str(item.get('country', '')).upper(), 'impact': str(item.get('impact', ''))})
            _cache.update(fetched=time.time(), events=events)
        except Exception:
            pass  # keep any stale copy; a feed outage must never crash the pipeline
        return _cache['events']


def news_status(bar_time: int, events: list | None = None) -> dict:
    """{'state': 'off'|'clear'|'blocked'|'unknown', 'detail': str} for a bar close time in Unix seconds."""
    if os.getenv('NEWS_FILTER', 'true').lower() != 'true':
        return {'state': 'off', 'detail': 'news filter disabled'}
    events = _load() if events is None else events
    if events is None:
        return {'state': 'unknown', 'detail': 'economic calendar unavailable'}
    before = int(os.getenv('NEWS_WINDOW_BEFORE_MIN', '30')) * 60
    after = int(os.getenv('NEWS_WINDOW_AFTER_MIN', '15')) * 60
    currencies = {c.strip().upper() for c in os.getenv('NEWS_CURRENCIES', 'USD').split(',') if c.strip()}
    relevant = sorted((e for e in events if e['impact'] == 'High' and e['country'] in currencies), key=lambda e: e['time'])
    for event in relevant:
        delta = event['time'] - bar_time
        if -after <= delta <= before:
            when = f'in {delta / 60:.0f} min' if delta >= 0 else f'{-delta / 60:.0f} min ago'
            return {'state': 'blocked', 'detail': f'{event["title"]} ({event["country"]}) {when}'}
    upcoming = [e for e in relevant if e['time'] > bar_time]
    if upcoming:
        nxt = upcoming[0]
        return {'state': 'clear', 'detail': f'next high-impact {nxt["country"]}: {nxt["title"]} in {(nxt["time"] - bar_time) / 3600:.1f} h'}
    return {'state': 'clear', 'detail': 'no further high-impact events this week'}
