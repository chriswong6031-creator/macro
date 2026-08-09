# CN limit-move alpha — Wave-2 band-progress construction protocol

**Frozen:** 2026-08-08 (America/Vancouver), before any Wave-2 band-progress
measurement  
**Authority:** research/display context only; no ranking, sizing, gating, Prophet,
Neural Web, or live-trading authority  
**Construction family:** partial-band progress, exact upper-band touches followed by
retreat, and sealed closes  
**Independence boundary:** no `claude/cn-limit-w1-*` result, receipt, branch, ref, or
worktree may be inspected

**Pre-measurement contract correction (2026-08-09):** no Wave-2 outcome, transition,
return, fill, or strategy measurement had run when the canonical full-A adapter became
available. The input binding below was therefore corrected from placeholder paths to the
frozen `china_tushare_spine` v1 contract. On that exact vendor-limit plane, legal touches
and seals use bounded integer-cent equality (`high_cents == up_limit_cents` and
`close_cents == up_limit_cents`), not defensive `>=` comparisons. Any event-eligible OHLC
outside `[down_limit_cents, up_limit_cents]` is quarantined. This is a source-contract
correction made before measurement, not threshold tuning after returns were observed; the
taxonomy, progress cut points, information clock, exits, costs, and ORE law are unchanged.
Commit `b2548fdc095` is retained only as the v1 layout/schema **shape snapshot** used to
write this adapter. It has no completeness, licensing, collection, or measurement-readiness
authority after adversarial review; promotion requires a remediated spine commit and schema.

This protocol answers one definitional question without collapsing unlike states:
an A-share can complete a meaningful part of its permitted daily move without closing
at the exact upper limit, and a stock that touches its limit before retreating is a
different object from a stock that never touches it. A legal sealed close, a tolerant
data-feed proxy, a failed seal, and a partial no-touch advance therefore remain separate
constructions throughout the packet.

The thresholds, clocks, fills, exits, costs, clustering rules, and outcome labels below
are frozen before outcome measurement. They may not be changed after seeing a return.

## 1. Authoritative substrate and hard fail-closed gate

The historical `data/china_stocks_raw/*.parquet` plane is **forbidden for strategy
measurement**. Despite its directory name, the collector contract says Yahoo's raw close
remains split-adjusted. The current audit finds millions of stored prior closes off the
legal CNY 0.01 tick. A scaled history cannot reconstruct the exact legal daily ceiling,
whether the arithmetic uses half-up or ties-to-even rounding.

The measurement runner must instead consume the frozen full-A TuShare relative contract
beneath an operator-supplied private spine root (`data/china_tushare_spine/` is only the
legacy CLI default, not a required repo-local location):

1. unadjusted `daily/year=YYYY/month=MM/part.parquet` rows keyed by canonical security and
   exact session, with integer-cent OHLC/pre-close and positive-volume state;
2. vendor `stk_limit/year=YYYY/month=MM/part.parquet` rows on the same key, with integer-cent
   upper/lower limits and source-limit presence;
3. canonical `event_daily/year=YYYY/month=MM/part.parquet`, the one-to-one daily/limit join;
4. `reference/market_sessions.parquet`, `reference/security_master.parquet`, monthly
   `stock_st`, and daily security coverage; and
5. `completeness_manifest.json`, validated against
   `contracts/cn_tushare_a_share_spine_manifest.v1.schema.json`, including hashes for every
   referenced file and partition.

The v1 event plane does not itself materialize the dense `rule_cohort`, exact-session
`session_eligible`, complete ST/IPO no-limit state, or corporate-action-reference state
needed by this protocol. Those fields remain explicit blockers until a provenance-bearing
overlay exists. The consumer may not silently derive them from ticker prefixes or observed
price ratios.

TuShare documents `daily` as unadjusted and explicitly labels `pre_close` as the
ex-right previous close. TuShare documents `stk_limit` as the daily market-wide upper
and lower limit-price table. The joined vendor `up_limit` and `down_limit` values are
the measurement authorities; a locally recomputed band is an audit value only.

The runner emits no strategy metrics unless all of these gates pass:

- every required input exists and its SHA-256 is recorded;
- every reference and partition hash is bound to one promoted-generation identity; correct
  paths and independent hashes from mixed collection vintages are insufficient;
