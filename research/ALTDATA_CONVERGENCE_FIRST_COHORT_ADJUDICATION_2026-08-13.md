# Alt-data convergence — first matured cohort adjudication (2026-08-13)

**Program owner:** Signal Intelligence / altdata

**Evidence cut:** `44c90f8f547` (`engine: regime update 2026-08-13`)

**Surface:** display/context only; no rank, size, gate, or promotion authority

**Verdict:** **HOLD — ADVERSE FIRST MATURITY, NON-DECISION-GRADE.**

The first spine maturity is a real negative-edge observation, not a display defect. It does
**not**, however, establish that the rebooted alt-data construction has failed. The 58-row graded
slice is an **instrument/epoch-contaminated receipt**: cross-sectional name-events emitted on only
two adjacent dates, all on the legacy 21-day clock; five same-ruler theses were already due but
excluded by a stale per-name price cache; family assignment predates later channel-weight caps;
admission counted raw channels before the co-firing correction. The honest action is to keep the
measured demotion, keep accruing, and refuse promotion. Do not flip the sign, suppress the chip,
or tune channels to this one window.

## 1. What matured

The frozen `data/spine/predictions.parquet` slice is:

| field | observed |
|---|---:|
| engine / family | `altdata_conv` / `altdata:convergence` |
| spine-graded rows | 58 |
| same-episode, same-ruler rows already due but ungraded | 5 |
| due-panel sensitivity total | 63 |
| spine-graded distinct thesis `event_key`s | 58 |
| firing dates | 2 |
| spine-graded 2026-07-13 / 2026-07-14 rows | 49 / 9 |
| horizon / direction | 21 days / long only |
| spine-graded directional accuracy (`excess > 0`) | 44.83% |
| spine-graded falsifier-survival rate (`excess >= -5%`) | 65.52% |
| spine-graded mean / median SPY excess | -0.103% / -0.670% |
| spine-graded row-level 95% t interval for mean | [-3.447%, +3.241%] |
| spine-graded two-sided row-level mean / sign p-values | 0.951 / 0.512 |

The interval and p-values are deliberately labelled **row-level** and are anti-conservative for
the market-time question: they treat ticker rows as independent. With only two entry episodes,
there is no honest episode-level inferential test to run.

On the **graded-only** slice, the two date cells disagree: the 2026-07-13 cell averaged
**+0.219%** excess and the 2026-07-14 cell averaged **-1.858%**. Equal-weighting those two dates
gives **-0.819%**, while row-weighting gives **-0.103%**. That apparent positive July 13 cell is
not panel-complete. Five additional July 13 theses—`ACGL`, `AES`, `ALGN`, `ECHO`, and `PSKY`—had
the same August 11 ruler and were already due, but remained ungraded because their
`data/yahoo/*.parquet` ticker caches ended August 7, so `engine.desk_scorer.covers()` withheld
them. The committed
`data/baskets/ohlcv/*.parquet` copies reach August 12; using their August 11 closes against the
committed SPY close makes all five negative. The complete due-panel sensitivity is therefore
**n=63, directional accuracy 41.27%, mean excess -0.507%**, and the July 13 cell becomes
**-0.281%** rather than +0.219%.

The sensitivity strengthens the adverse observation but does not manufacture extra market-time
independence: 63 ticker theses are still only two entry episodes. `spine.measured_ic()` is correct
to report the ledger it actually received—`n=58`, `hit_rate=0.4483`/`wrong_sign=True`—for display
de-escalation. In this spine API, `hit_rate` means directional accuracy, while
`data/altdata/track_record.json` calls the looser -5% falsifier-survival statistic `hit_rate`. The
qledger's date-clustered `n_dates` is the authority-bearing promotion count. The five-name cache
coverage defect should be repaired and backfilled in its owning scorer lane; it must not be hidden
or silently hand-written into the immutable 58-row spine receipt here.

