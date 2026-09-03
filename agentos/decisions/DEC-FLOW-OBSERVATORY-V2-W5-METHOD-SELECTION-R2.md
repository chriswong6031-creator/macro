---
key: FLOW-OBSERVATORY-V2-W5-METHOD-SELECTION-R2
question: >
  Does the first W5 method-selection adjudication (DEC-FLOW-OBSERVATORY-V2-W5-METHOD-
  SELECTION) survive an independent statistical review of its names and southbound
  rulings, or must it be revised?
answer: >
  No — REVISED. Themes: method M0 stays; thresholds tau=0.75, beta=30 STAND unchanged
  (verified sound on their applied surface: per-theme neutral_share 0.3222->0.4716 in
  band, flip 0.1865->0.1610 improves — reconfirmed, not a tie). Names: REVERTED to the
  incumbent tau=0.5, beta=25 — the R1 tau=0.3 selection was computed on the harness's
  breadth-tilt-style grid and misapplied to the per-name surface, where it breaches the
  frozen 25% neutral floor (measured neutral_share=0.188) and worsens one-day flip rate
  by +7.1% relative. Southbound: REVERTED to method M0, tau=0.5 (numerically and
  methodologically unchanged from pre-W5) — the R1 M1 (winsorized) adoption rested on a
  single unreplicated seeded draw of the frozen Sec 5(a) outlier/quiet metric; independent
  30-seed replication on both data configs found P(pass)~=0.75 under seed variation (median
  improvement ratio ~=0.57) — seed assignment, not a lens property, and not decisive
  support for a method change. Net W5 engine delta after this revision: themes thresholds
  only.
rationale: >
  An independent statistical review of DEC-FLOW-OBSERVATORY-V2-W5-METHOD-SELECTION
  returned FAIL with two concrete blockers, both accepted by the Fable principal without
  qualification. (1) Names: the R1 "mechanical completion of the frozen lexicographic
  rule" was arithmetically correct against the grid it read (threshold_sweep_all.M0, the
  same breadth-tilt-style construction Sec 4 defines for the sector-breadth gauge) but that
  grid is not what tau=0.3 was then deployed against — engine.flow_velocity applies the
  names threshold PER NAME, not to an aggregate breadth series. Recomputing the per-name
  state distribution at tau=0.3 directly (the same construction as Metric 1's per-entity
  pooled state-share table) shows it breaches the frozen 25% neutral floor and worsens flip
  rate — a violation of Sec 4's own objective on the surface the threshold actually governs
  production behavior on. Both lawful readings of the frozen rule once the wrong-surface
  reading is discarded (treat the R1 selection as invalid and re-run nearest-band on the
  correct surface, or fall back to "no point in band -> incumbent") land on the same
  answer: tau=0.5. (2) Southbound: Sec 5(a) requires >=30% outlier/quiet improvement to
  adopt a challenger method. R1 read that condition off ONE seeded draw of the harness's
  outlier fixture. A statistical claim resting on n=1 cannot be distinguished from noise;
  independent 30-seed replication found the pass/fail flips on which seed happened to run
  (P(pass)~=0.75), so roughly a quarter of equally-valid draws would have failed to satisfy
  Sec 5(a) at all. A method switch is not supportable on a condition that is itself a coin
  flip. Separately, R1's southbound "Step 2" (excluding held-out-unreachable tau from the
  re-sweep) applied the <2% sanity bound only to the just-adopted M1 grid, never to M0 — a
  post-hoc, challenger-only application the frozen Sec 4/Sec 5 text does not restrict to
  one candidate; WITHDRAWN as a prereg breach. With the method correctly reverted to M0,
  the frozen tie-break (ties, or every candidate excluded, -> incumbent tau=0.5, beta=25)
  is what actually retains tau=0.5, not the narrower M1-only exclusion R1 relied on. Themes
  was independently re-verified sound on its own applied surface (the per-theme rollup
  computes over the SAME cross-sectional grid the sweep evaluated) and stands unchanged.
  Full recomputation: reports/flow_observatory_w5_methods.md §7 Revised adjudication.
