# SMC Coach: how to read the chart

This indicator draws a story in five steps and tells you the one thing to do next. The honest answer is often **WAIT**. It never places orders and it cannot know the future.

Add it to a **15-minute** chart and read the panel in the corner from top to bottom. Hover over a row name to see a one-sentence explanation.

## The five steps, in order

| Step | What you see on the chart | Plain meaning |
| --- | --- | --- |
| 1. Direction | Panel row **1. DIRECTION (bias)**: UP, DOWN or UNCLEAR | The big picture. UP = only look for buys. DOWN = only look for sells. UNCLEAR = do nothing. It uses finished Daily and 4-hour candles, so it does not flip mid-day. |
| 2. Liquidity | Dotted lines named **PDH, PDL, PWH, PWL, Asia high, Asia low, EQH, EQL, Swing high, Swing low** with the words *magnet above* or *magnet below* | Old highs and lows where many stop orders may sit. Price is often pulled toward them. A gray line marked *taken* was already touched and no longer counts. |
| 3. Sweep, then MSS | Label **1. LOW SWEPT - PDL** (or HIGH SWEPT), then a dashed line with **2. MSS UP** (or MSS DOWN) | Sweep = price pokes through an old low or high and closes back. MSS = market structure shift: a strong candle then closes through the last swing. Both must happen, in this order. |
| 4. OB and FVG | Boxes named **BUY FVG - possible return area** and **BUY OB - possible reaction area** (or SELL) | FVG = fair value gap left by the strong candle. OB = order block, the last opposite candle before it. These are places price may come back to. A box alone is never a signal. |
| 5. Entry | Small triangle and label **BUY SETUP - WAIT**, later a **BUY** label with **BUY CONFIRMED** (or SELL) | Setup = a plan exists, do nothing yet. Confirmed = a later candle touched the FVG midpoint and closed back out of the gap. The entry is that candle's close. |

When both a low and a high are swept on the same candle you see **Both sides swept - wait**. Direction is unclear, so no setup starts.

## What the plan drawing means

When a setup exists the chart draws the plan for you:

- **WAIT: FVG MIDPOINT** dashed line: the price to watch. Price must touch it first.
- **ENTRY FVG - wait for retest + close** box: the gap price must return into.
- **BUY ENTRY** or **SELL ENTRY** solid line: appears only after the confirming candle closes.
- **STOP** dashed red line: just beyond the swept low or high. The red shaded area is the risk.
- **TP1 (PDH, 2.1R)** dashed green line: the first target. It is always a real untouched old high or low. The green shaded area is the reward. *R* means stop-distances: 2R is twice as far as the stop.
- **TP2, TP3, TP4 (reference)**: extra targets measured in R. They are arithmetic, not liquidity.

The plan can die before entry. You will then see **EXPIRED**, **CANCELLED** or **MISSED**. None of these count as a loss. After entry you see **TP1 REACHED** or **STOP REACHED**. When candle data cannot tell which came first you see **UNCERTAIN**, and that case is excluded.

**SETUP SKIPPED** with a reason means the sweep, MSS and gap all happened but a filter failed, for example the session was closed or the entry sat in the wrong half of the range. It is shown so you can learn, not so you can trade it.

## Colors and shading

| Color | Meaning |
| --- | --- |
| Green | Buy side: buy setup, buy entry, TP lines, old lows below price |
| Red | Sell side: sell setup, sell entry, stop line, old highs above price |
| Orange | Wait, skipped, expired or uncertain |
| Blue box | Order block |
| Light red / light green shading | Upper half (premium) and lower half (discount) of the recent range. Buys are only allowed in the lower half, sells only in the upper half. |
| Blue background | A trading session is open (London or New York open, New York time) |
| Yellow background | The Asian range is being built |
| Red background | Wrong chart: use standard candles on the 15-minute timeframe with an allowed ticker |

## The panel rows

1. **WHAT TO DO NOW**: the single next step. Read this first.
2. **DIRECTION**, then the Daily and 4H readings separately.
3. **LIQUIDITY above / below**: the nearest untouched old high and old low.
4. **SWEEP -> MSS (buy / sell)**: how far each side has progressed and the exact close needed.
5. **OB / FVG**, **ENTRY / STOP**, **TP1**: the plan levels once a setup exists.
6. **Plan status**, **Location / session**, **Last setup check**: why the indicator is waiting.
7. **RULE SCORE != accuracy**: how many rules agreed. 80/100 does **not** mean an 80% chance of winning.
8. **SIMULATED outcomes** and **Excluded from that rate**: this chart's own history of confirmed entries, counted from candle highs and lows without fees or slippage. Read the counts, not only the percentage.

## How much can I trust it?

- Everything is decided on **closed candles**. Labels appear when the event became known, never earlier, so history is not rewritten.
- A swing needs candles on both sides before it exists. With the default 3, it is confirmed three candles later.
- Direction uses completed Daily and 4-hour candles only.
- TP1 is never invented. If no untouched old high or low offers enough reward, there is no setup.
- The score is a rules-agreement count. The outcome history is a simplified simulation. Neither is a measured live accuracy. No accuracy is claimed or guaranteed.

## Put it on TradingView

1. Open a **15-minute** XAUUSD, BTCUSD or BTCUSDT chart with standard candles.
2. Open **Pine Editor**, paste all of `smc_setups.pine`, then **Save** and **Add to chart**.
3. In the indicator settings, add your broker's exact ticker to **Allowed tickers** if it differs. Session times are **New York time** whatever your chart timezone.
4. Keep the panel, liquidity lines and boxes visible while learning.
5. Alerts. The webhook alert stays **Any alert() function call** and sends only the BUY_SETUP / SELL_SETUP JSON. For your phone, create separate alerts from the named conditions: **BUY setup - wait**, **SELL setup - wait**, **BUY confirmed**, **SELL confirmed**, **TP1 reached**, **Stop reached**, **Plan cancelled or expired**. Choose **Once Per Bar Close**. Recreate alerts after any change to the script or its settings.

Practice on a paper-trading chart first, reading the sequence out loud: **direction → liquidity → sweep → MSS → FVG → wait for the confirming close**.

## Small glossary

- **Bias / direction**: which way the bigger timeframes last broke.
- **Liquidity**: an old high or low where stop orders may gather.
- **PDH / PDL**: previous day high / low. **PWH / PWL**: previous week high / low. **EQH / EQL**: equal highs / lows. **Asia high / low**: the finished Asian session range.
- **Sweep**: price pokes through liquidity and closes back on the original side.
- **MSS**: market structure shift, a strong close through the last swing after a sweep.
- **BOS**: break of structure, a close through a swing that continues the current direction.
- **FVG**: fair value gap, the empty space a strong candle leaves between its neighbors.
- **OB**: order block, the last opposite candle before the strong move.
- **Premium / discount**: upper / lower half of the recent range.
- **R**: one stop-distance. Reward is measured in R.
