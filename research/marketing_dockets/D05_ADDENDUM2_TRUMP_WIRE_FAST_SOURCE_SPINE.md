# D05 Addendum 2 — Trump Wire: fast-source spine + speed-posture amendment (PRESS-FEEDS source register)

**Author:** Fable main loop (assessment + charter input) · **Date:** 2026-07-27 · **Status:** RULING INPUT — operator-directed. Amends the **latency posture** (§3) of [`D05_APPENDIX_TRUTH_SOCIAL_AND_OFFICIAL_ACCOUNT_REDTEAM.md`](D05_APPENDIX_TRUTH_SOCIAL_AND_OFFICIAL_ACCOUNT_REDTEAM.md); **every §2 kill in that appendix STANDS** (no Truth Social scraping, no X scraping/Nitter, no post screenshots, official Truth API out of scope on cost). This document is the concrete source-register + architecture spec the **PRESS-FEEDS** wave (Media masterplan rev 4) calls for. D05 remains the docket of record.

**Operator directive (2026-07-27):** Trump-statement tracking is chartered as a growth lane. Quoting-Trump posts are among the highest-engagement/highest-converting formats on X right now. Requirements: (1) fastest live sources — "it can't be lagging all the time"; (2) no copy-paste relay (X spam exposure) — paraphrase or fully original 1–2-sentence summaries; (3) a creative, non-fixed hook family (not literal "JUST IN"/"BREAKING" every time); (4) identify the home lobe.

---

## 0. What is amended vs. the 07-22 appendix — and what stands

**AMENDED — appendix §3 ("the wire is fast enough").** The appendix optimized for credibility only and ruled minutes-late acceptable because we are not trading the news. The operator now rules that **speed is the reach lever**: on X the engagement wave accrues to the first posts carrying a statement, so detection latency is product quality for this lane. New budgets (targets, not gates):

| Path | Detect target | Post target (end-to-end) |
|---|---|---|
| Truth Social post (via mirror) | ≤ 2 min | ≤ 5 min (P0) → ≤ 90 s (P1) |
| Wire headline (licensed push feed) | ≤ 30 s | ≤ 3 min (P0) → ≤ 90 s (P1) |
| Live remarks (speech desk, P2) | ≤ 60 s from spoken line | ≤ 3 min |

**STANDS — everything else.** Scrape kills (appendix §2A/2B) are non-negotiable; wire-relay posture; no screenshot imagery; summarize-with-citation LLM law (the model may only restate facts present in the source; deterministic relevance decides what is market-moving); ≥2-source corroboration for *platform-sourced political hearsay*; Truth API ($60–100k/mo HFT product) out of scope on cost. Nothing below requires touching a kill: the speed gain comes from **better legitimate sources**, a **resident runner**, and a **shorter posting path** — not from scraping.

---

## 1. Verified source register (probes 2026-07-27; re-verify from the VPS at build time — e.g. CNBC's API is Akamai-blocked from DO IPs, so Mac-side probes do not transfer)

### Tier W — licensed wire push (the spine; NEW since the appendix)

