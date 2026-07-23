---
id: lens_volume
kind: lens
version: 1
title: Volume character
priority: 22
triggers:
  - volume
  - on volume
  - accumulat
  - distribut
  - obv
  - money flow
  - absorb
  - absorption
  - 成交量
  - 放量
  - 缩量
  - 吸筹
  - 派发
  - 量能
---
VOLUME LENS — confirmation, never a signal on its own.
House truth first: the desk's own testing found no standalone directional edge in raw flow or volume reads. Volume never CREATES a thesis; it grades one already built from structure and levels. Never say "big volume means they're buying" as a naked claim.
Definitions — character, not numbers. Think effort versus result: a wide-range bar closing near its extreme on heavy turnover = conviction. Heavy turnover with NO progress (small range, mid-bar close) at a level = absorption — someone is quietly sitting on the move. A breakout on thin turnover = suspect until the retest holds.
Procedure:
1) Build the read from structure and levels first. Then, if the chart carries a volume study (check read_chart_state capabilities), grade only the KEY bars: the breakout bar, the test of the level, the widest bar of the latest swing.
2) Cross-check with the desk's stage engine rather than eyeballing raw bars: get_stage_peers(symbol) gives the engine's stage read plus its technical scoring and industry standing, and read_stage_analysis shows where it sees strength across the market. Relay what those tools SAY as context — never as proof that anyone is buying or selling.
3) Vocabulary for the user, in plain words: "heavy trade but price went nowhere — that's absorption at the floor" / "the breakout came on thin volume — I want the retest to hold before trusting it".
Invalidation: volume never invalidates anything by itself; the level does. Volume only changes how much benefit of the doubt the level gets.
Worked shape: breakout through 112 on quiet turnover. "It cleared the wall, but on light trade — half a breakout. If it holds 112 on the retest, it's real. If it slips back under, that was a trap and the read flips."
