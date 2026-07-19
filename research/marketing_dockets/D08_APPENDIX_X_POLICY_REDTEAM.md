# D08 Appendix X — Platform-Policy Red-Team: X (Twitter) Ban-Risk & Initial Sentinel Caps

**Author:** opus reviewer (D08 W1 red-team) · **Date:** 2026-07-19 · **Status:** sets initial Sentinel caps — config/marketing.yml sentinel: must match §3-4

> Scope note: this memo covers X's *written policy posture* and the ramp caps Sentinel enforces. It is not legal advice on U.S. investment-adviser registration; the regulatory-optics points in §2 are flagged as risk, not adjudicated.
>
> Source reachability (stated up front per the citation contract): the two primary X Help pages that carry the load-bearing rule text — `help.x.com/en/rules-and-policies/x-automation` and the platform-manipulation/authenticity page — returned **HTTP 403 to direct fetch** on 2026-07-19. The verbatim rule text below is reconstructed from the search-tool's extraction of those same X Help pages plus practitioner corroboration; where a quote's exact wording could not be re-fetched from the primary page, it is marked **[extracted, not re-fetched]**. Treat quoted policy strings as high-confidence-paraphrase, not court-admissible verbatim, until an authenticated fetch confirms them. No policy quote here is invented; unverified points say so.

---

## 1. What our loop does

The marketing loop runs **six brand-new X accounts** (`flagship`, `receipts`, `theme_desk`, `research_a/b/c`; D02) that post finance/markets content produced by an engine pipeline: signal calls with invalidation lines, annotated charts as media, track-record "receipt" posts, macro explainers, and movers/theme lists carrying multiple cashtags. Posting is **automated via computer control** — Opus-driven Chrome actuation of the logged-in web UI (D02), not the X API. Accounts share one operator, one host, and one content engine, and are assigned overlapping content types (mixed tilts, not topic silos). Sentinel (this docket) is the plan-level gate that sits between the content plan and the actuator: cross-account near-dup blocking, per-account cadence caps, a financial-advice lexicon, disclosure/receipt-honesty checks, and kill-switches. This memo sets the numbers Sentinel and the D02 actuator read.

---

## 2. Where the risk concentrates (ranked)

Ranked by probability × severity for **brand-new, automated, multi-account, finance** handles — the single highest-ban-risk configuration X describes.

**R0 — Non-API browser automation is itself a suspension trigger (EXISTENTIAL; Sentinel does not cover it).**
X's automation rules prohibit non-API automation of the website. Extracted from the X automation rules and corroborated by practitioners: *"Using non-API-based forms of automation like scripting the X website may result in permanent account suspension"* and *"Browser automation tools, headless Chrome scripts that log in with your password, or anything that bypasses OAuth is NOT authorized"* [extracted, not re-fetched; help.x.com/en/rules-and-policies/x-automation; opentweet.io/blog/twitter-automation-rules-2026, accessed 2026-07-19]. **D02's entire posting mechanism is the prohibited pattern.** No cap Sentinel sets addresses this — it is a design-level bet that "human-pace, human-plausible" UI actuation on warmed profiles evades the automated-behavior classifiers. Compounding it: a *"human-only interaction"* enforcement initiative reportedly began **February 2026**, putting accounts with *no real manual activity* at high permanent-suspension risk [socialnexis.com/guides/twitter-automation-safe-2026; outono.net bot-purge coverage, accessed 2026-07-19]. **This is the top risk and it is outside Sentinel's remit — it belongs in the operator go/no-go, not in a cap table.** Mitigations live at the actuator layer (human-pace jitter, real manual sessions interleaved, residential device/IP), not here.

