# Long-Hold Thesis Layer — A2 OOS-Analysis Freeze Anchor Note

**Status:** FREEZE ANCHOR — this note records the LH-R11.1 roster freeze event.
**Governing amendment:** `AMENDMENT_LH_R11_MULTI_FAMILY.md` (LH-R11.1)
**Freeze date:** 2026-07-06

---

## LH-R11.1 Freeze Anchor

Per AMENDMENT_LH_R11_MULTI_FAMILY.md §LH-R11.1:

> The roster freezes at the **commit of the OOS-analysis script** for the
> operative OOS window (mirrors OBJECTIVE §7 lock semantics).

**The commit that introduced `scripts/research/a2_oos_analysis.py` is the
roster freeze anchor.** The in-code `ROSTER` table in that script is the
authoritative frozen record. No family may be added to or removed from the
A2 roster after this commit without a ratified amendment.

---

## Roster summary

| # | Family id | m | Authority |
|---|---|---|---|
| F1 | `long_hold.fundamental` | 9 | `OBJECTIVE.md §5` (frozen W1 list) |
| F2 | `long_hold.washout_tf` | 10 | `WASHOUT_TIMEFRAME_HYPOTHESIS.md §4` |
| F3 | `long_hold.expect_drift` | 7 | `EXPECT_DRIFT_FAMILY_PREREG.md §2` |
| F4 | `long_hold.insider_sponsor_lh` | 3 | `INSIDER_SPONSOR_LH_FAMILY_PREREG.md §2` |
| **Σ** | | **29** | ≤ 40 (LH-R12) |

---

## Roster hash (machine-verifiable freeze record)

```
sha256: b52165f8c9227199ca55a68165c7d21b2e971526d6358e5289bf9a831430bcbc
```

Computed by `scripts/research/a2_oos_analysis.roster_sha256()`:
canonical serialization = sorted JSON array of all 29 hypothesis dicts,
keys sorted, no extra whitespace. Reproducible with:

```bash
python scripts/research/a2_oos_analysis.py --print-hash
```

Any change to the in-code roster changes this hash — providing a tamper-
evident record of the frozen state.

---

## No-run gate

The outcome-contact stage of `scripts/research/a2_oos_analysis.py` REFUSES
TO RUN unless BOTH conditions are met:

1. **Honest compounder episode-cluster count >= 25** (LH-R4 floor;
   `AMENDMENT_A2_G1_RETEST.md §1`). Projected ~2027-H2 at the observed
   ~14 clusters/year accrual rate.

2. **Explicit `--operator-ack` flag** passed on the command line.

This gate is unconditional and untunable. There is no environment variable,
config file, or code path that bypasses it. The refusal message is printed
to stderr and the process exits with a non-zero code.

**Contact rules until the gate clears:** No feature-outcome statistics may
be computed on the 2024+/OOS-2 cohort before the gate clears. Forward
accrual (label panel advancing nightly) is not "contact." Feature panels
may be computed for all fire dates (features are at-entry, outcome-blind);
only the join to 2024+ outcomes is forbidden pre-gate.

Reference: `AMENDMENT_A2_G1_RETEST.md §4`.

---

## What this note is NOT

This note does NOT edit, amend, or supersede any of the ratified documents:
- `AMENDMENT_LH_R11_MULTI_FAMILY.md`
- `AMENDMENT_A2_G1_RETEST.md`
- `OBJECTIVE.md`
- `WASHOUT_TIMEFRAME_HYPOTHESIS.md`
- `EXPECT_DRIFT_FAMILY_PREREG.md`
- `INSIDER_SPONSOR_LH_FAMILY_PREREG.md`

It is a contemporaneous record of the freeze event, as directed by LH-R11.1.
