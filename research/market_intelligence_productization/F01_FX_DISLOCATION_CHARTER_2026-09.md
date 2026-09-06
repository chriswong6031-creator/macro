# F01 — FX Dislocation Charter (2026-09)

Scope: MO-PAID-025's `next_bounded_child` ("DEFER — no FX-dislocation spec exists; charter before build").
Authority ceiling: research_only. This document authorizes NOTHING to be built; a later build packet needs its own Sol/Chairman authority.
Verified in: /Users/chriswong/Documents/Cluade/macro-main @ 16b3734c9d87, 2026-09-05.

## 1. Purpose & authority

This is a charter, not a build. It names what an FX-scoped dislocation gauge would be, distinguishes it from the existing cross-asset Gate-1 switch, and lists the preconditions a future build packet must clear. It contains no code, no gauge, and no thresholds tuned against data. Authority ceiling: `research_only`. Nothing in this document may be read as approval to build; a build packet must obtain its own explicit authority above this ceiling.

## 2. The one-line distinction (MO-PAID-025's literal acceptance test)

> The cross-asset Gate-1 switch in `engine/dislocation.py:260` decides whether the US policy PUT is present, from `sahm` + `breakeven_10y` + `SPY` — three US macro/equity inputs and zero FX inputs — whereas an FX-scoped dislocation gauge would measure whether the FX plumbing itself is priced away from its own no-arbitrage anchors (covered-interest-parity basis, cross-currency basis, forward-points vs the rate differential), so the two answer different questions on different inputs and neither can substitute for the other.

## 3. What an FX dislocation IS (candidate measurable objects, named, NOT built)

| candidate | what it would measure | data availability |
|---|---|---|
| CIP deviation / cross-currency basis | the gap between the covered-interest-parity forward rate and the observed forward rate, in bps — the canonical post-2008 FX-plumbing-stress measure | `not_yet_available` — no forward-rate or cross-currency-basis collector exists; would need a named collector under `scripts/collect.py` and a `store` group, neither of which is registered today |
| forward points vs rate differential | whether FX forward points track the covered interest-rate differential implied by `fx_rates_short` (already collected, `engine/forex_inputs.py:45,139`) | `not_yet_available` — the rate-differential leg exists (`fred` group `fx_rates_short`), but no FX forward-points series is collected, so the comparison cannot be built today |
| onshore-offshore spread | divergence between an onshore-quoted rate and its offshore (NDF/CNH-style) counterpart | `unknown` — the nearest existing kin is `_cnh_basis_series` at `engine/forex_regime.py:353`, but that is a feature INSIDE a display-only scenario reader (`fx_stress_regime`/`fx_kinematics_table`), not a standalone dislocation gauge, and this charter does not verify whether its underlying series could be repurposed without further collector work |
| NDF-deliverable spread | pricing gap between a non-deliverable forward and its notional deliverable-forward equivalent, where one exists | `not_yet_available` — no NDF collector or store group exists |
| peg/band stress | distance of a managed-peg or band currency from its stated band edge, and rate-of-change toward it | `not_yet_available` — no peg-band reference table or collector exists |

The builder has not claimed availability that is not backed by a named `store` group or a named collector at `scripts/collect.py:<line>`; every row above states `not_yet_available` or `unknown` rather than asserting a series exists.

## 4. Vocabulary reuse (mandatory)

This charter adopts `engine/dislocation.py:143 evidence_scope`'s `covered | partial | uncovered | none` coverage vocabulary rather than minting a parallel one, and adopts the display-only honesty posture already stated at `engine/forex_regime.py:1-33`: past-tense conditional base rates, Wilson intervals, `n_eff`, never a forecast. Any future FX-dislocation build inherits both vocabularies rather than inventing new ones.

## 5. Non-goals / prohibitions

No BUY/SELL collapse of any FX-dislocation read. No LLM-originated signal, score, escalation, or rank — this stays true of any future build under this charter, not only of this document. No trading authority is granted by naming a candidate measurable object. No new nav header or third page family (only the two existing families in `templates/_site_nav.html.j2` and `templates/_public_nav.html.j2` may ever carry a surface, and this charter creates no surface at all). Nothing here may be promoted to authority without a pre-registered promotion gauntlet.

## 6. Gate to build

A future build packet under this charter must satisfy, before it starts:

1. At least one CIP/basis series with a named, rights-cleared source. Today this is `not_yet_available` — §3 finds no basis collector, and even if one existed it would inherit the same unresolved Yahoo-spine rights posture recorded in `F01_FX_COMMODITY_SOURCE_RIGHTS_AND_DEPTH_2026-09.md` §4 V-1 for any yfinance-sourced leg.
2. An owner workstream. MO-PAID-025's `current_owner` literally reads "no FX desk owner" — that gap is unresolved by this charter.
3. A pre-registered promotion gate (per the epistemics standing law: gauntlet applies at promotion to authority, not at build).
4. Explicit authority above `research_only` for the specific build packet.

## 7. Honest null

There is no FX dislocation gauge today, and this document does not create one. The reason is `not_yet_available`: the basis inputs it would need are not collected, and no FX desk owner exists. That is a gap we are naming, not a capability we are claiming.
