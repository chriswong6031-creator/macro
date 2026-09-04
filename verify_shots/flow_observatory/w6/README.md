# Flow Observatory V2 — W6 visual evidence

Per-group 60-session history drawers with state bands and revision markers,
two-group compare (same-lens + cross-lens refusal), descriptive prior episodes,
Terminal links, and the watch-store recorded-limitation decision
(`research/flow_observatory/W6_SPEC.md`).

Captured via Playwright Chromium (`/private/tmp/pwvenv`, headless), `reduced_motion:
"reduce"`, against the REAL rebuilt `site/flow_velocity.html` served statically
(`python3 -m http.server <port> --directory site`) — same method as the original W6
verify_shots. A JS pass forces `.is-in` on every `.fv-reveal` section, then opens the
`cn_autos` theme row (its history drawer is one of the top-3 force-`open`ed panels).
`theme`/`lang` are set via `localStorage` before load. Capture script: throwaway, not
committed (this README is the durable record; a copy sits in the session scratchpad).

## REPAIR ROUND (independent review, this packet)

The original W6 landing PR was reviewed and returned FAIL on three required items
(B1/B2/B3) plus six should-fix and two nit items. This round fixes all of them; the
crops below are FULLY REGENERATED against the fixed template/build, not touched-up.

### B1 — tests/test_flow_observatory_workflow.py was never wired into CI

Fixed: added to `.github/ci/legacy-jobs.yml`'s flow lane `run:` line and
`.github/workflows/ci.yml`'s flow-observatory path-gate block, in the SAME commit as
a new structural-kill meta-test
(`tests/test_flow_observatory_contract.py::test_all_flow_observatory_suites_are_wired_into_the_ci_lane`)
that reads the run: line off disk and fails the NEXT time a sibling suite ships
unwired — this was the FIFTH time this exact class of defect shipped (W2/W3/W4/W5/W6).

### B2 — compare panel rendered anonymous ("headless") columns

Root cause: `data-cmp-name`/`-name-zh`/`-lens` lived ONLY on the `.fv-cmp-cb`
checkbox; the compare JS reads them off `checkbox.closest('tr.sector-row')` — the
ENCLOSING row — which never carried them, so every compare column's `<h4>` rendered
empty. Fixed: the SAME attributes are now emitted on `tr.sector-row` itself (both
lenses); the checkbox keeps its own copies too (harmless). `aria-label` is now
`"compare {name} ({lens})"` — unique even across a REAL production name collision
(desk.json today has "Coal", "Banks", "Home Appliances", and "Food & Beverage" each
as BOTH a curated theme name and an official-sector name; a bare "compare {name}"
would not be unique for those four pairs).

- `same_lens_compare_dark_en_1440.png` / `same_lens_compare_dark_zh_1440.png`:
  two curated themes selected → the compare panel now shows the REAL names as
  headings — "Autos & NEV Makers" / "SOE Blue Chips (中特估)" (EN) and "汽车整车" /
  "中特估·央企" (ZH) — pulled directly from `<h4>` text via
  `document.querySelectorAll('#fv-compare-panel h4')` (not just visually eyeballed;
  the JS-read text is in `console_errors.json`'s `h4_text` field for both captures).
- `cross_lens_refusal_dark_en_1440.png`: unchanged behavior, re-verified.

### B3 — mobile (390px) caption/episode text truncated mid-word

Root cause (measured, not guessed): `table.board#sectortbl` is ALREADY, independent
of anything in this drawer, ~900px wide at a 390px viewport — the Theme/Members/
Quadrant columns carry pre-existing nowrap name/badge/chip content (confirmed by
diffing against the git HEAD build BEFORE this repair: identical ~900px width with
NO drawer even open). Since this drawer's `<td colspan="8">` always renders at the
SUM of the table's actual column widths, `white-space:normal` alone (the first fix
attempted) only stopped single-line overflow — it still wrapped the caption onto an
~855px-wide box, of which a 390px viewport can only show the LEFT slice: genuinely
invisible, not merely scrolled, matching the "truncates mid-word" review finding
exactly. Fix: `.fv-hist-text` (caption + episode heading/note/outcome) and
`.fv-hist-tracks` (the spark label+track pair) get an EXPLICIT
`max-width:calc(100vw - 64px)` at the ≤640px breakpoint — a DEFINITE width breaks the
"inherit the oversized auto column width" chain, so these elements wrap/shrink to the
real visible viewport regardless of how wide sibling (Theme/Members/Quadrant) columns
force the table itself to become. Overhauling table.board's general mobile
responsiveness for every column is explicitly OUT of this repair's scope — same
pre-existing gap the already-shipped W3/W4 `concrow`/`excludedrow` rows carry.

