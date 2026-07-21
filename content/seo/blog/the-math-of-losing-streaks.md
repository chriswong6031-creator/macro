---
slug: the-math-of-losing-streaks
family: article
title: "The Math of Losing Streaks"
description: "Losing streaks are a mathematical certainty at any realistic win rate. The only question is whether your position sizing lets you survive them."
cluster: risk-management
published: 2026-07-20
updated: 2026-07-20
related:
  calculators: [position-size]
  lessons: [risk/position-sizing]
cta: {href: /tools/calculators/position-size.html, label: "Size your positions to survive the streak"}
---
<p>At a 50% win rate over 100 trades, there is an 81% chance you will experience at least five consecutive losses at some point during that run. The math is not a warning about bad luck — it is a statement about the structure of random sequences. Position sizing is what decides whether a streak ends your account or just ends your day.</p>

<h2>Why streaks are not anomalies</h2>
<p>Traders often treat a run of losses as evidence that something broke: the market changed, the edge disappeared, or the strategy failed. Sometimes that is true. But before drawing that conclusion it is worth understanding how frequently long losing streaks appear in purely random coin-flip sequences.</p>

<p>The probability that a specific sequence of <em>N</em> trades is all losses is simply the loss probability raised to the power <em>N</em>. That is the per-position formula. Over 100 trades there are many overlapping windows where such a streak could start, so the chance that at least one streak of length <em>N</em> appears somewhere in 100 trades is much higher than any single-start calculation suggests.</p>

<div class="formula">
Per-streak probability: P(N consecutive losses starting at one position) = q<sup>N</sup><br>
where q = 1 − win rate<br><br>
Example: at 50% win rate, q = 0.50, so 5 losses in a row = 0.50<sup>5</sup> = 3.1% per streak start
</div>

<p>The table below uses exact dynamic-programming recurrence to answer the more useful question: over a 100-trade sample, what is the probability that a losing streak of at least <em>N</em> occurs at least once?</p>

<table class="data">
  <thead>
    <tr>
      <th>Consecutive losses</th>
      <th class="num">40% win rate</th>
      <th class="num">50% win rate</th>
      <th class="num">60% win rate</th>
    </tr>
  </thead>
  <tbody>
    <tr><td>3 in a row</td><td class="num">100%</td><td class="num">100%</td><td class="num">99%</td></tr>
    <tr><td>4 in a row</td><td class="num">100%</td><td class="num">97%</td><td class="num">80%</td></tr>
    <tr><td>5 in a row</td><td class="num">98%</td><td class="num">81%</td><td class="num">46%</td></tr>
    <tr><td>6 in a row</td><td class="num">87%</td><td class="num">55%</td><td class="num">21%</td></tr>
    <tr><td>7 in a row</td><td class="num">69%</td><td class="num">32%</td><td class="num">9%</td></tr>
    <tr><td>8 in a row</td><td class="num">49%</td><td class="num">17%</td><td class="num">4%</td></tr>
  </tbody>
</table>

<p>Read the 50% win rate column carefully. Seven losses in a row has a 32% chance of appearing in 100 trades — roughly one in three. A 40% win rate (realistic for many trend-following approaches) gives nearly a 70% chance of a seven-loss streak. These are not tail events. They are the expected texture of real trading under realistic assumptions.</p>

<h2>The common trap: treating a streak as a signal</h2>

<div class="callout warn">
  <span class="co-h">Common trap</span>
  After four or five consecutive losses, many traders cut position size dramatically or stop trading entirely. If the losses are just random variance within a positive-expectancy system, this is exactly when they are stopping right before the recovery. The streak itself tells you almost nothing about what the next trade will do.
</div>

<p>The right response to a losing streak is not to change how many trades you take — it is to verify that the setup conditions your edge depends on are still present. Edge verification and position sizing are separate questions. Confusing them is expensive.</p>

<h2>Fixed-fractional sizing and survival arithmetic</h2>

<p>The mechanism that determines whether a streak ends your account is position sizing. With fixed-dollar sizing (risk the same dollar amount every trade), a seven-loss streak removes a fixed dollar amount regardless of account size. With fixed-fractional sizing (risk a fixed percentage of current account each trade), the loss compounds against a shrinking base.</p>

<div class="worked">
  <span class="co-h">Fixed-fractional sizing through a streak</span>
  <p>Suppose a trader risks 2% of their current account per trade and suffers seven consecutive losses.</p>
  <p>After 1 loss: account × 0.98<br>
  After 2 losses: account × 0.98<sup>2</sup> = 0.9604<br>
  After 7 losses: account × 0.98<sup>7</sup> ≈ 0.8681</p>
  <p>Result: a 7-loss streak at 2% risk leaves the account at 86.8 cents on the dollar — a 13.2% drawdown.</p>
  <p>At 5% risk per trade, the same streak: 0.95<sup>7</sup> ≈ 0.6983 — a 30.2% drawdown.</p>
  <p>At 10% risk per trade: 0.90<sup>7</sup> ≈ 0.4783 — a 52.2% drawdown that now requires a 109% gain to recover.</p>
</div>

<p>The asymmetry of losses — covered in the companion article on <a href="/blog/why-a-50-percent-loss-needs-a-100-percent-gain.html">why a 50% loss requires a 100% gain</a> — means large drawdowns from oversized positions are far more damaging than the symmetric numbers suggest. This is why professional traders obsess over the risk percentage per trade, not the win rate.</p>

<p>A sizing framework that lets you survive an eight-loss streak is not being overly conservative — the table above shows there is roughly a 50% chance of encountering one at a 40% win rate over 100 trades. The <a href="/tools/calculators/position-size.html">position size calculator</a> turns the account size, entry price, and stop level into a share count that limits each loss to a chosen percentage of capital.</p>

<h2>Ruin logic: when size makes streaks fatal</h2>

<p>Ruin in trading rarely comes from one catastrophic trade. It comes from a streak that is ordinary in length but taken with a position size that makes it irrecoverable. An account that loses 50% requires a 100% gain to return to even. An account that loses 75% requires a 300% gain. The exit condition from ruin scales non-linearly with drawdown depth.</p>

<p>The practical implication is that position sizing is not a risk preference — it is a survival constraint. Risk per trade should be chosen so that the streak length with a reasonable probability of occurring in your expected sample of trades produces a drawdown from which recovery is arithmetically possible within a realistic time horizon.</p>

<h2>Where this analysis breaks</h2>

<p>The table above assumes independence: each trade's outcome has no relationship to the previous one. Real market outcomes are not fully independent. Consecutive losses in a live account often occur during the same unfavorable regime — trending systems losing repeatedly during choppy markets, mean-reversion systems getting run over during strong trends. In those cases streaks cluster, and the random-independence model understates the actual correlation.</p>

<p>This does not change the sizing conclusion — if anything it strengthens it. If losses are correlated rather than independent, streaks will be longer and more frequent than the table predicts at a given win rate. The table is a lower bound on streak severity in real markets, not a ceiling.</p>

<p>Second, the table assumes a fixed win rate across all 100 trades. Real systems show win rate variation by market condition. A 50% win-rate average can mask periods of 30% and periods of 70%, and the streaks during the 30% periods will be longer than the average-rate model suggests.</p>
