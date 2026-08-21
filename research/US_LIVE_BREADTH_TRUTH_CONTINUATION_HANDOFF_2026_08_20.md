# US live-breadth truth boundary — continuation handoff (2026-08-20)

**Wave:** repair the US Stock Dashboard live-breadth scoreboard's truth boundary
and its production ownership. **PR:** #6084 (`claude/us-live-breadth-truth-repair`).
**Base at branch:** `origin/main` `c54d1b55f673` → rebased onto `36da0a3c7d8e`.

**State: MERGED + PRODUCTION-PROVEN LIVE.** #6084 merged as `d972484c6474`
(2026-08-20 17:11Z) and the proof WAS taken during a live RTH session — see §5b.
The canonical lane self-installed on the VPS and is producing `usable:true`
payloads; the truth boundary was verified in both directions on real production
bytes. Follow-up #6107 fixes a delay-stamp honesty defect that the live proof
itself surfaced. ONE item remains and it needs a VPS shell: a pre-existing
non-repo-managed writer still shares the artifact path, so `producer` flaps —
see §5c. The failure direction is safe by construction (§4).

---

## 1. Defects — proven vs disproven

All four browser/producer defects were reproduced **before** any fix, with the real
repro output quoted in PR #6084. One handoff hypothesis was **disproven**.

| # | Defect | Verdict | Proof |
|---|---|---|---|
| 1 | Fail-soft empty payload treated as live data | **PROVEN** | `empty_payload` comp `{n:0,adv:0,dec:0}` satisfies `typeof comp.adv === "number"` → writes `sbx-adv=0`, adds `live` class. A valid 848/651 board became 0/0. |
| 2 | Browser freshness uses BUILD clock, not SOURCE clock | **PROVEN** | `build_breadth` with a 2h-old `snapshot_ts`: `asof` = NOW, `delay_min` = 135 (honest), no source clock emitted → browser age 0.0 min → ACCEPTED. |
| 3 | Full-day NYSE holidays classified as live sessions | **PROVEN** | Good Friday 2026-04-03 / Thanksgiving 2026-11-26 / observed 2026-07-03 at 10:00 ET all returned `session_tag=rth`, `within_rth=True` while `nyse_calendar.is_session=False`. |
| 4 | Requested publication failure returns success | **PROVEN** | `--once --publish` into a non-repo: `git add failed`, `publication failed: True`, **exit code 0**. |
| 5 | No canonical production owner | **PROVEN, with a correction** | `live-setup.sh` arms 5 lanes, none breadth; `VPS_LIVE_PRIMARY=true`; every scheduled `live-breadth` run for 2 days concluded `skipped`. |
| 5b | "Producer is dark / external file may be absent" | **DISPROVEN** | Production **is** serving fresh breadth — see §2. A VPS-side writer exists. |
| 6 | Health plane cannot see breadth | **PROVEN** | `/api/status` `checks` had no `breadth` key; `check_vps_live_health.py` had no breadth gate. |

Additionally found **during** the fix, not in the original brief:

- **Fail-open NaN hole (fixed).** The new gate's `buildAge > SLA` / `srcAge > SLA`
  comparisons are `false` when the stamp is unparseable (`new Date("x")` → `NaN`),
  so a malformed payload would have **passed** a gate whose entire job is to fail
  closed. Both clocks now use `isFinite`. Mutation-tested: removing `isFinite`
  reddens `tests/test_live_breadth_js_contract.py`.
- **`--publish` on the VPS unit would have failed every tick (fixed before merge).**
  See `DSC:LIVE-BREADTH-VPS-LANE-MUST-NOT-GIT-PUBLISH`.
- **Wiring only into `live-setup.sh` is a silent production no-op (fixed).**
  See `DSC:LIVE-BREADTH-NEW-LANE-INSTALLS-VIA-UPDATE-SH-ABSENT-FILE-CLAUSE`.
- **A dead producer read as healthy (fixed).** `source_age_min` is frozen at
  BUILD time, so a lane that stopped writing three hours ago keeps serving an
  artifact that still says `source_age_min: 4.0` and `usable: true` — grading
  that field would have declared a stopped producer healthy forever, which is
  precisely the blindness a dead-man exists to prevent. `check_vps_live_health.py`
  now derives source age from the **absolute** `source_asof` against *now*
  (`_source_age_min()`), so the value keeps ageing after the writer dies and one
  check answers both "is the source stale?" and "did the producer run?" without
  touching mtime. Mutation-tested: grading the frozen field reddens
  `test_breadth_health_catches_a_producer_that_stopped_writing`.