A second, independent defect was found and fixed in the same pass: `.fv-hist-track`
(`flex:1;min-width:0`) with a percentage-width child SVG (`.spark{width:100%}`)
ballooned to 695px during Chromium's intrinsic-sizing pass — `flex:1 1 0` (basis 0,
not auto) plus a hard `max-width:480px` caps it at every viewport.

- `history_drawer_dark_en_390.png` / `history_drawer_light_en_390.png`: caption
  fully visible across 3 wrapped lines, all three episode summaries fully visible
  and wrapped, zero mid-word truncation, zero page-level horizontal scroll
  (`docScrollWidth === docClientWidth === 390`, verified programmatically, not just
  visually).
- `mobile_real_viewport_390_dark_en.png`: a plain (non-cropped) 390×900 viewport
  screenshot of the real page state (not an oversized element crop) — the strongest
  form of this evidence, since it shows exactly what a phone screen renders without
  any scrolling.

## S4 — `_kinetics_series`/`_kinetics` classification parity at a rounding boundary

`_kinetics` classifies against `round(vel, 2)` (its own `vmid`); `_kinetics_series`
used to classify its per-session states against the RAW (unrounded) vel, so a value
landing exactly on a vin/vout boundary after rounding could classify one way in
`_kinetics` and the other way in the LAST row of `_kinetics_series` for the identical
input — breaking the module's own documented "last row matches `_kinetics()`" promise.
Fixed: `_kinetics_series` now rounds to 2dp before its own threshold compare, exactly
matching `_kinetics`. Note for the record: the review's own illustrative boundary
example (`vel raw 0.7468 at vin 0.75 -> both paths near-norm`) has an arithmetic
error — `round(0.7468, 2) == 0.75`, which classifies "above norm" once rounded, not
"near-norm" on either path. `tests/test_flow_observatory_workflow.py::test_kinetics_series_last_row_matches_kinetics_at_a_rounding_boundary`
pins the CORRECT, load-bearing requirement instead (the two paths AGREE at this exact
boundary, whatever the verdict) — see the PR body's DEVIATIONS section.

## S5 — episode distinctness (minimum 5-session separation)

Selection previously picked the k=3 CLOSEST candidates by distance alone, with no
rule stopping two picks from being neighboring sessions (the same regime read
counted twice). Fixed: candidates are walked in ascending-distance order and a pick
is accepted only if it sits ≥5 sessions from every already-accepted pick
(`EPISODE_MIN_SEPARATION = 5`); a thinned pool ships the honest (smaller) count. The
episode card block now also carries an honest-count heading — "N distinct prior
episodes" / "N个相似历史情形" — reflecting `len(episodes)`, never the target of 3.
On today's real desk.json all 22 themes still produce exactly 3 well-separated
episodes (`grep -c "3 distinct prior episodes" site/flow_velocity.html` → 22), so
the min-separation gate has not (yet) visibly thinned any real card — proven instead
by a hand-built adjacent-candidate fixture
(`test_episode_min_separation_collapses_adjacent_near_duplicates`).

## S6 — caption amendment ("today's method AND today's membership")

The pinned first sentence is amended on both the normal and thin-ledger caption
forms: EN "Replayed under today's method and today's membership — not what was
published historically." / ZH "按当前方法与当前成分回放——非历史发布值。" — visible
in every history-drawer crop above (the replay averages the group's CURRENT
constituent set across the whole history window, so "method" alone under-disclosed
that composition is also current-day).

