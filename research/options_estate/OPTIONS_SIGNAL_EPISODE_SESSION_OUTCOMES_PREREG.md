# Options signal-episode session outcomes preregistration

Status: **frozen evidence-stage contract / zero authority**
Owner: Options Intelligence Program
Producer: `scripts/build_options_signal_episode.py` only

## Question and unit

Measure the underlying return and observed coarse-path proxies after each immutable
`options.signal_episode/v1` watch event at five predeclared horizons. The unit is
exactly one `(episode_id, horizon)` row. A horizon row never creates another
candidate, signal, campaign, recommendation, position, or trade.

The semantic append key is exactly `(episode_id, horizon)`. The stable identity
is `oout_` plus the first 24 hex characters of SHA-256 over the new schema,
`session-close-aligned-bars/v1`, episode ID, and horizon. One matured horizon
never suppresses another.

The frozen horizons and NYSE-session offsets are:

| horizon | offset |
|---|---:|
| `eod` | 0 |
| `1d` | 1 |
| `3d` | 3 |
| `5d` | 5 |
| `10d` | 10 |

No expiry horizon is admitted in v1. Expiry and last-trade semantics require a
later contract and adjudication.

## Point-in-time clocks

- `horizon_anchor` is the episode's immutable `available_at`.
- `target_session` is
  `lib.nyse_calendar.session_n_forward(episode.session_date, offset)`.
- `target_time` is the declared close from
  `nyse_session_window_recurring_schedule/v1`. That v1 basis combines the NYSE
  session/holiday calendar with the repository's modeled recurring early-close
  rules. It is not an authoritative one-off exchange schedule.
- Entry is the first regular-session bar open at or after `available_at`.
- Exit price is the close of the bar covering `target_time`; the bar start and
  declared scheduled-close clock are stored separately. If the source has no
  close-covering bar at that declared clock, the horizon stays pending.
- For a complete row, `matured_at` is the later of declared target close plus
  the vendor delay and the exact source receipt's `source_available_at`. A
  clock-terminal EOD row also cannot mature before `episode.available_at`.
  Nothing persists before `computed_at >= matured_at`.

The selected path contains only RTH bars. Each included session must have a
complete declared-cadence grid from its admitted first bar through its
close-covering bar. Overnight, weekend, and holiday gaps are expected; an
interior session gap remains pending. The admitted first bar must be no more
than `1.10 * bar_seconds` after the applicable availability/session-open clock;
there is no five-minute floor. Cadence-dependent late entries stay pending
because a future finer source can resolve them. `uncovered_open_seconds`
discloses the interval from each scheduled open to the first retained bar. In
particular, production Polygon hourly bars are UTC-clock-aligned and normally
leave a 1,800-second opening stub on a regular full session.

## Immutable evidence and metrics

The new append-only ledger is:

```text
data/options_signal_episode/outcomes_session.jsonl
options.signal_episode_session_outcome/v1
```

Each complete row binds the existing receipt-before → exact parquet bytes →
receipt-after snapshot. The bounded
`options.signal_episode_session_price_evidence/v1` block stores the exact entry
bar time/open, exit bar time/declared close time/close, timestamped observed high
and low extrema, total count, and one cadence manifest per included session.
Each manifest carries its first/last bar times, opening-stub disclosure,
selected-span observation/expected counts, and a creation-time
`session_path_sha256` commitment to that session's canonical OHLC observations.
`manifest_root_sha256` is the recomputable SHA-256 of the ordered canonical
manifest list.

Return and the observed-path MFE/MAE proxies reproduce from the compact row;
manifest clocks, counts, leaf-digest formats, and the root commitment validate
without expanding ledger size with the horizon. The row is metric-replayable
and path-committed, not full-path-replayable. Full OHLC replay would require a
separately retained exact source snapshot; this v1 creates no CAS/R2 archive and
makes no durability claim for the mutable cache. A later cache correction cannot
mutate an already-appended JSONL row, but it may make full-path replay unavailable.
The fixed size regression requires a 1-minute 10-session row to remain below
8,000 canonical JSON bytes and all five rows for one episode below 30,000 bytes.

Pending rows are never appended. Clock-only terminal incomplete is allowed only
when `available_at >= target_time` (therefore EOD in v1); no cadence-dependent
condition is frozen as terminal.

## Authority and promotion fence

Every row is `label_authority=research_only` and
`training_eligible=false`. The option outcome is exactly unavailable with
`no_executable_nbbo_quote_path`; quote basis and option return/MFE/MAE remain
null. This ledger has no rank, gate, size, issue, publish-pick, trade, brokerage,
Neural Web, Prophet, or model-training consumer.

This slice does not create campaign aggregation, an options selector, contract
optimization, lifecycle management, Issue Desk changes, U-CHAIN changes,
focused quote changes, Terminal UI, or Macro scoring. In particular,
`~buy/~sell`, `repeated`, `swept`, and volume over prior OI are not opening or
closing identity and cannot be promoted into a campaign thesis.

## Durability and release gate

The existing sole builder validates all retained raw-stage prefixes, appends
episodes, appends unchanged H+60 v1 rows, appends session rows, then advances the
unchanged checkpoint last. A failure in the new ledger cannot bless an
unconsumed prefix; retry is byte-idempotent and drift-rejecting.

Code merge is evidence scaffolding, not proof of live accrual or alpha. Do not
start canonical campaign/model work until an RTH stage-before-index publication
and a later nightly have produced nonempty, causally ordered episode/H+60
receipts. Session horizons then accrue only as their own target clocks mature.
