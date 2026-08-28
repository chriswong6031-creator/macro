# XPV2-SC-R3B — Orchestrator (Fable) adjudication record

Cycle: `mastermind-xpv2-sector-r3b` · Commission: `COMMISSION.md` (Sol, final) ·
Date range: 2026-08-21 · Orchestrator: Fable main loop (per commission §4.3).

This file records every ruling the orchestrator made over the delegated lanes'
disclosed deviations, gaps, and conflicts. It is part of the cycle record so the
four fresh independent critics (commission §27) can audit each call rather than
rediscover it. Nothing here amends the R3A binding pack; where a ruling touches
production behavior it is filed as a delta for R3C, never claimed fixed.

## 0. Current-state verification verdict (commission §3)

- Worktree at `origin/main` (a65e15eafcd9); branch `claude/xpv2-sc-r3b-reference`.
- R3A attack suite 59/59 green pre-design.
- Post-R3A drift on main: exactly two diffs (`config/site_access.yml`
  +/portfolio_state.js public path; `scripts/build_site.py` +risk_envelope_live.js
  copy list). **Verdict: no semantic invalidation of any Sector Central
  producer/template/route/access contract. Fixture stands; no refresh.**
- No open PR owned Sector Central markup/reference scope at start.

## 1. Fixture supplement (RULING: extension is lawful; rebake is not)

The R3A fixture (18 receipts, frozen at `4c55fe433490`) deliberately excluded
artifacts its commission never listed (`fixture/PROVENANCE.md` §"What is NOT").
The reference cannot render Money/Map surfaces without them. Ruling: a
**supplementary R3B capture** under `mockups/.../build/fixture_supplement/`,
captured from git-pinned bytes at the SAME epoch commit `4c55fe433490`, with its
own receipts + provenance, R3A fixture and receipts byte-untouched. Captured:
`sector_cycles_data.js`, `marketdata/sp500_heatmap.json`,
`basketdata/etf_pulse.json`, `basketdata/vol_sentiment.json`, the extracted
`#sc-flows` server-rendered fragment, and (added after the D1 follow-up lane)
`marketdata/nasdaq_internals.json`. Hero context / `data-regime` /
`generated_utc` come from the R3A `si_handoff.json` fixture — no duplicate.

## 2. Reference architecture (frozen)

Single self-contained artifact assembled deterministically by
`build/build_reference.py`: shell + six view partials + verbatim embedded data
registry + runtime shim + **verbatim `templates/si_workspace.js`** (byte-checked
at assembly). Runtime shim: fetch interception against the registry
(hit / recorded-not-executed), `data-ref-nav` route recorder (commission §19
mock navigation), quarantine drawer (lang/theme/access-state/fetch-fail +
recorder log), scroll-offset wiring (`scroll-margin-top` — the §14 required
behavior; the router's `scrollIntoView({block:'start'})` honors it).
Time Machine episode/chunk fetches are RECORDED-not-executed (manifest is
fixture-real; the deferred-fetch contract is demonstrated by the recorder).
`REF.parseJSON` tolerates Python-serialized bare `NaN` in
`basketdata/action_board.json` — parse-only; embedded bytes verbatim.

## 3. Principal Design Lead — ratified with two disclosed chrome divergences

- **State Ledge** spatial authority grammar (present only on Overview and
  Confluence), token-level color rationing, tertiary `.r3-tag` for the Map
  `reco` CONFLICT field, names-never-ellipsize: ratified as binding lane law
  (`build/DESIGN_SYSTEM_SPEC.md`).
- **APPROVED divergences from production chrome** (both CSS-only, inside the
  R3A design brief §5 mobile grant, both repairing the VTC-002 hidden-offscreen
  defect class): (a) labels kept on the 768–1100 rail; (b) ≤767 six-tab
  horizontal scroller replaced by a 3×2 grid (production pushes Explore and
  Confluence — an Action view — off-edge at 320–390). **R3C must adjudicate
  both for production.**
- Skeleton-free loading (commission law) reconciled against master §9.12 by
  keeping reserved geometry, dropping animation. `--fs-display` deliberately
  unused. Both recorded, approved.
- Shell integration drops (specimen self-bootstrap toggles, placeholder
  banner, fake as-of stamp): approved — each avoided introducing a dual source
  of truth or misrepresenting real data/freshness.

## 4. Lane rulings — D1 (Overview + Confluence)

Approved: scoped `.st-head` sixth state ink (existing `--ink-down` rung;
Headwind needs a negative rung); Confluence full table default-capped at 8 with
counted reveal and per-selected-lane 8-cap (production default renders more —
disclosed composition delta, journeys preserved); CSS-drawn marks replacing
production Unicode `▾ ▴ ↗ →` (wording verbatim); board legend truncated to its
two live sentences (a legend describing undrawn marks is false); `dispshort()`
retained; `sc-top` id NOT minted (A7 seam (c) recorded, not repaired);
`+N more` resolved to in-page `#actnow-section` (its production target);
capture-phase trace handler + `REF.nav` fallback (quarantine-lawful);
Bottoming Watch constant-chip dedup to the strip foot with honest "All N rows:"
scope; 44px targets bought with padding+negative margin.
New display copy (→ copy ledger): authored ZH twin for the thin-data dot
(production's is an EN-only `title=`, which house law bans), and empty-lane
copy for the four Confluence buckets production ships no list copy for.
Cap findings bound and cited: `forming.slice(0,4)` (`subsectors.js:302`),
`avoid.slice(0,8)` (`:307`), `PICKS_CAP=12` (`:318`).

## 5. Lane rulings — D2 (Map + Moving)

- **RVX_Q stance strings not rendered** (production tooltip's "Hold / add",
  "Take profits", "Watch", "Avoid" halves): APPROVED as de-amplification under
  A3's do-not-amplify — action vocabulary on a context surface, not an
  enumerated ledger row; quadrant names/subtitles verbatim. Explicitly flagged
  for the fresh Data/Authority critic; trivially revertible.
- **Ranked list defaults to production's `slice(0,10)`** over the spec's ≤8:
  approved — observed production behavior outranks a composition guideline.
- **Desk Watch absent-vs-empty distinction**: approved — uses only production's
  recorded strings, makes the binding matrix's own failure state reachable, and
  answers commission §24 "null→zero collapse". Production's conflation (outage
  reads as calm) filed for R3C as a recommended repair.
- Axis domain widened only beyond production's clamp floor (no value/rank/
  quadrant change); `SECTOR_CYCLES` action-register fields (`signal`,
  `timing_state`, `action`, `stance`, `hazard`) NEVER rendered.
