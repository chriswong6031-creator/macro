# Quanted amalgamation masterplan — Terminal intraday options + Learn estate

Program owner: Fable main loop (this doc + RECON.md are the binding context for all spawns).
Companion: `RECON.md` (full teardown), `api_samples/`, `js_extracts/1736.beautified.js` (their renderer, reference only — we write our own).
Upstream context in charting-app: `docs/OPTIONS_SUITE_PARITY_MASTERPLAN.md` (QuantData sweep, phases 0–5),
`docs/OPTIONS_TERMINAL_UPGRADE_REVIEW_2026-07-23.md` (scorecard), `terminal/DESIGN_OBSERVATORY.md`, `terminal/AGENTS.md`.

## §0 ACCEPTANCE GATES (all Wave-1 lanes; phrased "not done unless")

1. Fresh end-to-end happy path with **zero manual workarounds**: `FLOW_FIXTURE=1 npm run dev` (terminal) renders every new pane
   with fixture data; no console errors; reload-races are bugs you own.
2. **Per-feature visual crops posted in the PR body** (light theme n/a — Terminal is dark-only; capture default + one alternate
   state per control: scrubbing mid-day, greek switched, per-min vs cumulative, hover popover open, evolution modal open).
3. Entry points wired: new panes reachable from the existing Options Hub tab bar / pane selectors — no orphan routes.
4. Unit tests: shader color function (exact-value assertions at o=0, 0.3, 0.6, 0.8, 1.0 for pos+neg+zero), replay index math
   (frame↔stamp mapping, Home/End/Space), snapshot-store contract (index.json ↔ per-stamp files), session-line rebase math.
   `npx vitest run` green.
5. Honesty laws (DESIGN_OBSERVATORY + house epistemics): every pane carries an as-of stamp + cadence label; sign colors via
   `var(--up)/var(--down)` resolved at runtime (never hex in TSX); display-tier language only, no "validated"; nulls render as
   honest empty-states ("No surface data yet — accruing"), never fabricated fields.
6. **No self-merge**: builder returns PR URL + crops to the commissioning session; main session reviews, then completes the
   merge chain (house completion law) unless a real check is red.
7. Collision guard: do NOT touch files owned by open PRs #195 (options paywall), #164 (sidebar IA), #144 (Levels board/Learn seed):
   `components/OptionsPaywall.tsx`, sidebar IA files, Levels-board files. New code in new files + minimal-diff tab registration.
8. Macro-repo learn lane: bilingual EN/ZH chrome per estate law (body EN-only per W1 language ruling), own SVG diagrams
   (no copied assets/text), `python3 -m scripts.check_validated_claims`-safe wording, killed-thesis guard (charm/vanna content is
   educational mechanics only — NO claims that these are live signals we trade; see DNR §2 signed-charm kill), template↔site sync law respected.

## §1 What we learned (one-paragraph brief)

quantedoptions.com = 3 surfaces (SPX/VIX licensed-CBOE gamma workspace at 1-min/10-min cadence tiers; per-ticker OPRA
gamma/delta/flow with 735×1-min replay; contract-flow scanner) built on an immutable-snapshot blob data plane
(signed CDN URLs + index.json per ticker-day) with a global replay scrubber that time-travels the whole workspace, and a
Canvas-2D "paint" heatmap renderer (tiny grid → high-quality upscale; two-band shader with white-hot cores — exact formula in
RECON §3). Their moat is licensed signed MM positioning; their UX moat is replay + surfaces + drill-downs. Full census RECON §4–6.

## §2 Amalgamation decisions (port / improve / invent)

**PORT (Wave 1, data already in hand):**
- P0-A Session flow charts: our Tide payload already carries per-minute net call/put premium series that the UI discards →
  build **Session Flow pane**: cumulative|per-min, C+P|C|P, off-open rebase, fill, absolute (quanted's Premium Flow/Net Delta panes).
- P0-B Greek switcher on Exposure tab: `delta_net/vanna_net/charm_net` already in gex payload, rendered nowhere → GEX|DEX|VEX|CHEX.
- P0-C Walls chip row + range presets (±2/±5/±10/All) on the exposure ladder; dual NOW|PEAK scale; strike hover popover
  (per-greek values + top-expiry breakdown from matrix payload) + "Intraday Evolution" modal (once store exists, else day-sparkline from gex history).
- P0-D The surface renderer + replay spine (below) driven by **net-premium-by-strike × time** which our live_flow ticker
  payloads can materialize TODAY; architecture greek-ready for GEX surfaces when the intraday greeks snapshotter lands (Wave 2).

**PORT (Wave 2+, needs data work):** true gamma/vanna/charm surfaces (per-minute greek snapshots; parity-plan Phase 3);
historical multi-day replay; exposure-by-expiry bubble drawer; Σ-expiry aggregation; quad view; scanner belts + highlights
bursts; contract drill (option candles + print tape — needs conditions capture, parity Phase 1); pop-out panes; workspace pages.

**IMPROVE over theirs (our edge):** bilingual EN/ZH; alerts on flip/wall-cross/flow-burst (they have none); OI-confirmation lane
(ours, they lack); flowScore calibration; macro-regime context strip; education wired into tooltips; mobile-responsive.

**DON'T build:** signed-participant views (we lack the license — never imply we have exchange-tagged positioning; our labels must
say "OI-assumption model"); any positioning-fusion composite score (DNR §1); charm/vanna *signal* claims (DNR §2 — display/educational only).

