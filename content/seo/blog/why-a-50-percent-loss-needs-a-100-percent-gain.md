---
slug: why-a-50-percent-loss-needs-a-100-percent-gain
family: article
title: "Why a 50% Loss Needs a 100% Gain"
description: "Losses and gains are not symmetric. A 50% drawdown requires a 100% return to recover — the math that makes drawdown depth the professional obsession."
cluster: risk-management
published: 2026-07-20
updated: 2026-07-20
related:
  calculators: [drawdown-recovery, cagr]
cta: {href: /tools/calculators/drawdown-recovery.html, label: "Calculate your recovery requirement"}
---
<p>Lose 50% of your account, and you need to earn 100% on the remaining capital just to get back to where you started. This is not a peculiarity of bad luck — it follows directly from arithmetic, and it explains why experienced risk managers focus on drawdown depth rather than average returns.</p>

<h2>The recovery arithmetic</h2>

<p>If you start with $100 and lose <em>d</em> percent, you have $<em>(100 − d)</em> remaining. To return to $100, the required gain on that smaller base is:</p>

<div class="formula">
Required recovery gain = d / (100 − d) × 100%
</div>

<p>The required gain is always larger than the loss that caused it, and the gap widens rapidly as losses grow deeper:</p>

<table class="data">
  <thead>
    <tr>
      <th>Loss suffered</th>
      <th class="num">Recovery required</th>
    </tr>
  </thead>
  <tbody>
    <tr><td>5%</td><td class="num">5.3%</td></tr>
    <tr><td>10%</td><td class="num">11.1%</td></tr>
    <tr><td>15%</td><td class="num">17.6%</td></tr>
    <tr><td>20%</td><td class="num">25.0%</td></tr>
    <tr><td>25%</td><td class="num">33.3%</td></tr>
    <tr><td>30%</td><td class="num">42.9%</td></tr>
    <tr><td>40%</td><td class="num">66.7%</td></tr>
    <tr><td>50%</td><td class="num">100.0%</td></tr>
    <tr><td>60%</td><td class="num">150.0%</td></tr>
    <tr><td>70%</td><td class="num">233.3%</td></tr>
    <tr><td>80%</td><td class="num">400.0%</td></tr>
    <tr><td>90%</td><td class="num">900.0%</td></tr>
  </tbody>
</table>

<p>A 20% drawdown requires a 25% gain to recover — uncomfortable but achievable. A 50% drawdown requires doubling. An 80% drawdown requires quintupling the remaining capital before you break even. At that point the math is not telling you that recovery is impossible, but it is telling you that your entire remaining capital must compound at exceptional rates for an extended period just to get back to zero progress.</p>

<h2>Common trap: treating return and loss as symmetric</h2>

<div class="callout warn">
  <span class="co-h">Common trap</span>
  A portfolio that loses 30% in one year and gains 30% the following year is not back to even — it is down 9%. The +30% applies to a smaller base. Evaluating performance by averaging annual returns without accounting for this compounding effect overstates actual wealth accumulation, sometimes dramatically.
</div>

<p>Suppose a trader reports: "I was up 40% last year and only down 30% this year — my average is +5%." The arithmetic says otherwise: $100 × 1.40 × 0.70 = $98. The two-year result is a 2% loss. The average-return narrative is not dishonest — it is just not the number that matters for wealth.</p>

<h2>The sequence-of-returns problem: a worked example</h2>

<p>The order of returns matters as much as the returns themselves when capital is moving in or out of an account. Consider a trader starting with $100,000 over three years with the following returns:</p>

<div class="worked">
  <span class="co-h">Three-year sequence example</span>
  <p>Year 1: +20% → $100,000 × 1.20 = $120,000<br>
  Year 2: −30% → $120,000 × 0.70 = $84,000<br>
  Year 3: +25% → $84,000 × 1.25 = $105,000</p>

  <p>Final value: $105,000 on a $100,000 start — a 5% total gain over three years.<br>
  Arithmetic mean of annual returns: (+20 − 30 + 25) / 3 = +5.0% per year<br>
  Actual CAGR: ($105,000 / $100,000)<sup>1/3</sup> − 1 = 1.64% per year</p>

  <p>The 5% arithmetic average is three times the actual annualized return. The single year of −30% dragged the geometric mean down to 1.64%, not because the negative year was particularly severe in isolation, but because it fell on a larger base (the account after a 20% gain) and left a smaller base for the recovery.</p>
</div>

<p>Use the <a href="/tools/calculators/cagr.html">CAGR calculator</a> to convert any start-value, end-value, and time period into a true annualized growth rate that accounts for compounding. It will consistently return a lower number than the arithmetic mean whenever any year is negative.</p>

<h2>Why drawdown depth, not return, is the professional measure</h2>

<p>The recovery table above makes clear why drawdown depth is the primary risk metric for professional managers. A fund that achieves 12% annual returns with a maximum drawdown of 15% is fundamentally different from one achieving 15% annual returns with a 40% maximum drawdown — not just in risk tolerance, but in achievable recovery paths for investors who entered near a peak.</p>

<p>An investor who bought at the peak of a 40% drawdown needs a 66.7% gain on their entry price to break even before they see any real profit. If the fund compounds at 15% annually from the trough, that recovery takes over three years. During that entire recovery period the investor has experienced no net progress from their personal entry point.</p>

<p>This is why the <a href="/tools/calculators/drawdown-recovery.html">drawdown recovery calculator</a> is not just for risk management — it is for setting honest expectations. Enter the drawdown depth and an assumed annual return, and it shows how many years the recovery requires. A 50% drawdown at a 10% annual recovery rate takes 7.3 years. At 7% annual it takes 10.2 years.</p>

<h2>Where this breaks</h2>

<p>The recovery formula assumes the account compounds quietly with no contributions or withdrawals. In practice, if a trader adds capital during a drawdown they reduce the percentage gain required for dollar recovery (though they now have more capital exposed at a depressed level). If they withdraw during a drawdown, the recovery percentage required is higher in dollar terms even if the math on the remaining base is unchanged.</p>

<p>The formula also says nothing about how long the recovery will take — only what percentage gain is needed. The time dimension depends on the post-drawdown return rate, which is unknown. A deep drawdown might recover in one exceptional year or might drag across a decade of normal returns. The <a href="/blog/compound-growth-for-traders.html">compounding article</a> covers why long-horizon CAGR is the honest measure here.</p>

<p>Finally, the table assumes a single drawdown event recovers fully before another occurs. In practice, accounts that have experienced a severe drawdown often sustain secondary drawdowns before full recovery, particularly if the original drawdown reflected a regime shift rather than normal variance. The table is the best case — no further losses until recovery is complete.</p>
