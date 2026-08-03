---
slug: zero-dte-regime
family: lesson
title: "The 0DTE Era: How Options Started Driving Markets"
description: "Same-day options grew from a niche to a huge share of index volume. Learn why the options chain now drives the tape instead of just tracking it."
track: options
cluster: dealer-positioning
published: 2026-07-25
updated: 2026-07-25
related:
  lessons: [options/market-makers-middleman]
  live:
    - {href: /options.html#ticker, label: "Options workspace — per-name dealer positioning"}
cta: {href: /learn/options/market-makers-middleman.html, label: "Next lesson: the market maker on the other side of every trade"}
---
<div class="callout lead">
<span class="co-h">Learning objective</span>
Understand why the options market has grown large enough to push the underlying index around, and why "same-day" (0DTE) contracts changed the chain from a passive mirror of the tape into an active driver of it.
</div>

<p>For most of options history, the standard mental model was that options track stocks. A stock moves; its options reprice to follow. The tail did not wag the dog. That model is now incomplete for the most heavily traded index products, and understanding why is the foundation for everything else in this track.</p>

<p>Two things changed. First, the sheer size of options activity relative to the underlying grew until the hedging it generated was no longer a rounding error against the cash tape. Second, the maturity of the average traded contract collapsed toward zero. Contracts that expire the same day they are traded — zero days to expiration, or <strong>0DTE</strong> — went from a niche curiosity to a large share of all index-option volume over the mid-2020s.</p>

<figure class="sig-fig">
<div class="sig-stage">
<svg viewBox="0 0 640 180" preserveAspectRatio="none" role="img" aria-label="Three stylised yearly bars showing the same-day share of index-option volume growing from a thin slice to about half.">
  <line class="sg-axis" x1="52" y1="150" x2="620" y2="150"/>
  <line class="sg-grid" x1="52" y1="95" x2="620" y2="95"/>
  <line class="sg-grid" x1="52" y1="40" x2="620" y2="40"/>
  <!-- year A: mostly other-expiry (muted), thin same-day slice (up) -->
  <rect class="fill-mut" x="110" y="66" width="80" height="84"/>
  <rect class="fill-up"  x="110" y="132" width="80" height="18"/>
  <!-- year B: same-day slice grows -->
  <rect class="fill-mut" x="290" y="52" width="80" height="98"/>
  <rect class="fill-up"  x="290" y="106" width="80" height="44"/>
  <!-- year C: same-day is now ~half -->
  <rect class="fill-mut" x="470" y="40" width="80" height="110"/>
  <rect class="fill-up"  x="470" y="95" width="80" height="55"/>
</svg>
<span class="sig-lbl axis" style="left:8%; top:22%;">share of<br>volume</span>
<span class="sig-lbl" style="left:23.4%; top:88%;">earlier</span>
<span class="sig-lbl" style="left:51.5%; top:88%;">middle</span>
<span class="sig-lbl" style="left:79.6%; top:88%;">recent</span>
<span class="sig-lbl up" style="left:23.4%; top:79%;">same-day</span>
<span class="sig-lbl up" style="left:51.5%; top:71%;">same-day</span>
<span class="sig-lbl up big" style="left:79.6%; top:58%;">~half</span>
<span class="sig-lbl" style="left:23.4%; top:44%;">other<br>expiries</span>
</div>
<figcaption>Schematic, not a precise data series: the same-day (0DTE) slice of index-option volume rose from a thin band to roughly half over the mid-2020s. The exact figure varies by product and by day.</figcaption>
</figure>

<h2>Why size alone is not the whole story</h2>

<p>A large options market does not automatically move the underlying. What matters is the <em>hedging</em> that trading generates. When contracts change hands, the firms that stand ready to trade them — market makers — accumulate risk they must offset by buying or selling the underlying. The next lesson covers that mechanism in full. For now, the key point is that hedging volume scales with options activity, so as options activity grew, so did the mechanical order flow it sends into the cash market.</p>

<p>This is why a market can gap on no obvious news. If a large block of options trades and the firms on the other side must rebalance immediately, the resulting buying or selling hits the tape as real orders — indistinguishable, to anyone watching price alone, from someone reacting to a headline.</p>

<h2>What 0DTE changes specifically</h2>

<p>Short-dated options behave differently from longer-dated ones in a way that matters for the whole market. The closer an option is to expiration and the closer its strike is to the current price, the more violently its sensitivity to the underlying changes as price moves. A contract expiring in weeks responds smoothly; a contract expiring in hours can flip from barely-sensitive to fully-sensitive within a small price range.</p>

<div class="callout key">
<span class="co-h">The core shift</span>
<p>When most of the volume sits in contracts that expire today, the hedging those contracts require becomes concentrated, fast, and highly reactive to small moves. The chain stops being a slow, smooth follower of the index and becomes a source of abrupt, same-session pressure on it.</p>
</div>

<p>This is the regime the rest of this track explains. It is not a claim that options "control" the market on any given day — plenty of days are driven by ordinary supply and demand in the underlying. It is a claim that the options chain is now large enough, and short-dated enough, that its mechanical hedging is a first-class force you should be able to read, not a footnote.</p>

<h2>Where this fits</h2>

<p>The remaining lessons build the machinery piece by piece: who takes the other side and why they must hedge (<a href="/learn/options/market-makers-middleman.html">the middleman</a>), what the widely-quoted open-interest number can and cannot tell you about that positioning (<a href="/learn/options/open-interest-limits.html">open interest limits</a>), how the hedging translates into concrete share orders (<a href="/learn/options/dealer-hedging-mechanics.html">dealer hedging mechanics</a>), and how the direction of that hedging defines two opposite market regimes (<a href="/learn/options/gamma-regimes.html">gamma regimes</a>).</p>

<details>
<summary>Self-check: 3 questions</summary>
<ol>
<li><strong>What does "0DTE" mean, and why is it singled out from other short-dated options?</strong><br>0DTE means zero days to expiration — a contract that expires the same day it is traded. It is singled out because a contract expiring within hours, near the current price, changes its sensitivity to the underlying far more sharply than a longer-dated one. That makes the hedging it requires fast and concentrated within a single session.</li>
<li><strong>Does a large options market, on its own, move the underlying stock or index? What is the missing ingredient?</strong><br>Not on its own. Size only matters because trading generates hedging: the firms that take the other side accumulate risk they must offset by buying or selling the underlying. The missing ingredient is that mechanical hedging flow, which scales with options activity. Without it, the options market could be large and still leave no footprint on the tape.</li>
<li><strong>A stock gaps sharply with no visible news. Why can options activity be a candidate explanation?</strong><br>Because a large options trade can force the firms on the other side to rebalance immediately, sending real buy or sell orders into the underlying. To an observer watching only price, that hedging flow is indistinguishable from a news reaction — the move is real, but its cause is mechanical, not informational.</li>
</ol>
</details>
