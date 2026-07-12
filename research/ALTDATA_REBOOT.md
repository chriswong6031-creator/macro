# Alt-Data Reboot — Per-Channel Claim Families with Pre-Registered Horizon Rulers

**Status:** MASTERPLAN (W2). Adjudicated by Fable, 2026-07-12.
**Program tag:** ALTDATA-W2-R1..R10.
**Activation date:** 2026-07-12 (new families route from this date forward).
**Forward families:** `altdata_event`, `altdata_flow`, `altdata_mid`, `altdata_slow`,
`altdata_attention`.

---

## 0. Diagnosis summary

The qledger `altdata` family pools ALL Quiver channels under one blended ruler. Three
structural problems were adjudicated:

**1. Horizon mismatch.** Channels span 1 day to 3 years in the literature:

| Channel class | Literature horizon | Legacy ruler |
|---|---|---|
| gov_contract, special_situation, material_8k | 5–20 trading days | 63d (wrong) |
| darkpool_accum, unusual_options | 15–20 trading days | 63d (wrong) |
| insider clusters, 13F position adds | 21–63 trading days | 63d (marginal) |
| congress trades, lobbying | post-STOCK-Act: 1–6 months; dead short-term | 63d (wrong sign at 5d) |
| retail_buzz (WSB) | reverses post-2021; long 5d measures wrong sign | 63d (wrong) |

**2. Emission burst / correlated-claim inflation.** ~13 correlated claims on one asof
date (n_obs=120 vs n_dates=9 after cluster-honest fix). All claims are long-only,
conviction=low, and the 63d ruler was applied uniformly regardless of the channel that
drove the convergence.

**3. No placebo tape.** Without a matched-placebo counterfactual, the blended hit-rate
cannot be separated from base-rate luck. Binary-hit at 54% true-WR needs ~600 independent
dates to show significance; excess return magnitude must carry the load instead, and only
with a placebo baseline can that claim be made.

**Legacy freeze:** Existing open claims in the `altdata` family (desk=altdata, no
`claim_family` set or claim_family=`altdata`) mature and grade under their original
check_by date. No retro-tagging. The ledger is append-only PIT; existing rows are not
modified.

---

## 1. Per-channel family map (pre-registered rulers)

Assignment rule: deterministic, based on the **highest-weight channel** present on the
thesis (using `CHANNEL_WEIGHTS` from `engine.altdata_models`). All channels are still
recorded on the claim.

### Family: `altdata_event`

**Channels (highest-weight channel triggers):**
`special_situation`, `material_8k`, `gov_contract`, `gov_contract_accel`, `gov_grant`,
`gov_grant_accel`, `fda_approval`, `fda_label_expansion`, `clinical_phase3_start`,
`activist_13d`

**Rationale:** Event channels carry hard dated catalysts with measurable post-event
windows (5–20d literature). The highest-weight channel in this group (`gov_contract_accel`
at 0.90, `fda_approval` at 0.80) is economically anchored to the event date.

**Pre-registered rulers:**
- `horizon_d` = 21 (calendar-day window ≈ 15 trading days)
- `horizon_role`: primary verdict at **5d** AND **21d** (both grade via GRADE_HORIZONS)
- Direction: +1 (overweight) / −1 (underweight) per thesis lean
- Benchmark: SPY

### Family: `altdata_flow`

**Channels (highest-weight channel triggers):**
`darkpool_accum`, `unusual_options`

**Rationale:** Off-exchange accumulation (DPI z-score) and unusual options flow are
positioning signals; the literature places their half-life at 15–20 trading days.

**Pre-registered rulers:**
- `horizon_d` = 21
- `horizon_role`: verdict at **21d**
- Direction: +1 per existing thesis lean (flow signals are directional by construction)
- Benchmark: SPY

### Family: `altdata_mid`

**Channels (highest-weight channel triggers):**
`insider_cluster`, `insider_buy`, `app_demand`, `analyst_upgrade_cluster`, `insider_mspr`

**Rationale:** Insider purchases carry signal over 21–63 trading days in the literature;
analyst consensus is lagging and noisy, grading at the 21d shadow and 63d primary.

**Pre-registered rulers:**
- `horizon_d` = 63
- `horizon_role`: shadow grade at **21d**, primary verdict at **63d**
- Direction: +1 per thesis lean
- Benchmark: SPY

### Family: `altdata_slow`

**Channels (highest-weight channel triggers):**
`congress_cluster`, `congress_buy`, `trump`, `lobbying`, `lobbying_spike`,
`smart_money_13f`, `13f_add`, `patent_cluster`, `affiliation`

