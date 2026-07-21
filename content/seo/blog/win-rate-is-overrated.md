---
slug: win-rate-is-overrated
family: article
title: "Win Rate Is Overrated"
description: "A 35% win rate can be more profitable than a 70% win rate. Expectancy — not how often you win — determines whether a system makes money."
cluster: risk-management
published: 2026-07-20
updated: 2026-07-20
related:
  calculators: [risk-reward]
  articles: [how-to-keep-a-trading-journal]
cta: {href: /tools/calculators/risk-reward.html, label: "Calculate your system's expectancy"}
---
<p>A trading system that wins 35% of the time can be more profitable than one that wins 70% of the time. Win rate is only half the equation — the other half is how much you win versus how much you lose on each trade. Expectancy, not win rate, is the number that determines whether a system makes money over time.</p>

<h2>The expectancy formula</h2>

<p>Expectancy measures the average amount won or lost per unit of risk across all trades. Expressed in R multiples — where 1R is the amount risked per trade — it is:</p>

<div class="formula">
Expectancy = (Win% × Average Win in R) − (Loss% × Average Loss in R)<br><br>
Win% + Loss% = 100%<br>
A positive expectancy means the system makes money over a large sample; negative means it loses.
</div>

<p>R multiples give a unit-neutral way to measure outcomes. If you risk $200 on a trade and the trade makes $600, the outcome is +3R. If you lose, it is −1R. Working in R separates sizing decisions from edge measurement — a useful property when reviewing trades across different position sizes.</p>

<h2>35% win rate beats 70% win rate: the arithmetic</h2>

<div class="worked">
  <span class="co-h">Two systems, 100 trades each</span>

  <p><strong>System A — 35% win rate, 3:1 average win to loss ratio</strong><br>
  Win% = 35, Average Win = 3R, Average Loss = 1R<br>
  Expectancy = (0.35 × 3R) − (0.65 × 1R) = 1.05R − 0.65R = <strong>+0.40R per trade</strong></p>

  <p>Over 100 trades at 1% risk per trade on a $50,000 account ($500 per trade):<br>
  Average profit = 100 × $500 × 0.40 = $20,000</p>

  <p><strong>System B — 70% win rate, 0.5:2 average win to loss ratio</strong><br>
  Win% = 70, Average Win = 0.5R, Average Loss = 2R<br>
  Expectancy = (0.70 × 0.5R) − (0.30 × 2R) = 0.35R − 0.60R = <strong>−0.25R per trade</strong></p>

  <p>Over 100 trades at the same 1% risk:<br>
  Average loss = 100 × $500 × 0.25 = $12,500</p>

  <p>System A wins 35% of the time and makes money. System B wins 70% of the time and loses money. The difference is entirely in the ratio of average winner to average loser.</p>
</div>

<p>System B is psychologically seductive precisely because of its high win rate. Winning 7 out of 10 trades feels good. But if each winner returns half a unit while each loser costs two units, the account bleeds steadily over time. This pattern — high win rate, poor reward structure — is how many intuitive trading styles produce inconsistent results despite frequent winning trades.</p>

<h2>The common trap: confusing win rate with edge</h2>

<div class="callout warn">
  <span class="co-h">Common trap</span>
  Traders who focus on win rate tend to cut winners early (to lock in the win) and hold losers long (to avoid booking the loss). Both behaviors directly undermine expectancy: they shrink average winners and expand average losers, moving toward a high-win-rate, negative-expectancy profile. The emotional pull toward high win rates actively works against profitability.
</div>

<p>The discipline that positive-expectancy systems require is usually the opposite of what feels comfortable. Trend-following approaches with 35–40% win rates often outperform over time precisely because they allow winners to compound while cutting losers promptly. The discomfort of frequent small losses is structural, not a signal that the system is broken. A <a href="/blog/how-to-keep-a-trading-journal.html">trading journal</a> that tracks R multiples per setup is the only reliable way to measure whether your actual expectancy matches your intended system.</p>

<h2>Breakeven win rate as a function of reward ratio</h2>

<p>For any given average win-to-loss ratio (the R:R ratio), there is an exact win rate at which expectancy equals zero. Any win rate above that level produces positive expectancy; below it produces negative expectancy.</p>

<div class="formula">
Breakeven win% = 100 / (1 + R:R)
</div>

<table class="data">
  <thead>
    <tr>
      <th>Average R:R (win/loss)</th>
      <th class="num">Minimum win rate needed</th>
    </tr>
  </thead>
  <tbody>
    <tr><td>0.5 : 1 (small winners vs losers)</td><td class="num">66.7%</td></tr>
    <tr><td>1 : 1 (equal winners and losers)</td><td class="num">50.0%</td></tr>
    <tr><td>1.5 : 1</td><td class="num">40.0%</td></tr>
    <tr><td>2 : 1</td><td class="num">33.3%</td></tr>
    <tr><td>2.5 : 1</td><td class="num">28.6%</td></tr>
    <tr><td>3 : 1</td><td class="num">25.0%</td></tr>
    <tr><td>4 : 1</td><td class="num">20.0%</td></tr>
    <tr><td>5 : 1</td><td class="num">16.7%</td></tr>
  </tbody>
</table>

<p>The table reveals the design space. A system with a 2:1 average reward-to-risk ratio is profitable at any win rate above 33.3%. A system with 0.5:1 requires winning more than two-thirds of the time to break even. Every trading approach implicitly sits somewhere in this space — the question is whether the trader knows where.</p>

<p>Use the <a href="/tools/calculators/risk-reward.html">risk-reward calculator</a> to compute the R:R on any trade before entry, given a specific entry price, stop level, and target. It also shows the expectancy contribution of a single trade given your historical win rate at that R:R.</p>

<h2>What win rate is actually useful for</h2>

<p>Win rate is not useless — it matters in at least two ways. First, very low win rates (below roughly 25%) create long losing streaks that can be psychologically difficult to sustain even when the system has positive expectancy. The <a href="/blog/the-math-of-losing-streaks.html">article on losing streaks</a> shows that a 35% win rate over 100 trades carries a roughly 99.5% chance of hitting at least a five-loss streak. Position sizing must account for this even when the long-run edge is positive.</p>

<p>Second, win rate interacts with expectancy stability. A system with a 70% win rate and positive expectancy will show more consistent short-term results than a 30% win-rate system with the same expectancy, because the high-win-rate system has lower per-period variance. This is not a reason to prefer high win rate — it is a reason to understand how many trades your edge requires before the expectancy becomes reliable.</p>

<h2>Where this breaks</h2>

<p>Expectancy assumes the distribution of wins and losses is stationary — that the win rate and average R values from your sample will persist into the future. In real markets they will not. Win rates shift with market regime, volatility conditions, and correlation regimes. A system with measured positive expectancy in one environment may have negative expectancy in another. This is why the journal and periodic recalculation matter: the expectancy calculation is not a one-time finding, it is a running measurement.</p>

<p>The formula also assumes trades are independent, which overstates reliability. When markets trend strongly in one direction, consecutive trades in a trend-following system will be positively correlated — both winning or both losing together. Correlated trade outcomes produce more variance than the independent model assumes, meaning that even a positive-expectancy system can underperform its expected value for extended periods during regime changes.</p>
