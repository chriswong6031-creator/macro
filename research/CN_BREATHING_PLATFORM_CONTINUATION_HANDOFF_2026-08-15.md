# CN Breathing Platform — continuation handoff (2026-08-15, session 1 close)

**Program:** CN-W-L3 / China Breathing Platform (chairman directive 2026-08-15;
sister session to Breathing Platform Production Revival US, which ran concurrently).
**Ruling (MERGED, #5744):** `research/CN_BREATHING_PLATFORM_ARCHITECTURE_2026-08-15.md`
— the build spec every lane is pinned to. Read it FIRST; this doc is only the state.

**Why this session stopped:** at ~16:45 PDT all three build agents died on the
account session limit (`resets 5:10am America/Vancouver`). Build capacity returns
then. Everything they wrote survives in this worktree:
`.claude/worktrees/china-breathing-platform-revival-1a334e` (branch
`worktree-china-breathing-platform-revival-1a334e`, tracks origin/main).
A scheduled resume session is filed for shortly after the reset.

---

## §0 ADDENDUM (session 1, ~17:3x PDT — read before §1)

**CN-PR-0 SHIPPED FROM THE MAIN LOOP during the outage** (PR #5759, branch
`claude/cn-pr0-calendar-threading`, armed merge-on-green): the reviewed-clean
subset — `armed_pack.py` calendar threading, `lib/cn_calendar.sessions_behind`,
and `engine/prophet_live/cn_clock.py` with TWO fixes beyond this doc's §1 rows:
the 301/689/302 limit prefixes (the builder had already applied it — verified)
AND a delay-aware `quote_age_min(..., delay_floor_min=)` anchor (bare wall-clock
age darked the board for the first delay-floor minutes of every afternoon/open;
the evaluator MUST pass the feed's declared delay, 15.0, when calling it).
Proof: tests/test_cn_live_clock.py 40 passed + the US suite 461 passed unmodified.

Consequences for §1/§3: those three files' rows are DONE once #5759 merges —
when resuming, rebase everything onto fresh origin/main and take MAIN's copies
(this WIP branch's cn_clock.py is superseded by the PR-0 version). cn_states /
cn_pack / the evaluator must consume `quote_age_min`'s `delay_floor_min` param.

---

## §1 Tree state at close (14 dirty paths, `git status` verbatim)

| Path | Lane | State |
|---|---|---|
| `engine/prophet_live/armed_pack.py` (M) | PR-1 | **REVIEWED CLEAN by main session**: additive `calendar=None` threading; NYSE branch byte-identical at every site; generic branch uses only `is_session`; `_NEXT_SESSION_HORIZON_DAYS=21`. US tests are the final arbiter — run them. |
| `lib/cn_calendar.py` (M) | PR-1 | **REVIEWED CLEAN**: additive `sessions_behind(latest, now)`; also exports `CST` (cn_clock imports it). NOTE its `sessions_between` returns a COUNT (NYSE returns a list) — the new docstring pins this; keep a test. |
| `engine/prophet_live/cn_clock.py` (??) | PR-1 | **REVIEWED, ONE FIX PENDING**: excellent module; but `limit_pct_for` misses ChiNext `301*.SZ` and STAR `689*.SS` (both ±20%). Fix was messaged to the builder AFTER it may have died — VERIFY the prefixes read `("688","689")`/`("300","301")` before ship, and add the 301-at-+10%-not-locked test. |
| `engine/prophet_live/cn_pack.py` (??) | PR-1 | Written, NOT yet reviewed. |
| `engine/prophet_live/cn_states.py` (??) | PR-1 | Written, NOT yet reviewed. |
| `scripts/build_cn_live_pack.py` (??) | PR-1 | Written, NOT yet reviewed. |
| `scripts/build_china_library.py` (M) | PR-1 | Builder edit (sanctioned): likely factoring the tradability predicate / price-adjustment helper additively — REVIEW the diff; nightly behavior must be unchanged. |
| **MISSING** `scripts/cn_live_evaluator.py` | PR-1 | The builder died "continuing with the drivers" — the evaluator + close pass DOES NOT EXIST yet. |
| **MISSING** `app/deploy/macro-live-cnprophet.{service,timer}`, `update.sh` block, `check_vps_live_health.py` clause, `.github/workflows/cn-prophet-live.yml` | PR-1 | Not started (live-breadth lesson: these MUST ship in the same PR as the evaluator). |
| **MISSING** all PR-1 tests | PR-1 | None written. |
| `templates/china.html.j2` (M) | PR-3 | Designer edit (script include + strip anchor in mode=='stocks'), NOT yet reviewed. |
| `templates/cn_prophet_live.js` + `site/cn_prophet_live.js` (??) | PR-3 | Written as a byte pair; NOT yet reviewed; sync-check not yet run by main session. |
| `mockups/refs/breathing-platform/cn_wl3_shots/` (??) | PR-3 | Designer died mid "shoot script that serves a scratch root, fakes the mainland clock, captures the crops" — crops likely INCOMPLETE; fixtures may exist. |
| **MISSING** `tests/test_cn_live_surface.py` | PR-3 | Not written. |
| `scripts/freshness_sentinel.py` (M) | PR-4 | Builder died MID-RENAME with a real finding: **the surface id `cn_prophet_live` trips an existing guard** (a US-program assert that no surface id contains the substring `prophet_live`). Their last word: rename the id, keep the artifact path `/live/cn_prophet_live.json`. Check what the diff currently holds — it may be half-renamed. |
| `scripts/cn_live_rescue.py` (??) | PR-4 | Written, NOT yet reviewed. |
| **MISSING** `tests/test_cn_live_watchdog.py` | PR-4 | Not written. |
| `research/CN_BREATHING_PLATFORM_ARCHITECTURE_2026-08-15.md` (??) | docs | MERGED to main as #5744 via a plumbing branch; the local untracked copy resolves on the next rebase onto origin/main. |
| this handoff (??) | docs | Ship with the program PRs or a docs PR. |

## §2 What the main session verified live today (do not re-derive)

- Production live plane alive + gating exactly per census: `/live/quotes.json` 200
  (public), `/live/china_risk_state.json` 401 (gated), **`/live/cn_prophet_live.json`
  already 401** (gated-by-default before it exists), `/china_stocks.html` 200 (open
  shell). `VPS_LIVE_PRIMARY=true` (backstop workflows self-disable).
- asia-close measured off `data/ops/nightly_timings/asia.jsonl` 08-10..08-14:
  start 08:25 UTC floor, 76–88 min total ⇒ CN board ~17:45–17:55 CST today. The
  ruling's before/after numbers are current.
- Four census reports (US prophet-live core, CN engine chain, live plane,
  sentinel/rescue + CN-LIMIT-ALPHA boundaries) are summarized in the merged ruling;
  the raw reports live only in session-1's transcript — the ruling carries
  everything load-bearing.

## §3 Resume plan (in order)

1. **Wait out the limit** (5:10am America/Vancouver reset; scheduled session filed).
2. Re-commission three builders (fresh agents; the tree + ruling carry the state —
   point each at §1's lane rows and the ruling's §-references; spawn-handoff law:
   gates INLINE): PR-1 finish (evaluator + close pass + deploy units + backstop +
   tests + the cn_clock prefix fix + review of cn_pack/cn_states), PR-3 finish
   (crops + surface test + sync check), PR-4 finish (complete the id rename —
   suggested `cn_board_live` — + tests).
3. Main-session review of every unreviewed file (cn_pack, cn_states, evaluator,
   build_china_library diff, client JS, sentinel diff, rescue script).
4. Adversarial reviewer (opus) pass on state-machine/close-observability/basis
   correctness before ship.
5. Ship serially per ruling §10: PR-1 → PR-3 → PR-4 (disjoint file sets; branch
   each off fresh origin/main via plumbing or clean-tree checkouts; arm
   merge-on-green; own to merge; NO stacked PRs — zero CI on non-main bases).
6. Commission CN-PR-2 (asia-close arming step + `reconcile_cn_live --asia` +
   confirmation receipt + evaluator settle-absorb phase + timer window extension
   to ~11:00 UTC — ruling §8; the receipt-in-hand law #5220).
7. Acceptance: replay battery green in CI; browser proof (static N−1 vs runtime N,
   desktop/390px/EN/ZH); then arm the 3-consecutive-live-session accrual
   (next mainland session: Mon 2026-08-17, first evaluator tick ~01:15 UTC).
8. Return packet per commission §19 + memory updates + this handoff superseded.

## §4 Standing cautions for the next session

- US sister session (`breathing-platform-revival-fc7825`) may resume too — keep
  shared-file diffs additive (`armed_pack.py`, `freshness_sentinel.py`,
  `update.sh`, `check_vps_live_health.py`), rebase fresh before every push.
- CN-LIMIT-ALPHA isolation is a hard gate (ruling §0-7/§11): no imports from
  `research/cn_prophet_audit/`, no China-Intelligence composites, no touching the
  5 collectors PR #5730 owns (`_first_seen_store`, `china_block_trades`,
  `china_buyback`, `tushare_broker`, `tushare_margin`) or the two agentos
  CN-LIMIT-ALPHA records both #5729/#5730 edit.
- The sentinel was touched TODAY by the commercial-alerts program — additive only.
- `evening asia-close runs EVERY day` incl. weekends (gate + floor) — a merged
  template edit is rendered by the next day's bake; no manual render needed.
- Do NOT run the full pytest suite in a sparse tree; this worktree is FULL
  (`worktree_sparse.py status` says so) — keep it that way for the replay battery.
