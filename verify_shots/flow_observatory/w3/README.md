# Flow Observatory V2 — W3 visual evidence (repair round)

This checkout's `data/flow_observatory/observations.parquet` ledger is bootstrap-empty
(no guarded asia-close/US-nightly lane run has happened here — the ledger only advances
under `COLLECT_LANE=nightly`/`CN_LANE=asia`, spec §1/§5). The real rebuilt
`site/flow_velocity.html` therefore shows the honest "first tracked session" state for
every row, not the new age/revision UI.

`_fv_w3_fixture.html` is the REAL `templates/flow_velocity.html.j2` rendered (same
Jinja env — `td`/`tr` i18n globals, `QUADRANT_LABELS`/`STATUS_WORD` — as
`scripts/build_flow_velocity` and the test suite) against the REAL rebuilt
`site/flowdata/desk.json`, with a small W3 fixture overlay:

- **`cn_autos`** ("Autos & NEV Makers"): `state_started=2026-08-24`,
  `state_age_sessions=6`, `prior_state=true_distribution`, `state_note=None` — the
  ordinary, non-frozen age-chip form.
- **`cn_soe_value`** ("SOE Blue Chips"): `state_started=2026-08-31`,
  `state_age_sessions=1`, `prior_state=true_accumulation`,
  `state_note="age frozen (stale source)"` — this is the shape the B3 repair exists
  for: an all-stale-baseline session that used to compute `state_age_sessions=None`
  forever (the age chip never rendering) now renders `age=1` with the ❄ marker, exactly
  as `tests/test_flow_observatory_history.py::test_all_stale_baseline_age_renders_as_one`
  proves at the data layer.
- **`change_summary.source_revisions`**: one fixture revision receipt on `cn_defense`
  ("Defense & Aerospace") — the exact shape `build_v2`/`compute_changes` emit once the
  ledger has depth ≥2 sessions and a correction lands (proven directly by
  `tests/test_flow_observatory_history.py`; this is the UI's own rendering of that same
  data shape).

Regenerated for the repair round after: the ZH age-caption short form (NIT12/THEME —
"状态第{n}日", replacing "本状态第{n}个交易日", so `.fv-age`'s `white-space:nowrap` never
wraps at any width tested); the light-theme `.fv-age` color fix (`var(--muted)`, was the
near-invisible `var(--faint)`); and the authored LIGHT treatment for `.fv-chg-row--revision`
(previously unauthored — dark's rule was rendering unexamined in light too, the exact
TP-0 bare-token-swap failure).

Captured via Playwright Chromium (`/private/tmp/pwvenv`, headless), `reduced_motion:
"reduce"` plus a JS pass forcing `opacity:1`/`.is-in` on every `.fv-reveal` section (same
W1/W2 method — the page's own IntersectionObserver reveal otherwise leaves off-screen
sections at `opacity:0` for a screenshot taken without a full scroll pass), against
`site/` served statically (`python3 -m http.server 8931 --directory site`,
`.claude/launch.json` `site-static`) with the fixture HTML copied in as a sibling file
so its relative `theme.js`/`product-nav-icons.css` references resolve — the temp copy is
never committed. `theme`/`lang` are set via `localStorage` before load (the page's own
boot script reads them). Capture script: throwaway, not committed (this README is the
durable record).

## Crops (dark/light × EN/ZH × 1440, + one 390 mobile crop per theme — THEME evidence-matrix completion)

