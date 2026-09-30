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
        now = time.time()
        age = now - _cache['fetched']
        if _cache['events'] is not None and age < 3600:
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
            _cache.update(fetched=now, events=events)
        except Exception:
            # A short outage may use the recent cache. An arbitrarily old weekly
            # calendar must not be described as checked and clear.
            maximum_stale = int(os.getenv('NEWS_MAX_STALE_SECONDS', '7200'))
            return _cache['events'] if _cache['events'] is not None and age <= maximum_stale else None
        return _cache['events']


def _relevant(events: list) -> list:
    currencies = {c.strip().upper() for c in os.getenv('NEWS_CURRENCIES', 'USD').split(',') if c.strip()}
    return sorted((e for e in events if e['impact'] == 'High' and e['country'] in currencies), key=lambda e: e['time'])


def next_event(bar_time: int, events: list | None = None) -> dict | None:
    """The next relevant high-impact event after the bar, or None (also when the filter is off or the feed is down)."""
    if os.getenv('NEWS_FILTER', 'true').lower() != 'true':
        return None
    events = _load() if events is None else events
    upcoming = [e for e in _relevant(events or []) if e['time'] > bar_time]
    return upcoming[0] if upcoming else None


def news_status(bar_time: int, events: list | None = None) -> dict:
    """{'state': 'off'|'clear'|'blocked'|'unknown', 'detail': str} for a bar close time in Unix seconds."""
    if os.getenv('NEWS_FILTER', 'true').lower() != 'true':
        return {'state': 'off', 'detail': 'news filter disabled'}
    events = _load() if events is None else events
    if events is None:
        return {'state': 'unknown', 'detail': 'economic calendar unavailable'}
    before = int(os.getenv('NEWS_WINDOW_BEFORE_MIN', '30')) * 60
    after = int(os.getenv('NEWS_WINDOW_AFTER_MIN', '15')) * 60
    relevant = _relevant(events)
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
