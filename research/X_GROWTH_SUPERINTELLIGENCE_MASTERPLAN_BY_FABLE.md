# X Growth Superintelligence — unified masterplan (by Fable, 2026-07-31)

Supersedes nothing; unifies: `X_GROWTH_UNIFIED_OPERATION`, Hot Tape program, Content
Studio LLM-first overhaul, E-waves, marketing cadence program. Those stay as build
history; THIS doc is the operating charter for the X Growth suite going forward.

Operator mandate (2026-07-31, verbatim intent): one-pass complete audit + upgrade of the
X Growth layers (not SEO/Ads) into an autonomous superintelligent news suite — high
quality, low latency, multi-account with real persona depth, expandable to other
platforms. Standing laws that bind every lane in this doc: **every ticker post carries a
chart**; **voice = a concrete fact + a reaction that costs the author**; **no stale
market facts** (evergreen/education may lag 1–2 days, nothing else may); **wire accounts
relay, never editorialize** (charter); **LLMs never originate signals or scores** (A7 —
they dress facts the engines computed).

---

## §0 ACCEPTANCE GATES (binding on every build lane in this plan)

A wave is NOT DONE unless:

1. **Payload gate**: no post ships whose text carries zero concrete payload (a number,
   a level, a named comparison, or a dated precedent). A hook with no fact is a build
   failure, not a style choice. Enforced in code (post-time gate), not in prompts only.
2. **Number-sanity gate**: every level/target in a post must be coherent with the
   quoted price (swing targets within a plausible band; no +50% "then 228" salads).
   Enforced in code against the fact packet the post was written from.
3. **Liveness gate**: an item whose `scheduled_at` has passed by more than its kind's
   TTL is auto-quarantined by the sweep, never posted late. "today/right now" language
   requires post-time tape verification (exists) AND a TTL (new).
4. **Chart law**: ticker posts carry hosted media at post time. A kind that cannot
   attach media does not ship cashtags. No deferral limbo past TTL (auto-quarantine
   with a loud tally).
5. **Variety proof**: a full nightly slate contains ≥4 distinct kinds across ≥3
   accounts, and mover/theme (what's-moving-today) posts render illustrated cards
   again. Proven by a live slate, not by code review.
6. **Distinct-voice proof**: given 10 shuffled posts from 3 personas, the persona is
   identifiable ≥7/10 by a blind LLM judge using the voice cards. Proven per release.
7. **No self-merge of flagship UI/copy changes by child agents** — commissioning
   session reviews (spawn-handoff law).
8. Ship loop: commit → push → PR → merge-on-green → live verification of the next
   real slate.

---

## §1 Current-state verdict (11-lane audit, 2026-07-31 — 63 defects)

One sentence: **the machine's parts are individually plausible and the LANES BETWEEN
THEM are broken — content is generated and silently discarded, gates fight the prompts
that feed them, and the approval path the whole design assumes has never been used.**

The eight systemic findings (full per-lane evidence in the audit workflow record):

1. **Supply is dark by wiring, not by weakness.**
   - The nightly Movers/Attention Desk has NEVER emitted one post: items are minted
     `slot=MOVER-nn/THEME-nn` (content_studio.py:3311/:3346) and the outbox emitter
     accepts only `D1-*` slots via a bare `continue` with NO counter
     (outbox.py:1861) — 12 straight nights of mover/theme posts generated, sentinel-
     passed, and invisibly discarded. This alone is the operator's "what's moving
     today posts are gone".
   - The publish-time mover lane is text-only by construction while the bare-cashtag
     law (correctly) refuses naked ticker rollups → structurally unpublishable; its
     day-cap bug limits it to 2 posts/day network-wide; its freshness anchor
     (sp500_heatmap.asof, systematically 1 day stale) fails the tape gate closed on
     every sweep.
   - DeepSeek's thinking-block ate 914/915 planned posts on 07-31 (fix 159537bcfe
     landed 39 min AFTER that nightly; first live test = the 08-01 nightly). No
     circuit breaker distinguishes "model rejected this post" from "provider returned
     nothing 915 times"; two consecutive dark days shipped through green runs.
   - Most hot-tape breaking volume routes to `mastermind_news` — a DARK account —
     because hot_tape bypasses wire_routing's liveness fallback (19 items died at
     dispatch on 07-31 alone).
   - The earnings wire has never run (armed only hours ago); `receipt` kind funds 8%
     of every tilt and is structurally famished (resolution window bug).
