# `us_basket_turn.v1` — US washout-lifecycle forward ledger

`ledger.jsonl` — one row per US basket per session carrying the washout-lifecycle
state (`FALLING` / `WASHED_OUT` / `BASING` / `TURNING` / `CONFIRMED` / `NONE`).
Producer: `engine/us_basket_turn.py`, stamped from `scripts/build_baskets.py` on
the nightly engine lane. Charter:
`research/PROPHET_US_EYES_OPEN_MASTERPLAN_BY_FABLE.md` §0 G0.6 / §3 W1-D.

Sibling ledgers, and how this one differs:

| ledger | organ | construction |
|---|---|---|
| `data/basket_turn/ledger.jsonl` | `engine/basket_turn_watch.py` | K-of-N confluence (6 legs) → WATCH / IGNITION / DOWNGRADE |
| `data/china_basket_turn/ledger.jsonl` | `engine/china_basket_turn.py` | CN washout lifecycle (this ledger's parent construction) |
| **`data/us_basket_turn/ledger.jsonl`** | **`engine/us_basket_turn.py`** | **US washout lifecycle — the port** |

They are three separate organs. Neither turn-watch nor this one feeds the other,
and no state in any of them ranks, gates, sizes, or escalates anything.

## The law on this page

**A state is a disclosure, not a call.** `TURNING` means the lifecycle machine
found washout depth plus one basing/velocity signal on that session. It does not
mean the basket bottomed. Replayed over the committed member tape,
`gold_miners` printed `TURNING` on 2026-06-16, 06-17, 07-02, 07-06, 07-09 and
07-10 — six sessions, in three episodes — and then made a LOWER low each time
before the 07-20 trough. The machine oscillates inside a washout by construction.
Any surface that renders these states must say so; any grading run must count
the oscillation, not just the last print.

*(Corrected 2026-08-07: this page shipped listing four of those six sessions.
06-17 and 07-06 were missing. Under-counting the oscillation is the one
direction this disclosure may never err in.)*

**This organ has no confirmed-state lead over the incumbent.** Replayed on
`gold_miners` (12/12 members, 2026-01-02..2026-08-06), it prints its first
post-trough `TURNING` on **2026-07-22** and its first `CONFIRMED` on
**2026-08-05** — the same session `engine/basket_turn_watch.py` printed
`IGNITION`. The earlier print is the oscillating one, and even the 07-22 run
lapsed on 07-30 without confirming. What this organ adds is a CONTINUOUS
lifecycle disclosure where the incumbent emits a single binary event; it does
not add earliness, and nothing rendered from this ledger may claim it does.

**The forward ledger starts at ship date (2026-08-07).** States shown for
earlier sessions come from `python -m engine.us_basket_turn --replay <basket>`,
which is descriptive evidence over committed data and writes nothing. Replayed
sessions are **not** prospective n and may not be graded as if they were.

**Coverage is part of the row, and it is counted at that row's own session.**
`members_read` / `members_total` ride on every row because this organ does its
own equal-weight aggregation from member closes (the CN parent reads a
pre-aggregated chart and never sees the hole). A basket read at a fraction of
its membership is not evidence about that basket — the `basket_turn` README's
W-B era-break is the precedent, and the same reading rule applies here from day
one rather than in hindsight.

`members_read` counts members carrying a **bar on the row's `date`**.
`members_with_store` (also on the row) counts members that merely own a store
file. The two differ exactly when part of a basket's tape has gone dark, which
is the case worth seeing. *(Amended 2026-08-07: v1 counted store files only, so
a basket whose whole tape was a week stale still read `3/3`.)*

**Every row's `date` is that basket's OWN last member bar.** Baskets in this
ledger do not share a date axis — each one is aggregated from its own member
parquets — so two rows written by the same nightly run routinely carry different
dates, and that is correct, not drift. Read `date` per row; never assume the
ledger's newest date describes every basket. The artifact
(`site/basketdata/us_basket_turn.json`) additionally carries a universe-wide
`as_of` / `data_session` header — that is a freshness display for the estate and
is **not** the stamp on any row.

## Row schema

| field | meaning |
|---|---|
| `date` / `as_of` | the **data-plane** session for THIS BASKET — the newest bar in its own equal-weight level series, never the wall clock and never the estate's newest bar (#4568 pattern). A basket whose tape did not advance re-derives the session it already logged, the keep-first dedupe refuses the row, and `days_in_state` does not move. A basket with no readable level series has no session and gets **no row**. |
| `basket_id` | US basket id from `data/baskets/membership.json` (`cn_` / `hk_` / `ca_` filtered out) |
| `state` | `FALLING` / `WASHED_OUT` / `BASING` / `TURNING` / `CONFIRMED` / `NONE` |
| `dd_252` | equal-weight level vs its rolling 252-session high (negative fraction) |
| `hist_d` | day-over-day change in the MACD histogram on the level series |
| `slope_20d` | 20-session OLS slope, normalised by mean level |
| `ret_5d` | 5-session equal-weight return |
| `evidence` | descriptive tags — no forward verbs, no buy vocabulary |
| `days_in_state` | consecutive sessions in the returned state (drives the CONFIRMED hysteresis). Counted only across **adjacent** sessions: if the basket's previous ledger row is not on its immediately preceding available session, the run-length resets to 1 rather than counting across the hole. |
| `members_read` / `members_total` | members with a bar ON `date`, over declared active members |
| `members_with_store` | members with a readable store file, regardless of whether it reaches `date` |

## Standing-law scope

`DNR:KILL-WASHOUT-TURN` killed the 2W operator-seed **scored entry trigger**
(#1747). This ledger is a display-tier lifecycle disclosure — the lawful form
the predecessor plan's G0.4 already reasoned through. Nothing here is an entry,
a buy claim, or an input to one, and `authority.may_rank/gate/size/escalate` are
all `false`.

`ledger_meta.json` carries the ship date, the advance gate, the quarantine slot
(empty at ship) and the era notes.
