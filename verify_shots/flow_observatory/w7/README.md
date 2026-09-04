# Flow Observatory V2 — W7 evidence (product-learning telemetry)

`research/flow_observatory/W7_SPEC.md` — nine typed events through the EXISTING
first-party `/api/collect` beacon (`templates/theme.js`'s `window.mmTrack`). This wave
adds **no visible UI or copy** (proved by
`tests/test_flow_observatory_workflow.py::test_w7_no_banned_vocabulary_and_visible_text_is_byte_identical_to_pre_w7`,
a byte-for-byte visible-text diff against the pre-W7 committed template), so the
evidence here is a beacon-stubbed interaction crop + the actual captured payloads —
not a dark/light/EN/ZH design matrix (there is no new art direction to prove).

## Repair round (PR #6815 independent review — this refresh)

An independent review of the first W7 pass returned FAIL:

- **B1** `trust_open` was wired to a bare `click` listener, but the LENS controller
  (`templates/theme.js`) opens a tip's popover on `pointerover` (desktop hover),
  `focusin` (keyboard tab), or — on touch — its own `click` handler, which a
  sheet-mode scrim can retarget away from the chip entirely before it ever reaches a
  page-level delegated `click` listener. Net effect: a genuine hover-only open on
  desktop emitted nothing, and mobile emitted nothing at all.
- **B2** `watch_note_view` measured accidental clicks on a static, always-visible
  paragraph with no LENS tip to open.
- **B3** the aggregate `__all__` row's `group_drill` payload carried `lens: null`
  instead of the spec's reserved `"aggregate"` value.
- Privacy comment overstated ("group ids and lens names only" while `terminal_out`
  carries a ticker in its `id` field).

Fixed in `templates/flow_velocity.html.j2`'s W7 block: trust_open now listens on
delegated `pointerover`/`focusin`/`pointerdown` scoped to `.fv-src[data-ev]` (never
click); watch_note_view moved onto the same `IntersectionObserver` used for
`episode_view` (impression, not click); the `__all__` row now carries
`data-cmp-lens="aggregate"`; the dedup key became `ev|lens|id` (N2); delegated
handlers guard `e.target && e.target.closest` (N3, matching theme.js's own idiom).
`config/growth_events.yml`'s `lens` property is now declared `enum:flow_lens|null` so
the five events that legitimately carry no lens conform to the registry instead of
silently violating an enum with no null allowance. Full per-item detail, source
citations, and the source-level pytest suite are in the PR body/EVIDENCE.

**Captured via Playwright Chromium** (`/private/tmp/pwvenv`, headless), `reduced_motion:
"reduce"`, against the REAL rebuilt `site/flow_velocity.html` served statically
(`python3 -m http.server 8931 --directory site`, `.claude/launch.json` config
`site-static`) — same method as the original W7 evidence, extended with genuine
`pointerover`/`focusin`/touch-`tap` interactions (Playwright's real input primitives —
`page.mouse.move()`, `locator.evaluate('el => el.focus()')`, `locator.tap()` under a
`has_touch: true, is_mobile: true` mobile context — never a synthetic `.click()`
standing in for a hover or a tap). `window.mmTrack` is overridden with a capturing stub
BEFORE each interaction (theme.js's own `loadMMAnalytics` never runs against
`localhost`, so nothing else defines it — this is exactly the "beacon blocked"
condition spec §0 gate 3 requires the page to survive identically under).

`changed_expand` required a separate fixture: the real live site's current
"what changed today" list has no >8-item day right now (the overflow `<details>` only
renders past 8 items), so it cannot be exercised against `site/flow_velocity.html` as
served today. `_fv_w7_fixture.html` is the SAME `_v2_with_everything()` fixture
`tests/test_flow_observatory_workflow.py` renders (a synthetic 9-transition change day),
saved to disk and probed the same way (temporarily copied alongside `theme.js`/`theme.css`
in `site/` to resolve relative asset paths, then removed — not a committed site file).

## Files

| file | shows |
|---|---|
| `trust_open_desktop_hover_dark_en_1440.png` | Genuine desktop HOVER (mouse moved onto the "A-share large-order flow" chip and held past the LENS controller's own open delay — no click) opens the EXISTING LENS popover ("Large & super-large order-size proxy — Tushare moneyflow_dc…"), proving B1's pointerover path against the real page. |
| `group_drill_interaction_dark_en_1440.png` | Unaffected by this repair (kept from the original evidence): clicking the "Autos & NEV Makers" theme row opens the existing accordion drilldown — `group_drill` and `episode_view` both still fire correctly under the new N2 (lens-keyed) dedup key. |
| `_fv_w7_fixture.html` | The `_v2_with_everything()` test fixture rendered to disk, used only to exercise `changed_expand` (see above) — not a `site/` artifact. |
| `captured_payloads.json` | The actual `window.mmTrack('flowobs', {...})` arguments captured for every genuine-open path (hover/focus/tap), `compare_run`, `changed_expand`, the `__all__` aggregate row's pre-open→close→reopen cycle, a direct dedup-key-with-lens probe, and the beacon-throw indifference re-proof. |
| `console_log.txt` | The stub's reconstructed `CAPTURED_BEACON_CALL <type> <json>` lines for every entry in `captured_payloads.json`, tagged with which capture they belong to — a stand-in for a real network trace, since a static `python -m http.server` render has no live `/api/collect` to send a real request to. |

## What the refreshed payloads prove (B1)

```json
{"meta":{"ev":"trust_open","lens":null,"id":"cn_large_order_proxy","sess":"2026-09-03"}}   // desktop hover
{"meta":{"ev":"trust_open","lens":null,"id":"sb_aggregate","sess":"2026-09-03"}}           // keyboard focus (fresh pageview)
{"meta":{"ev":"trust_open","lens":null,"id":"cn_large_order_proxy","sess":"2026-09-03"}}   // mobile 390 has_touch tap
```

- **Desktop hover → exactly 1 `trust_open` event**, with zero click ever involved —
  `trust_open.desktop_hover` in `captured_payloads.json`. Re-hovering the SAME chip a
  second time in the same pageview (`desktop_hover_second_hover_same_chip_no_new_events`)
  produced no additional `trust_open` — dedup still holds under the new `ev|lens|id` key.
- **Keyboard focus (fresh pageview) → exactly 1 `trust_open` event** — a
  `.evaluate('el => el.focus()')` call on a second trust-strip chip (`sb_aggregate`),
  the same DOM event (`focusin`) a real Tab keypress produces.
- **Mobile 390 `has_touch` tap → exactly 1 `trust_open` event** — `locator.tap()` under
  a `has_touch: true, is_mobile: true` context. The event fires on `pointerdown`, at the
  instant the touch lands, which is BEFORE the sheet-mode scrim can mount and retarget
  the tap's own synthesized `click` — so it is immune to the retargeting bug that made
  the pre-repair click-only listener fire zero times on mobile.
- **Zero `trust_open` events fire on none of these three paths** — every captured
  `trust_open` above corresponds 1:1 to a genuine hover/focus/tap on a real chip; no
  spurious extra `trust_open` appears anywhere in `captured_payloads.json`.
- **`history_open` entries interleaved in some captures are a pre-existing, unrelated
  browser behavior** (documented inline in `captured_payloads.json`'s `_note_...`
  field): the top-3 themes' history `<details>` render already-`open` server-side
  (`force_open`), and browsers queue one initial `toggle` event for a `<details open>`
  present at parse time — the W7 toggle listener (unchanged by this repair) fires on
  that queued event the first time any capture runs after load. Not specific to
  trust_open/B1.

### B2 — watch_note_view is now an impression, not a click

Not separately screenshotted (the note's rendered text is unchanged — this is a JS
wiring change only). Verified at the source level in
`tests/test_flow_observatory_workflow.py::test_w7_watch_note_view_is_an_impression_event_not_a_click`
(the shared impression `IntersectionObserver` now observes
`[data-ev="episode_view"], [data-ev="watch_note_view"]`) and confirmed live: the
`episode_view`/`group_drill` capture above shows the impression-based observer firing
correctly for the analogous `episode_view` case; `watch_note_view`'s own live capture
would require scrolling past the fold on the real page and is covered by the same code
path (identical observer instance, identical dedup Set).

### B3 — the aggregate `__all__` row now carries `lens: "aggregate"`

```json
// first click: row ships pre-open ("class=sector-row allnames open" in the server HTML)
// -> the FIRST click toggles it CLOSED -> drill events measure opens, not closes -> no fire
"all_row_first_click_group_drill": []

// second click: reopens -> fires, now with the real enum member, not null
{"meta":{"ev":"group_drill","lens":"aggregate","id":"__all__","sess":"2026-09-03"}}
```

This is intended, not a bug: `group_drill` measures a group being OPENED, and the
`__all__` row starts open, so its own first click is a close. `aggregate_row_all_pre_open_then_reopen`
in `captured_payloads.json` captures both clicks explicitly.

### N2 — dedup key now includes lens

`dedup_lens_keyed_direct_fvTrack_probe` calls the page's own real `window.__fvTrack`
(the exact function `fire()` wired to every DOM listener) three times:
`quadrant_select|theme|cn_autos`, `quadrant_select|sector|cn_autos` (same id, different
lens), then `quadrant_select|theme|cn_autos` again (an exact repeat of the first call).
Two payloads were captured, not three — the id-colliding-but-different-lens pair both
fired (proving the key is NOT `ev|id` alone), and the exact repeat was suppressed
(proving dedup still works under the new key).

### Indifference re-proof (spec §0 gate 3)

Re-run against the mobile context after `chip.tap()`: `window.mmTrack` re-stubbed to
throw on every call, a fresh (never-before-drilled) row clicked —
`page_errors_while_beacon_throws: []` (no uncaught JS error reached the page) and
`accordion_still_toggles_with_beacon_throwing: true` — the page's own functionality
remains fully indifferent to a broken/blocked beacon after the repair.

### `terminal_out`

`terminal_out_hook_present: true` — the built site renders 247
`a[data-ev="terminal_out"]` member Terminal links (`grep -c 'data-ev="terminal_out"'
site/flow_velocity.html`), unaffected by this repair (B4 only corrected the PRIVACY
WORDING describing it — `terminal_out`'s `id` field is genuinely a ticker symbol, not a
group id, which the original comment's "group ids and lens names only" overstated).

## Static render-time counts (real `site/flow_velocity.html`, refreshed rebuild)

```
1  data-ev="changed_expand"
23 data-ev="episode_view"
23 data-ev="history_open"
9  data-ev="quadrant_select"
247 data-ev="terminal_out"
5  data-ev="trust_open"
1  data-ev="watch_note_view" (the rendered element; a second textual match in the
   page's own <script> is the IntersectionObserver's selector STRING, not a second node)
1  data-cmp-lens="aggregate" (the __all__ row, new in this repair — B3)
```

`group_drill` and `compare_run` carry no static `data-ev` attribute (they reuse the
page's own existing accordion `data-sector`/`data-cmp-lens` attributes and the
compare-panel button's own click handler respectively) — both proven live above.

## Known out-of-scope finding (not fixed here — flagged separately)

Investigating the mobile tap path surfaced a SEPARATE, pre-existing bug in the shared
`templates/theme.js` LENS controller, unrelated to and not introduced by this W7
telemetry repair (theme.js is explicitly out of scope for this packet — "all fixes are
page-scoped"): tapping a bare (non-`lens-q`/`lens-term`) LENS-tip chip like the trust
strip's own chips in sheet mode (viewport ≤640px) opens the popover via the `focusin`
handler, but the SAME tap's synthesized `click` event then lands on `<body>` (the
newly-mounted scrim intercepts the hit-test) — the click handler treats that as "click
outside" and immediately calls `hide()`, so the popover opens and closes within the
same gesture (confirmed: polling `.lens-pop`'s class at 50/100/150/300/600ms after the
tap never observes `open`). This means a reader cannot currently read a bare-chip LENS
tooltip by tapping it on mobile anywhere on the site, not just here. It does NOT affect
this repair's correctness — `trust_open` still fires exactly once via `pointerdown`,
which lands before this cascade — but it is a real, separate product bug. Flagged as a
background task rather than fixed in this packet (spawn_task `task_868a2be8`).
