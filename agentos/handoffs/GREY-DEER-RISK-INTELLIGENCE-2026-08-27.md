---
workstream: "WS:GREY-DEER-RISK-INTELLIGENCE"
session: "worktree gd3-codex-handoff (Fable COO) — GD-3 acceptance handoff to a computer-access session"
model: fable
ended_because: blocked
prs: [6144, 6210]
mission: >
  Hand the ONE remaining GD-3 gate — the Gate-8-equivalent four-clock production
  receipt — to a session that has a real authenticated browser (Codex with
  computer access). Sol's standing law is unchanged: take the FIRST lawful real
  live-source change during an active US fast-lane window and preserve the actual
  four-clock chain; never manufacture, simulate, or hand-mutate the qualifying
  event; if no lawful change occurs in the available window, record
  WAITING_FOR_PRODUCTION_EVENT and stop. On PASS close GD-3 DONE, land the exact
  receipt in Agent OS, and stop. On FAIL repair ONLY the exact failing real path.
  GD-8A/8B/9A stay uncommissioned until GD-3 closes.
state_before: >
  GD-3 merged+deployed 2026-08-21 (PR #6144, 55d7ea02ce3e). GD-3R1 clock-truth
  repair merged 2026-08-22T05:16Z (PR #6210, e667ec39d176) after Sol found a
  §0b.5 violation in the shipped bytes (risk_state["built"] published as
  clocks.event_time; produced_at == observed_at). GD-4A.1 DONE (#6140). The
  2026-08-21 acceptance attempt failed for want of an authenticated browser
  (14 connection retries across the full window). A 2026-08-22 attempt connected
  the browser and the operator signed in — but 2026-08-22 was a SATURDAY, so no
  US session existed and no lawful event could occur. Nothing has touched the
  Grey Deer program between 2026-08-22 and this handoff (2026-08-27).
changed:
  - path: agentos/handoffs/GREY-DEER-RISK-INTELLIGENCE-2026-08-27.md
    what: This handoff — the executable acceptance packet for the browser session.
  - path: agentos/workstreams/WS-GREY-DEER-RISK-INTELLIGENCE.md
    what: >
      GD-3 entry updated with the GD-3R1 merge, the 2026-08-27 production
      pre-verification (the box IS running the repaired bytes and the
      closed-market clock laws hold in served bytes), and a CORRECTION of the
      false "no VPS shell from the fleet host" claim carried by the 2026-08-21
      record. next_action rewritten to the single remaining gate.
  - path: research/grey_deer/README.md
    what: Current-next-action rewritten for the 2026-08-27 state.
verified:
  - claim: >
      The VPS IS running the GD-3R1 bytes. /opt/macro HEAD tracks main
      (f5f11112da4 at probe time) and both repaired modules carry their
      GD-3R1 markers on the box: source_event_time appears 4x in
      scripts/build_risk_state.py and upstream_built 4x in
      scripts/build_live_risk_envelope.py.
    command: >
      ssh -i ~/.ssh/macro_dashboard_deploy_v2 root@146.190.142.17
      'git -C /opt/macro log --oneline -1;
      grep -c source_event_time /opt/macro/scripts/build_risk_state.py;
      grep -c upstream_built /opt/macro/scripts/build_live_risk_envelope.py'
    result: "f5f11112da4; 4; 4 (2026-08-27T05:07Z)"
  - claim: >
      The GD-3 module has been executing on EVERY fast-lane fire inside the
      gate window all week, at its designed cadence and cost — risk_envelope_live
      ok in ~0.9-2.2s every minute, with risk_state refreshing on odd minutes
      (~12s). This closes the 2026-08-21 handoff's named unverified item
      ("whether the new module executed cleanly on the box").
    command: >
      ssh -i ~/.ssh/macro_dashboard_deploy_v2 root@146.190.142.17
      'journalctl -u macro-live-fast.service --since "2026-08-26 15:00"
      --until "2026-08-26 15:12" --no-pager | grep -E "risk_envelope_live|risk_state: "'
    result: "14 consecutive ok lines; envelope every minute, risk_state odd minutes"
  - claim: >
      The GD-3R1 clock laws hold in PRODUCTION-SERVED BYTES on the closed-market
      path. The 2026-08-26 22:59Z envelope publishes
      clocks.event_time = null (NOT substituted with built) while
      clocks.observed_at = 2026-08-26T22:59:46.623Z and
      clocks.produced_at = 2026-08-26T22:59:47.538Z — millisecond precision and
      915ms APART (the F2 second-truncation defect is gone), with
      clocks.upstream_built = 2026-08-26T22:57:42.000Z preserved as separate
      lineage. revision=live_provisional, precedence=live, all four authority
      booleans false, live_transition carries candidate_stage/stable_stage/
      pending/last_observed_built, overlays.settled_bundle_id=cfceff99bc720316.
      risk_state agrees: live.source_event_time = None with an empty
      source_quote_clocks under stale_reason "market closed" — the lawful
      cannot-be-established -> null path, not a builder-clock substitution.
    command: >
      ssh -i ~/.ssh/macro_dashboard_deploy_v2 root@146.190.142.17 'python3 -c
      "import json; e=json.load(open(\"/var/lib/macro-live/public/live/risk_envelope.json\"));
      print(e[\"clocks\"], e[\"revision\"], e[\"authority\"])"'
    result: "all clauses as stated (2026-08-27T05:08Z, after-hours sample)"
  - claim: >
      A root VPS shell EXISTS from the operator's Mac and is the documented
      access path — app/deploy/README.md:29 gives
      `ssh -i ~/.ssh/macro_dashboard_deploy_v2 root@146.190.142.17`. The public
      hostname does NOT accept ssh (CDN-fronted, port 22 no-route); the raw IP
      does. The 2026-08-21 handoff's "no VPS shell exists from the fleet host"
      is FALSE and is corrected in the workstream record by this PR.
    command: >
      ssh -i ~/.ssh/macro_dashboard_deploy_v2 root@146.190.142.17
      'date -u; systemctl list-timers | grep macro-live'
    result: "root shell; macro-live-fast.timer enabled+active, ~60s cadence"
  - claim: >
      Nothing in the Grey Deer program changed between 2026-08-22 and
      2026-08-27 — the wave is exactly where the 2026-08-21 handoff left it,
      minus the GD-3R1 repair that landed on 08-22.
    command: >
      git log origin/main --since=2026-08-22 --oneline -- research/grey_deer/
      agentos/workstreams/WS-GREY-DEER-RISK-INTELLIGENCE.md agentos/handoffs/GREY-DEER*
      scripts/build_live_risk_envelope.py
    result: "empty"
unverified:
  - claim: >
      That clocks.event_time populates with a REAL source quote clock during an
      OPEN US session (the whole point of GD-3R1). Every production sample
      available to this session was taken after-hours, where null is the correct
      answer, so the open-market arm of the fix is proven by unit tests only.
    what_would_verify: >
      One authenticated read inside 13:30-20:00Z on a weekday showing
      rs.live_active true, rs.live.source_event_time non-null, and
      env.clocks.event_time equal to it (and never equal to rs.built).
  - claim: >
      That rs.live_active actually reaches true during the US session on current
      quote-plane behavior (the splice gate, not GD-3, owns this).
    what_would_verify: >
      Any in-session authenticated read of live/risk_state.json showing
      live_active true. If it stays false for a whole open session, that is a
      QUOTE/SPLICE plane defect and NOT a GD-3 failure — report it, do not
      "repair" GD-3 for it.
unresolved:
  - >
    The GD-3 wave closes on exactly one artifact: the four-clock production
    receipt, witnessed in an authenticated browser during a live window. The
    full executable recipe is in the body of this handoff under "The acceptance
    run".
  - >
    The tier-gated consumer script (anonymous 401 on /risk_envelope_live.js from
    a public page) is a deliberate posture, not a defect. If product ever wants
    the overlay visible pre-auth that is a separate operator public-boundary
    decision (config/site_access.yml + Caddyfile allowlists) — never taken as
    part of acceptance.
next_actions:
  - >
    Run "The acceptance run" in the body of this handoff from a session with a
    real authenticated browser, during 13:30-20:00Z on a weekday (US cash
    session; the fast-lane gate itself is 11:00-22:00Z but the qualifying live
    change needs the tape).
  - >
    On PASS: flip GD-3 to done in agentos/workstreams/WS-GREY-DEER-RISK-INTELLIGENCE.md
    with the four measured clocks inline, write
    agentos/handoffs/GREY-DEER-RISK-INTELLIGENCE-<date>.md carrying the receipt,
    refresh research/grey_deer/README.md, ship that records PR to MERGED, report, stop.
  - >
    On FAIL: repair ONLY the exact failing real path (Sol). Diagnose on the box
    read-only first; do not widen scope into ceilings, mappings, debounce,
    authority, the public boundary, ledgers, schedulers, or policy.
  - "GD-8A / GD-8B / GD-9A: commission only AFTER that receipt, and not from the acceptance seat."
  - "GD-4B / GD-4C remain open, unblocked, uncommissioned."
do_not_redo:
  - "Do not simulate, manufacture, or hand-mutate the acceptance event (Sol 2026-08-21) — no fixture, no local harness, no editing site/live/ artifacts, no forcing a builder run to create a 'change'."
  - "Do not run scripts.build_live_risk_envelope or scripts.build_risk_state BY HAND on the VPS. The dwell baseline (stable_stage / last_observed_built) persists inside site/live/risk_envelope.json; an out-of-band run corrupts the very state the receipt is measuring."
  - "Do not add risk_envelope_live.js or live/risk_envelope.json to any public allowlist — 'boundary unchanged' is an acceptance GATE, not an obstacle."
  - "Do not modify the GD-3/GD-3R1 implementation unless the real production witness falsifies it (Sol 2026-08-22)."
  - "Do not re-litigate the GD-4A.1 budget (max_sessions_behind=1 was adjudicated against three measured false-page classes)."
  - "Do not repeat the 2026-08-21 dead end: a VPS shell DOES exist (see verified[3]). Do not repeat the 2026-08-22 dead end: check `date -u +%A` before diagnosing a quiet market lane — a weekend is indistinguishable from a total outage of calendar-gated lanes."
  - "Do not start GD-8A/8B/9A before the receipt (Sol gate)."
danger_areas:
  - "site/riskdata/ is shared with market-regime-risk; Grey Deer owns only risk_envelope.json inside it."
  - "The live dwell state persists on the box in site/live/risk_envelope.json (gitignored). A manual delete resets the stable_stage baseline. Leave it alone."
  - "site/live/ is gitignored — nothing there can be committed, and nothing in a PR changes it. The box is the only place that state exists."
  - "The settled bundle id rotates every nightly settle (fd9ccdbe47f7f008 -> df843770aee6003c -> cfceff99bc720316 across 08-19/08-20/08-25). Never hardcode it; always compare the envelope's overlays.settled_bundle_id against the page's data-bundle-id read in the SAME session."
  - "gh REST is one shared 5,000/hr pool for the whole fleet: no unthrottled polling loops, one watcher per endpoint."
---

# Grey Deer GD-3 — acceptance handoff to a computer-access session · 2026-08-27

GD-3 is built, merged, deployed, repaired (GD-3R1), and **running in production
on every fast-lane fire**. Exactly one thing is missing, and it is not code: a
human-authenticated browser has never watched a real live-source change travel
the chain. This document is the executable packet for the session that can.

## Why a browser is required at all

`live/risk_envelope.json` and its consumer `risk_envelope_live.js` are both
tier-gated by design: Caddy's `@reg_asset` rule is default-deny and defers to
`app/regwall.py`, which authenticates on the `_mm_supabase_access_token` cookie
and has **no ops bypass**. Anonymous `curl` gets 401. Credentials may not be
typed by an agent. So the only lawful witness is a browser already carrying the
operator's signed-in session — which is precisely what the receiving session has
and this one does not.

A VPS root shell **does** exist (`ssh -i ~/.ssh/macro_dashboard_deploy_v2
root@146.190.142.17`, documented at `app/deploy/README.md:29`) and is how the
production pre-verification in the `verified` block was obtained. It is
excellent for read-only diagnosis. It is **not** a substitute for the receipt:
the acceptance explicitly measures the browser paint leg, and reading the file
on the box skips it.

## What is already proven (do not re-prove)

| Gate | State | Evidence |
|---|---|---|
| Module executes on the box every fire | PROVEN | journal, 14 consecutive `risk_envelope_live: ok` |
| `revision: live_provisional` | PROVEN | served bytes |
| All four authority booleans false | PROVEN | served bytes |
| `precedence` present and lawful | PROVEN | served bytes |
| `live_transition` shape | PROVEN | served bytes |
| ms precision, `observed_at != produced_at` | PROVEN | 22:59:46.623Z vs 22:59:47.538Z |
| `event_time` never substituted with `built` | PROVEN (closed path) | `event_time: null` while `built` was 22:59:46 |
| `upstream_built` kept as separate lineage | PROVEN | `clocks.upstream_built: 2026-08-26T22:57:42.000Z` |
| **`event_time` from a REAL quote clock (open market)** | **UNPROVEN** | needs the live window |
| **source change -> envelope within <=2 fast fires** | **UNPROVEN** | needs the live window |
| **browser paint of the overlay** | **UNPROVEN** | needs the authenticated browser |
| **`data/` + forward ledgers unchanged over the interval** | **UNPROVEN** | needs the interval |

## The acceptance run

Run on a weekday, inside **13:30-20:00Z** (US cash session). The fast-lane gate
is 11:00-22:00Z, but the qualifying event needs a moving tape.

**Step 0 — orient.** `date -u +%A` (a weekend has no session and no lawful
event). Open `https://www.mastermind-x.com/macro.html` in the authenticated
browser. Confirm the payloads return 200, not 401; if 401, reload once, and if
still 401 ask the operator to sign in. Record the page's `data-bundle-id` and
`data-settled-session` attributes.

**Step 1 — pin the interval start.** Record `origin/main`'s head SHA + commit
time and the blob SHAs of every `data/risk_radar_intl/*_forward_log.jsonl`
(single `gh api` calls, no loops). This is the baseline for the
durable-data-unchanged proof.

**Step 2 — sample the pre-state.** In-page, with `credentials: 'same-origin'`
and `cache: 'no-store'`, fetch `live/risk_state.json` and
`live/risk_envelope.json`. Record `rs.built`, `rs.live_active`,
`rs.live.source_event_time`, `env.built`, `env.clocks`.

**Step 3 — wait for the FIRST real change.** Poll no faster than every ~30-60s.
The qualifying event is `rs.built` advancing **with `rs.live_active === true`**
and `rs.live.source_event_time` carrying a real quote clock. Note the browser
wall-clock time at first sight. Take the first one that occurs; do not select
among them, and do not induce one.

**Step 4 — verify propagation.** `risk_state` refreshes on odd minutes and the
envelope rebuilds every minute, so the envelope must reflect that risk_state
observation within **<=2 fast fires (~2 minutes)**. That bound is THE gate.

**Step 5 — verify the clocks.** On the post-change envelope:
`clocks.event_time === rs.live.source_event_time` (or `null` if genuinely
unestablishable — but **never** equal to `rs.built`); `observed_at` and
`produced_at` both millisecond-precision and distinct; `clocks.upstream_built`
present and separate; `revision === "live_provisional"`;
`overlays.settled_bundle_id` equal to the page's `data-bundle-id`; `precedence`
lawful; all four authority booleans false; `live_transition` carrying
`candidate_stage`/`stable_stage`/`pending`.

**Step 6 — verify the paint.** `#gde-live-chip` visible on the page (the
overlay hooks `#gde-live-chip`, `#gde-pending-chip`, `#gde-live-receipt` are
baked into macro.html). Screenshot it. Record `browser_seen_at`.

**Step 7 — durable-data proof.** Re-read the head SHA and the ledger blob SHAs
from step 1. Live-plane `[skip ci]` ticks on main are expected and fine; the
`data/risk_radar_intl/*_forward_log.jsonl` blobs must be **unchanged** — the
live lane never writes forward ledgers, which is the point.

**Step 8 — report three latencies SEPARATELY.**

- **feed delay** = `observed_at - event_time`. **Informational only. Never a
  failure.** Sol: do not fail the system merely because an entitled feed itself
  is delayed — the vendor plane is ~15 min delayed by contract.
- **processing** = `produced_at - observed_at`, plus the source-change ->
  envelope span. **This is the gate (<=2 fires).**
- **paint** = `browser_seen_at - produced_at`.

## Pass / fail

**PASS** = steps 4, 5, 6 and 7 all hold on a real, unmanufactured event.
Then: flip GD-3 `status: done` in the workstream record with the four measured
clocks inline; write `agentos/handoffs/GREY-DEER-RISK-INTELLIGENCE-<date>.md`
carrying the receipt verbatim; refresh `research/grey_deer/README.md`; ship that
records PR through to MERGED; report; stop. Do not start GD-8A/8B/9A.

**FAIL** = repair only the exact failing real path, and nothing adjacent.
`scripts/**` edits make the PR authority-changing, so confirm main's newest
`ci.yml` baseline is green before merging.

**NO EVENT in the available window** = record `WAITING_FOR_PRODUCTION_EVENT`
and stop. That is a lawful terminal state, explicitly authorized by Sol, and it
is strictly better than a manufactured receipt.

## One likely snag, named in advance

If `rs.live_active` stays `false` for an entire open session, no lawful
qualifying event can occur. That is the quote/splice plane (`_usable()` /
`stale_after` in `scripts/build_risk_state.py`), **not** GD-3. Report it as a
quote-plane finding; do not "fix" GD-3 to make an event appear.
