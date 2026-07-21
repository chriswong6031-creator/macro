---
slug: market-breadth
family: lesson
title: "Market Breadth: Measuring Who Is Actually Participating"
description: "Breadth reveals whether gains are broad or narrow. Learn advance/decline, percent above moving averages, new highs minus lows, and what divergence signals."
track: technical
cluster: market-internals
published: 2026-07-20
updated: 2026-07-20
related:
  lessons: [technical/52-week-highs]
  live:
    - {href: /markets.html, label: "Markets overview and breadth dashboard"}
cta: {href: /markets.html, label: "Check today's breadth on the markets board"}
---
<div class="callout lead">
<span class="co-h">Learning objective</span>
Understand the three primary breadth measures — advance/decline, percent above a moving average, and new highs minus new lows — and why a rising index with deteriorating breadth is a structurally different situation than a broad rally.
</div>

<p>Market breadth measures participation: how many stocks in a given universe are moving in the same direction as the index. An index is cap-weighted, so a handful of large-cap stocks can carry the headline number higher while the majority of names decline. Breadth indicators make that divergence visible.</p>

<h2>Three primary breadth measures</h2>

<h3>1. Advance / Decline</h3>

<div class="formula">
Advance/Decline Line (cumulative):
  Daily Net Advances = (number of advancing stocks) − (number of declining stocks)
  A/D Line(t) = A/D Line(t−1) + Daily Net Advances(t)
<br><br>
A/D Ratio (snapshot):
  A/D Ratio = Advancing / Declining
</div>

<p>The cumulative A/D line is a running total of daily net advances. It rises when more stocks go up than down and falls when more go down than up. Because it is equal-weighted across all listed issues, it gives small-cap names the same vote as large-cap names — which is both its strength (catches broad participation) and a source of divergence from cap-weighted indexes.</p>

<h3>2. Percent above a moving average</h3>

<div class="formula">
% Above MA(n) = (count of stocks with Close > MA(n)) / (total stocks in universe) × 100
</div>

<p>Common lookbacks: 50-day and 200-day moving averages. When 80% of S&amp;P 500 stocks trade above their 50-day moving average, the rally is broad. When an index rallies to new highs but this figure is 40%, a narrow group of stocks is doing the lifting. The specific threshold that constitutes "strong" or "weak" breadth is market- and era-dependent — the number is more useful as a direction-of-change gauge than as an absolute level trigger.</p>

<h3>3. New highs minus new lows</h3>

<div class="formula">
NH−NL = (stocks making n-period highs) − (stocks making n-period lows)
</div>

<p>Commonly n = 52 weeks. A positive and rising NH−NL suggests broad leadership development. A negative reading during an index rally means more stocks are hitting annual lows than annual highs — a structurally weak condition regardless of what the index is doing. This measure connects directly to the individual-stock 52-week high concept covered in the <a href="/learn/technical/52-week-highs.html">52-week highs lesson</a>.</p>

<h2>Worked example</h2>

<div class="worked">
<span class="co-h">Worked example</span>
<p>Suppose a 500-stock index rises 0.8% on a given day. The advance/decline data shows: 180 advancing, 290 declining, 30 unchanged.</p>
<p>Daily Net Advances = 180 − 290 = <strong>−110</strong></p>
<p>The index rose 0.8% but the A/D line fell by 110 — more stocks declined than advanced. The index gain was driven by a subset of large-cap components outweighing the majority of declining names. Breadth was negative on a positive-index day.</p>
</div>

<h2>Breadth divergence</h2>

<p>Divergence occurs when the index and breadth move in opposite directions over the same period. The index making a new high while the A/D line makes a lower high means the new index high required fewer and fewer stocks to sustain it — an increasingly narrow base. Divergences can persist for extended periods without resolving, and they resolve in both directions: the broad market can catch up to a narrow rally, or the narrow rally can break down. Breadth divergence is a diagnostic observation, not a timing signal.</p>

<h2>Common trap: confusing breadth washouts with breadth thrusts</h2>

<p>A breadth washout occurs when NH−NL or the A/D ratio reaches an extreme negative reading in a declining market — the majority of stocks selling off simultaneously. This tends to be a short-term oversold condition in a healthy market but can persist or worsen in a genuine bear trend. A breadth thrust is when an extreme percentage of stocks move higher within a short window after a decline — a signal that the broad market has recovered participation rapidly. Confusing the two is common: a single day of strong advances after a washout does not constitute a thrust by the formal definitions; the magnitude and duration matter. Treating a one-day bounce as a thrust is a category error that generates false recovery signals.</p>

<h2>When this breaks</h2>

<p>Mega-cap concentration eras systematically reduce the usefulness of breadth-versus-index divergence as an early warning. When five or ten stocks represent 30–35% of an index's market capitalization, those names alone can sustain index levels while a large majority of names underperform. The "warning" of divergence is real — the majority of stocks are indeed underperforming — but the index may continue rising for quarters because the heavyweights are large enough to pull it. In those conditions, breadth divergence is a correct observation about participation but not a reliable predictor of near-term index reversal.</p>

<p>Today's breadth context — advance/decline, percent above key averages, and new high/low counts — is on the markets board: <a href="/markets.html">check today's breadth</a>.</p>

<details>
<summary>Self-check: 3 questions</summary>
<ol>
<li><strong>An index rises 1.2% to a new all-time high. At the same time, NH−NL for the full universe is −85 (more new lows than new highs). What does this tell you, and what does it not tell you?</strong><br>It tells you that the new index high was achieved with a majority of individual stocks making new annual lows — participation was extremely narrow, and the headline number was carried by a few large-cap components. What it does not tell you is when or whether the index will reverse. Narrow breadth can persist for months, especially in high-concentration index eras.</li>
<li><strong>The S&amp;P 500 cumulative A/D line has been declining for three weeks while the index has been flat. What condition does this describe?</strong><br>The index is being held up by a few large components while the majority of stocks within it are experiencing more declining than advancing days. The cap-weighting of the index allows a minority of large names to mask a broad deterioration in the equal-weight universe.</li>
<li><strong>What distinguishes a breadth washout from a breadth thrust, and why does the difference matter?</strong><br>A washout is extreme simultaneous selling across a broad universe — an oversold condition. A thrust is extreme simultaneous buying across the broad universe after a decline, typically requiring a specific percentage (often cited as 90%+ advancing volume or issues) over a short window. The distinction matters because a washout does not by itself predict recovery; a thrust is argued to be a different quality of signal because of the force and breadth of the buying response. Treating any strong up-day after a selloff as a thrust is the common error.</li>
</ol>
</details>