Composition is also narrow. The stored vintage calls 50 rows `altdata_event` and eight
`altdata_flow`. Under the **current** channel weights, 14/58 rows (24.1%) instead route to the
63-day `altdata_mid` or `altdata_slow` families: the July 22 caps on `activist_13d` and
`special_situation`, plus later channel changes, moved the highest-weight driver after these
theses were frozen. This is not data corruption—the stored vintage is immutable—but it means the
cohort is not an evaluation of today's routing construction. Four more rows have co-firing-adjusted
score 1 even though the source ledger admitted them at raw `convergence_score >= 2`; nine rows lose
at least one count under the co-firing map. Forty of 58 contain `special_situation`; 14 contain
`material_8k`. This cohort therefore cannot adjudicate “alt-data convergence” as one general
mechanism.

Two ore leads are worth preserving without promoting them into post-hoc findings. The 12 rows
containing both `material_8k` and `special_situation` averaged -4.52%; the seven rows containing
`activist_13d` averaged -3.78%. Both are entangled with the same two-date tape, and both channels
were subsequently capped to context by independent studies. They are candidates for prospective,
versioned arms—not explanations retrofitted onto this cohort.

The ruler also spans two contract epochs. W2's written preregistration calls the event ruler
“21 calendar-day window ≈ 15 trading days,” while the source ledger actually set `check_by` with
`BusinessDay(21)` (July 13→August 11; July 14→August 12). The later P0a clock contract correctly
declares new altdata/qledger rungs as `trading_days` and preserves these pre-P0a rows as
`legacy_calendar_unstamped`. Call this **ruler-contract drift**, not a retroactive “wrong clock”:
the matured slice matches the later trading-day choice but did not test the original written W2
calendar-day ruler. Those epochs may not be presented as one preregistered construction.

## 2. Gauntlet read

`research/ALTDATA_REBOOT.md` pre-registered family-specific rulers and requires matched-placebo
comparison before promotion. At the same evidence cut, the qledger says:

| promotion unit | ruler | n_obs | n_dates | hit rate | mean excess | Wilson low | state |
|---|---:|---:|---:|---:|---:|---:|---|
| `altdata_event` | 21d | 75 | 7 | 46.67% | +0.510% | 0.1582 | ACCRUING |
| `altdata_flow` | 21d | 18 | 5 | 50.00% | +0.871% | 0.1176 | ACCRUING |

Both miss the frozen `n_dates >= 25` floor by a wide margin. Neither clears the Wilson lower-bound
bar against a coin flip, and neither has earned the matched-control/placebo, block-stability, and
incremental-information legs required for promotion. The spine's row-level negative mean and the
qledger's currently positive family means are not contradictory: they answer different questions
over different grains and vintages. The former is the exact 58-row legacy spine maturity; the
latter includes later family fires and grades. It is context, not a clean counter-read on this
cohort. The promotion verdict is therefore **NO**.

## 3. Ore-ledger ruling

Under the ore law, a null closes only the construction actually tested.

**What this cohort closes:**

- Any claim that generic, long-only `altdata:convergence` demonstrated positive standalone 21-day
  edge in its first two firing dates.
- Any use of the cross-sectional `n=58` as though it were 58 independent timing episodes.
- Any promotion, channel weight change, or sign reversal justified by this first read.

**What it does not close:**

- The pre-registered `altdata_event` and `altdata_flow` constructions, which remain below their
  independent-date floors.
- The ungraded 63-day `altdata_mid` and `altdata_slow` primary constructions.
- Convergence as display/context or as a confluence input to another independently gauntleted
  signal.
- The search space for a better convergence ranker.

This is not enough evidence to label the construction broken, and it is not enough regime
coverage to blame the July window. July 13 was Q1/`RISK_ON`; July 14 was Q1/`MIXED`. Both carried
normalizing-vol/rate-pressure stamps. At the evidence cut, the current tape was Q2 with
raw/pending Q3 and `TRANSITIONING`. The current tape is therefore not in-sample of this two-date
cohort. The bounded statement is: **the first, date-concentrated legacy 21-day maturity returned
no standalone edge.** Construction-versus-window remains unidentified.