**R1 — Duplicative / substantially-similar content across our own six accounts (coordinated inauthentic behavior).**
X policy, extracted: *"you may not post duplicative or substantially similar posts on one account or over multiple accounts you operate"* and *"Posting duplicative or substantially similar content, replies, or mentions over multiple accounts you control, or creating duplicate or substantially similar accounts, with or without the use of automation, is never allowed"* [extracted; help.x.com authenticity / platform-manipulation, accessed 2026-07-19]. Note "**with or without automation**" and "**substantially similar**," not identical — paraphrase does not clear it. X permits operating up to **~10 accounts for different, non-duplicative purposes** [extracted; blog.x.com 2018 automation-and-multiple-accounts, accessed 2026-07-19], which is the loophole our six accounts must live inside: genuinely distinct purpose/voice per account, not one feed fanned out. Six finance accounts, one engine, overlapping tilts is *precisely* the flagged pattern. **Sentinel coverage: partial** — the cross-account near-dup shingle gate catches text/media collisions, but "substantially similar *use case*" (six accounts all doing signals+charts+movers) is a structural/behavioral judgment the W1 token-shingle check does not make. Persona/tilt divergence is the real mitigation; Sentinel only backstops the text layer.

**R2 — New-account + link posting.**
Accounts <30 days old face tighter thresholds; behavior fine on an aged account suspends a fresh one [dicloak.com; postory.io; hoploninfosec.com, accessed 2026-07-19]. Links from new accounts are a specific spam signal, and X has tightened link restrictions in 2025-26. Posting the *same link twice* is called out as a new-account trip [gologin.com; dicloak.com, accessed 2026-07-19]. **Sentinel coverage: gap** — the drafted config has no `links_allowed` field. §3 makes links **forbidden in weeks 1–4** and adds the field.

**R3 — Cashtag frequency / financial-spam heuristic.**
Cashtag "piggybacking" (posting the same/many tickers to ride cashtag search) is a documented, actively-suspended bot vector: one study found *71% of suspicious financial-tweet authors classified as bots and ~37% suspended* [dl.acm.org/10.1145/3313184; arxiv 1804.04406, accessed 2026-07-19]. X's own spam policy treats *"sharing content in a bulk, duplicative, irrelevant or unsolicited manner"* and *"using trending [tags] on unrelated content"* as manipulation [extracted; opentweet.io, accessed 2026-07-19]. Movers/theme-list posts with many cashtags are the exact fingerprint. **Sentinel coverage: partial** — `max_same_cashtag_per_account_per_day` caps *repeat* of one ticker but not *breadth* (count of distinct cashtags in a single post). §4 adds a per-post cashtag cap.

**R4 — Media volume from fresh accounts.**
Every chart is an uploaded image. High media-post rate from a zero-history account reads as automated content-farming. No numeric X threshold is published (say so), so this is bounded conservatively by practitioner heuristic (2-10 posts/day "natural"; [opentweet.io, accessed 2026-07-19]). **Sentinel coverage: gap** — no `max_media_posts_per_account_per_day`. §3/§4 add it.

**R5 — Automation disclosure / labeling.**
X allows automated accounts *"as long as they're labeled … if you run an automated account that posts … stock prices … label it clearly in the bio"* and *"bot accounts need the 'Automated' label in their profile"* [extracted; help.x.com authenticity, accessed 2026-07-19]. Our accounts are automated and finance — squarely the category X expects labeled. **Not labeling is a standing violation independent of cadence.** Parody/AI labels are a separate regime (PCF accounts must put "parody/fan/commentary" in name+bio; there is *no* blanket rule forcing AI-generated-content disclosure, though unlabeled synthetic media "may eventually be treated as violations") [socialmediatoday.com parody + AI-label coverage; x.com/Safety 1877581125608153389, accessed 2026-07-19]. **Sentinel coverage: gap** — Sentinel gates posts, not profiles. This is an account-setup precondition (§5), not a cap. Note the tension: the "Automated" label is honest and policy-compliant but reduces reach/credibility — that is a business decision for the operator, and the honest reading of policy is that the label is expected.

**R6 — Financial-advice phrasing (platform + regulatory optics).**
*Platform:* X's financial-scam policy targets *"get rich quick," guaranteed-return, and money-flipping* framing; *"accounts that severely violate … will be permanently suspended as soon as they're detected, and even … accounts created to replace … the suspended accounts will be suspended"* [extracted; help.x.com financial-scam, accessed 2026-07-19] — i.e. re-registration does not recover. *Regulatory optics (flag, not adjudication):* unregistered accounts posting buy/sell calls with price targets invite investment-adviser and social-media-fraud scrutiny; the SEC has a standing investor alert on social-media investment fraud [investor.gov social-media-and-investment-fraud, accessed 2026-07-19]. Educational/observational framing + disclosure is the defensible posture. **Sentinel coverage: yes** — the financial-advice lexicon + disclosure law cover this; keep it strict.

