# research/species/ — Species Pre-registration & Report Convention

This directory holds per-wave pre-registration and report documents for the Setup-Species
program.  Canonical program doc: `research/SETUP_SPECIES_MASTERPLAN_BY_FABLE.md`.

## Naming contract (§7 Governance)

Every wave that runs a species phase-0 or promotion measurement ships **two** files:

| file | when | contents |
|---|---|---|
| `<wave>_PREREG.md` | **before** any run | mechanism story, declared config grid, primary metric, pre-registered kill criteria, comparators, trial count registered in the trial ledger |
| `<wave>_REPORT.md` | **after** results land | full horizon grid (both classes), episode-clustered p-values, BH-FDR family correction across the wave, verdict, §8 status row entry, leak-audit section |

**The pre-registration is immutable once committed.**  Results are added to the report file
only; the prereg document is never edited to accommodate observed outcomes.

## Enforcement

- A wave PR that includes result data but no `<wave>_PREREG.md` is a protocol violation.
- A `<wave>_REPORT.md` that omits the fill-rule, known-date mapping, or forward-looking
  element enumeration (leak-audit section per §7) fails the wave gate.
- Species lifecycle transitions (`validation_status` changes in `data/species/registry.json`)
  require a `<wave>_REPORT.md` row and a §8 entry in the masterplan before merging.

## Existing files

- `MASTERPLAN_REDTEAM_RECORD.md` — the 41-agent red-team record from program birth
  (2026-07-03, 32 upheld findings applied to the masterplan).  Leave this file in place;
  it is the permanent audit trail for the program's initial design.

## Registry

The live registry lives at `data/species/registry.json` and is managed by
`engine/species_registry.py`.  Experiments-tab mirror entries are in
`data/experiments/registry_seed.json` (keys `species-<species_id>`).
