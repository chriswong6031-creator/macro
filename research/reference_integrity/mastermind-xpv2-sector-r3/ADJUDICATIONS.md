# XPV2-SC-R3A — Fable adjudications over the six-lane archaeology

Program: `WS:INSTITUTIONAL-PRODUCT-EXPERIENCE-V2` · Wave: `XPV2-SC-R3A` · Date: 2026-08-20
Inputs: `archaeology/lane_A_action_overview.md` … `lane_F_state_matrix.md` (six independent census dossiers, production-code-cited).
Authority precedence honored: production producers/payloads > production behavior > R2 review bundle > doctrine. The rejected R2 candidate HTML is never source authority.

These rulings are the frozen spec for Deliverables 1–6 and the attack tests. A builder may not soften, reinterpret, or extend them; a conflict discovered during build stops the build and returns here.

## A1 — Action lanes: SIX keys, FIVE columns
Production truth is six lane keys — `buy_now, buy_soon, on_the_run, take_profits, hold, avoid` (`scripts/build_sector_central.py:67-73`) — rendered as five columns because `hold`+`avoid` share the "Stand aside / 观望" column (`templates/_us_act_now_board.html.j2`). The handoff's "five action lane keys" refers to the five columns. The pack records both facts; the fixture preserves all six keys; attack tests pin the six-key list AND the five-column render.

## A2 — Moving/si_handoff: handoff presupposition REFUTED
`si_handoff.json` has exactly one writer (`scripts/build_baskets.py:590-597`) and one reader (`scripts/build_sector_central.py:379-384`), server-side at build time. It feeds the Overview hero, Money's `flow.cluster.regime` (baked into `#si-read-money`), and Explore's `basket_member_syms` — NOT the Moving view. Moving's canonical bindings are five nightly artifacts: `marketdata/rotation_events.json`, `marketdata/sector_fragmentation.json`, `marketdata/subsector_rotation.json`, `basketdata/oracle_turn_desk.json`, `basketdata/oracle_tape_onset.json`. Deliverables record THIS binding; the attack test "changes current Moving destination/source" pins the five artifacts. The pack README must carry this deviation from the handoff text explicitly.

## A3 — Map `reco` action-tags under a context disclaimer: recorded, flagged, NOT repaired
Production's Map board renders `theme_intel.themes[].reco` as Buy/Add/Hold/Trim/Avoid tags (`sector_central.html.j2:2941-2942`) beneath its own context-only disclaimer (`:2267`) — the same defect class the critics filed against the R2 mockup (DAC-001/002), live in production. Ruling: the fixture preserves production as-is; the producer binding matrix marks these fields `authority: CONFLICT (context surface rendering action vocabulary)`; the R3 design brief FORBIDS the designer from amplifying Map reco tags into action-lane authority. Production repair is out of scope (handoff non-goal) and is filed separately.

## A4 — Confluence tab order: DAC-005 drift claim REFUTED
Canonical order is the hard-coded DOM order S&P → Nasdaq → Russell → Baskets (`sector_central.html.j2:2499-2502`). The critic conflated the JS `DS` declaration order with tab order. The routing/capability contracts and the brief record the DOM order as law.

## A5 — Thin semantics differ by universe; basket coverage disclosure is BLOCKED_DATA
S&P "thin" (48) means gate-DROPPED — absent from the payload array, not "thin-but-listed"; the thin-but-listed wording (`templates/subsectors.js:220-222`, EN/ZH verbatim in lane E dossier) renders only when coverage carries a nonzero `n_thin`. `basket_confluence.json` coverage carries only `n_baskets` — no gateable/thin fields exist, so the honesty line cannot render on the Baskets tab. Ledger disposition: Baskets-tab thin/gateable disclosure = `BLOCKED_DATA` (producer emits no field). Nasdaq (12/12) and Russell (93/93) currently have thin=0; their thin-but-listed behavior is code-shared but unobserved — fixture records the zero state as-is.

