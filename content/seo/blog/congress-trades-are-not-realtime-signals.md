---
slug: congress-trades-are-not-realtime-signals
family: article
title: "Congress Trades Are Not Real-Time Signals"
description: "The STOCK Act gives members of Congress 45 days to disclose trades. By the time you see a filing, the position is weeks old and the context has shifted."
cluster: market-intelligence
published: 2026-07-20
updated: 2026-07-20
related:
  lessons: [ownership/insider-filings-form-4]
  live:
    - {href: /congress_trades.html, label: "Congressional trades tracker"}
cta: {href: /congress_trades.html, label: "See recent congressional disclosures"}
---
<p>The Stop Trading on Congressional Knowledge Act — the STOCK Act — requires members of Congress to disclose trades within 45 days of the transaction. By the time a filing appears in a public database and generates a news headline, the trade is legally allowed to be over a month old. Treating those disclosures as actionable buy or sell signals misunderstands what the law actually requires.</p>

<h2>What the STOCK Act actually says</h2>

<p>The STOCK Act, enacted in 2012 (<a href="https://www.congress.gov/bill/112th-congress/senate-bill/2038">S. 2038, 112th Congress</a>), requires members of the House and Senate to report the purchase, sale, or exchange of stocks, bonds, commodities, futures, and other securities within 30 days of receiving notification of the transaction, but no later than 45 days after the transaction itself. The House Ethics Committee's <a href="https://ethics.house.gov/financial-disclosure/stockact-information">disclosure guidance</a> specifies that the report must include the date of the transaction, the asset, and the amount in broad ranges (the largest range is simply "over $1,000,000").</p>

<p>This means a member could buy a position on day one, hold it for forty days, sell the entire position, and only then file a disclosure showing the original purchase — with no requirement to report the sale until another 45-day window opens. A reader looking at that disclosure would see a purchase with no indication that the position no longer exists.</p>

<h2>The filing-date versus transaction-date gap</h2>

<p>Published databases of congressional trades typically sort by filing date — when the report was submitted. This creates a systematic lag that looks like this in practice:</p>

<div class="worked">
  <span class="co-h">Typical timeline</span>
  <p>Day 1: Member executes a trade through a broker.<br>
  Day 3–5: Broker confirms and settles the transaction.<br>
  Day 30–45: Member files the periodic transaction report.<br>
  Day 46–52: The report is processed and appears in public databases.<br>
  Day 53+: News articles summarize "recent" congressional purchases.</p>

  <p>A retail trader acting on that news article is copying a position that may be 7–8 weeks old at minimum. The news event that prompted the trade, if any, occurred before day 1.</p>
</div>

<p>The gap between broker execution date and the filing date is the true signal lag — and it is not evenly distributed. Trades that are filed promptly (within a week of execution) do exist. But the disclosure window legally permits the maximum gap, and many filings appear at or near the 45-day limit. Any strategy that depends on timing cannot be designed around an upper bound.</p>

<h2>Amendments and their implications</h2>

<p>The STOCK Act also permits amendments to prior disclosures. A member may file an initial disclosure, then amend it to correct the transaction date, the ticker, or the amount range. Some databases surface the amended filing date, not the original transaction date, as the primary timestamp — compounding the dating ambiguity. The amendment may appear weeks or months after the original filing, showing up as new activity in screens that sort by most recent filing date.</p>

<h2>Common trap: confusing early disclosure with a signal</h2>

<div class="callout warn">
  <span class="co-h">Common trap</span>
  Headline-backtests of "congressional trading performance" typically measure returns from the transaction date forward, not from the public disclosure date forward. Since the transaction date is 30–45 days before the disclosure, these backtests are measuring something a public trader cannot access. Performance from the disclosure date forward is almost always weaker, and after accounting for the bid-ask spread, commissions, and the fact that many positions are in illiquid securities, often negative.
</div>

<p>The comparison to corporate insider filings (Form 4) is instructive here. Corporate insiders must file within two business days of a transaction. Two days of lag is categorically different from 45 days. A study of Form 4 signals (<a href="/learn/ownership/insider-filings-form-4.html">covered in the insider filings lesson</a>) can plausibly measure something a trader can act on. A study of STOCK Act filings at the 45-day average lag cannot make the same claim.</p>

<h2>What congressional disclosure data is actually useful for</h2>

<p>The 45-day lag does not make the data worthless — it means the data answers different questions than "what should I buy today."</p>

<p><strong>Position context:</strong> Congressional disclosures show broad ranges of position size, which can indicate conviction level relative to a member's other disclosed holdings. A purchase in the $500,001–$1,000,000 range versus $1,001–$15,000 carries different weight as an expression of view.</p>

<p><strong>Conviction clusters:</strong> When multiple members purchase the same security or sector within a short period — visible only in aggregate view across filings — the cluster may reflect shared information exposure through committee hearings, briefings, or legislation. The useful signal is the cluster pattern, not any single filing. Committee assignments, which are public, provide the context for interpreting which sectors a given member's trades are most likely to be informed by.</p>

<p><strong>Longer-horizon thematic context:</strong> Congressional portfolios shift slowly. A member's disclosed positions over a year can indicate sectors or companies that benefit from legislation their committee is working on. This is not a timing signal — it is thematic background research.</p>

<p>Mastermind's <a href="/congress_trades.html">congressional trades tracker</a> displays disclosures with the original transaction date surfaced alongside the filing date, so the lag is visible rather than hidden. It shows recent filings with entry-timing context — useful for the pattern and cluster analysis described above, not as a same-day trade signal.</p>

<h2>Where this analysis breaks</h2>

<p>The 45-day window is a legal maximum, not a typical filing behavior for all members. Some members file within days of a transaction and have a disclosed pattern of doing so. If a specific member consistently files within 5 days and their disclosed committee assignments cover the sector in question, the lag argument weakens. The data needed to know this — all historical filings for a given member with their actual transaction dates — is in the public record. Any serious use of this data should start there, not with the aggregate headline feed.</p>

<p>Additionally, the above analysis applies to equity trades. Options disclosures under the STOCK Act have different characteristics: an options position may represent a view on a specific time window, and the expiration date relative to the disclosure date may tell you whether the expressed view has already resolved before you can act on it.</p>
