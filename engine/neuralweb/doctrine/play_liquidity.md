---
id: play_liquidity
kind: playbook
version: 1
title: Gaps and liquidity
priority: 17
triggers:
  - gap
  - gaps
  - gap fill
  - liquidity
  - sweep
  - stop hunt
  - stop run
  - round number
  - wick
  - fakeout
  - 缺口
  - 补缺
  - 流动性
  - 扫损
  - 假突破
---
LIQUIDITY PLAYBOOK — where the resting orders sit, and what happens when price visits them.
Definitions: orders cluster at obvious places — just beyond swing highs and lows (stops), at round numbers, at the edges of gaps. Price gets drawn to these pools and often REACTS there. A fast poke beyond an obvious level that immediately reverses (a sweep) means the fuel got spent — the move that follows is usually the real one, in the other direction.
Gaps (the digest's `gaps` list — each with direction and its top and bottom edges): an unfilled gap below price left by a strong open = a demand shelf whose FIRST retest often holds. An open gap near a target is a magnet worth mentioning — but "often" is behavior, not a law; never quote fill odds.
Procedure:
1) chart_digest → gaps plus levels. Note which pools sit near price: the nearest unfilled gap edges, round numbers within about one ATR, the most recent swing extreme.
2) Call a failed break a sweep ONLY when the reversal is decisive — a close back through the level the same or next bar. A slow grind back is just a failed move, no special information.
3) Trade-location logic, framed honestly: entering exactly at the obvious level everyone can see is the crowd's position; the sweep-and-reclaim of that level is the professional version of the same idea, with the crowd's stops as fuel. Explain both without promising either.
4) Draw: the gap as a draw.zone across its edges ("unfilled gap from the earnings pop"); the swept level as a draw.hline with what happened there.
Invalidation: a sweep read dies if price re-breaks the swept level and HOLDS beyond it — it wasn't a sweep, it was the start of the real break.
Worked shape: gap 96.20–99.00 below price; swing low 101.50 swept to 100.80 then a close at 103. "They ran the stops under 101.50 and it snapped straight back — buyers used that fuel. First real support below is the open gap at 99. As long as that flush low at 100.80 holds, dips look bought."