## A6 — State matrix rulings
- **Correction/revision: UNREPRESENTED in production** (both surfaces). Ledger: `BLOCKED_DATA`. The fixture set includes a `correction/` entry documenting the absence (no invented UI state); the brief instructs R3 not to invent a correction affordance without a producer.
- **Confluence staleness: no enforcement exists** — only a baked relative `ticks` delta and a plain `as_of` string, zero threshold logic. Recorded as-is; fixture "stale" for Confluence documents current no-op behavior.
- **Overview stale guard fails open on malformed `as_of_utc`** (`sector_central.html.j2:1794-1795` — `isFinite` short-circuit returns not-stale). Recorded in the state matrix; repair filed separately (non-goal here).
- **Zero vs missing is sound** in production (`== null` / `is not none` idioms throughout); attack test "collapses missing to zero" pins the fixture's preserved nulls and the S&P row-identity rule, not a generic idiom grep.
- **Error-state copy collapse**: fetch-fail/malformed/5xx/401/403 are JS-distinguishable but share one user-facing string per surface (hydration `.catch` at `:3543-3612` is a silent no-op preserving the baked preview + sign-in disclosure). Recorded as production law for the access contract.

## A7 — Routing contract: reuse verbatim, seams recorded not repaired
R3 MUST reuse `templates/si_workspace.js` (six views; 21-entry `LEGACY_ANCHORS`; unknown-hash→Overview; empty-hash `replaceState('#overview')`; `#read-*` deferred trace-open with retry) plus the template's `resolveThemeHash()`. Recorded seams, filed separately, not repaired in this wave: (a) `#theme-*` resolves only at initial boot, never on later `hashchange`; (b) mobile ≤767px sticky top bar has no compensating `scroll-margin-top` on legacy targets; (c) `sc-top` and `forming-narratives` legacy anchor targets not confirmed as present DOM ids. Deep-link scroll is instant (`scrollIntoView({block:'start'})`, no behavior key) — the R2-era smooth-scroll concern does not apply.

## A8 — Forming Narratives: classified
Ranking/score is 100% deterministic (`engine/narrative_emergence.py` fixed-weight formula; no LLM). The single LLM-originated field is `ai_watch` (`engine/thematic_desk.py`, DeepSeek via `engine.master_brain._call_model`), printed verbatim as disclosed commentary and feeding no score/rank/gate — A7-compliant display-tier commentary. Per the handoff, the brief and binding matrix label the `ai_watch` field "model analysis"; the deterministic rank is NOT so labeled.

## A9 — Access/hydration law
The page's only premium wall is `site/premiumdata/sector_central.json` gating the Overview Act-Now board (`config.yml:7204-7206`: `gated:true, preview_rows:3`; freeze-time split preview=3/locked=29/total=44; counts computed off the FULL board regardless of gate state). Explore, Confluence, Map, Moving, Money payloads are ungated. Hydration: authenticated client fetches the premiumdata URL, matches by `data-ab-lane`/fold id; any `!r.ok` (401/403/5xx/offline) collapses to a no-op keeping the server-baked preview and the sign-in disclosure. Track Record ledger (`data/sector_central/calls.parquet`) advances only via the nightly gate (`engine.ledger_lane.nightly_advance_enabled()`), obeying the sole-advancer law.

## A10 — Attack-test placement law (moving-data trap)
Mutation/attack tests MUST assert against (a) the frozen fixture files under `research/reference_integrity/mastermind-xpv2-sector-r3/fixture/` and (b) code constants (builder lane list, `LEGACY_ANCHORS`, thin wording, gate config) — NEVER against live `site/`/`data/` artifacts, which the nightly rewrites (the merge gate must not ride moving data). SHA-256 receipts are recomputed from the fixture in-test. The new test file must actually be collected by a `gate: code` CI job (a `gate: data` home is advisory-only; a new suite left out of the pack map is grandfathered-dark) — verify collection, don't assume it.

## Capability ledger priors (builder fills the full inventory; these dispositions are fixed)
- All working destinations, all six views' journeys, 21 legacy anchors, `#read-*` trace, premium preview/hydrate, thin-but-listed wording (where fields exist), Bottoming Watch display-tier contract, Track Record/self-grader, Time Machine, Forming Narratives (with A8 labeling): **RETAIN**.
- Baskets-tab gateable/thin disclosure; correction/revision representation: **BLOCKED_DATA**.
- Nothing in this wave is REMOVE or RELOCATE. Any candidate for those requires a new ruling here first — no implicit deletion.
