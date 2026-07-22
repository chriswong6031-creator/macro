# PSQ-TILT W1 — hold-leash implementation design (by Fable)

Authored 2026-07-22 (main-loop). Implements the promotion granted in
`research/reports/PROPHET_STAGE_QUALITY_RESULTS.md` §Adjudication (PSQ-H1 PASS,
2026-07-20): a PROVISIONAL quality/hold tilt for Prophet picks Stage-2∩EC-positive at
entry. Authority boundary (binding): **never an entry veto, never rank suppression,
never a win-rate gate or fused rank bonus** (DO_NOT_REBUILD §2 Stage row + WA-R1-class
fusion bans); bear-tape default 1.0×; auto-demote tied to the #3157 forward shadow;
"validated" never appears (CI-scanned in `site/prophet/plans/*.json`).

## W1 scope ruling

- **SHIPS: the hold-leash.** PSQ's evidence is hold-quality evidence (median fwd126 /
  EA right-shift; the stopped-rate leg FAILED — no loss-avoidance claim). The leash
  converts it into behavior with one lever.
- **DEFERRED (chartered, not built): the display size-multiplier (≤1.25×).** No size
  field or consumer exists anywhere in the lane (recon dossier §3); the only plan-field
  renderer is the out-of-repo Terminal oracle-tab. A display-only number with no
  consumer adds surface risk for zero behavior. Revisit as PSQ-TILT W2 alongside a
  Terminal change.
- **No public template/design work in W1** (fields only → no designer lane needed). No
  `data/prophet/ledger.jsonl` schema change (row schema stays `prophet.ledger/v1`, its
  12 keys pinned by test).

## Mechanism (all changes in the nightly origination + shadow summary path)

### 1. Leash at origination — `engine/prophet_bridge.py::originate_plans`

After candidate selection and BEFORE geometry/option resolution, for each accepted
candidate compute:

