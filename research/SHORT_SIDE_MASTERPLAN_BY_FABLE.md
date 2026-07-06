# Short-Side / Breakdown Intelligence — Masterplan (by Fable)

**Chartered:** 2026-07-06, by `research/NW_RAILS_AND_TIER1_LOBES_PROGRAM_BY_FABLE.md` (W2 PR-5; docket L1).
**Status:** ACTIVE lobe, Phase-0. Display-only; nothing here may touch a scored-path surface until it climbs the ladder in §5.

---

## §1. Objective

The house identity is drawdown control with one validated reversal edge. This lobe answers the mirror question the stack has almost nothing on: **which names are showing distribution, failed-rally, or topping species — so we avoid longs, trim conviction, or (much later, if ever) hedge.**

Two scope fences, permanent:
- This is an **avoid/de-risk lens**, NOT a shorting-execution program. No short-sale mechanics, borrow costs, or squeeze risk modeling in scope; if a validated species ever motivates actual short exposure, that is a NEW charter with its own constitution work.
- Per docket L1 and RUL-P6 of the build program: **asymmetry is a question, never a premise.** Nothing below assumes bottoming edges invert. Phase-0 exists to measure whether they do.

## §2. The asymmetry ruling (RUL-P6, binding)

Every breakdown event is graded BOTH ways on the same bars: long-side terminal states (does the name keep working?) and short-side mirror states (does it break?). The readout is a **paired within-event contrast** — CIs on paired differences, never two independent samples. A world where breakdown events grade neutral-long AND neutral-short is a null; a world where they grade bad-long but not good-short is an *avoid* signal that never becomes a *short* signal. The ladder in §5 distinguishes those outcomes explicitly.

## §3. Species-inversion hypothesis space

The 13 entry species (`research/SETUP_SPECIES_MASTERPLAN_BY_FABLE.md` §4) inverted, with mechanism sketches and testability on current data. This table is hypothesis inventory, NOT registration — each species that graduates from this list gets its own prereg.