| Source | Access | Latency | Cost | Status |
|---|---|---|---|---|
| **Alpaca News API (Benzinga-backed)** | WebSocket `wss://stream.data.alpaca.markets/v1beta1/news` + REST; free key | ~seconds (vendor ~25–100 ms wire-side) | **Free tier** (200 calls/min; WS included) | TOP BUILD CANDIDATE — Benzinga politics/Government channel carries Trump/tariff/WH headlines; needs a live probe with a key (BUILD GATE) |
| Benzinga News API direct / via Massive | WS `wss://api.benzinga.com/api/v1/news/stream` | ~25 ms claimed | $99/mo (Massive add-on) or contact-sales | Paid upgrade if Alpaca free proves thin/delayed |
| **Newsquawk** | web/app; no public API | editorial seconds | $199–399/mo | The only retail service that **explicitly monitors Truth Social** as a product feature; optional operator buy — human squawk desk as a corroboration/coverage layer |
| FinancialJuice | WS `wss://stream.financialjuice.com/v1/stream` | free tier = 10-min delay; paid ~$69/mo real-time | free/paid | Secondary wire; political coverage unconfirmed |
| Existing RSS register (`config/marketing.yml breaking:`) | Fed/BLS/BEA/WH-actions/CNBC/MarketWatch RSS | 5-min poll design | free | Built (#3054); appendix §4A also calls for +1–2 more wire RSS feeds for 2-wire corroboration |

This tier upgrades D05's wire lane from "poll RSS every 5 minutes" to **push delivery in seconds** using a licensed feed — fully inside the wire-relay posture. It is the single highest-leverage change in the whole design.

### Tier M — Truth Social relay mirrors (published feeds; wire-relay posture — the mirror bears the platform relationship, we consume its published feed exactly as we consume CNBC's RSS)

| Source | Access | Probe result 2026-07-27 | Latency | Cost |
|---|---|---|---|---|
| **trumpstruth.org** (Defending Democracy Together) | RSS `https://trumpstruth.org/feed` (~98 KB) | **HTTP 200; items timestamped minutes before probe** (20:24Z at a 20:40Z probe); structured `xmlns:truth` ns; status URLs + full content incl. RT/media | ~2–5 min from post | free |
| **CNN archive** | JSON `https://ix.cnn.io/data/truth-social/truth_archive.json` (.csv/.parquet variants) | **HTTP 200; 34,930 rows / 19.2 MB; newest row ~3 h behind the mirror at probe time** | batchy (hours at times) | free |

Ruling: **trumpstruth = primary Truth-Social detector** (fast poll, 60–90 s interval, conditional GET); **CNN = corroboration + nightly backfill only** (19 MB payload → conditional GET mandatory, never the hot poll). Dual-mirror + wire fallback is the resilience posture: if a mirror dies, fall back to the wire tier — **never** to scraping (appendix kill 1). Residual risk stated honestly: a mirror can be pressured or die (TMTG actively monetizes this data); that is availability risk for us, not ToS risk — the mirror operator holds the platform relationship.

### Tier O — official channels

- WH RSS ×3 (news / presidential-actions / fact-sheets) — already polled by the sentinel (`engine/whitehouse_feed.py`) and present in the breaking register. Latency 1–8 h for releases; **whitehouse.gov stopped publishing remarks transcripts in May 2025**, so official text ≠ speech coverage.
- Roll Call Factbase (`rollcall.com/factbase/trump/`) — the only complete transcript archive post-May-2025; hours-lagged; archival/verification tier, not detection.
- WH public schedule + `whitehouse.gov/live` — the **event calendar** that arms the P2 speech desk.

### Tier X — X read lane · ⚡ OPERATOR OVERRIDE 2026-07-27: twitterapi.io AUTHORIZED as primary

**Override (operator ruling, 2026-07-27 — precedent: rev-3 posture overrides):** managed scrape-by-proxy X reading via **twitterapi.io** is **authorized and is the PRIMARY X-read provider**. The operator weighs its breadth (Zerohedge-class accounts, the full fast-wire set, @WHPressPool and beyond at ~$0.15/1k reads) above the supply-chain risk. This supersedes this addendum's earlier "do not substitute" line and narrows appendix kill 1 to **first-party scraping**: WE never run scrapers, browser automation, or cookie-auth readers against X or Truth Social — consuming a managed provider's API is now cleared.

Named conditions that keep the override bounded (all required):
1. **Read-only lane, VPS-resident key** (`TWITTERAPI_IO_KEY`) — never mingled with posting credentials, Buffer channels, or persona-account fingerprints/egress.
2. **Hard monthly spend cap in config** — the lane stops LOUDLY at the cap (start-of-line `::warning`), never silently degrades.
3. **Fallback ladder on provider death/degradation:** official X API read at allowlist scale (§4B mitigations, ~$10–30/mo) → wire-only. **Never DIY scraping** — that kill stands untouched.
4. **Allowlist-only** (`x_follow` register below) — no keyword firehose.
5. We never claim or imply a direct platform feed; attribution rules in §3 apply unchanged.

#### `x_follow` register v1 (from operator-supplied examples, evaluated for reword+value-add fit)

| Handle | Why / role | Class | Poll tier |
|---|---|---|---|
| @DeItaone | Bloomberg-Terminal relay — the benchmark wire; broadest fast macro/political/company flashes | hearsay unless source named | fast (60–90 s) |
| @FirstSquawk | squawk relay; geopolitical + macro flashes | hearsay | fast |
| @financialjuice | squawk relay that NAMES upstream sources ("Mehr News citing…") — good corroboration hygiene | hearsay w/ named source | fast |
| @zerohedge | fast one-liners + the only account in the set carrying sell-side research excerpts (JPM/GS quotes) → feeds `registers.claims` | claims/hearsay | fast |
| @WHPressPool | pool reports — primary-adjacent record of unstreamed remarks | primary-adjacent | fast |
| @NewsWire_US · @remarks · @Osint613 | Trump statement flashes + OSINT direct quotes | hearsay | mid (90–120 s) |
| @BRICSinfo | huge Trump/geopolitical engagement; accuracy varies — ALWAYS corroborate; doubles as an engagement-topic sensor | hearsay (strict) | mid |
| @rawsalerts | breaking geopolitical/security | hearsay (strict) | mid |
| @StockMKTNewz · @tradfi | clean company-news flashes | hearsay | mid |
| @unusual_whales | exec-voice quotes (Dimon class) + market factoids | hearsay | mid |
| @WatcherGuru · @WhaleInsider | crypto+macro JUST-IN reach leaders; crypto-company data posts | hearsay | mid |
| @HormuzLetter | long-form sourced geopolitical analysis → **Brief-planner story candidates, NOT the fast wire** | claims | slow (300 s) |
| @CoinDesk · @Cointelegraph | crypto-media confirmation layer | confirm | slow |

**EXCLUDED (encode the why so it isn't re-added):** **@HalfwayPost — SATIRE** (its "Obama third term" bit is a joke; a naive reworder relays it as news → hard satire/parody blocklist in the relevance filter, and any PCF-labeled account is auto-excluded); @Polymarket/@CoinbasePredict (brand/odds accounts — their news is relayed; a prediction-market "odds stamp" is a possible later content flavor, not a source); @SpencerHakimian/@FluentInFinance (opinion/takes — rewording opinion is low-value and plagiarism-adjacent; at most trend sensors); niche/foreign-language accounts deferred.

**Value-add law for relayed items:** attribute the NAMED upstream when the relay names it (NYT/Bloomberg/Mehr) — never the relay handle as if it were the source; unnamed → ≥2-account/wire corroboration or explicit "reports:" phrasing; attach our tape stamp whenever the tape moved; never relay satire; never lift an account's original *analysis* without attribution. Cost estimate at v1 shape (~18 handles, tiered 60–300 s polls, since-id cursors): **~$20–60/mo**; config default hard cap $75/mo (verify twitterapi.io's per-request floor at build).

### Tier S — speech desk (P2; the moat nobody at RSS tier has)

Live-event pipeline: WH YouTube/C-SPAN **audio** → `whisper.cpp` `large-v3-turbo` on the Mac Studio (Metal; ~0.4–0.7 s streaming lag; $0) → rolling transcript window → deterministic keyword arming (tariff/Fed/Iran/named-company lexicon) → LLM line-picker (summarize-with-citation **from transcript text only**) → wire lane, class `live-remarks`. YouTube's own caption track has a ~15 s server-side floor — acceptable fallback; direct audio beats it. This is the automated version of the Bloomberg Speed-Desk/Newsquawk human model and is the only lane in this doc that can put us *ahead* of RSS-tier relay accounts on live remarks. STT guard: a transcribed **precise number never posts uncorroborated** — round-phrase paraphrase only until a wire confirms the figure.

**What DeItaone actually is** (research ground truth): a human relaying Bloomberg Terminal headlines — upstream is the Terminal/Reuters. We cannot legitimately beat that on wire flashes; we can match its *effective* audience latency via Tier W and beat it on Truth-Social-native posts (Tier M at 2–5 min vs. his manual relay) and on live remarks (Tier S). The April 7 2025 case (Hammer-Capital false "tariff pause" → DeItaone → $6T whipsaw, Reuters 14 min later) is the standing reason the **corroboration law dominates speed** for hearsay-class items.

---

## 2. Architecture (build shape for PRESS-FEEDS)

**Runner — VPS-resident, not Actions cron.** Actions cron is documented-laggy (15–45 min); the VPS already runs 60 s systemd loops (`macro-live-fast`). Generalize `scripts/marketing_fastlane_daemon.py` (exists: kill-switch, heartbeat, 120 s tick; its only provider is the dead finviz path) into the statements poller driving `breaking_feed.poll_all()` + the new providers. D05 W0 laws carry over: honest UA, conditional GET/backoff, local-only seen-ledger, **zero repo/git writes from pollers**. The WH **sentinel stays the single canonical writer** of `data/whitehouse/*` on the Mac (unchanged); the poller keeps its own VPS-local store, and the **nightly** consolidates a curated statements ledger into the repo (forward-ledger law: nightly is the sole advancer).

**Posting path — reuse the #3478 breaking rail, then shorten it.**
- **P0 (no new mechanics):** poller emits qualifying items as immediate outbox items → `marketing-publish.yml` dispatch (`post_now`-class path) → Buffer `customScheduled` → X. Actions spin-up + deps ≈ 2–3 min → **~3–5 min end-to-end**. Competitive with everything except HFT feeds.
- **P1 (the real unlock):** a VPS-resident publish tick for wire-kind items (reuse `social_publisher.BufferPublisher` + the floor logic) → **detect-to-post < 90 s**. Needs Buffer creds on the VPS + an off-Actions source of truth for floor/cadence state — design that before building (the 10-min-floor ledger read must not race the Actions publisher).

**Accounts & preconditions (unchanged from the masterplans).** `news_flash` cohort + `mastermind_news` anchor are hard-blocked on **PRESS-FEEDS live + Persona W2 cadence resolver** — this addendum changes neither. **Interim:** the flagship (@mastermindx001) may carry **top-K wire posts today** (high salience threshold, e.g. ≤3/day) through the existing rail under the 10-min floor — this exercises the whole pipeline end-to-end before the news estate exists, on the account least sensitive to cadence.

**Triage & LLM economics.** Deterministic first (`breaking_relevance`: entity/keyword/event-class/salience — the JPMorgan finding stands: most Trump posts move nothing; the filter's job is to discard). LLM = haiku summarize-with-citation per surviving item (~$0.001/post), sonnet only for flagship-grade items. At 30–80 scored/day, 10–25 posted: **< $5/mo**. The operator's "higher LLM usage" concern about the fully-original-content route is a non-issue at wire scale — original 1–2-sentence summaries are BOTH the cheapest compliant option and the one D05 already mandates.

---

## 3. Copy law (originality / spam posture — answers the reword-vs-paraphrase-vs-original question)

**Ruling: fully original ≤2-sentence paraphrase, never verbatim relay, never "reword the relay account."** Three reasons: (a) X's copypasta/duplicate-content policy visibility-filters near-identical text, and its documented exemption is copy **plus your own commentary** — original phrasing with our own read is the safe class; (b) rewording DeItaone-class posts launders hearsay we didn't verify (April-7 failure mode) and adds zero value; (c) close-paraphrase of wire prose is exactly what the press validators exist to prevent. Source-of-truth first: his own posts (mirror-verified, cite "on Truth Social"), official releases, licensed wire headlines.

**House wire format:** `[opener] [original 1–2-sentence summary]. [tape-stamp when the tape actually moved]` — the tape-stamp ("WTI −1.8% on the headline") comes from **our own live feeds** (Sina hf_ futures, Webull, crypto) and is the differentiator no relay account has; it also satisfies the retained "every post carries real value" rule. Attribution inline always (`— WH pool report`, `— on Truth Social`, `— Benzinga wire`); honest tier chip on cards (appendix §4A).

**Hook family:** rotating opener pool per account codex, never one fixed phrase. Research found **no phrase-level penalty** on "JUST IN"/"BREAKING" (enforcement targets engagement *solicitation* and template-detection ML) — the risk is the fixed template, not the words. Seed pool (grow per persona voice): `🚨 TRUMP:` · `Now crossing —` · `White House, minutes ago:` · `On the tape:` · `New this hour:` · `Heads up:` · plain `TRUMP:` with flag emoji variants. Cross-account near-dup radar (Persona §2) applies at post time.

**Link posture:** no external link in the speed post (documented ~80% distribution suppression for link posts); source link in the first reply if threading is supported on our rail (BUILD CHECK: Buffer thread capability), else inline named attribution only.

**Hearsay law (kill criterion 4, restated):** direct-quote class (his own Truth/X post, mirror-verified against the status URL) = single primary source suffices. Hearsay class ("Trump told reporters…", TV remarks) = ≥2 independent wires OR explicit attributed phrasing ("Reuters reporting…") — an uncorroborated single-wire political claim never instant-publishes.

**Style guards already law:** AI-tell lexicon validator (rev 4); no signal-disclosure needed (wire ≠ signal kind); factual-tone rule on tragedy-class events (D05 trap list); no fabricated imagery; **no post screenshots** (kill stands).

---

## 4. Lobe placement (operator question: "see what lobe we integrate this into")

- **Program home: Agentic Media → PRESS-FEEDS** (Media Network D14), feeding the **Mastermind News anchor wire** + the **`news_flash` growth-spearhead cohort** (Persona D13). This addendum is PRESS-FEEDS' source-register spec; D05 stays the docket of record. It is NOT a new program.
- **Data organ:** VPS-local hot store + nightly-consolidated `data/statements/` forward ledger (statement.v1 rows: id, source, tier, url, published_at, detected_at, text, entities, event_class, salience, corroboration). Display-tier; accrues freely (context-accrual law — no gauntlet until anything here seeks authority).
- **Existing organs upgrade, don't duplicate:** WH sentinel keeps the site banner/qledger lane (Mac, single writer); `policy_lever` jawboning block later reads the richer statements ledger; **Chronicle** gains a `statements` adapter (nightly, deterministic) so Trump/WH statements become spine events.
- **Brain:** once the ledger accrues, register a lobe via the three `mastermind_context.py` registration points (fold into `chronicle` or a new `washington` summarizer) — **not** a W1 deliverable. This is a marketing/media + context organ, not a Neural-Web reasoning lobe; metabolism lobe-genesis machinery does not apply.

## 5. Sequencing

| Wave | Contents | Blocked on |
|---|---|---|
| **B1** | Tier-W probe (Alpaca key) + trumpstruth/CNN providers + widen wire RSS (§4A) + VPS runner for `poll_all` + outbox emission; **flagship top-K interim posts** through the existing rail | nothing (operator arms `MARKETING_FASTLANE_ENABLED`) |
| **B2** | Persona W2 cadence resolver + news accounts/Buffer channels/W1.5 properties → full wire cadence on `mastermind_news` + `news_flash` | operator account creation; W2 build (chartered) |
| **B3** | P1 VPS-direct publish (<90 s) · Tier-X read lane (operator credential + spend guard) · Tier-S speech desk | B1 proven; operator decisions below |

**Operator decisions:** (1) arm B1 + accept interim flagship wire posts; (2) ~~X read credential~~ **DECIDED 2026-07-27: twitterapi.io override (Tier X above) — operator provisions the twitterapi.io key**; official X API demoted to fallback; (3) optional Newsquawk subscription ($199–399/mo) as squawk corroboration; (4) P1 Buffer-creds-on-VPS approval.

**Added kill/health criteria** (inherit appendix §5): mirror death → wire-only fallback, never scraping; STT-sourced precise numbers never post uncorroborated; if wire-account reach collapses vs. its own baseline (visibility-filter signature), the health monitor throttles the lane and rotates templates before any expansion.

---

## 6. Topic expansion — one wire spine, many registers (operator directive, same day)

Operator (2026-07-27, second directive): expand beyond Trump to other high-reach topics — Mag 7, crypto companies (Coinbase/Circle/Robinhood), high-retail-participation + high-short-interest names, exec voices (Jamie Dimon, JPM/Goldman views/outlook), institutional research; engaging, distilled, non-robotic; some posts as **generated image cards** (post text in the image, logo corner mark, no URL) for screen space.

**Ruling: do NOT build per-topic pipelines.** Everything above (§1 sources → deterministic relevance → §3 copy law → card → rail) generalizes; topics are **config registers** in the source-register file, not new code:

- **`registers.people` (exec voices):** rows of person → org → cashtags → salience floor (Dimon/JPM, Solomon/GS, Armstrong/COIN, Tenev/HOOD, Huang/NVDA, Musk, Fed speakers…). Benzinga-class wires (Tier W) already carry "Dimon says…" headlines; earnings-call season amplifies. Trump is simply the first and loudest row of this register.
- **`registers.companies`:** Mag 7; crypto equities (COIN, CRCL, HOOD, MSTR…); a high-retail/high-short-interest rotation set. The rotation set should refresh from **our own engines** where data exists (movers, options flow, darkpool, breadth) rather than a static list.
- **`registers.claims` (bank calls/outlook):** "JPM in-house indicator flashing buy" class items are **hearsay-class** by §3 — ≥2 wires or explicitly attributed phrasing; never re-report a re-report as fact.
- **`registers.topics` (geopolitical; operator third directive):** the `geopolitical` event class already exists in `breaking_relevance`'s taxonomy — arm it with the Iran/Hormuz/CENTCOM-class keyword set. War-adjacent claims are the **highest-corroboration class**: a state-media or single-wire report ("Mehr News citing Iraqi sources") never instant-publishes — ≥2 independent wires or attributed phrasing, tragedy tone rule (no CTA footer), per the D05 traps.

**The differentiator stays our own data.** "Catchy but valuable" = one real number in plain words, not adjectives: tape stamp, short-interest/darkpool/options-flow stat, 52-week context — things relay accounts cannot attach because they don't own engines. This is also what keeps the lane inside "every post carries real value."

**Institutional lane = our research vault, not repurposed sell-side PDFs.** W2R (chartered, #3804) already triages ~150 papers/day (deterministic W-score + haiku veto → flagship/note tiers). Wire-grade nuggets ("what the Street is saying today") route through the same outbox under the press validators (named+linked source, windowed close-paraphrase, fact-anchor). The Zerohedge full-note-republication model is explicitly NOT ours — worse rights posture, and vault-native distillation cross-sells the product instead.

**Image-card wire posts — endorsed, mostly built.** D05 W0 already shipped a breaking-card renderer (`chart_render.py`: headline, source chip + timestamp, ticker mini-strip, brand footer/logo cache). Extend it into a designed **wire-card family**: post text set large in the image, logo corner mark (no site URL per operator), event-class accent colors, light/dark variants. Design choices route to `designer` (Opus, frontend-design skill + house chart config) per the Design lane — a card template is taste-as-surface, not mechanical. Constraints stand: no fabricated imagery, no screenshot-of-source cards, tragedy-class tone rule (no CTA footer). Native images carry no link-suppression penalty, so cards buy screen space at zero reach cost.

**Site surface — "Intelligence Suite" (operator, third directive):** the wire spine's consumer set includes the site itself. A live-wires rail on the Markets News surface (the #3287 revamp already has the hero-led ranked feed + AI-feed connector to extend) reads a `site/live/wires.json` payload published by the VPS poller — same client-side pattern as `wh_banner.json`, so it needs no render-lane dependency and stays minutes-fresh via the VPS. Marketing wire and site news then share ONE spine; chartered as **B4** (surface design via `designer`; glance-tier design law applies — plain-word headlines, technicals demoted).

**Sequencing:** registers ship in **B1** as config alongside the Trump register (same poller tick — zero marginal infra); exec-voice, company, and geopolitical registers day one; vault wire-nuggets after W2R lands; wire-card family after one `designer` pass; news.html live-wires rail as B4. Multi-register volume strengthens (does not bypass) the Persona-W2 cadence-resolver precondition for the news cohort; the interim flagship top-K cap is global across all registers.
