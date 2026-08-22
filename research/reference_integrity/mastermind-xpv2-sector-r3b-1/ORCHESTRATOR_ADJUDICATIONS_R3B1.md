# XPV2-SC-R3B.1 — Orchestrator adjudications

Running record of every ruling the R3B.1 orchestrator (returning R3B Fable session) takes
executing Sol's surgical-fix commission (`COMMISSION.md` in this directory). Same convention
as the predecessor's `ORCHESTRATOR_ADJUDICATIONS.md`: rulings here are the cycle's audit
trail, not authority — Sol's commission and the RIG govern.

## §0 Pre-start sequence — receipts

1. **Critic integration (commission step 1-2).** The four review-only critic PRs were
   verified review/evidence-only by file list (every path under
   `research/reference_integrity/mastermind-xpv2-sector-r3b/reviews/`), their recorded
   HOLD-FOR-SOL holds released by comment naming the R3B.1 commission as the Sol release
   condition, and squash-merged: #6228 (Data/Authority, BLOCK, DAC-101..108), #6231
   (Visual/Taste, BLOCK, VTC-001..014), #6233 (Product Regression, PASS_WITH_CONDITIONS,
   PRC-001..003), #6234 (Mobile/Accessibility, BLOCK, MAC-001..006). Check state at merge:
   every check concluded, sole red = the by-design `ci-authority/codex/merge-queue-pilot`.