alternatives:
  - option: Keep the R1 names selection (tau=0.3) since its OWN grid arithmetic is correct
    why_not: >
      Correct arithmetic against the wrong surface is not evidence for the production
      behavior it is deployed to control. The per-name application of tau=0.3 measurably
      breaches the frozen 25% neutral floor and worsens flip rate — the exact objective
      Sec 4 exists to protect — so keeping it would ship a threshold that fails the rule it
      was chosen under, just not on the grid the failure would be visible in.
  - option: Keep the R1 southbound M1 adoption since 4.49% state-disagreement genuinely
      cleared the 20% HOLD bound
    why_not: >
      The state-disagreement figure answers a different question (does M1 look almost
      identical to M0 on history) than Sec 5(a) (does M1 measurably improve outlier/quiet
      behavior). A sanity bound clearing does not manufacture evidence for the adoption
      condition it was never meant to substitute for; Sec 5(a)'s own evidence is the one
      shown to be a single noisy draw.
  - option: Re-run the full W5 harness now with a 30-seed outlier/quiet metric and a
      per-name-surface names sweep, and re-adjudicate from fresh output
    why_not: >
      Out of scope for this corrective round (explicitly excluded from the commissioning
      packet: "any new evaluation running"). The independent review's 30-seed replication
      and per-name recomputation are cited as given facts from that review, not re-derived
      here; a properly-replicated, preregistered re-run is left as future work (ruling 5 —
      a legitimate preregisterable follow-up, not this wave).
  - option: HOLD the whole PR (all three lenses) pending a fresh preregistered re-run
    why_not: >
      Themes was independently re-verified sound and has no open blocker; holding it too
      would block a real, checked improvement over a defect neither blocker touches. The
      minimal correct action is to keep what survived review and revert what did not.
evidence:
  - "PR #6808 comment 5531154940 — https://github.com/mastermindx-market-intelligence/macro/pull/6808#issuecomment-5531154940
    (verbatim revised adjudication this record implements; supersedes comment 5530582923)"
  - "reports/flow_observatory_w5_methods.md §7 Revised adjudication (appended; §6 R1
    section preserved unchanged) — verbatim rulings + the review's key recomputations
    (names applied-surface neutral_share=0.188 and +7.1% relative flip; the 30-seed
    P(pass)~=0.75 / median ratio ~=0.57 replication; the withdrawn post-hoc held-out
    exclusion)"
  - "reports/flow_observatory_w5_methods.json adjudication_r2 key (appended alongside the
    unmodified adjudication R1 key)"
  - "engine/flow_velocity.py: _NAMES_VIN/_VOUT reverted to 0.5/-0.5; _channel()'s
    winsorize=(name==\"southbound\") call removed (southbound now always M0); dead
    module-level _VIN/_VOUT constants removed (readerless in production); _winsorize_causal
    kept as a dormant harness-parity utility with an explicit no-production-caller
    docstring note"
  - "engine/flow_observatory/contract.py: dead NAMES_REL_THRESH constant removed (never
    read outside its own definition even under R1 — engine.flow_velocity's names lens
    always passed its own module-level threshold explicitly); THEMES_REL_THRESH and
    SOUTHBOUND_REL_THRESH unchanged"
  - "tests/test_flow_velocity.py and tests/test_flow_observatory_methods.py updated to pin
    the reverted constants and the R2 report block (see this PR's test diff)"
  - "templates/flow_velocity.html.j2 Method tooltip updated to the actual per-lens numbers"
affects: ["WS:FLOW-OBSERVATORY-V2", "engine/flow_velocity.py", "engine/flow_observatory/contract.py",
         "reports/flow_observatory_w5_methods.md", "reports/flow_observatory_w5_methods.json",
         "templates/flow_velocity.html.j2", "site/flow_velocity.html", "site/flowdata/desk.json",
         "docs/site_semantics/china.md"]
confidence: high
reversibility: easy
decided_by: coo-fable
decided_at: 2026-09-03
supersedes:
  - DEC:FLOW-OBSERVATORY-V2-W5-METHOD-SELECTION
---

## Grounds

W5's whole point is a preregistered, evaluated selection that cannot be reverse-fit to a
preferred outcome — which cuts both ways: it also means a selection whose evidence is
found to be flawed AFTER the fact must be revised rather than defended. The independent
review here did exactly the job the program's own epistemics law calls for (adjudication
coverage gate: red-team make-or-break calls before presenting) one step late — against an
already-committed decision record rather than before it. Accepting the review in full,
appending (never rewriting) the R1 record, and minting a reciprocally-linked superseding
record is the honest way to correct course: the R1 numbers were real measurements of what
the harness computed, they were simply computed on, or evaluated from, the wrong surface
for two of the three lenses.

The asymmetry in the outcome is itself evidence the process worked: themes — independently
re-checked on its OWN applied surface — reconfirmed cleanly, while names and southbound —
where the review found a surface mismatch and a single-draw statistic respectively — both
reverted. A review that reversed everything indiscriminately would be more suspicious than
one that reversed exactly the two lenses with a demonstrable defect and left the third
alone.

## What would reopen this

- A future, properly preregistered W6+ wave that re-runs the harness with (a) the names
  threshold sweep computed directly against the per-name state-distribution surface
  (never the breadth-tilt-style grid) and (b) a replicated, CI-carrying outlier/quiet
  metric (multiple seeds, a confidence interval, not a single draw) could revisit either
  reversion on its own merits — ruling 5 explicitly preregisters this as legitimate future
  work for southbound's M1 outlier promise specifically.
- If a future wave adds a genuine names-lens breadth-tilt gauge to production, the names
  beta value would need its own fresh threshold sweep against THAT gauge's actual surface
  — not a revival of the withdrawn R1 number, which was never validated against any
  surface that exists in production.
