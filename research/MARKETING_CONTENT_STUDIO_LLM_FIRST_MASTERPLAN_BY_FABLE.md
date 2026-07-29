# CONTENT STUDIO LLM-FIRST — facts by engine, words by model, nothing else ships

Operator directive 2026-07-29 (verbatim intent): *"We can't do it like this any
longer… anything remotely requiring intelligence needs LLM with what I've seen
so far with the garbage we are generating with Content Studio… actually create
a superintelligent Content Studio that actually works to create high quality
content, at low latency… while not sounding like a bot."* Trigger: operator
review of the 2026-07-29 outbox batch (65 posts) — review aborted in disgust at
D1-S15.

**The ruling this plan encodes: the mixed architecture stays, but the boundary
moves. The engine decides WHAT (signals, facts, numbers, charts, allocation,
schedule). A model writes EVERY user-facing sentence of planned content. A
deterministic layer verifies what must never be wrong; a model critic verifies
what a human would cringe at; the operator ratifies until autonomy is earned
per (account, kind). Template-composed prose never again reaches a reader on a
planned lane — when the model lane fails, we post NOTHING for that slot, never
the template.** Wire lanes (hot tape, press) keep their deterministic fallback:
wire register survives templating; diary register does not.

## §0 ACCEPTANCE GATES — not done unless

1. **No template prose on planned kinds.** For kinds
   `signal/chart/education/macro/receipt/watchlist/event` emitted by
   content_studio, `write_posts_deterministic` output can no longer reach the
   outbox while `copywriter.llm.required: true` (new, default). A post whose
   model copy fails validation + one repair round is DROPPED and counted, not
   replaced. Test-pinned (emit path refuses `mode != "llm*"` planned items).
2. **One failure no longer zeroes the night.** Per-post model calls (small
   parallel batches), per-post token budget; a truncated or failed call
   isolates to its item. The 60-posts-in-one-6000-token-call design is dead.
   Test: one poisoned item in a 10-item plan yields 9 written posts.
3. **Every operator-named defect class has a named regression test:**
   (a) duplicate body within a batch (D1-S1 == D1-S5);
   (b) same ticker on >2 accounts/day (ARES ×5) — and signal kinds with
       entry/stop numbers on >1 account/day;
   (c) cross-day ticker repeat inside the cooldown (LKFN two days running);
   (d) 2-decimal price in copy on a ≥$100 name (285.10 → 285);
   (e) orphaned hedge tail ("Historical, not a promise." with no historical
       stat in the post);
   (f) internal jargon: count-without-denominator ("18 groups on the move"),
       screen/board/graded/plan vocabulary;
   (g) >35% of a day's posts sharing one shape (the two-line skeleton was
       100%; the real-corpus rate is 2.8%);
   (h) degenerate screen stat (231 of 231 names bullish);
   (i) repeated headline stem across a batch ("Watching $X right now" ×3).
4. **Shape distribution is corpus-grounded and enforced by the mixer**, not
   requested politely in a prompt: per account per day, one-liners ≥25%,
   classic headline+body ≤30%, the rest stacks/lists/captions. Measured in the
   plan report.
5. **Cold-read critic on every planned post** (model pass, fresh context, no
   authorship bias): comprehensibility to a reader with zero context, bot-tell
   scan, dangling references. Reject → one writer repair → reject → drop.
   Drop-rate >30% of a night's plan raises a `::warning` annotation.
6. **Numbers law unchanged and extended**: every number in copy resolves to
   the item's whitelist (existing); the whitelist now carries DISPLAY-ROUNDED
   forms (≥$100 → integer, $10–100 → 1 decimal, <$10 → 2 decimals; percents
   1 decimal) so fake precision is structurally impossible. Full-precision
   values stay in provenance/ledgers/site — grading is untouched.
7. **Supply-honest volume**: posts/day per account = f(fresh facts that
   survived cooldown + reuse budgets), floored and capped by cadence config —
   never slot-count-driven. The plan report prints supply vs emitted.
8. **Live proof in the PR**: dry-run against the real current plan with a real
   key, ≥5 model-written posts pasted in the PR body next to the template
   posts they replace. Then same-day merge, and next nightly's plan report
   shows `llm` mode >0, `det` = 0 on planned kinds.
9. **CI**: new/changed suites named in the marketing-engine lane run line AND
   ci.yml trigger paths; the lane stays LLM-free (lazy imports pinned by
   existing tests).
