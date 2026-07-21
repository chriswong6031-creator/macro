---
slug: trading-journal
family: page
title: "Free Trading Journal Spreadsheet (Excel & Google Sheets)"
description: "Free trading journal spreadsheet tracking R multiples, expectancy, profit factor and the cost of your mistakes. Works in Excel and Google Sheets."
cluster: trading-tools
published: 2026-07-20
updated: 2026-07-20
related:
  lessons: [risk/risk-reward-expectancy, risk/position-sizing]
  articles: [how-to-keep-a-trading-journal]
  live: []
cta: {href: /assets/downloads/mastermind-trading-journal.xlsx, label: "Download the free trading journal (.xlsx)"}
---
<p>This is a free, no-email-required trading journal spreadsheet in .xlsx format. Download it once and use it in Excel or Google Sheets. It logs your trades, scores your setups in R multiples, and shows you the dollar cost of your worst habits — a dashboard feature the popular free alternatives skip.</p>

<h2>What is in the spreadsheet</h2>

<p>Five sheets, each with a distinct job:</p>

<ul>
  <li><strong>Start Here</strong> — a one-page guide explaining what R multiples are, how to log a trade in 30 seconds, and what to do with the example rows before you start.</li>
  <li><strong>Trade Log</strong> — one row per trade, 600 rows pre-formatted. Fill in ticker, direction, entry, stop, target, and shares. Risk $, Planned R:R, P/L $, P/L %, R Multiple, and Days Held all calculate automatically once you close the trade. A mistake-tagging dropdown (Chased entry, Moved stop, Oversized, Early exit, No plan, Revenge trade, Other) feeds directly into the dashboard.</li>
  <li><strong>Settings</strong> — set your starting account size and default risk percentage once. The dashboard references these to keep context for your stats.</li>
  <li><strong>Dashboard</strong> — every stat recalculates automatically from your closed trades: total trades, win rate, average win and loss, payoff ratio, profit factor, expectancy in dollars and in R, average R multiple, best and worst trade, average days held, and a breakdown of each setup's win rate and total P/L. A cumulative P/L line chart updates as you add trades. The standout line is <strong>cost of mistakes</strong>: the combined P/L on every trade you tagged with a mistake. Most free journals do not compute this.</li>
  <li><strong>Playbook</strong> — a 20-row table where you define your setups: entry rules, exit rules, the market conditions that make the setup valid, and notes. The Trade Log's setup dropdown pulls from this list, so your performance data ties back to the rule set you were trading at the time.</li>
</ul>

<h2>Key metrics explained</h2>

<p><strong>R multiple</strong> — the ratio of your actual P/L to your planned risk on the trade. An R of 2.0 means you made twice what you put at risk. An R of -1.0 means you took a clean full stop. Scoring in R lets you compare performance across trades of different sizes and calculate expectancy — the average R you earn per trade across a large sample.</p>

<p><strong>Expectancy</strong> — win rate multiplied by average winning R, plus loss rate multiplied by average losing R. A positive expectancy means that, given enough trades, the edge is real. A negative expectancy means it is not — regardless of your win rate.</p>

<p><strong>Profit factor</strong> — gross winning dollars divided by gross losing dollars. A value above 1.0 means total wins exceed total losses. Combined with win rate and payoff ratio, it gives a fuller picture of whether a setup produces durable results.</p>

<p><strong>Per-setup breakdown</strong> — the dashboard tables your setups from the Playbook against trades where you used them, showing trade count, win rate, total P/L, and average R for each. If Breakout — 52-week high produces an average R of 1.8 and Oversold bounce produces -0.3, you have a data-grounded reason to size the former larger and review whether the latter belongs in your playbook at all.</p>

<h2>How to use it in 30 seconds per trade</h2>

<ol>
  <li>When you enter a trade: fill in Date Opened, Ticker, Direction (dropdown), Setup (dropdown), Entry, Stop, Target, and Shares. Risk $ and Planned R:R calculate immediately.</li>
  <li>When you close: add Date Closed, Exit, and Fees. P/L $, P/L %, R Multiple, and Days Held fill in automatically.</li>
  <li>Tag any mistake from the dropdown. This is the step most traders skip and the one that pays the most dividends when you review a month of data.</li>
</ol>

<p>That is the entire daily workflow. The dashboard does everything else.</p>

<h2>Works in Excel and Google Sheets</h2>

<p>Every formula uses only functions supported in both applications: IF, IFERROR, AND, OR, ABS, SUMIF, SUMIFS, COUNTIF, COUNTIFS, AVERAGEIF, AVERAGEIFS, MAX, MIN, SUM, COUNT. No macros, no XLOOKUP, no LAMBDA, no external connections.</p>

<p>In Google Sheets: go to <strong>File &rarr; Import</strong>, choose the downloaded .xlsx file, and select "Insert new sheet(s)". Dropdowns and formulas carry over. The line chart may need a manual data-range confirmation in Google Sheets — if it appears blank, right-click the chart, select Edit chart, and verify the data range points to the Trade Log helper columns.</p>

<h2>A common reason trading journals fail</h2>

<p>The most common failure mode is not bad design — it is logging friction. When entering a trade takes more than a minute, traders stop doing it after the first losing week. This journal is one row. The formulas handle the math. The hardest part is the mistake tag, and that is exactly the part worth slowing down for.</p>

<p>The three example rows pre-loaded in the Trade Log (a winning long, a losing long, and a winning short) show every formula working before you enter your first trade. Delete them when you start — their Notes column says "EXAMPLE — delete me" so they are easy to spot.</p>

<h2>Related</h2>

<ul>
  <li><a href="/learn/risk/risk-reward-expectancy.html">Risk-reward and expectancy — how to calculate edge</a></li>
  <li><a href="/learn/risk/position-sizing.html">Position sizing — the only edge you fully control</a></li>
  <li><a href="/blog/how-to-keep-a-trading-journal.html">How to keep a trading journal that actually improves your trading</a></li>
</ul>
