# X Growth — the unified operation (doc-of-record)

**Status:** chartered 2026-07-28 (Fable main loop). This document AMALGAMATES and supersedes-where-overlapping: the Codex editorial constitution (`handoffs/MASTERMINDX_X_GROWTH_GRANDMASTER_HANDOFF.md`, committed verbatim with provenance), the borrowed-distribution growth playbook (operator-pasted research, encoded in §3), the Persona Network masterplan (D13), the Media Network masterplan (D14), the Intelligence Suite masterplan (#3863), and D05 Addendum 2 (Trump wire). Where charters overlap, §6 names the surviving owner. Operator context: 7 Buffer channels live, all accounts ~0 followers; the mandate is real follower growth and impressions feeding organic revenue.

---

## §0 ACCEPTANCE GATES (top of file by law)

Every wave below ships through the full loop (commit → push → PR → adversarial review → CI → same-day squash-merge → live verify) with these gates INLINE in each spawn prompt:

- **XG-W1 (employee desks live):** not done unless all 4 employees are wired in ALL THREE layers the founder precedent uses (`config/marketing.yml` `desk_network` entries + `copywriter.personas` voice notes + `config/personas/` specs — the spec layer alone is decorative: nothing generative reads it at W1), all 7 Buffer channels are bound in `publish.channels` with ids discovered by the buffer-channels workflow, the expression-dial validator rejects a dial-3 fixture and passes the four codex dial-1 examples verbatim, and one dry-run item per employee renders through the copy pipeline with the codex quirk-injection pass ON (built in this wave) and zero AM-R1 violations.
- **XG-W2 (cadence + collision spine):** not done unless the resolver replaces the decorative `-1` live cap with per-account profiles read from persona specs, two accounts drawing the same story produce exactly one emission (one-conversation-one-owner lock, fixture-tested), cross-account near-dup radar covers employee accounts (today's `outbox.near_duplicate()` is same-account only), and BOTH hand-rolled outbox writers (`press_lane._write_outbox_item()` and `fastlane._write_outbox()`) are replaced by the canonical `make_item()`/`validate_item()` path — no raw-file bypass remaining.
- **XG-W3 (desk feeds + franchises):** not done unless each live account has a desk feed producing scheduled + breaking + market-hours + analysis candidates with context packs attached, franchise slots emit on their declared cadence (fixture-clock tested), and every emission carries its Gift–Grip–Proof gate verdict in the item metadata (abstention logged with reason).
- **XG-W4 (reply desk phase 1):** not done unless target discovery runs inside the existing twitterapi.io spend cap with since-id cursors; every draft passes the independent critic pass — near-dup vs parent, dignity/screenshot rubric, satire/sensitivity blocklist, **position-consistency check** (contradiction with the account's recent public position rejects unless the change is explained in-draft), **the persona-label test** (a draft interesting only because of who says it rejects), **the informational-surplus test** (restating the parent rejects), and the **shared copywriter banned-vocab guard**; the reply queue enforces expiry (stale drafts auto-killed); mode dial ships at M0/M1 only with M2/M3 config-gated OFF; **the per-account health monitor + network tripwire (XG-W6) are a hard precondition for ANY dial flip above M1** — failures must be able to halt one account without halting seven; and the M1 desktop runbook + handoff contract are committed.
- **All waves:** no new first-party X scraping (twitterapi.io is the only X read path); "validated" word law; numbers whitelist for LLM copy; GitHub annotations start-of-line; tests wired into a CI lane that installs their imports.

---

## §1 The operation in one view

**Eight properties, one intelligence spine, three output surfaces.**

| Account | Handle | Buffer | Kind | Spec | Editorial identity (constitution §4/§5, adopted) |
|---|---|---|---|---|---|
| Flagship | mastermindx001 | ✅ | branded | `config/personas/flagship.yml` | **Evidence desk** — chart/state-change/receipts; no lifestyle, provenance always |
| Founder | w_chris6031 | ✅ live #3851 | branded | `config/personas/founder.yml` | Founder's own read; first-person, dry, never pitches |
| Mastermind News | mastermindnews1 | ✅ | branded (corporate) | `config/personas/mastermind_news.yml` | Wire + Brief property voice; pairs with mastermindx.ai (Media W1.5, dark pre-cutover) |
| Mastermind Research | *(not created yet)* | — | branded (corporate) | `config/personas/mastermind_research.yml` | Research property voice; pairs with blog.mastermind-x.com; W2R triage upstream; long-form + X Articles |
| Meagan | meagmastermind | ✅ | employee | `config/personas/meagan.yml` (XG-W1) | **Crowd translator** — mood vs money, market psychology |
| Sophia | sophmastermind | ✅ | employee | `config/personas/sophia.yml` (XG-W1) | **Narrative architect** — the story markets believe and when it changes |
| Kelly | mastermindkelly | ✅ | employee | `config/personas/kelly.yml` (XG-W1) | **Mechanism detective** — the missing variable, cross-asset confirmation |
| Cici | mastermindcici | ✅ | employee | `config/personas/cici.yml` (XG-W1) | **Cross-border correspondent** — Asia's read before New York wakes |

Employees are REAL people who also post manually (founder precedent — official rails, no isolation theater, near-dup radar prevents engine/manual collisions). The 9 pseudonymous D13 specs (chart_gremlin, news_flash, receipts, research_a/b/c, theme_desk, zh_navigator, corp_desk, control_v3) stay spec-only; the pseudonymous cohort and its isolation checklist are DEFERRED until the named-account operation proves the machinery (they remain chartered in D13, untouched).

**The spine** is the Intelligence Suite (#3863): sources → scoring brain → pathway router. This charter extends it with per-account **desk feeds** (§4) and the **reply desk** (§5). **Surfaces:** (1) X posts via Buffer, (2) X replies via the reply desk, (3) site properties (news/research/news.html rail) — one content spine feeding all three.

---

## §2 Adjudication of the editorial constitution

The Codex handoff is ADOPTED as the editorial constitution, with these house amendments (where the two disagree, this section wins):

**Adopted wholesale:** Laws 1–10; the four growth loops; the five editorial identities; the six-layer persona model (attention/judgment/taste/position/relationship/language) + three changing states; autobiographical canons and their do-not-invent list (subject to amendment 8 below); per-persona franchises (§12 concepts become the franchise register in XG-W3); **Gift–Grip–Proof as the publish gate, Bridge as a non-blocking virality marker** (the constitution's own formula — Bridge raises option value, it never blocks); informational-surplus, social-object, one-useful-sentence, why-now tests; reply strategy (§9) in full; the anti-sameness discipline (subject to the quirk-budget rule in amendment 2); adaptive cadence doctrine (this IS the cadence resolver's requirements spec); negative-feedback budget; relationship memory with its "do not infer sensitive traits" law; measurement families, north-star, parent-adjusted evaluation, bottleneck table (all as §8 hypotheses, not settled numbers); learning-without-collapse (§16); experiments A–H as the standing experiment backlog (§8 pre-registration law applies); the avoid-list; capability requirements 1–15 (requirement 8's "engagement potential" per amendment 9).

**Amendments (house law wins):**

1. **"No routine human review" is the destination, not the starting state.** Autonomy is EARNED per (account, kind) through the existing approve-ladder (`auto_approve_kinds`), exactly like the ads human gate. The constitution's separation-of-powers critics (§13.1) are the mechanism that earns escalation; hard publication failures (§13.2) are validators, not vibes.
2. **Persona codexes: pinned v1 signatures are FROZEN; the constitution grafts — under a named reconciliation rule.** Intelligence Suite masterplan §5 keeps authority over the language layer (register, quirk whitelists, banned lists, emoji signatures, dial examples). The constitution's cognitive layers (perception, judgment, taste, worldview, franchises, canon, restraint clauses) graft on as codex rev-2 in the XG-W1 specs. The adversarial cross-check (2026-07-28) refuted the naive "no contradictions" reading — the pinned signature quirks (Kelly's numbered micro-lists, Meagan's "okay so —" openers and em-dash asides, Sophia's story-shaped openers) are exactly the repeated-structure tells the constitution's §13.7 anti-sameness discipline hunts. **Reconciliation rule: a whitelisted signature quirk is exempt from the anti-sameness counter only up to a per-quirk frequency cap encoded in the spec** (signature openers ≤1/day and ≤30% of posts over any rolling 7 days; em-dash asides ≤1/post; numbered lists ≤1/day); over-cap emissions reject like banned tokens. Sub-rulings: Sophia's wine/museum canon is taste-context only and NEVER surfaces in copy (her own voice law forbids it; tokens on her banned list); Cici's "Tea and Tickers" is capped ≤1/week (shares the tea lexicon budget); "Before New York Wakes" is classified analysis (dial 1), not news. Where a new conflict emerges, §5-pinned wins.
3. **Expression dial extends to replies.** Wire/news = 0, analysis = 1, charts/watchlist = 2 (unchanged); NEW: `reply` = 2 for employees, 1 for flagship — replies are persona-forward by nature, but the finance-value floor (one useful sentence) binds always.
4. **Falsification formats are X-legal, site rulings untouched.** Kelly's falsification-card and "What Would Prove This Wrong?" franchises are her intellectual method and ship on X. The #3821 ruling (no falsifier/refutation language on site cycle surfaces) is unchanged; "validated" word law and the numbers whitelist apply to every post.
5. **Opinion/forecast ledgers ride the graded machinery.** Public calls log to persona memory (`data/marketing/personas/<id>/theses.jsonl`) and are graded by the existing forward-ledger/scoring core (nightly sole advancer) — a persona never grades itself. "What Changed" posts cite the graded record; receipts posts print losses (our epistemics law is a marketing differentiator — constitution agrees).
6. **One conversation, one owner is a hard lock, not an editorial preference** (XG-W2): cross-account same-story lock at emission time + zero cross-account engagement ever (no mutual likes/reposts/replies — fleet-linkage law).
7. **AM-R1 stands doubly:** no invented trades, meetings, or first-person experience — the engine never speaks as the human beyond the codex register.
8. **The autobiographical canon ships DARK until each employee confirms it (cross-check blocker, 2026-07-28).** The lifestyle textures describe real, identifiable people; an unconfirmed hobby attributed to a real employee is fabricated personal texture — exactly what AM-R1 exists to prevent, and the three pinned AM-R1 patterns cannot detect it. Canon quirk slots ship `enabled: false`; no lifestyle token appears in generated copy until the employee confirms their own texture list (operator lever, §7).
9. **LLM-never-scores extends to EVERY critic, including persona/readability/engagement.** The constitution's separation-of-powers critics may veto and de-escalate only; "engagement potential" and "follow-conversion potential" come from the deterministic scorer's features, never from an LLM judgment; mode-dial escalation evidence is telemetry outcomes, never critic scores.
10. **A crowd-state claim requires a measured input.** Meagan's Mood-vs-Money / crowd-emotion beat has no sanctioned sentiment source until XG-W5 lands (GDELT tone; observed x_follow engagement). Interim form: the "mood" side quotes attributed headlines/posts, never asserts an unmeasured crowd state — the LLM does not originate the crowd reading.
11. **Signal states on X are display-tier.** Flagship "Signal of the Day"-class posts follow the site's display-tier language posture: plain-word stance, "what we're watching" framing, no "validated" (word law), no calibrated-authority claims until a signal passes the gauntlet at promotion. Cross-surface consistency: a flagship post about a cycle read uses the same projection-window language as the site surface (#3821) — the two surfaces never publicly disagree in register.
12. **One vocab guard, every drafter.** Every new copy path (quirk-injection pass, reply drafter, franchise emitters) REUSES the existing copywriter banned-vocab guard — the "validated" word law and hype bans are inherited, never re-implemented, because `check_validated_claims.py` cannot see runtime-generated text.
13. **Persona memory stores respect the nightly-sole-advancer law.** Emission-time counters (phrase fatigue, relationship touches, open promises) accumulate in host/VPS runtime state (same posture as poller cursors — zero repo writes intraday); a nightly consolidator advances the repo ledgers under `data/marketing/personas/<id>/`. The ledger law is unchanged.

---

## §3 Growth doctrine (borrowed distribution, encoded)

Zero-follower accounts own no distribution; every mechanism below borrows someone else's and converts at the profile:

1. **Replies are the primary engine** → §5 reply desk. Targets: mid-tier (10K–100K) authors over megacaps; 5–15 min windows; 15–20/day quality bar, hard ceiling 30/account; every reply carries a gift nobody else in the thread can produce (chart, stat, mechanism) — our chart speed is the structural advantage. Author reply-back is the highest-value outcome; relationship tier > vanity reach.
2. **X Communities** — operator lever: join 2–3 large finance/trading Communities per relevant account; the router marks community-eligible items. (Buffer cannot target Communities; community posting rides the desktop lane or manual posting — flagged, not blocking.)
3. **Cashtag/search moments** — the press/event lane already builds this: flash + chart within minutes of prints, exactly one cashtag, tape stamps as differentiator (FOMC/megacap-earnings weeks are the lab).
4. **Seed followers from owned assets** — operator + small build wave: announce accounts to terminal users and newsletter; follow-CTAs and X timelines on mastermindx.ai, blog, and macro-site footers; handles in every email footer. This converts cold-start to warm-start for every account (XG-W7).
5. **Own a data lane, don't compete on takes** — the differentiated beats: China/HK desk depth (Cici), the graded receipts ledger (flagship — losses printed, category of one), chart speed (all). Megacap takes are seasoning, never the meal.
6. **Profile conversion floor** — per-account profile kit (bio = who it's for + one proof line; pinned = best receipt asset; XG-W1 commits drafts as `docs/x_profiles/<account>.md`); the last-nine-post diagnostic joins the per-account health monitor (XG-W6).
7. **Paid distribution: parked** until profiles convert and a content lane is proven.

---

## §4 Desk feeds — every account knows its day (XG-W3)

Extends the IS-W3 pathway router with a per-account subscription layer. Each live account's desk feed assembles candidates from four lanes:

- **Scheduled** — franchise slots on the cadence resolver's clock (e.g. Cici "Before New York Wakes" pre-open ET daily; Meagan "Mood vs Money"; Kelly "Confirmation Check"; Sophia "The Story the Market Believes"; flagship "What Changed Since Yesterday"). Franchises come from the codex franchise register; slots are windows, not quotas — Law 1 (value before activity) means an empty slot abstains, and abstentions are logged with reasons (§16.5).
- **Breaking** — press_lane candidates routed by beat fit + the one-owner lock; corroboration classes and the copy law (D05 Addendum 2 §3) unchanged.
- **Market-hours** — session posts from our live tape (movers, stamps, divergences) during each account's active session (Cici: Asia; others: US).
- **Analysis** — daily-read derivatives, chart-backed reactions, thread explainers (pathway P3/P4), digest revival.

Every generation call receives: context packs (chronicle, desk organs, live tape), persona memory (opinion ledger, open promises, recent posts, phrase-fatigue counters), and the codex. Every emission carries the Gift–Grip–Proof verdict; Bridge presence marks virality-option items for prime slots.

**Persona memory stores (new, XG-W3):** per account under `data/marketing/personas/<id>/` — `theses.jsonl` (exists), `promises.jsonl` (open loops with due conditions — every promise closed or explicitly released), `phrases.jsonl` (rolling n-gram fatigue counters feeding anti-sameness), `relations.jsonl` (public interaction context per author handle: topics, stage, last contact; nothing sensitive inferred).

---

## §5 The reply desk (XG-W4) — borrowed distribution's engine room

**Split of responsibilities:**

**In-repo (build now; no new operator dependencies):**
- **Target discovery** — `engine/marketing/reply_targets.py`: twitterapi.io polling (existing key, $75/mo cap, since-id cursors) over (a) a committed per-persona **author register** (community maps from the constitution §14.2 seeded by Fable, tiers: relationship / conversion / breakout), (b) mentions of + replies to our posts, (c) high-velocity moments (trends + our own press lane). No first-party scraping, ever.
- **Opportunity scoring** — deterministic: author tier, post age (5–15 min window), velocity, saturation (reply count), beat fit, relationship stage. LLM never scores; scores rank a queue.
- **Drafting** — per-persona codex + reply formula (one gift, one grip, one doorway) + reply-family rotation (constitution §9.4 — a strategy register, not paraphrase variants) + **reply artillery**: pre-rendered charts for the day's trending tickers via the existing chart pipeline so a reply can attach a chart nobody else in the thread has.
- **Independent critics** — separate validator pass: near-dup vs parent and vs our corpus, hard blocklists (satire, sensitive events), fact discipline (numbers only from whitelisted own-feed values), screenshot/dignity rubric (LLM may only de-escalate), portfolio collision (one-owner lock covers replies too).
- **Reply queue** — outbox-pattern two-zone approve flow; new kind `reply`: `{account, target_url, parent_author, parent_excerpt, draft, alt_drafts, chart_path, tier, score, expires_at, mode}`. Expiry enforced (a stale reply is dead — auto-kill past window).
- **Telemetry** — outcome polling (author reply-back, likes, our follower delta) via twitterapi.io own-account reads → parent-adjusted labels (constitution §15.4) into the IS-W5 labels store.

**Load-bearing facts the build is shaped around (verified in-tree 2026-07-28):**
- **Buffer cannot reply** (`social_publisher._CREATE_POST_MUTATION` has no reply target; `wire_format.py:15-18` documents it) — every reply necessarily leaves the sanctioned posting rail; that is the honest reason the desktop lane exists, and why a future official X-API write lane should be able to replace it without rewriting the brain (the split above guarantees that).
- **The standing reply cap is 0** (D08: "default to 0 indefinitely unless the operator explicitly opens it"). The operator's 2026-07-28 directive IS the opening ruling — recorded here: caps open per the mode dial only (M0 = sends stay 0; M1+ raises per-account caps toward 15–20/day, hard 30), never by a builder config edit.
- **The sentinel reply counter is vacuous today** (`sentinel.py` counts `item["type"]=="reply"`; outbox items carry `kind`) — XG-W4 fixes the gate so the cap it enforces is real.
- **twitterapi.io spend is one shared bucket** — reply discovery gets its OWN provider class, cursor namespace, spend sub-budget, and endpoint-shape-aware cost counter (the existing `_count_tweets` only recognizes the `tweets` response key and hardcodes `includeReplies=false` — exactly wrong for a reply desk); the Trump wire must never be starved by reply polling.
- **Charts are EOD-only** (`chart_render` reads nightly parquet) — reply-artillery charts must ride the existing post-time live gate (`live_verify`) or carry an as-of stamp; never present yesterday's bar as live.
- **One-owner extends to reply targets:** two of our accounts never reply to the same thread (the coordination signal no existing gate catches — enforced in the queue, not by convention).

**M1 desktop lane (operator-procured $200 desktop account + 7 browser profiles):** consumes the queue via a local non-repo store the M1 owns — `~/.mastermind/reply_desk/{queue,claims,receipts}/` (the M1 is the nightly render host; an intraday writer inside the render checkout would collide with render-lane resets, and the house law is "pollers make zero repo writes") — with a lease/claim protocol (claim before navigating; expired lease returns the item to queued) and screenshot+URL receipts. Item schema carries BOTH `local_path` and `public_url` for media so a future API rail needs no rewrite. Credentials live only in the browser profiles, never in files we read. Runbook committed at `docs/reply_desk_runbook.md` (XG-W4): per-account browser profiles, session hygiene, activity staggering, never-synchronized windows. Isolation posture: these 7 accounts are openly Mastermind-affiliated (founder + 4 real employees + 2 branded anchors) — the pseudonymous §2 isolation checklist explicitly does not apply; the exposure that remains is reply automation itself plus same-thread coordination, which the dial + the one-owner lock govern.

**Mode dial (per account, config-gated, operator flips each escalation):**
- **M0** draft-only (queue fills, nothing sends) — launch state.
- **M1** assisted: desktop lane sends APPROVED items only (approval in the outbox UI).
- **M2** auto-approve inbound: replies to comments on OUR OWN posts auto-approve within caps (lowest risk, our thread, our audience).
- **M3** auto-approve outbound within daily caps — only after an account has ≥100 M1/M2 sends with zero incidents, passing blind-identity and anti-sameness evals, and an explicit operator flip.

**Halt cadence — a standing M2/M3 precondition (XG-W6, #3916).** The per-account health monitor and network tripwire are built and enforced on both rails, but they evaluate **NIGHTLY ONLY**: every monitor input is daily-cadence telemetry (the Buffer metrics poll refreshes about once a day), so an incident that starts at 10:00 is caught that night, not that hour. At M0/M1 a human is in the loop on every send and a nightly halt is proportionate. **At M2/M3 it is not** — auto-approval means an account can keep sending for a full day after the signal that should have stopped it. **Intraday halt evaluation is therefore a precondition for any dial flip above M1, alongside the monitor itself.** The launch tripwire action is `warn`, not `halt_implicated`, until a real correlation baseline exists (§8).

**Risk register (honest):** X's automation rules require API-based automation; browser-automated posting is outside them, and the fleet-linkage research (one device/IP/behavior signal can chain-suspend all linked accounts; text-similarity clustering since 2026-03) is why the dial exists and why M3 is opt-in per account. Irreducible residuals at M2+: single-machine device/IP correlation across 7 profiles; the mitigation (profile isolation, staggering, per-persona voice divergence, hard caps, zero cross-account engagement) reduces but cannot eliminate it. The queue/critics/telemetry stack is identical at every dial setting — capability is built once; arming is the operator's per-account decision, exactly like the press service and the ads gate.

---

## §6 Wave reconciliation — one build order

*(Reconciled against the four masterplans + census, 2026-07-28. Where a wave appears in two charters, the OWNER column names the surviving home; the other charter's row is absorbed, not rebuilt.)*

| # | Wave | Contents | Absorbs / supersedes | Lane |
|---|---|---|---|---|
| XG-W1 | Employee desks live | 4 employee specs (codex rev-2 = §5-pinned signatures + constitution cognitive layers), desk_network + copywriter.personas + spec wiring (three layers, founder precedent), all-7 Buffer channel binding, codex quirk-injection pass, expression-dial validator (+reply level), profile kits | IS-W4 (in full) | Opus `builder`; codexes frozen |
| XG-W2 | Cadence + collision spine | cadence resolver (per-account profiles from specs; adaptive-cadence doctrine §13.8 as spec), **per-account wire routing** (press_lane hardcodes `_ACCOUNT="flagship"` at line 46 — uncharted gap, the wire lane cannot address the other 6 channels today), one-owner lock, cross-account near-dup, outbox KINDS hardening (`wire`/`breaking` admitted via make_item; both hand-rolled writers replaced) | Persona W2a (resolver slice) + IS-W1 hardening slice | Opus `builder` |
| XG-W3 | Desk feeds + franchises | per-account feed assembly, franchise register + scheduler, persona memory stores (promises/phrases/relations), Gift–Grip–Proof gate, market-hours lane | IS-W3 extension (router stays IS-W3's) | Opus `builder` |
| XG-W4 | Reply desk phase 1 | targets + scorer + drafter + critics + queue + admin UI + telemetry + M1 runbook; M0/M1 only | NEW (this charter) | Opus `builder`; register seeded by Fable |
| XG-W5 | Scoring brain | L0/L1 + golden set + eval harness; L2 after labels | IS-W2 (unchanged, renumbered) | Opus `builder` + `reviewer` |
| XG-W6 | Telemetry + learning | **SHIPPED (#3916)** — IS-W5 labels loop (`engine/marketing/labels.py`, four named consumers, nightly-sole-advancer) + parent-adjusted reply labels (3 covariates, expansion encoded as config) + blind-identity eval **pre-registered, NOT run** (`docs/blind_identity_eval_prereg.md`) + per-account health monitor + network tripwire (`engine/marketing/health_monitor.py`, launch action = **warn**) + last-nine-post diagnostic + the reply-desk **producer** XG-W4 left unbuilt + learned-rule version log with an enforced rollback path. ALL feedback-loop charters converge here (D05 §7 loop ≡ IS-W5 ≡ Persona W4 report card ≡ Media W2 scorecards — one loop, four consumers) | IS-W5 + Persona W2b/W4 + Media W2 measurement slice | Opus `builder` |
| XG-W7 | Surfaces + seeding | IS-W6 (news.html rail via `designer`, zh, tier gate, terminal feed) + follow-CTA sweep on site properties + email-footer handles | IS-W6 (in full) | `designer` + builder |
| XG-W8 | Research property lane | W2R triage build (`engine/press/research_triage.py`, masterplan D14 §5b) → blog posts + short-form + X Articles for the research account (when operator creates it) | Media W2R (in full) | Opus `builder` |

**Standing, not renumbered:** press cutover PR (blocks on operator DNS — runbook step 2); PRESS-FEEDS arming (`systemctl enable --now marketing-press-feeds` + `MARKETING_FASTLANE_ENABLED=1`); D13 pseudonymous cohort + isolation (deferred, unchanged — Persona W3 goes LAST, after the health monitor and a real traction baseline); Chronicle/Media property waves not named here (unchanged in D14).

**Reconciliation rulings (2026-07-28):**
- **Chronicle W2 is a false blocker on the cadence resolver.** The Persona masterplan gates all of W2 on Chronicle W2; only the copywriter *context-injection* slice actually needs it. The resolver (XG-W2) proceeds now; context injection waits for Chronicle W1/W2 and lands in XG-W3.
- **The "6 official desk accounts" premise in the older docs is stale.** Only flagship + founder exist among the D13 desks; receipts/theme_desk/research_a/b/c are phantoms (`enabled: false`, no handles) NOT filled by the 7 new channels — the new channels are a different identity set (4 employees + news). No wave may count phantom desks as install targets.
- **Media W2R's W-score reuses IS-W2 components** (L1 features, garbage gate) rather than growing a parallel scorer — one scoring brain, two consumers (XG-W5 feeds XG-W8).
- **All 7 Buffer channel ids are discovered** (buffer-channels run 30327218626): mastermindx001 `6a61f3d5e2638b94d7bd6c9b`, w_chris6031 `6a67dd714b2d03035f4f9659`, meagmastermind `6a681b5e4b2d03035f52d4fc`, sophmastermind `6a6810824b2d03035f52ac24`, mastermindkelly `6a681b4d4b2d03035f52d3ec`, mastermindcici `6a6822f94b2d03035f5312a5`, mastermindnews1 `6a6823a74b2d03035f53147b`.

**Order rationale:** W1→W2 are the posting-precondition pair (specs without cadence resolver leaves news kinds blocked; resolver without specs has nothing to resolve). W3 makes accounts worth following; W4 makes people find them; W5–W6 make the system learn; W7–W8 widen the funnel. W4 may start in parallel with W3 (disjoint files) once W1–W2 merge.

---

## §7 Operator levers (this charter adds none that block engines)

1. Create the **Mastermind Research** X account + Buffer channel (XG-W8's posting surface).
2. **Join Communities** (2–3 large finance/trading) from flagship + relevant accounts when convenient.
3. **Seed announcement** to terminal users/newsletter once XG-W1 profile kits are applied (bios + pins are drafted for you).
4. **M1 desktop account**: procure the $200 desktop Claude/ChatGPT seat + set up 7 browser profiles per the runbook (XG-W4 commits it); reply desk runs M0 (draft-only) until then.
5. **Employee canon confirmation** (amendment 8): each employee confirms (or edits) their lifestyle texture list before their canon quirks arm — a 5-minute ask per person.
6. Standing from prior charters: DNS for the press properties; golden-set labeling session; NewsAPI.ai $90/mo call; press-feeds arming flips.

---

## §8 Assumptions requiring validation + configurable thresholds (cross-check addition, 2026-07-28)

The constitution's §20 closing instruction — suggested weights, cadences, and thresholds are hypotheses to calibrate, never fixed truth — binds this charter too. Everything below ships as a **config key with a pre-registered evaluation plan**, not a constant:

**Assumptions register (validate with our own telemetry before treating as fact):**
- The borrowed-distribution reply numbers (5–15 min windows; 15–20/day quality bar; mid-tier > megacap targeting; author reply-back value) come from an uncontrolled tracked cohort — directionally credible, survivorship-prone. Encode as initial config values; the parent-adjusted evaluation grades them once ≥ launch-scale samples exist.
- The four growth loops descend from two single-account case studies (Phantom Flow, Stock Mom) the constitution's own evidence list does not include — treat as design priors, not measured mechanics.
- Author-tier scorer weights are hypotheses (the constitution says so itself) — the scorer's `_components` stay inspectable and re-weightable; no tier weight is load-bearing until telemetry ranks it.
- The ≥80% blind-identity target is a point estimate with no n or CI, judged on samples from the generator it polices — pre-register the eval (sample size, holdout construction, chance = 20% baseline) in XG-W6 before the number gates anything. **DONE (#3916): `docs/blind_identity_eval_prereg.md` + `engine/marketing/blind_identity.py::PREREG`** — n=150 (30 × 5), chance 0.20, Wilson intervals with Bonferroni (z=2.638) on the per-persona family, a ≥20-answered floor per identity, and the rater-is-a-sibling-model confound declared in advance. **Status `not_run`; `GATES_NOTHING = True`, grep-enforced.** The ≥80% figure still authorises nothing, and promoting it to a gate is a separate decision with its own record.
- The north-star metric (qualified retained followers per 100 contributions) is undefined-at-zero — during cold start, use the simple bottleneck table (§15.7) on raw counts; the north-star activates only when accounts clear a follower floor set in config.
- The 8-covariate parent-adjusted evaluation is over-parameterized at launch volumes — start with 2–3 covariates (parent size, post age, market intensity), expand with sample size.

**Experiment law:** experiments A–H run under house stats law — pre-registered gates, declared sample sizes, multiplicity correction across concurrent arms, nulls printed. No learning promotes from one viral accident (constitution §16.3 evidence standard, now with teeth).

**Reversibility:** learned rules (format preferences, timing, reply families) are versioned config entries with a rollback path — XG-W6 ships the version log alongside the scorecards; a rule that cannot be reverted may not be learned.
