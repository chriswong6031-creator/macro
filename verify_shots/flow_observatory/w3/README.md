# Flow Observatory V2 — W3 visual evidence

This checkout's `data/flow_observatory/observations.parquet` ledger is bootstrap-empty
(no guarded asia-close/US-nightly lane run has happened here — the ledger only advances
under `COLLECT_LANE=nightly`/`CN_LANE=asia`, spec §1/§5). The real rebuilt
`site/flow_velocity.html` therefore shows the honest "first tracked session" state for
every row, not the new age/revision UI.

`_fv_w3_fixture.html` is the REAL `templates/flow_velocity.html.j2` rendered (same
Jinja env, same `QUADRANT_LABELS`/`STATUS_WORD` globals as `scripts/build_flow_velocity`
and the test suite) against the REAL rebuilt `site/flowdata/desk.json`, with a W3 fixture
overlay: two theme rows given `state_age_sessions`/`state_started`/`prior_state` (one
normal, one `state_note="age frozen (stale source)"`), and one revision receipt added to
`change_summary.source_revisions` — the exact shape `build_v2`/`compute_changes` emit once
the ledger has depth ≥2 sessions and a correction lands (proven directly by
`tests/test_flow_observatory_history.py`; this is the UI's own rendering of that same
data shape). Captured via headless Chromium (Playwright, `pwvenv` in the worker-browser
runtime) against `site/` served statically (`python3 -m http.server 8931 --directory
site`, `.claude/launch.json` `site-static`), `reduced_motion="reduce"` plus a JS pass
adding `.is-in` to every `.fv-reveal` section (same W1/W2 method — the page's own
IntersectionObserver reveal otherwise leaves off-screen sections at `opacity:0` for a
region clip taken without a full scroll pass).

## Crops (dark/light × EN × 1440 — spec §0.5 minimum)

| file | shows |
|---|---|
| `theme_table_age_chip_dark_en_1440.png` | Theme flow board, dark: "Autos & NEV Makers" → **session 6 in this state**; "SOE Blue Chips" → **session 2 in this state ❄** (frozen — stale source) |
| `theme_table_age_chip_light_en_1440.png` | Same region, light theme — hairline white-material cards, age chip in muted ink, contrast preserved |
| `changed_revision_row_dark_en_1440.png` | "What Changed Today", dark: **Defense & Aerospace: 2026-08-30 data revised** with the blue revision-row rule |
| `changed_revision_row_light_en_1440.png` | Same row, light theme |

`console_errors.json`: `{"dark": [], "light": []}` — zero console errors in either capture.

## What each new element is

- **State-age chip** (`.fv-age`, under the quadrant chip): pinned EN "session {n} in this
  state" / ZH "本状态第{n}个交易日" (spec §2). LENS (`data-tip-en`/`data-tip-zh`, the
  site-wide `[data-tip-en]` popover, `templates/theme.js`) carries prior state + the
  started date. `state_note == null` renders the plain age; `"first tracked session"`
  renders the italic `.fv-age--new` form; `"age frozen (stale source)"` appends a ❄ marker
  and reuses the FROZEN (unincremented) age number (spec §3 test 6).
- **Revision row** (`.fv-chg-row--revision`, "What Changed Today"): pinned EN "{name}:
  {session} data revised" / ZH "{name}：{session}数据已修正" (spec §2), rendered via the
  new shared `chg_row()` macro alongside transition/rank-mover/quality rows. LENS carries
  old→new quadrant/status/vel detail. `engine.flow_observatory.changes.compute_changes`
  excludes the same entity from `transitions[]`/`rank_movers[]` for that build (spec §3
  test 9 — a correction never also reads as a duplicate transition).

Both reuse the page's EXISTING token-driven chip idiom (`.qchip`/`.rk`, already proven
dark+light in the W1/W2 evidence) — same `var(--faint)`/`var(--muted)`/`var(--blue)`
tokens, no new palette, no runtime-authored stylesheet.