- each source has unique `(ticker, date)` keys after `.SH -> .SS` normalization;
- every measured daily row joins exactly one attested market session and one security-session
  record;
- missing `stk_limit` joins are quarantined and remain below 0.5% of otherwise eligible
  ordinary-band rows;
- `up_limit > pre_close >= down_limit > 0` (the one-cent price floor can make the lower
  bound equal pre-close), OHLC is positive, and `vol > 0` for every
  measured signal row;
- every event-eligible open, high, low, and close lies inside the exact inclusive vendor
  interval `[down_limit_cents, up_limit_cents]`; out-of-bound rows are quarantined rather
  than classified with `>=`/`<=` fallbacks;
- prices represented as legal ticks are CNY 0.01-aligned within a fixed numerical epsilon;
- post-corporate-action reference prices come from the vendor row rather than a shifted
  prior stored close; and
- the requested exit horizon has an exact attested-session clock.

If a gate fails or the authoritative planes are absent, the only permissible output is a
deterministic `BLOCKED_SUBSTRATE` receipt plus non-return data diagnostics. Missing rows,
halts, no-limit sessions, unknown rules, and corporate-action ambiguity are null states,
not silent drops or later-date hops.

Primary mechanics references:

- TuShare `daily`: https://tushare.pro/document/1?doc_id=27
- TuShare `stk_limit`: https://tushare.pro/document/2?doc_id=183
- SZSE 2026 Trading Rules, rule 3.3.19 (`四舍五入` to CNY 0.01):
  https://docs.static.szse.cn/www/lawrules/rule/trade/current/W020260424690713155663.pdf

## 2. Tick rounding audit

`half_up_yuan_tick(x)` uses decimal `ROUND_HALF_UP` to CNY 0.01. Python/NumPy
`round` is not an exchange rule because binary representation and ties-to-even can differ
at half-cent boundaries. The half-up function is frozen for rule reconciliation and tests;
it does **not** replace vendor `stk_limit` in the measurement.

On the authoritative joined plane, the receipt must print:

- vendor `up_limit` versus half-up reconstruction differences by board/rule cohort;
- vendor `down_limit` versus half-up reconstruction differences;
- half-up versus legacy Python/NumPy-round price differences; and
- exact strict-seal and exact-touch event-key deltas under the two local rounding rules.

The legacy Yahoo plane may be scanned only by an explicit audit mode. That output is
labelled `SUBSTRATE_INVALID_DIAGNOSTIC_ONLY` and is limited to tick-integrity and event-key
delta counts. It may not contain returns, transition rates, strategy metrics, or verdicts.

## 3. Canonical construction key

Every result is keyed as:

```text
K = universe × board/rule cohort × signal state × information cutoff
    × order protocol × fill rule × outcome/exit × portfolio rule × cost × split
```

Two rows with any different coordinate are not replications. Main 10%, risk-warning 5%
or 10%, ChiNext 10%, ChiNext 20%, STAR 20%, and BSE 30% are always separate cohorts.
No pooled headline is allowed.

The four frozen date blocks match the independent SOL Wave-1 packet:

- `train_2011_2019`: 2011-01-01 through 2019-12-31;
- `calibration_2020_2023`: 2020-01-01 through 2023-12-31;
- `historical_replay_after_common_prior`: 2024-01-02 through 2026-06-12;
- `vendor_tail_audit`: 2026-06-15 through 2026-08-07.

These are descriptive replay blocks, not virgin holdouts. Ten attested sessions at a model
boundary are purged if a later model is fitted. This packet fits no model.

## 4. Exact band coordinates

For an eligible session `D`, use the vendor values:

```text
band_span_D     = up_limit_D - pre_close_D
high_progress_D = (high_D  - pre_close_D) / band_span_D
close_progress_D = (close_D - pre_close_D) / band_span_D
```

Progress is retained as a continuous audit field. Values outside ordinary ranges are
printed and quarantined when they conflict with the security/rule spine. A 6% close under
a 10% band is approximately 0.6 progress; the same 6% close under a 20% band is
approximately 0.3 progress. That is why absolute returns are never pooled across widths.

The state predicates are evaluated only after the full OHLC bar passes the inclusive
vendor-bound gate. On the integer-cent authority fields they are:

- `strict_seal`: `close_cents == up_limit_cents` (and therefore
  `high_cents == up_limit_cents` under valid OHLC ordering);
