---
slug: how-to-keep-a-trading-journal
family: article
title: "How to Keep a Trading Journal"
description: "Most trading journals die from friction or vanity metrics. The exact fields that let you compute expectancy, R multiples, and mistake cost per setup."
cluster: trading-process
published: 2026-07-20
updated: 2026-07-20
related:
  articles: [win-rate-is-overrated]
  live:
    - {href: /tools/spreadsheets/trading-journal.html, label: "Free trading journal spreadsheet"}
cta: {href: /tools/spreadsheets/trading-journal.html, label: "Download the free trading journal"}
---
<p>Most trading journals fail within a month. The two most common reasons are friction — the journal takes longer to fill in than the trade took to execute — and vanity metrics — columns that track how the trade felt rather than what it actually did to your edge. A journal that does not let you compute your expectancy per setup type at the end of each month is not telling you anything actionable.</p>

<h2>Why journals die</h2>

<p>A journal that asks "how did you feel about this trade?" is a mood diary. Mood does not have a clear relationship to future performance. A journal that only records P/L in dollars tells you whether you made money, but not whether your system has an edge or whether your results are driven by a few lucky large bets.</p>

<p>The most common fatal design flaw is the effort asymmetry: the journal requires significant time to complete (screenshots, written rationale, tagging) but the value delivered back to the trader is vague ("I see I should be more disciplined"). When the return on the time investment is not clear, the journal gets skipped on busy days, then skipped on average days, then abandoned.</p>

<div class="callout warn">
  <span class="co-h">Common trap</span>
  Adding more fields to a journal does not make it more useful. Every field that is not used to compute a specific metric at review time is dead weight that increases friction without increasing signal. Start with the minimum fields that compute expectancy and mistake cost, and add nothing else until those two metrics are being calculated consistently.
</div>

<h2>The minimum viable field set</h2>

<p>These are the exact fields that enable the calculations that matter:</p>

<table class="data">
  <thead>
    <tr>
      <th>Field</th>
      <th>Used to compute</th>
    </tr>
  </thead>
  <tbody>
    <tr><td>Date opened</td><td>Setup clustering by date/market condition</td></tr>
    <tr><td>Ticker / instrument</td><td>Per-instrument performance breakdown</td></tr>
    <tr><td>Setup type</td><td>Expectancy per setup; which to add size to</td></tr>
    <tr><td>Direction (long/short)</td><td>Directional bias analysis</td></tr>
    <tr><td>Entry price</td><td>R per share calculation</td></tr>
    <tr><td>Stop price at entry</td><td>Risk per share (entry − stop)</td></tr>
    <tr><td>Planned target</td><td>Planned R:R at entry</td></tr>
    <tr><td>Position size (shares/contracts)</td><td>Dollar risk</td></tr>
    <tr><td>Exit price</td><td>Actual R multiple outcome</td></tr>
    <tr><td>Date closed</td><td>Holding period; time-in-trade analysis</td></tr>
    <tr><td>Mistake type (or blank)</td><td>Mistake cost in R per category</td></tr>
  </tbody>
</table>

<p>From these eleven fields you can calculate: win rate per setup type, average winner in R, average loser in R, expectancy per setup (covered in the <a href="/blog/win-rate-is-overrated.html">win rate article</a>), actual versus planned R:R, and the cost in R of every mistake category. That is the information needed to improve.</p>

<h2>Mistake typing: the field most journals omit</h2>

<p>The "mistake type" field is the highest-leverage addition to any journal. Leave it blank when the trade was executed according to plan — win or lose. Fill it in only when the execution deviated from the plan. Common categories:</p>

<ul>
  <li><strong>Chased entry:</strong> entered after the planned trigger, changing the R:R</li>
  <li><strong>Moved stop:</strong> changed the stop level after entry</li>
  <li><strong>Oversized:</strong> took more than planned size</li>
  <li><strong>Early exit:</strong> closed before the stop or target was reached</li>
  <li><strong>No plan:</strong> entered a trade with no defined stop or target at entry</li>
  <li><strong>Revenge trade:</strong> re-entered to win back a loss just taken, outside the plan</li>
</ul>

<p>At the end of each month, sum the R impact of every trade tagged with each mistake category. This gives you the cost of each mistake in R — a direct measurement of what the mistake is actually taking out of your account. An early-exit habit might cost 0.8R per instance. If you have ten instances in a month at 1% risk, that is 8% of account drag from a single, fixable behavior.</p>

<h2>The 15-minute weekly review</h2>

<p>The weekly review is where the journal pays back its maintenance cost. A structured 15-minute review on the same day each week covers:</p>

<ol>
  <li>Last week's trades: actual R versus planned R per trade. Any systematic gap between planned and actual R:R is a sizing or exit discipline signal, not a market signal.</li>
  <li>Mistake count and cost this week: which categories appeared and what they cost in R.</li>
  <li>Running month-to-date expectancy by setup type: are the setups with positive expectancy from your historical data still performing as expected?</li>
  <li>Next week: any setups approaching that your historical journal shows as your highest-expectancy configurations.</li>
</ol>

<p>The weekly review is not a performance evaluation — it is a process audit. Whether you made money last week matters less than whether your execution matched your plan. A week of execution matches and a small P/L loss is a better outcome than a profitable week with three execution mistakes that happened to work out.</p>

<h2>Per-setup accountability</h2>

<p>The most actionable output of a journal after 50–100 trades is expectancy per setup type. If setup type A shows +0.5R expectancy and setup type B shows −0.1R expectancy, the decision is straightforward: size A larger and reduce or eliminate B. This is not possible with journals that record only dollar P/L, because position sizes vary and the dollar amount tells you nothing about whether the setup has edge.</p>

<p>Setup types should be defined before looking at results — defined by objective entry criteria, not by retroactive pattern recognition. A setup defined as "looked like a breakout" is not a repeatable category. A setup defined as "price above 20-day high on above-average volume, stop below prior day's low" is measurable across instances.</p>

<h2>Where this breaks</h2>

<p>A journal built around discrete, well-defined setups works well for systematic or rule-based approaches. For discretionary traders whose process involves significant context judgment that cannot be reduced to objective criteria, the per-setup expectancy calculation is harder to make meaningful because the "same" setup in two different market contexts may not be the same setup at all. In that case, the most valuable journal fields shift toward capturing market context at entry — regime, breadth, trend strength — so that expectancy can be segmented by context rather than just by price pattern.</p>

<p>The free <a href="/tools/spreadsheets/trading-journal.html">Mastermind trading journal spreadsheet</a> includes the eleven fields above plus auto-calculated R columns and a monthly summary tab that computes expectancy by setup type and mistake cost by category. The download is a starting point — the fields that matter are the ones you actually fill in.</p>
