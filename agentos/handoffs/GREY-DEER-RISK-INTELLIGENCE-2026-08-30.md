---
workstream: "WS:GREY-DEER-RISK-INTELLIGENCE"
session: "claude/gd-compact-risk-context-20260830"
model: local
ended_because: complete
prs: [6685]
mission: >
  Chairman-direct: replace the full-width Grey Deer / Risk Envelope panel on
  Macro macro.html with a compact Market Reads rail inside the regime hero,
  and move the explanatory Grey Deer projection into the existing #dlg-risk
  dialog. Presentation only. Open a HOLD-FOR-SOL draft PR; do not self-merge.
state_before: >
  GD-2 shipped a dedicated full-width L1 band below the regime hero. GD-3 live
  overlay hooks (#risk-envelope-band, #gde-live-chip, #gde-pending-chip,
  #gde-live-receipt) were production-proven. Chairman overruled the dedicated
  full-width L1 for presentation only; semantic freeze unchanged.
changed:
  - path: templates/_risk_envelope_band.html.j2
    what: >
      Macros only (gde_rail / gde_detail). Shared glance vocabulary. L1 is one
      button opening #dlg-risk. L2/L3 live in #gde-detail inside that dialog.
  - path: templates/_risk_envelope_band.css.j2
    what: >
      Compact hero rail + dialog detail. [hidden] display trap closed. Tablet
      density tightened. Semantic inks via gde-ms-* / gde-hz-* classes.
  - path: templates/dashboard.html.j2
    what: >
      Import macros; rail inside #regime-radar; #dlg-risk title Risk Detail;
      gde_detail first in the dialog body. Scare Ladder retained below.
  - path: tests/test_risk_envelope_presentation.py
    what: Presentation contract for L1/L2/L3 hooks, null-hazard vocabulary, site splice.
  - path: site/macro.html
    what: Spliced compact rail + detail; hashed CSS link d1ad36ff.css.
  - path: mockups/refs/grey-deer-compact/
    what: Before/after screenshots and measurements.json for Sol review.
verified:
  - claim: >
      Presentation tests pass, including the compact site/macro.html contract
      and the [hidden] CSS override.
    command: "python3 -m pytest tests/test_risk_envelope_presentation.py -q"
    result: "15 passed"
  - claim: >
      Envelope, live-envelope, and live-session-floor suites still pass on this
      checkout (no engine edits).
    command: "python3 -m pytest tests/test_risk_envelope.py tests/test_live_risk_envelope.py tests/test_risk_state_live_session_floor.py tests/test_risk_envelope_presentation.py -q"
    result: "157 passed"
  - claim: >
      Playwright DOM heights on this worktree's site/ via 127.0.0.1:8777:
      1440=57px (≤80), 768=88.78px (≤96), 390 EN=85.38 / ZH=67.38 (≤118);
      no horizontal overflow; default rail shows Settled not Live; live-healthy
      fixture shows Live 05:12Z and hides Settled; #dlg-risk opens with
      #gde-detail and title Risk Detail / 风险详情.
    command: "node /tmp/gde_proof.cjs after 8777 mockups/refs/grey-deer-compact/after extra"
    result: "measurements.json in mockups/refs/grey-deer-compact/after/"
  - claim: "Title i18n, template↔site sync, runtime style injection, and design-system enforce-added are clean for this diff."
    command: "python3 scripts/check_title_i18n.py; python3 -m scripts.check_template_site_sync; python3 scripts/check_runtime_style_injection.py; python3 scripts/check_design_system.py --mode enforce-added --diff-file /tmp/gde-design.diff"
    result: "all exit 0; design-system blocking=0"
unverified:
  - claim: "Production https://www.mastermind-x.com/macro.html shows the compact rail."
    what_would_verify: "Sol merge + VPS pull + authenticated live load. PRODUCTION STATUS: NOT DEPLOYED."
  - claim: "A real US-session live overlay poll paints #gde-live-chip without a fixture."
    what_would_verify: "Open-session browser against live/risk_envelope.json; this wave only fixture-painted the overlay."
unresolved:
  - "Sol product/taste/semantic review of the HOLD-FOR-SOL draft. Do not merge until Sol releases the hold."
  - "Hero moon/sun watermark can visually overlap the open #dlg-risk panel (pre-existing decorative stacking, not introduced by engine changes)."
next_actions:
  - "Sol reviews draft PR #6685 (HOLD-FOR-SOL: compact Grey Deer Market Reads into the regime hero)."
  - "On Sol release: squash-merge, wait for the covering render or VPS pull, then verify live macro.html. This session must not self-merge."
do_not_redo:
  - "Do not edit engine/risk_envelope.py, live cadence, schema, or templates/risk_envelope_live.js for this presentation wave — hook IDs were kept unique so the overlay needs no JS change."
  - "Do not restore the dedicated full-width .gde-band panel; Chairman overruled that L1 shape."
  - "Do not average Trend and Breakage, quote the hero 77/100 in the rail, or print No breakage when hazard stage is null with an unavailable required source."
  - "Do not start GD-8A / GD-8B / GD-9A from this wave."
danger_areas:
  - "site/macro.html was spliced, not produced by a full scripts.build_site run. A later full render must keep the dashboard.j2 rail/detail wiring; do not re-include the old _risk_envelope_band.html.j2 as a standalone panel."
  - "Hashed CSS must match sha256 of a leading newline plus templates/_risk_envelope_band.css.j2. Editing the j2 without rewriting site/assets/css/<hash>.css and the macro.html href ships a 404 rail."
  - "body.page-macro .gde-stamp-live { display: inline-flex } out-specs the UA [hidden] rule. The [hidden] { display: none !important } override is load-bearing (same class of trap as .pv-live)."
  - "Local python -m http.server can bind IPv6 *:port and a leftover IPv4 127.0.0.1:port can serve a different tree. Playwright to 127.0.0.1 will hit the IPv4 leftover. Proof in this session used --bind 127.0.0.1 --directory <this-worktree>/site on port 8777."
  - "mx5OpenDlg still redirects anonymous macro visitors to sign-in. Local dialog screenshots stubbed MMXAccessPreview.isAnon. Both the rail and the existing hero Risk Detail button share that gate."
---

## §0 State — what is true right now

Chairman-direct compact Market Reads is implemented in worktree
`.claude/worktrees/gd-compact-risk-context` on branch
`claude/gd-compact-risk-context-20260830`. The full-width Grey Deer band is gone.
A 57px rail sits inside `#regime-radar`. Clicking it opens `#dlg-risk` titled
Risk Detail, with Market reads first and Scare Ladder retained below. This is
not on production. Sol owns merge.

## §1 What is LEFT — in order

1. Push the branch and open one **draft** PR titled `HOLD-FOR-SOL: …`. No
   `merge-on-green`. Comment names Sol as authority and the release condition.
2. Sol product / taste / semantic review.
3. Only after Sol releases the hold: squash-merge, then verify live
   `https://www.mastermind-x.com/macro.html`.

## §2 What will bite you

Spliced `site/macro.html` will be overwritten by the next full site bake — the
source of truth is `templates/dashboard.html.j2` plus the two `_risk_envelope_band.*`
partials. Visual proof against the wrong `http.server` tree reproduces the old
472px band even when the worktree files are compact. Do not treat a local live
chip fixture as production live-window proof.

## §3 What was decided and found

No new `DEC:` / `DSC:` minted. Presentation-only Chairman override of GD-2's
dedicated full-width L1; semantic freeze untouched.

## §4 Not in scope — do not adopt

Engine, schema, adapters, coherence, live cadence, Terminal, Prophet, nav, fused
scores, and any GD-8/9 start. No Slack thread was required for this project.
