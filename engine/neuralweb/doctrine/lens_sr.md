---
id: lens_sr
kind: lens
version: 1
title: Support and resistance
default: true
priority: 28
triggers:
  - support
  - resistance
  - level
  - levels
  - zone
  - ceiling
  - floor
  - key level
  - retest
  - 支撑
  - 阻力
  - 压力
  - 关键位
  - 回踩
---
S/R LENS — where the fight happens.
Definitions: the digest's `levels` are price shelves built from repeated pivots. Each carries touches (how many times it was fought over), side (support / resistance / both), and freshness (fresh / recent / stale). Side "both" = a role-flip level — an old ceiling now acting as floor, or the reverse. Those are the strongest kind.
Validity: levels weaken with age and with every clean break. A "stale" level untouched for months is a zone of interest, not a wall.
Procedure:
1) chart_digest → keep the two to four levels that actually bracket today's price (`context.nearest_support` / `nearest_resistance`, each with its atr_away distance). A level three swings away is trivia; the two nearest are the trade.
2) Weight levels by touches (more = realer), freshness, and role-flips (side "both" outranks).
3) Draw a zone, not a line, when touches cluster across a band: draw.zone over the cluster. A single crisp level = draw.hline. The caption says what happened there ("rejected here three times since May").
4) Breaks count on a decisive CLOSE through the level. The retest from the other side is the higher-quality entry area — flag it ("watch how it behaves if price comes back to 112 from above").
5) atr_away tells you if there is room: a thesis aimed at a target with less than one ATR of air to the next wall is a poor trade even when the direction is right — say so.
Invalidation: an S/R thesis dies when its level is closed through in the wrong direction.
Worked shape: levels show 112.40 resistance (5 touches, fresh) and 104.80 support (3 touches, side "both"); price 106. "Price sits just above a floor that used to be a ceiling — that flip usually means real buyers. 112.40 has turned back five attempts; that's the wall. Above it there's open air. Below 104.80 the floor is gone and I'd stand aside."
