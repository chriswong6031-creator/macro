---
slug: gamma-regimes
family: lesson
title: "Long Gamma vs Short Gamma: Two Market Regimes"
description: "In long gamma dealers fade moves and volatility compresses; in short gamma they chase and moves amplify. Learn the feedback loop behind each regime."
track: options
cluster: dealer-positioning
published: 2026-07-25
updated: 2026-07-25
related:
  lessons: [options/charm-and-time-drift]
  live:
    - {href: /options.html#ticker, label: "Options workspace — regime read & positioning"}
cta: {href: /learn/options/charm-and-time-drift.html, label: "Next lesson: charm and vanna, the second-order mechanics"}
---
<div class="callout lead">
<span class="co-h">Learning objective</span>
Understand the two opposite regimes that dealer hedging can create — long gamma, which dampens moves, and short gamma, which amplifies them — as feedback loops, and connect them to the regime chip on our GEX page.
</div>

<p>The <a href="/learn/options/dealer-hedging-mechanics.html">previous lesson</a> showed that as price moves, an option's delta drifts, forcing the dealer to rehedge — and that the <em>direction</em> of that rehedging depends on which side of the options the dealer is on. <strong>Gamma</strong> is the name for how fast delta drifts. This lesson shows that the sign of the dealer's gamma splits the market into two regimes that behave in opposite ways.</p>

<h2>Gamma in one sentence</h2>

<p>Gamma is the rate of change of delta with respect to the underlying price. High gamma means delta moves a lot for a small price change (short-dated, near-the-money options — recall the 0DTE lesson); low gamma means delta barely budges. What matters for the market is not just the size of gamma but its <strong>sign</strong> from the dealer's point of view — whether their hedging leans against moves or with them.</p>

<h2>The two loops</h2>

<figure class="sig-fig">
<div class="sig-stage">
<svg viewBox="0 0 640 190" preserveAspectRatio="none" role="img" aria-label="Two panels. Left: a long-gamma damped wave settling toward the centre line as opposing hedge arrows pull it back. Right: a short-gamma diverging wave pushed away from the centre line by same-direction hedge arrows.">
  <!-- split divider -->
  <line class="sg-split" x1="320" y1="14" x2="320" y2="176"/>
  <!-- LEFT: long gamma — centre line + damped oscillation converging -->
  <line class="sg-zero" x1="24" y1="95" x2="300" y2="95"/>
  <path class="sg-up" d="M28 95 C 70 40, 100 150, 140 78 S 200 118, 236 90 S 280 100, 296 95"/>
  <!-- opposing hedge arrows (pull back toward centre) -->
  <path class="sg-up" d="M96 52 L96 82"/><path class="sg-up" d="M90 74 L96 84 L102 74"/>
  <path class="sg-up" d="M170 130 L170 104"/><path class="sg-up" d="M164 112 L170 102 L176 112"/>
  <!-- RIGHT: short gamma — centre line + diverging oscillation -->
  <line class="sg-zero" x1="340" y1="95" x2="616" y2="95"/>
  <path class="sg-down" d="M344 95 C 380 78, 404 112, 444 74 S 512 128, 552 52 S 604 150, 612 30"/>
  <!-- same-direction hedge arrows (push away from centre) -->
  <path class="sg-down" d="M470 70 L470 44"/><path class="sg-down" d="M464 52 L470 42 L476 52"/>
  <path class="sg-down" d="M556 120 L556 148"/><path class="sg-down" d="M550 140 L556 150 L562 140"/>
</svg>
<span class="sig-lbl up big" style="left:25%; top:9%;">long gamma</span>
<span class="sig-lbl up" style="left:25%; top:92%;">dealers fade → calms</span>
<span class="sig-lbl down big" style="left:75%; top:9%;">short gamma</span>
<span class="sig-lbl down" style="left:75%; top:92%;">dealers chase → amplifies</span>
</div>
<figcaption>Left (long gamma): every move is met by opposing hedging that pulls price back toward the centre — the oscillation shrinks, volatility compresses. Right (short gamma): every move is met by same-direction hedging that pushes price further from the centre — the oscillation grows, volatility expands.</figcaption>
</figure>

<h2>Long gamma — the shock absorber</h2>

<p>When dealers are <strong>long gamma</strong>, their hedging leans against price moves: they sell as the market rises and buy as it falls. That is stabilising. A rally is met with dealer selling that caps it; a dip is met with dealer buying that cushions it. The feedback loop is negative — moves feed forces that oppose them — so realised volatility tends to compress. Days spent deep in long-gamma positioning often feel slow, mean-reverting, and hard to trend. Think of a heavy shock absorber: push it and it pushes back.</p>

<h2>Short gamma — the accelerator</h2>

<p>When dealers are <strong>short gamma</strong>, the sign flips. Their hedging leans <em>with</em> price moves — the exact pattern from the worked example last lesson, where a dealer short calls had to buy into a rally and sell into a decline. Now the feedback loop is positive: a move generates hedging that extends it, which forces more hedging, which extends it further. Realised volatility expands, and moves can become abrupt and self-reinforcing. This is the mechanical engine behind many sharp, seemingly-newsless slides and squeezes. Think of a hand shoving a swing at the top of each arc: each push makes the next one bigger.</p>

<div class="callout key">
<span class="co-h">The one-line contrast</span>
<p><strong>Long gamma</strong> = negative feedback = moves get absorbed = volatility compresses. <strong>Short gamma</strong> = positive feedback = moves get amplified = volatility expands. Same hedging machinery, opposite sign, opposite market character.</p>
</div>

<h2>Reading it on the GEX page</h2>

<p>Our GEX page carries a regime read that tells you which side of this line the modelled dealer positioning currently sits on — a "long gamma / short gamma" style chip. Used correctly, it is context, not a trade trigger: it tells you what <em>kind</em> of tape to expect (a fade-friendly, range-bound one versus a trend-and-squeeze-prone one), which is exactly the "what to expect" the regime distinction is good for.</p>

<div class="callout warn">
<span class="co-h">Read it honestly</span>
<p>Remember the <a href="/learn/options/open-interest-limits.html">open-interest lesson</a>: the sign of dealer gamma is inferred from a model built on open interest plus assumptions, not read directly off an exchange-tagged book. The regime chip is a display-tier map of the modelled state, not a signal that tells you to buy or sell. Treat a "short gamma" read as "expect the tape to amplify moves," not as an instruction.</p>
</div>

<p>The next lesson looks at the slower, second-order forces — <a href="/learn/options/charm-and-time-drift.html">charm and vanna</a> — that nudge delta even when price sits still, and it carries an important honesty note about their limits.</p>

<details>
<summary>Self-check: 3 questions</summary>
<ol>
<li><strong>In the long-gamma regime, which way do dealers hedge as the market rises, and what does that do to volatility?</strong><br>They sell as the market rises and buy as it falls — hedging against the move. That negative feedback absorbs moves and tends to compress realised volatility, producing a slower, more mean-reverting, range-bound tape.</li>
<li><strong>Why does short gamma tend to produce sharp, self-reinforcing moves?</strong><br>Because dealers hedge with the move: buying into rallies and selling into declines. That positive feedback extends the move, which forces more same-direction hedging, which extends it further. Volatility expands and moves can become abrupt and squeeze-like, even without fresh news.</li>
<li><strong>How should the GEX regime chip be used, and what is it not?</strong><br>As context for what kind of tape to expect — fade-friendly and range-bound under long gamma, trend-and-squeeze-prone under short gamma. It is not a buy or sell signal: it reflects a modelled state inferred from open interest plus assumptions, presented as a display-tier map, not an instruction to trade.</li>
</ol>
</details>
