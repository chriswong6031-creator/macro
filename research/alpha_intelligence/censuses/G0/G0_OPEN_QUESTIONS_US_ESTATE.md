# GROK-G0 — Open Questions

**Executed by macro-fleet researcher (sonnet) on FABLE-00 commission, 2026-08-19; Grok lane was undispatched.**

These are the questions `WS:EARNINGS-INTELLIGENCE-OS` (the Earnings owner) must adjudicate before any
G-wave build is authorized — none are answered here, per the commission's read-only/research-lane
scope. Any future G-wave build queues behind E2 under this owner; there is no independent G build lane
(commission WHY clause).

## Q1. Where does the frontier-state object live, and under what authority?
`event_workspace.v1`'s existing two-timestamp lifecycle pair (`observed_at`/`source_available_at`,
CODE VERIFIED `event_workspace.py:234-241`) is the closest existing precedent, but it is ONE pair per
lifecycle state, not eight named frontier states. Does a G-wave (a) extend `event_workspace.v1`'s
schema (a contract change to a live, published object — `DEC:EARNINGS-EVENT-WORKSPACE-PUBLICATION-
CONTRACT` would need to be revisited), (b) mint a new sibling object under the same
`company_intelligence/` prefix, or (c) live entirely outside `event_workspace.v1` as a derived,
context_only annotation the way `expectation_state.py` does today? This census recommends none of the
three — it names the choice as unresolved.

## Q2. Does the frontier vocabulary conflict with the frozen `EVENT_STATES` enum?
`events.py`'s `EVENT_STATES` (`discovered`, `scheduled`, ..., `distributed`, `cancelled`) is a CLOSED,
tested enum with an explicit transition table (CODE VERIFIED, `events.py:44-69`). The commission's
PRE_EVENT→ANALYST_REVISION_STATE vocabulary describes a different axis (information availability,
not event lifecycle) but a careless implementation could conflate the two. `G0_INFORMATION_FRONTIER_
SPEC_DRAFT.md` §0 proposes treating the frontier states as a read-only derived VIEW rather than a new
enum member — this needs the owner's explicit ruling, not a research-lane assumption.

## Q3. How does a frontier-state build interact with the `basis_match` legal gate?
`event_workspace.py:272-278` refuses to mint `beat`/`miss`/`beat_miss` on any delta unless
`basis_match is True`, and refuses `basis_match is True` at all ("not minted in E1 without a licensed
consensus") — CODE VERIFIED. Several of the casebook's most useful classes (headline beat/deep
weakness, headline miss/deep strength, basis mismatch) are DEFINED in terms of a beat/miss verdict.
Does a G-wave (a) wait for a licensed consensus source before it can legally classify any event into
these classes in production, (b) build the frontier-state timing infrastructure now while leaving
beat/miss classification display-only/manual/research-tier (the way the casebook itself does — every
class label in `G0_POST_EVENT_CASEBOOK.md` is this research session's own read of public reporting, not
a repo-computed verdict), or (c) something else? Not answered here.

## Q4. Is a price/options reaction join in scope for ANY future wave, or permanently excluded?
`promotion.py:52` currently forbids `market_data`, `market_reaction`, and `trading_action` as inputs to
the Earnings claim/promotion graph — CODE VERIFIED. This is a deliberate, tested boundary (the E0
freeze), not an oversight. A reaction-geometry build is, definitionally, about joining price/options
reaction to earnings events. Does the Earnings owner intend to relax this boundary for a G-wave (through
a new DEC record, analogous to how `expectation_state.py` was allowed to exist as a SEPARATE,
disconnected, display-only plane), or does "Post-Event Reinterpretation" stay entirely on the document/
disclosure side (frontier timing + claim contradiction, no price join at all)? This is the single
highest-leverage scope question for the whole G-wave and this census does not answer it.

## Q5. What closes the options-reaction audit gap?
This session found no earnings-specific options join via targeted grep, but did NOT open each of the
~20 `engine/options_*.py` modules to rule one out definitively (§`G0_REACTION_GEOMETRY_INPUT_MATRIX.md`
§2). Before any G-wave scopes an options-reaction input, someone should run a bounded, dedicated census
of that options engine specifically for earnings-date joins — a distinct, smaller research commission
from this one.