2. **Planned kinds have NO approval path.** `decisions.jsonl` (the designed
   operator-approve flow) has zero rows in the repo's entire history; every planned
   post that ever went live was hand-transitioned by an agent session. The suite was
   built around a human gate nobody staffs — the single deepest reason "nothing goes
   out unless an agent babysits it".
3. **The writer fights its own gates.** The system prompt PRESCRIBES phrases the
   validator BANS ("size appropriately"); shape contracts demand 3–6 numbers while
   the number budget caps at 2 (number salad by construction); 11 payload keys
   (persona codex, franchise, lead_with, example_lines, win_rate…) are sent and never
   explained to the model; persona voice is ~180 tokens vs ~4,400 tokens of
   account-invariant law that CONTRADICTS the cards ("No puns" vs a pun-quirk
   persona) — so all accounts sound identical and 27% of posts end on one of nine
   welded pool tails.
4. **Arithmetic and attribution failures shipped live**: a fabricated "White House,
   minutes ago:" dateline on a MarketWatch Fed story (wire_voice maps the 'markets'
   register onto TRUMP openers); mixed-as-of sentences false on their own two numbers;
   "231 of 231" saturated denominators; "first since Jul 2026" degenerate lookbacks;
   invented targets ("then 228" where the source carries only T1 189.63); hot-tape
   dollar aggregates that shrink while the median grows; "just broke below $325" hours
   after the level fell.
5. **State is misread everywhere**: items.jsonl's `status` field freezes at write
   time; 69 ledger transitions declare a `from` that never matched; a double-publish
   fired and an auto-approver reverted a quarantine; the Buffer-429 retry (added
   07-31) calls an ILLEGAL posting→approved transition with an unchecked return —
   stuck-in-posting is still the outcome it was built to prevent. Wire items have no
   reaper (the AMZN/COIN "right now" movers stalled queued 8h with zero ledger rows).
6. **XG-W3's persona depth is inert in production**: publisher writes persona memory
   to a gitignored spool on the EPHEMERAL ubuntu runner; consolidation runs on the
   Mac Studio and has never seen one row. Franchise register exists and
   content_studio never reads it. Two unreconciled persona-voice sources (spec YAMLs
   vs marketing.yml prose) — the LLM reads the older one.
7. **The learning loop is decoration**: learned_rules has no proposer (dead code), no
   kind-mix rule type (the exact dimension that failed on 07-31), follower counts are
   never captured anywhere (the charter's north star is unmeasurable), x_intel
   harvests 0 rows/day, and the exemplar store is config-pinned off.
8. **The reply system is complete and disconnected**: producer never invoked
   (service runs `--lane press` only), target register is 100% disabled placeholders,
   all accounts at M0 draft-only, and the send path is by design a manual desktop
   browser session per reply (Buffer cannot post replies).

Queue hygiene as of this audit: 16 pending items adjudicated, all 16 quarantined
(stale schedules, dead facts, zero-payload education, number salads, two 8h-stalled
"right now" movers), `actor=fable-audit` with per-item reasons in the ledger.

## §2 Target architecture — the superintelligent news suite

The suite is five engines around one queue, with the LLM as a *voice*, never a source:

```
   FACTS                 EDITORIAL                  DELIVERY
   engines (site) ──► fact packets ──► writer (LLM, persona voice)
   hot tape P1                          │ N candidates
   press wire                           ▼
   earnings/filings              judge + hard gates      ──►  outbox ──► publisher ──► X
   China desk                    (payload, number-sanity,      │ TTL, chart law,
   receipts/calibration           dedup, voice, liveness)      │ tape re-verify
                                                               ▼
                                                        metrics poll ──► learning loop
                                                        (engagement, follows) ──► shape/
                                                         timing/persona priors (closed)
```

Non-negotiable properties:
- **Latency budget by lane**: hot tape fact→posted ≤ 10 min during RTH; press wire
  ≤ 15 min; nightly plan slots post within ±15 min of schedule; anything that misses
  its window dies loudly (quarantine + tally), it never posts late.
- **Every fact packet is engine-computed** (prices, levels, ranks, precedents). The
  writer may drop facts, never add them. The number-sanity gate re-checks the text
  against the packet.
- **Candidates + judge, not single-shot**: each slot generates 2–3 candidates (cheap
  models are fine for drafts), a judge selects/rejects with named reasons; rejects
  feed the golden set as negative exemplars.
- **The queue is not a warehouse**: TTL per kind (breaking 2h, mover/theme 6h,
  watchlist/chart 36h against a re-verified tape, education/evergreen 72h). Expiry is
  automatic and loud.

## §3 Persona architecture (the grand strategy, formalized)

The operator's field result: team-member accounts (real profile, real woman, hybrid
authored) reach 1,000 followers far faster than the flagship. The asset being monetized
is *scarcity* — genuinely intelligent, finance-obsessed, personable women are rare on
fintwit; the persona that is both is magnetic to the (mostly male) finance audience.
The bar that makes it work is **indistinguishability**: one bot-tell burns the account.

