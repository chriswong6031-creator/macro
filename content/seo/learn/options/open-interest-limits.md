---
slug: open-interest-limits
family: lesson
title: "What Open Interest Can and Cannot Tell You"
description: "The same open interest fits a dealer being flat, long, or short. Learn why OI alone cannot sign dealer inventory and what modelling fills the gap."
track: options
cluster: dealer-positioning
published: 2026-07-25
updated: 2026-07-25
related:
  lessons: [options/dealer-hedging-mechanics]
  live:
    - {href: /options.html#ticker, label: "Options workspace — per-name dealer positioning"}
cta: {href: /learn/options/dealer-hedging-mechanics.html, label: "Next lesson: how dealer hedging becomes real order flow"}
---
<div class="callout lead">
<span class="co-h">Learning objective</span>
Understand exactly what open interest measures, why it cannot by itself tell you which side the dealer is on, that some venues publish exchange-tagged participant data that can, and — most importantly — that our own surfaces present dealer positioning as a model built from open interest plus heuristics, and label it as such.
</div>

<p>Open interest is the number of option contracts of a given strike and expiration that are currently outstanding — opened and not yet closed or expired. It is one of the most quoted numbers in options analysis, and it is genuinely useful: it tells you where activity has accumulated, which strikes carry the most outstanding exposure, and how that exposure builds or unwinds over time.</p>

<p>But there is a hard limit to what open interest can tell you, and getting this limit right is the single most important honesty point in this entire track.</p>

<h2>Every contract has two sides — open interest hides which is which</h2>

<p>Open interest counts contracts, and every contract has a buyer and a seller. A strike showing 5,000 contracts of open interest tells you 5,000 contracts exist. It does <strong>not</strong> tell you whether the market maker is long them, short them, or flat because their customer positions offset. The same open-interest number is consistent with completely opposite dealer positions.</p>

<figure class="sig-fig">
<div class="sig-stage">
<svg viewBox="0 0 640 180" preserveAspectRatio="none" role="img" aria-label="Three columns all showing the same open interest of five, but with the dealer flat in the first, long in the second, and short in the third — proving open interest cannot sign the dealer position.">
  <line class="sg-zero" x1="40" y1="95" x2="620" y2="95"/>
  <!-- column A: dealer flat (on the zero line) -->
  <rect class="fill-mut" x="70" y="60" width="120" height="70"/>
  <circle class="dot-mut" cx="130" cy="95" r="6"/>
  <!-- column B: same OI, dealer LONG (marker above neutral) -->
  <rect class="fill-mut" x="260" y="60" width="120" height="70"/>
  <rect class="fill-up" x="300" y="52" width="40" height="43"/>
  <circle class="dot-up" cx="320" cy="52" r="6"/>
  <!-- column C: same OI, dealer SHORT (marker below neutral) -->
  <rect class="fill-mut" x="450" y="60" width="120" height="70"/>
  <rect class="fill-down" x="490" y="95" width="40" height="43"/>
  <circle class="dot-down" cx="510" cy="138" r="6"/>
</svg>
<span class="sig-lbl axis" style="left:8%; top:53%;">dealer<br>neutral</span>
<span class="sig-lbl big" style="left:20.3%; top:41%;">OI = 5</span>
<span class="sig-lbl big" style="left:50%; top:41%;">OI = 5</span>
<span class="sig-lbl big" style="left:79.7%; top:41%;">OI = 5</span>
<span class="sig-lbl" style="left:20.3%; top:63%;">dealer flat</span>
<span class="sig-lbl up" style="left:50%; top:22%;">dealer long</span>
<span class="sig-lbl down" style="left:79.7%; top:82%;">dealer short</span>
</div>
<figcaption>All three strikes show identical open interest, yet the dealer is flat, long, and short respectively. Open interest counts the contracts; it cannot sign the position behind them. Any tool that infers dealer inventory from open interest alone is making an assumption at this exact step.</figcaption>
</figure>

<p>This is why sizing a "dealer gamma" number straight off raw open interest requires an assumption — usually that customers are net buyers of options and therefore dealers are net sellers. That assumption is often reasonable, and it is not always right. When it is wrong, a positioning read built on it points the wrong way at precisely the moments it matters most.</p>

<h2>Some venues publish data that does sign it</h2>

<p>The limitation above is a limitation of open interest, not a law of nature. Certain exchanges publish <strong>exchange-tagged participant data</strong> — breakdowns that separate volume or open interest by the type of account behind each trade (market maker, firm, broker-dealer, customer). Where that data is licensed and available, you no longer have to assume who is on which side; the tagging tells you. This is a real, meaningful distinction between a positioning read that guesses the dealer's side and one that observes it.</p>

<p>That data is not universally available. It is licensed, it covers specific products, and it is not something every analysis platform has. So most dealer-positioning tools in the market — including surfaces you will see elsewhere — are working from open interest plus assumptions, whether or not they say so.</p>

<h2>How we handle it here — stated plainly</h2>

<div class="callout warn">
<span class="co-h">What our numbers are</span>
<p>Our dealer-positioning surfaces — including the levels and gamma reads on the GEX page — are a <strong>model</strong>. They estimate dealer inventory from open interest combined with heuristics (such as assumptions about which side customers are on), and they are labelled as a model, not as observed positioning. They are a structured, transparent estimate to reason with, not a claim to know the dealer's book. When exchange-tagged participant data is not in hand, no tool — ours included — can sign that book with certainty, and we do not pretend otherwise.</p>
</div>

<p>Stating this is not a hedge; it is the correct reading of the mechanics. A model of dealer positioning can be useful precisely because it is explicit about its assumptions — you know where it could be wrong and can watch for those conditions. A number that hides the assumption behind a confident label is more dangerous than a modelled estimate that shows its work, because it invites you to trust a guess as if it were an observation.</p>

<h2>What open interest is still good for</h2>

<p>None of this makes open interest useless — far from it. It reliably shows where outstanding exposure sits, which strikes are crowded, and how positioning migrates as expirations approach. Combined with price and with the hedging logic in the <a href="/learn/options/dealer-hedging-mechanics.html">next lesson</a>, it supports a genuinely useful map of where mechanical pressure is likely to concentrate. The discipline is simply to remember what it does not contain: the sign of the dealer's position. Read it as a map of exposure, treat any dealer-side inference as a model, and you will be reading it honestly.</p>

<details>
<summary>Self-check: 3 questions</summary>
<ol>
<li><strong>A strike shows 5,000 contracts of open interest. Can you conclude from this number alone whether the dealer is long or short that strike? Why or why not?</strong><br>No. Every contract has a buyer and a seller, so open interest counts existence, not sides. The same 5,000 is consistent with the dealer being long, short, or flat depending on how customer positions net out. Signing the dealer's position requires information open interest does not carry.</li>
<li><strong>What kind of data can actually sign dealer inventory, and why isn't it used everywhere?</strong><br>Exchange-tagged participant data, which separates activity by account type (market maker, firm, broker-dealer, customer). Where it is licensed and available it lets you observe rather than assume the dealer's side. It is not used everywhere because it is licensed, covers specific products, and is not available to every platform.</li>
<li><strong>How should you interpret our GEX page's dealer-positioning numbers, in the site's own words?</strong><br>As a model: an estimate of dealer inventory built from open interest plus heuristics, labelled as such — not as observed positioning. It is a transparent estimate to reason with, useful because its assumptions are explicit, and it makes no claim to know the dealer's book with certainty when exchange-tagged data is not in hand.</li>
</ol>
</details>
