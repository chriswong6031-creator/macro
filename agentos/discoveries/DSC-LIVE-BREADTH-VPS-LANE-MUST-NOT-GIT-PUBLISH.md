---
key: LIVE-BREADTH-VPS-LANE-MUST-NOT-GIT-PUBLISH
claim: >
  The live-breadth producer has TWO publication mechanisms that must never be
  combined in one process, and the split is what keeps exactly one writer claiming
  primary ownership of site/live/breadth.json. The VPS lane
  (app/deploy/macro-live-breadth.service) publishes by ATOMIC RENAME into
  $MACRO_LIVE_DIR = /var/lib/macro-live/public/live, which app/deploy/Caddyfile's
  @vps_public_live matcher serves FIRST with `Cache-Control: no-store` — the artifact
  is live the instant it lands and no git is involved. The GitHub backstop
  (.github/workflows/live-breadth.yml) is the ONLY producer that may pass --publish:
  its job is to commit site/live/breadth.json to main so the STATIC fallback copy
  (served `public, max-age=60` from /opt/macro/site.served) advances on a box where
  the VPS lane is down. Adding --publish to the VPS unit is not merely redundant, it
  hard-fails the unit on every tick: with MACRO_LIVE_DIR set, the output path is
  OUTSIDE the /opt/macro git work tree, so `git add -f <abs path>` returns
  "fatal: ... is outside repository", publish() returns False, and (since PR #6084
  made requested-publication failure honest) `--once --publish` correctly exits
  non-zero. Verified by direct run against a temp MACRO_LIVE_DIR: exit 1, artifact
  written, "is outside repository" in stderr. Corollary for diagnosis: the
  `cache-control` response header is how you tell WHICH path served a /live/*.json —
  `no-store` means the external /var/lib/macro-live/public copy, `max-age=60` means
  the static git-committed fallback. On 2026-08-20 production returned `no-store`
  with asof 2026-08-19T20:07:13Z while the committed artifact was still 2026-07-27,
  which is how the VPS-side writer was proven to exist before any shell access.
falsifier: >
  Making config.site_dir() env-overridable to point inside the work tree, moving
  MACRO_LIVE_DIR under /opt/macro, or changing Caddy's @vps_public_live matcher so
  the static copy wins. Any of these would let one process legitimately do both, and
  would invalidate the "never --publish on the VPS lane" rule. Pinned by
  tests/test_vps_live_orchestration.py::test_breadth_vps_lane_never_publishes_via_git.
so_what: >
  When adding or repairing ANY VPS live lane, decide which of the two planes it
  publishes to and pass flags accordingly — do not copy --publish from the backstop
  workflow into a systemd unit because "that is how the runbook showed it". The old
  docs/live_breadth_runbook.md did exactly that (a launchd plist carrying
  `--rth-only --publish`) and following it would have armed a second writer racing
  the systemd lane for the same artifact. Also: when a live artifact looks fresh in
  production but stale in git, read the cache-control header before theorising —
  it names the serving path in one request, with no VPS shell required.
kind: landmine
verified_at: 2026-08-20
verified_by: >
  Direct run of `python -m scripts.live_breadth_poller --once --offline --publish`
  with MACRO_LIVE_DIR pointed at a temp dir outside the work tree: exit 1, stderr
  `git add failed: fatal: ... is outside repository`, artifact still written. Plus
  `curl -sS -D- https://www.mastermind-x.com/live/breadth.json` returning
  `cache-control: no-store` with asof 2026-08-19T20:07:13Z against a committed
  site/live/breadth.json of 2026-07-27T21:19:20Z.
scope: [macro, scripts/live_breadth_poller.py, app/deploy/macro-live-breadth.service, app/deploy/Caddyfile]
confidence: verified
metadata:
  type: discovery
---

Related: [[LIVE-BREADTH-NEW-LANE-INSTALLS-VIA-UPDATE-SH-ABSENT-FILE-CLAUSE]],
[[LIVE-BREADTH-EARLY-CLOSE-STILL-UNMODELLED]]
