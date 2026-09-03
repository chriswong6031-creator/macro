# Flow Observatory V2 — W6 visual evidence

Per-group 60-session history drawers with state bands and revision markers,
two-group compare (same-lens + cross-lens refusal), descriptive prior episodes,
Terminal links, and the watch-store recorded-limitation decision
(`research/flow_observatory/W6_SPEC.md`).

Captured via Playwright Chromium (`/private/tmp/pwvenv`, headless), `reduced_motion:
"reduce"`, against the REAL rebuilt `site/flow_velocity.html` served statically
(`python3 -m http.server <port> --directory site`) — same method as the W1-W4
verify_shots. A JS pass forces `.is-in` on every `.fv-reveal` section, then opens the
`cn_autos` theme row (its history drawer is one of the top-3 force-`open`ed panels).
`theme`/`lang` are set via `localStorage` before load. Capture script: throwaway, not
committed (this README is the durable record; a copy sits in the session scratchpad).

Every capture's `document.documentElement.scrollWidth - clientWidth` (no page-level
horizontal scroll) and Chromium console `error`-level messages were checked —
`console_errors.json` (committed) shows **zero** horizontal-scroll violations and
**zero** console errors across all 9 captures.

## Real drill walked (group → history → episode → member → Terminal URL)

1. **Group**: curated theme "Autos & NEV Makers" (`cn_autos`), rank 1 by |vel| today
   (`history_drawer_dark_en_1440.png`).
2. **History**: click opens (already pre-opened, top-3) the 60-session drawer —
   dual sparklines (absolute 4wk rate / relative pressure), a below-norm (red) band
   for the first ~35% of the window transitioning to an above-norm (green) band for
   the rest, the pinned replay caption ("Replayed under today's method — not what was
   published historically. No published record yet — this desk's ledger is still
   accruing." — genuinely bootstrap-thin, `data/flow_observatory/observations.parquet`
   does not exist yet in this checkout).
3. **Episode**: 3 prior-episode cards, e.g. "2026-08-17 +2.58σ / -1.0% — over the next
   10 sessions, pressure faded and absolute flow worsened" — descriptive only, no
   %-return, no predictive word.
4. **Member**: 上汽集团 600104.SS, "above norm, rising", +3.76σ.
5. **Terminal URL**: `a[href*=terminal]` on that member resolves to
   `https://app.mastermind-x.com/terminal?sym=600104.SS&from=macro` — the EXISTING
   contract (verified against `templates/flow_velocity.html.j2`'s own `nameln` macro
   and `templates/portfolio.js`), confirmed live via `document.querySelector(...).href`
   in the browser (not just template source).

## Compare (spec §2)

- **Same-lens** (`same_lens_compare_dark_en_1440.png`): two curated themes selected via
  checkbox → "Compare" renders two stat columns (abs 4wk / vs norm / quadrant /
  coverage / top contributor) each with its OWN cloned 60-session history drawer
  (real `<svg><polyline>` markup cloned from the already-server-rendered DOM — no new
  chart element is constructed by JS).
- **Cross-lens refusal** (`cross_lens_refusal_dark_en_1440.png`): one curated theme +
  one official sector selected → renders the pinned one-line reason, EN "Themes and
  official sectors can't be compared directly — different denominators and
  universes." / ZH "主题与官方行业口径不同（分母与样本范围不同），无法直接比较。"
  (same reason `engine.flow_observatory.workflow.compare_groups` returns —
  `tests/test_flow_observatory_workflow.py::test_compare_refuses_cross_lens_pairs`).

## Official-sector accrual gate (spec §2A honored, not re-litigated)

`official_sector_row_dark_en_1440.png` — the official (Shenwan L1) lens today: every
sector renders `insufficient coverage` or `quiet / insufficient data`; "Nonferrous
Metals" (the one sector with enough coverage to score) shows `accruing — 1/130
sessions` in its Flow Trend column and gets **no** history drawer — the membership
store has accrued exactly 1 session, and W6 refuses to backfill a 60-session replay
under today's membership before real accrual covers the window (identical rule
`engine.flow_observatory.groups.aggregate_lens` already applies to the single-point
spark; `scripts/build_flow_velocity.py:_attach_group_histories` applies the SAME gate
to history/episodes — 0/31 official sectors carry a history panel today, and that
`0` is the correct, honest number for real current data, not a bug).

## TP-0 dual-theme state-band treatment (declared, both captured)

- **DARK** (`history_drawer_dark_en_1440.png`): low-alpha glow fill —
  `color-mix(in srgb, var(--up)/var(--down) 18%, transparent)` — a command-center
  luminance wash under the relative-pressure spark.
- **LIGHT** (`history_drawer_light_en_1440.png`): a 6%-tinted block bounded by a
  1px top/bottom hairline in the same hue — a research-workspace idiom (flat glow
  reads as a smudge on white paper; the hairline gives the band a defined edge
  instead). Visibly a DIFFERENT material treatment, not a token-swapped copy of dark's
  glow (TP-0 law).
- Band direction (up/down) is **not** flipped by `data-lang`, unlike `.chg`/`.vbar`/
  `.cdot` — these bands describe a macro regime read, not a raw buy/sell color; the
  ZH capture (`history_drawer_dark_zh_1440.png`) shows the identical red→green band
  placement as the EN capture despite the member rows' own pos/neg colors flipping
  (Chinese convention, pre-existing, unrelated to W6).

## Mobile (390px) — no page-level horizontal scroll, table-internal clipping is
pre-existing

`history_drawer_dark_en_390.png` / `history_drawer_light_en_390.png`: the PAGE itself
never scrolls horizontally (`console_errors.json` confirms `hscroll: 0` on every
capture, including both 390px ones). Long text inside the shared `table.board`
structure (the group's own `concrow` line, and now the historyrow/episode text) is
visually clipped at 390px because `table.board` (pre-existing, `min-width:780px`,
`.tbl-wrap{overflow-x:auto}`) does not reflow into a narrow viewport — this is the
SAME characteristic the already-shipped W3/W4 `concrow`/`excludedrow` colspan-8 rows
already have (verified: the concrow "top name = ..." line is equally clipped in the
390px crop). W6's `historyrow` reuses that identical colspan-8 pattern rather than
diverging into a one-off responsive layout for just this new row — flagged as a
pre-existing GAP in the PR body, not a new regression.

## Console + horizontal-scroll receipts

See `console_errors.json` (committed) — every one of the 9 captures: `errors: []`,
`hscroll: 0`.