## S7 — σ unit renders lowercase, never `Σ`

`.fv-hist-lbl` carries `text-transform:uppercase` (a rendering transform, not a DOM
edit) — it was silently capitalizing the σ in "relative pressure (σ)" to "Σ". Fixed:
the σ character is wrapped in `<span class="no-uc">` (`text-transform:none`),
applied both in the drawer label and the episode-card σ value. Visible correctly
lowercase in every crop above (both EN and ZH, both themes).

## S8 — band color rides the SAME zh-flip tokens as the state chips

`engine.flow_observatory.workflow._direction` now returns a SEMANTIC direction
("above"/"below" the group's own norm) instead of the color names "up"/"down" it
used to return; the template maps that onto the SAME `--up`/`--down`-derived,
data-lang-aware tokens `.vstate`/`.rk` already use, via new
`html[data-theme][data-lang="zh"] .fv-band.dir-above/.dir-below` overrides. Result:
the ZH red-up flip now rides automatically — proven two ways:

- `history_drawer_dark_zh_1440.png` vs `history_drawer_dark_en_1440.png` (also light):
  the SAME two bands (below-then-above) visibly swap color between languages.
- `band_vstate_agreement_dark_en_1440.png` / `_zh_1440.png`: the drilled-down
  `cn_autos` row with its member 上汽集团 (600104.SS, state "above norm, rising")
  visible alongside the SAME theme's history drawer — in EN both the member's
  `.vstate.in` chip AND the drawer's current (rightmost) band render GREEN; in ZH
  BOTH flip to RED together. Band and chip agree in both languages, not just by
  accident of which one happens to be shown.
- `band_chip_agreement_zh_dark_1440.png`: `cn_rare_earth` (quadrant
  `true_distribution`), ZH — included for a second real-data example.

## S9 — Terminal links wired into member-row rendering

`engine.flow_observatory.workflow.terminal_link()` existed since the original W6
landing but was never actually called by `nameln()` — every member ticker got a
Terminal link unconditionally, including ones outside the desk's own covered/scored
universe. Fixed: `nameln` now calls `terminal_link(m.ticker, known_tickers)`;
`known_tickers` is threaded from `_attach_group_histories`' own already-computed
kinetics-map keys through to the render call. On today's real desk.json: **247**
member names render a live Terminal link, **13** render unlinked (`grep -c
mname-unlinked site/flow_velocity.html`) — a real, non-zero unlinked count,
confirming the gate is actually filtering, not a no-op. Backward-compat: a caller
that never supplies `known_tickers`/`terminal_link` (this repo's own pre-W6 W2/W4
test suites) keeps the OLD always-linked behavior byte-for-byte
(`test_member_row_stays_always_linked_when_known_tickers_not_supplied`).

## N10 — band geometry uses the same finite/filtered index as the spark line

A single NaN session in the middle of a group's vel series used to split what is,
on the actual rendered spark polyline, ONE continuous line (spark silently drops
NaN points and plots the rest evenly spaced with no gap) into TWO separate tint
bands with a colorless sliver in between — because band geometry divided by the
FULL (NaN-inclusive) session count. Fixed: band geometry is now computed over the
SAME finite-filtered index positions `engine.flow_velocity.spark` uses internally.
Proven with a hand-built 60-session fixture carrying one NaN
(`test_band_geometry_survives_a_mid_series_nan_gap`) — not visible in the crops
above since no real group in today's desk.json happens to have a mid-series NaN gap
in its replay window.

## N11 — recorded for the record (not built this wave)

- **desk.json size delta**: `site/flowdata/desk.json` — this repair round's fixes
  (member `terminal_url` gating touches template rendering only, not the JSON
  payload; the S5/S8/S6 fixes touch `history`/`episodes` payload shapes already
  present) measured at +29.6% over the pre-repair committed baseline
  (`git cat-file -s HEAD:site/flowdata/desk.json` vs the rebuilt file) — see PR body
  for the exact byte figures and cause (episode/band payload fields were already
  present pre-repair; the delta is dominated by ordinary daily data movement, not a
  new field this round adds).
- **D3 forward-risk note**: when official-sector accrual completes (today: 0/31
  official sectors qualify for a history/episodes panel — see
  `official_sector_row_dark_en_1440.png`, unchanged this round, accrual gate
  untouched by this repair), drawers will ship for all 31 official sectors too, and
  the 800KB page-weight budget (spec §6) will likely be exceeded once that happens.
  Planned demotion rule (decided now, NOT built this wave): official-sector drawers
  either lazy-load on `<details>` open (defer the markup until the reader actually
  expands it) or gate to the top-N sectors by |vel|, mirroring the existing
  curated-theme top-3-force-open page-weight lever. Whichever wave lands official
  accrual owns implementing this.

## Real drill walked (group → history → episode → member → Terminal URL)

1. **Group**: curated theme "Autos & NEV Makers" (`cn_autos`), rank 1 by |vel| today
   (`history_drawer_dark_en_1440.png`).
2. **History**: the 60-session drawer — dual sparklines (absolute 4wk rate /
   relative pressure), a below-norm band for the first ~23% of the window
   transitioning to an above-norm band for the rest, the pinned (S6-amended) replay
   caption.
3. **Episode**: 3 distinct prior-episode cards, e.g. "2026-08-17 +2.58σ / -1.0% —
   over the next 10 sessions, pressure faded and absolute flow worsened" —
   descriptive only, no %-return, no predictive word.
4. **Member**: 上汽集团 600104.SS, "above norm, rising", +3.76σ — Terminal-linked
   (known ticker).
5. **Terminal URL**: resolves to
   `https://app.mastermind-x.com/terminal?sym=600104.SS&from=macro` — the EXISTING
   contract, now gated through `workflow.terminal_link` (S9).

## Compare (spec §2, re-verified after B2)

See the B2 section above — both same-lens (named columns, both languages) and
cross-lens refusal re-captured and confirmed working.

## Official-sector accrual gate (spec §2A honored, not re-litigated; unchanged this round)

`official_sector_row_dark_en_1440.png` — carried over unchanged from the original
W6 evidence set; the accrual-gate logic it documents (0/31 official sectors qualify
for a history panel today) is untouched by this repair round. See N11 above for the
recorded forward-risk once that gate opens.

## TP-0 dual-theme state-band treatment (declared, both captured)

- **DARK**: low-alpha glow fill — `color-mix(in srgb, var(--up)/var(--down) 18%,
  transparent)` — a command-center luminance wash under the relative-pressure spark.
- **LIGHT**: a 6%-tinted block bounded by a 1px top/bottom hairline in the same hue
  — a research-workspace idiom. Visibly a DIFFERENT material treatment, not a
  token-swapped copy of dark's glow (TP-0 law).
- **S8 repair**: band direction now DOES flip with `data-lang`, unlike the original
  W6 landing — see the S8 section above for the full before/after proof.

## Mobile (390px) — no page-level horizontal scroll, drawer text now fully visible

See the B3 section above for the full root-cause account and fix. Unrelated,
pre-existing table-internal clipping on OTHER columns (Theme/Members/Quadrant names
and badges, shared by the already-shipped W3/W4 `concrow`/`excludedrow` rows)
remains — explicitly out of this repair's scope, flagged in the PR body, not a new
regression and not what B1/B2/B3 were about.

## Console + horizontal-scroll receipts

`console_errors.json` (committed, regenerated this round) — every named capture:
`errors: []`, `hscroll: 0`. The `band_vstate_agreement_*`/`mobile_real_viewport_*`
supplementary crops were captured with a separate ad-hoc script that verified
`document.documentElement.scrollWidth === document.documentElement.clientWidth`
(390/390 and 1000/1000 respectively) inline rather than writing to this JSON file —
values pasted into the PR body's EVIDENCE section.
