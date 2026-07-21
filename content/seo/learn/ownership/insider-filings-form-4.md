---
slug: insider-filings-form-4
family: lesson
title: "Form 4 Insider Filings: What They Show and What They Don't"
description: "Form 4 discloses insider trades within 2 business days. Learn who files, what each code signals, and why open-market buys outweigh grants or exercises."
track: ownership
cluster: ownership-analysis
published: 2026-07-20
updated: 2026-07-20
related:
  articles: [congress-trades-are-not-realtime-signals]
  live:
    - {href: /congress_trades.html, label: "Congressional trades disclosure tracker"}
cta: {href: /congress_trades.html, label: "See the congressional trades disclosure tracker"}
---
<div class="callout lead">
<span class="co-h">Learning objective</span>
Understand who is required to file Form 4, what the 2-business-day deadline means in practice, how to read the transaction code table, and why an open-market purchase is structurally different from a grant or option exercise as an information signal.
</div>

<p>Form 4 is a Statement of Changes in Beneficial Ownership filed with the U.S. Securities and Exchange Commission. When a corporate insider — a director, officer, or holder of more than 10% of a registered class of equity — buys or sells shares, they are required by Section 16(a) of the Securities Exchange Act of 1934 to report the transaction on Form 4 within two business days of its execution.</p>

<h2>Who must file</h2>

<p>The filing requirement covers three categories: (1) directors of the company, (2) officers (typically those designated as such in SEC filings — CEO, CFO, General Counsel, and others designated by the board), and (3) beneficial owners of more than 10% of any registered class of equity security. Family members and entities controlled by an insider may also be covered. The definition of "officer" for Section 16 purposes is set by SEC rules and may not match the company's internal titles.</p>

<h2>The 2-business-day deadline</h2>

<p>Under SEC rules implementing Section 16(a) (codified at 17 CFR §240.16a-3), a Form 4 must be filed electronically before the end of the second business day following the execution date of the transaction. The SEC maintains the full EDGAR system for public access: <a href="https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&type=4&dateb=&owner=include&count=40">Form 4 filings on SEC EDGAR</a>. A two-business-day window means that on the day you read a Form 4, the transaction may be up to two business days old — plus whatever time passed before the filing appeared in EDGAR and was indexed by data providers. The practical lag between execution and when the signal reaches a retail screen is typically two to four calendar days.</p>

<h2>Transaction codes</h2>

<table class="data">
<thead><tr><th>Code</th><th>Description</th><th>Information content</th></tr></thead>
<tbody>
<tr><td><strong>P</strong></td><td>Open-market purchase</td><td>Highest — voluntary, out-of-pocket capital at market price</td></tr>
<tr><td><strong>S</strong></td><td>Open-market sale</td><td>Mixed — may reflect diversification, taxes, or estate planning; not specific to view on stock</td></tr>
<tr><td><strong>A</strong></td><td>Grant, award, or other acquisition from company</td><td>Low — compensation event, not a voluntary investment decision</td></tr>
<tr><td><strong>M</strong></td><td>Exercise of derivative security (option)</td><td>Low to moderate — exercise alone does not indicate a directional view; often paired with an S code on the same filing</td></tr>
<tr><td><strong>F</strong></td><td>Payment of tax withholding by forfeiture of shares</td><td>Not a market signal — administrative tax event</td></tr>
<tr><td><strong>D</strong></td><td>Disposition to the company (surrender, forfeiture)</td><td>Context-dependent — often related to vesting conditions</td></tr>
<tr><td><strong>G</strong></td><td>Gift</td><td>Not a market signal — estate or charitable transfer</td></tr>
</tbody>
</table>

<h2>Why P codes carry more information</h2>

<p>An open-market purchase (code P) requires the insider to spend personal after-tax capital at the current market price. They are not receiving shares as part of compensation; they are choosing to buy additional exposure. The decision is voluntary, personal, and made with full knowledge of material non-public information they are legally prohibited from trading on under Rule 10b-5. This creates an incentive alignment: when an insider buys in the open market, they are adding economic risk they did not have to take. Grants and option exercises, by contrast, are compensation events — a new director receiving a stock grant is not expressing a directional view on the stock; they are receiving compensation structured to align long-term incentives. The transaction occurs because a board decision triggered it, not because the individual chose to deploy capital.</p>

