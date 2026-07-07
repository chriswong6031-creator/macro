# Final-3 Lobes — Partial Adoption, Kills, and Deferred Conditioning

**Source:** PR #1695 (PR-F3.1). Primary doc: `research/NW_FINAL3_LOBES_ADJUDICATION_AND_MASTERPLAN_BY_FABLE.md`. **Status:** canonical (RUL-SUCC-8).

## What was asked

Codex proposed upgrades to the last three "institutional realism" layers of the Neural Web (exit/trim, residual selection-trust, execution cost). A 7-PR build lane was proposed (PR-A..G). The docket fraction was ~55–65% duplicate/stale/forbidden. Fable was asked to adopt, reshape, kill, or defer each element.

## What was decided (the holding)

- **RUL-F3.1 (scope/cap):** no new lobe charter. Two-lobe cap stays L1+L3. All Final-3 work ships as R1-registered experiments, research-lane derivations, ops harnesses, or docs.
- **RUL-F3.4 (exit regret v2 — KILLED):** standalone `scripts/research/exit_regret_v2.py` killed as a governor bypass; 4/10 metrics already shipped in EXIT-GRID-1. The computable increments ride TRIM-GRID-1 and NET-REPLAY-1 instead.
- **RUL-F3.5 (TRIM-GRID-1 — ADOPTED):** ExitPolicy `scaled` enum formally amended to add composite partial-trim kind; exactly 6 frozen cells; `derived_from_surface=exit_grid_v1`; descriptive-only; promotion requires fresh OOS fires ≥ 2026-H2.
- **RUL-F3.9 (NET-REPLAY-1 — ADOPTED):** net-of-friction re-pricing of already-seen replay cells; gross and net always side-by-side; per-position size grid only (no book-level AUM claims); unmodeled frictions explicitly printed.
- **RUL-F3.10 (tax engine — KILLED):** `engine/tax_sensitivity.py` killed as over-engineering on unknowable inputs. Replaces with a scenario-rate table (symbolic rates only; printed as assumptions, not advice).
- **RUL-F3.11 (passport — KILLED):** the Realized-Decision Passport is not built; three passport-like objects already exist in the repo; revisit only after L2+L5 charters both live.
- **RUL-F3.6 (DISP-GATE-1 — ADOPTED with amendments):** feasibility/exclusion gate prints first; universe construction held fixed; realized-vol tercile added as a second covariate split. PASS enables a display flag only.
- **RUL-F3.8 (feature store/conditioning matrix — DEFERRED):** n-starved (a 7×6×7 matrix against a 25-episode-cluster floor is mostly empty); forking-paths-contaminating; not built now.
- **RUL-F3.3 (label law):** role/classifier labels must be computed from pre-outcome state only; `exit_helped_21`-style look-ahead labels are blocked as classifier targets.
- **RUL-F3.2 (exit referent honesty):** no held-position ledger exists; all exit metrics attach to fire events on the replay tape; every artifact and report must say "fire-tape counterfactual."
- **RUL-F3.14 (L7 dependency corrected):** Cash/Patience is blocked only on the two-lobe cap and a charter owner, not on missing machinery (WAIT-GRID-1 is the substrate).
- **RUL-F3.15 (exit-role taxonomy — charter-ready spec, not a build):** six-exit-problems taxonomy preserved as the future L2 charter's role vocabulary with a deterministic arbitration order; no nightly builder until an L2 slot frees.

## Tier mapping under the succession bench

| Decision | decision_class | Tier | Decider |
|---|---|---|---|
| Deny L2/L5 charters (cap consumed) | new_lobe_charter (denied) | **T2** if approving; denial = **T0** | Opus alone with case law scan |
| Kill exit_regret_v2 (governor bypass) | retire/reject | **T0** (ROUTINE) | Opus alone |
| Kill tax engine (over-engineering) | retire/reject | **T0** (ROUTINE) | Opus alone |
| Kill passport (redundant + premature) | retire/reject | **T0** (ROUTINE) | Opus alone |
| ExitPolicy `scaled` enum amendment | scoped_build amending frozen spec | **T1** (CONSEQUENTIAL) | Opus + completed packet |
| TRIM-GRID-1 (6 new cells, `replay` family) | new FDR cells within existing program | **T1** (CONSEQUENTIAL) | Opus + completed packet |
| DISP-GATE-1 harness authorization | scoped_build, display-flag-only outcome | **T1** (CONSEQUENTIAL) | Opus + completed packet |
| RUL-F3.8 defer (feature store) | deferred with come-back condition | **T0** (ROUTINE) | Opus alone |

## Lenses that did the work

- **Case law:** two-lobe cap blocked new charters; the existing EXIT-GRID-1 (15 pooled cells) meant exit regret v2 was building on an already-contaminated surface without `derived_from_surface` — the governor-bypass lens caught this.
- **Statistics:** label law (RUL-F3.3) caught look-ahead tautology in Codex's exit-role classifiers; RUL-F3.8 applied the 25-episode-cluster floor to the 7×6×7 matrix and found it n-starved.
- **Build feasibility:** red-team (Opus ×4) caught: no held-position ledger (RUL-F3.2), circular classifier labels (RUL-F3.3), PIT reconstruction infeasibility in the feature store, n-starvation in the conditioning matrix, uncalibrated cost model in NET-REPLAY-1 (fixed), third-passport redundancy (RUL-F3.11).
- **Collision:** DISP-GATE-1 was simultaneously built by two programs (#1696 gap-map PR-B2); replications converged (flip 31.4% vs 34.8%) and the DEFER-on-non-stationarity verdict held across both independent runs.
- **Ops budget:** net-of-friction re-pricing (NET-REPLAY-1) is a derivation over already-seen cells — zero new trial budget.

## Citable holding

A program adjudicating a large multi-item docket should kill forbidden shapes immediately (governor bypass, look-ahead labels, over-engineered unknowables), adopt verified clean items with explicit scope fences, and defer everything n-starved or cap-blocked with named unblock conditions — partial adoption is the expected and correct outcome, not a sign of a weak proposal.

## Ruling IDs

RUL-F3.1, RUL-F3.2, RUL-F3.3, RUL-F3.4, RUL-F3.5, RUL-F3.6, RUL-F3.7, RUL-F3.8, RUL-F3.9, RUL-F3.10, RUL-F3.11, RUL-F3.12, RUL-F3.13, RUL-F3.14, RUL-F3.15