## Q6. What closes the FILING vs FULL_RELEASE vs HEADLINE_AVAILABLE timing gap?
No ingester in the estate currently distinguishes the newswire headline flash from the full EDGAR
Exhibit 99.1 body from the eventual 10-Q/10-K reconciliation as three separately timestamped events for
the SAME issuer-quarter (§`G0_EVENT_CLOCK_AND_CONTRACT_CENSUS.md` §2, §`G0_INFORMATION_FRONTIER_SPEC_
DRAFT.md` §2.1). Does the owner consider HEADLINE_AVAILABLE worth building (it would likely require a
new, low-latency newswire/8-K-flash collector), or is FULL_RELEASE (`earnings_release/binding.py`'s
existing acceptance-timestamp discipline) an acceptable first frontier boundary for a G-wave, treating
"headline vs full release" as a refinement for a LATER wave?

## Q7. What is the rights/licensing posture for a wider historical casebook?
This census's casebook (`G0_POST_EVENT_CASEBOOK.md`) cites public news reporting (CNBC, Variety,
Forbes, company press releases, HBS case materials) under fair-use-scale research citation, not bulk
reproduction. A production-grade casebook with 60+ fully-verified, receipt-grade rows would likely need
either (a) a licensed historical price/options data vendor (to compute reactions directly rather than
citing secondary reporting of them), or (b) continued reliance on public reporting at a much larger
search-budget scale than this session used. Neither is decided here — this is a RIGHTS RISK named for
the owner, not resolved.

## Q8. Should `expectation_state.py` be treated as the G-wave's starting point?
It is the one place in the estate that actually computes price reaction to an earnings event today, is
already PIT-disciplined, and is already display-only/context_only. It is also structurally
DISCONNECTED from `event_workspace.v1` (no shared `event_id`, different directory, different authority
note) — `DSC:EARNINGS-WIRE-AND-CI-DIVERGE-ON-THE-SAME-ISSUER` (cited, not re-verified this session
beyond its existence as a discovery key in the WS record) already names this exact split-plane pattern
for a different pair of modules. Reconnecting `expectation_state.py` to the Earnings claim graph (vs.
building a THIRD disconnected reaction plane) is a design question for the owner.

---

# RETURN PACKET (commission-mandated closing section)

## MISSION
Audit Earnings Intelligence + FIF + market-reaction capabilities and produce the event-clock and
historical casebook needed for a Post-Event Reinterpretation extension under the existing Earnings
owner (`WS:EARNINGS-INTELLIGENCE-OS`). Read-only, research-lane, no build, no trading signal, no
Prophet change, no new Earnings store.

## WHAT I VERIFIED
- The full Earnings Intelligence OS ownership/freeze state (`WS-EARNINGS-INTELLIGENCE-OS.md`), its
  `owns_paths`, `do_not_redo` list, and wave status (E0 frozen, E1/E1P done+live, E2 `todo`).
- `event_workspace.v1`'s schema, its `basis_match`/beat-miss legal gate, its lifecycle-timestamp pair,
  and its PIT ordering invariant (`observed_at` cannot precede `source_available_at`).
- `engine/earnings_release/`'s filing-vs-event identity model, acceptance-timestamp normalization, and
  byte-replayable span-receipt discipline.
- FIF-1R3's frozen status (git log receipts) and its bitemporal source/recorded-cutoff pattern.
- `collectors/yf_analyst.py`'s current-snapshot-only (not historically PIT) nature and its forward
  accrual mechanism.
- `digest.py`'s forced-empty `market_reaction` typed absence and `promotion.py`'s explicit ban on
  `market_reaction`/`market_data`/`trading_action` as promotion inputs.
- `engine/expectation_state.py` as the one live, display-only, PIT-disciplined price-reaction
  computation in the estate, and its structural disconnection from the Earnings claim graph.
