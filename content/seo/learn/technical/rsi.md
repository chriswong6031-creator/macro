---
slug: rsi
family: lesson
title: "RSI Explained: Mechanics, Limits, and When It Lies"
description: "RSI measures recent gains vs. losses via Wilder smoothing. Learn the exact formula, what 70 and 30 actually mean statistically, and when RSI stops working."
track: technical
cluster: momentum-indicators
published: 2026-07-20
updated: 2026-07-20
related:
  lessons: [technical/macd]
cta: {href: /learn/technical/macd.html, label: "Next lesson: MACD — the trend-momentum hybrid"}
---
<div class="callout lead">
<span class="co-h">Learning objective</span>
Understand how RSI is constructed using Wilder smoothing, what the 70 and 30 thresholds actually represent statistically, and under what market conditions RSI stops providing useful information.
</div>

<p>The Relative Strength Index measures the average size of recent upward price moves against the average size of recent downward moves, compressed into a 0–100 scale. It does not measure strength relative to other stocks; it measures momentum within a single price series.</p>

<h2>The exact formula</h2>

<div class="formula">
Step 1 — Separate gains and losses over n periods (default n = 14):
<br>
  Gain(t) = max(Close(t) − Close(t−1), 0)
  Loss(t) = max(Close(t−1) − Close(t), 0)
<br><br>
Step 2 — Wilder smoothing (exponential, α = 1/n):
<br>
  AvgGain(t) = (AvgGain(t−1) × (n−1) + Gain(t)) / n
  AvgLoss(t) = (AvgLoss(t−1) × (n−1) + Loss(t)) / n
<br><br>
Step 3 — Relative Strength and RSI:
<br>
  RS = AvgGain / AvgLoss
  RSI = 100 − (100 / (1 + RS))
</div>

<p>The first calculation requires a simple average over n periods to seed the smoothing. After that, each bar uses the recursive Wilder formula. This smoothing is slower to react than a standard EMA with the same period — by design. J. Welles Wilder published the indicator in 1978 intending it for commodities markets with daily bars.</p>

<h2>Worked example</h2>

<div class="worked">
<span class="co-h">Worked example</span>
<p>Suppose a 5-period RSI with the following closes: 100, 102, 101, 104, 103, 106.</p>
<p>Gains: 2, 0, 3, 0, 3 — Losses: 0, 1, 0, 1, 0</p>
<p>Seed AvgGain = (2+0+3+0+3)/5 = <strong>1.6</strong></p>
<p>Seed AvgLoss = (0+1+0+1+0)/5 = <strong>0.4</strong></p>
<p>RS = 1.6 / 0.4 = 4.0</p>
<p>RSI = 100 − (100 / (1 + 4.0)) = 100 − 20 = <strong>80</strong></p>
<p>An RSI of 80 on this 5-period window reflects that gains over the period substantially outpaced losses — not that the stock is about to fall.</p>
</div>

<h2>What 70 and 30 actually mean</h2>

<p>Wilder chose 70 and 30 as rules of thumb for commodity markets with mean-reverting tendencies. They are not mathematically derived thresholds — they are approximate distribution tails. In a strongly trending equity market, RSI can remain above 70 for weeks or months without reversing. In a strongly declining market, it can stay below 30 for extended periods. The levels do not predict reversal; they describe recent momentum composition. A reading above 70 means recent gains have substantially dominated recent losses. Whether that continues is a separate question.</p>

<h2>Divergence: what it measures and what it does not</h2>

<p>Bullish divergence occurs when price makes a lower low while RSI makes a higher low. This means the second low was reached with less downward momentum than the first — the selling acceleration slowed. It does not tell you when or whether price will reverse. Divergence can persist or deepen before resolving. It is a momentum observation, not a trigger.</p>

<h2>Common trap: oversold in a downtrend</h2>

<p>The most reliable RSI trap is treating an oversold reading in a downtrend as a buy signal. In a true downtrend, RSI reaching 30 is simply describing the ongoing downtrend — not signaling its end. The instrument is working correctly; the assumption that oversold means "about to rally" is the error. Mean-reversion interpretations of RSI work better in range-bound markets where price genuinely oscillates around a center.</p>

<h2>When this breaks</h2>

<p>RSI becomes nearly uninformative in two conditions. First, during strong trends, the indicator parks near an extreme and stays there — providing no actionable differentiation between "just entered a strong trend" and "trend is about to end." The 14-period Wilder smoothing was calibrated for a specific market era and regime; it was not derived from cross-market backtests. Second, RSI is highly sensitive to the starting seed. Two implementations seeded differently on the same price series will produce different RSI values until enough bars accumulate to wash out the seed. When comparing RSI readings across platforms, a difference of several points on the same price chart is normal and expected — it is not a calculation error.</p>

<p>The MACD lesson covers how combining a trend filter with a momentum oscillator can address RSI's trend-pinning weakness: <a href="/learn/technical/macd.html">MACD — the trend-momentum hybrid</a>.</p>

<details>
<summary>Self-check: 3 questions</summary>
<ol>
<li><strong>In the Wilder smoothing formula with n=14, what is the effective decay factor (α)?</strong><br>α = 1/n = 1/14 ≈ 0.0714. Each new period contributes 1/14th of its value; the prior smoothed average carries 13/14ths. This is slower to react than a standard 14-period EMA, which uses α = 2/(14+1) ≈ 0.133.</li>
<li><strong>A stock has been in a confirmed downtrend for eight weeks. RSI drops to 28. What does this reading tell you, and what common mistake should you avoid?</strong><br>RSI at 28 describes that recent losses have heavily outpaced recent gains over the 14-period window — it is accurately reflecting the downtrend's momentum. The common mistake is interpreting "oversold" as a buy signal. In a downtrend, oversold readings are the norm, not a reversal indicator.</li>
<li><strong>You open two charting platforms and both show RSI(14) for the same ticker. Platform A shows 62; Platform B shows 58. Is one of them wrong?</strong><br>Not necessarily. The difference almost certainly reflects different seeds. RSI is initialized with a simple average over the first n periods, and depending on how much history each platform loaded before applying the recursive formula, the smoothed values will differ. Given enough history, they converge — but "enough" can mean hundreds of bars.</li>
</ol>
</details>
