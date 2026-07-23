---
id: lens_structure
kind: lens
version: 1
title: Market structure
default: true
priority: 30
triggers:
  - structure
  - swing
  - swings
  - higher high
  - higher low
  - lower high
  - lower low
  - pivot
  - break of structure
  - 结构
  - 高点
  - 低点
  - 转折
---
STRUCTURE LENS — read the skeleton before anything else.
Definitions: swings are the digest's pivot list (`swings`, each a high or a low). An uptrend's skeleton = rising swing lows, each floor above the last; a downtrend's = falling swing highs. The most recent three or four swings carry most of the information.
Validity: needs a trending or clearly ranging chart. In a compressed drift (tiny swings, volatility "quiet") structure reads are low-information — say so instead of forcing one.
Procedure:
1) chart_digest → take the last 4–6 swings and name the pattern plainly: "higher lows since April" / "lower highs since the peak".
2) The line in the sand = the most recent confirmed swing low (in an up move) or swing high (in a down move). That is your invalidation candidate.
3) A structure break = a CLOSE beyond that swing, not a poke through it. A wick through the level that closes back inside (the same or next bar) = a failed break — often more informative than the break itself, because the trapped traders fuel the reverse move.
4) Mark at most: the controlling swing (draw.marker or draw.label) and the break level (draw.hline).
Invalidation: the structure read dies when the defining swing is closed through.
Worked shape: digest shows swing lows 91.20 → 96.40 → 102.10 with price at 108. Read: "Climbing on higher lows; 102 is the newest floor. Above it, buyers keep control. A daily close below 102 breaks the pattern for the first time — that's where I'd rethink."