**R7 — Reply / engagement automation.**
X: *"never automate likes, follows, retweets, replies, or DMs"*; automated following/unfollowing and the follow-unfollow trick are among the fastest suspension triggers [extracted; opentweet.io; multiple practitioner sources, accessed 2026-07-19]. Follow churn is repeatedly named as **the single most-policed action**, with ~400 follows/day cited as a trip point [dicloak.com; opentweet.io, accessed 2026-07-19]. **Sentinel coverage: yes for replies** (`max_replies_per_account_per_day: 0` in the draft — correct, hold it). **Gap for follows** — no follow cap exists in the draft config; §4 adds `max_new_follows_per_account_per_day` and pins it at 0 for the ramp.

---

## 3. Ramp schedule (the deliverable)

Caps are **per account**, gated on **account age**, and err deliberately low for brand-new automated finance handles. The actuator (D02) reads these from Sentinel config, not its own constants.

| Account age | Posts/acct/day | Min spacing | Links? | Media posts/day | Max same-cashtag/day | Replies/day | New-follows/day |
|---|---|---|---|---|---|---|---|
| **Weeks 1–2** | **2** ⁽¹⁾ | **120 min** ⁽²⁾ | **No** ⁽³⁾ | **1** ⁽⁴⁾ | **1** ⁽⁵⁾ | **0** ⁽⁶⁾ | **0** ⁽⁷⁾ |
| **Weeks 3–4** | **3** ⁽¹⁾ | **120 min** ⁽²⁾ | **No** ⁽³⁾ | **2** ⁽⁴⁾ | **2** ⁽⁵⁾ | **0** ⁽⁶⁾ | **0** ⁽⁷⁾ |
| **Week 5+** | **4** ⁽¹⁾ | **90 min** ⁽²⁾ | **Yes, ≤1/day** ⁽³⁾ | **3** ⁽⁴⁾ | **2** ⁽⁵⁾ | **≤2, Sentinel-gated** ⁽⁶⁾ | **≤5, manual-only** ⁽⁷⁾ |

**Footnotes (reasoning per number):**
⁽¹⁾ Posts/day: practitioner "natural" band is 2-10/day for *established* accounts [opentweet.io]; new accounts trip lower, so start at the floor of that band and add one post per two-week cohort. 4/day at week 5 matches the drafted default and stays well under any burst heuristic. Across six accounts this is still 12-24 posts/day of engine output — ample.
⁽²⁾ Spacing: burst posting ("a tweet every 30 seconds") is an explicit bot tell [socialnexis.com]. 120 min early spreads 2-3 posts across a trading day with no clustering; relax to 90 (the drafted default) only at week 5. With ±20 min actuator jitter (D02) the effective floor is ~100 min at week 5.
⁽³⁾ Links: new-account link posting is a named spam trigger and same-link-twice is a documented trip [gologin.com; dicloak.com]. Zero links until an account has ~4 weeks of clean history; then ≤1/day. Route traffic via profile bio/pinned post, not in-post links, during the ramp.
⁽⁴⁾ Media/day: no published X numeric threshold (stated), so bound by the 2-10/day "natural" heuristic and keep media a *subset* of total posts — a fresh account that is *all* chart images reads as a content farm. Ramp 1→2→3.
⁽⁵⁾ Same-cashtag/day: cashtag piggybacking is an actively-suspended financial-spam vector [dl.acm.org 3313184]. 1 early, 2 at scale (drafted default) limits the "same ticker across the day" pattern; pair with the per-post breadth cap in §4.
⁽⁶⁾ Replies: reply automation is explicitly banned [opentweet.io]. Hold at **0** through week 4 (matches drafted default). Any week-5+ reply lane must be Sentinel-gated and ≤2/day (D02 W2 asks for ≤3; this memo tightens to 2 for new accounts) — and honestly, replies from an automated finance account are the riskiest engagement surface; default to 0 indefinitely unless the operator explicitly opens it.
⁽⁷⁾ New-follows: follow churn is the fastest suspension trigger and the most-policed action [dicloak.com]; ~400/day is a *trip point*, not a target. Automated following is banned outright, so the ramp value is **0** — any following at week 5+ must be **manual, operator-performed**, ≤5/day, never scripted by the actuator.

