---
slug: market-makers-middleman
family: lesson
title: "Market Makers: Who Takes the Other Side of Your Trade"
description: "A market maker takes the other side and stays delta-neutral. Learn why that neutrality forces mechanical buying and selling in the underlying stock."
track: options
cluster: dealer-positioning
published: 2026-07-25
updated: 2026-07-25
related:
  lessons: [options/open-interest-limits]
  live:
    - {href: /options.html#ticker, label: "Options workspace — per-name dealer positioning"}
cta: {href: /learn/options/open-interest-limits.html, label: "Next lesson: what open interest can and cannot tell you"}
---
<div class="callout lead">
<span class="co-h">Learning objective</span>
Understand who stands on the other side of an options trade, why they try to stay market-neutral rather than take a directional bet, and why that neutrality is exactly what forces them to trade the underlying stock.
</div>

<p>When you buy a call option, someone sells it to you. That someone is usually not another retail trader with the opposite view — it is a <strong>market maker</strong>: a firm that continuously quotes both a bid and an ask on thousands of contracts and profits from the spread between them, plus fees, by trading in volume. Their business is to be the counterparty, not to have an opinion about direction.</p>

<h2>Neutrality is the business model</h2>

<p>A market maker who accumulated directional views on every contract they traded would be running an enormous, unmanaged bet on the market. That is not their business. Their edge is the spread — the small, repeatable difference between what they buy and sell at — captured across a huge number of trades. To keep that edge clean, they try to hold as little directional exposure as possible. The industry term is <strong>delta-neutral</strong>: positioned so that a small move up or down in the underlying does not, by itself, make or lose them money.</p>

<figure class="sig-fig">
<div class="sig-stage">
<svg viewBox="0 0 640 180" preserveAspectRatio="none" role="img" aria-label="A flow diagram: a trader buys a call from a market maker, who then buys shares of the underlying to return to a neutral position on the zero line.">
  <!-- the neutral datum -->
  <line class="sg-zero" x1="40" y1="150" x2="620" y2="150"/>
  <!-- trader node -->
  <circle class="dot-mut" cx="90" cy="70" r="5"/>
  <rect class="sg-line" x="60" y="52" width="60" height="36" rx="6"/>
  <!-- arrow: trader buys call -> MM -->
  <path class="sg-up" d="M124 70 L286 70"/>
  <path class="sg-up" d="M278 64 L288 70 L278 76"/>
  <!-- MM node (the middleman) -->
  <rect class="sg-pivot" x="292" y="46" width="96" height="48" rx="8"/>
  <!-- MM now holds risk ABOVE neutral (short a call = negative delta) -->
  <path class="sg-down" d="M340 100 L340 138"/>
  <path class="sg-down" d="M334 130 L340 140 L346 130"/>
  <!-- hedge arrow: MM buys shares to come back to neutral -->
  <path class="sg-up" d="M392 70 L556 70"/>
  <path class="sg-up" d="M548 64 L558 70 L548 76"/>
  <!-- underlying node -->
  <rect class="sg-line" x="560" y="52" width="56" height="36" rx="6"/>
  <circle class="dot-up" cx="588" cy="70" r="5"/>
</svg>
<span class="sig-lbl" style="left:14%; top:26%;">you</span>
<span class="sig-lbl up" style="left:32%; top:31%;">buy a call →</span>
<span class="sig-lbl pivot big" style="left:53%; top:39%;">market<br>maker</span>
<span class="sig-lbl down" style="left:53%; top:70%;">now off-neutral</span>
<span class="sig-lbl up" style="left:74%; top:31%;">buys shares →</span>
<span class="sig-lbl" style="left:91.5%; top:26%;">stock</span>
<span class="sig-lbl axis" style="left:8.5%; top:88%;">neutral line</span>
</div>
<figcaption>You buy a call; the market maker who sold it is now off-neutral (they are short the call, so they gain delta as the stock falls and lose it as the stock rises). To return to the neutral line, they buy shares of the underlying. The hedge is not optional — it is how they stay in business.</figcaption>
</figure>

<h2>Why neutrality forces trading in the underlying</h2>

<p>Here is the pivotal idea of this whole track. When a market maker sells you a call, they inherit the opposite exposure to the one you now hold. You want the stock to rise; they are now exposed to it rising against them. Right after the trade they are no longer neutral. To get back to neutral, they buy an amount of the underlying stock that offsets the directional exposure the option just handed them.</p>

<p>That offsetting trade is a real order in the real stock. It is the bridge between the options market and the cash market — and it is entirely mechanical. The market maker is not expressing a view that the stock will rise; they are buying because the arithmetic of neutrality tells them to. Multiply this across the volume of a modern index-options market, and the aggregate of all that mechanical hedging becomes a force on the tape.</p>

<div class="callout key">
<span class="co-h">The consequence to remember</span>
<p>A market maker's neutrality is not passivity. Staying neutral is an active, continuous process of buying and selling the underlying to offset the exposure that customer trades keep handing them. Their indifference to direction is precisely what generates direction-agnostic order flow in the stock.</p>
</div>

<h2>"The other side" is a position, and it changes</h2>

<p>Because market makers absorb whatever customers do, their aggregate position reflects — in mirror image — what the crowd has been trading. If customers have been heavy buyers of calls, dealers are net short those calls and must hedge accordingly. If customers loaded up on puts, the dealer inventory tilts the other way. This is why people talk about "dealer positioning" as a readable state of the market. But — and this is the subject of the next lesson — you cannot read that position directly off the most commonly quoted options statistic. <a href="/learn/options/open-interest-limits.html">Open interest</a> counts contracts; it does not, by itself, tell you which side the dealer is on.</p>

<details>
<summary>Self-check: 3 questions</summary>
<ol>
<li><strong>Why does a market maker try to stay delta-neutral instead of taking a directional view on the options they trade?</strong><br>Their edge is the bid-ask spread captured across enormous volume, not directional bets. Accumulating a view on every contract would turn their book into a huge, unmanaged market wager. Staying neutral protects the spread-capture business from being swamped by directional profit and loss.</li>
<li><strong>You buy a call. In one sentence, why does the market maker then buy shares of the underlying?</strong><br>Selling you the call left them with exposure opposite to yours (they are hurt if the stock rises), so they buy shares to offset that exposure and return to a neutral position. The share purchase is mechanical, driven by the arithmetic of neutrality, not by any opinion that the stock will go up.</li>
<li><strong>Why is dealer positioning described as a "mirror" of what customers have been doing?</strong><br>Market makers absorb the other side of customer flow, so their aggregate inventory is the opposite of the crowd's. Heavy customer call-buying leaves dealers short those calls; heavy put-buying tilts them the other way. Their book reflects, in reverse, what the market has been trading.</li>
</ol>
</details>
