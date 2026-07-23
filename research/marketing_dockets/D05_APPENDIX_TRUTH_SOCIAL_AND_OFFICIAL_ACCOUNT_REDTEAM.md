# D05 Appendix — Red-Team: Truth Social & Official-Account Monitoring (D05 item 7)

**Author:** opus reviewer (D05 W2 red-team) · **Date:** 2026-07-22 · **Status:** RULING — gates D05 item 7. Verdict per source class in §2; W1 shape for the cleared path in §4. Supersedes the D05 W0 assumption ("official-account mirrors … scrape lanes") for the Trump/Truth-Social case: an **official licensed API now exists** (§1), which reframes the whole question.

> Scope note: this memo covers automated **reading/monitoring** of Truth Social and official company X accounts to feed the breaking desk — a distinct question from D08's posting-automation red-team (D08 ruled our *own posting* via non-API browser control is the existential R0 risk). Reading someone else's public posts implicates the *source platform's* scraping/ToS terms and API economics, not X's automation-suspension rules for our handles. This is not legal advice; ToS-breach and platform-ban exposure are flagged as risk, not adjudicated.
>
> Source reachability (citation contract, per D08): `help.truthsocial.com/legal/terms-of-service/` and `help.x.com/en/rules-and-policies/x-automation` returned **HTTP 403 to direct WebFetch** on 2026-07-22 (same posture D08 hit). Truth Social ToS §-clauses below were extracted via the search tool's fetch of that same primary page and are **verbatim-confidence**; X automation strings are marked **[extracted, not re-fetched]** and corroborated by the developer agreement. No quote is invented; unverified points say so.

---

## 1. What changed since D05 W0 was written (2026-07-19)

