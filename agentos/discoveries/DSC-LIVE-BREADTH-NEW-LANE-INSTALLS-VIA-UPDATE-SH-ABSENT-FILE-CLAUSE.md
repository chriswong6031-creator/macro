---
key: LIVE-BREADTH-NEW-LANE-INSTALLS-VIA-UPDATE-SH-ABSENT-FILE-CLAUSE
claim: >
  app/deploy/live-setup.sh does NOT install a new VPS live lane onto an
  already-provisioned box. It is a manual operator act (`sudo bash live-setup.sh`),
  nothing invokes it automatically, and app/deploy/update.sh — the script the VPS
  actually runs on its pull — installs live-plane units through SEPARATE per-lane
  blocks. The mechanism that makes go-live "a repo commit and nothing else" is the
  self-arming clause those blocks carry, e.g. for Prophet Live at
  app/deploy/update.sh:1484-1486:
  `if systemctl is-enabled macro-live-fast.timer && { CHANGED matches
  '^app/deploy/macro-live-prophet\.(service|timer)$' || [ ! -f
  /etc/systemd/system/macro-live-prophet.timer ]; }`.
  The `|| [ ! -f ... ]` half is load-bearing and is commented as such at line 1470:
  the unit did not exist when live-setup.sh was last run on the box, so a
  CHANGED-only trigger would install a timer that nobody ever enables. The
  `is-enabled macro-live-fast.timer` guard is what keeps the block inert on any host
  that is not the serving VPS. A lane wired ONLY into live-setup.sh is therefore
  dark in production until a human re-runs that script — which is exactly the state
  live breadth was in: five lanes armed, no breadth lane, and VPS_LIVE_PRIMARY=true
  disabling the only repo-managed producer that remained.
falsifier: >
  update.sh growing a generic loop that installs every app/deploy/macro-live-*.unit
  it finds (making per-lane blocks unnecessary), or a puller that runs live-setup.sh
  on each pull. Either would make wiring into live-setup.sh alone sufficient. Pinned
  by tests/test_vps_live_orchestration.py::test_update_sh_self_arms_the_breadth_lane_on_a_running_box.
so_what: >
  Wiring a new VPS live lane into live-setup.sh ONLY is a silent no-op in
  production, and it is the kind that reviews clean: the unit file exists, the setup
  script lists it, tests pass, and the lane never runs. Always add the matching
  update.sh block with BOTH the CHANGED regex and the absent-file clause, keep the
  regex narrow to the two paths that lane owns (a widened regex restarts unrelated
  sibling timers), and never `systemctl restart` a oneshot .service — that runs a
  pass out of band, off the windowed schedule, burning a vendor call outside the
  lane's entitlement. Only the timer is re-armed.
kind: landmine
verified_at: 2026-08-20
verified_by: >
  Read of app/deploy/update.sh:1463-1511 (the macro-live-prophet block and its
  line-1470 comment) and app/deploy/live-setup.sh:96-160; grep confirming nothing
  invokes live-setup.sh automatically. Cross-checked against the observed
  production state: VPS_LIVE_PRIMARY=true, live-setup.sh arming five lanes and no
  breadth lane, and every scheduled live-breadth workflow run concluding `skipped`.
scope: [macro, app/deploy/update.sh, app/deploy/live-setup.sh]
confidence: verified
metadata:
  type: discovery
---

Related: [[LIVE-BREADTH-VPS-LANE-MUST-NOT-GIT-PUBLISH]]