| Inv. | Mirror of | Mechanism sketch | Testable now? |
|---|---|---|---|
| S1⁻ Cohort Euphoria Distribution | S1 Capitulation Reversal | cohort-wide parabolic exhaustion → first cracks while index pinned; froth A4_parab is cohort-level prior art | YES (price/volume) |
| S2⁻ Donor Exhaustion | S2 Donor-Funded Bottom | the leader that funded the rotation cracks; B_leaddist / S3_leaders froth legs are prior art | YES |
| S3⁻ Escalation Window | S3 De-escalation Window | NOT A SPECIES — this is the Risk Radar's existing job; filing it here would be a WAVE misfiled as a lobe (docket §1). Excluded. | — |
| S4⁻ Two-Clock Rollover | S4 Two-Clock Re-Arm | weekly+daily clocks rolling over from cycle high; cycles ladder rollover-veto is prior art (#1500) | YES |
| S5⁻ Coiled Breakdown | S5 Coiled Thrust | tight range under distribution resolving DOWN; inverted coil | YES |
| S6⁻ Failed-Rally Fuel | S6 Failed-Fire Fuel | failed reclaim after a stopped fire = continuation of the break (this is BD-2 in Phase-0) | YES |
| S7⁻ RS-Deterioration-Before-Price | S7 RS-Before-Price | relative weakness precedes absolute break; NOTE: S7 is already registered two-sided in the species masterplan — coordinate, don't duplicate | YES (pending W0.4 RS series) |
| S8⁻ Revision-Acceleration Top | S8 Revision-Deceleration Bottom | estimate momentum turning down while price holds | EDGAR-gated |
| S9⁻ Good-News Immunity | S9 Bad-News Immunity | name stops responding to good news = distribution tell | news-coverage-gated |
| S10⁻ Margin-Peak Fade | S10 Margin-Inflection Reclaim | peak-margin deceleration | EDGAR-gated |
| S11⁻ Buyback Exhaustion | S11 Buyback-Floor Washout | repurchase support fading / dilution onset | EDGAR-gated |
| S12⁻ Rate-Pressure Duration Break | S12 Rate-Relief Rebound | duration-sensitive names breaking on rate impulse | needs episode floor (≥8) |
| S13⁻ Within-Sector Leader Fade | S13 Within-Sector Reversal | sector leader fading vs its own sector | YES |

Phase-0 (§4) deliberately tests only three cheap, price-based definitions (BD-1 ≈ S1⁻/S2⁻ family at per-name scale; BD-2 = S6⁻; BD-3 = an EMA8-anchored arming condition adjacent to S4⁻). Everything else waits for Phase-0 base rates.

## §4. Phase-0 — the breakdown event tape

Built by `scripts/research/dump_breakdown_events.py`. **The numeric freeze authority is `research/short_side/BD_PHASE0_PREREG.md`, committed before the script runs.** Phase-0 produces an event tape with paired two-sided grading and base rates. No signal, no site surface, no chip, no synapse consumer. Output: `data/research/breakdown_events.parquet` (Mac-local, gitignored) + committed vintage-stamped summary JSON.

## §5. Ladder (identical to entry species, short-side semantics)

`phase0 → accruing → validated → falsified | retired` × `unshipped → chip → ledger_fields → graded_bonus → gate_weight`, with the entry-species promotion bar unchanged: ≥5pp on the constitution axes at the declared horizon_class, episode-clustered bootstrap, BH-FDR q ≤ 0.10 within the wave family, both-halves sign-stable, per-name majority, n ≥ 300 per side. Short-side axes: the "stop-out" axis maps to adverse move (price UP against the avoid/short thesis); dead-money and cushion map to the mirror barriers per the prereg. **A species may validate as AVOID (long-side degradation) without validating as SHORT (mirror-side edge) — the ladder records these as separate claims and the chip vocabulary must say which.**

## §6. Evidence constraints (inherited, binding)

- **No PIT short interest.** `data/finra/short_interest.parquet` is latest-snapshot-only; `short_interest_history.parquet` is not a true vintage matrix. Short interest may appear as display context only, never as species evidence. The PIT accrual (Signal Commons W0) becomes usable ~2027+.
- FINRA daily short volume (`data/finra_short_volume/panel.parquet`) IS PIT-safe (never revised) and may be used as species evidence with its limited depth stated.
- Options tissue: GEXR is vol-conditioning weather with era-dependent sign (W-E1: 6/6 survive, sign flips Era1 vs Era2/3) — stop-width/context only, NEVER directional. Single-name gamma_regime is structurally constant (audit #29) — index/sector level only. CWIV Era3-only, skeptical prior. SKEW-decel and DOI are dead (W-E1).
- Froth/fragility gauge is import-locked to `engine/run.py` — any consumption goes through `latest["froth_fragility"]`, never a direct import.

## §7. Graveyard (seeded at charter, per house law)

- **EMA8 as auto-sell:** killed by the exit bake-off (joint DD-AND-capture 37–43% vs 70% floor). It survives only as a display tail-flag; in this lobe it is an ARMING INPUT to BD-3, never an action.
- **Exit-rule routing generally:** settled NO-GO — "drawdown control is an ENTRY problem." This lobe does not re-litigate; its exits/avoids are entry-side (don't take the long) or context (trim conviction display).
- **Short-interest crowding as signal:** Phase-0 verdict was no forward-return edge (~0.6pp worse drawdown at 63d, |t|≈2.3, not robust) — display-only forever absent PIT accrual.
- **Symmetric inversion as premise:** prohibited by RUL-P6; every claim of inversion must survive its own prereg.

## §8. Forward-ledger plan

Phase-0 is a static tape (no live accrual). If any BD definition graduates to `accruing`, it gets: a single-writer firings ledger under `data/reflexes/` conventions or a dedicated `data/short_side/<species>_forward.jsonl` (registered in synapse.yml, nightly-graded via the standard grading primitives with `terminal_state_short`), following the reversion-forward-ledger pattern (`scripts/oracle_reversion_forward_ledger.py`) — backtest grader and live grader must be the same function.

## §9. Status log

- 2026-07-06: Chartered (this doc + BD prereg committed). Phase-0 tape build dispatched.
