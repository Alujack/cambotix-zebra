# XAUUSD ICT dataset `xauusd_ict_zerospread` (development rows)

23,966 development candidates from 2008-01-01 to 2024-11-20; 23,476 fit the account (stop at most $10 at the minimum position); 15,538 of those filled. Lockbox: 2,915 candidates from 2024-11-20 on, written unread; 1 straddling candidates dropped.

Built 2026-11-21 14:36 UTC from `D:\tradingPlatform\cambotix-zebra\.local\history_dukascopy_full\XAUUSD_m1.csv` at commit 45da2c1; target 2R, entry expiry 120 min, hold 360 min; spread x 0.

Every tradable setup, no model: +0.003R per filled trade before slippage, total +49.2R (overlapping trades all counted).

| Year | Candidates | Tradable | Filled | Target | Stop | Timeout | Exp. R | Total R |
|---|---|---|---|---|---|---|---|---|
| 2008 | 1519 | 1490.0 | 945.0 | 22.4% | 58.7% | 18.8% | -0.074 | -70.2 |
| 2009 | 1357 | 1349.0 | 897.0 | 24.0% | 54.2% | 21.9% | -0.004 | -3.5 |
| 2010 | 1336 | 1329.0 | 922.0 | 25.9% | 53.5% | 20.6% | +0.056 | +51.7 |
| 2011 | 1639 | 1543.0 | 1044.0 | 26.5% | 54.6% | 18.9% | +0.040 | +41.9 |
| 2012 | 1413 | 1387.0 | 942.0 | 26.2% | 53.1% | 20.7% | +0.045 | +42.6 |
| 2013 | 1348 | 1315.0 | 834.0 | 23.0% | 56.5% | 20.5% | -0.036 | -30.2 |
| 2014 | 1441 | 1429.0 | 918.0 | 24.1% | 54.2% | 21.7% | -0.001 | -1.3 |
| 2015 | 1347 | 1346.0 | 870.0 | 26.6% | 54.5% | 19.0% | +0.069 | +59.9 |
| 2016 | 1412 | 1401.0 | 922.0 | 24.3% | 56.2% | 19.5% | -0.003 | -3.0 |
| 2017 | 1328 | 1326.0 | 884.0 | 23.5% | 53.7% | 22.7% | +0.027 | +23.7 |
| 2018 | 1439 | 1436.0 | 953.0 | 23.4% | 56.7% | 19.9% | -0.031 | -29.6 |
| 2019 | 1420 | 1412.0 | 931.0 | 25.1% | 53.8% | 21.1% | +0.034 | +32.1 |
| 2020 | 1400 | 1320.0 | 895.0 | 25.8% | 55.2% | 19.0% | +0.028 | +25.1 |
| 2021 | 1381 | 1358.0 | 882.0 | 23.8% | 58.4% | 17.8% | -0.040 | -35.1 |
| 2022 | 1467 | 1428.0 | 964.0 | 25.1% | 58.6% | 16.3% | -0.039 | -37.9 |
| 2023 | 1394 | 1361.0 | 906.0 | 26.6% | 57.0% | 16.4% | +0.020 | +17.9 |
| 2024 | 1325 | 1246.0 | 829.0 | 24.2% | 59.7% | 16.0% | -0.042 | -34.8 |

Outcomes:

- closed: 15,874
- not_filled:tp1_reached_before_entry: 5,419
- not_filled:entry_expired: 2,668
- not_filled:opened_beyond_stop: 5

Spread repair (ml.data.repair_spread):

- 2003: floor 0.606 raised 102,991 bars
- 2004: floor 0.606 raised 209,255 bars
- 2005: floor 0.706 raised 274,710 bars
- 2006: floor 0.706 raised 329,188 bars
- 2007: floor 0.606 raised 343,430 bars
- 2008: floor 0.604 raised 359,761 bars
- 2009: floor 0.704 raised 358,369 bars
- 2010: floor 0.806 raised 362,099 bars
- 2012: 8,145 zero spreads replaced
