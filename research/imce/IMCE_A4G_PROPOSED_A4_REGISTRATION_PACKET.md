# IMCE-A4G — Proposed A4 Registration Packet

**STATUS: PROPOSED — NOT REGISTERED.** No `data/` write has occurred. No `declared_budget` row has actually been appended to `data/trial_ledger.jsonl`. No `rf.cycle_pattern.imce_*` family is registered by this document or by any document in this A4G wave. Registration is a separate, future act (A4 / IMCE-03), requiring its own wave approval per `agentos/workstreams/WS-CYCLE-PATTERN-ISSUER-MECHANISM.md`.

**Wave:** A4G. Records-only. **This document proposes exact byte-ready row contents; it registers nothing.**
**Authority:** amended contract V1.1 (`IMCE_PREREGISTRATION_AND_EVALUATION_CONTRACT_V1.md`), as amended by `IMCE_A4G_AMENDMENT_LOG.md`; contract §1 (cell budgets, A5), §11 (multiplicity and trial budget), §15/§15a (stop condition, two-commit discipline).
**Purpose:** the mandatory Sol deliverable (e) — the exact proposed A4 registration packet: the three `rf.cycle_pattern.imce_*` `declared_budget` row contents as they would be written, byte-ready, clearly marked PROPOSED — NOT REGISTERED; plus the criteria-commit checklist (criteria commit strictly before any outcome access).

---

## 1. Row schema (verbatim from `engine/trial_ledger.py`)

`TrialLedger.log_declared_budget(n, family=..., reason=...)` appends exactly this row shape to `data/trial_ledger.jsonl` (the canonical, committed, append-only ledger — `engine/trial_ledger.py` `DEFAULT_PATH = Path("data") / "trial_ledger.jsonl"`):

```json
{
  "ts": "<ISO8601 UTC, set automatically by datetime.now(timezone.utc).isoformat() at the moment of actual registration>",
  "family": "<family name, string>",
  "kind": "declared_budget",
  "n": "<int, the declared multiple-testing budget = frozen cell count>",
  "reason": "<string>",
  "config_hash": "<sha1(f'{family}\\x00{canon({\"__declared_budget__\": n, \"reason\": reason})}').hexdigest()[:16]>"
}
```

`config_hash` is a pure function of `(family, n, reason)` — it does not depend on `ts`, on any outcome, or on any `data/` content. It has been **computed exactly** below for each of the three proposed rows, using the repo's own `_canon`/`_hash` functions (`json.dumps(..., sort_keys=True, default=str, separators=(",", ":"))` then `sha1(family + "\x00" + canon).hexdigest()[:16]`), verified against `engine/trial_ledger.py` lines 53–62 and 159–190 — no engine code was executed to write to any ledger; the hash was computed as a standalone pure-function check. **Only `ts` is genuinely unknowable in advance** (it is stamped at the moment of actual registration) and is left as an explicit placeholder rather than invented.

---

## 2. Proposed row — `rf.cycle_pattern.imce_phase_v0`

```json
{
  "ts": "<set at actual registration>",
  "family": "rf.cycle_pattern.imce_phase_v0",
  "kind": "declared_budget",
  "n": 3,
  "reason": "IMCE preregistration V1.1 (A4G-amended) - 3 cells frozen [A5]: 3 state targets x pooled homebuilder stratum x contrast [M vs family/age prior]; predetermined underpowered_accruing [A2]; block basis <=5 general / <=3 cancellation-scoped [AG5/AG6]; criteria commit precedes outcome access [G8-B1]. See research/imce/IMCE_PREREGISTRATION_AND_EVALUATION_CONTRACT_V1.md and research/imce/IMCE_A4G_AMENDMENT_LOG.md.",
  "config_hash": "29dce2d62989e7f1"
}
```

**Cell definition (unchanged from contract §1):** 3 state targets × pooled homebuilder stratum × contrast [M vs family/age prior]. **Settled block basis (MAJ-1, A4G revision):** all 3 cells in this family are B≤3-entire cancellation-scoped cells under the cell-level ruling in `IMCE_A4G_SIX_CELL_DISPOSITION.md` §1 (Cells 1–3), not the general B≤5 cap — the reason string above states the law in general form; the per-cell settlement is in the disposition document. **Open item this row inherits (§4 of `IMCE_A4G_SIX_CELL_DISPOSITION.md`, now binding at registration per §15/§15a AG14/MAJ-5):** the exact D5-state mapping of the 3 targets is not registered by A4G — a future A4 registration session must confirm or re-map before this row's `n=3` cells are individually itemized in code, and may NOT register a target left unmapped.