Architecture:

1. **Voice cards, not adjectives** — the spec layer EXISTS (config/personas/<id>.yml:
   voice_codex with register, quirk whitelists with per-post/day/7d caps, dial
   profiles, session cadence read by cadence_resolver — XG-W1/W2). What's broken is
   delivery: the LLM reads the OLDER marketing.yml prose block, the card arrives as
   ~180 tokens against ~4,400 tokens of generic law that contradicts it, and
   example corpora are truncated to 2 lines (W1c + W2c fix delivery). Each card
   still needs its 6–10 operator-blessed example tweets — that corpus is the one
   thing code cannot invent.
2. **Continuity memory is the anti-bot-tell** (`persona_memory.py` — BUILT, but
   production-inert: the publisher spools memory on the ephemeral runner and the
   consolidator on the Mac Studio has never seen a row; W2a heals the spool path):
   humans reference their own past. Every persona post can cite her own earlier call
   ("still not touching AVNT — said 37.1 was my trigger Tuesday, we never got it").
   Callbacks double as receipts. No bot farm does this; it is our cheapest
   authenticity moat.
3. **Day rhythms with jitter**: schedule per persona follows a human day (pre-open
   look, midday reaction, close wrap, evening quirk), with minute-level jitter and
   occasional missed slots. Perfect cadence is a tell; the plan builder gets a
   controlled sloppiness parameter.
4. **Lifestyle-fusion formats** (the quirk lane — new kind `life`): grounded in a real
   number from our engines, dressed in her life. Formats, not templates: the coffee
   CPI bit, the gym/market parallel, "girl math vs my actual math" on a real stat,
   weekend reading with one chart. Cap 1/day/persona, never market-hours prime slots.
   The engine supplies the FACT; the persona supplies the metaphor. Zero pure-fluff
   posts — the fusion is the brand (hot AND right).
5. **Ensemble choreography, sparse**: personas may disagree with each other and QT the
   flagship with their own spin — 1–2 interactions/day across the whole fleet, never
   simultaneous, never uniform. (X coordinated-behavior detection: interaction must
   stay sparse, opinionated, and asymmetric. No engagement rings.)
6. **The girls stay in the loop**: real selfies/lifestyle posts from the humans are
   the trust anchor; the suite's job is to keep the account alive and smart between
   them. Approval UX (Factory Floor) must make daily human skim ≤ 2 minutes.

## §4 Distribution mechanics + guerrilla playbook (beyond more accounts)

Ranked by leverage-per-build-hour, with the psychological arbitrage named:

1. **Mention-driven on-demand analysis** (flagship + personas): "reply with a ticker,
   I'll run it" — the reply system pointed at OUR OWN mentions first. Each answer is a
   personality-codex/chart card from the product: free personalized analysis (people
   crave it), guaranteed-engagement (they asked), and a product demo in one. Safest
   possible use of the reply lane (no cold outreach), infinitely scalable, and the
   request stream is free market research. *Arbitrage: everyone wants their ticker
   read; nobody serves it on demand.*
