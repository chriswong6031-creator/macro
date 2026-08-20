# US live-breadth truth boundary — continuation handoff (2026-08-20)

**Wave:** repair the US Stock Dashboard live-breadth scoreboard's truth boundary
and its production ownership. **PR:** #6084 (`claude/us-live-breadth-truth-repair`).
**Base at branch:** `origin/main` `c54d1b55f673` → rebased onto `36da0a3c7d8e`.

**State: CODE MERGED / PRODUCTION PROOF OWED.** The repair is complete and proven
in CI. The live RTH proof could not be taken in this session and is the single
open item — see §6. The failure direction is safe by construction (§4).

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

## 6. NEXT ACTION — the one open item

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
