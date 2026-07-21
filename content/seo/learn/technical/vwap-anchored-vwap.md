---
slug: vwap-anchored-vwap
family: lesson
title: "VWAP and Anchored VWAP: The Fair-Price Reference"
description: "VWAP is volume-weighted average price from a chosen anchor. Learn the formula, why institutions use it as a benchmark, and the trap of calling it support."
track: technical
cluster: price-volume
published: 2026-07-20
updated: 2026-07-20
related:
  lessons: [technical/macd]
  live:
    - {href: /us_stocks.html, label: "Live ranked stock board"}
cta: {href: /us_stocks.html, label: "See the live ranked stock board"}
---
<div class="callout lead">
<span class="co-h">Learning objective</span>
Understand the VWAP formula, why anchor choice determines what question you are asking, how institutions use VWAP as a cost benchmark, and why calling VWAP "support" misframes what the indicator actually measures.
</div>

<p>VWAP — Volume-Weighted Average Price — is the cumulative sum of (price × volume) divided by the cumulative total volume since a chosen starting point. It answers one question: what is the average price at which all shares traded since the anchor have exchanged hands?</p>

<h2>The formula</h2>

<div class="formula">
VWAP from anchor bar A to current bar t:
<br>
  Typical Price(i) = (High(i) + Low(i) + Close(i)) / 3
<br>
  Cumulative PV = Σ [Typical Price(i) × Volume(i)]  for i = A to t
  Cumulative V  = Σ [Volume(i)]                      for i = A to t
<br>
  VWAP(t) = Cumulative PV / Cumulative V
</div>

<p>VWAP is cumulative — it cannot be re-derived from bar i alone. Each new bar updates both cumulative totals. The typical price uses the high-low-close average rather than the close alone, distributing weight across the full bar's trading range.</p>

<h2>Session VWAP vs. anchored VWAP</h2>

<p>Session VWAP resets at the market open each day, answering: "what is the average price at which today's volume has traded?" Anchored VWAP holds a fixed starting bar — an earnings release, a breakout, a market structure pivot — and answers: "what is the average price at which volume has traded since that event?" The anchor choice <em>is</em> the analytical question. A VWAP anchored to an earnings date measures the average cost basis of participants who entered after the news. A VWAP anchored to a market-wide low measures the average cost basis of the post-trough buyers. Choosing an anchor carelessly produces a number that answers a question you did not mean to ask.</p>

<h2>Worked example</h2>

<div class="worked">
<span class="co-h">Worked example</span>
<p>A stock reports earnings on Monday at open. You anchor VWAP to Monday's open bar.</p>
<p>Monday: typical price $52, volume 4M shares → PV = $208M<br>
Tuesday: typical price $54, volume 2M shares → cumulative PV = $316M, cumulative V = 6M<br>
Wednesday: typical price $53, volume 1M shares → cumulative PV = $369M, cumulative V = 7M</p>
<p>Anchored VWAP after Wednesday = $369M / 7M = <strong>$52.71</strong></p>
<p>Price above this line means the average post-earnings buyer is currently profitable. Price below means the average post-earnings buyer is sitting on a loss — a meaningful context for understanding near-term supply pressure.</p>
</div>

<h2>Why institutions use VWAP as a benchmark</h2>

<p>Large buy-side institutions measure execution quality against VWAP: did their order fill at a better or worse price than the day's volume-weighted average? An institutional desk that bought a block above the session VWAP paid more than the average participant that day — a cost it must justify. This benchmark use means that institutional algorithms actively work orders around VWAP throughout the session, which concentrates real buying and selling pressure near the line. That concentration is the source of the observed price behavior around VWAP — it is a self-fulfilling mechanism tied to a real institutional workflow, not a market magic number.</p>

<h2>Common trap: treating VWAP as support</h2>

<p>Calling VWAP "support" or "resistance" misframes what it measures. VWAP is a rolling cost-basis reference, not a structural price level. When price returns to VWAP, it simply means the current price equals the average cost of all shares traded since the anchor — a potential equilibrium point, but not one with any physical or mechanical reason to hold. The observed tendency for price to react at VWAP reflects the institutional benchmark behavior described above, and it can break cleanly without warning when volume composition changes or when a macro catalyst overrides the mechanical order flow.</p>

<h2>When this breaks</h2>

<p>Two conditions destroy VWAP's usefulness as a reference. First, low-volume sessions: if a significant portion of a session's volume is concentrated in a brief opening or closing burst, the VWAP reflects that skewed distribution rather than a genuine all-day price equilibrium. A stock with 80% of its daily volume traded in the first 30 minutes has a VWAP that is dominated by the open and tells you little about mid-session fair value. Second, overnight gaps: session VWAP resets at the open, so a large gap automatically places price far from the prior session's VWAP and creates an apparent "distance from VWAP" that reflects nothing about intraday supply and demand — it is purely the arithmetic of the gap.</p>

<p>The live ranked stock board provides context on where today's movers sit relative to key price and volume levels: <a href="/us_stocks.html">see the live ranked stock board</a>.</p>

<details>
<summary>Self-check: 3 questions</summary>
<ol>
<li><strong>You anchor VWAP to a stock's earnings date six weeks ago. What specific question does this anchored VWAP answer?</strong><br>It answers: what is the average price at which all shares traded since the earnings date have changed hands? When current price is above this VWAP, the average post-earnings buyer has a gain; below it, the average post-earnings buyer has a loss. This is a cost-basis reference for the post-event participant pool, not a prediction of future price direction.</li>
<li><strong>A trading platform shows session VWAP at $48 and the stock is trading at $46. A commentator says "VWAP is overhead resistance at $48." What is wrong with this framing?</strong><br>VWAP is not a structural resistance level — it is the session's average cost. Calling it "overhead resistance" implies a mechanical reason price should stop there. The actual mechanism is institutional benchmark behavior (algorithms trying to fill near VWAP), which can and does break when conditions change. "Price is below the session's average cost" is more accurate than "VWAP is resistance."</li>
<li><strong>Why does VWAP become less informative on a day when 80% of a stock's volume trades in the first 30 minutes?</strong><br>Because the cumulative formula weights bars by volume. With 80% of volume concentrated at the open, VWAP is numerically dominated by the opening price range and barely changes thereafter. It no longer represents a meaningful all-day fair-value reference — it mostly reflects the opening auction price, which is its own separate mechanism.</li>
</ol>
</details>