**Rationale:** Congressional trades post-STOCK-Act show drift at 1–6 months (dead at
short horizons). 13F filings carry a mandatory 45-day reporting lag; the 21d post-filing
window from the literature maps here. Lobbying and patent clusters are 3-year factors in
the academic literature; this program grades them at 63d as a display-tier check.

**Pre-registered rulers:**
- `horizon_d` = 63
- `horizon_role`: primary verdict at **63d** (GRADE_HORIZONS grades all ≤horizon_d)
- Direction: +1 per thesis lean
- Benchmark: SPY

### Family: `altdata_attention`

**Channels (highest-weight channel triggers):**
`retail_buzz` (and future social channels)

**Rationale:** Post-2021, WSB/retail-attention exhibits **reversal** — going long into a
WSB surge has measured the wrong sign. The construction is pre-registered as a **fade**:

- `direction` = **−1** regardless of the underlying thesis lean (fade the buzz)
- `horizon_d` = 5 (the reversal effect is concentrated in the first week)
- `horizon_role`: verdict at **5d**
- Benchmark: SPY
- **Display-tier accrual only** — no authority surfaces; no size implication

**Note:** The sign reversal is the pre-registered claim (not a hypothesis). If future data
shows the reversal no longer holds, the construction is falsified and closed.

### Previously unmapped channels (routed in W2 review)

Six channels were unmapped and previously absorbed into `altdata_event` with wrong horizons.
Explicit routes as of 2026-07-12 review:

| Channel | Route | Rationale |
|---|---|---|
| `github_momentum` | `altdata_mid` | Dev-adoption momentum builds over weeks-months; mid ruler (W2 review correction) |
| `hf_model_momentum` | `altdata_mid` | Model-adoption momentum builds over weeks-months; mid ruler (W2 review correction) |
| `earnings_beat` | `altdata_event` | Hard dated catalyst with 5–20d post-event window |
| `cnbc_pick` | `altdata_mid` | Attention-adjacent but `altdata_attention` is dormant; mid-horizon safer |
| `news_sentiment` | `altdata_mid` | Same rationale as cnbc_pick |
| `bill_catalyst` | `altdata_slow` | Legislation horizon — months not days |

### Truly unknown channels

Any channel not in the lists above maps to `altdata_mid` with a log warning. Mid-horizon
is the safer fallback for channels with uncertain timing (63d; not catastrophically wrong).
The previous fallback to `altdata_event` was incorrect — the 21d window is the narrowest
and most likely to be wrong for genuinely unknown channels.

---

## 2. Emission and episode rules

### 2.1 Episode-based dedup (cooldown)

Within each family, a ticker is subject to a **cooldown** after a thesis closes or
expires:

| Family | Cooldown (business days) |
|---|---|
| `altdata_event` | 21 |
| `altdata_flow` | 21 |
| `altdata_mid` | 63 |
| `altdata_slow` | 63 |
| `altdata_attention` | 5 |

The cooldown equals the family's `horizon_d`. A new thesis for the same (ticker, family)
is blocked until this many business days after the prior thesis's `check_by` date.

