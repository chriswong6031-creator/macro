# BioCatalyst — handoff to Codex, 2026-08-10

You wrote `BIOCATALYST_REMAINING_BUILD_WAVES_HANDOFF_FOR_CLAUDE_2026-08-06.md` and handed the
program over. This is the return handoff. Everything below is on `origin/main` and verified.

**Companion:** `research/BIOCATALYST_HANDOFF_2026-08-10_ACCOUNT_TRANSFER.md` carries the exact
VPS state, SSH command, env-file contents and the two worker-config traps. Read that for
mechanics. This document is for *what to do next and why*.

---

## 1. Is the project complete? No — and the distinction matters

**The foundation is complete and live. The product and the intelligence layers are not.**

| Wave | State |
|---|---|
| **W0** reconcile / approve / isolate | **COMPLETE** — all five lanes shipped |
| **W1** bounded live operation | **A complete** (deployment package shipped). **B/C/D not started** — needs arming + 14-day soak |
| **W2** premium trial product | **COMPLETE and LIVE** — Screen, facets, Peer Matrix, replay-verified Change Tape, Decision Sentence, Temporal Braid |
| **W3** temporal identity graph | **BLOCKED** — no owning plane publishes a PIT identity contract |
| **W4** regulatory / corporate / capital / market facts | **Mostly not built.** See §4 — the blockers are not what my earlier docs implied |
| **W5** unified intelligence suite | **Not built** |
| **W6** outcomes / calibration / EV | **O1b built, clocks CLOSED.** No forecast, no outcome, no model exists |
| **W7** Neural Web + Mastermind | **A + B built** — packet producer and one allowlisted reader. Not wired to a live consumer |
| **W8** Prophet shadow | **Not started** |
| **W9** operations / commercial / MedTech | **Not started** |

**Benchmark parity: 6 of 32 rows** satisfy the §17 test
(`research/BIOCATALYST_PARITY_LEDGER_2026-08-06.md`). Twenty of the remaining 26 depend on
decisions or contracts outside BioCatalyst's control.

### What is genuinely finished and verifiable

- **Main is green**: `pytest tests/ -k biocatalyst` → **1061 passed** before this session's ten
  PRs, which added ~191 more with zero cross-lane regressions.
- **Production serves the new product**: `biocatalyst.html` grew 61,226 → 69,127 bytes; JS/CSS
  return 401 with an `authentication_required` lock to anonymous callers (entitlement boundary
  working, not a break).
- **The collector works end to end.** First live canary, 2026-08-10: four trials fetched,
  parsed, and mirrored to R2 with **verified receipts** at `biocatalyst/raw/clinicaltrials/v2/`.
  The operator's R2 credentials are proven.

---

## 2. THE ONE OPEN DEFECT — start here

The canary **fetched successfully and then refused to publish**, dead-lettering the generation
and ending `state: quarantined`. `health.json`'s `observed_nct_count: 0` counts the *published*
generation, not the fetch.

**Leading hypothesis, recorded but NOT confirmed:** every fetched record carries
`source_dataset_timestamp_raw: 2026-08-07T09:00:05`; health reports
`freshness_budget_seconds: 7200`; the run was ~**69 hours** later.

**Do not widen the budget before confirming the cause.** Two readings are open with opposite
remedies:

1. ClinicalTrials.gov genuinely stamps its dataset on a multi-day cadence → the 2-hour budget is
   mis-specified for this source and must be re-derived from observed cadence.
2. The stamp means something other than dataset freshness → the budget is fine and the
   comparison is wrong.

Read `engine/biocatalyst/publication.py`, find where `freshness_budget_seconds` and
`source_dataset_timestamp_raw` meet, and settle it. Evidence is preserved on the VPS at
`/var/lib/macro-biocatalyst/state/dead-letter/attempt_20260810T055235959556Z_b4e57dc858e6/`.

Success looks like `observed_nct_count: 4` and a non-null `last_success_at` in
`/var/lib/macro-biocatalyst/public/health.json`.

---

## 3. Correcting my own earlier claim about the forward clock

My strategy doc originally said Move 1 (start the forward clock) was "not blocked", reasoning
that trial outcome families are NCT-keyed and need no ticker. **The identity half was right and
the conclusion was wrong.**

Every trial family's entry gate also names `clinicaltrials_gov_record_history`, which was
`production_ingest_allowed: false`. I checked the famous gate (identity), found it clear, and
stopped — instead of the gate that binds. The operator has since cleared the **rights** gate by
ruling, but the runtime gate `BIOCATALYST_HISTORY_ENABLED` is still `0` **by design**: it stays
off until the canary is green (§2).

**No outcome-family clock is open, deliberately.** A clock over a source that is not yet
collecting accrues nothing while later reading as "accruing since <date>" — the exact
fabrication this program exists to prevent. Clocks open through an activation receipt, never a
config edit (`clock_state_authority: activation_receipt_not_this_file`).