---

## 3. Proposed row — `rf.cycle_pattern.imce_sync_v0`

```json
{
  "ts": "<set at actual registration>",
  "family": "rf.cycle_pattern.imce_sync_v0",
  "kind": "declared_budget",
  "n": 2,
  "reason": "IMCE preregistration V1.1 (A4G-amended) - 2 cells frozen [A5]: targets {next_local_state_1rp, forward_63d_drawdown_tail} x contrast [M+R vs M]; predetermined underpowered_accruing [A2]; block basis <=5 general / <=3 cancellation-scoped [AG5/AG6]; criteria commit precedes outcome access [G8-B1]. See research/imce/IMCE_PREREGISTRATION_AND_EVALUATION_CONTRACT_V1.md and research/imce/IMCE_A4G_AMENDMENT_LOG.md.",
  "config_hash": "76b9eb13dcc0fbf8"
}
```

**Cell definition (unchanged):** targets {`next_local_state_1rp`, `forward_63d_drawdown_tail`} × contrast [M+R vs M]. Only the primary incremental comparison (M+R vs M) supports the synchronization claim (contract §5); secondary comparisons are print-only, zero budget, outside the FDR partition [A7]. **Settled block basis (MAJ-1):** `next_local_state_1rp` (Cell 4) is B≤3-entire (same D5 next-state class as the phase family); `forward_63d_drawdown_tail` (Cell 5) is conditional on its `M_t` feature composition at registration — B≤3 entire if cancellation-rate is included, B≤5 if not. See `IMCE_A4G_SIX_CELL_DISPOSITION.md` §1.

---

## 4. Proposed row — `rf.cycle_pattern.imce_risk_v0`

```json
{
  "ts": "<set at actual registration>",
  "family": "rf.cycle_pattern.imce_risk_v0",
  "kind": "declared_budget",
  "n": 1,
  "reason": "IMCE preregistration V1.1 (A4G-amended) - 1 cell frozen [A5]: forward_63d_drawdown_tail x [M vs family/stratum prior]; predetermined underpowered_accruing [A2]; block basis <=5 general / <=3 cancellation-scoped [AG5/AG6]; criteria commit precedes outcome access [G8-B1]. See research/imce/IMCE_PREREGISTRATION_AND_EVALUATION_CONTRACT_V1.md and research/imce/IMCE_A4G_AMENDMENT_LOG.md.",
  "config_hash": "82749c8a20babb5a"
}
```

**Cell definition (unchanged):** `forward_63_trading_day_drawdown_tail` × [M vs family/stratum prior]. Market grading uses QLedger's 63-trading-day ruler and canonical exchange calendar (contract §5). **Settled block basis (MAJ-1):** conditional on this cell's `M_t` feature composition at registration — B≤3 entire if cancellation-rate is included, B≤5 if not; a registration-time decision, not an open election. See `IMCE_A4G_SIX_CELL_DISPOSITION.md` §1 (Cell 6).

---

## 5. BH-FDR partition registration (accompanies, does not replace, the three rows above)

Per contract §1/§11 (A6): all 6 cells across the three families above run under **one** BH-FDR partition, `imce_hist_v0`, at **q = 0.10**. This is not itself a `declared_budget` row (it is a separate FDR-family registration act, also part of A4/IMCE-03, mechanically distinct from the per-family trial-budget rows above) but is named here for completeness, since a `declared_budget` row without its FDR partition registered alongside it would be an incomplete A4 act:

```json
{
  "fdr_partition": "imce_hist_v0",
  "q": 0.10,
  "member_cells": 6,
  "member_families": ["rf.cycle_pattern.imce_phase_v0", "rf.cycle_pattern.imce_sync_v0", "rf.cycle_pattern.imce_risk_v0"],
  "note": "single BH-FDR partition over the union of all 6 historical cells; the three rf.* family names are trial-ledger provenance labels, not separate FDR partitions",
  "producer": "A4 registration session — no current repo writer for this shape; deliberate, this is proposed content only [M6 fix]"
}
```

