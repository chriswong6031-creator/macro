# Persona Network — X desk network expansion (masterplan, docket D13)

**Program:** Agentic Media / Persona Network · **Author:** Fable · **Date:** 2026-07-25 · **Status:** CHARTERED
**Umbrella:** `AGENTIC_MEDIA_PROGRAM_BY_FABLE.md` (AM-R1 provenance, AM-R2 scale, AM-R3 value, AM-R6 routing, AM-R7 measurement)
**Extends (never parallels):** desk_network in `config/marketing.yml` + `engine/marketing/accounts.py` (6 desks, flagship live); D02 outbox/actuation (`engine/marketing/outbox.py`, `scripts/` publisher); D08 Sentinel (`engine/marketing/sentinel.py` + `D08_APPENDIX_X_POLICY_REDTEAM.md` ramp caps); voice v3 + copywriter (`engine/marketing/content_studio.py`, `copywriter.py`); guerrilla doctrine §3 (`research/MARKETING_LOBE_GUERRILLA_GROWTH_AND_OPERATIONS_BY_FABLE.md`).

The delta this masterplan adds to the existing 6-desk newsroom: **(a)** a first-class *persona* layer (identity/voice/character, not just beat+tilt), including fictional characters; **(b)** per-persona **thesis memory** (long-horizon calls with invalidation + scheduled reopens); **(c)** a **pipeline experiment harness** (engine vs hybrid vs LLM × model tier × effort × cadence) with pre-registered promote/kill gates; **(d)** the **earned-scale ladder** past 6 accounts; **(e)** the cross-account **near-dup radar at post time** (closing the known gap: memory `marketing-autonomous-cadence-program` — "NO post-time cashtag dedup").

## §0 ACCEPTANCE GATES