- The E0 Capability Ledger's own state-tagged census (`research/earnings_intelligence/
  E0_CAPABILITY_LEDGER.md`) as an authoritative, dated (2026-08-16) predecessor artifact, cross-checked
  against this session's own independent reads of `digest.py`/`promotion.py`.
- 18 distinct historical earnings-reaction events via WebSearch against named publishers, each cited
  with URLs, feeding 29 of the casebook's 48 rows.
- 10 academic papers via WebSearch against publisher/citation-index pages, each with confirmed
  author/year/venue.

## WHAT I COULD NOT VERIFY
- Any `data/` parquet's actual contents, row counts, or freshness (this worktree is sparse; `data/`,
  `site/`, `mockups/`, `verify_shots/` are off disk, and the commission forbade running
  `worktree_sparse.py` to pull them).
- Whether any of the ~20 `engine/options_*.py` modules independently join options data to an earnings
  event date under a non-obvious name (grep-only search, not exhaustive).
- The exact single-quarter attribution for the Peloton GAAP-miss/adjusted-EBITDA-beat casebook row
  (search results returned overlapping figures across two releases).
- The combined-magnitude figure for Snap's May+July 2022 pre-announcement-plus-print sequence (two
  individually-sourced figures, no single primary source for the combined number).
- Terminal (`terminal/` repo) transcript-search/Q&A-filter behavior beyond what the E0 ledger already
  reported — cross-repo, out of this commission's scope.
- 32 of the casebook's 60-target rows — the shortfall is stated in `G0_POST_EVENT_CASEBOOK.md` §Honesty
  declaration rather than closed with fabricated or unverified-magnitude rows.

## CODE / SOURCE RECEIPTS
Representative sample (full receipts distributed across all six output files):
- `event_workspace.py:272-278` — beat/miss forbidden without licensed `basis_match`.
- `event_workspace_build.py:150-153` — `observed_at` cannot precede `source_available_at`.
- `digest.py:397-400` — `market_reaction` forced to `{"status": "not_joined", ...}`.
- `promotion.py:52` — `_FORBIDDEN_INPUTS` includes `market_data`, `market_reaction`, `trading_action`.
- `events.py:44-69` — closed `EVENT_STATES` enum + transition table; `blocked_rights`/`source_missing`
  reserved as coverage states, not event states.
- `earnings_release/binding.py:14-28,57-76` — filing-vs-event identity; acceptance-timestamp
  normalization from EDGAR's own clock.
- `collectors/yf_analyst.py:9-21,71` — display/context-only, current-snapshot-not-historical-PIT.
- `engine/fundamental_forensics/financial_intelligence_packet.py:88-90` — bitemporal
  `GOLDEN_SOURCE_CUTOFF`/`GOLDEN_RECORDED_CUTOFF` pattern.
- `git log ef2554c9909f` / `e2a584496b08` — FIF-1R3 freeze commits, confirmed via `git log`.
- `research/earnings_intelligence/E0_CAPABILITY_LEDGER.md:40,57,59` — market reaction `SPEC_ONLY`; Q&A
  exchange structure `PARTIAL`, "no exchange object"; non-answer detection `NOT_BUILT`.

## OUTPUT ARTIFACTS
- `research/alpha_intelligence/censuses/G0/G0_EVENT_CLOCK_AND_CONTRACT_CENSUS.md` (244 lines)
- `research/alpha_intelligence/censuses/G0/G0_POST_EVENT_CASEBOOK.md` (235 lines)
- `research/alpha_intelligence/censuses/G0/G0_INFORMATION_FRONTIER_SPEC_DRAFT.md` (95 lines)
- `research/alpha_intelligence/censuses/G0/G0_REACTION_GEOMETRY_INPUT_MATRIX.md` (73 lines)
- `research/alpha_intelligence/censuses/G0/G0_ACADEMIC_RESEARCH_REVIEW.md` (184 lines)
- `research/alpha_intelligence/censuses/G0/G0_OPEN_QUESTIONS_US_ESTATE.md` (this file)

## ASSUMPTIONS
- That the E0 Capability Ledger (2026-08-16, code base `3b16672fcfee`) remains substantially accurate on
  current `origin/main` (`aa9ee6cd3f68`, 2026-08-19) for the specific rows this census independently
  re-verified (`digest.py`, `promotion.py`, `events.py`) — confirmed true for those rows; NOT
  independently re-verified for every row in that ledger (e.g. the Distribution/Consumers section was
  not re-audited here).
- That "well-documented historical earnings events" in the commission's CASEBOOK instruction permits
  citing public news reporting rather than requiring direct historical intraday/options data (which is
  unreachable in this sparse worktree) — treated as a reasonable reading of the instruction's "public/
  web primary sources" clause, not verified with the commissioning agent.
- That INFERRED casebook rows without numeric magnitudes are more useful (for demonstrating class
  coverage) than dropping those classes entirely — a judgment call favoring showing the shape of the gap
  over hiding it; the alternative (dropping to fewer classes shown) was considered and rejected as less
  transparent.

## PIT RISKS
- The `data/narrative/analyst_snapshots.parquet` accrual window is UNKNOWN in this session — any
  ANALYST_REVISION_STATE backtest before its true start date would silently look PIT but is not.
- `earnings_release/binding.py`'s acceptance-timestamp discipline guarantees DOCUMENT identity PIT
  correctness but says nothing about WHEN a downstream consumer actually processed the body — a
  frontier-state build that conflates "acceptance timestamp" with "system recorded_at" would overstate
  historical availability.
- Every casebook magnitude is as-reported by 2024-2026-era news outlets; none were independently
  recomputed from raw tick/quote data — if any of the cited outlets' own numbers were later corrected,
  this casebook would carry the stale figure without knowing it.

## RIGHTS RISKS
- FIF-1R3 (`engine/fundamental_forensics/`) is Sol-frozen; this census treated it as read-only and made
  no proposal to alter it, but any future G-wave that wants to JOIN FIF facts to earnings events would
  need to re-open that freeze under its own authority, not under a G-wave's.
- The casebook cites public news reporting under research-scale citation; a production casebook at
  60+ receipt-grade rows would likely need a licensed data source (Q7 above) rather than continued
  reliance on secondary news citation at scale.
- `collectors/yf_analyst.py` is explicitly `annotate_only` with a rate-limit policy tuned for a free,
  unlicensed data source (yfinance) — any G-wave build must not silently promote this to a licensed-grade
  consensus input.

## OPEN QUESTIONS
See Q1-Q8 above.

## RECOMMENDATIONS
(Offered as research-lane observations for the Earnings owner's adjudication, not as a build directive
— this census does not carry authority to recommend a build.)
1. Resolve Q1-Q4 (frontier-state placement, enum-vs-view design, `basis_match` interaction, and whether
   price/options join is in scope at all) before any implementation wave, since each materially changes
   what "done" means for a G-wave.
2. Treat `expectation_state.py` reconnection (Q8) as the cheapest available starting point if the owner
   decides a price-reaction join IS in scope — it already exists, is already PIT-disciplined, and is
   already display-only, unlike building a fourth new plane from scratch.
3. Commission the options-engine audit (Q5) as its own small, bounded research task before scoping any
   options-reaction input — this census's grep-level pass was not sufficient to close that question and
   should not be treated as a `NOT_BUILT` verdict.
4. If a wider casebook (60+ verified rows) is required before a G-wave prereg, budget it as its own
   multi-session research task with either a much larger WebSearch allowance or a licensed historical
   data source — this session's ~20-query budget produced 18 solidly-sourced events, which scales
   roughly linearly, not the order-of-magnitude jump needed to reach 60 without either more budget or a
   different data source.

## NO-BUILD / DO-NOT-INFER WARNINGS
- **Do not treat any casebook class label as a repo-computed verdict.** Every beat/miss/gap/fade
  classification in `G0_POST_EVENT_CASEBOOK.md` is this research session's own reading of public
  reporting, produced entirely outside `event_workspace.v1`'s `basis_match` legal gate. None of it may
  be cited as evidence that the gate should be relaxed, and none of it may be wired into production as
  though it were licensed-consensus-backed.
- **Do not infer that "no options join found" means "no options join exists."** §Q5 names this
  explicitly as an open audit gap, not a closed `NOT_BUILT` finding.
- **Do not silently promote `collectors/yf_analyst.py` or `data/narrative/analyst_snapshots.parquet`**
  beyond their current `annotate_only` authority on the strength of anything in this census.
- **Do not build against FIF/`engine/fundamental_forensics/` as though it were open for a G-wave.** It
  is Sol-frozen (FIF-1R3); this census's use of it was read-only contact, not an invitation.
- **Do not treat the INFERRED casebook rows (§3 of `G0_POST_EVENT_CASEBOOK.md`) as receipts.** They
  carry no verified magnitude and exist only to show class-coverage shape.
- **This census does not authorize a G build.** Per the commission's WHY clause, any future G build is
  the Earnings owner's wave, queued behind E2 — this document is an input to that owner's decision, not
  a decision itself.
