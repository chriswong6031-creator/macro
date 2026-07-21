---
slug: compound-growth-for-traders
family: article
title: "Compound Growth for Traders"
description: "Return sequencing and drawdowns dominate long-run CAGR. Why the arithmetic mean of annual returns overstates actual wealth growth and what to use instead."
cluster: risk-management
published: 2026-07-20
updated: 2026-07-20
related:
  calculators: [compounding, cagr]
cta: {href: /tools/calculators/compounding.html, label: "Model your compound growth"}
---
<p>Compounding is often described as a free lunch — let returns build on themselves and wealth grows exponentially. For traders specifically, the mechanism has a critical hidden cost: any year with a negative return does not just reduce gains, it shrinks the base that all future returns must compound against. The arithmetic mean of your annual returns systematically overstates your actual long-run wealth growth whenever any year is negative.</p>

<h2>Arithmetic mean versus geometric mean: the core difference</h2>

<p>Suppose a portfolio earns +50% in year one and −50% in year two. The arithmetic mean is (50 + (−50)) / 2 = 0%. Many traders would read this as "broke even over two years." The arithmetic tells a different story:</p>

<div class="worked">
  <span class="co-h">The +50% / −50% example</span>
  <p>Start: $10,000<br>
  After year 1 (+50%): $10,000 × 1.50 = $15,000<br>
  After year 2 (−50%): $15,000 × 0.50 = $7,500</p>

  <p>Net result over two years: −25%. Arithmetic mean: 0.0%.</p>
  <p>Geometric mean (true annual growth rate): ($7,500 / $10,000)<sup>1/2</sup> − 1 = −13.4% per year</p>

  <p>The arithmetic mean of 0% is not dishonest — it is just the wrong average for compounded wealth. The geometric mean of −13.4% per year is what actually happened to purchasing power.</p>
</div>

<p>The gap between arithmetic and geometric mean is always zero or negative, and it grows with the variance of returns. Volatile sequences — even with the same average — produce worse compound outcomes than smooth sequences. This is the volatility drag on geometric returns, and it is not a small effect in trading accounts.</p>

<h2>Why return sequencing dominates long-run CAGR</h2>

<p>Consider a trader with three years of returns: +20%, −30%, +25%. The arithmetic mean is +5% per year. The actual outcome:</p>

<div class="worked">
  <span class="co-h">Three-year compounding sequence</span>
  <p>Start: $100,000<br>
  Year 1 (+20%): $100,000 × 1.20 = $120,000<br>
  Year 2 (−30%): $120,000 × 0.70 = $84,000<br>
  Year 3 (+25%): $84,000 × 1.25 = $105,000</p>

  <p>Total 3-year gain: 5.0% — barely above zero.<br>
  CAGR: ($105,000 / $100,000)<sup>1/3</sup> − 1 = 1.64% per year.</p>

  <p>The arithmetic mean (+5.0%) is three times the actual annualized return (1.64%). The single negative year dragged the geometric mean down because it fell on a larger base (post-Year-1 gain) and forced Year 3 to recover from a deeper hole.</p>
</div>

<p>Note that the order of returns does not change the end value when there are no contributions or withdrawals — +20%, −30%, +25% and +25%, −30%, +20% both end at $105,000. Order matters enormously when cash is flowing in or out of the account, which is the situation for any trader adding to or withdrawing from their account over time.</p>

<h2>Common trap: measuring performance by arithmetic mean</h2>

<div class="callout warn">
  <span class="co-h">Common trap</span>
  Annual performance summaries often list return by year and compute an arithmetic average for the period. A trader who was up 80%, down 40%, up 80%, down 40% over four years would report a 20% average. The actual compound result: $100 × 1.80 × 0.60 × 1.80 × 0.60 = $116.64 — a 16.6% total gain over four years, or 3.9% CAGR. The 20% average is not wrong, it is just the wrong summary statistic for wealth growth.
</div>

<p>The <a href="/tools/calculators/cagr.html">CAGR calculator</a> converts a start value, end value, and time period into the true annualized growth rate. It will always return a lower number than the arithmetic mean of annual returns whenever any year is negative. Use it as the baseline for any multi-year performance comparison.</p>

<h2>How drawdowns dominate long-run CAGR</h2>

<p>The recovery arithmetic from the <a href="/blog/why-a-50-percent-loss-needs-a-100-percent-gain.html">asymmetry article</a> shows that a 30% drawdown requires a 42.9% gain just to return to the starting point. During the recovery period, compounding is working against the trader: the compound growth clock is not running — the account is merely recovering lost ground. Every year spent in recovery is a year where compound growth is zero relative to the pre-drawdown peak.</p>

<p>A 10% annual drawdown sustained over five years and recovered each time costs significantly more in foregone compounding than five years of a 2% annual drawdown. The cost is not just the drawdown itself — it is the compounding that did not happen during the recovery.</p>

<h2>Contributions and their real effect</h2>

<p>Regular contributions to a trading account interact with compounding in a way that is mechanically favorable but psychologically misleading. Adding $500 per month to an account does not earn the portfolio return on that money from inception — it earns the return only from the date of contribution. The standard compounding formula:</p>

<div class="formula">
FV = P × (1 + i)<sup>m</sup> + c × ((1 + i)<sup>m</sup> − 1) / i<br><br>
where P = initial capital, c = contribution per period, i = rate per period, m = total periods
</div>

<p>The <a href="/tools/calculators/compounding.html">compounding calculator</a> applies this formula with any combination of initial capital, monthly or quarterly contribution, annual rate, and time horizon, and outputs both the final value and a year-by-year table so the growth curve is visible rather than a single number.</p>

<p>The important limitation: the formula assumes a fixed annual rate every year. Real trading accounts have variable returns. The table is useful for modeling a target outcome — "if I start with $20,000, add $500 per month, and compound at 8%, what do I have in 15 years?" — but it does not reflect the volatility drag described above. An account that actually earns 8% arithmetic average per year with significant annual variance will end below the calculator's output because the geometric mean is lower than 8%.</p>

<h2>Honest time horizons</h2>

<p>Compounding curves are often shown with impressive-looking 20 or 30-year charts. For a retail trader who actively manages their account, the honest time horizon is the period over which they can realistically sustain the same approach. Strategy edge degrades, market regimes shift, and personal circumstances change. A 30-year compounding projection for an active trading account assumes the same edge persists for three decades, which is a significant assumption.</p>

<p>A more tractable framing: what CAGR do you need over the next five years to reach a specific account target, and is that CAGR consistent with the expectancy your system has shown over your documented trade history? The <a href="/tools/calculators/cagr.html">CAGR calculator</a> in inverse mode answers the first question; the <a href="/blog/how-to-keep-a-trading-journal.html">trading journal</a> process answers the second.</p>

<h2>Where this breaks</h2>

<p>All compounding models assume the rate of return is independent of account size. For most retail traders this is approximately true. For traders in size — where position requirements approach the liquidity available in the instruments they trade — the edge available at a small account may not be replicable at ten times the size. The compounding math is correct in that scenario, but the input (the rate) changes as the account grows.</p>

<p>The arithmetic also treats contributions as constant. In practice, contributions are irregular and discretionary. A model built on consistent monthly contributions will overestimate outcomes if the contributions are skipped in low-income months or during periods of poor trading performance. The calculator is a planning tool for a specified set of assumptions, not a forecast of what will happen.</p>