2. **Receipts engine as content**: weekly self-graded scorecard per account — wins AND
   losses, machine-honest, signature visual. Humans can't sustain posting losses; we
   can. Trust compounds into follows. (Calibration infra already exists — this is a
   renderer + a format.) *Arbitrage: accountability is the scarcest good on fintwit.*
3. **Scheduled-event domination**: CPI/FOMC/mega-cap earnings are pre-scheduled
   attention supernovas. Pre-build scenario matrices (A/B/C posts + charts drafted
   before the print), publish the matching branch within seconds. We win on
   infrastructure, not wit. *Arbitrage: the first coherent chart after a print owns
   the cashtag page for an hour.*
4. **Quote-tweet judo**: QT big-account vague claims with the chart that tests the
   claim (agree OR refute — costs us something either way; voice law native). QTs
   distribute to both audiences; a data-backed public test is memorable. Target feed
   comes from x_intel harvesting; drafts through the reply-craft gates.
5. **Time-zone arbitrage — "While You Slept"**: branded 13:00Z daily format (overnight
   futures, Asia/Europe moves, China desk read — engines nobody else has) + China-open
   coverage at 01:30Z. Owns the morning scroll slot with zero competition for the
   China leg. Bilingual later (ZH US-market content for the diaspora audience).
6. **Franchise formats with names** — PARTIALLY BUILT (XG-W3,
   engine/marketing/franchises.py: Cici's "Before New York Wakes" IS the
   while-you-slept slot; Kelly's "Confirmation Check"; flagship's "What Changed Since
   Yesterday"; "Tea and Tickers" as the lighter format). The register exists with
   windows, caps, and an abstention taxonomy — and content_studio never reads it
   (W2b arms it). New franchises to ADD to the register once armed: "The 4:05"
   (close wrap, five charts, 4:05pm ET sharp) and "Receipts Friday" (§4.2). Named
   formats create appointment viewing and convert template-pressure from a bot-tell
   into a brand.
7. **Follower-graph seeding (first-1,000 protocol)**: for each new persona, 90 days of
   genuine replies to mid-size accounts (1k–50k) in her beat, ranked by reply-back
   probability (reply_discovery already scores targets). Mid-size accounts follow
   back; mega accounts don't. Content grows accounts that already have followers;
   replies grow accounts from zero.
8. **Crowd-number formats**: "my line in the sand on NVDA is 165 — what's yours?"
   (people love giving numbers), next day the engine grades the crowd vs the tape.
   First-30-min reply velocity is the algorithmic unlock; asking for a number is the
   cheapest honest velocity there is.
9. **Contrarian-moment sniping**: engines detect washout/euphoria extremes; personas
   post the calm data-backed read AT the extreme, pre-registered into the receipts
   engine. High variance, legend-making when right, honestly graded when wrong.
10. **Platform mirrors, sequenced**: Stocktwits first (API-trivial, fintwit-native,
    mirror ticker posts at zero marginal content cost), LinkedIn for macro/education
    long-form, IG/TikTok only after a chart-video pipeline exists. Affiliate program
    stays HELD until user traction + beta deployment (operator 2026-07-31).

Safety rails binding all of the above: X automation policy respected (no engagement
rings, no simultaneous cross-account patterns, sparse choreography only); financial
content stays "what we're watching", never personalized advice; competitor names
debranded; wire accounts never take stances; rate budgets per account enforced in the
publisher, not in prompts.

## §5 Build waves (defect-driven; each spawned lane carries INLINE gates)

**W1 — supply restoration + quality gates + state integrity (BUILT 2026-07-31, this
session, 7 opus builder lanes + follow-on):**
- W1a nightly-emit: mover/theme re-slot into the D1 ladder; counted
  `skipped_slot_mismatch`; movers folded into plan summary; reach-chart budget ordered
  movers-before-confluence (confluence cannot ship; it was eating all 8 cards).
- W1b publish-time movers: watchlist/mover cards rendered + R2-hosted inside the lane
  (chartless → not enqueued, tallied); day-cap bug fixed (status-filtered); freshness
  anchored to the artifact the rows came from, no "today" claims on stale asof;
  stance-bearing direction-consistent tails.
- W1c writer-prompt surgery: prescribed-vs-banned contradiction removed; per-shape
  number budgets agreeing with shape contracts; payload contract section (every key
  explained, lead_with binding, open_promises callbacks encouraged); persona card into
  the system prompt with quirk whitelist outranking generic bans; invented_level
  validator (targets only from the fact packet); welded-tail mechanism killed +
  repeated-closer validator.
- W1d wire integrity: attribution openers only on true-provenance items (the
  fabricated "White House, minutes ago" class is dead); press_lane rasters + hosts its
  cards; hot-tape prompt states every validator law + one repair turn; violations
  telemetry keeps the strings.
- W1e publisher state: Buffer-429 retry via legal edges with checked returns; wire
  reaper (TTL by kind, expired_stale_wire); _bare_cashtag_post kind-scoped;
  item['status'] reads routed through the ledger fold; hot-tape account routing
  through wire_routing liveness fallback.
- W1f hot-tape data: "just broke" requires a fresh first-cross; dollar aggregates pin
  their cap base or drop the claim; group counts carry a universe; media_render
  telemetry restored.
- W1g facts + legacy: degenerate "first since" suppressed (<60td) and placeholder
  killed; vacuous 231-of-231 denominators dropped; intraday/close basis coherence;
  weekend_levels idempotence + v2 writer; claude_rewrite supersedes instead of
  appending; scheduled_at >= created_at floor.
- W1h approval desk (follow-on batch, same session): the standing operator
  authorization codified — a machine audit-approve step for planned kinds
  (payload gate, number-sanity vs fact packet, liveness TTL, chart law, banned-language
  re-check) that transitions queued→approved with a full audit note or quarantines
  with the named failure; replaces the never-used decisions.jsonl human gate as the
  default path while the admin UI keeps veto power. Conservative: anything
  unverifiable stays queued for the human.
- W1i provider resilience (follow-on batch): generic thinking-block guard (any
  provider), circuit breaker distinguishing editorial drops from provider outages
  (>50% provider-stage drops → one retry pass against the next provider on the
  ladder, then a loud ::error), so a single provider fault can never again silently
  delete a whole day.

**W2 — persona depth + loop closure (next session(s); specs pinned here):**
- W2a persona memory heals: the publisher's host spool must survive the ephemeral
  runner — write the spool under the tracked outbox commit the publisher already
  pushes (or consolidate runner-side pre-push); consolidation then reads repo state.
  Not done unless a posted item's persona-memory row survives to the next nightly's
  consolidation on a different machine.
- W2b franchise arming: content_studio reads franchises.open_slots() during plan
  build; franchise id rides item metadata; abstentions recorded. Cici's "Before New
  York Wakes" and the flagship's "What Changed Since Yesterday" become real scheduled
  surfaces. (No new kinds — charter §4.)
- W2c voice-source unification: the W2 migration personas.py's docstring promised —
  copywriter reads the spec YAMLs (voice_codex + example corpus), marketing.yml prose
  block deleted with a no-orphan test.
- W2d lifestyle-fusion lane: `life` register posts (fact-grounded quirk formats,
  §3.4) for employee personas, capped 1/day, using the franchise mechanism — needs
  operator sign-off on formats per account before arming.
- W2e follower telemetry: a snapshot writer for account follower counts (Buffer
  profile endpoint or twitterapi.io), FOLLOWERS_OBSERVED_KEY populated, north-star
  computable; kind_mix added to learned_rules.KINDS with a proposer script reading
  the scorecard (evidence floor n=30 stands).
- W2f x_intel heal + exemplar activation: fix the 0-rows-per-day harvest, then flip
  intel.exemplar_store.active_version through its designed manual gate.
- W2g reply arming, draft-tier: populate config/reply_targets.yml with a real
  allowlist (operator supplies/blesses handles), run the daemon `--lane all` on the
  VPS service, keep M0 (drafts only) until the manual send workflow has been
  exercised once end-to-end; mention-driven on-demand analysis (§4.1) becomes the
  first M1 candidate because it answers OUR mentions only.
- W2h press-wire cadence: the session-poller pattern hot-tape got (GitHub cron
  starvation measured at ~104-min mean gaps vs 5-min requested).

**W3 — distribution mechanics (masterplan §4, sequenced):** receipts engine renderer
+ weekly format; scheduled-event scenario matrices; QT-judo lane through reply-craft
gates; Stocktwits mirror; crowd-number formats. Each is its own adjudicated build
with pre-registered engagement measurement.

## §6 Measurement — the loop must close

- Per-post: impressions, likes, replies, follows-attributed (metrics poll), graded
  nightly; per-account: follower curve vs posting mix.
- The learning nightly converts labels into *priors the plan builder actually reads*
  (shape mix, timing, kind weights per account). A written label no generator reads is
  decoration (standing law: the loop is closed or it is theater).
- Kill-switches stay: MARKETING_PUBLISH_ENABLED is the master arm; per-account pause
  via account_overrides.

## §7 Field-study findings (2026-07-31 twitterapi.io study; full doc:
`research/agentic_media/X_VOICE_FIELD_STUDY_2026_07_BY_FABLE.md`)