## 2. Actual production breadth ownership (as observed 2026-08-20 ~10:56Z)

```
GET https://www.mastermind-x.com/live/breadth.json
  HTTP 200 · cache-control: no-store · last-modified: Wed, 19 Aug 2026 20:07:13 GMT
  asof 2026-08-19T20:07:13Z · session "post" · comp n=1503 adv=854 dec=649
  meta.snapshot_names 12740 · missing {large:2, small:1}
```

`no-store` is the decisive detail: that is Caddy's `@vps_public_live` branch, i.e.
`/var/lib/macro-live/public/live/breadth.json`, **not** the static fallback. So a
VPS-side process writes it. Meanwhile:

- committed `site/live/breadth.json` = `asof 2026-07-27T21:19:20Z`, and the last
  `live: breadth poll` commit is `5fc77aa` (2026-07-27) — the **git backstop
  artifact has not advanced in over three weeks**;
- `VPS_LIVE_PRIMARY=true`, so the GH backstop is `skipped` on every schedule;
- nothing in `scripts/`, `engine/`, `app/`, `.github/` wrote that path — the
  shipped poller **could not**, because `config.site_dir()` (`lib/config.py:39`) is
  repo-relative and not env-overridable.

**Open question this session could not close:** the identity of that pre-existing
VPS writer. It is not repo-managed. Its 20:07:13Z stamp (~16:07 ET, just past the
`--rth-only` 16:05 ET self-exit) is consistent with a hand-installed
`live_breadth_poller` loop. **This matters for the next session**: after #6084, the
canonical `macro-live-breadth.timer` writes that same path, so if the legacy writer
is still running there are momentarily TWO writers. The new `producer` field makes
this observable — a `producer` that flaps between `vps:macro-live-breadth` and
anything else (or `host:<hostname>`) is the signature. Resolve by inspecting the box
(`systemctl list-units 'macro-live*'`, `crontab -l`, `launchctl list`) and retiring
whatever is not `macro-live-breadth`.

## 3. What changed (15 files)

**Contract** (`engine/live_breadth.py`): additive keys `built_at`, `source_asof`,
`source_age_min`, `feed_status`, `usable`, `unusable_reason`, `coverage`,
`producer`. `schema` stays `"live.breadth.v1"` (shape unchanged; pinned by
`tests/test_market_packet.py`). One pure adjudicator `evaluate_usable()` with 7
ordered checks → `(bool, reason)`. Quality floor: coverage ≥ 90% of an expected
1500 **and** all 3 tiers present (healthy live n=1503 with a handful missing, so
the floor catches collapse, not noise).

**Producer** (`scripts/live_breadth_poller.py`): `session_tag`/`within_rth` consult
`lib.nyse_calendar.is_session` first; `source_asof`/`source_age_min` emitted from
the Polygon snapshot ts (**never** mtime); `_out_path` honours `MACRO_LIVE_DIR`
without double-appending `live`; `run_cycle` returns `CycleResult(payload,
published)`; `--once --publish` exits non-zero on failure with a bare line-start
`::error`; the long-running loop still survives a transient git error.

**Consumer** (`templates/live.js` + synced `site/live.js`): `applyBreadth` gates on
`usable === true`, comp shape, `session !== "closed"`, finite `source_age_min` ≤ 25,
finite build age ≤ 25 — each returning early with **zero** DOM writes. The stamp is
now derived from `source_asof` / `source_age_min`, not the build clock.

**Ownership**: new `app/deploy/macro-live-breadth.service`/`.timer` (oneshot
`--once`, **no `--publish`**, `MACRO_LIVE_PRODUCER=vps:macro-live-breadth`, every
2 min 12..22 UTC Mon–Fri), wired into `live-setup.sh` **and** `update.sh`'s
self-arming block. `.github/workflows/live-breadth.yml` no longer swallows a failed
publish.

**Health**: `/api/status` gains a `breadth` check with semantic fields;
`check_vps_live_health.py` gains breadth gates — absent-key OK, closed session /
weekend demands no freshness, and the 14..20 UTC live window requires
`usable`, `source_age_min ≤ 25`, `coverage_pct ≥ 90`, non-empty `producer`.

## 4. Tests added

