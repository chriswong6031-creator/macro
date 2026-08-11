# MomoEdge completion benchmark — frozen preregistration

Status: **registered; goal not complete**

Machine contract: `completion_benchmark_prereg_v1.json`

Contract digest: `20e6c19f691cf9a07381288d6bdb33c6d74c8957b074ceefcdaf0ab8da1b1f42`

This is the non-post-hoc ruler for the program. It defines two different claims:

1. **Catch up** means production workflow parity, truthful cadence, exact-option
   lifecycle and return readiness, bilingual/mobile acceptance, and honest
   authority.
2. **Surpass** means catch-up has already passed, every evaluated decision is
   point-in-time reproducible, the selector is explicitly sparse and may
   abstain, and new exact-option outcomes beat new MomoEdge outcomes on one
   common quote basis.

The goal is complete only at **surpass**. A feature win cannot replace an
outcome gate, and an outcome win cannot replace a missing production workflow.

## Freeze and hindsight fence

The request clock is `2026-08-11T14:30:19Z`. The effective freeze is the later
of that clock and the committer time of the first `origin/main` commit that
contains the exact contract digest above. This prevents a local or backdated
file from creating a prospective cohort.

Rows before the effective freeze are `retrospective_discovery`. Rows at or
after it may be `prospective_after_benchmark_freeze` only when they also carry
the exact benchmark digest. Missing, older, or mismatched rows are excluded and
counted as incomplete. Retrospective evidence may define the feature target;
it can never satisfy an exact-option return gate.

## Frozen competitor context

The authorized aggregate receipt contains 157 history rows, 103 displayed wins,
a 65.6% headline win rate, a +1249.5% additive headline, 129 option-format rows,
and 124 observed option-return marks. It also states that reconstructed option
returns are not a track record, all 157 issue times are date-only, and 18 rows
have no close date.

Those numbers remain useful product context, not a prospective pass threshold.
Using a retrospective additive sum or mixed-basis win rate as if it were a
same-time executable option comparison would manufacture an advantage. The
surpass gate therefore compares only new calls from both systems after the
freeze.

## Registration baseline

At registration, Macro production was healthy at checkout
`e1100ee158a8b18576bbc6130276ef6f8becd373`. Public Flow exposed
`live_flow.meta/v2` with measured clocks and 53/53 source-root coverage for the
captured cycle. Public Prophet marks exposed two exact contracts; one of two
quote clocks was younger than 15 minutes at observation.

The committed evidence ledgers held 384 episodes, 301 H+60 outcomes, 270
session outcomes, and eight campaigns. Every campaign was retrospective and
the benchmark counted zero prospective rows. These live and repository
observations prove the starting state only; they do not pass a completion gate.

## Catch-up gates

All five machine-contract gates must pass:

- `CU_FEATURE_PARITY`: Flow, price/flow heatmap, GEX, PRISM including
  GEX/OI/VOL/UNUSUAL/VEX, unusual baseline, Prophet exact-option
  plan/lifecycle/history, options alerts/preferences, and onboarding are live
  in the normal production product on non-fixture inputs. Every data surface
  carries schema, source clock, freshness, coverage, and authority.
- `CU_CADENCE_TRUTH`: collect within five minutes of 10:00, 11:30, 13:00, and
  14:30 ET across five NYSE sessions. At least 19/20 Flow observations must
  have source age no more
  than 900 seconds and root coverage at least 90%; p95 measured cycle spacing
  must be no more than 900 seconds. Eligible exact-contract marks must have at
  least 90% publication-or-reason coverage; 95% of published eligible marks
  must have quote age no more than 900 seconds and publication age no more than
  600 seconds. A scheduler setting is never cadence evidence.
- `CU_LIFECYCLE_AND_RETURN_READINESS`: exact OCC contract, trigger,
  invalidation, targets, expiry, rule/evidence digests, and immutable lifecycle
  transitions are required. At least ten post-freeze terminal plans must have
  complete ask-to-bid NBBO returns with at least 90% quote-eligible outcome
  completeness.
- `CU_BILINGUAL_MOBILE`: every workflow passes reviewed EN and ZH copy at
  390x844, 768x1024, and 1440x900, with no page overflow, clipped primary
  action, hidden freshness disclosure, or inaccessible lifecycle state.
- `CU_AUTHORITY_HONESTY`: unsigned flow direction stays soft, single-name GEX
  keeps its assumption label, stale/EOD evidence fails closed for intraday use,
  and LLM output cannot originate or escalate a decision.

## Surpass gates

All three gates pass only after catch-up:

- `SP_POINT_IN_TIME_PROVENANCE`: 100% of cohort candidates, decisions, plans,
  transitions, quotes, and outcomes have stable identity, event/observed/
  available clocks, vintage and source digests, quality, and missingness. Every
  issued plan has price-technical and options-structure evidence plus at least
  one macro-regime or news/alternative-data receipt and a frozen falsifier.
- `SP_SPARSE_ABSTENTION`: publish the immutable candidate denominator before
  scoring, reconcile exactly one issue or abstention per candidate, allow zero
  issues, forbid quotas, cap new plans at three per NYSE session, and retain
  stable abstention reasons. Sample accrual cannot force a marginal plan.
- `SP_PROSPECTIVE_OPTION_SUPERIORITY`: evaluate the same covered RTH window,
  after at least 63 covered sessions and at least 60 complete exact-option
  outcomes per system. The 95% stationary-block-bootstrap lower bound for mean
  net return difference, MastermindX minus MomoEdge, must be strictly positive.
  MastermindX's tenth-percentile return must also be no worse than MomoEdge's
  minus 5.0 percentage points.

## Common exact-option basis

Competitor capture remains user-controlled and authorized; raw rows stay
private and only aggregate receipts may enter git. A capture gap over 900
seconds excludes that session from both systems. Covered-session capture must
be at least 95%.

Both systems use licensed OPRA NBBO observations with event and availability
clocks. Entry is the first valid ask at or after the immutable trigger; exit is
the first valid bid at or after the immutable terminal event. An otherwise open
contract receives a frozen expiry-liquidation terminal event at 15:55 ET on its
last tradable session. Either quote must be available within 600 seconds. One
contract and a $0.65 fee per side are fixed. The net return is:

```text
100 * ((100 * exit_bid - fee) - (100 * entry_ask + fee))
    / (100 * entry_ask + fee)
```

Mid, last, EOD, underlying return, intrinsic reconstruction, and later-filled
quotes cannot substitute for missing NBBO. Any selector, lifecycle, quote, or
metric change starts a new version and a new forward cohort.

## Authority

This benchmark is research-only. Catch-up, surpass, and the future completion
receipt do not themselves promote Prophet, Neural Web, model training, signal
origination, alerts, or brokerage authority. Promotion remains a separate
governed decision.