- `stage_at_entry`, `weeks_in_stage` via `engine.prophet_stage_fusion.stage_at_entry`
  (PIT: series truncated at signal_date) — the SAME function the shadow uses (one code
  path; the shadow's own ledger is gitignored + written downstream, unusable upstream).
- `ec_sent` via `engine.prophet_stage_fusion.ec_sent_at_entry` (most-recent
  `call_date < signal_date`), gate `>= psf.EC_SENT_GATE` (24). EC table via
  `psf.load_ec_table()` default path, loaded once per nightly run, not per pick.
- `bear` per §2.

`tilt_eligible = (stage == 2) and (ec_sent is not None and ec_sent >= psf.EC_SENT_GATE)`
`leash = 1.25 if (tilt_eligible and not bear) else 1.0`
`horizon_days = round(BASE_HORIZON_DAYS * leash)` → 45 or 56. `min_hold_days`
unchanged (10). The scaled horizon flows naturally to τ/overtime (management), the
EXPIRED ledger close, and option-expiry selection (`resolve_option` sees the later
min date — intended coupling: longer intended hold → longer-dated contract; document
in code comment).

**Anti-veto/anti-rank invariant (test-pinned):** the tilt computation runs strictly
after `select_candidates` and must not read into it; the selected id set and order are
byte-identical with the tilt enabled vs disabled. Tilt failure of any kind (missing EC
table, stage classify error, missing regime artifact) degrades to `leash = 1.0` with a
logged `::warning::` — origination NEVER fails because of the tilt.

### 2. Bear-gate — deterministic, artifact-based

Read `data/regime/latest.json` (committed nightly; engine/run.py writer):
`bear = risk_radar.context_gate.spy_below_200dma == True or risk_radar.state == "risk-off"`.
Missing file / missing keys / unparseable → `bear = True` (fail-safe: tilt off).
Do NOT activate the `macro_stance` management socket (it shifts confidence for the
whole book — out of scope; dossier Option C risk). The bear boolean lives in the
driver/bridge only.

### 3. Provenance field — plan payload + index whitelist

Add to the trade_plan dict (permissive validators accept it):

```
"stage_tilt": {
  "leash": 1.25 | 1.0,
  "eligible": bool,            # stage2 ∩ EC, before bear-gate
  "stage_at_entry": int|null,
  "ec_sent": float|null,
  "ec_call_date": "YYYY-MM-DD"|null,
  "bear_gate": bool,           # True = gate forced 1.0
  "provisional": true,
  "demoted": false,            # §4
  "basis": "PSQ 2026-07-20 quality re-grade; provisional — forward-shadow checked (~2026-12)"
}
```

Thread `stage_tilt` into the `site/prophet/index.json` `active_entries` whitelist
(build_prophet.py field projection) so the Terminal can consume it later. All strings
plain-word EN (this is a data field, not display copy; no ZH pair needed in W1 — no
template renders it). Never the word "validated".

### 4. Auto-demote — mechanical, read from the shadow's committed summary

The PSQ §6 clause must be checkable by code, not memory:

- **Shadow side (`engine/prophet_stage_shadow.py::summarize` — measurement addition
  only, no tagging/grading logic change):** emit a `median_tilt` block in
  `summary.json`: for matured-126 entries, `median fwd_ret_126` for the
  stage2∩EC-positive subset vs rest, their difference, and `n_matured_126` per side.
  Nulls until cohorts mature (n tiny until ~2026-12 — the existing accrual disclaimer
  already says so). Update the shadow summary schema test accordingly; keep
  `is_context_only` / `display_only` / no-trading-verbs pins intact.
- **Tilt side (bridge/driver):** before applying any leash, read the committed
  `data/prophet_stage_shadow/summary.json`: if
  `median_tilt.n_matured_126.stage2_ec >= 30` AND `median_tilt.diff <= 0` → the tilt
  is DEMOTED: force `leash = 1.0`, set `stage_tilt.demoted = true`, log `::warning::`
  once per run. This implements "reverts to display-tier automatically, no new ruling."
  Until the floor is met, the tilt stays provisional-active. (The shadow itself still
  never gates picks — it remains the measurement instrument; the TILT is what reads
  the measurement and self-demotes.)

### 5. Copy audit

`_build_what_to_do_now`/`_build_profit_plan` (EN+ZH) and the option `note`: any
hardcoded "45" / horizon phrasing must read the plan's actual `horizon_days`. Builder
greps and fixes; no other copy changes.

## Tests (added; existing suites stay green)

1. Leash matrix: (stage2, EC≥24, non-bear) → 56; each single failing condition → 45.
2. Bear fail-safe: missing/corrupt `data/regime/latest.json` → leash 1.0, no raise.
3. Anti-veto/anti-rank pin: selected candidate ids + order identical tilt-on vs
   tilt-off (monkeypatch the tilt inputs to force eligibility).
4. Degrade-to-1.0 on EC-table load failure and on stage-classify exception (no raise).
5. Horizon propagation: tilted plan reaches management with τ computed on 56; ledger
   EXPIRED fires at ≥56 not 45; option expiry min-date respects the scaled horizon.
6. Ledger row schema unchanged (12 keys — existing pin must still pass).
7. `stage_tilt` present in plan JSON + index.json projection; `"validated"` absent
   from plan JSONs (existing CI scanner also covers).
8. Auto-demote: synthetic summary.json with n≥30 & diff≤0 → leash forced 1.0 +
   `demoted: true`; n<30 → active.
9. Shadow `median_tilt` emission: schema, nulls-when-unmatured, context-only pins
   intact.

## Dormancy disclosure (PR body + code comment)

Live intersection is currently EMPTY (shadow summary: stage2 n=11, positive_ec n=0 of
40 tagged) — the leash will apply to zero picks until an EC≥24 name is picked.
Dependency flagged, not fixed here: forward EC accrual comes from the stage_analysis
earnings feed; builder reports `earnings_calls.parquet` max `call_date` in the PR body
so the operator can see whether the feed is advancing.

## Out of scope (observations only, do not fix)

`management_ref` singular-vs-plural path mismatch; non-atomic `_write_json`; size
multiplier W2; any governor/admin surface change.
