---
id: lens_trend
kind: lens
version: 1
title: Trend and trendlines
default: true
priority: 29
triggers:
  - trend
  - trendline
  - trend line
  - uptrend
  - downtrend
  - moving average
  - ema
  - sma
  - slope
  - channel
  - 趋势
  - 趋势线
  - 均线
  - 通道
---
TREND LENS — direction, quality, and age.
Definitions: the digest's `trend` segments give direction (rising / falling / flat) and length in bars. A trend's QUALITY shows in its swing rhythm — orderly pullbacks that hold prior swings; its AGE shows in how far price has traveled from the level that started it.
Validity: trend reads mean little inside a range. If the recent segments alternate rising/falling with no net progress, call it a range and switch to the support/resistance lens.
Procedure:
1) Weekly first: the weekly trend is the tide; the daily is the wave you time. When they disagree, state both in one line and let the weekly outrank.
2) Trendlines: take candidates from the digest's `trendlines` (already ranked by touches and fit) or a line the user proposes — then measure_line. Verdict "holds" = draw it (draw.trendline, or draw.ray to project it forward) and build on it; "weak" = mention only with the caveat; "invalid" = it is not a trendline, do not draw it.
3) A good trendline has three or more touches, roughly evenly spaced, with a slope shallow enough to be sustainable. Steep lines that price hugs almost vertically break by time, not weakness — treat their break as a pace change, not "trend over".
4) Moving averages (only if the chart has them, per read_chart_state capabilities): trend context only — price above a rising average means the trend is intact. Never call a moving-average touch or cross a signal by itself.
Invalidation: the trend read dies on a daily close through the measured trendline or the controlling swing, whichever is nearer.
Worked shape: measure_line on the user's line returns 4 touches, verdict "holds". "Your line is real — four clean touches, rising support near 96.50 today. It's the spine of this move. A daily close under it is the first crack; until then, pullbacks into it are the spot to watch, not chase."
