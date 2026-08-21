# GD-2R1 Commission — semantic-correctness repair of the settled envelope (pre-acceptance)

**Commissioned by:** Sol post-merge review 2026-08-19 (after #6026 merged as e6a3fcd6e094)
**Wave:** `WS:GREY-DEER-RISK-INTELLIGENCE` GD-2R1 · **One narrow PR** on the merged GD-2 surface.
**Standing:** GD-2's Gate 8 (production acceptance) is BLOCKED until GD-2R1 merges; Gate 8
then runs on the REPAIRED production render. GD-3 starts only after that. Do not change any
raw source state.

## §0 Acceptance gates (each is Sol's ruling verbatim in intent — not done unless)

1. **FRAGILE, not TRANSMITTING, from dislocation alone.** Leadership Crack
   `BROKEN/dislocation` by itself maps to `hazard_stage: FRAGILE` — never TRANSMITTING.
   Dislocation means cohort damage while the index holds; a `TRANSMITTING` stage requires an
   INDEPENDENT settled transmission source confirming current transmission. With no such
   source mapped in V0, TRANSMITTING must be unreachable from LC alone.
2. **The Grey Deer lifecycle clock is not the source's onset clock.** V0 `stage_since` may
   NOT reuse Leadership Crack's retrospective `state_since`. Keep the source onset inside
   `provenance` (per-source detail), and keep the envelope's lifecycle clock
   (`hazard_summary.stage_since`) **null** until a lawful first-observed episode transition
   exists (an episode lifecycle is GD-3+/expert territory; V0 has none).
3. **Required-source null law tightened.** A REQUIRED fresh source whose state cannot be
   mapped must null the hazard stage. An optional calm source can never yield `NONE` while a
   required source is unmapped. (`NONE` continues to require fresh required coverage + an
   explicit no-active-hazard result.)
4. **No behavioral copy while zero policies exist.** Remove "Watch — don't chase",
   "Ignore — nothing to act on", and any other action-instruction stance from the band and
   drawer. Replace with descriptive market-read/coherence language plus the literal state
   "no Grey Deer policy active" (EN/ZH equivalents). Behavioral guidance returns only when a
   registered policy exists to carry it.
5. **Coherence scoped to market reads only.** `coherence_state` and every agree/disagree
   surface statement describe the MARKET READS (trend vs hazard evidence) only. Capital
   policy is orthogonal — it must not be presented as agreeing or disagreeing with them
   (the posture row may not participate in the spine's agreement encoding).
6. **Permanent fixture updated, sources unchanged.** The 2026-08-18 fixture now expects:
   `RISK_ON 76 + LC BROKEN + Risk Radar calm → hazard FRAGILE / coherence CONTRADICTORY`,
   authority all false, `stage_since` null. The raw source states in the fixture are
   byte-identical to before — only the expected composition changes.
7. All existing GD-2 §0 gates keep holding (pure composer, authority hard-false, null ≠
   NONE ≠ 0, order invariance, byte stability, no risk_state arithmetic, EN/ZH + dark/light
   + 390/768/1440 with refreshed crops for the changed copy/states).

## Scope

`engine/risk_envelope.py` (stage mapping, stage_since, required-source null law, coherence
scoping), `templates/_risk_envelope_band.html.j2` / `.css.j2` + the copy strings
(behavioral → descriptive), `tests/test_risk_envelope.py` + the updated fixture
expectations, regenerated `site/riskdata/risk_envelope.json` + `data/risk_envelope/latest.json`,
refreshed `verify_shots/gd2_envelope_*` crops. Nothing else — no new sources, no schema
version bump (semantics tighten within v1; document the mapping change in the module
docstring), no synapse changes.

## Stop conditions

If FRAGILE-vs-TRANSMITTING cannot be expressed without inventing a new transmission source —
stop; V0 simply never emits TRANSMITTING. If any gate seems to require touching raw source
artifacts or Prophet/Radar paths — stop and return to Fable. scripts/**-adjacent edits keep
the authority-changing merge discipline.