**[M6 fix]** Unlike the `declared_budget` row (§1, written by `engine/trial_ledger.py`'s `log_declared_budget`), this repository has **no existing writer** for an FDR-partition registration record — no module, script, or schema in `engine/` or `scripts/` currently accepts or persists this shape. That absence is deliberate to this proposal, not an oversight: the FDR-partition registration mechanism itself (where it lives, what module writes it, what file it lives in) is unspecified A4/IMCE-03 design work, separate from the already-built `declared_budget` mechanism. A future A4 registration session must either build that writer or fold this content into an existing mechanism before this JSON shape has anywhere real to go.

---

## 6. Criteria-commit checklist — criteria commit STRICTLY before any outcome access

Per contract §15a ("Two-commit discipline: the criteria commit strictly precedes the runner/outcome commit") and freeze G8-B1. **Every item below must be true and committed BEFORE the first outcome value of any kind is accessed for any of the 6 historical cells or any prospective cell.** This checklist is itself part of the criteria commit — the actual A4 registration commit must include all of the following, in this order, in one commit or a tightly sequenced series that entirely precedes any runner/outcome commit:

- [ ] **Contract V1.1 frozen** — `IMCE_PREREGISTRATION_AND_EVALUATION_CONTRACT_V1.md` and its YAML projection, as amended by A4G (this wave), committed to `origin/main`.
- [ ] **All 18 A4G rulings encoded** — `IMCE_A4G_AMENDMENT_LOG.md` present, every AG1–AG18 entry cross-referenced against the amended contract sections.
- [ ] **Six-cell disposition recorded** — `IMCE_A4G_SIX_CELL_DISPOSITION.md`, including the explicit open item (§4: phase-family target-to-D5-state mapping) named, not silently resolved.
- [ ] **Source/boundary table recorded** — `IMCE_A4G_SOURCE_BOUNDARY_TABLE.md`, including every macro block boundary's receipt status (`not_yet_receipted` where applicable — no invented dates).
- [ ] **Three `declared_budget` rows appended** to `data/trial_ledger.jsonl` — the exact contents in §2–§4 above, with `ts` populated at the moment of the actual write.
- [ ] **FDR partition registered** — `imce_hist_v0` at q=0.10, per §5 above.
- [ ] **`n_effective_blocks` computation path frozen** — B ≤ 5 (general) / B ≤ 3 (cancellation), per AG3/AG5/AG6, applied **cell-level per the MAJ-1 ruling** (not feature-level); no ρ-based estimator used as N; the precision-diagnostic field name (AG4) fixed if it is to be computed at all.
- [ ] **Phase-family (and any other) state target mapped to a named D5 state with a registered observability class** (contract §15/§15a, AG14/MAJ-5) — **BINDING**: no `rf.cycle_pattern.imce_phase_v0` target may be registered unmapped or mapped to a `descriptive_only` state without an explicit accepted re-scoping.
- [ ] **Bootstrap draws and seed registered** (contract §11) — not yet chosen by any A4G document; must be frozen at actual registration, before any outcome access.
- [ ] **Preregistered minimum prospective share registered** (contract §13, A24) — not yet chosen by any A4G document; must be frozen at actual registration.
- [ ] **Come-back date published on the B=5 hardened basis: ~2153** (contract §13, AG5) — **there is no basis election to make; the A4G revision (BLK-1) settled B=5 as the sole N-accounting law, so ~2153 is the one figure to publish.** The pre-A4G ~2145 figure was computed against a superseded, non-hardened reading and must not be republished.
- [ ] **`config_hash` recorded** (contract §15a) — computed at registration from the actual committed contract content, not the exact-but-narrower `declared_budget` row hashes in §2–§4 above (those are genuinely exact, computed against `engine/trial_ledger.py:53-62` — they are simply a different, narrower hash over `(family, n, reason)` only, not the contract-level `config_hash`).
- [ ] **Repository pin recorded** (contract §15a) — the exact commit SHA of the contract as registered.
- [ ] **Zero outcome access verified** — a final, explicit statement in the actual A4 registration commit message or record that no forward return, drawdown, Brier score, calibration statistic, p-value, correlation, or regression was computed on any cell before this checklist's items above were all committed.

**Only after every box above is checked, committed, and pushed may any runner/outcome commit occur.** This document does not check any box — it is the proposed content and checklist for a future session to execute and verify.

---

## 7. What this document does NOT do

- Does not write `data/trial_ledger.jsonl`.
- Does not access any outcome, return, drawdown, Brier score, or price series.
- Does not register the `imce_hist_v0` FDR partition.
- Does not compute or freeze bootstrap draws/seed.
- Does not compute or freeze the preregistered minimum prospective share.
- Does not compute the contract-level `config_hash` (only the three row-level `config_hash` values, which are a narrower, different hash over `(family, n, reason)` only).
- Does not itself constitute A4 registration — it is the proposed, byte-ready content for a future, separately-authorized registration act to execute verbatim or amend before executing.

---

**This document authorizes nothing beyond itself.** The next authorized act on this family is actual A4 registration (IMCE-03), executing the checklist in §6 above, as its own separately-authorized wave.
