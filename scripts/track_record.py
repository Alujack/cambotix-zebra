#!/usr/bin/env python3
"""Print the graded track record, verify the ledger chain independently, and optionally export a public page.

  python3 scripts/track_record.py                       report + forward-test verdict
  python3 scripts/track_record.py --expect 42:ab12...   also check a chain head posted in Telegram
  python3 scripts/track_record.py --html record.html    write the full public record as one static page
"""
import argparse
import hashlib
import html
import json
import sys
import urllib.request
from datetime import datetime, timezone

from setup import read_env

GENESIS = '0' * 64


def get(env, path):
    request = urllib.request.Request('http://localhost:' + env['ANALYZER_PORT'] + path,
                                     headers={'X-Zebra-Token': env['ANALYZER_TOKEN']})
    with urllib.request.urlopen(request, timeout=15) as response:
        return json.load(response)


def fetch_ledger(env):
    rows, after = [], 0
    while True:
        page = get(env, f'/ledger?after={after}')
        if not page:
            return rows
        rows += page
        after = page[-1]['seq']


def verify(rows):
    """Same rule as app/ledger.py, reimplemented here so the check does not trust the service."""
    prev = GENESIS
    for expected, row in enumerate(rows, 1):
        body = json.loads(row['body'])
        if (row['seq'] != expected or body.get('seq') != expected or body.get('prev') != prev
                or hashlib.sha256(row['body'].encode()).hexdigest() != row['hash']):
            return False, expected
        prev = row['hash']
    return True, prev


def trades(rows):
    """One entry per published plan with its final state."""
    found = {}
    for row in rows:
        body = json.loads(row['body'])
        if row['kind'] == 'published':
            found[row['event_id']] = {'seq': row['seq'], 'plan': body, 'result': None, 'filled': None}
        elif row['kind'] == 'filled':
            found[row['event_id']]['filled'] = body
        elif row['kind'] in ('closed', 'not_filled'):
            found[row['event_id']]['result'] = body
    return list(found.values())


def stamp(epoch, pattern='%Y-%m-%d %H:%M'):
    return datetime.fromtimestamp(epoch, timezone.utc).strftime(pattern)


def percent(value):
    return 'n/a' if value is None else f'{value * 100:.0f}%'


def report(record, chain_ok, head, rows):
    h = record['headline']
    print('ZEBRA TRACK RECORD (every published plan, nothing removed)')
    print(f'  published {record["published"]} | open {record["open"]} | never filled {record["not_filled"]} '
          f'{record["not_filled_reasons"] or ""}')
    print(f'  closed {h["closed"]} | wins {h["wins"]} | win rate {percent(h["win_rate"])} | '
          f'total {h["total_r_tp1"]:+.2f}R | expectancy {h["expectancy_r"]:+.3f}R | '
          f'profit factor {h["profit_factor"] if h["profit_factor"] is not None else "n/a"}')
    print(f'  scale-out total {h["total_r_scaled"]:+.2f}R | max drawdown {h["max_drawdown_r"]:.2f}R | '
          f'ambiguous candles {h["ambiguous"]}')
    for title, key in (('by model', 'by_model'), ('by symbol', 'by_symbol'), ('by month', 'by_month')):
        for name, item in record[key].items():
            print(f'  {title:<9} {name:<8} {item["closed"]:>4} closed  {percent(item["win_rate"]):>4}  '
                  f'{item["total_r_tp1"]:+.2f}R')
    print(f'\nFORWARD TEST: {h["verdict"]} (needs {h["min_trades"]} closed trades, positive expectancy, '
          f'max drawdown <= {h["max_drawdown_limit_r"]:g}R)')
    print(f'\nLEDGER: {len(rows)} rows, chain ' + (f'valid, head #{len(rows)} {head}' if chain_ok
                                                   else f'BROKEN at row {head}'))