- Rank-note clarifier approved and added ("Rank across all groups /
  排名范围：全部分组") — copy ledger.

## 6. Lane rulings — D3 (Money + Explore)

Approved: achromatic measures with printed thresholds (production's tinted
verdict bars violate the context color law this reference exists to prove);
style-tilt legs and leadership drivers as named lists (chip-budget law);
production's decorative emoji dropped (§18); "N% stretched" chip dropped (the
producer's own caveat states it in plain words — one fact, said once);
Time Machine tier labels from manifest date ranges (no Unicode arrow); category
filter in a labelled `<details>` (summary always names the active state);
inert `@layer` fallback; two achromatic literals mirroring heatmap.js; 4×4
stroke identity replacing 14 hardcoded hexes (legend doubles as the chart's
text equivalent); refetch-on-activation only after failure; sync registry reads
vs fetched heatmap (matches production boot semantics). Inline-SVG chart chosen
over embedding `lightweight-charts.js` (same data, production's own rebase
transform cited, theme-token-native, 200%-zoom-safe). New ZH copy (manifest
notes, section subs, empty-state why lines) → copy ledger. `ai_watch` is
`null` in the fixture: production's absence path renders; the A8 "Model
analysis / 模型分析" branch is live code — a fixture carrying the field is the
only way to show it visually (recorded in the state matrix).

## 7. D1 follow-up — Confluence supporting organs

Ruling that triggered it: capability preservation outranks the L1 budget; the
three un-composed RETAIN organs (Leadership running-&-coiling, sector backdrop
rollup, Nasdaq internals) return behind `.r3-disc` disclosures in the grammar's
own EVIDENCE slot. Approved on delivery, including two disclosed
never-fires-on-this-fixture fallback upgrades (ZH label falls back to EN
instead of a raw slug; unmapped enum prints the raw producer value instead of a
bare em-dash) — both doctrine-driven, both dead code on this fixture, both
disclosed rather than silent. Nasdaq internals initially rendered nowhere
(artifact absent from fixture+supplement); ruled a lawful supplement extension
(§1 above) since `marketdata/nasdaq_internals.json` exists at the epoch commit
(4,004 bytes).

## 8. Production baseline evidence (RULING after live-capture blocker)

Live capture of the six baseline views is impossible anonymously: production
401-gates `si_workspace.js` and all non-overview view assets for anonymous
visitors (`x-regwall: deny`, `authentication_required`, signin_url) — only the
baked Overview slice renders. This RESOLVES the R3A access contract's open GAP
("ungated = config grep, not live curl") in the direction of a site-wide
anonymous regwall in FRONT of the single premium tier gate; it does not
contradict any R3A binding (the tier-gate semantics for signed-in readers are
unchanged). Signing in is prohibited for worker lanes. Ruling: baselines are
captured from the COMMITTED production bytes at a pinned commit, rendered
locally (the VPS serves the committed `site/` tree), with method + commit in
`production/PROVENANCE.md`; the one live anonymous capture is retained as
`prod-live-anon-overview.png` — the receipt of the regwall finding. The finding
itself is R3C input, not something this cycle repairs.

## 9. Scope calls carried in continuity

- Four predecessor findings targeting `intelligence_hub.html`/LENS (PRC-008,
  VTC-009, VTC-010, DAC-008) are out of this cycle's route; carried as
  `CARRIED_BLOCK` with ownership deferred to a future LENS RIG cycle — not
  silently dropped.
- DAC-005 is compound: only its tab-order sub-claim is OVERRIDDEN (refuted by
  ADJUDICATIONS §A4); the state-label and coverage-wording sub-claims stay
  alive through the SC-065/SC-077 known-defect RETAIN rows.
- R2's cycle issued no `verdict.yml` (review halted at four BLOCKs), so the
  checker's mandate derivation is empty; continuity closure was hand-authored
  over all 39 predecessor findings with self-referencing predecessor refs —
  disclosed in the file header.

## 10. Standing prohibitions honored

No production file modified. No `approval.yml` produced. No self-issued
verdict. R3A attack suite untouched and green. `R3B_HANDOFF_DRAFT.md` (in-pack,
DO-NOT-START) not used as commission — the Sol-issued commission supersedes it
(operator instruction, 2026-08-21).

## 11. Freeze-pass adjudications (2026-08-21)

- **QA3/QA-v1 independent pass**: its Gate-4/5 failures reproduced the PRE-fix
  build and are closed by the fix wave (`FIX_VERIFICATION.md`); its contest of
  QA2-07 matches the fix lane's non-repro — the contract-correct fetch-based
  hydrate stands. Its four NEW items (QA3-01 producer +N-more line, QA3-04
  triple CSS emission/offset shadowing, QA3-08 boot-time fail arming, QA2-10
  completion) plus the QA3-05 destination check were all closed in the QA3
  closure commit (`afc6c8e2394c`) with production-cited determinations:
  production's +N-more line is `.muted.sm`, never `.pg-more` (hydrate strips
  only the sign-in tease — mirrored); heatmap `layoutList()`/`hm-mrow` IS the
  Money per-stock mechanism (503-name Browse-the-names disclosure added,
  `stock_url`-faithful). QA3-02 (gated stand-aside stacks two disclosures) is
  production-shaped (both lines render in production's gated state) — recorded,
  no change. Map having no fetch-dependent content (build-time bake only) is a
  faithful production property, not a fail-test gap.
- **Continuity compound findings**: the builder's treatment RATIFIED — five
  compound findings resolved for their Sector Central half with the LENS half
  explicitly disclosed unaddressed in the same note; MAC-007 honestly carried
  (no touch-dispatch harness in this cycle's evidence pack).
- **§25 taste review (orchestrator, seat of record after the Principal Design
  Lead's three-round pass)**: inspected the frozen candidate's primary crops —
  Overview/Confluence (Action tier), Money light (the historically weak
  quadrant), plus the lanes' 50+ working crops. First-screen hierarchy answers
  first; panel count within budget; whitespace deliberate; full names wrap and
  never truncate; charts prominent without outranking the answer; caveats
  deduplicated to section feet; chip budgets held; authority weight legible
  pre-linguistically (ledge present only on Action views — QA §7 masquerade
  PASS with zero `.st-*`/ledge selectors in context views); phone compositions
  are recompositions, not scales; dark and light are both deliberate art
  directions; styling institutional throughout. VERDICT: meets the §25 target
  ("credible as a flagship product from a billion-dollar institutional
  fintech company") — subject, as commissioned, to the four fresh critics.
- **Honest limits carried to the critics**: `ai_watch` null in fixture (A8
  label branch is live code, unprovable visually on this fixture);
  `n_thin>0` unobserved for Nasdaq/Russell; forming bucket empty everywhere
  (4-cap path unexercised); loading/partial states not capturable
  (state_matrix.md documents why); near-bottom deep-link targets land at the
  scroll ceiling (visible, not buried — §14 satisfied).