- `tolerant_close`: `close_cents * 1000 >= up_limit_cents * 998`;
- `tolerant_only`: tolerant close but not strict seal;
- `exact_touch`: `high_cents == up_limit_cents`;
- `exact_touch_failed`: exact touch but not strict seal; and
- `partial_no_touch`: `high_cents < up_limit_cents`.

`tolerant_close` is a feed-noise sensitivity, **not** a claim that the exchange legally
sealed the name. A close at +9.9%, +9.5%, or +8% is therefore never silently renamed a
strict +10% seal.

## 5. Frozen non-combinatorial signal families

The packet measures these one-dimensional constructions exactly as written. It does not
search a high-by-close grid, tune cut points, or retain attractive cells after inspection.

### 5.1 Seals and exact-touch retreats (mutually exclusive)

| Construction ID | Frozen predicate |
|---|---|
| `S_STRICT` | strict sealed close |
| `S_TOL_ONLY` | tolerant-only close, printed as sensitivity rather than legal seal |
| `TF_TOL_ONLY` | exact touch, close below the legal ceiling but inside the 0.2% tolerant cushion |
| `TF_CP_095_100` | exact-touch failure outside the cushion, `0.95 <= close_progress < 1.00` |
| `TF_CP_080_095` | exact-touch failure, `0.80 <= close_progress < 0.95` |
| `TF_CP_060_080` | exact-touch failure, `0.60 <= close_progress < 0.80` |
| `TF_CP_LT060` | exact-touch failure, `close_progress < 0.60` |

`S_TOL_ONLY` and `TF_TOL_ONLY` describe the same close sensitivity only when an exact
touch is observed. They are reported in separate seal-sensitivity and touch-morphology
panels; they are never added together in one portfolio.

### 5.2 Partial no-touch progress (parallel marginals)

High-progress constructions:

- `NT_H_095_100`, `NT_H_080_095`, `NT_H_060_080`, `NT_H_040_060`.

Close-progress constructions:

- `NT_C_095_100`, `NT_C_080_095`, `NT_C_060_080`, `NT_C_040_060`.

All require `high < up_limit`. Boundaries are left-closed/right-open. Rows below 0.40
remain in the denominator census but do not become signals. High and close marginals are
separate research families; a row may appear once in each, so no aggregate is allowed to
sum those families.

## 6. D+1 state outcomes

Information freezes after the complete `D` close. On the exact attested successor session,
the packet reports these prespecified outcomes with Wilson 95% intervals:

- strict sealed close;
- tolerant-only close;
- exact upper touch;
- exact-touch failed seal;
- close progress at least 0.80;
- close progress at least 0.60; and
- missing, halted/no-trade, no-limit, rule-unknown, and right-censored states.

Daily high/low cannot reveal first-touch time, path order, seal duration, break count,
replenishment, cancellation, or whether the close was reached in the closing auction. No
daily result may use those words as measured facts.

## 7. Entry, fill, and T+1-legal exits

### Entry: `D1_OPEN_DAILY_PROXY`

- Decision information ends at `D` close.
- The order is modelled at the exact `D+1` reported daily open.
- A positive-volume, valid OHLC row and joined D+1 vendor limits are required.
- `open >= up_limit * (1 - 0.002)` is an upper-queue **no-fill**.
- Missing, halted/no-trade, no-limit, rule-unknown, invalid-price, and upper-queue rows
  are nonfills and retain cash with contribution zero.
- Every other row is called `daily_tradability_proxy`, never a verified fill.

The realised D+1 open is an execution result, not a selection feature. The packet cannot
claim a post-09:25 decision filled at that same reported daily open.

### Frozen exits

A D+1 purchase cannot be sold before D+2:

- `E1_OPEN`: D+2 reported daily open;
- `E1_CLOSE`: D+2 reported daily close; and
- `E3_CLOSE`: D+4 reported daily close (three-session holding ruler from D+1).

An exit at or inside the 0.2% lower-limit cushion carries one exact attested session at a
time to the first non-lower-queued open. Missing/zero-volume intermediate sessions are
unresolved; the runner never jumps directly to a later resumption. Right-censored and
unresolved filled positions remain explicitly null rather than being recoded as nonfills.

