# Flow Observatory V2 — W7 evidence (product-learning telemetry)

`research/flow_observatory/W7_SPEC.md` — nine typed events through the EXISTING
first-party `/api/collect` beacon (`templates/theme.js`'s `window.mmTrack`). This wave
adds **no visible UI or copy** (proved by
`tests/test_flow_observatory_workflow.py::test_w7_no_banned_vocabulary_and_visible_text_is_byte_identical_to_pre_w7`,
a byte-for-byte visible-text diff against the pre-W7 committed template), so the
evidence here is a beacon-stubbed interaction crop + the actual captured payloads —
not a dark/light/EN/ZH design matrix (there is no new art direction to prove).

Captured via Playwright Chromium (`/private/tmp/pwvenv`, headless), `reduced_motion:
"reduce"`, against the REAL rebuilt `site/flow_velocity.html` served statically
(`python3 -m http.server 8931 --directory site`, `.claude/launch.json` config
`site-static`) — same method as the W1/W4/W6 verify_shots. `window.mmTrack` is
overridden with a capturing stub BEFORE each interaction (theme.js's own
`loadMMAnalytics` never runs against `localhost`, so nothing else defines it — this is
exactly the "beacon blocked" condition spec §0 gate 3 requires the page to survive
identically under).

## Files

| file | shows |
|---|---|
| `trust_open_interaction_dark_en_1440.png` | Clicking the "A-share large-order flow" trust-strip chip: the EXISTING LENS popover opens unchanged ("Large & super-large order-size proxy — Tushare moneyflow_dc…") — the `trust_open` telemetry hook adds zero visible change to this pre-existing interaction. |
| `group_drill_interaction_dark_en_1440.png` | Clicking the "Autos & NEV Makers" theme row: the existing accordion drilldown opens (concentration line, 60-session history drawer, 3 prior episodes, member rows) — `group_drill` and `episode_view` both fire from this one interaction, telemetry-only, no rendering change. |
| `captured_payloads.json` | The actual `window.mmTrack('flowobs', {...})` arguments captured for each interaction below, plus the dedup and beacon-throw indifference checks. |
| `console_log.txt` | The stub's `console.log` lines for the same captured calls (`CAPTURED_BEACON_CALL <type> <json>`) — a stand-in for a real network trace, since a static `python -m http.server` render has no live `/api/collect` to send a real request to. |

## What the payloads prove

```json
{"meta":{"ev":"trust_open","lens":null,"id":"cn_large_order_proxy","sess":"2026-09-03"}}
{"meta":{"ev":"group_drill","lens":"theme","id":"cn_autos","sess":"2026-09-03"}}
{"meta":{"ev":"episode_view","lens":"theme","id":"cn_autos","sess":"2026-09-03"}}
```

- **Envelope reuse verified against the actual code**: every call goes through
  `window.mmTrack('flowobs', {...})` — `templates/theme.js`'s existing first-party
  beacon function (`function track(type, extra)`, assigned to `window.mmTrack` in its
  `loadMMAnalytics` IIFE). No second transport, no new endpoint.
- **Field names match the frozen schema exactly**: `ev`/`lens`/`id`/`sess`, nested under
  `meta` — the SAME passthrough object `theme.js`'s own `click` event already uses for
  `{tag, text, href}`, since `/api/collect`'s row builder (`app/main.py::collect`) only
  ever persists a closed set of named columns plus one arbitrary `meta` JSONB blob; any
  top-level field beyond that fixed set is silently dropped. This is *why*
  `app/main.py` is an OWNED file here (the endpoint whitelists event `type`s via
  `_MM_EVENT_TYPES`, which now includes `"flowobs"`) even though the row schema itself
  needed no change.
- **`sess`** is `snap.market_session` (falls back to `snap.as_of`), confirming the
  page's own market-session string, not the visitor's tab/analytics session id.
- **`dedup_second_click_on_same_chip: []`** in `captured_payloads.json` — clicking the
  identical trust-strip chip a second time in the same pageview produced ZERO new
  captured calls (the `(ev, id)` `Set` dedup, spec §1).
- **`indifference_test`** — with `window.mmTrack` re-stubbed to `throw` on any
  `'flowobs'` call, clicking a fresh quadrant-cell chip produced
  `page_errors_while_beacon_throws: []` (no uncaught JS error reached the page), and a
  second, never-before-drilled group row still toggled its accordion state normally
  (`accordion_still_toggles_with_beacon_throwing: true`) — the page's own functionality
  is fully indifferent to a broken/blocked beacon (spec §0 gate 3).
- **`terminal_out_hook_present: true`** — the built site renders 247
  `a[data-ev="terminal_out"]` member Terminal links (verified separately via
  `grep -c 'data-ev="terminal_out"' site/flow_velocity.html`).

## Static render-time counts (real `site/flow_velocity.html`, not the test fixture)

```
1  data-ev="changed_expand"
23 data-ev="episode_view"
23 data-ev="history_open"
9  data-ev="quadrant_select"
247 data-ev="terminal_out"
5  data-ev="trust_open"
1  data-ev="watch_note_view"
```

`group_drill` and `compare_run` carry no static `data-ev` attribute (they reuse the
page's own existing accordion `data-sector`/`data-cmp-lens` attributes and the
compare-panel button's own click handler respectively) — both are proven live above
(`group_drill` in `captured_payloads.json`; `compare_run`'s call site is asserted by
source in `tests/test_flow_observatory_workflow.py::test_w7_every_event_hook_renders_for_a_fully_populated_page`).
