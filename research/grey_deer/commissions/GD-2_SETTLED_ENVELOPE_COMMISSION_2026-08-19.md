# GD-2 Commission — Settled Risk Envelope + three-answer Macro hero

**Commissioned by:** Sol continuation ruling 2026-08-19 (after GD-1 acceptance) → Fable COO
**Wave:** `WS:GREY-DEER-RISK-INTELLIGENCE` GD-2 · **One PR.** Separate from GD-4A.
**Authority at birth: DESCRIPTIVE ONLY.** No predictive probability, no ARMED/TRIGGERING
lead claim, no Prophet restriction, no size or execution authority.
**Governing law (precedence):** the architecture freeze → the Fable command packet §11 GD-2
→ this commission. On any conflict, stop and return to Fable.

## §0 Acceptance gates (not done unless)

1. `engine/risk_envelope.py` is a PURE composer (no I/O, no clock reads inside composition;
   inputs in, envelope out) implementing the freeze §5.2 `mastermind.risk_envelope/v1`
   skeleton, with every top-level authority boolean hard-false and
   `policy_actions_require_individual_authority: true`.
2. `scripts/build_risk_envelope.py` produces `site/riskdata/risk_envelope.json` (settled
   lane only) from EXISTING source-native states — Market State, Leadership Crack, Risk
   Radar, deterioration/breadth organs as available — with per-source clocks and
   freshness carried through. **No new weighted risk number anywhere.**
3. V0 hazard semantics: `hazard_stage` is descriptive and may be `null` (= not lawfully
   knowable with current coverage). `null` ≠ `NONE`; `NONE` requires fresh required
   coverage and an explicit no-active-hazard result. **Because birth authority forbids
   lead claims, V0 may emit only `NONE | FRAGILE | TRANSMITTING | BREAKDOWN | null`
   descriptive stages from settled same-session evidence — never ARMED/TRIGGERING (those
   are anticipatory claims reserved for promoted experts).** `repair_state`, `data_state`,
   `coherence_state` per freeze §2.1; `policy_summary.posture: NORMAL` with zero policies
   (no policy can exist yet — no registered policy objects exist).
4. **The GD-1 2026-08-18 dual-read is a permanent regression fixture**: a committed test
   fixture reproducing Leadership Crack BROKEN + Market State RISK_ON 76 + US Risk Radar
   calm 53.9 must compose to an envelope carrying measured_state RISK_ON alongside the
   broken-leadership evidence with `coherence_state: CONTRADICTORY` (or MIXED per the
   frozen vocabulary) — asserted verbatim, never averaged into a middle score.
5. Macro page shows the three answers as separate rows (measured trend + slow score /
   transition hazard with drawer evidence + freshness / capital posture as display
   summary of zero active policies), EN + ZH, dark + light, 390/768/1440 with no
   horizontal overflow. Falsifier language law: no "falsifier fired / refuted / 证伪" on
   user surfaces.
6. Synapse registration for the new artifact (copy the `market-state-latest` entry shape,
   `config/synapse.yml:755-782`; tier display, consumers listed) + regenerated
   `docs/SIGNAL_BUS.md` via its canonical generator. Legacy `engine/risk_state.py` score
   MUST NOT enter composer arithmetic.
7. Packet §11 GD-2 acceptance tests all present: source-order invariance; byte-stable
   semantic output on same inputs; stale/missing can only shrink confidence or null the
   stage (never a calm vote); Market State value preserved exactly; null ≠ 0 ≠ NONE.
8. Production proof after merge: a real settled session → generated envelope → live site
   → browser screenshot + DOM receipt showing source session, bundle id, measured state,
   hazard/data state. The PR body carries local render proofs (crops at the three
   breakpoints, EN/ZH, dark/light); the post-merge nightly render completes the proof and
   is verified by the owning session before the wave is called done.

## Scope (owned paths this PR)

`engine/risk_envelope.py` · `scripts/build_risk_envelope.py` ·
`site/riskdata/risk_envelope.json` · macro hero integration via the existing
`scripts/build_site.py` `_dash.render(**vm, mode="macro")` composition (write at
`build_site.py:6340`, render at `:6945`) · `config/synapse.yml` + generated
`docs/SIGNAL_BUS.md` · `tests/test_risk_envelope*` + the CI wiring for the new test files
(fold into an existing wired suite's `run:` step — a new `tests/test_*.py` that no `run:`
step names reds `legacy-job-workflow-yaml`; adding it to an existing named suite avoids
editing the manifest structure).

## Archaeology you inherit (verified 2026-08-19, cite-checked)

- Settled riskdata builders run inside daily.yml's "run regime engine + build dashboard"
  step (`scripts/ci/daily_engine_regime_dashboard.sh:29` engine.run, `:91` build_site);
  `engine/risk_brain.py` has its own daily.yml step (~`:4020`). Your builder joins the
  same settled lane (invoke from build_site or the shared step — mirror
  `engine/risk_radar_scorecard.py`'s dual `data/` + `site/riskdata/` atomic write).
- Market State artifact: `data/market_state/latest.json`, persist at
  `engine/market_state.py:1270-1327` with a `freshness` object and an asof no-regress
  guard (`:1284-1291`). Consume it source-native; do not recompute it.
- Contracts convention: `contracts/*.schema.json` exists — ship
  `contracts/risk_envelope.schema.json` for `mastermind.risk_envelope/v1`.

## Non-goals / stop conditions

No live lane (`site/live/` is GD-3, gated on GD-2 production acceptance). No policies, no
sidecars, no alerts, no Terminal/Portfolio work, no Prophet/Radar path edits
(`engine/entry_radar/**` fenced — #5925 production proof outstanding). No edits to
`.github/ci/legacy-jobs.yml` structure. No LLM fields with authority. If the composer
cannot express a state without a new store or a fused number — STOP, return to Fable.
`scripts/**` edits make the PR authority-changing: verify main's latest ci baseline is
green before merging.

## Worktree law

Full checkout required before touching `site/`/`data/`: `python3 scripts/worktree_sparse.py full`.
Run `python -m scripts.check_template_site_sync --fix` if any paired plain-copy asset is
touched. Never `git add -A` an unexpected `data/`/`site/` diff.