PAGE = '''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Zebra Track Record</title>
<style>
:root {{ --bg:#f7f7f5; --fg:#1c1c1a; --muted:#6b6b66; --card:#fff; --line:#e3e3de; --win:#1f7a4d; --loss:#b3362d; }}
@media (prefers-color-scheme: dark) {{ :root:not([data-theme="light"]) {{ --bg:#141413; --fg:#ecece8; --muted:#a3a39c;
  --card:#1e1e1c; --line:#33332f; --win:#4fbf87; --loss:#e8766b; }} }}
:root[data-theme="dark"] {{ --bg:#141413; --fg:#ecece8; --muted:#a3a39c; --card:#1e1e1c; --line:#33332f; --win:#4fbf87; --loss:#e8766b; }}
body {{ margin:0; background:var(--bg); color:var(--fg); font:15px/1.5 system-ui, -apple-system, "Segoe UI", "Noto Sans Khmer", sans-serif; }}
main {{ max-width:1100px; margin:0 auto; padding:24px 16px 48px; }}
h1 {{ margin:0 0 4px; font-size:26px; }} h2 {{ margin:32px 0 8px; font-size:18px; }}
.km {{ color:var(--muted); font-size:14px; }} .muted {{ color:var(--muted); }}
.tiles {{ display:grid; grid-template-columns:repeat(auto-fit, minmax(150px, 1fr)); gap:12px; margin-top:20px; }}
.tile {{ background:var(--card); border:1px solid var(--line); border-radius:10px; padding:12px 14px; }}
.tile b {{ display:block; font-size:22px; font-variant-numeric:tabular-nums; }}
.verdict {{ margin-top:16px; padding:12px 14px; border-radius:10px; border:1px solid var(--line); background:var(--card); }}
.wrap {{ overflow-x:auto; border:1px solid var(--line); border-radius:10px; background:var(--card); }}
table {{ border-collapse:collapse; width:100%; font-variant-numeric:tabular-nums; font-size:13px; }}
th, td {{ padding:7px 10px; border-bottom:1px solid var(--line); text-align:right; white-space:nowrap; }}
th:first-child, td:first-child, th.l, td.l {{ text-align:left; }}
.win {{ color:var(--win); }} .loss {{ color:var(--loss); }}
code {{ word-break:break-all; font-size:12px; }}
</style></head><body><main>
<h1>Zebra track record</h1>
<div class="km">កំណត់ត្រាលទ្ធផល — គ្រប់សញ្ញាទាំងអស់ គ្មានលុបចោលទេ</div>
<p class="muted">Generated {generated} UTC. Every published plan, graded on broker M1 candles including spread. Nothing is removed.</p>
<div class="tiles">
<div class="tile"><span class="muted">Closed · បានបិទ</span><b>{closed}</b></div>
<div class="tile"><span class="muted">Win rate · អត្រាឈ្នះ</span><b>{win_rate}</b></div>
<div class="tile"><span class="muted">Total (TP1 basis)</span><b>{total}</b></div>
<div class="tile"><span class="muted">Expectancy / trade</span><b>{expectancy}</b></div>
<div class="tile"><span class="muted">Max drawdown · ធ្លាក់ចុះអតិបរមា</span><b>{drawdown}</b></div>
<div class="tile"><span class="muted">Never filled · មិនបានចូល</span><b>{not_filled}</b></div>
<div class="tile"><span class="muted">Open · កំពុងបើក</span><b>{open}</b></div>
<div class="tile"><span class="muted">Ambiguous candles</span><b>{ambiguous}</b></div>
</div>
<div class="verdict"><b>Forward test: {verdict}</b> <span class="muted">— needs {min_trades} closed trades, positive expectancy, max drawdown at most {dd_limit}R.</span></div>
<h2>By month</h2>
<div class="wrap"><table><tr><th>Month</th><th>Closed</th><th>Wins</th><th>Win rate</th><th>Total R</th><th>Scale-out R</th></tr>{months}</table></div>
<h2>Every plan · គ្រប់ផែនការ</h2>
<div class="wrap"><table><tr><th>#</th><th class="l">Published (UTC)</th><th class="l">Market</th><th class="l">Side</th><th class="l">Model</th>
<th>Entry</th><th>Stop</th><th>TP1</th><th class="l">Result</th><th>R (TP1)</th><th>R (scale-out)</th></tr>{trades}</table></div>
<h2>How to check this record</h2>
<p>{basis}</p>
<p>The record is a hash chain: each row contains the previous row's SHA-256, so changing any past result changes every
later hash. The chain head is posted to Telegram every day. Current head <b>#{head_seq}</b>:</p>
<p><code>{head_hash}</code></p>
<p class="muted">Paper tracking of published analysis. Not financial advice. Trading carries risk of loss.</p>
</main></body></html>
'''


