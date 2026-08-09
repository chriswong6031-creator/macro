# Prophet US outage and date-integrity adjudication — 2026-08-08

## Decision

The missing August 6/7 surface was not one defect. It was three interacting defects:

1. Prophet ran inside a multi-hour engine job and its files were not committed until the
   far end of that job. A later wedge/cancel could erase an already-successful Prophet run.
2. The August 6 engine never reached Prophet because the weekly S&P 500 cap refresh wedged
   for 3h36m. The August 7 scheduled engine reached Prophet after midnight and published on
   August 8, so there is no honest August 7 publication record to manufacture.
3. The UI's old `signal_date` was actually a base/hold formation label, while `entry_date`
   was sometimes the run date rather than the session whose close supplied `entry`. Thus a
   plan created on August 6 could still appear under a July or August 5 label.

The repair keeps immutable publication records, adds explicit causal/price/publication
clocks, applies proven historical corrections through append-only overlays, quarantines
uncertain or temporally impossible records, removes the 12-plan intake slice, and makes a
successful Prophet build durable immediately.

## Workflow evidence

| Market/run window | GitHub run | What happened | Prophet consequence |
|---|---:|---|---|
| Aug 5 scheduled | `31056495943` | Prophet succeeded 03:43:44–03:43:48Z; engine was later cancelled at its job cap before `commit engine outputs`. | Generated Prophet files were not durable. |
| Aug 6 scheduled | `31138544929` | `S&P 500 heatmap real-cap reference` ran 13:59:26–17:35:32Z and was cancelled; all later core steps were skipped. | Prophet never ran. |
| Aug 7 manual recovery | `31210097197` | Prophet itself wedged 23:07:57–02:00:56Z and was cancelled at the job cap. | No completed Prophet publication. |
| Aug 7 scheduled / Aug 8 execution | `31226002132` | Prophet succeeded 07:06:33–07:06:57Z and the engine completed. | Recovery plans were published with an August 8 run clock. |
| Aug 8 recovery | `31254922905` | Prophet succeeded 15:29:04–15:29:25Z. | A second recovery batch was published. |

This explains why inventing August 6 or August 7 rows after the fact would be wrong: one
run never reached Prophet and another crossed midnight before a successful publication.

## Date-family contract

| Field | Meaning | Historical policy |
|---|---|---|
| `formation_date` | Base/hold anchor and immutable plan-ID date component. | May be added when the ID/raw legacy label proves it. ID never changes. |
| `signal_date` | Causal fired-event close: T1 marker knowability close or native T2 cross close. | Never inferred from price matching or an unrelated marker. |
| `confirmed_date` | T1 marker buy-filter confirmation close. | Nullable; never used as T2 confirmation. |
| `observed_date` | Session that produced the tier verdict. | T3 uses this with `signal_date=null` because its event has not fired. |
| `price_basis_date` / `entry_date` | Session whose close supplied the plan's displayed entry price and starts grading. | Correct only from creation-vintage price/board evidence. |
| `recorded_at` | First publication/run date. | Correct from the immutable plan plus its first-add commit. |
| legacy marker `date` | Immutable 3D bucket-open chart label. | Preserved; it is not renamed into an event close. |

For new boards, T1 and T2 carry `tier_event_date`; T3/T4 carry no event and disclose their
observation vintage. Prophet admits actionable T1–T3 only. T4 remains visible as a forming
board opportunity but cannot originate an actionable plan.

## Marker adjudication

The outage-window replay found 25 markers with legacy bucket labels on August 5 whose 3D
bucket was not knowable until the August 7 close. Those labels are not rewritten. The
marker schema now preserves `date=2026-08-05` and adds `signal_date=2026-08-07`; buy/rebuy
`confirmed_date` remains null until its forward filter clears. Because first publication
was not persisted for old markers, historical `recorded_at` remains null rather than being
back-stamped from Git history.

The merge law is fail-closed: only an exact immutable marker label may fill a previously
null derived date. A nearby tolerance match with a different frozen label cannot graft the
other bucket's dates. Old pending markers cannot acquire a confirmation date unless their
pending-to-final verdict advances atomically.

## Prophet signal-date adjudication

Price matching cannot prove a tier event. Therefore the chronology generator emits **zero
`signal_date` corrections**. Two plan dates proposed for rewriting by the earlier marker-
based audit were replayed against their creation vintages and rejected:

- `NVDA-BULL-20260805`: first appears in commit
  `f13016b3e2339d7de9a63e1580c29c3d2883021e`. Its creation board admitted NVDA on T2;
  the native T2 event was August 5. The August 7 blocked §7 marker was unrelated. The
  existing August 5 plan signal is correct. Entry 224.0 matches the August 7 close, so
  `price_basis_date=2026-08-07` and `recorded_at=2026-08-08`.
- `GE-BULL-20260805`: first appears in commit
  `2dfebf35dbdf27d4240b655ebbee0787bb85df4c`. Its creation board admitted GE on T2;
  the native T2 event and 381.2 entry-price close were both August 5. A later reconstructed
  §7 marker ending August 4 did not originate the plan. The existing August 5 signal is
  retained; `price_basis_date=2026-08-05`, `recorded_at=2026-08-06`.

Neither plan proves a real fill: both remained pre-trigger. `entry_date` here is the plan's
price/grading basis, not a claim that an order executed.

