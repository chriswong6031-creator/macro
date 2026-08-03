---
slug: gamma-flip-levels
family: lesson
title: "The Gamma Flip and Walls: Reading Regime Boundaries"
description: "The gamma flip is where dealer hedging switches from stabilising to amplifying. Learn what crossing it means and how to read a levels map on our GEX page."
track: options
cluster: dealer-positioning
published: 2026-07-25
updated: 2026-07-25
related:
  lessons: [options/gamma-regimes]
  live:
    - {href: /options.html#ticker, label: "The levels map — flip, call wall, put wall"}
cta: {href: /options.html#ticker, label: "See the levels map: flip, call wall, and put wall"}
---
<div class="callout lead">
<span class="co-h">Learning objective</span>
Understand the gamma flip as the price level where modelled dealer hedging switches sign — from stabilising to amplifying — understand what call and put "walls" represent, and learn to read our GEX levels map as a display-tier map rather than a set of trade signals.
</div>

<p>The <a href="/learn/options/gamma-regimes.html">gamma regimes lesson</a> established two opposite states: long gamma, where dealer hedging dampens moves, and short gamma, where it amplifies them. Which state the market is in is not fixed — it depends on where price sits relative to the structure of dealer positioning. This lesson is about the specific price levels where that structure changes, because those levels are the most-watched output of any dealer-positioning model.</p>

<h2>The gamma flip: where the sign changes</h2>

<p>The <strong>gamma flip</strong> (also called the flip point or zero-gamma level) is the price at which modelled net dealer gamma crosses zero. Above it, the model has dealers net long gamma — hedging that leans against moves, a stabilising regime. Below it, the model has dealers net short gamma — hedging that leans with moves, an amplifying regime. The flip is the boundary between the two.</p>

<p>Crossing it is mechanically meaningful. As price falls through the flip, the same dealer hedging that was cushioning dips can invert into selling that extends them. Picture a hill whose slope reverses at one line: on the upper side, gravity rolls a ball back toward the crest; a step below that line, the identical ball accelerates away downhill. Nothing about the ball changed — only which side of the line it sits on. That is the flip: the market's behaviour around price can change character not because of news, but because the sign of the hedging flipped.</p>

<figure class="sig-fig">
<div class="sig-stage">
<svg viewBox="0 0 640 190" preserveAspectRatio="none" role="img" aria-label="A vertical price rail with three horizontal levels: a call wall near the top, a dashed gamma-flip line in the middle separating a stabilising zone above from an amplifying zone below, and a put wall near the bottom.">
  <!-- price rail -->
  <line class="sg-axis" x1="150" y1="16" x2="150" y2="176"/>
  <!-- stabilising zone tint (above flip) -->
  <rect class="fill-up" x="152" y="30" width="300" height="66" opacity="0.5"/>
  <!-- amplifying zone tint (below flip) -->
  <rect class="fill-down" x="152" y="96" width="300" height="66" opacity="0.5"/>
  <!-- call wall (upper) -->
  <line class="sg-up" x1="152" y1="40" x2="452" y2="40"/>
  <circle class="dot-up" cx="150" cy="40" r="5"/>
  <!-- gamma flip (middle, dashed pivot) -->
  <line class="sg-pivot-dash" x1="120" y1="96" x2="470" y2="96"/>
  <circle class="dot-pivot" cx="150" cy="96" r="6"/>
  <!-- put wall (lower) -->
  <line class="sg-down" x1="152" y1="152" x2="452" y2="152"/>
  <circle class="dot-down" cx="150" cy="152" r="5"/>
  <!-- current price marker -->
  <circle class="dot-mut" cx="150" cy="72" r="5"/>
</svg>
<span class="sig-lbl axis" style="left:12%; top:8%;">price</span>
<span class="sig-lbl up" style="left:47%; top:21%;">call wall — resistance</span>
<span class="sig-lbl up" style="left:47%; top:38%;">stabilising zone (long gamma)</span>
<span class="sig-lbl pivot big" style="left:63%; top:45%;">gamma flip</span>
<span class="sig-lbl down" style="left:47%; top:63%;">amplifying zone (short gamma)</span>
<span class="sig-lbl down" style="left:47%; top:80%;">put wall — support</span>
<span class="sig-lbl" style="left:9%; top:38%;">now</span>
</div>
<figcaption>A dealer-positioning levels map: the dashed flip line splits a stabilising (long-gamma) zone above from an amplifying (short-gamma) zone below. The call wall is the strike with the largest modelled positive gamma above price (often acts as resistance); the put wall is its counterpart below (often acts as support). All three are modelled levels, not guaranteed price barriers.</figcaption>
</figure>

<h2>Walls: where gamma concentrates</h2>

<p>Around the flip, positioning is not evenly spread — it clusters at specific strikes with large open interest. The two most-watched clusters get names. The <strong>call wall</strong> is the strike with the largest concentration of modelled positive gamma above the current price; because dealer hedging there leans against upward moves, it often behaves like resistance. The <strong>put wall</strong> is the equivalent concentration below price and often behaves like support. Think of them as the strikes where the stabilising force is strongest — price tends to slow as it approaches them, because that is where the most hedging pushes back.</p>

<p>"Often behaves like" is doing deliberate work in those sentences. Walls are places where mechanical hedging concentrates, which makes them plausible inflection points — not walls in any literal sense. Price passes through them regularly. They are a map of where pushback is likely to be strongest, not a fence.</p>

<h2>How to read the GEX levels map</h2>

<p>Our GEX page plots exactly these levels: the flip, the call wall, and the put wall, against current price. Read it as a structural context map:</p>

<ul>
<li><strong>Price relative to the flip</strong> tells you which regime the model currently places you in — expect a fade-friendly, range-bound tape above it; expect amplification and trend/squeeze risk below it.</li>
<li><strong>Distance to the nearest wall</strong> tells you where the strongest modelled hedging pushback sits — a nearby call wall overhead is a plausible drag on a rally; a nearby put wall below is a plausible cushion under a dip.</li>
<li><strong>How the levels move day to day</strong> tells you how positioning is migrating, especially into expirations, when the flip and walls can shift as short-dated open interest rolls off.</li>
</ul>

<div class="callout warn">
<span class="co-h">The essential caveat</span>
<p>These levels are a display-tier map, not trade signals. Every one of them is derived from a model of dealer positioning built on open interest plus assumptions — not from an exchange-tagged dealer book (see the <a href="/learn/options/open-interest-limits.html">open-interest lesson</a>). They describe where mechanical pressure is likely to concentrate; they do not tell you to buy at the put wall or sell at the call wall. Use them to understand the terrain and set expectations, not as entry or exit triggers.</p>
</div>

<h2>Putting the track together</h2>

<p>You now have the whole chain. Options grew large and short-dated enough to move markets (<a href="/learn/options/zero-dte-regime.html">the 0DTE regime</a>); market makers absorb the other side and must hedge to stay neutral (<a href="/learn/options/market-makers-middleman.html">the middleman</a>); open interest cannot sign their position, so a dealer read is a model (<a href="/learn/options/open-interest-limits.html">open-interest limits</a>); the hedge is concrete share flow driven by drifting delta (<a href="/learn/options/dealer-hedging-mechanics.html">hedging mechanics</a>); the sign of dealer gamma splits the market into a dampening and an amplifying regime (<a href="/learn/options/gamma-regimes.html">gamma regimes</a>); slower second-order forces exist but are mechanics, not signals (<a href="/learn/options/charm-and-time-drift.html">charm and vanna</a>); and the flip and walls are the price levels where the regime structure lives. See it all on the map:</p>

<details>
<summary>Self-check: 3 questions</summary>
<ol>
<li><strong>What defines the gamma flip level, and what changes when price crosses it?</strong><br>It is the price where modelled net dealer gamma crosses zero. Above it, dealers are modelled net long gamma and hedge against moves (a stabilising regime); below it, they are modelled net short gamma and hedge with moves (an amplifying regime). Crossing it flips the sign of the hedging, so the market's character around price can change without any news.</li>
<li><strong>What is the call wall, and why does it often act like resistance? Why "often" rather than "always"?</strong><br>The call wall is the strike with the largest concentration of modelled positive gamma above the current price. Dealer hedging there leans against upward moves, so rallies tend to slow near it — resistance-like behaviour. It is "often" not "always" because it marks where hedging pushback concentrates, not a literal barrier; price passes through walls regularly.</li>
<li><strong>How should the GEX levels map be used, and what is it explicitly not?</strong><br>As a display-tier structural context map: price versus the flip sets the expected regime, distance to a wall shows where hedging pushback concentrates, and day-to-day shifts show positioning migrating. It is explicitly not a set of trade signals — the levels come from a model built on open interest plus assumptions and describe terrain, not entry or exit points.</li>
</ol>
</details>