Once §2 is green and history is enabled, three families open with **no code change**:
`trial_progression_termination`, `timing_slip`, `enrollment_site_change`. That is pinned by
`tests/test_biocatalyst_m0a_clock_activation.py::test_the_trial_families_would_open_once_their_source_is_eligible`.
`endpoint_readout` stays closed on a second declared blocker
(`endpoint_alignment_review_queue_not_drained`).

---

## 4. IMPORTANT CORRECTION — C2 / MKT0 / EST1 are not all licensing problems

My earlier docs said these needed "contracts that do not exist", which read as *buy a licence*.
That was ambiguous and wrong for two of the three. "Contract" in the blocker strings means an
**executable software interface**, not a commercial agreement.

| Lane | What it actually needs | Licence helps? |
|---|---|---|
| **BC-C2** Capital Structure PIT | An `as_of` read on an **internal plane already in this repo** | **No** |
| **BC-MKT0** market / options | A **rights review** of existing feeds + a PIT adapter | Maybe — depends on existing terms |
| **BC-EST1** estimates | A real vendor feed with **point-in-time vintages** | **Yes — the genuine one** |

**BC-C2 is the highest-value and needs no external anything.** `app/capital_structure.py`
contains exactly **one** `as_of`, and it is a current-bundle stamp rather than a query parameter.
So the plane can answer "cash now" and cannot answer "cash as of the date that trial started".
The recorded blocker is literally
`versioned_internal_pit_adapter_with_unavailable_state_semantics`. This is a few days of
engineering on a plane the house already owns, and every financing-survival scenario in W6-F
hangs off it.

**BC-MKT0** — `collectors/` already has `cboe.py`, `databento_tbbo.py`, options chain data. The
gap is a documented rights record (retention, redistribution, derived-model-training) plus a PIT
adapter with corporate-action handling. If existing terms permit internal derived use, this
unblocks with paperwork and an adapter.

**BC-EST1** — `yf_analyst.py` and `china_analyst.py` are free-tier/scraped and not
redistributable. If a vendor is procured, **insist on point-in-time vintages**. A current-only
consensus feed will silently leak look-ahead — the exact defect that already ruined the
retrospective trial store and produced `DNR:KILL-PHASE3-START-WEIGHT`.

---

## 5. Recommended next five, in order

1. **Settle the publication refusal** (§2). Nothing downstream moves until the canary is green.
2. **Build the `BC-C2` PIT adapter** (§4). Internal, unblocked, highest leverage of the three.
3. **Once the canary is green**: set `BIOCATALYST_HISTORY_ENABLED=1`, re-run, confirm three
   family clocks open, and **record the activation receipt**. That starts the forward clock —
   the single most time-sensitive act in the program, because forward accrual is the only clean
   evidence it will ever have and needs 12–24 months before a pre-registered test is possible.
4. **Adopt the new Change Tape fields in the UI.** `#4947` shipped exact before/after values,
   source locators and declared correction lineage through the API, but **no surface renders
   them yet** — the D0b braid still drives its redline branch from an inferred
   `op === 'replace'` signal.
5. **`B1S2c`** — operator arming plus the fourteen-day soak. A calendar, not a task.

---

## 6. Standing constraints — do not relax these

- **A0/A1 authority.** Nothing may originate probabilities, rankings, signals, scores, sizing or
  escalation. Prophet remains the selection owner.
- **`DNR:KILL-PHASE3-START-WEIGHT`** is live: Phase-3 START is killed as a **scored** catalyst
  leg. Display/context tier only.
- **The sponsor→ticker map is post-selection context only.** 34 admitted rows (29 direct issuers
  + 4 subsidiaries + 1), 16 still `ambiguous_queued`. A model may not self-admit — a test fails
  if any committed row is `reviewed_admitted` without an operator attestation carrying the ruling
  digest. Never wire it to Prophet, Neural Web, or a scoring path.
- **`theme_clinical` keeps its authority block**: `is_context_only`, display-tier, never scored,
  never folded into `fused_obs_z`.
- **All BioCatalyst PRs conflict on `.github/ci/legacy-jobs.yml`** because a deploy guard forces
  every new `test_biocatalyst_*.py` to be registered there. **Merge serially.** Resolve that
  block as a union taken from `git show origin/main:<file>` — never with a regex over conflict
  markers.

---

## 7. The strategic picture, unchanged

- **A contextual layer already exists and is already live**, and it is *not* BioCatalyst:
  `engine/theme_clinical.py` aggregates trials to a theme, joins that theme to baskets, and
  feeds Mastermind — reaching price with **no per-company identity at all**.
- **There is no authorized signal, and there will not be one before 2027** even in the best case.
- The retrospective ClinicalTrials.gov store is **look-ahead-selected pre-2019 and cannot be
  cleaned**. That is why forward accrual is the only clean evidence available, and why item 3
  above is the most time-sensitive thing in the program.