Round-trip cost sensitivities are frozen at `0`, `30`, `60`, and `100` basis points and
apply only to daily-proxy fills. Candidate expectancy retains all nonfills as zero:

```text
candidate_contribution = 0                                  if no daily proxy fill
candidate_contribution = gross_return - round_trip_cost     if fill and exit resolve
candidate_contribution = null                               if filled exit is unresolved
```

Every table prints candidate count, proxy-fill count, nonfill reason counts, resolved-exit
count, unresolved count, conditional fill return, and cash-zero candidate contribution.

## 8. Dependence, clustering, and duplicate positions

Signals are clustered both by `signal_date` and by immutable run:

- a run is a ticker/construction sequence on adjacent attested sessions;
- a one-session break starts a new run;
- path words are never reconstructed from the ticker's next observed bar when an attested
  session is missing.

For each construction/cohort/split/exit at 60 bp, the receipt prints the row-weighted point
estimate plus deterministic 1,000-replicate date-cluster and run-cluster bootstrap 95%
intervals. Event rates also print Wilson 95% intervals. `THIN` is mandatory at `n < 20`.

The main panel is an event-row diagnostic, not a portfolio. A separate no-duplicate state
machine accepts the first signal for a ticker and rejects later signals until the named exit
resolves. Rejected overlaps stay cash; no ex-post replacement name is admitted. Counts and
cash-zero returns for accepted, overlap-rejected, queue-rejected, missing, and unresolved
states are printed for every exit.

## 9. Determinism and receipt identity

The canonical command is run from repo root under `TZ=UTC`. JSON keys are sorted, floating
values are normalized, bootstrap seed is `20260808`, and each input, source file, protocol,
configuration, and output is SHA-256 stamped. A second run over identical inputs must produce
byte-identical JSON and Markdown. Duplicate source keys, output mutation, or a different input
hash fails loudly.

## 10. Exact verdict language

An adverse cell may only close its complete canonical key. It may not kill partial-band
progress, failed seals, near-limit moves, or rerating windows as a family. The legal-seal
probability panel and the fill/cost panel receive separate verdicts. No probability lift is
called alpha without a corresponding daily-proxy return, and no daily proxy is called an
executed fill.

Until the TuShare `daily` + `stk_limit` + security-session spine exists and passes Section 1,
the only correct verdict is:

`BLOCKED_SUBSTRATE_NO_STRATEGY_MEASUREMENT`

## 11. UNTESTED VARIANTS — strict ORE ledger

The following remain open even if every frozen construction is eventually adverse:

- first-touch, first-seal, last-seal, break/reseal, cumulative sealed minutes, and path order;
- order-wall size, growth, depletion, replenishment, cancellations, queue rank, partial fills,
  and signed trade flow;
- real opening-auction imbalance and a post-09:25 decision executed at 09:30 or the next
  complete minute;
- exact failed-seal retreat timing: early absorption versus late exhaustion;
- closing-auction-only seals and the post-2026-07-06 post-close fixed-price venue;
- intraday upper-then-lower versus lower-then-upper traversal;
- multi-step cadence words such as `P-P-B`, `B-P-P`, `B-N-B`, and `F-N-B`;
- flexible 3/5/10-session first-passage to +6%, +8%, or one full band before a frozen
  adverse barrier;
- T+1 inventory vintages, volume-at-price cost stacks, free float, restricted-share unlocks,
  and normalized queue elasticity;
- PIT theme topology, locked-leader spectator substitution, and failed-leader redistribution;
- ladder topology, acceleration/deceleration hysteresis, and regime interactions;
- availability-safe LHB/block sponsorship and catalyst classes;
- full-universe delisted-name completeness, historical risk-warning identity, exact IPO
  no-limit regimes, suspensions, and corporate-action reference-price history not covered by
  the forthcoming spine;
- locally calibrated main/ChiNext/STAR/BSE models, nonlinear mixtures, threshold/cash books,
  and nested holdout confirmation;
- commissions, stamp duty, live slippage, order rejection, capacity, sector caps, and
  mark-to-market portfolio drawdown beyond the stated cost/proxy rulers; and
- prospective grading for at least ten exact sessions and every authority-promotion gauntlet.

The purchased historical minute, pre-market share-capital, and auction datasets are the
explicit bridge to the first six open items. Daily bars are not a substitute for them.