D05 item 7 assumed direct-scrape lanes with "screenshot-of-source as citation imagery where APIs don't exist." For **Trump/Truth Social specifically, an API now exists.** On **2026-07-16** Trump Media & Technology Group (TMTG) announced **Truth API**, a *licensed, real-time, machine-readable* B2B feed of the **10 most influential Truth Social accounts** (Trump's included), delivering posts "in milliseconds," 24/7, with a historical archive back to 2022; **GA 2026-08-01** [cnbc.com/2026/07/16 truth-social-wall-street-traders-api; finance.yahoo.com TMTG-launches-truth-api, accessed 2026-07-22]. It is explicitly aimed at "high-frequency and algorithmic trading firms," priced in reporting at **up to $100,000/month** [tradersunion.com truth-social-data-feed; time.com/2026/07/17 truth-social-api-wall-street; fortune.com/2026/07/17, accessed 2026-07-22]. TMTG's own framing: "no official, integrated API has existed" before, and firms that pulled the data anyway had been "running afoul of its terms of service" [cnbc, accessed 2026-07-22]. That last clause is the tell — see §2.

---

## 2. Verdicts by source class

### 2A. Truth Social (Trump's posts) — direct scraping: **DO NOT BUILD.** Official Truth API: **DO NOT BUILD (economically out of scope).** Wire-relay of his posts: **BUILD (already covered — §3).**

**Direct scraping is a flat ToS violation.** Truth Social's ToS bars it three ways over, verbatim [extracted via search-tool fetch of help.truthsocial.com/legal/terms-of-service/, accessed 2026-07-22]:
- §7(9): "engage in any automated use of the system, such as using scripts … or using any data mining, robots, or similar data gathering and extraction tools."
- §7(22): "use, launch, develop, or distribute any automated system, including … any spider, robot … scraper, or offline reader that accesses the Site."
- §7(1): "systematically retrieve data or other content from the Service to create or compile … a collection, compilation, database, or directory without written permission."
- §2 caps it: the user license is "solely for your personal, non-commercial use," and "no … Content … may be … aggregated, republished … for any commercial purpose whatsoever, without our express prior written permission."

Our use is commercial (a monetized product's marketing engine) and systematic (a poller building a ledger). **Every clause above is on point.** TMTG has *just* launched a paid product for this exact demand and publicly framed prior scrapers as ToS-breaching — i.e. an actively-defended, monetized surface with a plaintiff's motive. Scraping it is the worst risk/reward on the board: legal exposure + IP/robots blocking + fragile HTML, to beat the wire by seconds we cannot monetize. **Kill.**

**The official Truth API is correct-but-not-for-us.** It is the licensed, ToS-clean path — and it is a ~$100k/mo HFT product delivering millisecond latency we have no use for (a marketing post going out 4 minutes vs 4 seconds later is indistinguishable to our audience). Building against it fails on cost, not principle. Revisit only if the operator ever buys the feed for the *trading* side and the marketing lobe can piggyback on an already-licensed pull.

### 2B. Official company X accounts (e.g. $NVDA IR, hot-company drops) — direct scrape/RSS-bridge: **DO NOT BUILD.** X API read tier: **BUILD WITH NAMED MITIGATIONS (deferred; not W1).** Wire-relay: **BUILD (already covered — §3).**

- **Scraping / RSS-bridge / Nitter is dead and prohibited.** "Nitter is dead" after X's Feb-2024 guest-account shutdown; "direct scraping remains explicitly prohibited by X's Terms of Service" [socialcrawl.dev/blog/x-twitter-api-2026, accessed 2026-07-22]. Same kill as 2A. No RSS-bridge lane.
- **Reading via the X API is permitted and is a genuinely different question from D08's posting/following bans.** The prohibited automations are write-side — "never automate likes, follows, retweets, replies, or DMs" and mass follow/unfollow [extracted, not re-fetched; help.x.com/en/rules-and-policies/x-automation, accessed 2026-07-22]. **Read-only, server-to-server monitoring of public accounts via an App-Only Bearer Token is explicitly allowed** [socialcrawl.dev; developer.x.com/en/developer-terms/agreement-and-policy, accessed 2026-07-22]. This does **not** touch our own accounts' suspension risk (D08 R0) — it is a separate app/credential reading third-party public data.
- **The blocker is economics, not policy.** As of **2026-02-06** there is **no free tier for new developers**; new signups go to pay-per-use at **~$0.005 per post read, capped at 2,000,000 reads/month**, GET /2/tweets at 300 req/15 min [autotweet.io/blog/twitter-api-guide-2026; blotato.com/blog/twitter-api-pricing; socialcrawl.dev, accessed 2026-07-22]. Polling a handful of IR accounts is cheap in dollars, but stands up a metered paid dependency + credential + spend cap for marginal latency over the wire. **Verdict: cleared on policy, deferred on value** — do not build for W1; named mitigations if the operator later wants it (§4B).

### 2C. Practical middle path (wire-relay via existing `breaking_feed.py`) — **BUILD / already built; this is the answer for W1.**

`engine/marketing/breaking_feed.py` already ingests CNBC + MarketWatch wire feeds (plus Fed/BLS/BEA/White-House official feeds) with conditional GET, backoff, and a local seen-ledger. Financial wires relay market-moving Trump posts and major company announcements **within minutes** — and that is exactly how essentially every non-HFT desk consumes them. The only party for whom the wire lag matters is the algo trader paying $100k/mo to shave seconds; **for a content-marketing post it does not matter at all.** See §3 for the honest latency accounting. **This lane is the recommended home for the entire "hot news drop" use case.** Ship it (it needs the D01 wiring D05 item 6 already calls for — orthogonal to this memo).

---

## 3. Latency reality check (why the wire is "fast enough")

The gap the direct-monitor lanes would close is small and, for our purpose, worthless:
- Algo desks "ingest presidential statements within seconds"; the entire premium product exists to beat a **push notification** by milliseconds-to-seconds [editorandpublisher.com see-how-trumps-posts-move-stocks; time.com/2026/07/17, accessed 2026-07-22]. The competition is measured in seconds — a race we are not in.
- Wires relay the same event in **single-digit minutes**; a marketing card that publishes a few minutes post-event is fully on-time for an audience of retail traders, not a liability.
- **Epistemic caveat that matters more than latency:** JPMorgan's analysis finds **most** Trump posts move markets *no more than normal daily noise*; only a small subset — tariff/Fed/named-company posts — are the exceptions (e.g. AEO +20% after his ad-controversy post; the Apr-2025 tariff-pause rally) [san.com the-market-largely-ignores-trumps-posts, accessed 2026-07-22]. A raw Truth-Social firehose would be **mostly non-market-moving content** our deterministic `breaking_relevance` filter would (correctly) discard anyway. The wire self-selects for the newsworthy subset — an advantage, not a deficiency: the wire's editorial filter is doing free relevance pre-screening that a direct feed would force us to replicate. Direct monitoring would buy us *more noise, sooner.*

**Conclusion:** the existing wire-relay lane already gets us there in practice. The honest answer to D05 item 7 is that the middle path is the whole path.

---

## 4. Implementation shapes (for the cleared paths only — no build in this memo)

### 4A. W1 (recommended, now): nothing new to build — extend the existing wire lane.
- **Module:** none new. Widen `_SOURCES` in `engine/marketing/breaking_feed.py` to add 1–2 more `source_tier: "wire"` finance-wire RSS endpoints (e.g. a Reuters/AP markets feed) so major Trump/company events land from ≥2 independent wires (corroboration + resilience if one lags). Each stays a plain `FeedItem` (schema in `breaking_feed.py` docstring) — no code path changes; `breaking_relevance._classify_event` already routes `policy`/`company_news`, `_match_tickers` already tags $NVDA-class names, `breaking_summary.validate_summary` already blocks unsourced numbers, and `chart_render.render_breaking_card` already stamps the wire tier chip.
- **Citation imagery:** for a Trump/official-account event surfaced via a wire, the card cites **the wire** (honest tier = `wire`), never a laundered "as if from the source" claim — matches the D05 trap "the card must show the tier-source actually used, not a laundered re-report." Do **not** screenshot Truth Social/X posts as card imagery (redistribution of §2A/2B content + implies a direct feed we don't have).

### 4B. Deferred (operator-gated, only if wire proves insufficient): X API read lane.
- **Module:** new `engine/marketing/breaking_x_read.py`, adapter-shaped like the existing pollers — reads a small allowlist of **official/verified IR handles** ($NVDA, etc.) via App-Only Bearer Token GET, emits the same `FeedItem` dict with `source_tier: "official"`, feeds straight into `poll_all`'s dedupe/relevance/card path. Zero changes downstream.
- **Named mitigations (all required before it may ship):** (1) operator provisions a **read-only, separate app credential** — never share the D02 posting/actuation identity; (2) budget guard honoring the 2M-reads/mo cap + a hard spend ceiling in config (metered dependency); (3) allowlist of **verified official accounts only** — no keyword/cashtag firehose (that reintroduces the noise §3 warns of and burns reads); (4) still cite the account+timestamp honestly, `source_tier: "official"`; (5) **no write scope on the token** — reading is clean, but a posting-capable token on this lane would collide with D08 R0.
- **Truth API:** out of scope for the lobe on cost; documented here only so a future session doesn't re-litigate — if TMTG's feed is ever licensed for the *trading* side, marketing may piggyback the already-authorized pull; do not license it for marketing alone.

---

## 5. Kill criteria (for anything cleared here)

1. **Any direct-scrape lane against Truth Social or X** — kill on sight; it violates the ToS clauses in §2A/2B and this memo. Non-negotiable.
2. **Card imagery that screenshots a Truth Social / X post** — kill; redistribution of §2 content and implies a direct feed we don't have. Wire tier chip only.
3. **X read lane (4B) exceeds its spend cap or touches a write-scoped / D02-shared credential** — pull the lane; it has crossed from "reading public data" into cost-overrun or D08-R0 territory.
4. **A cited wire is caught relaying an unverified/hoax "Trump said" claim** — the breaking-desk credibility rule (D05 §Why) dominates: prefer ≥2-wire corroboration for platform-sourced political posts; a single-wire uncorroborated political-post relay must fall to the next-morning digest, not instant publish.

---

### Sources (accessed 2026-07-22)
- Truth Social Terms of Service — https://help.truthsocial.com/legal/terms-of-service/ *(403 to direct fetch; §7/§2 clauses extracted via search-tool fetch of the primary page)*
- Truth API launch — https://www.cnbc.com/2026/07/16/trump-truth-social-wall-street-traders-api.html ; https://finance.yahoo.com/technology/articles/trump-media-technology-group-launches-130000261.html ; https://time.com/article/2026/07/17/truth-social-api-wall-street-trump-media/ ; https://fortune.com/2026/07/17/trump-media-truth-psi-fast-market-posts/ ; https://tradersunion.com/news/financial-news/show/2711539-trump-media-truth-social-data-feed/
- X API 2026 pricing / read tier / no-free-tier / Nitter dead — https://www.autotweet.io/blog/twitter-api-guide-2026 ; https://www.blotato.com/blog/twitter-api-pricing ; https://www.socialcrawl.dev/blog/x-twitter-api-2026
- X automation rules (read vs write) — https://help.x.com/en/rules-and-policies/x-automation *(403 to direct fetch; extracted via search tool)* ; https://developer.x.com/en/developer-terms/agreement-and-policy
- Trump-post market-impact / latency / most-posts-don't-move — https://www.editorandpublisher.com/stories/see-how-trumps-truth-social-posts-move-stocks,262665 ; https://san.com/cc/the-market-largely-ignores-trumps-posts-these-are-the-exceptions/
