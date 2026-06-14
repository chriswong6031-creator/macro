# Dislocation validation (Phase 0, hardened)

```
====================================================================================================
DISLOCATION VALIDATION (hardened) — SPY 1997-01-01..2026-06-12
  MASTER SWITCH: PUT-ABSENT = recession(Sahm>=0.5) OR fedput_off(sust. 10y breakeven>=2.5%)
  honest lens: hit-rate AND conditional max-drawdown · episode-declustered · bootstrap CI · split-half · LOYO
====================================================================================================

### AQR NULL — buying a RANDOM day (the 'stay fully invested' bar to beat)
  all days (21d)         n=7620  hit= 64.6%  medRet=  +1.4%  medDD=  -1.8%  p10DD=   -7.2%
  all days (63d)         n=7620  hit= 69.9%  medRet=  +3.6%  medDD=  -3.3%  p10DD=  -12.5%
  all days (126d)        n=7557  hit= 74.1%  medRet=  +6.3%  medDD=  -4.2%  p10DD=  -17.6%
  all days (252d)        n=7431  hit= 79.7%  medRet= +13.2%  medDD=  -5.7%  p10DD=  -24.7%

### master-switch coverage
  recession    true on  16.4% of days
  fedput_off   true on   7.6% of days
  downtrend    true on  21.0% of days
  PUT-ABSENT   on  24.0% of days  => PUT-PRESENT 76.0%

====================================================================================================
MASTER-SWITCH TEST — stress episodes split by Fed-put state (63d & 252d)
====================================================================================================

[DIP>10%]
  -- 63d --
  PUT-PRESENT (buyable)  n= 17  hit= 64.7%  medRet=  +4.0%  medDD=  -7.2%  p10DD=   -9.6%
  PUT-ABSENT (stand aside) n=  5  hit= 40.0%  medRet=  -0.2%  medDD=  -6.2%  p10DD=   -7.9%
  -- 252d --
  PUT-PRESENT (buyable)  n= 17  hit= 76.5%  medRet= +16.9%  medDD=  -9.5%  p10DD=  -25.9%
  PUT-ABSENT (stand aside) n=  5  hit= 40.0%  medRet=  -3.4%  medDD= -14.0%  p10DD=  -38.6%

[VIX>30]
  -- 63d --
  PUT-PRESENT (buyable)  n= 19  hit= 63.2%  medRet=  +2.4%  medDD=  -4.5%  p10DD=   -9.0%
  PUT-ABSENT (stand aside) n= 10  hit= 50.0%  medRet=  +3.2%  medDD=  -7.5%  p10DD=  -18.4%
  -- 252d --
  PUT-PRESENT (buyable)  n= 19  hit= 57.9%  medRet= +14.7%  medDD= -11.2%  p10DD=  -28.9%
  PUT-ABSENT (stand aside) n= 10  hit= 60.0%  medRet= +10.0%  medDD= -12.8%  p10DD=  -27.2%

[VRP pctile>0.90]
  -- 63d --
  PUT-PRESENT (buyable)  n= 40  hit= 75.0%  medRet=  +5.0%  medDD=  -2.0%  p10DD=   -9.8%
  PUT-ABSENT (stand aside) n= 15  hit= 40.0%  medRet=  -1.4%  medDD=  -7.7%  p10DD=  -19.3%
  -- 252d --
  PUT-PRESENT (buyable)  n= 40  hit= 87.5%  medRet= +13.9%  medDD=  -3.4%  p10DD=  -16.7%
  PUT-ABSENT (stand aside) n= 15  hit= 60.0%  medRet= +12.6%  medDD= -14.0%  p10DD=  -30.4%

[VIX backwardation]
  -- 63d --
  PUT-PRESENT (buyable)  n= 29  hit= 69.0%  medRet=  +4.1%  medDD=  -2.6%  p10DD=  -12.0%
  PUT-ABSENT (stand aside) n= 12  hit= 66.7%  medRet= +10.1%  medDD=  -3.0%  p10DD=   -8.7%
  -- 252d --
  PUT-PRESENT (buyable)  n= 27  hit= 81.5%  medRet= +15.2%  medDD=  -4.6%  p10DD=  -18.2%
  PUT-ABSENT (stand aside) n= 12  hit= 75.0%  medRet= +19.2%  medDD=  -4.7%  p10DD=  -19.1%

[STRESS (composite)]
  -- 63d --
  PUT-PRESENT (buyable)  n= 37  hit= 70.3%  medRet=  +3.8%  medDD=  -2.9%  p10DD=   -8.8%
  PUT-ABSENT (stand aside) n= 10  hit= 40.0%  medRet=  -4.1%  medDD=  -6.8%  p10DD=   -9.6%
  -- 252d --
  PUT-PRESENT (buyable)  n= 37  hit= 86.5%  medRet= +13.3%  medDD=  -4.5%  p10DD=  -17.0%
  PUT-ABSENT (stand aside) n= 10  hit= 60.0%  medRet= +11.4%  medDD= -10.5%  p10DD=  -25.3%

====================================================================================================
EPISODE BLOCK BOOTSTRAP — 95% CI on (PUT-PRESENT minus PUT-ABSENT), STRESS composite, B=5000
  drawdown diff > 0  => present-bucket trough is SHALLOWER (the veto reduces path pain)
====================================================================================================
  n: PUT-PRESENT=37 episodes, PUT-ABSENT=10 episodes
  -- 63d --
    tail drawdown (p10)    diff=  +0.2  95% CI [  -3.2,   +3.5]  (>0 shallower) -> spans 0
    median drawdown        diff=  +3.9  95% CI [  +0.3,   +6.3]  (>0 shallower) -> ROBUST
    hit-rate               diff= +30.3  95% CI [  -5.1,  +63.0]  (>0 higher) -> spans 0
    median return          diff=  +7.4  95% CI [  -2.7,  +12.3]  (>0 higher) -> spans 0
  -- 252d --
    tail drawdown (p10)    diff=  +8.2  95% CI [  -4.6,  +37.0]  (>0 shallower) -> spans 0
    median drawdown        diff=  +5.6  95% CI [  -2.9,  +16.6]  (>0 shallower) -> spans 0
    hit-rate               diff= +26.5  95% CI [  -4.3,  +59.2]  (>0 higher) -> spans 0
    median return          diff=  +2.8  95% CI [  -4.7,  +26.0]  (>0 higher) -> spans 0

====================================================================================================
DOES PRIMARY-TREND ADD ON TOP OF THE PUT SWITCH?  (PUT-PRESENT stress, 63d)
====================================================================================================
  put-present & uptrend  n= 38  hit= 73.7%  medRet=  +4.1%  medDD=  -2.2%  p10DD=   -8.6%
  put-present & downtrend n=  9  hit= 55.6%  medRet=  +6.5%  medDD=  -5.2%  p10DD=   -8.0%

====================================================================================================
SPLIT-HALF (OOS) — STRESS composite, PUT-PRESENT vs PUT-ABSENT, 63d
====================================================================================================
  1997-2011:
  put-present    n= 13  hit= 61.5%  medRet=  +2.0%  medDD=  -2.9%  p10DD=   -9.8%
  put-absent     n=  6  hit= 33.3%  medRet=  -4.4%  medDD=  -6.7%  p10DD=   -9.1%
  2012-2025:
  put-present    n= 25  hit= 76.0%  medRet=  +5.3%  medDD=  -2.6%  p10DD=   -7.9%
  put-absent     n=  4  hit= 50.0%  medRet=  -0.8%  medDD=  -7.0%  p10DD=   -9.0%

====================================================================================================
LEAVE-ONE-YEAR-OUT — sign consistency of the tail-drawdown edge (63d)
  edge = p10DD(put-present) - p10DD(put-absent); >0 means present is shallower
====================================================================================================
  full-sample edge = +0.8pp;  sign holds dropping 26/28 of the crisis years (1997..2025)

====================================================================================================
GATE-2 ENTRY TIMER — within BUYABLE-WASHOUT episodes, immediate vs wait-for-confirm (63d)
  hook = VIX term un-invert (2 closes); thrust = Zweig adv-ratio (no up-volume in store).
  arms ONLY after Gate-1 buyable. A confirm that REDUCES drawdown at acceptable return cost = useful.
====================================================================================================
  buyable episodes (2006+): 28;  with a hook: 18 (median lag 13d);  with a thrust: 12 (median lag 16d)
  -- term-structure hook (matched subset) --
  immediate entry        n= 18  hit= 61.1%  medRet=  +2.2%  medDD=  -4.5%  p10DD=   -8.6%
  wait for hook          n= 18  hit= 66.7%  medRet=  +4.6%  medDD=  -2.9%  p10DD=   -9.9%
  -- breadth thrust (matched subset) --
  immediate entry        n= 12  hit= 66.7%  medRet=  +2.2%  medDD=  -3.9%  p10DD=   -8.0%
  wait for thrust        n= 12  hit= 66.7%  medRet=  +6.1%  medDD=  -1.7%  p10DD=  -11.0%

====================================================================================================
NAMED-EPISODE LEDGER — entry = max-VIX day in window; put-state tag + outcome
====================================================================================================
  episode         entry        VIX  Sahm   be  200d    put-state   fwd63  fwd252   dd63  dd252
  1998 LTCM       1998-10-08    46  0.20  nan    up  put-present  +29.3%  +34.7%  +2.0%  +2.0%   
  2000-02 dotcom  2002-08-05    45  1.13  nan  DOWN   PUT-ABSENT   +6.1%  +20.5%  -6.4%  -6.4%   recession
  2008 GFC        2008-11-20    81  1.70  0.0  DOWN   PUT-ABSENT   +5.8%  +49.0%  +5.4%  -9.0%   recession
  2010 flash      2010-05-20    46  0.80  1.9    up   PUT-ABSENT   +2.4%  +27.8%  -4.5%  -4.5%   recession
  2011 EU/dgrade  2011-08-08    48  0.23  2.2    up  put-present  +13.0%  +21.9%  -1.6%  -1.6%   
  2015-16 China   2015-08-24    41 -0.13  1.5    up  put-present  +10.6%  +17.3%  -1.2%  -2.4%   
  2018 volmaged   2018-02-05    37  0.00  2.1    up  put-present   -0.1%   +1.7%  -2.4%  -9.5%   
  2018Q4 selloff  2018-12-24    36  0.07  1.8  DOWN  put-present  +22.0%  +36.0%  +0.0%  +0.0%   
  2020 COVID      2020-03-16    83  0.30  0.7    up  put-present  +26.1%  +62.0%  -6.5%  -6.5%   
  2022 bear       2022-03-07    36 -0.10  2.8    up   PUT-ABSENT   -0.2%   -3.4%  -6.9% -14.0%   fedput_off
  2023 SVB        2023-03-13    27  0.00  2.2    up  put-present  +11.8%  +33.4%  +1.0%  +1.0%   
  2024 yen carry  2024-08-05    39  0.57  2.1    up   PUT-ABSENT  +10.2%  +24.1%  +0.2%  -3.1%   recession
  2025 tariff     2025-04-08    52  0.27  2.2    up  put-present  +26.3%  +31.4%  +3.5%  +3.5%   

====================================================================================================
READ-ME: a robust risk-filter shows the bootstrap drawdown-diff CI ENTIRELY > 0 and the LOYO sign holding across most crisis years. Return-diffs spanning 0 = no return edge (expected).
====================================================================================================
```
