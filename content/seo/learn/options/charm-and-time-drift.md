---
slug: charm-and-time-drift
family: lesson
title: "Charm and Vanna: Second-Order Options Mechanics"
description: "Charm and vanna describe how an option's delta drifts with time and volatility. Learn the mechanics as context only, with an honest note on their limits."
track: options
cluster: dealer-positioning
published: 2026-07-25
updated: 2026-07-25
related:
  lessons: [options/gamma-flip-levels]
  live:
    - {href: /options.html#ticker, label: "Options workspace — per-name dealer positioning"}
cta: {href: /learn/options/gamma-flip-levels.html, label: "Next lesson: the gamma flip and walls as regime boundaries"}
---
<div class="callout lead">
<span class="co-h">Learning objective</span>
Understand charm and vanna — the second-order forces that move an option's delta even when price sits still, one driven by the passage of time and the other by changes in volatility — as educational context, and understand clearly why we do not build trading signals on them.
</div>

<p>So far, delta has changed for one reason: the underlying price moved (that sensitivity is gamma). But delta can drift even when price does not move at all. Two forces cause this. <strong>Charm</strong> is the drift in delta caused by the passage of <em>time</em>. <strong>Vanna</strong> is the drift in delta caused by a change in <em>volatility</em>. Because dealers hedge delta, anything that moves delta — including these two — can in principle nudge their hedging. That is why they are worth understanding mechanically.</p>

<h2>Charm — delta drift from time</h2>

<p>As an option approaches expiration, its delta migrates toward one of two destinations. An option that is in-the-money drifts toward a delta of 1 (for a call): it is increasingly certain to expire with intrinsic value, so it increasingly behaves like the stock itself. An option that is out-of-the-money drifts toward a delta of 0: it is increasingly certain to expire worthless, so it increasingly behaves like nothing. Charm is the speed of that migration, and it accelerates as expiration nears — which is why it is discussed most around large expiration events.</p>

<figure class="sig-fig">
<div class="sig-stage">
<svg viewBox="0 0 640 180" preserveAspectRatio="none" role="img" aria-label="Two delta curves drifting over time as expiration approaches: an in-the-money call rising toward a delta of one, an out-of-the-money call sinking toward zero, with no change in price.">
  <line class="sg-axis" x1="52" y1="150" x2="620" y2="150"/>
  <line class="sg-axis" x1="52" y1="20" x2="52" y2="150"/>
  <line class="sg-grid" x1="52" y1="85" x2="620" y2="85"/>
  <!-- ITM call drifts up toward delta 1 -->
  <path class="sg-up" d="M56 92 C 200 88, 360 66, 500 34 S 600 22, 612 20"/>
  <circle class="dot-up" cx="612" cy="20" r="5"/>
  <!-- OTM call drifts down toward delta 0 -->
  <path class="sg-down" d="M56 98 C 200 104, 360 124, 500 142 S 600 148, 612 148"/>
  <circle class="dot-down" cx="612" cy="148" r="5"/>
</svg>
<span class="sig-lbl axis" style="left:8.5%; top:12%;">delta</span>
<span class="sig-lbl axis" style="left:9%; top:15%;">1.0</span>
<span class="sig-lbl axis" style="left:9%; top:82%;">0.0</span>
<span class="sig-lbl axis" style="left:90%; top:92%;">time to expiry →</span>
<span class="sig-lbl up" style="left:80%; top:14%;">in-the-money → 1</span>
<span class="sig-lbl down" style="left:80%; top:86%;">out-of-money → 0</span>
</div>
<figcaption>Charm at work: with price unchanged, the passage of time pulls an in-the-money call's delta up toward 1 and an out-of-the-money call's delta down toward 0. The drift accelerates as expiration nears. Because dealers hedge delta, this drift is, mechanically, a slow source of rehedging pressure.</figcaption>
</figure>

<h2>Vanna — delta drift from volatility</h2>

<p>Vanna is the same idea with volatility as the driver instead of time. When implied volatility rises or falls, the deltas of options shift even if price is flat, because a higher-volatility world makes more strikes "reachable" and redistributes how much each option behaves like the stock. A common informal description is that vanna links moves in volatility to shifts in dealer hedging — for example, a falling-volatility environment nudging deltas in a way that can add a gentle directional lean to hedging. As with charm, the mechanical chain is real: volatility changes delta, and dealers hedge delta.</p>

<h2>Why we teach these but do not trade them</h2>

<div class="callout warn">
<span class="co-h">Honesty note — charm and vanna as signals</span>
<p>We surface charm and vanna as educational context only — tested as standalone signals they failed our gauntlet and we do not trade or rank on them.</p>
<p>Concretely: when we studied signed charm and charm-intensity as their own predictive inputs, the apparent effect was confounded by volatility and position size, and it did not survive as an independent edge. So while the mechanics on this page are real, any story that treats a charm or vanna reading as a reason to buy or sell is a story we do not stand behind. These forces may exist in the plumbing; that is different from being a signal you can act on.</p>
</div>

<p>This distinction is the whole point of the lesson. It is entirely possible for a mechanism to be genuine and for a <em>signal</em> built on it to be worthless — because the mechanism is small next to other forces, because it is confounded by things you cannot cleanly separate, or because by the time it is measurable it is already priced. Charm and vanna are our standing example of exactly that gap. Understanding them makes you a better reader of expiration-week behaviour; it does not hand you a trade.</p>

<h2>How this fits the honest read of the desk</h2>

<p>Notice the through-line with the <a href="/learn/options/open-interest-limits.html">open-interest lesson</a>. There, the honest move was to label dealer positioning as a model rather than an observation. Here, the honest move is to label charm and vanna as mechanics rather than signals. Both are the same discipline: keep what is real, refuse to dress up an assumption or a confound as an edge. The <a href="/learn/options/gamma-flip-levels.html">final lesson</a> applies that same discipline to flip levels and walls — real, readable structure that is a map, not a trade signal.</p>

<details>
<summary>Self-check: 3 questions</summary>
<ol>
<li><strong>What is the difference between charm and vanna?</strong><br>Both describe delta drifting when price is unchanged, but the driver differs. Charm is delta drift caused by the passage of time; vanna is delta drift caused by a change in volatility. Both matter mechanically because dealers hedge delta, so anything that moves delta can nudge their hedging.</li>
<li><strong>As expiration approaches with price unchanged, which way does the delta of an in-the-money call drift, and why?</strong><br>Toward 1. As expiry nears, an in-the-money call is increasingly certain to expire with intrinsic value, so it increasingly behaves like the underlying stock itself — a delta approaching 1. An out-of-the-money call drifts the opposite way, toward 0, as it becomes increasingly certain to expire worthless.</li>
<li><strong>Does our platform treat charm and vanna as trading signals? State the position exactly.</strong><br>No. We surface them as educational context only; tested as standalone signals they failed our gauntlet, and we do not trade or rank on them. The mechanics are real, but the studied edge was confounded by volatility and size and did not survive, so we make no signal claim on them.</li>
</ol>
</details>
