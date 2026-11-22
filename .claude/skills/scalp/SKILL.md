---
name: scalp
description: Run a hands-on scalping session in MetaTrader 5 where Claude reads the 1-minute chart and places the trades itself, with a stop loss and take profit on every order. Works on whichever MT5 account is logged in (demo, standard or cent; the symbol suffix and lot size are worked out automatically). Use this whenever the user asks Claude to trade, scalp, "trade for me", open a position, flip or grow an account, or test Claude's trading on BTC, gold or forex in MT5, even if they do not say "scalp" or name the skill.
---

# Scalp

A trading session that Claude runs by hand: read the chart, wait for a pullback, place one trade with a
stop and a target on the broker's server, wait for it to close, repeat a few times, then report.

Everything goes through one script, which adapts to the account that MT5 is logged in to:

```
py -3.13 .claude/skills/scalp/scripts/trade.py <command>
```

Only `py -3.13` has the MetaTrader5 package on this PC. The script needs MetaTrader 5 open and logged in.

Arguments the user may give after `/scalp`: a symbol (default `BTCUSD`), a number of trades (default 5), a
risk per trade (default 2%), a loss limit, a profit target. Use the plain symbol name (`BTCUSD`, `XAUUSD`,
`EURUSD`); the script finds the broker's version (`BTCUSDm`, `BTCUSDc`, ...).

## What to be honest about

This method has no proven edge. On 2026-11-22 nine simple 1-minute rules were backtested on two years of
BTC data and all lost after the spread; the same was found on gold. The first live demo session won three
trades out of three, but BTC fell $700 in a straight line that hour, so that proves nothing. Say this once
at the start of a session in one or two sentences, then get on with it. Never promise a result, and never
suggest a bigger size to chase a target: a bigger size only reaches the loss limit sooner.

## Step 1: check the account

Run `status` first, every session. The user switches accounts often, and what they call an account is not
always what it is (a "demo cent account" turned out to be real money).

- **DEMO**: carry on.
- **REAL** (or anything that is not DEMO): stop and tell the user plainly what `status` shows: the login,
  the server, that it is real money, and the balance converted to dollars (a cent account shows cents: 1,000
  USC is $10). Ask whether they want real-money trades on it. Only after a clear yes in this conversation,
  pass `--confirm-real <login>` on `open` and `trig`. A yes for one account or one session does not carry
  over to another. If Claude Code itself blocks the order, that is a separate safety check: tell the user and
  leave it blocked.
- **Trading disabled, or balance zero**: say so; there is nothing to trade.
- A position that is "not this skill" belongs to the user or another tool. Leave it alone.

## Step 2: start the session

```
trade.py start --max-loss-pct 6 --max-trades 5            # add --target-pct 20 if the user gave a target
```

This records the starting equity and the limits. The script then refuses any order that could take equity
below the floor, that comes after the trade limit, or that comes after the target is reached. Defaults:
2% risk per trade, at most 5 trades, stop at -6% (three full losses). If the user asks for other numbers,
use theirs. The limits exist so that a bad run ends the session instead of the account.

Tell the user the plan in one or two sentences before the first trade: symbol, risk per trade, the limits.

## Step 3: read the chart

```
trade.py look BTCUSD
```

Decide three things from the output.

**1. Direction.** Trade only with the short-term trend, never against it.
- Sell only: the H1 and M15 rows say DOWN, M5 highs are getting lower, and price is under the M1 ema50.
- Buy only: the mirror image.
- MIXED on M15 and M5 with price crossing the averages back and forth: no trade. Look again in a few minutes.

**2. Entry level.** Do not sell at the low or buy at the high; the stop would have to be far away and the
target close. Wait for a pullback to the last level that broke:
- in a downtrend, the cluster of M1 lows that price fell through (old support), or the last small M1 high;
- in an uptrend, the cluster of M1 highs it broke above, or the last small M1 low.
If price is already sitting at that level and turning back, enter at market with `open`. Otherwise use `trig`
with the level, so the order is sent only if price comes back to it.

**3. Stop and target, as distances from the entry.**
- Stop: just beyond the swing that would prove the idea wrong (for a sell, a little above the most recent
  lower high). In practice this is 2 to 2.5 times the M1 ATR shown by `look`.
- Target: just in front of the next obstacle (for a sell, slightly above the recent low, or slightly below
  it only when the trend is strong). Aim for 1.1 to 1.4 times the stop distance.
- Cost check: the spread should be no more than about a tenth of the stop distance. `plan` prints this
  share. If it is higher, the market is too quiet or too expensive to scalp; skip the trade.

`plan` shows the lot size, the money at risk and the spread share without sending anything:

```
trade.py plan BTCUSD sell 2 80 95        # symbol, side, risk %, stop distance, target distance
```

## Step 4: place and manage the trade

```
trade.py trig BTCUSD sell 2 80 95 59972 --timeout 300 --wait 200     # enter only if price touches 59972
trade.py open BTCUSD sell 2 80 95 --wait 300                         # enter now
trade.py wait 400                                                    # keep waiting for stop or target
trade.py close                                                       # close at market
```

Give the tool call a 600000 ms timeout and keep `--timeout` plus `--wait` under about 540 seconds, since one
call cannot run longer than ten minutes. Write one short sentence to the user before each order (what and
why) and one after each result.

- **Not triggered**: price never came back. Do not chase it. Run `look` again and set a new level from the
  new structure. Three misses in a row usually means the move is running away or ending; consider stopping.
- **Still open**: `wait` again. If it has gone nowhere after about 15 minutes, `close` it; a scalp that
  stalls has lost its reason.
- **Never move a stop further away**, and never add to a losing trade. One trade at a time.
- **When volatility jumps** (M1 ATR doubles compared with the start of the session), widen the stop to match
  the new ATR; the script shrinks the lot so the money at risk stays the same.

## Step 5: when to stop

Stop the session when any of these is true: the trade limit is used, the script refuses an order because of
the floor or the target, the M1 ATR has roughly tripled since the start, a sharp reversal bar appears against
the trend (a long wick with heavy volume after a long run), the trend rows turn MIXED, or the user says stop.
Before the final report, make sure nothing from this skill is still open (`status`).

## Step 6: report

Run `session` and give the user:

1. One sentence with the account, the start and end equity in the account's currency, and the percentage.
2. A table: trade, entry, stop, target, exit, result in money and in R.
3. Entries that were skipped or not triggered, in one line.
4. One honest line on what the result does and does not show (sample size, whether the market moved one way).

Write in plain, short sentences; the user's first language is not English.

## Worked example

`references/session-2026-11-22.md` has the first session trade by trade: what the chart showed, where each
entry, stop and target went, and why. Read it when a setup is unclear.