2. **Predecessor verdict (step 3-4).** Sol's REVISE transcribed into
   `mastermind-xpv2-sector-r3b/verdict.yml` (schema `mastermind.rig_verdict.v1`, eight-answer
   packet complete); manifest flipped `in_review -> revise` anchored on the newline-bounded
   field (the freeze's comment-collision trap avoided). No `approval.yml` exists or will.
   PR #6239.
3. **Mandate tool (step 5).** `python3 scripts/check_reference_integrity.py --mandate`
   run against both sets; the successor derivation returned **29 open items** (15
   `upheld_revise` findings + 14 `R3B1-*` conditions) — continuity.yml was generated from
   that output, not hand-enumerated.
4. **Successor ID (step 6).** `mastermind-xpv2-sector-r3b-1` accepted by current tooling
   (RIG scan exit 0 with the new set admitted at draft).
5. **Frozen predecessor untouched (step 7).** All fixes land in
   `mockups/refs/reference_integrity/mastermind-xpv2-sector-r3b-1/`; the R3B tree keeps its
   frozen bytes.

## §1 Verdict transcription rulings (what was adjudicated, not merely copied)

- **15 upheld_revise**: VTC-003, VTC-006, MAC-001, MAC-002, MAC-003, MAC-005, MAC-006,
  DAC-101..108 — each mapped to its owning R3B1-* fix item in the note, so the successor
  closure is mechanical (id-for-id).
- **6 overridden, with permanent authority records**:
  - `mastermind-xpv2-sector-r3b::visual_taste::VTC-001` / `::VTC-002` — the critic's own
    second pass downgraded both to minor (dead-token sub-claim withdrawn as factually
    wrong; composition meets its stated budget). Deferred to R3C input per the commission's
    do-not-reopen list (Map reserved-hue law; Explore task architecture).
  - `mastermind-xpv2-sector-r3b::mobile_accessibility::MAC-004` — an authority CONFLICT,
    not a defect: the critic commission said 3×2, the responsive contract said 2×3 at
    ≤359. Sol resolved it in the R3B.1 commission do-not-reopen list: **2 columns × 3 rows
    at ≤359 is RATIFIED**. The frozen candidate already renders exactly that (critic's own
    measurement: unclipped, ≥53px targets at 320). Consequence: **no artifact change is
    owed for MAC-004**; the reconciliation IS this record plus the verdict override row.
  - `mastermind-xpv2-sector-r3b::product_regression::PRC-001/002/003` — all three are
    live-integration properties a frozen reference cannot execute (Time Machine episode
    fetch, optional pulse.json column, first-viewport composition); recorded for the R3C
    draft's live-integration conditions, not R3B.1 fixes.
- **Scope guard**: upheld VTC minors with no R3B1-* item (VTC-011 universe-tab selected
  state at 320, VTC-013 empty grid cell) are NOT successor obligations — Sol's commission
  is the authority on the surgical scope ("fixes only what the fresh four-critic cycle
  proved defective", enumerated as R3B1-01..14). They remain in the critic receipts for the
  R3C record. VTC-014 (px-only type ramp) is the commission's own R3C-only list item
  ("site-wide relative-unit typography debt").

## §2 Cycle-start integrity proof

The successor build tree began as a byte-identical copy: before any fix landed,
`build_reference.py` in the copied tree rebuilt the candidate to sha256
`19553267d3f51659503fc836da6b6bdaa06afc9cdd607aafb1bb795e46c47dca` — exactly the frozen
R3B candidate hash. Every diff between the successor candidate and the frozen predecessor
is therefore attributable to an R3B1-* fix by construction.

## §3 Lane decomposition (commission "Operator decomposition")

- Lane A — authority hero repair (R3B1-01..07, R3B1-13 investigation): Opus `designer`.
- Lane B — accessibility + token repair (R3B1-08..12): Opus `designer`, sequential after A
  (shared view files).
- Lane C — verification hardening (R3B1-14 + acceptance gates): Sonnet `builder`, after A/B
  (the restored features must exist before bidirectional inventory can pin them).
- Lane D — evidence recapture: Sonnet `builder`, after A/B/C converge.
- Orchestrator: adjudication, scope-creep prevention, continuity closure, freeze, PR/merge.

## §4 Lane A return — adjudicated ACCEPTED (commit 3dd85a6a05d4)

All of R3B1-01..07 landed producer-bound with production citations (sizing inert-guard
reproduced from `sector_central.html.j2:2888`; caveat clauses verbatim from `:2155`;
migration `:2130`; playbook `:2163`; enrichment guards `:2926-2933`). Evidence accepted:
deterministic rebuild ×2 = `57fe91cf7409…`, verify 10/10, 6-view sweep clean, 44/44
contrast cells ≥4.5:1 on restored nodes, 10 crops. **R3B1-13 RESOLVED, no Sol return
needed:** the bare decimal is `subsector_confluence.json → double_gated.double_buy[]
.combined_score`, contract at `engine/subsector_confluence.py:322-347`, and the label used
is production's OWN header for that exact field — `Conviction / 综合把握`
(`templates/subsectors.js:330`). The commission's never-Score/Probability/Confidence/
Strength rule is satisfied by construction (the producer contract names it).

Rulings on the lane's flagged items:

1. **R3B1-06 residual (DAC-107 partial closure) — carve-out obeyed, residual DISCLOSED to
   Sol.** The lane proved the Overview action-board "Score / 评分" column is byte-identical
   to `theme_intel.themes[].score` (`scripts/build_site.py:1784` copies `th.get("score")`),
   so the commission's "independent action-board score" carve-out protects a column that is
   not independent on this fixture. The prohibition is explicit; the reference obeys it.
   Consequence recorded honestly: DAC-107's one-measure-two-names exposure survives on
   Overview's action board (context surfaces are unified to Strength / 强度 as
   commissioned). If Sol intends R3B1-06 to close DAC-107 completely, the residual fix is a
   one-line header change — flagged in the freeze return.
2. **Unit-consistency deviation UPHELD.** Production renders the same producer byte
   (`-0.0959`) at two magnitudes on one screen (`fmtPct()` on the raw fraction → "-0.10%"
   in the hero vs "-9.6%" on the board). The reference renders it once, at the board's
   standard percent convention. No value invented; a production unit DEFECT is not carried
   into migration law. Recorded as copy-ledger R-4; the production `fmtPct`-on-fraction
   defect joins the R3C production-repair candidates.
3. **Conviction label collision across producers** (`combined_score` "Conviction / 综合把握"
   vs `conviction.score` "Conviction / 信心") — both labels are production's own; neither is
   the reference's to rename. Recorded as an R3C producer-side naming item.
4. Glyph substitutions (drawn chevron/receipt mark per spec §9.3), caveat clause order
   (governing caveat leads), `.r3-rcpt--named` modifier, and `pre-line` tipbox: accepted as
   in-grammar design execution; the CSS source-order specificity trap is handed to Lanes
   B/C in their commissions.

## §5 Lane B return — adjudicated ACCEPTED (commit 264987cfb032)

All of R3B1-08..12 landed by the semantic-token route with committed rerunnable gates
(zoom_sweep.py, contrast_audit.py, aria_id_audit.py, lang_probe.py). Evidence accepted:
candidate `fec05b058fbc…` deterministic ×2, verify 10/10, R3A suite 59 passed, zoom 0/48
failing (painted-box method), contrast 0 AA failures / 0 sub-10px (was 44) / 0 parser
suspects with EN and Lane A floors unregressed to the second decimal, 0 duplicate ids /
0 unresolved ARIA refs, lang probe 7/7 with `zh-CN` cited from production
(`templates/theme.js:600`). The ZH-dark repair is a structural token — the missing fourth
quadrant of the ink-rung matrix (`--ink-mix-up: 84%` under dark+ZH), the same rung the
system already gives red in both light cells — not a spot patch.

Rulings on the lane's flagged items:

1. **sc_flows verbatim fragment (75 cells 2.24–4.45:1) NOT repaired — UPHELD.** Those tint
   fills are producer bytes under a sha256 receipt the reference may not rewrite; the
   commissioned R3B1-11 cells are all closed. Production's own contrast debt is recorded
   where the commission directs — `design_system_dependency_r3c.md` — as a bounded
   Design-System dependency for R3C.
2. **Heatmap shadowed tile text has no honest flat-surface ratio — UPHELD.** Measured and
   bucketed rather than scored under a formula that does not apply; the repair delivered is
   containment (painted-width label gates, no cut tickers), which is what the finding's
   customer harm was.
3. **Cross-lane geometry fixes ACCEPTED**: the sweep found 25px/1px overflow cells
   introduced by Lane A's new hero controls and repaired them as geometry only (producer
   copy untouched) — exactly the gate's job. The shared receipt controller changes (stable
   `#r3-receipt` id, tap-toggle promotion, Escape/focusout dismissal) were required by
   R3B1-08's no-second-controller rule and verifiably left Lane A's floor at 5.11:1.