def page(record, rows, head):
    h = record['headline']
    fmt = lambda value: f'{value:+.2f}R'
    months = ''.join(f'<tr><td>{html.escape(name)}</td><td>{m["closed"]}</td><td>{m["wins"]}</td><td>{percent(m["win_rate"])}</td>'
                     f'<td>{fmt(m["total_r_tp1"])}</td><td>{fmt(m["total_r_scaled"])}</td></tr>'
                     for name, m in record['by_month'].items()) or '<tr><td colspan="6">No closed trades yet</td></tr>'
    lines = []
    for item in reversed(trades(rows)):
        plan, result = item['plan'], item['result']
        digits = 2 if plan['entry'] >= 100 else 5
        if result is None:
            outcome, r1, rs, css = 'open', '', '', ''
        elif result['kind'] == 'not_filled':
            outcome, r1, rs, css = 'not filled (' + result['reason'].replace('_', ' ') + ')', '', '', 'muted'
        else:
            outcome = result['exit'].replace('_', ' ') + (' *' if result['ambiguous'] else '')
            r1, rs = fmt(result['r_tp1']), fmt(result['r_scaled'])
            css = 'win' if result['r_tp1'] > 0 else 'loss'
        lines.append(f'<tr><td>{item["seq"]}</td><td class="l">{stamp(plan["published_at"])}</td>'
                     f'<td class="l">{html.escape(plan["symbol"])}</td><td class="l">{plan["direction"]}</td>'
                     f'<td class="l">{html.escape(plan["model"])}</td><td>{plan["entry"]:.{digits}f}</td>'
                     f'<td>{plan["stop"]:.{digits}f}</td><td>{plan["targets"][0][1]:.{digits}f}</td>'
                     f'<td class="l {css}">{html.escape(outcome)}</td><td class="{css}">{r1}</td><td class="{css}">{rs}</td></tr>')
    return PAGE.format(generated=datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M'), closed=h['closed'],
                       win_rate=percent(h['win_rate']), total=fmt(h['total_r_tp1']),
                       expectancy=f'{h["expectancy_r"]:+.3f}R', drawdown=f'{h["max_drawdown_r"]:.2f}R',
                       not_filled=record['not_filled'], open=record['open'], ambiguous=h['ambiguous'],
                       verdict=h['verdict'], min_trades=h['min_trades'], dd_limit=f'{h["max_drawdown_limit_r"]:g}',
                       months=months, trades=''.join(lines) or '<tr><td colspan="11">No published plans yet</td></tr>',
                       basis=html.escape(record['basis']) + ' * marks a candle where the order of hits was unknown; the worse outcome is counted.',
                       head_seq=len(rows), head_hash=head)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--expect', metavar='SEQ:HASH', help='chain head posted earlier, e.g. in the daily Telegram record')
    parser.add_argument('--html', metavar='PATH', help='write the public record page to PATH')
    args = parser.parse_args()
    env = read_env()
    record, rows = get(env, '/track-record'), fetch_ledger(env)
    chain_ok, head = verify(rows)
    report(record, chain_ok, head, rows)
    failed = not chain_ok
    if args.expect:
        seq, _, expected = args.expect.partition(':')
        actual = rows[int(seq) - 1]['hash'] if 0 < int(seq) <= len(rows) else None
        match = actual == expected.strip().lower()
        print(f'Posted head #{seq}: ' + ('matches the ledger' if match else 'DOES NOT MATCH the ledger'))
        failed = failed or not match
    if args.html:
        if not chain_ok:
            raise SystemExit('Refusing to export a page from a broken chain.')
        with open(args.html, 'w', encoding='utf-8', newline='\n') as handle:
            handle.write(page(record, rows, head))
        print(f'Wrote {args.html}')
    sys.exit(1 if failed else 0)


if __name__ == '__main__':
    main()