## Plan and ledger correction receipt

The reproducible receipt is
`research/prophet_us_audit/OUTAGE_PLAN_CHRONOLOGY_2026-08-08.json`, generated by:

```bash
python3 -m scripts.audit_prophet_plan_chronology \
  --from 2026-08-03 --to 2026-08-08 \
  --corrected-at 2026-08-08 \
  --output research/prophet_us_audit/OUTAGE_PLAN_CHRONOLOGY_2026-08-08.json \
  --plan-corrections-output data/prophet/plan_corrections.jsonl \
  --ledger-corrections-output data/prophet/ledger_corrections.jsonl
```

Results over 42 plans first published in the window:

- 27 have a current, session-coherent creation price basis.
- 5 match the publication session but their creation board explicitly carried mixed
  vintages: 3 remain disclosed as `audited_mixed_vintage`; SE is quarantined because
  its creation tier was non-actionable T4, and WB is quarantined because no causal
  admission tier was persisted.
- 8 used a price session older than the last completed session at publication.
- 2 lack correction-grade creation-vintage price evidence.
- 10 plans have stale/unknown price chronology; one additional plan was originated from
  non-actionable T4 and one has no persisted causal admission tier. All 12 are
  quarantined from action and record claims. Their raw plan files remain unchanged, and
  a future current signal may re-originate the ticker.

`data/prophet/plan_corrections.jsonl` contains 373 append-only field corrections across
42 plans. In addition to proven price/publication clocks and dispositions, every legacy
plan is explicitly labeled `signal_date_basis=legacy_formation_alias`; creation-vintage
tier and source-marker provenance are projected where present. No plan `signal_date` is
rewritten. `data/prophet/ledger_corrections.jsonl` contains nine corrections for the only
intersecting terminal row, `SYY-BULL-20260731`. SYY's raw close predates publication; its
proven date facts are projected, but its outcome remains quarantined and is excluded from
the index summary, Brain, Governor, Stage Shadow, and Chronicle.

## Opportunity-width decision

The 12-plan limit was an attention/display cap in the origination lane. It was applied
after duplicate/open-plan suppression and could still hide valid lower-ranked survivors;
two August 8 recovery runs also reset the slice and admitted only 12 each time.

Live origination is now lossless: every ranked row that passes the existing admission
criteria and is neither a duplicate ID nor blocked by an already-open same-direction plan
is attempted. Validation failures are itemized. The full ranked long tail remains in the
index even when management enrichment lacks price history. Featured shelves, alerts,
sector limits, capital/risk limits, and challenger experiments retain their own explicit
caps. Arena C0/C6 mirror the uncapped champion; registered challengers keep a 12-name cap
so the experiment remains comparable.

## Operational controls shipped

- The heatmap refresh that blocked August 6 is bounded to 15 minutes and remains nonfatal.
- Prophet itself is bounded and streams logs instead of buffering a silent wedge.
- A successful Prophet build is checkpointed immediately, before the regional/tail band.
- The checkpoint publishes only a hash-verified allowlist delta from a source checkout
  proven to be `main`; off-main dispatches cannot publish to `main`.
- Each first-add plan is committed atomically with an immutable origination receipt that
  binds the exact admitted board row and plan bytes to their hashes, the source checkout,
  and the board's price-vintage contract. Later chronology audits use that receipt ahead
  of mutable checkout artifacts and fail closed on missing or ambiguous receipt evidence.
- Correction ledgers are protected inputs. No whole-root delete, conflict preference, or
  same-path race can overwrite a newer correction on `main`.
- The late broad engine commit cannot bypass a refused checkpoint or republish stale
  Prophet roots.
- Git is the publication authority. R2 receives only the accepted checkpoint's exact
  index blob, with conditional-write protection and checkpoint/hash metadata; direct
  generator publication is disabled.
- Freshness monitors `source_asof=staleness.price_through`, not the rerun/publication
  clock, and requires `source_basis=panel_majority` with delayed, unknown, and
  mixed-vintage flags all false. Re-stamping a frozen wrapper can no longer look healthy.
- Ledger advancement and quarantine persistence are build-critical. Either failing now
  aborts before index publication instead of silently emitting a partial or rehabilitated
  record set.
- Stage Shadow applies canonical corrections and quarantine before grading, persists its
  raw PIT rows and append-only revisions through its own guarded checkpoint, and refuses
  partial cohort publication. The previously ignored raw Stage ledger is not recoverable
  from Git history; the first accepted live run bootstraps it deterministically from the
  canonical effective Prophet projection, after which its bytes are durable.
- Chronicle retracts only receipt-backed Prophet quarantine IDs from its effective union,
  fingerprints both correction authorities in its rebuild closure, and leaves the raw
  Prophet ledger untouched.
- Arena begins a disclosed `price_basis_trigger_v2` era. It shares the live date and stale-
  board gates, grades from the price-basis session, preserves trigger state, and records a
  never-triggered plan as `NO_ENTRY` with null P&L. The old top-level v1 ledgers remain
  sealed and audit-counted rather than being silently reinterpreted.
- The US board remains a full ranked/searchable opportunity set. Its green-glow shelf is
  explicitly only a featured attention layer; it does not determine Prophet admission.