No `DO_NOT_REBUILD` row is minted: this adjudication neither kills nor forbids nor defers the
program. It records a null, preserves the existing display ceiling, and applies the already-frozen
promotion gate.

## 4. Binding next read

1. Keep the live display behavior from PR #5547: measured basis, printed record, and
   wrong-sign `high -> medium` de-escalation.
2. Continue the family ledgers unchanged. Do not suppress null fires; do not back-edit the 58
   theses; do not optimize channel inclusion or direction after seeing this cohort.
3. Re-adjudicate `altdata_event@21d` and `altdata_flow@21d` separately only when the existing
   promotion instrument is eligible to speak: at least 25 independent date clusters, with the
   matched-placebo/control leg, date-block uncertainty, and the registered incremental-information
   check printed regardless of sign.
4. At that read, report channel and sector composition, missing/unscorable names, date and regime
   coverage, and whether the then-current tape is represented. A single cross-sectional burst may
   never be promoted by its ticker count.
5. Judge `altdata_mid` and `altdata_slow` only at their registered 63-day primary rulers. Their
   absence from this cohort is ungraded, not a null.
6. The next construction must freeze the instrument it means to test: explicit `horizon_unit`,
   current family/version metadata, and co-firing-adjusted admission (`>=2` independent clusters),
   with a new vintage. Do not rewrite or relabel these 58 rows. That admission change is a new
   construction and belongs in its own preregistered implementation, not in this adjudication PR.

### Untested variants

- Current family routing at the registered 21-trading-session event/flow rulers.
- A convergence episode admitted on at least two co-firing-adjusted clusters rather than two raw
  channels.
- The registered 63-day primary rulers for `altdata_mid` and `altdata_slow`.
- Regime-conditioned behavior across independent market episodes, including the current
  Q2→Q3 transition tape.
- The `material_8k + special_situation` and `activist_13d` ore leads under prospective,
  pre-registered arms; their within-cohort cuts are descriptive only.

## 5. Reproduction

The primary slice is reproducible without network access:

```python
import json
import pandas as pd

spine = pd.read_parquet("data/spine/predictions.parquet")
g = spine[(spine.engine == "altdata_conv") &
          (spine.family == "altdata:convergence") &
          spine.outcome_graded.fillna(False)]
signed = g.outcome_excess * g.direction
print(len(g), g.event_key.nunique(), g.as_of.value_counts().sort_index().to_dict())
print((signed > 0).mean(), signed.mean(), signed.median())

theses = {r["id"]: r for r in map(json.loads, open("data/altdata/theses.jsonl"))}
print(pd.Series([theses[s.removeprefix("altdata_conv:")].get("claim_family")
                 for s in g.signal_id]).value_counts(dropna=False))
```

The promotion-frame values are the committed `by_family` entries in
`site/qledger/track_record.json`; `engine.qledger.promotion_check()` is the governing gate.

The due-panel sensitivity uses only committed local bars:

```python
missing = ["ACGL", "AES", "ALGN", "ECHO", "PSKY"]
source = {r["ticker"]: r for r in map(json.loads, open("data/altdata/theses.jsonl"))
          if r.get("state_asof") == "2026-07-13" and r.get("check_by") == "2026-08-11"}
spy_end = pd.read_parquet("data/yahoo/SPY.parquet").loc[:"2026-08-11", "close"].iloc[-1]
extra = []
for ticker in missing:
    thesis = source[ticker]
    ticker_end = pd.read_parquet(
        f"data/baskets/ohlcv/{ticker}.parquet"
    ).loc[:"2026-08-11", "close"].iloc[-1]
    extra.append((ticker_end / thesis["entry_levels"][ticker] - 1) -
                 (spy_end / thesis["entry_levels"]["SPY"] - 1))
due_panel = list(signed.astype(float)) + extra
print(len(due_panel), sum(x > 0 for x in due_panel) / len(due_panel), sum(due_panel) / len(due_panel))
```