10. **The rejected 65-post batch is dead** (quarantined with reasons — PR
    #3945) and the next nightly regenerates under the new lane.

## §1 Evidence — what the 2026-07-29 batch proves (all 65 read)

The batch is 100% deterministic-template output — bank strings appear verbatim
("Win or lose it gets graded" = copywriter.py:1040). The persona LLM lane
(`write_posts_llm`) is armed and credentialed since the 2026-07-26 incident
fix, but it structurally cannot run at current volume: ONE batched call for 60
posts with `max_tokens` 6000 (≈100 tokens/post for ~10k tokens of required
JSON) truncates, the JSON parse fails length check, the function returns None,
and every post silently falls back to templates. The queue confirms it; the
distinctness checker scored the batch max_similarity 0.467 ("variants checked")
because token Jaccard cannot see one fact wearing five outfits.

Defect census (operator complaints in bold; the rest found on full read):

| Class | Instances | Root cause |
|---|---|---|
| **Exact/near duplicate bodies** | D1-S1==D1-S5; AI-selloff body ×4 | fact→template rotation; jaccard 0.8 sees only tokens |
| **Same fact, many accounts** | ARES ×5, LKFN ×5, FDS ×4, TEL ×4, KMT ×3, CBOE ×2 with identical entry/target | planner splices the same plan into every desk queue; no fact-reuse budget |
| **Cross-day ticker repeats** | LKFN, GPI, CBOE (posted 07-28, planned again 07-29) | NO cross-day cooldown exists anywhere (map §4) |
| **Fake precision** | every level 2dp (285.10, 375.91, 121.66) | `_fmtp` = `f"{v:.2f}"`; whitelist then forces the LLM to repeat it |
| **Internal jargon as copy** | "18 groups on the move", "the screen", "the board", "gets graded", "the read's up top" | fact strings carry engine vocabulary; ban lists enumerate words, not the failure mode |
| **Orphan hedge tails** | "Historical, not a promise." ×4 variants with no stat | tail device decoupled from the fact kind (#3928's exact class) |
| **Degenerate stats** | "231 of 231 names… bullish" ×2 | no information-content gate on screen stats |
| **Uniform skeleton** | 65/65 = headline + 2–4 clipped sentences | `compose_text` = hook\n\nbody for every item; banks all share one rhythm |
| **Aphorism soup** | "Your move." "The market will provide it or it won't." | persona differentiation is cosmetic seasoning on one bank |
| **Stale entries** | CBOE entry 285.10 vs "reclaimed 287.74" | plan levels frozen nightly; plan-time runaway check tolerates +0.9% |

Fintwit reality (corpus: 286 original posts, 17 large accounts, 2026-07-29,
`research/marketing_dockets/x_corpus_2026_07_29/{stats.md,exemplars.md}`;
refresh cadence monthly):
exactly-two-line posts are the RAREST real shape (2.8%); real posts are ~49%
one dense line, ~17% headline+blank+body, ~34% multi-line stacks. Strict
2-decimal prices appear in 5.9% of posts; 68% use bare integers. 1% end with a
question. Median 9 words/sentence. The corpus winners run on device stacking
(since-dates, streaks, dollar translations) — the same §2.D devices the Hot
Tape masterplan already codified.

## §2 Why templates cannot be patched into adequacy

Six sessions patched this system in four days (#3904 volume, #3907 fragments,
#3913 publish faults, #3918 headline gate, #3922 hand-rewrite of a day's queue,
#3928 tail coherence) and the operator still aborted review. The pattern:
every patch adds an enumerated ban; the generator cannot SEE its output, so the
next failure mode is always one synonym away ("screen" wasn't on the list that
banned "cross-checks"). Coherence (does the tail follow from the fact? does
"that level" point at anything?) is not enumerable. The one system that can
judge prose is a language model; the one system that must never write a number
is also the language model. Hence the boundary above — and it is the SAME
boundary Hot Tape P2 (#3937, merged) already established for wire copy:
engine computes, model phrases, validators verify, template only as fallback.
This plan extends that pattern to the nightly Content Studio and then removes
the fallback for diary-register lanes (a wire one-liner survives templating; a
persona's "diary" voice is precisely what cannot be templated).

## §3 The post ecosystem — every lane, who writes it, who reviews it

| Lane | Trigger | Writer | Review | Latency | Status |
|---|---|---|---|---|---|
| Nightly persona desks (signal/chart/watchlist/macro/education/event/receipt) | nightly plan (daily.yml governor step) | **LLM per-post (this plan)**; no fallback | validators → LLM critic → **operator approve** → post-time gates | overnight batch | REBUILT HERE |
| Hot Tape wire (movers, routs, streaks, thresholds) | 5-min RTH radar | wire templates + `hot_tape_llm.phrase_or_fallback` | numeric gate + device requirement; auto-post (sev-gated) | ≤9 min | #3941 in flight; LLM wiring = P2 seam |
| Press / breaking / Trump wire | VPS press daemon (RSS + corroboration) | `breaking_summary` (LLM, cite-constrained) | corroboration gate + wire validators; auto | minutes | LIVE (separate program) |
| Publish-time movers/theme lists | each publisher pass, live quotes | v3 template banks (numbers ARE the content) | sentinel + tape gate; auto (`auto_approve_kinds`) | ≤30 min | LIVE (#3932) |
| Earnings cards | fastlane detectors → radar fold-in | card builder | wire validators | minutes | folds into radar (hot-tape plan §3) |
| Weekend levels | weekend governor | copywriter personas (LLM-capable) | advisory copy_review | weekend | LIVE; inherits this plan's writer when copywriter migrates |
| Replies | reply desk producer | reply_drafter + critics | M0 draft-only → operator | n/a | XG-W4/W6 (separate arming) |
| Research property | W8 triage | research_lane | veto pass + operator | daily | dark, arming steps pending |

One writer doctrine (voice), one numbers law, one publisher, one outbox —
different speeds and different fallback policies per register.

## §4 Target architecture — the nightly planned lane, rebuilt

```
plans + stat-kit ──► SELECTION (deterministic)          ──► candidate facts
                      cooldowns • reuse budgets • degeneracy • entry sanity
candidate facts ──► ALLOCATION (deterministic)          ──► (account, kind, angle, shape, slot)
                      supply-honest volume • shape mixer • angle assignment
per item        ──► FACT PACKET (deterministic)         ──► typed packet
                      display-rounded numbers • denominators • since-dates
                      streak rarity • persona card • recent-post window
packet          ──► WRITER (LLM, per post)              ──► text (free shape)
                      voice doctrine v4 prompt • shape contract • angle
                      • numbers whitelist verbatim
text            ──► VALIDATORS (deterministic, free)    ──► pass | violations
                      numeric whitelist • banned language • kind bans •
                      shape conformance • dup ledgers • length/cashtags
violations      ──► REPAIR (LLM, once)                  ──► text' → validators
pass            ──► CRITIC (LLM, fresh context)         ──► pass | reject+reasons
                      cold-read • bot-tells • dangling refs • sameness
reject          ──► repair once → recheck → DROP (logged, counted)
pass            ──► OUTBOX queued → operator approve → post-time gates → X
```

Key mechanics:

- **Per-post calls.** `write_posts_llm_v2`: one model call per item (parallel,
  bounded workers), `max_tokens` ~400/post, JSON `{"text": ...}`. The nightly
  30-post plan costs ~100–200k tokens ≈ cents on `marketing_copy`
  (claude-sonnet-4-6) through the existing `llm_auth` waterfall (oauth pool →
  anthropic → deepseek). `daily_token_cap` stays as the runaway brake.
- **Shape mixer** (deterministic): per (account, day) quotas drawn from corpus
  stats with jittered rotation; a 14-day shape ledger prevents streaks. Shapes:
  `one_liner` (≤140 chars, no headline), `two_part` (headline + blank + body —
  the ONLY shape that keeps a headline), `stack` (2–5 single-\n lines, numbers
  carry it), `list` (ticker rows + one read), `caption` (≤90 chars riding a
  chart). The outbox `compose_text` becomes shape-aware; `headline` is empty
  for every shape except `two_part` (admin panel falls back to a text excerpt).
- **Angle assignment**: when one fact legitimately appears on two accounts, the
  allocator assigns disjoint angles (e.g. `level_watch` vs `risk_frame`) and
  the writer receives the OTHER account's already-written text with the
  instruction "different angle, different shape, zero shared phrasing" —
  checked by a cross-account 3-gram overlap gate at plan time (tighter than
  jaccard 0.5).
- **No-fallback**: planned kinds with `mode != llm*` cannot emit while
  `copywriter.llm.required` (default true). Provider mute/failure now emits a
  `::error` annotation (bare print at line start) and posts NOTHING for those
  kinds. Config escape hatch documented for emergencies only.
- **Numbers**: display rounding at packet build (`_fmtp` magnitude-aware);
  validators' regexes updated so a 2dp price on a ≥$100 name is itself a
  violation (d-class test). Percents 1dp. Since-dates in words ("since March"),
  reusing the `_iso_human` device from hot_tape_llm.
- **Jargon at the source**: `market_facts` count facts carry denominators and
  plain nouns as STRUCTURED FIELDS (`n_moving=18, n_tracked=30,
  noun="industry groups"`); prose like "on the screen"/"on the board" is
  removed from fact strings; the writer translates fields, the critic kills
  leaks. Grep-audit of fact-string vocabulary is part of this wave.
- **Stat-kit enrichment**: the packet joins the nightly Hot Tape context pack
  (`data/marketing/hot_tape_pack.json`, #3941) when present — streak rarity
  ("longest run since March"), 52w/ATH distance, since-dates — dependency-
  inverted: absent pack degrades to today's facts, no import of radar code.
  This is the single biggest content upgrade: "TEL has closed green 6 sessions
  in a row" becomes a post only when the pack says how rare that is.

## §5 Selection layer (deterministic, before any writing)

1. **Cross-day ticker cooldown** (new, the LKFN/GPI/CBOE fix): fleet-wide, from
   the outbox ledger (items + status, already repo-truth): a ticker
   posted/booked on ANY account in the last 3 trading days is ineligible for
   watchlist/chart mentions; 5 trading days for signal kinds; override ONLY
   when a genuinely new fact class fires (earnings, |move| ≥4%, level break,
   streak-rarity record) — and then the post must lead with the new fact.
2. **Fact-reuse budget**: (ticker, day) ≤2 accounts with disjoint angles;
   signal kinds with entry/stop numbers: exactly 1 account/day. Confluence and
   movers lanes count toward the budget.
3. **Degenerate-stat gate**: a screen count with hit-rate ≥95% or ≤5% of its
   universe carries no information → fact dropped, logged.
4. **Entry sanity at plan time**: tighten plan-time runaway/underwater to the
   publisher's live thresholds and re-verify at packet build; a signal already
   through its entry beyond tolerance is re-planned as a watch ("it went
   without me" is `watchlist_runaway`'s honest job) or dropped.
5. **Supply-honest volume**: emitted = min(cadence cap, facts surviving 1–4).
   No slot-filling. The ladder keeps its rungs; empty rungs stay empty.

## §6 Voice doctrine v4 (extends v3; corpus-grounded)

v3's register laws stand (fintwit deadpan, cheese test, translation law,
sarcasm aim points). v4 adds what the corpus measured:

- **Shape truth**: one dense line is the default human post. Blank-line
  headline+payoff is a REAL winner shape but at ~17%, not 100%. Stacks where
  numbers escalate (Kobeissi) are the highest-engagement structure.
- **Numbers as drama**: integers and 1-dp percents; "since <month day>"
  anchors; dollar translations for scale; denominators on every count.
- **Personas differ by WHAT THEY NOTICE, not by seasoning**: each desk's codex
  worldview drives which fact leads (Sophia: precedent/analogue; Kelly:
  receipts/discipline; Cici: group-first; Meagan: process). Signature phrases
  stay under existing quirk caps; NO persona may narrate its own accountability
  system ("graded", "on the page") — show a receipt, never explain receipts.
- **Hedges must bind**: an uncertainty tail may only restate the specific
  stat's nature ("that 78% is history, not a promise" requires the 78% in the
  post). The generic tail is banned as a floating device (extends #3928).
- **The cold-read law is the first law**: every post must parse for a reader
  who sees ONLY these words, no chart, no context, no prior posts.

## §7 Review + autonomy

- Generation-time: validators (hard) → critic (hard on planned lanes).
- Queue-time: **planned persona kinds return to operator approval** —
  `publish.auto_approve` becomes kind-scoped so `mover/theme_list/breaking`
  stay auto but planned kinds require a decision until the approve-ladder
  (XG charter) grants per-(account,kind) autonomy on measured quality. The
  07-29 batch auto-approving 61 garbage posts is the proof this scoping is
  needed. Operator reverses with one config line if they prefer full auto.
- Post-time: existing tape gate, language gate, byte-repeat gate unchanged.
- Learning: provenance stamps `mode/shape/angle/critic_verdict`; the metrics
  poll + labels store (XG-W6) joins engagement; the weekly scorecard gains a
  per-shape/per-angle table; shape quotas and angle weights move on evidence.
  A monthly corpus refresh re-runs the stats and diffs the doctrine.

## §8 Rollout

- **W1 (this session, one PR)**: everything in §4–§7 except the learning
  table: selection layer, shape mixer, per-post writer, repair, critic,
  no-fallback, rounding, jargon-source fixes, kind-scoped auto-approve,
  emit-path shape support, expiry of stale queued planned items (>36h past
  slot), tests for every §0 gate, dry-run script + PR proof. Arm on merge
  (keys already in daily.yml env since the mute-incident fix).
- **W1.5 (follow-up)**: per-shape engagement table in the weekly scorecard;
  critic calibration vs operator approve/reject decisions (the approve queue
  IS the label stream); requeue-stale-copy migration for weekend_levels to the
  v2 writer.
- **W2**: Hot Tape P2 wiring (radar → `phrase_or_fallback`) once #3941 lands —
  owned by the radar's session or this one, whichever is free; zh twins for
  planned lanes stay out of scope (EN accounts).
- **W3**: reply-desk drafter adopts the v4 doctrine + critic; autonomy ladder
  arming per (account, kind) on measured approve rates.

## §9 Collisions & standing law

- **Epistemics**: the model never originates a number, level, signal, or
  score; packets are engine-computed; critic is de-escalation-only. Consistent
  with DO_NOT_REBUILD's LLM rows (checked 2026-07-29: bans cover origination
  and classification-into-calibrated-keys; phrasing behind numeric gates is
  the #3937 sanctioned pattern).
- **Ledger law**: cooldown reads the outbox ledger; no new forward ledger; the
  nightly remains the sole advancer.
- **In-flight PRs**: #3941 (hot tape P1) — complementary, dependency-inverted
  here; #3918 (post-time headline gate) — complementary last-gate; #3928
  (tail coherence) + #3927 (cadence specs) — DIRTY vs main; their surviving
  intent is absorbed by this plan (tail-binding is §6 law; cadence caps stay
  config-side) — adjudicate/rebase or close with reasons after W1 merges.
- **Render budget**: all work lives in the marketing governor step (off the
  render path); per-post calls are parallel and bounded; zero new render-lane
  cost.
- **Charts**: ticker-post-carries-chart law unchanged; caption shape REQUIRES
  media present at emit.
- **Board/quota**: twitterapi.io corpus refresh uses the existing $75 bucket,
  ~17 calls/month.

## §10 ECOSYSTEM COMPLETION — operator escalation 2026-07-29

Operator directive (verbatim intent): *"complete the entirety of our X Growth
system to perfection … breaking news, earnings releases, politician trades,
Trump's tweets, occasional analysis … each account has its distinct personality
… continually self improving and learning … the automated reply system on the
M1 studio … THIS ENTIRE INFRASTRUCTURE AND BUILD OUT MUST BE COMPLETED AT THE
HIGHEST QUALITY."* Codex case-study evidence pack ratified as editorial input:
23-post breaking/insider analysis (operator-supplied 2026-07-28) — its findings
(consequence+specificity wins; two-step publish alert→context; attribution in
sentence one; mechanism makes context repostable; insider posts need the
RELATIVE stake math, not the dollar headline) are adopted as law for the wire
and insider lanes below.

### The complete lane matrix (target end-state)

| # | Lane | Trigger/data | Writer | Speed | State 2026-07-29 | Completing wave |
|---|---|---|---|---|---|---|
| 1 | Nightly persona desks | plans + stat kit | LLM v2 (no fallback) | overnight | **W1 this PR** | done |
| 2 | Intraday tape (movers/routs/streaks/thresholds) | 5-min radar | wire templates → LLM phrasing | ≤9 min | radar LIVE (#3941); LLM phrasing built (#3937) UNWIRED | E1 |
| 3 | Breaking/press/geopolitics | RSS + corroboration (VPS daemon) | breaking_summary LLM | minutes | built; split-brain to publisher + arming to verify | E7 |
| 4 | Trump/White-House wire | press providers (Truth Social/WH feeds per addendum) | wire voice | minutes | providers exist; verify + arm | E7 |
| 5 | Earnings reactions | earnings.parquet calendar + gap/AH detection | wire + LLM | ≤20 min | card builder exists, daemon never ticked | E1 |
| 6 | Insider buys (Form 4) | EDGAR/Form-4 feed | fact-locked LLM (codex §insider workflow) | daily batch | NOT BUILT (recon in flight) | E2 |
| 7 | Politician trades | congressional disclosures | fact-locked LLM | daily batch | NOT BUILT (source recon in flight) | E2 |
| 8 | Occasional analysis / research property | W8 triage | research_lane | daily | built DARK (operator arming steps) | operator |
| 9 | Movers/theme lists | live quotes at publish slots | v3 templates (numbers ARE content) | ≤30 min | LIVE (#3932) | done |
| 10 | Replies (growth engine) | reply producer + M1 seat | reply_drafter LLM | daily ops | M0 draft-only; producer dark; targets placeholder | E4 + operator |
| 11 | Receipts/track record | graded ledgers | LLM v2 receipt kind | overnight | rides W1 | done |

### E-waves (build order after W1 merges; each = builders + adversarial review)

- **E1 — intraday completeness**: wire `hot_tape_llm.phrase_or_fallback` into
  the radar emit path (template fallback stays, wire register); earnings
  detector into the radar detector registry (calendar join: BMO gap-at-open /
  AH next-open reaction until extended-hours quotes exist); adopt the codex
  **two-step publish**: severity ≥90 events auto-file a follow-up "context
  brief" item (mechanism + transmission + what-to-watch, LLM-written, numeric-
  gated) 20–40 min after the alert.
- **E2 — fact-locked filing lanes**: insider Form 4 lane exactly per the codex
  workflow (validate transaction code/ownership/10b5-1 → compute value, prior
  shares, RELATIVE stake change → mechanism classification NEW_POSITION /
  MATERIAL_ADDITION / REPEAT_BUY / CLUSTER_BUY / SMALL_ADDITION_TO_LARGE_STAKE
  → fact-locked writer → validators). Politician-trades lane same skeleton if
  recon finds a clean primary source (no scraping revival where kills stand).
  Both OBSERVATION register, display-tier, no calls.
- **E3 — competitive-intelligence loop (self-improving)**: recurring harvester
  (weekly deep + daily light) over a config roster of top accounts via
  twitterapi.io → `data/marketing/x_intel/` corpus + per-format/per-trigger
  engagement tables (codex measurement schema: capture timestamps, normalize
  by views; repost/view for distribution) → auto-distilled exemplar candidates
  → **operator-ratified** exemplar store versions → writer/critic prompts load
  exemplars from the store (config-pinned version, never auto-flipped) →
  monthly doctrine drift report. LLM distills style; engagement math stays
  deterministic (LLM-never-scores law).
- **E4 — reply-craft intelligence**: harvest reply corpora under top fintwit
  posts (rank replies by engagement); write REPLY doctrine (value taxonomy:
  data-drop, sharp read, dry wit, useful question; length/tone laws; never
  argue, never hedge-spam); upgrade reply_drafter prompt with doctrine +
  exemplars + per-persona register; reply critic gets the cold-read bar; eval
  fixtures from real (anonymized) reply threads. M1 seat consumes the same
  doctrine via the runbook.
- **E5 — persona depth**: per-account rolling self-exemplars from OPERATOR-
  APPROVED posts only (voice compounds from ratified wins); cross-account
  stylometry in the weekly scorecard (shape/opener/length distributions per
  desk — sameness regression visible before followers see it).
- **E6 — learning spine**: shape/angle/trigger provenance joined to the W6
  labels store; weekly scorecard gains per-shape/per-angle/per-trigger tables;
  quota/weight moves happen as CONFIG EDITS citing the table (deterministic,
  auditable); critic calibration vs the operator approve/reject stream.
- **E7 — press estate closure**: fix the press split-brain (VPS items → the
  publisher's checkout), verify Trump-wire providers live, arm the daemon
  service, wire two-step context briefs on corroborated majors.

### Standing operator levers (cannot be coded around; restated honestly)

employee texture confirmations (AM-R1); golden-set labeling (scoring brain
ordering); research X account + Buffer channel; press-property DNS + NewsAPI.ai
call; M1 desktop seat + browser profiles; X Communities joins; Buffer channels
for any new account; `datasketch` on the press host; DEEPSEEK_API_KEY on the
VPS (zh twins).
