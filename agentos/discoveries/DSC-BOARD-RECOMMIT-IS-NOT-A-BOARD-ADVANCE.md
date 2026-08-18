---
key: BOARD-RECOMMIT-IS-NOT-A-BOARD-ADVANCE
claim: >
  The render lane re-commits every `site/factordata/*_standouts.json` board on a
  `scope=all` pass whether or not its content moved, so a frozen market board carries a
  git mtime and a commit timestamp minutes old while its `as_of` stands still. Measured:
  `site/factordata/canada_standouts.json` held `as_of=2026-08-13` on every commit from
  2026-08-14 through 2026-08-18 (14+ commits, several of them same-day re-renders) while
  `us_standouts.json` advanced 08-13 -> 08-14 and `hk_standouts.json` /
  `china_standouts.json` sat at 08-14. Any instrument that grades a board by file age,
  commit recency, or "was the artifact written this run" is structurally blind to this.
falsifier: >
  A `scope=all` render that writes a board file only when its payload changed (so an
  unchanged board leaves no commit), or a measured window in which a board's commit
  timestamp and its `as_of` move together. Check with:
  `git log --format='%ad %h' --date=short -8 origin/main -- site/factordata/canada_standouts.json`
  against `git show <sha>:site/factordata/canada_standouts.json | jq -r .as_of` at each sha.
so_what: >
  Board freshness must be read from the CONTENT stamp graded against that market's own
  exchange calendar — never from mtime, commit age, or lane conclusion. It also means the
  five market boards fail INDEPENDENTLY: one green nightly writes all five, so four can
  advance while the fifth freezes, and no lane-level or single-artifact check can see it.
  `engine/neuralweb/prophet_governor._build_dashboard_integrity` grades these very
  artifacts by `_artifact_age_hours` (file mtime) and is blind to this class by
  construction; treat its per-market "ok" as evidence about the FILE, never the board.
kind: landmine
verified_at: 2026-08-17
verified_by: >
  origin/main @789e6e10, 14-commit walk of `as_of` across
  site/factordata/{us,china,hk,canada}_standouts.json (ca pinned at 2026-08-13 throughout,
  us advancing at 6f223ed0->e9f4a155); `git log` on canada_standouts.json showing
  re-render commits dated 2026-08-17 over that frozen payload;
  engine/neuralweb/prophet_governor.py:626-690 (`_artifact_age_hours` per-market check).
scope: [macro]
confidence: verified
---

## Detail

This is the gap `scripts/check_nightly_liveness.py` check D closes (PR #5852). Checks
A and B ask GitHub whether `daily.yml` produced and concluded a run; check C reads one
artifact, `site/prophet/index.json`, which is the US Prophet board. All five market
boards are baked by that same lane, so A and B genuinely cover "did the nightly run"
for every market — but the *per-market* dual-read existed for US alone, and the market
that froze was not the one anyone graded.

The second half of the discovery is that a shared anchor cannot fix it. HKEX closes
16:00 HKT and the mainland 15:00 CST, both hours BEFORE the 22:30 ET nightly fires, so
those boards routinely carry a session date the US board has not reached yet — measured
2026-08-04, `hk`/`cn` read `2026-08-04` while `us` read `2026-07-31`. Grading them
against `lib/nyse_calendar.expected_last_session` reads that healthy state as an anomaly
in one direction and papers over a real freeze in the other. Each board needs its own
calendar; `lib/tsx_calendar.py` was written for Canada in that PR, and
`lib/hk_calendar.sessions_behind()` added, because HK was the one market whose calendar
could not state a lag in sessions.

Related: [[PROPHET-ASOF-IS-WALL-CLOCK]] is the same failure family one artifact over —
there a publication clock masqueraded as a data watermark; here a commit clock does.
