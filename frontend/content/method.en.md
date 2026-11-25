# How Zebra reads the market

**Educational use only. Trading can cause substantial financial loss.**

Zebra is a rule-based desk. Every setup it publishes comes from fixed rules on the broker's own candles, never from a language model's opinion. The AI only writes a short note; the rules decide. This page explains the ideas behind those rules in plain words.

## 1. The market moves between pools of orders

Behind every obvious high and low sit resting orders: stops of people already in a trade and entries of people waiting for a breakout. ICT traders call these pools **liquidity**. Price tends to travel from one pool to the next, because that is where the orders are.

Zebra names the pools it watches: the previous day's high and low (PDH / PDL), the previous week's (PWH / PWL), the completed Asian session range, equal highs or lows, and the last confirmed swing. Each pool can be used once; after price touches it, it is spent until a new one forms.

## 2. A sweep is price poking through a pool and coming back

When a candle trades beyond a pool and closes back inside, the orders there have been taken. That is a **liquidity sweep**. It does not mean "buy" or "sell" by itself. It means the fuel on that side is gone and the market may now travel the other way.

## 3. A market structure shift needs displacement

After a sweep, Zebra waits for a strong candle — its body at least one ATR — that closes through the last swing in the opposite direction. That is a **market structure shift (MSS)**. A weak drift through the level does not count; the candle must show intent.

## 4. The fair value gap is where price moved too fast

A fast candle leaves a gap between the candle before and the candle after it: a **fair value gap (FVG)**. Price often returns to fill part of it. Zebra plans its entry at the middle of that gap, and only confirms the entry when a later candle touches the middle and closes back beyond the gap in the trade's direction.

## 5. Discount and premium

Between the swept low and the recent high (or the reverse for a short) lies the dealing range. Buys are planned only in the lower half — a **discount** — and sells only in the upper half — a **premium**. Buying high in the range is not a plan.

## 6. Higher timeframes decide the direction

The Daily and the 4-hour chart must agree on the direction before a 15-minute setup is allowed. Both are read from completed candles only, never from the one still forming.

## 7. Time matters

Setups must form inside an ICT killzone in New York time: the London open (02:00–05:00) or the New York open (08:30–11:00). Outside those windows the same shape is ignored. High-impact news for the currency blocks setups for a window around the event.

## 8. The plan is fixed before the trade

Entry, stop beyond the swept liquidity, TP1 at the next untouched pool, and further targets in multiples of the risk — all computed deterministically and frozen into the ledger the moment the plan is published. Nothing about a plan is changed afterwards.

## 9. The record is graded, not told

A grader replays the broker's one-minute candles, spread included, and records what really happened: filled or not, which targets, the stop, or a time-out. When one candle could have hit both a target and the stop, the stop is counted. Wins and losses stay on the record forever.

## 10. What the classic model does differently

The classic model is a trend filter rather than a structure model: price above a rising EMA20 / 50 / 200 stack, RSI in its band, MACD histogram on the right side, ADX strong enough, ATR inside a volatility band, during London or New York hours. It is simpler and fires less often; both models are graded on their own lines so the record shows which one actually earns.

## 11. What Zebra will not do

It will not place orders. It will not show a win rate that excludes losses. It will not sell live signals before the forward test reads GO: at least 150 closed trades, positive expectancy and a drawdown within the limit.
