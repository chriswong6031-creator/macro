# Persona Network — X desk network expansion (masterplan, docket D13)

**Program:** Agentic Media / Persona Network · **Author:** Fable · **Date:** 2026-07-25 (rev 2 after adversarial review) · **Status:** CHARTERED
**Umbrella:** `AGENTIC_MEDIA_PROGRAM_BY_FABLE.md` (AM-R1 provenance incl. post-tier disclosure, AM-R2 scale, AM-R3 value, AM-R6 routing, AM-R7 measurement)
**Extends (never parallels):** desk_network in `config/marketing.yml` + `engine/marketing/accounts.py` (6 desks, flagship live); D02 outbox/actuation (`engine/marketing/outbox.py`, publisher); D08 Sentinel (`engine/marketing/sentinel.py` + `D08_APPENDIX_X_POLICY_REDTEAM.md` ramp table); voice v3 + copywriter (`engine/marketing/content_studio.py`, `copywriter.py`); guerrilla doctrine §3 (`research/MARKETING_LOBE_GUERRILLA_GROWTH_AND_OPERATIONS_BY_FABLE.md`).

The delta this masterplan adds to the existing 6-desk newsroom: **(a)** a first-class *persona* layer (identity/voice/character, not just beat+tilt), including fictional characters; **(b)** per-persona **thesis memory** (long-horizon calls with invalidation + scheduled reopens); **(c)** a **pipeline experiment harness** with statistically usable, pre-registered promote/kill gates; **(d)** the **earned-scale ladder** past 6 accounts; **(e)** the **post-time cross-account near-dup radar** (closing the known gap: memory `marketing-autonomous-cadence-program` — "NO post-time cashtag dedup"); **(f)** **per-account ramp enforcement** (the D08 ramp table is currently decorative — no code reads `sentinel.ramp`, and the live global cap is -1/unlimited; this program builds the reader before any pilot posts).

## §0 ACCEPTANCE GATES

**Ledger law (all waves):** `data/marketing/personas/<id>/theses.jsonl` is **nightly-advanced only** — intraday lanes (reopen scheduler, invalidation triggers) may *read* it and *enqueue outbox drafts*, never append; outcome grading is owned by the Growth-Science lane (no persona lane grades itself). Any publisher-side receipt writing follows the existing outbox git-add precedent, scoped in the publish workflow.

**W1 (spec + substrate) not done unless:** persona spec v1 (§3) validates + round-trips for all 6 existing desks with zero behavior change — the six `desk_network` entries byte-unchanged, a dry-run content plan byte-diff-zero, and `copywriter._get_copy` never falls back for any configured persona (the spec keeps `voice:` as the live template-pool join key — §3); spec-loader validation rejects a tilt whose key set ≠ the content-studio type-id set or whose `signal` weight is not the max ≥0.28 (partial tilts inherit `_DEFAULT_TILT`, so omit ≠ disable — validator makes the declared mix the delivered mix); 3 pilot persona specs + 1 control (§3.3) committed with full voice codexes + disclosure lines; admin Persona Roster panel (markup pinned by the commissioning session or `designer`) renders every persona with status/scorecard-skeleton, read-only, fail-soft; no new account is created and no cap/ramp value changes; the `config/personas/` ↔ `copywriter.personas` precedence ruling (§3) is implemented as written.

**W2 (lanes + safety) not done unless:** copywriter generation consumes persona codex + chronicle pack (via the Chronicle-W2 injection helper — never re-implemented here) + thesis memory in the prompt (one logged sample per persona); thesis-memory nightly advancer + reopen scheduler emit draft kinds into the existing outbox; **per-account ramp resolver ships and enforces** — `desk_network.accounts[].created` date → ramp tier from `sentinel.ramp`, per-account cap = min(global, tier) so a -1 global no longer means unlimited for a week-1 account, with a drift-guard test proving a 0-day-old account resolves to 2/day while the live flagship keeps its current behavior; **post-time cross-account near-dup radar blocks a seeded duplicate pair in a live-shaped dry run** (test proves the block); per-persona validator profile wired (banned vocab, cheese-test threshold, advice-disclaimer cue on thesis/level posts, in-post connection token on product-mentioning posts per AM-R1 post tier); all Sentinel gates still pass on the whole plan.

