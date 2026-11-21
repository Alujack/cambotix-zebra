# XAUUSD ICT dataset `xauusd_ict_halfspread` (development rows)

23,966 development candidates from 2008-01-01 to 2024-11-20; 23,476 fit the account (stop at most $10 at the minimum position); 15,052 of those filled. Lockbox: 2,915 candidates from 2024-11-20 on, written unread; 1 straddling candidates dropped.

Built 2026-11-21 11:57 UTC from `D:\tradingPlatform\cambotix-zebra\.local\history_dukascopy_full\XAUUSD_m1.csv` at commit 45da2c1; target 2R, entry expiry 120 min, hold 360 min; spread x 0.5.

Every tradable setup, no model: -0.097R per filled trade before slippage, total -1464.9R (overlapping trades all counted).

| Year | Candidates | Tradable | Filled | Target | Stop | Timeout | Exp. R | Total R |
|---|---|---|---|---|---|---|---|---|
| 2008 | 1519 | 1490.0 | 908.0 | 18.6% | 63.7% | 17.7% | -0.206 | -187.3 |
| 2009 | 1357 | 1349.0 | 840.0 | 18.3% | 60.8% | 20.8% | -0.194 | -163.3 |
| 2010 | 1336 | 1329.0 | 870.0 | 20.0% | 62.0% | 18.0% | -0.162 | -141.3 |
| 2011 | 1639 | 1543.0 | 1008.0 | 23.4% | 59.0% | 17.6% | -0.070 | -70.4 |
| 2012 | 1413 | 1387.0 | 915.0 | 23.4% | 57.0% | 19.6% | -0.059 | -54.0 |
| 2013 | 1348 | 1315.0 | 819.0 | 21.7% | 59.7% | 18.6% | -0.111 | -91.2 |
| 2014 | 1441 | 1429.0 | 882.0 | 21.7% | 57.1% | 21.2% | -0.088 | -77.4 |
| 2015 | 1347 | 1346.0 | 838.0 | 24.0% | 58.2% | 17.8% | -0.027 | -23.0 |
| 2016 | 1412 | 1401.0 | 902.0 | 23.1% | 58.9% | 18.1% | -0.061 | -55.1 |
| 2017 | 1328 | 1326.0 | 852.0 | 21.2% | 56.3% | 22.4% | -0.053 | -44.9 |
| 2018 | 1439 | 1436.0 | 931.0 | 21.7% | 59.0% | 19.3% | -0.088 | -81.5 |
| 2019 | 1420 | 1412.0 | 898.0 | 21.4% | 58.7% | 19.9% | -0.108 | -96.9 |
| 2020 | 1400 | 1320.0 | 878.0 | 23.5% | 57.5% | 19.0% | -0.043 | -37.6 |
| 2021 | 1381 | 1358.0 | 873.0 | 22.0% | 60.9% | 17.1% | -0.117 | -102.4 |
| 2022 | 1467 | 1428.0 | 939.0 | 23.3% | 60.9% | 15.8% | -0.103 | -97.0 |
| 2023 | 1394 | 1361.0 | 888.0 | 24.9% | 59.3% | 15.8% | -0.044 | -38.9 |
| 2024 | 1325 | 1246.0 | 811.0 | 21.8% | 62.3% | 15.9% | -0.127 | -102.7 |

Outcomes:

- closed: 15,377
- not_filled:tp1_reached_before_entry: 5,427
- not_filled:entry_expired: 3,158
- not_filled:opened_beyond_stop: 4

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