| file | shows |
|---|---|
| `theme_table_age_chip_dark_en_1440.png` | Theme flow board, dark: "Autos & NEV Makers" → **session 6 in this state**; "SOE Blue Chips" → **session 1 in this state ❄** (B3-fixed all-stale-baseline form) |
| `theme_table_age_chip_dark_zh_1440.png` | Same region, ZH: **状态第6日** / **状态第1日 ❄** — the new short form, one line, no wrap |
| `theme_table_age_chip_light_en_1440.png` | Same region, light theme — hairline white-material cards, age caption in `var(--muted)` (legible against the paper canvas, not the near-invisible `--faint` the pre-repair rule used) |
| `theme_table_age_chip_light_zh_1440.png` | Light + ZH short form together |
| `theme_table_age_chip_dark_en_390.png` | Mobile (390px) crop, dark — both age chips still legible at the narrow breakpoint |
| `theme_table_age_chip_light_en_390.png` | Mobile (390px) crop, light |
| `changed_revision_row_dark_en_1440.png` | "What Changed Today", dark: **Defense & Aerospace: 2026-08-30 data revised** — the restrained 2px/55%-blue command-center left rule (unchanged dark treatment) |
| `changed_revision_row_dark_zh_1440.png` | Same row, dark + ZH: **军工航天：2026-08-30数据已修正** |
| `changed_revision_row_light_en_1440.png` | Same row, LIGHT — the newly-authored idiom: a visible 7% `--blue` paper tint band, a FULL-STRENGTH (not color-mixed) 3px blue left rule, and full-weight ink body text — reusing `.fv-src--revised`'s own light mechanism, a genuinely different material treatment from dark's glow, never a bare token swap |
| `changed_revision_row_light_zh_1440.png` | Light + ZH: **军工航天：2026-08-30数据已修正** with the same light idiom |
| `changed_revision_row_dark_en_390.png` | Mobile (390px) crop, dark |
| `changed_revision_row_light_en_390.png` | Mobile (390px) crop, light — tint band + full-strength rule still read clearly at the narrow width |

`console_errors.json`: `{}` (empty error list) for all six page loads (dark/light × en/zh
at 1440, dark/light at 390) — zero console errors in any capture.

All twelve crops were opened and read directly (not merely generated) before this PR was
returned — see the worker's EVIDENCE section for what was checked in each.

## What each new element is

- **State-age chip** (`.fv-age`, under the quadrant chip): pinned EN "session {n} in this
  state" / ZH "状态第{n}日" (spec §2, ZH form updated by the repair round — NIT12/THEME).
  LENS (`data-tip-en`/`data-tip-zh`, the site-wide `[data-tip-en]` popover,
  `templates/theme.js`) carries prior state + the started date. `state_note == null`
  renders the plain age; `"first tracked session"` renders the italic `.fv-age--new`
  form; `"age frozen (stale source)"` appends a ❄ marker. Age semantics are now the B3
  pinned rule (`engine/flow_observatory/history.py::_state_from_series`): onset is the
  first ledger row in the current state, stale-stamped or not; age is 1 + the count of
  non-stale sessions in the run, floored at 1 — an all-stale baseline renders `age=1`
  forever after the very first session, never a permanent `None`.
- **Revision row** (`.fv-chg-row--revision`, "What Changed Today"): pinned EN "{name}:
  {session} data revised" / ZH "{name}：{session}数据已修正" (spec §2, unchanged),
  rendered via the shared `chg_row()` macro alongside transition/rank-mover/quality rows.
  LENS carries old→new quadrant/status/vel detail. `engine.flow_observatory.changes.
  compute_changes` excludes the same entity from `transitions[]`/`rank_movers[]` for that
  build (spec §3 test 9 — a correction never also reads as a duplicate transition; S7
  narrows this suppression to same-entity-same-from/to only).

Both elements reuse the page's EXISTING token-driven idiom family
(`.qchip`/`.rk`/`.fv-src--revised`) — no new palette, no runtime-authored stylesheet.
Dark keeps its original restrained command-center treatment (a bare inherited rule was
NEVER authored differently for dark, so nothing changed there); light now has its OWN
explicit `html[data-theme="light"]` rules for both elements (the repair this evidence set
exists to prove), per `research/MASTER_PRODUCT_DESIGN_SYSTEM_V1.md` / TP-0.