1,219 posts harvested across five archetype lanes (wire, technical, macro,
female-finance persona, reply mechanics); all lift claims are WITHIN-ACCOUNT paired
deltas (cross-account raw gaps are account-mix artifacts and were discarded).
Measured laws to encode as generation-time gates (W1c follow-up work):

- **M1 length plateau**: 120–300 chars wins (Δ+0.28, 14/20 handles); <100 chars is
  the worst bucket on the board. Gate: reject <110 or >320, target 140–260.
- **M2 structure**: 2–3 line posts beat one-liners AND walls (Δ+0.20, 7/8).
- **M3 body links are the largest measured penalty** (Δ−0.41, positive on only 2/7
  handles). Ruling: CTA-with-URL becomes KIND-SCOPED — conversion kinds
  (watchlist/theme_list/receipt/education) keep the link, presence kinds
  (signal/chart/macro/mover/event/breaking) never carry one; the profile carries
  the funnel. (Exposure lives in the CTA/ramp machinery — tag_text only rewrites,
  never inserts.)
- **M4 cashtags**: exactly 1–2 for single-name kinds (Δ+0.18, 5/5); 3+ only lawful
  on theme_list (buys raw reach, loses rate — a list-post shape, not a signal).
- **M5 number density**: 3–5 numbers per post is the optimum (Δ+0.14, 8/11);
  6–10 underperforms. Coheres with the per-shape budgets: the salad defect was
  numbers WITHOUT narrative logic, not the count alone.