**W3 (pilots live) not done unless:** operator has verified current X policy wording (umbrella §8 item 1) and created/warmed the pilot accounts (human step, D02 law); each pilot bio carries the network disclosure line; unattended accounts carry X's Automated label; account names/handles/avatars pass the naming lint (§1 — nothing evoking a real person, firm, or publication; PCF name-level label if ever parody of a real entity); Buffer/API channel wired per account with per-account credentials; W2's ramp resolver enforcing Week-1-2 caps on the new accounts (2 posts/day, 120-min spacing, no links, 1 media, 0 auto-replies/follows); first-week posts pass 100% of gates with zero manual overrides; scorecard ledger receives real post-level metrics rows (poller #3346 per account), with the **follower-metrics source named and provisioned or explicitly deferred** — the Buffer per-post poller cannot supply follower Δ / follower quality; either an X API read tier (costed) or a manual weekly capture is declared, or those fields are dropped from the gates and post-level engagement gates alone apply.

**Every wave:** no browser-automation actuation (R0 stays parked per D08 Appendix — API/Buffer only); cross-account link/citation follows the similarity rule (§5 — a publication's account + the flagship may each share a piece once with distinct framing; all else asynchronous >24h, radar-checked); kill-switch hierarchy reachable (global `MARKETING_PUBLISH_ENABLED`, per-account `enabled:false`, per-persona lane flags).

## 1. What a persona is (and is not)

A persona = **a disclosed editorial character with a beat, a voice, a memory, and a scorecard.** Three persona kinds (spec field `persona_kind` — deliberately NOT the existing config `kind:` key, which keeps its shipped `branded|generic` vocabulary; `generic` maps to `specialist` at read time):

| persona_kind | example archetypes | identity rules |
|---|---|---|
| `branded` | flagship, receipts, theme desk (existing) | Mastermind-branded; product talk allowed |
| `specialist` | macro wonk, why-moving fast desk, analogue historian (existing 3, upgraded with codexes) | own name/handle ok; bio: network line; product mentions occasional, first-party framed + in-post token (AM-R1 post tier) |
| `character` | corporate desk professional; meme/cartoon mascot; stylized "Wall St" archetypes; zh-market voice | fictional presentation; avatar may be illustrated or AI-generated **but never a real person's likeness**; bio: network line + AI-assisted; **no testimonial-style product claims ever** (16 CFR 465); may go long stretches with zero product content |

Hard lines (all DNR-registered via AM-R1):

- **The deceptive act is the line, not the art style:** no persona may claim personal trading experience, positions, P&L, employment history, or lived experience of any kind — theses are stated as the desk's calls, never as the character's trades. (Enforced as banned-pattern rules in every persona's validator profile.) An AI-photorealistic avatar is permitted when the name/bio disclose AI + network affiliation; what is banned is fabricated *experience*, fake-selfie authenticity theater, and any presentation as an independent real human.
- No persona "discovers" or endorses the product as an outsider.
- No coordinated amplification between personas (occasional genuine cross-citation ok under the §5 similarity rule).
- **Naming lint:** no persona name, handle, avatar, or masthead may reference or evoke a real person, firm, publication, or their marks; if any persona is ever a parody/commentary of a real entity, X's PCF regime requires the label in the account **name**, not just the bio.
- The "hot girl Wall Street" archetype is buildable under these rules as a disclosed stylized character — if it needs fabricated lived experience or fake-selfie authenticity to work, it does not ship.

## 2. Why this can reach real followers (the honest bet)

The network's edge is not volume — X is saturated with volume. It is: (a) **receipts** — every persona grades its own calls on schedule (nobody else does); (b) **speed with evidence** on why-moving/event days (we already compute the answer); (c) **chronicle context** — persona takes reference the running story ("third week of the positioning unwind narrative"), which reads as memory/judgment, the scarcest texture in finance-X; (d) **craft floor** — branded chart cards (chart v2/v3 pipeline) beat screenshot noise. Personas are the *casting* that lets different audience segments (wonk / degen / professional / zh) each find a voice they'd follow; the content spine is shared machinery.

## 3. Persona spec v1 (`config/personas/<id>.yml`, referenced from `config/marketing.yml` desk_network)

**Precedence ruling:** at W1 the spec is **additive** — `copywriter.personas.<id>` (shipped block, keyed by the same account ids) remains canonical for `voice_notes`/`example_lines`, and the spec overlays codex/beat/memory/scorecard around it (this is what keeps the W1 zero-diff gate honest). **W2 migrates**: the codex supersedes `copywriter.personas`, the old block is deleted in the same PR with a no-orphan test. Never two live sources of voice truth beyond that one staged wave.

```yaml
id: macro_wonk          # joins desk_network.accounts entry by id (accounts.py unchanged: enabled/status law stands)
persona_kind: specialist # branded | specialist | character   (config `kind:` untouched; generic→specialist at read time)
archetype: "plain-English macro/rates explainer"
voice: "educational"     # REQUIRED — the live template-pool join key (deterministic floor), unchanged from config
voice_codex:             # taste-as-deliverable: authored per AM-R6, not builder-generated; LLM-ceiling voice
  register: "calm, wry, teacherly; short declaratives; no exclamation marks"
  quirks: ["opens threads with a question", "always names the counter-case"]
  emoji_policy: none     # none | sparse | signature-set
  banned: ["moon", "rocket", "guaranteed", "trust me", …house list…]
  banned_patterns: ["first-person trade claims (my position/I bought/my P&L)", "personal-experience fabrication"]
  zh: false              # zh-voice personas render zh-first
disclosure:
  bio_line: "Research character from the @MastermindX network · AI-assisted"
  automated_label: true  # X Automated label when posting is unattended
  in_post_required_kinds: [product_mention, product_link, product_screenshot]   # AM-R1 post tier lint
  advice_disclaimer: true # standing bio text + required in-post cue on any thesis/level-bearing post
beat: "macro/rates/liquidity, translated for humans"
tilt: {signal: 0.30, chart: 0.13, mover: 0.05, theme_list: 0.05, receipt: 0.10,
       event: 0.09, education: 0.18, macro: 0.07, watchlist: 0.03}
# ALL NINE kinds, summing to 1.0, signal max ≥0.28 — spec-loader validated; partial tilts inherit
# _DEFAULT_TILT (omit ≠ disable), so the validator rejects partial key sets outright.
pipeline: hybrid         # engine | hybrid | llm   (experiment axis)
model_tier: default      # default | opus          (experiment axis; effort via copywriter config)
cadence_profile: standard_ladder   # D08 ramp tier resolved from accounts[].created via the W2 resolver
context_packs: {chronicle: [short, medium], desks: [macro, rates]}
memory: data/marketing/personas/macro_wonk/theses.jsonl   # nightly-advanced (§0 ledger law)
scorecard:               # pre-registered at charter time, per persona — statistically usable form
  min_impressions: 20000          # gate evaluates only past this floor
  promote_after: {weeks: 4, engagement_rate_ci_lower_above: 0.015, follower_quality_min: null}
  kill_after: {weeks: 8, engagement_rate_ci_upper_below: 0.005}
  alpha_note: "decision thresholds Bonferroni-adjusted across live arms; expected arm size at ramp cadence ≈56 posts/4w — printed on the roster panel so gate power is legible"
```

### 3.3 Pilot roster (S1)

| id | persona_kind | archetype | pipeline | note |
|---|---|---|---|---|
| `corp_desk` | character | corporate desk professional (suit-and-terminal voice) | hybrid | EN |
| `chart_gremlin` | character | illustrated meme/cartoon mascot, chart-first | llm | EN; strictest banned-patterns profile |
| `zh_navigator` | specialist | zh-first market navigator (CN/HK beat) | hybrid | zh:true |
| `control_v3` | specialist | current voice-v3 engine lane, no codex/LLM | engine | **control arm** — pinned baseline |

S1 is a **descriptive pilot**, not a clean factorial — archetype, audience, and language vary together by design; the control arm supplies the baseline, and attribution-grade single-axis experiments begin at S2 (≥2 personas sharing an archetype varying pipeline/model only). Stated so no one reads S1 deltas as causal.

## 4. Thesis memory (the long-interval answer)

`data/marketing/personas/<id>/theses.jsonl`, append-only, **nightly-advanced** (§0): `{id, opened_at, claim (plain-word), tickers, invalidation (level/condition), review_at, status: open|hit|invalidated|expired, reopened_post_ids[]}`. Sources: only calibrated engine/signal surfaces may seed a thesis (LLM never originates — house law); the persona *voices* it. Intraday, the reopen scheduler and tape-gate invalidation triggers *read* the ledger and enqueue draft "update on my <X> call" outbox items; status transitions and grading land in nightly, graded by the Growth-Science lane (receipts-ledger discipline — no persona lane marks its own homework). Effects: long-horizon continuity the operator asked for, per-persona public receipts, and a natural anti-repetition brake (a persona with 4 open theses talks about *them*, not the same breadth stat daily).

## 5. Content pipeline matrix (the experiment the operator sketched)

Axes: **pipeline** engine-only (voice-v3 templates) / hybrid (template skeleton + LLM voice pass) / full-LLM (copywriter with codex + chronicle pack + memory); **model/effort** default vs opus, effort low vs high on LLM lanes; **cadence** ladder density within ramp caps; **archetype** across personas. S1 is descriptive (control-anchored, §3.3); S2+ varies one axis at a time. Weekly scorecard rows feed the §3 gates (min-impressions floor + CI decision rules + alpha adjustment); measurement lives in Growth-Science-owned ledgers. Content guards: engine-only share ≤ tilt cap per persona; every LLM post passes cheese-test + persona banned-vocab/banned-patterns + disclosure lints (network line contexts, in-post token kinds, advice-disclaimer cue); signal posts keep the invalidation+disclosure cue words (Sentinel lexicon law). **Cross-account citation rule:** no two accounts may post substantially similar text/media for the same URL; a publication's own account and the flagship may each share a piece once with distinct framing; all other cross-citation is asynchronous (>24h) and radar-checked.

## 6. Scale ladder (AM-R2 operationalized)

| Stage | Handles / surfaces | Gate to advance |
|---|---|---|
| Now | 6 handles configured / 1 live | — (in flight, D02) |
| S1 | +3–4 pilot handles (§3.3) → ≤10 total | Each pilot passes W3 §0; network zero warnings 4 consecutive weeks |
| S2 | Winners scaled (cadence/lanes), losers retired; still ≤10 handles | ≥2 personas hit promote gates; dedup radar clean streak; **divergence gate**: pairwise tilt-vector cosine below declared threshold + beat/archetype-overlap check + scheduled human read-through — all three before any handle is added |
| S3 | Publication accounts (Media program) + Verified-Org affiliation badges if purchased → 15–25 **surfaces** (handle count still ≤~10 editorial + per-publication accounts) | Media W2 live; operator ruling + budget for Verified Org |
| S4 | Labeled automated utility feeds (per-market data feeds) if wanted → higher N | Explicit operator ruling; each feed X-Automated-labeled; separate prereg |

Retired handles are parked, never content-recycled. The ceiling is a **review trigger, not a hard law**: `max_editorial_accounts_without_ruling: 10` in Sentinel config warns and blocks automatically-provisioned handles past 10 (provenance: 2018 X developer automation guidance + D08 R1, medium confidence, re-verify at W3 — the operative platform test is genuinely-distinct, non-duplicative purpose per account, not the count).

## 7. Waves

| Wave | Ships | Model lane |
|---|---|---|
| **W1** | Persona spec loader + validation (`engine/marketing/personas.py`), 6 existing desks migrated additively (zero-diff gate), §3.3 pilot codexes (main-loop/Fable authored), admin Persona Roster panel | Opus `builder`; codexes NOT delegated; panel markup pinned or `designer` |
| **W2** | Copywriter context injection (codex + chronicle pack via injection helper + memory), thesis nightly advancer + reopen scheduler → outbox kinds, **per-account ramp resolver in sentinel.py** (+ drift test), **post-time cross-account near-dup radar** (shingle store keyed by (cashtag, template-family, 24h) across ALL accounts), per-persona validator profiles, `copywriter.personas` migration (+ no-orphan test) | Opus `builder` |
| **W3** | Pilot go-live runbook: operator account creation/warm checklist + policy-wording verify, naming lint, Buffer channel wiring, ramp arming, scorecard poller per account, follower-metrics source decision | Operator + Opus `builder` |
| **W4** | Scorecard→promotion engine (gates from spec, auto-narrow on warnings — extends `authority.py` should_narrow), weekly persona report card in admin (incl. expected-arm-size/power line) | Opus `builder`; panel via pinned markup or `designer` |
| **W5** | S2/S3 scale wave per §6 gates | Ruling-gated |

## 8. Risks (printed)

- Pilot personas may simply not grow — the gates make that a cheap, legible kill (8 weeks, known cost), and the codex/memory machinery transfers to the survivors.
- Character voices drift toward cringe under LLM generation — codex banned-lists + cheese-test + weekly human skim (operator or main-loop) on a 10-post sample per persona.
- X policy shifts (label rules, account caps) — per-account policy adapter + the review-trigger assertion localize the response; the network narrows, never dies as a graph.
- Buffer per-channel cost (~$6–12/mo/channel) + 2026 API pay-per-use economics are real at S3+ — revisit posting rail per account at W3 with live numbers; follower-level metrics likely need an X API read tier (costed at W3) or stay out of the gates.
- Engagement-rate gates on young accounts are noise below the impression floor — the floor + CI rules exist precisely so a quiet fourth week doesn't promote or kill anyone by accident.
