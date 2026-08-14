# Options episode H+60 outcome coverage — adjudication

Status: **ruling / display-tier disclosure / zero authority**
Date: 2026-08-13
Owner: Options Intelligence Program
Governing prereg: `OPTIONS_SIGNAL_EPISODE_SESSION_OUTCOMES_PREREG.md`
Instrument: `engine/options_episode_coverage.py`,
`scripts/audit_options_episode_outcome_coverage.py`

## §0 Ruling in one paragraph

The unlabelled H+60 backlog is **two defects, not one**, and the single-cause
attribution it arrived with was wrong for 94% of it. **Class 1
(`no_admissible_price_source`, 223 of 237 episodes, 26 tickers) is NOT accepted**
— it is a universe-reconciliation defect on a fix path, and accepting it would
ratify a survivorship bias in the labelled population. **Class 2
(`source_dependent_pending`, 14 episodes, 3 tickers) IS accepted forever**
(option **a**) with disclosure, a bounded census, and a declared tripwire,
because the governing prereg forbids the alternative. **Option (c) is ruled
out** and may not be implemented without a prereg amendment. Option (b) is the
correct remedy for Class 1 but in its *general* form ("obtain an intraday
source"), not the "finer source" form, and its vendor-cost step is escalated
rather than taken unilaterally.

## §1 What was measured, and the correction to the reported cause

Measured 2026-08-13 against the committed estate at `origin/main`
(`data/options_signal_episode/`, 1,206 episodes / 969 H+60 rows):

| | count | share of estate |
|---|---:|---:|
| complete labels | 852 | 70.6% |
| terminal-incomplete labels (persisted) | 117 | 9.7% |
| **no row at all** | **237** | **19.7%** |

The 117 terminal-incomplete rows are persisted and visible
(`decision_after_session_close` 86, `horizon_crosses_session_close` 31). They
are not the problem. The 237 are.

**The reported root cause was real but explains 5.9% of the backlog, not 100%.**
`aligned_exit_crosses_session_close` (`engine/options_signal_episode.py:2506`)
requires an hourly source *and* an anchor in the final bar, which constrains it
to anchors in the 18:00Z hour. Cross-tabulating anchor hour against outcome
status refutes the attribution immediately:

| anchor hour (UTC) | complete | no row | persisted terminal |
|---|---:|---:|---:|
| 13Z | 436 | 25 | — |
| 14Z | 301 | 117 | — |
| 15Z | 5 | 13 | — |
| 16Z | 10 | 4 | — |
| 17Z | 100 | 60 | — |
| 18Z | — | 18 | — |
| 19Z | — | — | 31 |
| 20Z | — | — | 86 |

219 of the 237 are anchored 13Z–17Z with hours of runway to the close. The
cadence mechanism cannot reach them.

**The actual dominant cause.** Splitting the unlabelled set by whether its
ticker has *ever* produced a complete label gives a clean partition with no
overlap:

- **Class 1 — 223 episodes across 26 tickers with ZERO complete labels, ever.**
  Anchor hours spread 13Z–18Z. `_price_snapshot`
  (`scripts/build_options_signal_episode.py:513`) returns `(None, None)` when a
  ticker has no `<T>.parquet` + `.parquet.receipt.json` pair, which yields
  pending `missing_price_receipt` on every episode of that ticker, every run,
  forever.
- **Class 2 — 14 episodes across 3 tickers that DO get labels** (AMD 12,
  SOXX 1, VRT 1), **all anchored 18Z.** This is exactly the reported mechanism.

**Why Class 1 exists — the universe mismatch.**
`build_polygon_intraday._universe()` is `data/stocks/*.parquet` ∪ the
`config.yahoo` sector/factor/extras ETF groups. Membership predicts labelling
with one exception in 65 tickers:

| | in intraday universe | outside it |
|---|---:|---:|
| ticker gets complete labels | 39 | 0 |
| ticker has never been labelled | 1 (`DE`) | 25 |

The options flow detector mints episodes for a universe the price lane does not
cover, and nothing reconciles the two. The 25 uncovered names —
SMCI, LITE, DELL, CRWV, NBIS, ASTS, COHR, GLW, NOW, ARM, SNOW, DDOG, NET, ADBE,
CBRS, FAST, FIX, TER, TLT, CIEN, HEI, MPWR, OKLO, RKLB, TLN — share the property
the intraday universe keys on: **no deep price history**. (`DE` is in
`data/stocks/` yet unlabelled on 3 episodes; it is a genuine residual, not part
of the universe gap, and the census will keep reporting it.)

## §2 Survivorship — the finding that actually matters

The hole is not a random 20% thinning. It is **26 entire tickers absent from the
labelled population**, and they are a coherent slice: recent listings and
high-beta AI/datacenter names. The labelled set is therefore biased *toward*
established deep-history mega-caps and *away from* exactly the names an
options-flow signal is most likely to be about.

Any cross-sectional statistic computed over `outcomes_h60.jsonl` — hit rate,
mean return, MFE/MAE distribution, per-bucket comparison — silently describes
the old-and-liquid subset while reading as if it described the estate. This is
the concrete harm, and it is why Class 1 cannot be accepted.

## §3 Consumers — what already handles this and what does not

Checked before ruling, as required.

- **`engine/options_signal_campaign.py` — handles it correctly.** Campaign
  outcomes carry `member_outcome_coverage` with explicit
  `expected_member_count` / `observed_member_count` / `missing_episode_ids`, and
  `validate_campaign_outcome` rejects inconsistent counts. No blind spot.
- **`engine/options_market_memory_context.py` — not a statistical consumer.** It
  digests `outcomes_h60.jsonl` as a byte snapshot for provenance
  (`_SOURCE_PATHS`), not as a population.
- **`OPTIONS_SIGNAL_CAMPAIGNS_PREREG.md` §"H+60 reference gate" — carries a
  false premise.** It states a qualifying prefix without its H+60 row "is
  retried on a later nightly run". For Class 1 that retry can never succeed, so
  a campaign whose crossing episode is a Class 1 episode is suppressed
  permanently while the contract describes it as transient.
- **Measured campaign exposure today is small and must not be overstated: 1 of
  21 campaign-qualifying groups** has an unlabelled crossing episode, and it is
  `osep_70fb17ad11445cca4f3f7c4b` (AMD, 2026-08-12, anchor 18:16:46Z) — a
  **Class 2** case. The Class 1 tickers rarely form the tight repeat groups the
  ≥2-event / ≥$3M rule requires. The mechanism is real; its current cost is one
  group.
- **`config/synapse.yml`** described missing bars as "retryable" without
  qualification. Corrected in this change to disclose the permanent class at the
  registry, which is where a consumer looks.

That AMD episode is also the one `PR #5524 §3` flagged. Its downstream effect —
`tests/test_options_signal_episode.py::test_committed_campaign_ledger_is_exact_frozen_corpus_not_future_recomputation`
failing on `assert pending == []` — is an append-only ledger pinned by equality,
and is **owned by PR #5525**, which freezes that replay to the activation-vintage
prefix. This adjudication does not touch that test.

## §4 The ruling

### Class 2 — `source_dependent_pending` → **accepted (option a)**

Accepted forever, disclosed, bounded, tripwired. The reasoning is not "it is
small"; it is that the governing prereg already decided it:

> Pending rows are never appended. Clock-only terminal incomplete is allowed
> only when `available_at >= target_time` (therefore EOD in v1); **no
> cadence-dependent condition is frozen as terminal.**

`aligned_exit_crosses_session_close` is cadence-dependent by construction. The
in-code note is correct that a v1 terminal row carries no cadence or admitted
entry provenance and so could not be reproduced from the episode/outcome join.

### Class 1 — `no_admissible_price_source` → **NOT accepted; defect on a fix path**

The remedy is option (b) in its general form: **give the affected tickers an
intraday source at all.** Not a *finer* source — any admissible receipt-bound
parquet resolves them, because they are pending on `missing_price_receipt`, not
on cadence.

Implemented here: detection, classification, census, disclosure, tripwire.
**Escalated, not taken:** extending `build_polygon_intraday._universe()` by ~25
tickers is a vendor-quota and nightly-runtime change with a cost the options
program does not own unilaterally. It is a bounded work item — the exact ticker
list is in §1 and the census reprints it every run.

### Option (c) — **ruled out**

A preregistered causal contract that persists a terminal-incomplete row for
these conditions may **not** be implemented as a code change. Two independent
reasons:

1. For Class 2 it directly contradicts the frozen prereg line quoted above. It
   requires a prereg amendment and its own adjudication, not an engine edit.
2. For Class 1 (94% of the backlog) it is simply the wrong answer: freezing "we
   never collected this ticker" as a terminal fact would convert a fixable
   collection gap into a permanent record of absence, and would *remove* the
   pressure to reconcile the universe while making the survivorship bias look
   like a measured property of the estate.

## §5 Declared bounds (preregistered)

Evaluated against the **matured** denominator only — an episode inside its own
H+60 clock is not a hole. Pinned in `engine/options_episode_coverage.py`.

| tripwire | warn | fail | 2026-08-13 observed |
|---|---:|---:|---:|
| `matured_unlabelled_share` | > 10% | > 30% | **19.7%** → warning |
| `source_dependent_share` (accepted class) | > 3% | > 10% | **1.2%** → quiet |
| `structural_price_source_gap` | ≥ 1 ticker | — | **26 tickers** → warning |

Two deliberate choices:

- **The warn level sits below the measured state.** The current 19.7% is a real
  defect and must be loud from the first run. Drawing the threshold around
  today's number would normalise it — the failure mode these bounds exist to
  prevent.
- **The fail level sits above it, and the audit is non-fatal by default.** A
  known, disclosed defect must not red the nightly lane that reports it.
  `--strict` is available for a caller that wants the bound enforced.

The accepted class carries the tighter bound precisely because it is the one
permitted to persist: growth there is the signal that the acceptance is no
longer safe and this ruling must be revisited.

## §6 What ships in this change

- `engine/options_episode_coverage.py` — pure classifier and bound evaluator.
- `scripts/audit_options_episode_outcome_coverage.py` — bounded census +
  GitHub-annotation tripwires; non-fatal by default.
- `tests/test_options_episode_outcome_coverage.py` — 27 tests, wired into the
  existing options CI job (not an 181st job) with `ci.yml` path filters widened
  so the guard is not dark.
- `config/synapse.yml` — consumers declared; the "retryable" note corrected to
  disclose the permanent class.

The census is bounded (capped ticker/session lists with explicit `truncated`
counts) so it stays readable as the estate grows, and it reports its
`evidence_mode`: `price_source` when the mutable intraday cache is readable
(ground truth), `ledger_inference` otherwise (CI, sparse worktrees).

## §7 Open items (not taken here)

1. **Universe reconciliation** — extend the intraday collector to the options
   episode universe, or declare an explicit minted-episode fence so the detector
   stops minting episodes the outcome lane cannot label. Needs the vendor-quota
   decision. Until then the census names the 26 tickers nightly.
2. **`OPTIONS_SIGNAL_CAMPAIGNS_PREREG.md` §"H+60 reference gate"** — the
   "retried on a later nightly run" sentence should be qualified for Class 1.
   Left to the campaigns lane, which owns that prereg.
3. **Nightly wiring** — the audit is a standalone CLI here. Adding it to
   `config/dag.yml` after `build_options_signal_episode` is the natural next
   step; deferred to keep this change off the render path while
   `merge-on-green` traffic is heavy.
4. **`DE`** — in the intraday universe yet unlabelled on 3 episodes. A genuine
   residual worth a look once Class 1 is drained; too small to block on.
