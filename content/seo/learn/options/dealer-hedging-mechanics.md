---
slug: dealer-hedging-mechanics
family: lesson
title: "Dealer Hedging: How Delta Rebalancing Becomes Order Flow"
description: "Selling 100 calls at 0.4 delta means buying 4,000 shares to stay neutral. Learn how continuous delta rehedging turns into real buy and sell pressure."
track: options
cluster: dealer-positioning
published: 2026-07-25
updated: 2026-07-25
related:
  lessons: [options/gamma-regimes]
  live:
    - {href: /options.html#ticker, label: "Options workspace — per-name dealer positioning"}
cta: {href: /learn/options/gamma-regimes.html, label: "Next lesson: long gamma vs short gamma regimes"}
---
<div class="callout lead">
<span class="co-h">Learning objective</span>
Work through the exact arithmetic that turns an options position into stock orders: how delta sets the initial hedge, why delta drifts as the underlying moves, and why closing that drift means the dealer must trade the underlying again — and again.
</div>

<p>The previous lessons established that a market maker who sells options must hedge in the underlying to stay neutral, and that open interest cannot tell you which way. This lesson makes the hedge concrete. Once you can compute it, "dealer flow" stops being an abstraction and becomes a number of shares.</p>

<h2>Delta: the hedge ratio</h2>

<p><strong>Delta</strong> is how much an option's price moves for a one-point move in the underlying, expressed as a fraction between 0 and 1 (for calls) or 0 and −1 (for puts). A call with a delta of 0.40 gains about $0.40 for each $1 the stock rises. Delta doubles as the hedge ratio: it is the number of shares per option that offsets the option's directional exposure. Each listed option controls 100 shares, so one option contract at 0.40 delta carries the directional punch of 40 shares.</p>

<div class="formula">
Shares to hedge = (contracts) × (100 shares per contract) × (delta)
<br><br>
Example: 100 contracts × 100 × 0.40 = <strong>4,000 shares</strong>
</div>

<h2>Worked example — the initial hedge</h2>

<div class="worked">
<span class="co-h">Worked example — selling 100 calls</span>
<p>A dealer sells <strong>100 call contracts</strong> at a delta of <strong>0.40</strong>. Selling a call is a negative-delta position: the dealer loses as the stock rises. To offset it, they buy the equivalent long stock exposure.</p>
<p>Hedge = 100 × 100 × 0.40 = <strong>buy 4,000 shares</strong></p>
<p>After this trade the dealer is delta-neutral: a small move in the stock does not move the value of the combined (short-calls + long-shares) book. The 4,000 shares just hit the tape as a real buy order — mechanical, driven only by the arithmetic above.</p>
</div>

<h2>Why the hedge does not stay put</h2>

<p>Here is the crucial complication. Delta is not constant — it changes as the underlying moves. As the stock rises toward and through the strike, the call's delta climbs (from 0.40 toward 0.60, 0.80, and beyond). The dealer sold those calls, so their exposure grows with it, and the 4,000 shares that neutralised a 0.40 delta no longer neutralise a 0.60 delta. They are under-hedged and must buy more.</p>

<figure class="sig-fig">
<div class="sig-stage">
<svg viewBox="0 0 640 180" preserveAspectRatio="none" role="img" aria-label="A rising price line with a staircase beneath it: as price climbs, the dealer's required share hedge steps up, each step marking an additional buy order.">
  <line class="sg-axis" x1="52" y1="150" x2="620" y2="150"/>
  <line class="sg-axis" x1="52" y1="20" x2="52" y2="150"/>
  <!-- price rising left to right -->
  <path class="sg-line" d="M56 132 L180 110 L320 78 L470 44 L604 26"/>
  <!-- hedge staircase (shares held), stepping UP with price -->
  <path class="sg-up" d="M56 140 L180 140 L180 120 L320 120 L320 92 L470 92 L470 58 L604 58"/>
  <!-- buy-order dots at each step -->
  <circle class="dot-up" cx="180" cy="120" r="5"/>
  <circle class="dot-up" cx="320" cy="92" r="5"/>
  <circle class="dot-up" cx="470" cy="58" r="5"/>
</svg>
<span class="sig-lbl axis" style="left:8%; top:12%;">shares<br>hedged</span>
<span class="sig-lbl axis" style="left:92%; top:92%;">price →</span>
<span class="sig-lbl" style="left:11%; top:80%;">Δ 0.40</span>
<span class="sig-lbl up" style="left:29%; top:60%;">buy more</span>
<span class="sig-lbl up" style="left:51%; top:44%;">buy more</span>
<span class="sig-lbl up" style="left:74%; top:24%;">buy more</span>
</div>
<figcaption>As price rises (upper line), the delta of the calls the dealer is short climbs, so the share hedge (lower staircase) must step up with it. Each step is another buy order the dealer is forced to place into a rising market. Falling price runs the staircase in reverse — selling into weakness.</figcaption>
</figure>

<div class="worked">
<span class="co-h">Worked example — the rehedge</span>
<p>The stock rallies and the calls' delta rises from 0.40 to <strong>0.55</strong>. Required hedge is now 100 × 100 × 0.55 = <strong>5,500 shares</strong>. The dealer already holds 4,000, so they must buy <strong>1,500 more shares</strong> — into the rally that caused the delta to rise in the first place.</p>
<p>If instead the stock had fallen and delta dropped to 0.30, the required hedge would be 3,000 shares; holding 4,000, the dealer would <strong>sell 1,000 shares</strong> — into the decline.</p>
</div>

<h2>The pattern that matters</h2>

<p>Look at the direction of those trades. In this example — where the dealer is <em>short</em> the calls — a rising stock forces buying and a falling stock forces selling. The hedging pushes in the same direction as the move. That is not a coincidence; it is the mechanical fingerprint of one of the two gamma regimes, and it is what the next lesson is entirely about. The rate at which delta changes as price moves has a name — <strong>gamma</strong> — and whether the dealer is on the amplifying side or the dampening side of it defines how the whole market behaves around that positioning.</p>

<div class="callout key">
<span class="co-h">The takeaway</span>
<p>Dealer hedging is not a one-time trade; it is a continuous stream of buy and sell orders generated automatically as delta drifts with price. The size of each rehedge is just arithmetic. The <em>direction</em> of it — with the move or against it — is set by which side of the options the dealer is on, and that is the gamma regime.</p>
</div>

<p>Continue to <a href="/learn/options/gamma-regimes.html">long gamma vs short gamma</a> to see how this rehedging stream either calms the market or accelerates it.</p>

<details>
<summary>Self-check: 3 questions</summary>
<ol>
<li><strong>A dealer sells 250 call contracts at 0.30 delta. How many shares do they buy to hedge, and why?</strong><br>250 × 100 × 0.30 = 7,500 shares. Selling calls is a negative-delta position (they lose as the stock rises), so they buy 7,500 shares of long exposure to offset it and return to neutral. The number is pure arithmetic: contracts × 100 × delta.</li>
<li><strong>The stock rallies and the calls' delta rises from 0.30 to 0.50. What does the dealer from question 1 now do, and how much?</strong><br>Required hedge rises to 250 × 100 × 0.50 = 12,500 shares. They already hold 7,500, so they buy 5,000 more — into the rally that lifted the delta. Rising price raises the delta of the short calls, forcing additional buying to stay neutral.</li>
<li><strong>In this short-calls example, does the hedging push with the move or against it, and why does that matter?</strong><br>With the move: rising price forces buying, falling price forces selling. It matters because same-direction hedging amplifies moves rather than dampening them — the mechanical signature of the short-gamma regime covered in the next lesson.</li>
</ol>
</details>
