# Open-PR backlog — continuation handoff, 2026-08-08

## What this session was for

The operator asked to drain ~30 open PRs, some 2–3 days old. The backlog is **not** 33
independent problems. Main was red on **all four `ci-pack-*` jobs** — ~15 failing legacy
jobs — so every armed PR inherited the failure and `merge_on_green` correctly refused to
merge anything. The backlog grew to 35 while this ran.

The fleet had already opened one heal PR per red, which **deadlocks**: a pack is ONE
check, so with several independent reds in a pack each partial heal stays red from the
others and none can ever go green. #4962 was the clearest case — it healed `ci-pack-1`
outright and still sat red on 0/2/3.

## The heal: PR #4965 (`claude/main-heal-all-packs`)

One PR carrying every fix all four packs need. Siblings **merged, not rewritten**
(authorship preserved): #4962, #4963, #4949.

### Root causes fixed

| cause | fix |
|---|---|
| China news tape shipped a wire headline containing "validated" | #4963 structural third-party skip |
| spent ob_mask tripwire, collect-staging, marketing chart grep, path prune, us_board rank/w3, deploy self-heal | #4962 |
| gex session re-stamp **reverted a second time** by a nightly predating #4883 | `scripts/restore_polygon_gex_session_stamps.py` — restore from #4883's verified-clean tree, never re-derive (the remap is not idempotent) |
| exit-policy report stale vs renderer | re-render at the pinned vintage |
| exit-policy **calibration** drift | `xfail(strict=True)` — this is the ERA BREAK, see Owed below |
| `check_factor_boundaries` — #4822 shipped "allowlisted reader" without the allowlist entry | added `packet_producer.py` / `packet_reader.py` |
| 4 shipped-but-undeclared contract fields | declared, required vs optional decided per emitting site |
| `unrun-market-plumbing` structurally at-cap | `timeout-minutes` 6 → 15 |
| yahoo tape keyed UPPERCASE, read with `.lower()` | `lake.yahoo_key()` + a guard that sees it on macOS |
| 6 cboe tests dead every weekend | `trading_day` fixture + anti-vacuity pin |
| 3 tests writing the REAL `data/` tree | ohlc marker, prophet arena, demand Alert Center |

### Two failure classes worth carrying forward

**1. Local-green / CI-red on the same sha.** Two independent causes, both of which cost
me wrong verdicts:
- **Filesystem case** — `data/yahoo/XLK.parquet` is tracked, nothing is lowercase; a
  `.lower()` read resolves on macOS/APFS and returns `None` on `ubuntu-latest`. Silent by
  construction: a `None` read is indistinguishable from "no tape", so the whole
  us_sector/country cross-section went null.
- **The clock** — CI is UTC, this checkout is US/Pacific, so **every evening after 17:00
  PDT CI is already on the next calendar day**. Reproduce with `TZ=UTC python -m pytest`.

**2. `N passed` + exit 1, failure summary naming no test.** `MM_DATA_GUARD` forces exit 1
when a session dirties `data/`/`site/`. Hit three times. **Verify with the exit code and
`git status`, never the pytest summary line** — a run piped through `| tail` cannot see
either (I reported a step green twice this way before catching it).

The `unrun-market-plumbing` timeout is the compounding case: the cap was **masking** six
real weekend failures. Raising it made the job look worse before it got better.

## Status at handoff

- PR #4965: rounds 1–5. Round 4 = packs **0, 1, 3 green**, pack-2 red on
  `unrun-builders-stores` (fixed, pushed as round 5). Every pack has been green at least
  once.
- Main's last own `ci.yml` run is still red — it will heal on this merge.

## Next steps

1. **Land #4965**, then confirm a green `ci.yml` on main (`gh workflow run ci.yml --ref main`
   is the operator lever if the push run does not fire).
2. **Drain the armed backlog.** `merge_on_green`'s #4823 path fast-forwards a PR whose
   every failing check is green on main's tip — but it is capped at
   **`MAX_REFRESHES_PER_SWEEP = 8`**, and each refresh queues a fresh 36–91 min CI run.
   So the drain is several hours of wall-clock by design, not minutes. Force sweeps with
   `gh workflow run merge-on-green.yml`; do NOT reach for `--admin`.
3. **Rebase the conflicted PRs by hand.** Verified locally with
   `git merge-tree --write-tree origin/main <ref>` — these are REAL content conflicts, not
   stale-base reds, so no sweep will clear them:

   | PR | conflicts in |
   |---|---|
   | #4512 | `site/nav_market.js`, `site/rotation_events.js`, … |
   | #4622 | `collectors/breadth.py`, `config.yml`, `data/baskets/…` |
   | #4729 | `templates/_us_act_now_board.html.j2`, `tests/test_us_act_now.py` |
   | #4734 | `.github/ci/legacy-jobs.yml`, `.github/workflows/ci.yml` |
   | #4843 | `.github/workflows/ci.yml`, `docs/HOUSE_LAW_CI_GUARD_SUITE.md` |
   | #4865 | `tests/test_prophet_miss_audit.py` |

   #4735 test-merges CLEAN. Note #4512/#4765 are site-heavy — prefer REBUILD over rebase
   ([[site-heavy-branch-rebuild-beats-rebase]]).
4. **Close as superseded, with a pointer** (containment verified by empty
   `git diff HEAD <ref> -- <files>`): **#4934**, **#4953** — fully contained in #4965.
   **#4936** — superseded by a *better* fix: its version imports `engine.prophet_bridge`,
   which `ModuleNotFoundError`s on the minimal-deps `marketing-engine` lane, and
   `importorskip` would silently switch the guard off in the lane where marketing actually
   renders; #4965 reads the binding out of the AST instead. **#4744** — superseded by
   main's frozen-vintage approach; merging it would revert #4842's frozen-slice render to
   a live-cache one.

## OWED — operator decisions, not builder work

- **The US track-record ERA BREAK is due and unexecuted.** #4732's absolute session anchor
  reached `grade_us_board._ob_mask` — the incumbent episode's TARGET EXIT leg — so every
  published number moved. `site/factordata/us_track_ledger.json` is still the pre-era
  object (`as_of` 2026-07-31, `win_pct` 63.6, **no** `meta.anchor_era`).
  #4965 touches **no published number**; it marks the calibration guard
  `xfail(strict=True)` with the mechanism and measured deltas in the marker
  (`win_pct −4.6`, `expectancy_pct −0.89`, `profit_factor −0.54`, `capture −0.36`).
  **#4942 executes the break** and is the PR that must drop the marker — strict mode reds
  the day the deltas go to zero, so it cannot be forgotten. #4942 is currently CONFLICTING
  and red on all four packs.
- **`.gitignore:80` ignores `data/russell_breadth/_closes_cache.parquet`** while its
  high/low/volume siblings are tracked and every other breadth store ships its closes.
  Consequence: `ohlc-basis-coherence` checks **3 of 4** breadth panels in CI, and the
  committed marker records a russell panel a clean checkout cannot reproduce. #4965 fixed
  the WRITE (the test no longer dirties the tree) and deliberately left the coverage gap
  open — closing it means deciding whether that ~8 MB cache should be tracked.
- **Weekend exposure is not fully mapped.** 94 test files reference `date.today()` /
  `datetime.now()`. I swept the 11 session-gated ones under `TZ=UTC` (644 passed), so that
  family looks closed — but the other ~83 were not swept and any of them can be a
  scheduled weekend red.