<h2>Cluster buying context</h2>

<p>A single P-code purchase from one insider has limited information value on its own — insiders buy for many reasons unrelated to corporate outlook (tax-loss harvesting, rebalancing, contractual commitments). Multiple P-code purchases from different insiders in a short window — often called cluster buying — is a stronger observation because it requires that several independent individuals with different roles and risk tolerances all reached similar conclusions about the value of deploying personal capital at the current price. Even cluster buying is descriptive, not predictive: it reflects a concentration of insider cost basis at a price level, not a forecast.</p>

<h2>Common trap: reading grants as conviction</h2>

<p>A Form 4 showing an A-code transaction for 10,000 shares to the new Chief Marketing Officer is not evidence of insider conviction — it is a compensation grant. Reading grants as bullish signals is the most common Form 4 misinterpretation. When filtering Form 4 data for informative signals, filter to P codes only, exclude M codes unless the shares are retained rather than immediately sold (look for paired S codes on the same filing), and discard A, F, G, and D codes entirely for directional analysis.</p>

<h2>When this breaks</h2>

<p>Two structural features limit Form 4 usefulness. First, 10b5-1 plans: insiders who pre-schedule trades through a Rule 10b5-1 plan can execute purchases and sales during future windows when they may possess material non-public information, because the plan was established at a time when they did not. A P-code transaction executed under a 10b5-1 plan was decided months in advance and does not reflect the insider's current view of the company. Form 4 requires disclosure of whether a 10b5-1 plan was in place, but not all data aggregators surface this flag prominently. Second, filing lag: the 2-business-day deadline is frequently extended by late filings — SEC enforcement of late filers is periodic but not immediate. A filing that appears today may describe a transaction that occurred a week ago, well past the window when the information had maximum freshness.</p>

<p>The adjacent disclosure tracker covers congressional stock trades — a related but legally distinct category of mandated ownership disclosure: <a href="/congress_trades.html">see the congressional trades disclosure tracker</a>.</p>

<h2>Related</h2>
<ul>
<li><a href="/blog/congress-trades-are-not-realtime-signals.html">Congress trades are not real-time signals</a> — the disclosure lag and interpretation pitfalls that apply to STOCK Act filings, a parallel to Form 4's own lag issues</li>
</ul>

<details>
<summary>Self-check: 3 questions</summary>
<ol>
<li><strong>A Form 4 shows three insiders each filing a P-code transaction on the same date. A fourth filing on the same date shows an A-code for a different insider. How should you weight these transactions for informational purposes?</strong><br>The three P-code transactions represent voluntary open-market purchases — personal capital at market price — and the cluster of three different insiders acting near simultaneously adds incremental informational weight. The A-code transaction should be excluded from this analysis entirely; it is a compensation grant triggered by a board decision, not a directional investment choice. The cluster of three P codes is the informative observation.</li>
<li><strong>An insider files a Form 4 showing an M-code exercise of 5,000 options, immediately paired with an S-code sale of the same 5,000 shares on the same date. What does this transaction represent, and what information does it carry?</strong><br>This is a cashless exercise — the insider exercised options and immediately sold all resulting shares, netting the spread between exercise price and market price as cash. It reflects no directional conviction about the stock; the insider ended the transaction with zero incremental stock exposure. This is a compensation monetization event, not a market signal.</li>
<li><strong>Why might an insider's P-code purchase, filed today, not reflect their current view of the company?</strong><br>If the transaction was executed under a Rule 10b5-1 plan, it was scheduled in advance at a time when the insider did not possess material non-public information. The actual purchase decision was made months earlier when the plan was established. Form 4 discloses whether a 10b5-1 plan was in effect — checking this field before treating a P-code as a current bullish signal is essential.</li>
</ol>
</details>