## §3 Wave 1 lanes

### Lane T (charting-app, one Opus builder, branch off fresh origin/master, PR → master)
Repo: /Users/chriswong/Documents/Cluade/charting-app (worktree under .claude/worktrees/). Read terminal/AGENTS.md +
terminal/DESIGN_OBSERVATORY.md + docs/OPTIONS_SUITE_PARITY_MASTERPLAN.md first.

**T1 — Surface pane + replay spine (flagship):**
- `terminal/lib/heatSeries.ts`: LWC v5 custom-series heatmap plugin (cells {low,high,amount}; offscreen grid canvas;
  imageSmoothingQuality high blit; RECON §3 shader with pos/neg RGB from CSS vars at mount; opacity option; zero-contour optional).
- `terminal/components/surface/SurfacePane.tsx`: candles (existing intraday API) over the field; controls: metric tabs
  (Wave 1: `Net Prem`; scaffolding for Gamma/Vanna/Charm as disabled-with-tooltip "accruing"), scope 0DTE|All where data allows,
  agg 1m/5m/15m, opacity slider, ±range slider; crosshair readout pill (strike + value); as-of + cadence stamp.
- `terminal/components/surface/ReplayBar.tsx`: global-to-the-pane-group scrubber — frames from snapshot index; ⏮◀▶⏭, 1x/2x/4x/8x,
  Space/Home/End, LIVE badge at head; time-travels SurfacePane + Session panes + ladder via shared context.
- Snapshot store contract + materializer: `live_flow/surface/{ROOT}/{DATE}/index.json` + `{HHMM}.json`
  ({spot, price_levels, time_steps, grids:{netprem}, asof, cadence}) — Python materializer in the poller repo path
  (`scripts/` or `hub/`, follow existing live_flow writer conventions) aggregating existing per-ticker strike flow into
  per-stamp files; `/api/flow` route additions `surface_idx:{ROOT}` + `surface:{ROOT}:{STAMP}`; FLOW_FIXTURE fixtures with a
  dense synthetic day (sinusoid + hot pockets so the paint look is visible in crops).
**T2 — Session charts + ladder upgrades (P0-A/B/C):** new `SessionFlowPane` (tide per-minute series) + Exposure tab greek
switcher + walls chips + range presets + NOW|PEAK dual scale + hover popover; register in OptionsHubView tab bar with minimal diff.
Separate commits T1/T2; one PR; crops per §0.2.

### Lane M (macro repo, one Opus builder, branch off fresh origin/main, PR → main)
**M1 — Learning Center: "Dealer Positioning" cluster** — new track `options` (extend _VALID_TRACKS/_TRACK_ORDER/_TRACK_LABELS)
with 7 lessons rewriting RECON §7 concepts in our voice (NOT their copy): 0DTE regime shift; the middleman; what OI can/can't
tell you (honest version: we model dealer sign from OI heuristics — say so; contrast with exchange-tagged data as a concept);
rehedging mechanics; gamma gravity; charm drift (educational mechanics + explicit "we do not trade this as a signal" honesty box);
the flip/regime change. Each lesson: inline SVG diagram in Signal-Ink idiom (paths + HTML labels, currentColor,
var(--up)/var(--down)), formula box, worked example, self-check details block, cross-links + CTA to /gex.html and /learn.html
flagship. Wire _URL_MAP, run `python3 -m scripts.build_free_content`, commit site/ outputs per template↔site sync law.

## §4 Wave 2+ charter (separate sessions; re-read RECON before each)
1. Intraday greeks snapshotter (BS recompute per stamp from chains; 51GB EOD surface backfill) → real GEX/vanna/charm surfaces + evolution modals everywhere.
2. Exposure-by-expiry bubble drawer + Σ-expiry aggregation + specific-expiry lens.
3. Scanner upgrade: index/sector belts as click-filters, Highlights bursts w/ windows, contract drill (candles+tape) once conditions land.
4. Alerts: flip-cross, wall-touch, flow-burst, surface hot-pocket → AlertsView conditions + push.
5. Workspace system: layout presets, add-row, multi-page, pop-out panes.
6. Replay v2: multi-day history, event annotations, cross-pane sync on /flow.
7. Theme engine: per-greek color pairs + presets (Style menu equivalent) within obs design language.
