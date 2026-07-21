---
slug: risk-reward-expectancy
family: lesson
title: "Risk/Reward Ratios and Trade Expectancy Explained"
description: "R multiples, breakeven win rates, and expectancy show whether a setup has edge. Learn the formulas and the trap that makes most R:R calculations worthless."
track: risk
cluster: risk-management
published: 2026-07-20
updated: 2026-07-20
related:
  calculators: [risk-reward]
  lessons: [risk/position-sizing]
cta: {href: /tools/calculators/risk-reward.html, label: "Try the risk/reward calculator"}
---
<div class="callout lead">
<span class="co-h">Learning objective</span>
Understand R multiples and R:R ratios, how to calculate the breakeven win rate for any given R:R, and what expectancy in R means — including why inflated targets make these numbers meaningless.
</div>

<p>A risk/reward ratio expresses how much you stand to gain relative to how much you stand to lose on a trade. Measured in R (one R = the dollar risk on the trade), a 3:1 R:R means the target is three times as far from entry as the stop. The ratio is only as honest as the target and stop it is built on.</p>

<h2>The formulas</h2>

<div class="formula">
Inputs: Entry (E), Stop (S), Target (T), optional Win Rate (w%)
<br>
R:R ratio = |T − E| / |E − S|
<br>
Breakeven win rate = 100 / (1 + R:R)   [%]
<br>
Expectancy in R   = (w/100) × R:R − (1 − w/100)
  [where w is your actual win rate as a percentage]
</div>

<p>These formulas assume that wins exit exactly at target and losses exit exactly at stop — an idealization discussed in the "when this breaks" section below.</p>

<h2>Worked example</h2>

<div class="worked">
<span class="co-h">Worked example</span>
<p>Entry: <strong>$100</strong> | Stop: <strong>$95</strong> | Target: <strong>$115</strong></p>
<p>R:R = |$115 − $100| / |$100 − $95| = 15 / 5 = <strong>3.0</strong></p>
<p>Breakeven win rate = 100 / (1 + 3.0) = 100 / 4 = <strong>25%</strong></p>
<p>At a 3:1 R:R, you only need to be right on 1 in 4 trades to break even over time.</p>
<p>Now suppose your actual win rate is 40%:</p>
<p>Expectancy = (0.40 × 3.0) − (0.60 × 1) = 1.20 − 0.60 = <strong>+0.60R</strong></p>
<p>Every trade in this setup has a positive expected value of 0.60R — 60% of one unit of risk, on average, per trade placed.</p>
</div>

<h2>Breakeven win rates at common R:R ratios</h2>

<table class="data">
<thead><tr><th>R:R ratio</th><th class="num">Breakeven win rate</th></tr></thead>
<tbody>
<tr><td>1:1</td><td class="num">50.0%</td></tr>
<tr><td>2:1</td><td class="num">33.3%</td></tr>
<tr><td>3:1</td><td class="num">25.0%</td></tr>
<tr><td>4:1</td><td class="num">20.0%</td></tr>
<tr><td>5:1</td><td class="num">16.7%</td></tr>
</tbody>
</table>

<p>This table shows a mechanical fact: as R:R increases, the win rate required to break even decreases. There is no free lunch here — a very high R:R ratio requires a target that is very far from entry, which means fewer trades will ever reach it.</p>

<h2>What expectancy in R means</h2>

<p>Expectancy expresses the average result per trade in units of R. A +0.60R expectancy on a setup where you risk $100 per trade means you expect to earn $60 per trade on average over a large sample. It does not mean any individual trade returns $60 — individual trades return either a win (approximately +RR × risk$) or a loss (approximately −risk$). The expectancy is the population average, meaningful only over many repetitions of the same setup under similar conditions.</p>

<h2>Common trap: inflating R:R with fantasy targets</h2>

<p>A trader sets a $3 stop and a $15 target, producing a 5:1 R:R and a comfortable-looking 16.7% required win rate. If the target has no structural basis — no identified resistance level, no earnings catalyst, no measured move — then the 5:1 is a planning fiction. The actual exit distribution for that trade will be determined by what happens in the market, not by the number written in the trading plan. A theoretical 5:1 with a target that gets hit 3% of the time has a negative expectancy. The ratio only means something when both the target and stop are rooted in your actual exit discipline.</p>

<h2>When this breaks</h2>

<p>Two real-world conditions systematically shift actual results away from the formula's predictions. First, slippage: stops are not always honored at their stated price. A stock that gaps through your stop produces a loss larger than 1R. Over many trades in volatile or thinly traded names, actual average losses per trade exceed 1R, which degrades the expectancy below its theoretical value. Second, fat tails: the formula assumes wins cluster around target and losses cluster around stop. Real price distributions include occasional very large moves in both directions. A position held through a takeover bid might exit at 10R; a position held through a flash crash might exit at −5R. These outliers affect the empirical expectancy but are invisible in the theoretical R:R calculation.</p>

<p>Expectancy also requires knowing your actual win rate — which requires a trading log. The <a href="/learn/risk/position-sizing.html">position sizing lesson</a> covers how to size each trade so your actual dollar risk matches what the formulas assume.</p>

<p>Run these calculations with your own entries, stops, and targets: <a href="/tools/calculators/risk-reward.html">try the risk/reward calculator</a>.</p>

<details>
<summary>Self-check: 3 questions</summary>
<ol>
<li><strong>Entry: $200. Stop: $190. Target: $230. What is the R:R and the breakeven win rate?</strong><br>R:R = |$230 − $200| / |$200 − $190| = 30 / 10 = 3.0. Breakeven win rate = 100 / (1 + 3.0) = 25%. You need to win on at least 1 in 4 such trades to break even.</li>
<li><strong>Using the same trade above (R:R = 3.0), suppose your historical win rate on this setup is 35%. What is your expectancy in R, and what does it mean in dollar terms if you risk $200 per trade?</strong><br>Expectancy = (0.35 × 3.0) − (0.65 × 1) = 1.05 − 0.65 = +0.40R. At $200 risk per trade, this means an expected average result of 0.40 × $200 = $80 per trade over a large sample. Individual trades still win or lose; $80 is the population mean.</li>
<li><strong>A setup has a theoretical 4:1 R:R. In practice, the target is almost never reached, and most profitable trades are closed early at roughly 1.5R. What is the actual effective R:R, and what does that do to the required win rate?</strong><br>The effective R:R is approximately 1.5 (based on actual exit behavior, not the planned target). Breakeven win rate at 1.5:1 = 100 / (1 + 1.5) = 40% — significantly higher than the 20% the 4:1 plan implied. The gap between theoretical and actual R:R is where most trading plans quietly fail.</li>
</ol>
</details>