- `tests/test_live_breadth.py` — 46 tests (was ~30): `evaluate_usable` truth table,
  the 4 calendar cases, source-clock emission, stale-source rejection, never-usable
  empties, `MACRO_LIVE_DIR` path, 3 publication-truth tests. **Existing EDT/EST DST
  tests still green.**
- `tests/test_live_breadth_js_contract.py` **(new; pytest-wired; executes real
  node)** — extracts `applyBreadth` from `templates/live.js`, runs it against a DOM
  seeded with the baked **848 / 651**, 10 cases A–J. Every "no mutation" case asserts
  **both** the counts and the absence of the `live` stamp class. Follows the
  `tests/test_wl1_board_state_surface.py` idiom: raises under `CI` if node is
  missing rather than skipping silently. (`tests/live_tape.test.mjs` is a
  pre-existing ORPHAN with no runner — do not imitate it.)
- `tests/test_vps_live_orchestration.py` — 14 breadth/ownership tests including
  `test_breadth_vps_lane_never_publishes_via_git` and
  `test_update_sh_self_arms_the_breadth_lane_on_a_running_box`.

Green at merge: 47 (`test_live_breadth` + JS contract), 14 (ownership), 172
(`test_market_packet`), `check_template_site_sync` 89 pairs OK.

**`tests/test_live_breadth.py` was GRANDFATHERED DARK — it had never run in CI.**
Caught by the `contract-delta` gate, which redded the PR for the *new* JS
contract suite being "named by no `run:` step". Investigating that surfaced the
bigger fact: `tests/test_live_breadth.py` sat in `config/unrun_test_baseline.json`'s
893-row shrink-only grandfather list, so **every** live-breadth test — the
pre-existing ones and the ones this wave added — would have been dark in CI.
Both suites are now wired into the `.github/ci/legacy-jobs.yml` job that already
owns `tests/test_vps_live_orchestration.py` (same subject family), and the row
was removed from the grandfather list (893 → 892; shrinking is the allowed
direction). `ci-pack` provides node 20 via `actions/setup-node@v4`, so the JS
contract test genuinely executes there rather than raising.

**Pre-existing, unrelated, NOT caused by this wave:** 3 failures in
`tests/test_vps_live_orchestration.py` (`test_bea_known_feed_bound_state_repairs_only_from_successful_detail_page`,
`test_aged_governed_pce_defect_forces_feed_and_detail_repair`,
`test_aged_governed_pce_defect_failure_is_quarantined_and_bounded`). They live in
`watch_release_publications.py`'s BEA/FOMC source-sha repair logic and fetch real
federalreserve.gov URLs; nothing in this PR touches that module.

## 5. Before / after payload clocks

| | before | after |
|---|---|---|
| build clock | `asof` only (= now) | `asof` + explicit `built_at` |
| source clock | **absent** — only folded into `delay_min` | `source_asof` + `source_age_min`, first-class |
| eligibility | `now - asof ≤ 25min` and `session != closed` | `usable === true` **and** finite `source_age_min ≤ 25` **and** finite build age ≤ 25 **and** `session != closed` |
| holiday | `rth` by clock | `closed` via `nyse_calendar` |
| stamp | `delay_min` + `asof` time | `round(source_age_min)` + `source_asof` time |

## 5b. PRODUCTION PROOF — TAKEN 2026-08-20 during a live RTH session

#6084 merged as `d972484c6474` at 17:11Z (13:11 ET), i.e. mid-session, so the
live proof this doc originally deferred was taken after all.

**Canonical lane self-installed.** Within ~8 minutes of the merge the VPS pull
ran `update.sh`, whose self-arming block installed and enabled
`macro-live-breadth.timer`. First canonical write observed at 17:19:08Z:

```
built_at        2026-08-20T17:27:07Z   source_asof   2026-08-20T17:27:06Z
source_age_min  0.0                    delay_min     15
session         rth                    feed_status   ok
usable          True                   unusable_reason  None
producer        vps:macro-live-breadth
coverage        {'n': 1503, 'expected': 1500, 'pct': 100.2}     tiers 3
comp            553 adv / 950 dec / n=1503
```

**Truth boundary verified on real production bytes, both directions**, by
evaluating the shipped gate logic in the production page's own context against
live payloads fetched from the production URL:

- legacy payload (no `usable`, no source clock) → `REJECT: usable!=true; no
  source clock`. Board showed baked **848 / 651**, stamp `last close ·
  2026-08-19`, no `live` class.
