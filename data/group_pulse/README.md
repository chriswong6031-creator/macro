# `group_pulse` — basket participation-episode ledger

`episodes.parquet` — one row per PARTICIPATION EPISODE per US basket: a stretch of
sessions during which the basket's members were moving together in unusual size.
Producer: `engine/group_pulse.py`, advanced from `scripts/build_baskets.py` on the
nightly engine lane only (`engine.ledger_lane.nightly_advance_enabled()` — house law:
nightly is the sole advancer of forward ledgers; an intraday lane computes and
discards). Program: Group Reads (GR0),
`research/GROUP_READS_MASTERPLAN_BY_FABLE.md`.

## Columns

| column | meaning |
|---|---|
| `basket_id` | the basket in `data/baskets/membership.json` |
| `episode_id` | `"<basket_id>:<start_date>"` — stable, derivable, never re-minted |
| `start_date` | first ACTIVE session of the episode |
| `end_date` | last ACTIVE session; `NA` only if a row is written mid-flight |
| `sessions_active` | ACTIVE sessions inside the episode |
| `sessions_span` | calendar-of-sessions length `start..end` inclusive (>= `sessions_active` when the episode bridged a gap) |
| `members_ever_active` | members active in >= 1 session of the episode |
| `members_persisted` | members active in EVERY active session |
| `persistence_share` | `members_persisted / members_ever_active` |
| `closed` | `True` once the episode ended; see immutability below |
| `advanced_at` | UTC stamp of the advance that WROTE this row |

## The machine

A basket-day is ACTIVE when `activity_share >= 0.50` and `activity_n >= 3`. Once an
episode is open the bar drops to `0.35` (hysteresis — one soft session does not chop
an episode in two). Active days at most 2 inactive sessions apart are ONE episode;
3 consecutive inactive sessions close it, and it closes AT ITS LAST ACTIVE SESSION,
so the trailing quiet days belong to no episode. Member ACTIVITY, and every
threshold, is defined in `engine/group_pulse.py`'s module docstring.

## Immutability, and why it is a rule rather than a coincidence

The open episode's row is PROVISIONAL and is recomputed on every advance. A row with
`closed=True` is **immutable**: `merge_episodes()` re-emits the stored row verbatim
and DISCARDS its freshly-computed twin. The stored row is never asked to agree with
the recompute, so a later data revision cannot silently rewrite a closed episode.
Pinned by `tests/test_group_pulse_episodes.py::test_closed_rows_are_immutable`.

The episode history IS re-derivable from the committed member tape
(`data/baskets/ohlcv/`) — the seed committed with GR0 is that derivation, and every
row before the ship date is DESCRIPTIVE REPLAY, never forward evidence.

## The web-readable projection

A page cannot read parquet, so the same run publishes
`site/basketdata/episodes.json`: `{basket_id: [<= 10 CLOSED episodes, newest first]}`,
each carrying `start_date`, `end_date`, `sessions_active`, `sessions_span`,
`members_ever_active`, `persistence_share`. That is the "has this happened before"
read; `site/basketdata/pulse.json`'s `episode` block carries only the CURRENT state.

The projection reads THIS ledger read-only and is written in any lane. The
PROVISIONAL open row is excluded — an episode still running is not history. A basket
with no closed episode keeps its key with an empty list, so the two artifacts join
1:1 by `basket_id`. The cap keeps the artifact a page payload; this parquet remains
the full record.

## The law on this page

**An episode is participation, not direction and not a call.** It says the group's
members moved in unusual size together for a stretch of sessions. It does not say
which way, it does not say the move continues, and nothing in this ledger — or in
`site/basketdata/pulse.json`, which it feeds — ranks, gates, sizes, or escalates
anything. There is no fused score in this plane by construction (program law
R-TIL-3, pinned by `tests/test_group_pulse_tripwire.py`).
