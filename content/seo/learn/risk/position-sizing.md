---
slug: position-sizing
family: lesson
title: "Position Sizing: The Only Edge You Fully Control"
description: "Fixed-fractional sizing sets shares from account size, risk %, entry, and stop. Learn the formula, a worked example, and what it cannot protect you from."
track: risk
cluster: risk-management
published: 2026-07-20
updated: 2026-07-20
related:
  calculators: [position-size]
  lessons: [risk/risk-reward-expectancy]
cta: {href: /tools/calculators/position-size.html, label: "Try the position size calculator"}
---
<div class="callout lead">
<span class="co-h">Learning objective</span>
Understand the fixed-fractional position sizing formula, why dollar risk and position value are different numbers, and what happens to the model when stops cannot be honored at their stated price.
</div>

<p>Position sizing determines how many shares to buy or sell short on a given trade. It is the mechanism that translates a probability estimate and a risk tolerance into a concrete share count. Of all the decisions in a trade — entry timing, exit target, stop placement — position size is the one variable a trader controls with certainty before entering the market.</p>

<h2>The fixed-fractional formula</h2>

<div class="formula">
Inputs: Account size (A), Risk percent per trade (r%), Entry price (E), Stop price (S)
<br>
Dollar risk   = A × r / 100
Risk per share = |E − S|
Shares        = floor(Dollar risk / Risk per share)
Position value = Shares × E
Position %    = 100 × Position value / A
</div>

<p>The floor function (rounding down to the nearest whole share) ensures you never exceed your intended dollar risk. Direction is determined by the stop placement: if S is below E, the trade is long; if S is above E, the trade is short.</p>

<h2>Worked example matching the calculator</h2>

<div class="worked">
<span class="co-h">Worked example — Long trade</span>
<p>Account: <strong>$10,000</strong> | Risk: <strong>1%</strong> | Entry: <strong>$50.00</strong> | Stop: <strong>$48.00</strong></p>
<p>Dollar risk = $10,000 × 1 / 100 = <strong>$100</strong></p>
<p>Risk per share = |$50.00 − $48.00| = <strong>$2.00</strong></p>
<p>Shares = floor($100 / $2.00) = <strong>50 shares</strong></p>
<p>Position value = 50 × $50.00 = <strong>$2,500</strong> (25% of account)</p>
<p>If the stop is hit and the trade exits at exactly $48.00, the loss is 50 × $2.00 = <strong>$100</strong> — 1% of the account, as intended.</p>
</div>

<div class="worked">
<span class="co-h">Worked example — Short trade</span>
<p>Account: <strong>$25,000</strong> | Risk: <strong>0.5%</strong> | Entry: <strong>$12.40</strong> | Stop: <strong>$13.10</strong> (above entry, short)</p>
<p>Dollar risk = $25,000 × 0.5 / 100 = <strong>$125</strong></p>
<p>Risk per share = |$12.40 − $13.10| = <strong>$0.70</strong></p>
<p>Shares = floor($125 / $0.70) = <strong>178 shares</strong></p>
<p>Position value = 178 × $12.40 = <strong>$2,207.20</strong> (8.8% of account)</p>
</div>

<h2>Risk per trade vs. position value: a critical distinction</h2>

<p>Dollar risk ($100 in the first example) and position value ($2,500) are not the same number. Dollar risk is how much you lose if stopped out at your intended exit — the amount at stake in the trade. Position value is the total capital deployed, which determines margin requirements, concentration exposure, and what happens if the stock goes to zero. A trader risking 1% of account per trade on high-volatility names with tight stops may be deploying 30–40% of account value per position. Both numbers are worth knowing; conflating them is a common accounting error.</p>

<h2>Common trap: sizing by conviction</h2>

<p>Adding to position size when you "feel strongly" about a trade is the most common deviation from fixed-fractional discipline, and it is precisely backwards from a risk-management perspective. The trades you feel most certain about do not have better outcomes on that basis alone — certainty is a psychological state, not a statistical edge. Systematically over-sizing on high-conviction trades concentrates the variance exactly where you are least prepared to be wrong, which is when conviction is highest.</p>

<h2>When this breaks</h2>

<p>Fixed-fractional sizing assumes your stop will be honored at or near your stated exit price. Two conditions break this assumption. First, overnight gaps: if a stock gaps below your stop at the open, your broker fills you at the open price, not your stop — the actual loss may be substantially larger than the 1% you sized for. Sizing for an intended 1% risk does not cap your actual loss if fills are gapped through. Second, correlated positions: if you hold five positions each sized for 1% risk but all five are in the same sector and all gap down on the same macro event, your portfolio experiences a simultaneous 5% loss — the per-trade sizing model treated each position independently, but they were not independent in their risk.</p>

<p>The <a href="/learn/risk/risk-reward-expectancy.html">risk/reward and expectancy lesson</a> covers how the trade-off between win rate and reward size determines whether a given sizing approach has positive expectancy over time.</p>

<p>The position size calculator runs these formulas with any inputs: <a href="/tools/calculators/position-size.html">try the position size calculator</a>.</p>

<details>
<summary>Self-check: 3 questions</summary>
<ol>
<li><strong>Account: $50,000. Risk per trade: 0.5%. Entry: $30.00. Stop: $27.50. How many shares, what is the dollar risk, and what is the position value?</strong><br>Dollar risk = $50,000 × 0.5 / 100 = $250. Risk per share = |$30.00 − $27.50| = $2.50. Shares = floor($250 / $2.50) = 100 shares. Position value = 100 × $30.00 = $3,000 (6% of account).</li>
<li><strong>A trader has two positions, each sized for 1% risk. Both are technology stocks. On a macro event, both gap down through their stops at open. The actual losses are 2.8% and 3.1% of account. Why did fixed-fractional sizing not protect the trader from a combined 5.9% loss?</strong><br>Fixed-fractional sizing defines intended risk assuming fills at the stop price. Overnight gaps mean the stock opens beyond the stop, and the fill is at the opening price — which can be far through the stated stop. The method controls the risk you take at entry; it cannot control how the market prices the exit. Additionally, the two positions were correlated and responded to the same event simultaneously, compounding the gap effect across both positions.</li>
<li><strong>Why is "size larger because I'm very confident" a risk-management error rather than a rational adjustment?</strong><br>Confidence is a psychological state about your own assessment. It does not change the statistical distribution of outcomes. Markets can and do move against high-conviction positions. Systematically concentrating more capital on the trades where you are most certain means the trades that deviate most from your expectations (which will happen) are the ones where you have the most at stake — the opposite of a risk-controlled approach.</li>
</ol>
</details>