The existing open-window dedup (blocking while a thesis's window has not elapsed) is
retained and runs first. The cooldown applies after expiry.

Cross-ticker same-day claims are NOT blocked — date-cluster n already handles them
via the cluster-honest Wilson CI fix (PR-A/#2369).

### 2.2 Placebo tape

At registration, for each real claim, emit **2 matched placebo claims**:
- `is_placebo=True`, `placebo_path='altdata_matched'`
- Tickers drawn **deterministically** by ranking candidates via per-candidate
  `hashlib.sha256(asof + "|" + real_ticker + "|" + candidate)` digest — this is
  stable under unrelated universe membership changes (a new ticker gets its own rank;
  existing ranks are unchanged). The previous `h % len(candidates)` modulo approach
  caused reshuffles on any membership change, producing new `claim_id`s across nights.
- **Liquid universe:** `data/universe/membership.parquet` filtered to `active=True`
  and `group='sp500'` (509 large-cap members). Falls back to a hardcoded S&P 50 list
  when the parquet is absent. Universe is loaded once per backfill run and cached.
- **Exclusion:** the FULL set of tickers with any open real altdata-family claim
  (not just same-day converging tickers). 29 of the 50 hardcoded fallback tickers
  were themselves convergent altdata names — the parquet loader avoids this contamination.
- **Emit-once guard:** before emitting placebos for a thesis, `claims.jsonl` is scanned
  for existing placebo claims whose `placebo_real_source_id` matches the real thesis's
  source_id. If present, placebo emission is skipped. This prevents placebo accumulation
  across nightly runs when the same thesis re-appears in `theses.jsonl`.
- Same family, horizon, direction as the real claim
- Registered via `register_batch()` exactly as real claims

The placebo tape allows the `_placebo_magnitude` comparison in `qledger._aggregate` to
run, giving a "beat placebo" baseline for each family's hit-rate report.

### 2.3 altdata_attention: DORMANT-BY-CONSTRUCTION in W2

The `altdata_attention` family is **dormant** in W2 by construction: `retail_buzz` has
weight 0.15 in `CHANNEL_WEIGHTS`, which can never be the highest-weight channel when
any other channel is present (minimum other weight > 0.15). In practice, a thesis
with ONLY `retail_buzz` is the sole path to `altdata_attention`. Empirically:
attention=0/169 theses in the current corpus. This is expected and intentional.

**W3 will wire independent attention emission** via option (b) ruled 2026-07-12: a
dedicated emission path in `build_theses` that fires when `retail_buzz` is present
on ANY thesis regardless of whether it is the highest-weight channel. This is gated on:
1. The fade-check-semantics fix (MINOR-1, merged in W2 review) — attention now emits
   `op: ">"` with positive threshold (fade broken if realized > +5%), not the erroneous
   long-direction `op: "<"`.
2. The per-family dedup fix (MINOR-2, merged in W2 review) — `_active_subjects` now
   deduplicates per-(ticker, family), allowing a ticker to hold theses in different
   families simultaneously.

---

## 3. Activation statement

From 2026-07-12 forward:
- `altdata_ledger.build_theses()` assigns `claim_family` from the channel routing table
- `scripts.backfill_qledger_us.backfill_altdata()` routes new theses into the five
  families and emits 2 placebos per real claim
- The legacy `altdata` family (claim_family=None or "altdata") receives NO new claims
  from this date
- `daily.yml` invokes `backfill_qledger_us` in the collect job, after the collectors
  step and before `commit data`

---

## 4. Backfill lag root cause and fix

**Root cause:** `scripts/backfill_qledger_us.py` was never wired into `daily.yml`. It
ran only manually. New theses written by `altdata_ledger.build_theses()` after 2026-07-02
(the last manual backfill run) were never registered as qledger claims.

**Fix:** Add a step in `daily.yml`'s `collect` job after the collectors step and before
`commit data`:

```yaml
- name: qledger backfill (altdata + radar + policy → claims.jsonl)
  run: |
    set +e
    python -m scripts.backfill_qledger_us \
      > "$RUNNER_TEMP/backfill_qledger_us.log" 2>&1; rc=$?
    cat "$RUNNER_TEMP/backfill_qledger_us.log"
    if [ "$rc" -ne 0 ]; then
      echo "::warning title=backfill_qledger_us::rc=$rc (non-fatal)"
    fi
    exit 0
```

---

## 5. Wave structure

| Wave | Scope | Status |
|---|---|---|
| W1 (PR-B, #2369) | Cluster-honest Wilson CI fix for `n_dates` counting | MERGED |
| **W2 (this PR)** | Per-channel families, horizon rulers, episode emission, placebo tape, cadence fix | ACTIVE |
| W2 review fixes | MAJOR-1: parquet universe loader; MAJOR-2: stable draw + emit-once guard; MINOR-1: fade-check semantics; MINOR-2: per-family dedup; MINOR-3: 6 unmapped channels routed | MERGED IN W2 |
| W3 (future) | Independent attention emission (option b); template wiring for new families on alt_data.html; promotion-gate studies | DEFERRED |

---

## 6. Nulls and display doctrine

- All new families are **display-tier** pending gauntlet promotion
- Null results (no hit-rate edge) are **printed**, not hidden
- The word "validated" is banned in user-facing copy (`scripts/check_validated_claims.py`)
- The placebo beat-rate (per `_placebo_magnitude`) is the required comparator before
  any promotion claim
- A null for a standalone family does not close the search: it is retained as a
  confluence input per the context-accrual law

---

## 7. Deferred (Wave 3)

- `alt_data.html.j2` family chip iteration: the template currently shows
  `claim_family=altdata` desk-level chips. The new families (`altdata_event` etc.) will
  not surface until the template's family-iteration loop is updated to include them.
  **Wave-3 work; do not build in W2.**
- Promotion-gate pre-registration studies (per-family at 63d for slow/mid; 21d for
  event/flow; 5d for attention)
- China altdata family routing (separate adapter)
