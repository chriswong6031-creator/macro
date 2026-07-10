# Tech Lab × Mastermind Terminal Integration — Masterplan (by Fable)

Date: 2026-07-10 · Operator request (verbatim intent): upgrade `site/tech_lab.html` into an
actual technical-analysis research & testing surface, deeply integrated with the Mastermind
Terminal (charting-app); indicators directly testable in the Terminal and visible on its UI;
robust and testable both programmatically (LLM sessions) and visually (humans); full UI
revamp of tech_lab; fix Chinese text leaking into the English side.

Status: ACTIVE program. Builds on `STOCKINVEST_TECH_INDICATOR_SUITE_PROGRAM.md` (#1891) and
`DANNYTRADES_INDICATOR_DOCKET_ADJUDICATION_2026-07-10_BY_FABLE.md` (DT-R17..R24, #2086/#2087).

## 0. Findings that motivate the program (scout, 2026-07-10)

1. `engine/tech_catalog.py` now holds 64 signals / 14 families, but the page's data
   (`site/factordata/tech_screener.json`, `tech_lab.json`) is stale at 46 signals because
   `scripts/build_tech_lab_data.py` is OFF-render **and unwired** — it only runs manually.
2. The Terminal's 8-indicator suite (DT-R19) is complete on local branch
   `feat/dt-technicals-suite` but never merged/deployed; master has since moved 93 commits
   (TV-parity passes touching `ChartPanel.tsx`).
3. An intel bridge already exists (`charting-app/ingest/pull_macro_intel.py` reading the R2
   copy of `site/stockdata/<SYM>.json` → `<SYM>.intel.json`) with a deployed chart-marker
   overlay system — the natural seam for lab↔Terminal integration.
4. tech_lab.html is the only page on the site with the `"EN / 中文"`-in-one-string
   antipattern (option text, placeholder, JS-concatenated titles) — house patterns exist
   (`data-en`/`data-zh` option swap, `data-ph-zh` placeholders, `L(en,zh)` + `langchange`).

## 1. Rulings (TLT-R1..R9)

**TLT-R1 — Charter / DT-R24 supersession.** DT-R24's fence ("no new bridge exports through
`pull_macro_intel.py` in this wave") is superseded for exactly the candidate follow-up DT-R24
itself flagged: forwarding display-tier tech blocks into `intel.json`. Authority: explicit
operator request 2026-07-10 ("deeply integrate the two platforms"). The rest of DT-R24
stands: **no new `mastermind:context` tags, no NW keys, no `dt_contra_state` export** — the
bridge feeds the Terminal's display surface only, never `mastermind_context.json`.

**TLT-R2 — Data freshness law.** `build_tech_lab_data.py` runs nightly as a dedicated
off-render job (`tech_lab_offrender`, modeled on `oracle_offrender` in daily.yml) that
rebuilds AND commits `site/factordata/tech_screener.json`, `tech_lab.json`, and
`tech_events/`. Render budget untouched; the render-path step remains the cheap Jinja render.

**TLT-R3 — One canonical fire source.** Catalog signal fires are computed only by
`engine.tech_catalog` (Python). The per-ticker export `site/factordata/tech_events/<T>.json`
is the single substrate every downstream chart (tech_lab UI, Terminal markers) reads.
No client-side reimplementation of catalog signal logic.

**TLT-R4 — Terminal lab layer is display-tier.** The Terminal gains (a) a toggleable
"Lab signals" marker layer rendering tech_events fires labeled by signal name + direction
glyph — explicitly NOT "BUY"/"SELL" badges — and (b) a Tech Lab panel (fin/ tab family)
showing the descriptive lab profile for signals on the current symbol, with the survivor-
universe caveat and era-split columns verbatim. No authority, no ranker contact, no alerts.

**TLT-R5 — Cross-platform parity fixtures.** Where both platforms implement the same math
(ichimoku lines, EMA ribbon, RSI, Bollinger bands), the macro repo exports deterministic
golden vectors (`scripts/build_tech_parity_fixtures.py`, seeded synthetic OHLCV, committed
fixtures); charting-app carries a copy and a vitest suite asserting `indicatorMath.ts`
matches within tolerance. Fixture source of truth = macro repo script. This is the anti-
drift contract between the two platforms.

**TLT-R6 — Testing is descriptive-tier.** The LLM/human test harness
(`scripts/tech_lab_cli.py`) emits descriptive fire profiles only: fixed metric set (21d
display convention), era split ALWAYS printed (DT-R16), months-not-fires N framing
(DT-R14 caveat printed), base-rate comparison, `"tier": "descriptive_profile"` stamped in
every output. It never emits a verdict; promotion still requires a pre-registered gauntlet
(house epistemics). No free-horizon verdicts: `--horizon` accepts only the declared
descriptive ladder {10, 21, 42, 63}d and outputs all requested horizons as descriptive rows.

**TLT-R7 — tech_lab i18n law.** The page must pass a zero-CJK-in-EN-mode audit: options via
`data-en`/`data-zh` + `langchange` repopulation; placeholders via `data-ph-zh`; all
JS-rendered strings through an `L(en, zh)` dual-span helper; re-render on `langchange`.
(These are the existing house patterns from `reports.html.j2` / `baskets_china.html.j2`.)

**TLT-R8 — DT suite completion.** Merging + deploying `feat/dt-technicals-suite` onto
current master (rebase, ChartPanel conflict resolution, build + Playwright verification)
completes the DT-R19 build. DT-R20 vocabulary law and DT-R23 reject list apply verbatim to
all new Terminal surfaces in this program.

**TLT-R9 — Verification law.** Every UI PR ships with browser verification on prod-shaped
data (Playwright screenshots, light+dark, EN+ZH, desktop+mobile) per the terminal-ui quality
bar; curl-status checks alone are theater. The tech_lab revamp is mockup-first: variants
screenshotted and judged before the build.

## 2. Wave map

Macro Dashboard repo:
- **W1 (PR-A)** fix(tech-lab): i18n leak fixes on the current page + regen `site/tech_lab.html`.
- **W2 (PR-B)** ops(tech-lab): `tech_lab_offrender` nightly job + fresh 64-signal JSON regen.
- **W3 (PR-C)** feat(tech-lab): `tech_events/` per-ticker fire export (inside the existing
  single-pass build), parity-fixture generator + fixtures, `tech_lab_cli.py` harness,
  missing engine tests (`compute_fire_metrics`, build schema, CLI).
- **W4 (PR-D)** feat(tech-lab): full UI revamp (chart-centric research cockpit; LWC chart
  with fire markers from tech_events; sortable per-signal lab table with era-split badges;
  confluence mini-screener; per-stock profile with signal timeline; "Open in Terminal"
  deep links; TLT-R7 i18n; display-only banner retained).

charting-app repo:
- **W5 (PR-E)** feat(terminal): dt-technicals-suite integrated onto master + `?ind=`
  deep-link param + vitest + parity tests (TLT-R5).
- **W6 (PR-F)** feat(terminal): macro bridge — `pull_macro_intel.py` tech block
  (tech_events + lab profile from R2 factordata), lab marker layer (default off),
  Tech Lab fin/ panel with backlink to tech_lab page.
- **W7** deploy to VPS (`/opt/terminal`), live verification through the CDN/domain.

## 3. Contracts

`site/factordata/tech_events/<TICKER>.json`:
```json
{ "ticker": "NVDA", "generated_utc": "...", "window_start": "YYYY-MM-DD",
  "signals": { "<signal_id>": { "dir": 1, "kind": "event|state",
    "fires": ["YYYY-MM-DD", ...], "state": 0 } } }
```
Window = last 3 years of fires (event fires; state rising edges). Index file
`tech_events/_index.json` lists tickers + fire counts + generated_utc.

Parity fixtures (`tests/fixtures/tech_parity/`): `ohlcv.json` (seeded synthetic, ~500 bars,
full OHLCV) + `expected_<indicator>.json` per shared indicator with per-bar line values
(nulls for warmup). Tolerance: 1e-6 relative (documented per file).

Terminal deep link: `https://app.mastermind-x.com/terminal?sym=<SYM>&ind=<key,key>` —
`ind` keys = `IndKey` union values; unknown keys ignored.

intel/v1 tech block (added by pull_macro_intel): `{"tech": {"events": <tech_events payload>,
"profiles": {sid: <tech_lab.json row>}, "asof": ...}}` — display-tier, absent tolerated.

CLI: `python -m scripts.tech_lab_cli {list|state|profile|series}` — JSON to stdout,
`--sample N` supported, exit 0 on honest nulls.

## 4. Inherited constraints (binding, from standing law)

- "validated"/已验证 CI-guarded (`check_validated_claims.py`); no Danny/whale/glassnode etc.
  tokens on public surfaces (DT-R20, RUL-CL-9); 35/50/75 as labeled reference bands only.
- No buy/sell threshold semantics on Terminal indicators (DT-R19); no act-now routing of
  fresh fires (#1513); no composite feeding allocation (Signal Commons R3); no LLM-originated
  numbers (Article 1); era-split (DT-R16) + time-control framing (DT-R14) on any pooled stat.
- RSI-stack periods frozen 7/14/21 (DT-R18); ichimoku PIT displacement guard retained.
- Nightly job step endings use `if/fi`, never `[ ... ] && echo` tails (guard-echo law, #2070).
- No `title=` bilingual text (check_title_i18n.py); theme.js included (report_base).

## 5. Clocks

- First fresh nightly tech_lab data cycle: 2026-07-11 (verify `tech_lab_offrender` green).
- Terminal live verification: same-day as W7 deploy.
- Come-back 2026-07-24: confirm two weeks of nightly tech_events accrual + Terminal panel
  consumption; then assess whether a reverse read (Terminal usage → lab priorities) is worth
  a charter (unchartered today).