**W1 (spec + substrate) not done unless:** persona spec v1 (§3) validates + round-trips for all 6 existing desks with zero behavior change (flagship posts unchanged, byte-diff on a dry-run plan); 3 new pilot persona specs (§3.3) committed with full voice codexes + disclosure lines; admin Persona Roster panel renders every persona with status/scorecard-skeleton (read-only, fail-soft); no new account is created and no cap/ramp value changes.
**W2 (lanes + safety) not done unless:** copywriter generation consumes persona codex + chronicle pack + thesis memory in the prompt (visible in a logged sample per persona); thesis-memory ledger appends + reopen scheduler emit into the existing outbox as draft kinds; **post-time cross-account near-dup radar blocks a seeded duplicate pair in a live-shaped dry run** (test proves the block, not the code path's existence); per-persona validator profile (banned vocab, cheese-test threshold) wired; all Sentinel gates still pass on the whole plan.
**W3 (pilots live) not done unless:** operator has verified current X policy wording (umbrella §8 item 1) and created/warmed the pilot accounts (human step, D02 law); each pilot bio carries the network disclosure line; unattended accounts carry X's Automated label; Buffer/API channel wired per account with per-account credentials; D08 Week-1-2 ramp caps enforced from Sentinel config (2 posts/day, 120-min spacing, no links, 1 media, 0 auto-replies/follows); first-week posts pass 100% of gates with zero manual overrides; scorecard ledger receives real metrics rows (poller #3346 extended per account).
**Every wave:** no browser-automation actuation (R0 stays parked per D08 Appendix — API/Buffer only); no cross-account same-link posting inside a 24h window (radar-enforced); kill-switch hierarchy reachable (global `MARKETING_PUBLISH_ENABLED`, per-account `enabled:false`, per-persona lane flags).

## 1. What a persona is (and is not)

A persona = **a disclosed editorial character with a beat, a voice, a memory, and a scorecard.** Three kinds:

| kind | example archetypes | identity rules |
|---|---|---|
| `branded` | flagship, receipts, theme desk (existing) | Mastermind-branded; product talk allowed |
| `specialist` | macro wonk, why-moving fast desk, analogue historian (existing 3, upgraded with codexes) | own name/handle ok; bio: network line; product mentions occasional, first-party framed |
| `character` | corporate desk professional; meme/cartoon mascot (illustrated); stylized "Wall St" archetypes; zh-market voice | obviously fictional presentation (illustrated/stylized avatar — never a real person's likeness, never fake-selfie authenticity theater); bio: network line + AI-assisted; **no testimonial-style product claims ever** (16 CFR 465); may go long stretches with zero product content |

Hard lines (all DNR-registered via AM-R1): no persona presents as an independent real human; no persona "discovers" or endorses the product as an outsider; no coordinated amplification between personas (occasional genuine cross-citation ok, asynchronous, with the receipts desk pattern); the "hot girl Wall Street" archetype is buildable **only** as an overtly stylized illustrated character under these rules — if it needs to look like a real woman posting selfies to work, it does not ship.

## 2. Why this can reach real followers (the honest bet)

The network's edge is not volume — X is saturated with volume. It is: (a) **receipts** — every persona grades its own calls on schedule (nobody else does); (b) **speed with evidence** on why-moving/event days (we already compute the answer); (c) **chronicle context** — persona takes reference the running story ("third week of the positioning unwind narrative"), which reads as memory/judgment, the scarcest texture in finance-X; (d) **craft floor** — branded chart cards (chart v2/v3 pipeline) beat screenshot noise. Personas are the *casting* that lets different audience segments (wonk / degen / professional / zh) each find a voice they'd follow; the content spine is shared machinery.

## 3. Persona spec v1 (`config/personas/<id>.yml`, referenced from `config/marketing.yml` desk_network)

```yaml
id: macro_wonk          # joins desk_network.accounts entry by id (accounts.py unchanged: enabled/status law stands)
kind: specialist        # branded | specialist | character
archetype: "plain-English macro/rates explainer"
voice_codex:            # taste-as-deliverable: authored per AM-R6, not builder-generated
  register: "calm, wry, teacherly; short declaratives; no exclamation marks"
  quirks: ["opens threads with a question", "always names the counter-case"]
  emoji_policy: none    # none | sparse | signature-set
  banned: ["moon", "rocket", "guaranteed", "trust me", …house list…]
  zh: false             # zh-voice personas render zh-first
disclosure:
  bio_line: "Research character from the @MastermindX network · AI-assisted"
  automated_label: true # X Automated label when posting is unattended
beat: "macro/rates/liquidity, translated for humans"
tilt: {signal: 0.25, chart: 0.15, education: 0.20, macro: 0.20, receipt: 0.10, event: 0.10}   # existing tilt law
pipeline: hybrid        # engine | hybrid | llm   (experiment axis)
model_tier: default     # default | opus          (experiment axis; effort via copywriter config)
cadence_profile: standard_ladder                  # D08 ramp + 2h ladder + 10-min floor all inherited
context_packs: {chronicle: [short, medium], desks: [macro, rates]}
memory: data/marketing/personas/macro_wonk/theses.jsonl
scorecard: {promote_after: {weeks: 4, min_engagement_rate: 0.015, min_follower_quality: 0.3},
            kill_after: {weeks: 8, engagement_rate_below: 0.005}}   # pre-registered at charter time, per persona
```

## 4. Thesis memory (the long-interval answer)

`data/marketing/personas/<id>/theses.jsonl`, append-only: `{id, opened_at, claim (plain-word), tickers, invalidation (level/condition), review_at, status: open|hit|invalidated|expired, reopened_post_ids[]}`. Sources: only calibrated engine/signal surfaces may seed a thesis (LLM never originates — house law); the persona *voices* it. The reopen scheduler emits draft "update on my <X> call" items into the outbox at `review_at` (and on invalidation triggers via the existing tape gate machinery). Effects: long-horizon continuity the operator asked for, per-persona public receipts, and a natural anti-repetition brake (a persona with 4 open theses talks about *them*, not the same breadth stat daily).

## 5. Content pipeline matrix (the experiment the operator sketched)

Axes (one varied at a time per persona, AM-R7): **pipeline** engine-only (voice-v3 templates) / hybrid (template skeleton + LLM voice pass) / full-LLM (copywriter with codex + chronicle pack + memory); **model/effort** default vs opus, effort low vs high on LLM lanes; **cadence** ladder density within D08 caps; **archetype** across personas. Weekly scorecard rows (extend metrics poller #3346 per account) feed promote/kill gates (§3 spec). Measurement lives in Growth-Science-owned ledgers (no self-grading, lobe law). Content mix guards: engine-only share ≤ tilt cap per persona; every LLM post passes cheese-test + persona banned-vocab + disclosure lint; signal posts keep the invalidation+disclosure cue words (Sentinel lexicon law).

## 6. Scale ladder (AM-R2 operationalized)

| Stage | Accounts | Gate to advance |
|---|---|---|
| Now | 6 configured / 1 live | — (in flight, D02) |
| S1 | +3–4 pilots (1 character, 1 specialist, 1 zh-voice, optional meme) → ≤10 total | Each pilot passes W3 §0; network zero warnings 4 consecutive weeks |
| S2 | Winners scaled (cadence/lanes), losers retired; still ≤10 handles | ≥2 personas hit promote gates; dedup radar clean streak |
| S3 | Publication accounts (Media program) + Verified-Org affiliation badges if purchased → 15–25 surfaces | Media W2 live; operator ruling + budget for Verified Org |
| S4 | Labeled automated utility feeds (per-market data feeds) if wanted → higher N | Explicit operator ruling; each feed X-Automated-labeled; separate prereg |

Retired handles are parked, never content-recycled. Any step that would exceed ~10 operator-run editorial handles without the S3/S4 mechanisms requires a fresh operator ruling against then-current X policy — hard-coded as a Sentinel config assertion (`max_editorial_accounts: 10`).

## 7. Waves

| Wave | Ships | Model lane |
|---|---|---|
| **W1** | Persona spec loader + validation (`engine/marketing/personas.py`), 6 existing desks migrated (zero-diff), 3 pilot codexes (main-loop/Fable authored), admin Persona Roster panel | Opus `builder`; codexes NOT delegated |
| **W2** | Copywriter context injection (codex+pack+memory), thesis ledger + reopen scheduler → outbox kinds, **post-time cross-account near-dup radar** (shingle store keyed by (cashtag, template-family, 24h) across ALL accounts), per-persona validator profiles | Opus `builder` |
| **W3** | Pilot go-live runbook: operator account creation/warm checklist, Buffer channel wiring, D08 ramp arming, scorecard poller per account | Operator + `builder` |
| **W4** | Scorecard→promotion engine (gates from spec, auto-narrow on warnings — extends `authority.py` should_narrow), weekly persona report card in admin | Opus `builder` |
| **W5** | S2/S3 scale wave per §6 gates | Ruling-gated |

## 8. Risks (printed)

- Pilot personas may simply not grow — the gates make that a cheap, legible kill (8 weeks, known cost), and the codex/memory machinery transfers to the survivors.
- Character voices drift toward cringe under LLM generation — codex banned-lists + cheese-test + weekly human skim (operator or main-loop) on a 10-post sample per persona.
- X policy shifts (label rules, account caps) — per-account policy adapter + `max_editorial_accounts` assertion localize the response; the network narrows, never dies as a graph.
- Buffer per-channel cost (~$6–12/mo/channel) + 2026 API pay-per-use economics are real at S3+ — revisit posting rail per account at W3 with live numbers.