4. **Raising the six 9.5px glyphs and the 9px eyebrow beyond the named cells — UPHELD**:
   "live type >=10px, no 9px exception" is a floor, not a named-cell list.
5. **Dark+EN red rung (`--ink-mix-down: 100%`) untouched — UPHELD** (5.07:1 passing today;
   tuning it is an uncommissioned EN visual change; recorded D-1 in the dependency file).

## §6 Lane C return — adjudicated ACCEPTED (commit 6fb0646826dc)

R3B1-14 landed as commissioned: bidirectional inventory (`inventory_check.py` — direction 1
= 15 producer-derived pins re-computed from fixture bytes at every run, checked against the
RENDERED DOM, never candidate self-enumeration; direction 2 = 22/22 registry blocks traced
to receipts, unresolved fetches all documented exceptions, every data-ref-nav href matched
to one of 8 contract-derived destination families), unique-kill mutation suite (11
mutations, pristine-copy green proven, all reds pairwise distinct — "a guard true before
the feature is not a guard" satisfied literally), and acceptance wiring
(`verify_reference.py` now 16 checks, slow browser gates asserted from committed
artifacts). Evidence accepted: 16/16 ALL GREEN, inventory 26/26, mutation 13/13, R3A suite
59 passed, candidate sha unchanged `fec05b058fbc…`. DAC-108's failure mechanism —
completeness proven by the candidate enumerating itself — is now structurally impossible
for the pinned inventory: removing any restored hero fact produces a unique named red.

Rulings: (1) the premiumdata access-gate fetch not being in ALLOWED_UNRESOLVED_FETCHES is
correct-as-built (the default boot path never issues it; instructions recorded for any
later wave that wires it); (2) the two extra direction-1 entries (coverage sentence,
Conviction label) follow the commission's own scope text — accepted, not scope creep.

(§7+ appended as further lane returns are adjudicated.)