- canonical payload → `ACCEPT`, adv 551 / dec 952 / n 1503, and the stamp text
  the gate would emit was checked directly (see the #6107 defect below).

The served asset is the new build: `live.js?v=b9357424` contains
`SBX_MAX_SOURCE_AGE_MIN`, `b.usable !== true` and `isFinite(buildAge)`, and no
longer contains the old `age > 25 || b.session` gate.

**PRECISELY WHAT THE BROWSER EVIDENCE DOES AND DOES NOT PROVE — read this before
claiming the live upgrade was seen end to end.** The board was never observed
*visibly flipping* to live counts, and the reason is the HARNESS, not the
product: `templates/live.js:331` guards its poll with
`if (_paused || document.hidden || inflight) return;`, and the automated browser
pane reports `document.hidden === true` / `visibilityState "hidden"` even after
a screenshot fronts it. Measured: `performance.getEntriesByType('resource')`
filtered to breadth/quotes returned `[]` — the page made **zero** live requests,
not even for `quotes.json`, so `applyBreadth` was never invoked on any load.
That guard is pre-existing and correct (do not poll a hidden tab) and is
untouched by this wave. Reloading at the very start of a canonical window
(payload age 0 s, 527/976) still produced a baked board for exactly this reason.

So the chain is proven in two verified links rather than one screenshot:
1. **Real production payload + real gate semantics → ACCEPT**, with the correct
   stamp string, evaluated inside the production page (above).
2. **Real `applyBreadth` → DOM mutates to the payload's values**, proven by
   `tests/test_live_breadth_js_contract.py`, which extracts the function from the
   shipped `templates/live.js` and executes it under node (case C).

What remains unproven by direct observation is only the middle link — that the
page's own visibility-gated tick calls `applyBreadth` — which no line of this
wave modified. A human opening the page in a real, focused tab during RTH closes
that gap in seconds; it could not be closed from an automated hidden pane.

**Health plane verified**, three consecutive runs of
`scripts/check_vps_live_health.py --url https://www.mastermind-x.com/api/status`:
`healthy` → `UNHEALTHY: breadth: not usable during the live window / missing or
invalid source_asof / missing or invalid coverage_pct / missing producer
(unowned)` → `healthy`. The dead-man now sees breadth at all, which it could not
before this wave.

**Defect found BY that proof and fixed in #6107:** the canonical payload carries
`source_age_min 0.0` with `delay_min 15`, because Polygon STANDARD stamps a
CURRENT `quote_ts` on 15-minute-delayed prices. #6084's stamp rendered
`round(source_age_min)`, so it would have printed **"≈0-min delayed"** over
quarter-hour-old prices. #6107 stamps `max(delay_min, round(source_age_min))`;
gating still keys off `source_age_min` (unchanged). Contract case K pins it.

## 5c. THE ONE REMAINING PRODUCTION ITEM — an operator act

**`producer` is flapping, which is the two-writer signature.** Sampled every
~75s at 17:17–17:26Z:

```
17:17:05Z producer=None                    usable=None
17:19:08Z producer=vps:macro-live-breadth  usable=True
17:20:16Z producer=None                    usable=None
17:23:11Z producer=vps:macro-live-breadth  usable=True
17:23:24Z producer=None                    usable=None
17:25:24Z producer=vps:macro-live-breadth  usable=True
```

The pre-existing, non-repo-managed VPS writer of §2 is **still running** and
overwrites the canonical lane's artifact within seconds. Consequence today: the
scoreboard alternates between the live read and the baked nightly board. Both
states are TRUTHFUL — the fallback is valid nightly data and the gate is doing
its job — so this is not a user-facing correctness bug, but it is not the end
state and the live enhancement is only intermittently visible.

**This is the last step and it needs a VPS shell, which this session does not
have.** On the box:

```bash
systemctl list-units --all 'macro-live*' 'live-breadth*'
systemctl list-timers --all | grep -i breadth
crontab -l | grep -i breadth
launchctl list 2>/dev/null | grep -i breadth
journalctl -u macro-live-breadth.service -n 30 --no-pager
```

Retire whatever writes `/var/lib/macro-live/public/live/breadth.json` that is
**not** `macro-live-breadth.service`, then confirm `producer` stays pinned at
`vps:macro-live-breadth` across >=10 consecutive samples and
`check_vps_live_health.py` stays healthy across the same window. Do not disable
`macro-live-breadth.timer` to "stop the flapping" — that is the canonical owner.

**Measured flap period (2026-08-20, 6 s sampling):** the canonical payload holds
for about 70 s per cycle, then the legacy writer takes the path back:

```
19:06:26Z .. 19:07:02Z  legacy  asof=19:05:58Z
19:07:09Z .. 19:08:20Z  CANON   asof=19:07:08Z   producer=vps:macro-live-breadth
19:08:28Z ..            legacy  asof=19:07:36Z
```

While in the legacy half the artifact carries no `usable`, so the surface
correctly falls back to the nightly board — the read is never WRONG, only
intermittently non-live. Second visible symptom of the same cause: the second
line of `check_vps_live_health.py` output alternates, which is the dead-man
reporting the contention rather than a fault in either writer.

## 6. Original open item (now CLOSED by §5b, except §5c)

**Production RTH proof is owed.** It could not be taken here: this session has no
VPS shell, and at the time of the work the US market was **pre-market (~07:00 ET)**,
so no live RTH snapshot existed to verify an upgrade against. Green CI is not
production proof and is not claimed as such.

During the **next real NYSE session**, in order:

1. `curl -sS -D- https://www.mastermind-x.com/live/breadth.json` — record
   `cache-control` (expect `no-store`), `usable`, `feed_status`, `source_asof`,
   `source_age_min`, `coverage`, `producer`, `comp.adv/dec`.
   **Expect `producer: vps:macro-live-breadth`.** Anything else means the legacy
   writer of §2 is still primary — resolve that before proceeding.
2. `systemctl list-timers macro-live-breadth.timer` and
   `journalctl -u macro-live-breadth.service -n 30` on the box; confirm exactly ONE
   breadth writer exists (retire any hand-installed poller / cron / launchd job).
3. Open production `us_stocks.html` at **1440px** and **390px**; confirm the baked
   board upgrades to the same counts the JSON carries, the delayed stamp is truthful
   against `source_asof`, and the console is clean. Check EN+ZH and light+dark for
   the patched fields only.
4. `curl .../api/status` → `checks.breadth` present and semantically healthy; run
   `python scripts/check_vps_live_health.py`.
5. Degradation proof **without poisoning the public artifact**: point a local
   fixture / test endpoint at an unusable payload and confirm the nightly board
   survives untouched. Do NOT write a degraded payload to production.

**Do not** absorb the Intraday Flow / OPEX / Theta continuation (PR #6070) into this
lane — `templates/intraday_flow.html.j2`, `engine/opex.py` and options flow are
untouched here and stay that way.

## 7. Records minted

- `DSC:LIVE-BREADTH-VPS-LANE-MUST-NOT-GIT-PUBLISH`
- `DSC:LIVE-BREADTH-NEW-LANE-INSTALLS-VIA-UPDATE-SH-ABSENT-FILE-CLAUSE`
- `DSC:LIVE-BREADTH-EARLY-CLOSE-STILL-UNMODELLED` — the early-close risk the brief
  asked to record separately rather than absorb. `lib/nyse_calendar.py:11` states
  outright that early closes are not modelled, so there is no canonical helper to
  reuse and it was correctly left out of scope. Residual exposure is bounded: after
  a 13:00 ET close the vendor snapshot stops advancing, so `source_age_min` crosses
  the 25-min SLA within ~half an hour and the surface self-heals to the baked board.

## 8. Danger areas / do-not-redo

- **Never `git checkout`/`git status` this worktree while the machine is under a git
  storm.** An interrupted `git checkout -- site/live/breadth.json` truncated that
  tracked artifact to 0 bytes mid-session (load average was 161 with 237 git
  processes wedged in uninterruptible disk wait, spawned by Cursor's extension host
  on the `macro-main` workspace; the data volume is at 93%). Recovered by fetching
  the blob over the **GitHub contents API** instead of the local object store.
- **`repro.py`-style `--publish` runs write the real `site/live/breadth.json`.**
  Running the poller from the repo root with `--publish` and no `MACRO_LIVE_DIR`
  clobbers the committed fallback artifact. It was restored; verify
  `git status -- site` before every commit.
- Do NOT bump `schema` off `"live.breadth.v1"` — `tests/test_market_packet.py` and
  `tests/test_live_breadth.py` pin it, and the new keys are additive by design.
- Do NOT relax `usable === true` back to a shape check. A legacy v1 payload lacking
  `usable` **must** be rejected; that is the fail-closed default that protects the
  board during any rollback window.