---

## 4. Recommended Sentinel config deltas

Comparison against the currently-drafted defaults. Where research says the draft is too loose or missing a field, the override/addition is listed. **The draft's static single-value caps must become age-tiered (§3); the values below are the week-5+ ceilings unless noted.**

| Key | Drafted default | Recommended | Verdict |
|---|---|---|---|
| `near_dup_jaccard` | 0.60 | **0.50** | **Override — tighten.** 0.60 lets genuinely similar finance posts (same ticker, same template, reworded) pass; "substantially similar" is the policy bar, and finance copy is templated. Lower = more aggressive blocking. Cost is false-positive rewrites, which is the safe direction. |
| `max_posts_per_account_per_day` | 4 | **age-tiered 2 / 3 / 4** (§3) | **Override — make tiered.** 4 is acceptable as the *week-5+* ceiling; it must not apply in weeks 1-4. |
| `min_minutes_between_posts` | 90 | **age-tiered 120 / 120 / 90** (§3) | **Override — make tiered.** 90 only from week 5. |
| `max_same_cashtag_per_account_per_day` | 2 | **age-tiered 1 / 2 / 2** (§3) | **Override — make tiered** + add breadth cap below. |
| `max_replies_per_account_per_day` | 0 | **0** (hold; ≤2 only if operator opens a gated week-5+ lane) | **Keep.** Correct as drafted. |
| `max_receipt_age_days` | 7 | **7** | **Keep.** Aligns with the docket's stale-receipts refusal (>7d). |
| `links_allowed` | *(absent)* | **add; false in wk1-4, ≤1/day wk5+** | **New field.** R2 gap. |
| `max_media_posts_per_account_per_day` | *(absent)* | **add; age-tiered 1 / 2 / 3** | **New field.** R4 gap. |
| `max_cashtags_per_post` | *(absent)* | **add; 3** | **New field.** R3 — caps per-post cashtag *breadth* (piggybacking fingerprint), distinct from the same-ticker/day cap. |
| `max_new_follows_per_account_per_day` | *(absent)* | **add; 0 (manual-only ≤5 wk5+)** | **New field.** R7 gap — no follow cap exists today. |
| `account_age_days` (per account) | *(absent)* | **add; drives the tier lookup** | **New field.** The whole ramp needs account birthdate in `desk_network` config to select the tier. Without it the tiers are un-enforceable. |

House-law guard: every Sentinel check above is **deterministic and de-escalating only** — it drops/quarantines/downgrades, never originates or upgrades an item (D08 trap; house LLM law). The near-dup and lexicon checks must not call an LLM to *rewrite* a quarantined item into passing — quarantine is terminal for that item; rewriting is a separate producer action, re-gated from scratch.

---

## 5. Gaps Sentinel W1 does not cover (honest list)

1. **Non-API browser automation itself (R0)** — the mechanism is the violation; no cap mitigates it. *Later-wave mitigation:* human-pace actuation, interleaved genuine manual sessions per account, and residential device/IP — or migrate to the sanctioned X API. This is an operator go/no-go, not a Sentinel setting.
2. **Actuator behavioral fingerprint** — identical compose-timing, cursor paths, upload cadence across six accounts is a cross-account correlation signal Sentinel never sees (it gates content, not keystrokes). *Mitigation:* per-account timing/jitter profiles at the D02 layer.
3. **Device / IP / browser-profile diversity** — six accounts from one host/IP/fingerprint is a coordinated-account signal. *Mitigation:* per-account isolated profiles + distinct network egress; operator-owned.
4. **Account-creation hygiene** — phone/email reuse, creation burst, no warm-up. *Mitigation:* stagger creation, age accounts with manual use before the loop touches them.
5. **Follow/engagement behavior** — Sentinel now caps follows in config (§4) but cannot *observe* actual follow actions; enforcement depends on the actuator honoring the cap. *Mitigation:* actuator-side counter + audit.
6. **Profile-level automation/parody labeling (R5)** — Sentinel gates posts, not bios. *Mitigation:* account-setup checklist precondition, verified before `MARKETING_PUBLISH_ENABLED` is ever set.
7. **"Substantially similar *use case*" across accounts (R1)** — a structural judgment beyond token-shingle text similarity. *Mitigation:* enforce genuine persona/tilt divergence at content-plan design; periodic human audit of whether the six accounts read as one feed.