- **Honest nulls**: hook-carries-the-number is register-conditional (9/18 — enable
  for flagship/kelly/wire, don't enforce globally); reply timing windows are
  UNMEASURED (the harvest captured the late tail, not winners — do not encode);
  day/hour schedules unmeasurable from a 3-day snapshot.

Charter-conflict adjudications (Fable, 2026-07-31):
- **F6 — ALL-CAPS wire headlines** (measured top form, banned by
  mastermind_news charter): CHARTER WINS. The siren-caps costume is the commodity
  wire aesthetic; we take the substance (front-loaded label compression) in
  sentence case. Ban stands.
- **F7 — lifestyle garnish on employee personas**: CHARTER WINS and the data
  agrees. All four lifestyle canons stay DARK pending each employee's own
  confirmation (AM-R1: no unverified personal texture on real names; "fabricated
  personal experience" is banned per spec). The shippable form of personality is
  the REACTION WORD + UNHEDGED VERDICT on a real number — the lane's single best
  post (×25.2 account median) was exactly that shape with zero biography. §3.4's
  lifestyle-fusion lane and W2d are re-scoped accordingly: reaction-forward voice
  NOW; lifestyle texture only after employee sign-off, and then only their own.
- The 56 distilled per-persona example lines are CANDIDATES for the spec YMLs'
  example corpora — the language layer is provenance-frozen, so wiring them in
  needs an operator blessing (W2c ships the delivery mechanism regardless).

---

## §8 W4 — VOLUME RESTORATION (adjudicated by Fable, 2026-08-02)

Operator complaint (2026-08-02): "We're not getting any posts out today. Only one post
went out on flagship 17 hours ago… the several girl accounts are posting nothing.
Mastermind News account is posting nothing."

### §8.0 ACCEPTANCE GATES (binding — a lane is NOT DONE without these)

1. **≥3 posts/day/account** for flagship, founder, meagan, sophia, kelly — measured
   over a simulated week AND proven on one real nightly + its sweeps. Report actual
   numbers per account, never an assertion that it should work.
2. **ZERO quality-gate weakening.** No threshold relaxed, no check disabled, no gate
   bypassed to hit volume. Prove it: the approval desk's verdict distribution and each
   validator's rejection reasons, before vs after. A *volume cap* (top-K, slot count,
   forward-day count) is NOT a quality gate and may be changed on evidence; a
   *threshold* (salience, near-dup Jaccard, number budget, payload, tape freshness) is,
   and may not.
3. Every account expected to post HAS posted in live verification, or is named in plain
   words with the reason it did not.
4. Every fix ships a test that FAILS on pre-fix code. Mutation-check the load-bearing
   ones and report which mutation caught which test.
5. `pytest tests/ -k marketing` green.

### §8.1 MEASURED DIAGNOSIS (7-lane census, 2026-08-02 — all numbers from
`outbox.fold_state`, never the frozen `items.jsonl.status`)