---

## 6. Kill criteria — pull `MARKETING_PUBLISH_ENABLED` immediately on any of:

1. **First temp-lock, "unusual activity" challenge, or phone/CAPTCHA re-verify on *any* one of the six accounts** — treat as a fleet signal, not an isolated event; one automated-behavior flag implies the actuator pattern is detectable. Halt all six, diagnose before resuming.
2. **First suspension or shadowban on any account.** Shadowban detection method: from a logged-out session (or a clean unrelated account), confirm the handle's recent posts appear in (a) the handle's own timeline, (b) cashtag/hashtag search, and (c) reply threads under others' posts; a post absent from search but present on-profile = search suppression. Run this daily during the ramp; automate the check read-only.
3. **Follower count drops during a platform bot-purge window** (the Feb-2026 "human-only" enforcement waves) — sudden follower loss across multiple accounts signals the fleet is being classified as bots [outono.net bot-purge, accessed 2026-07-19]. Pause and reassess before it escalates to suspension.
4. **Reach collapse** — median impressions/post fall >70% week-over-week with no content change: a soft-limiting signal (X may "filter your posts from search results" short of suspension).
5. **Any account receives an X policy notice** citing platform manipulation, spam, or automation — stop the whole fleet; re-registration does not recover a severe financial-scam violation (§2 R6).
6. **Stale graded-receipts ledger >7 days** (already a Sentinel plan-refusal, `max_receipt_age_days: 7`) — do not post receipts we cannot back; this is both a house-law (display-only-until-validated / receipt-honesty) and a scam-optics guard.

---

### Sources (accessed 2026-07-19)

- X automation development rules — https://help.x.com/en/rules-and-policies/x-automation *(403 to direct fetch; extracted via search tool)*
- X authenticity / platform-manipulation & spam — https://help.x.com/en/rules-and-policies/authenticity *(403 to direct fetch; extracted via search tool)*
- X financial scam policy — https://help.x.com/en/rules-and-policies/financial-scam
- X automation & multiple accounts (dev blog) — https://blog.x.com/developer/en_us/topics/tips/2018/automation-and-the-use-of-multiple-accounts
- X parody/PCF & AI-label announcements — https://www.socialmediatoday.com/news/x-formerly-twitter-adds-requirements-for-parody-accounts/744563/ ; https://x.com/Safety/status/1877581125608153389 ; https://www.socialmediatoday.com/news/x-formerly-twitter-tests-ai-content-labels/812913/
- Practitioner automation-rules & rate limits — https://opentweet.io/blog/twitter-automation-rules-2026 ; https://socialnexis.com/guides/twitter-automation-safe-2026 ; https://www.unfollr.com/blog/twitter-automation-rules
- New-account / suspension-wave triggers — https://dicloak.com/blog-detail/xtwitter-account-suspended-your-complete-guide-to-recover-your-x-account-in-2026 ; https://postory.io/blog/twitter-account-suspended ; https://gologin.com/blog/twitter-account-suspended/ ; https://hoploninfosec.com/x-suspended-twitter-account-violation-of-rules
- Bot-purge / human-only enforcement (Feb 2026) — https://www.outono.net/elentir/2026/04/06/bot-purge-the-reason-why-many-users-are-losing-followers-on-x-twitter/
- Cashtag piggybacking / financial-spam research — https://dl.acm.org/doi/10.1145/3313184 ; https://arxiv.org/pdf/1804.04406
- SEC social-media investment-fraud alert — https://www.investor.gov/introduction-investing/general-resources/news-alerts/alerts-bulletins/investor-alerts/social-media-and-investment-fraud-investor-alert