All-time outbox: **posted 58 (23%), quarantined 188 (74%)** of 253 items.
Network emitted/day: 07-30→15, 07-31→0, 08-01→6 then 3, 08-02→4.
7-day posted per account: flagship 22, founder 6, sophia 5, cici 5, meagan 3,
**kelly 0 (never posted once, ever)**, mastermind_news 0.

**V1 — The nightly ladder discards 97% of what it plans, and starves the one day that
ships.** `plan_account(n_days=7, per_day=28)` (content_studio.py:2735) books a 7-day
forward ladder; `emit_from_content_plan` takes only `D1-` (outbox.py:2199). Nothing
reads a previous plan — tomorrow regenerates the whole week — so D2–D7 are discarded by
construction (the code says so at outbox.py:2205). Tonight: 154 planned, **5 on D1**,
flagship 0 and sophia 0.
The imbalance is NOT random. At content_studio.py:2170-2179 the cross-day cooldown pool
is applied **only** to `emit_day_prefix` slots; D2–D7 draw from the full uncooled pool.
When the cooled pool empties, the D1 slot is dropped entirely while the never-published
days fill. D1 runs ~5x under the other days. The stated rationale ("cooling D2-D7 would
delete posts nothing was going to send") is exactly inverted in effect.

**V2 — The planner spends an account's only at-bat on a format that account is banned
from using.** Kelly's sole D1 item on 08-02 was a `theme_list`; `sentinel.ramp.
weeks_1_2.theme_list_allowed: false` kills it at plan-build. The per-account tilt is
never intersected with the ramp tier's permitted formats before slot assignment.

**V3 — The largest volume sink in the planner has a counter that goes nowhere.**
`report["dropped_cooldown"]` (content_studio.py:2177) is written into a caller-supplied
dict that is never persisted to `content_plan.json.summary` nor to `activity.jsonl`.
Same defect class as the mover bug that hid for 12 nights.

**V4 — The copy lane drops 113 of ~120 attempts; the top cause is a provider fault
below the alarm floor.** Tonight: `provider returned no text` 32, `number soup` 19,
format violations 22 → **7 posts written network-wide**. W1i's circuit breaker trips at
>50% provider-stage drops; 32/113 = 28% degrades in silence. Provider-stage faults are
DROPPED, not retried down the `provider_order` ladder.

**V5 — The healthiest lane is the most throttled.** Press wire converts ~90-100
candidate facts/weekday into **≤3** emitted (`_DEFAULT_FLAGSHIP_TOP_K = 3`,
press_lane.py:132 — a code default with NO config override) and posts **89%** of what
it emits (8/9). It is event-driven, never stale, and it is the cheapest volume in the
system. `salience_threshold: 60` is the quality gate and does not move.

**V6 — mastermind_news is dark by config, and its dispatch losses are already fixed.**
`enabled: false / disabled: true` (marketing.yml:1263). Buffer channel IS bound
(marketing.yml:623, `@mastermindnews1`); `BUFFER_TOKEN` exists (rotated 2026-07-24).
The 33 `account_disabled` quarantines are all dated 07-30/07-31, BEFORE
`hot_tape.live_account()` landed (PR #4154) — that fix now rescues dark-target items to
flagship, so arming is a volume ADD, not a leak repair. No `created:` key → `resolve_ramp`
fails closed to `weeks_1_2` (10/day), which is the safe tier for a cold account.
`wire_routing.classes` still point every class at flagship — a deliberate second step.

**V7 — The breaking card.** `render_breaking_card` (chart_render.py:3345). Body text is
**15.5px** on a 1000×560 canvas — the smallest type on the card except 12.5px metadata,
yet it carries the primary content. Headline is wrap-then-clip: `_break_wrap` fills
`max_lines` then slices the last line and appends `…` (chart_render.py:3322-3328); the
size table bottoms out at `>150 chars → 26px/56/3 lines ≈ 168 chars displayed` with no
further downscale. The live Iran item's `headline` is a **~1,140-character verbatim
press quote** — `build_breaking_payload` (breaking_summary.py:695) passes it through with
NO length gate, so ~156 of 1,140 chars render before the ellipsis. Whitespace comes from
the centering block (`v_offset ≤ 56`, chart_render.py:3530-3536).
BLAST RADIUS: `earnings_call_lane.py:399` calls `render_breaking_card` directly — same
function, not a copy. No existing test pins any geometry value.

### §8.2 THE RULING

The nightly ladder is the worst supply source in the system (23% post rate,
staleness-prone, 97% discarded) and it carries nearly all the load. The event-driven
lanes are the best (press wire 89% post rate, never stale) and are throttled by code
defaults. **Rebalance toward event-driven supply, and stop the ladder from throwing away
the day it is supposed to publish.** No threshold moves.

- **W4a — collapse the ladder to one day.** `forward_days` config knob, default **1**.
  Every slot becomes an emit slot, so the cooldown applies uniformly and honestly
  instead of decimating D1 alone. `per_day` sized to the account's ramp cap × a small
  headroom factor rather than a flat 28 — generating 28 to publish 10 is the same waste
  in miniature. When the cooled pool is empty the slot still drops (supply-honest
  volume, §5.5) — it must NOT fall back to the uncooled pool, which would publish the
  repetition the cooldown exists to stop.
- **W4b — intersect tilt with ramp-permitted formats** before slot assignment, so a cold
  account never spends an at-bat on a banned kind.
- **W4c — persist `dropped_cooldown`** into the plan summary and the activity row, with
  a bare line-start `::warning`.
- **W4d — press-wire headroom.** `flagship_top_k_per_day` becomes config-driven and
  rises; surplus routes ACROSS accounts rather than piling onto flagship.
  `salience_threshold` unchanged.
- **W4e — copy-lane yield.** Provider-stage faults RETRY down `provider_order` instead
  of being dropped; the outage alarm fires well below 50%. Reconcile the blanket "ONE
  number per post" prompt line with the per-shape budget the validator enforces — the
  budget itself does not move; the writer is simply told what it is.
- **W4f — arm mastermind_news**: `enabled: true`, add `created:` so the ramp tier is
  explicit rather than fail-closed, route wire classes per the charter (relay, never
  editorialize — F6 sentence-case compression stands).
- **W4g — redesign the breaking card**: body type materially larger, whitespace reduced,
  and a headline of ANY length renders without truncation-by-ellipsis (upstream length
  gate + downscale/wrap, never clip). Proven with committed before/after PNGs at mobile
  and desktop scale, with the 1,140-char Iran headline as the explicit fixture.
