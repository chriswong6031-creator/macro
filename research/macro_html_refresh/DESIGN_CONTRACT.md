# macro.html full UI refresh — design contract (mockup-adjudicated)

**Status:** mockups approved-pending-operator; implementation NOT started.
**Date:** 2026-07-10 · Program: Weather-Station design-framework rollout (framework shipped in #2180 `macro_context.html`).

## Deliverable
Rebuild `site/macro.html` (produced by `scripts/build_site.py`, mode "macro") onto the Weather Station design framework, following `mkv_final.html` in this directory (open in a browser; theme toggle included). It was produced by a judged two-variant competition + steal-list merge:

- `mkv_brief.html` — "one-glance brief" (won trader-UX 42/50: hierarchy + simplicity)
- `mkv_deck.html` — "full-parity deck" (won design 41/50: parity + polish)
- `mkv_final.html` — **the binding hybrid**: brief's IA + deck's parity content in a detail tier

## Binding design rules (from the judge panel)
1. **Single-dial discipline** — the 77 verdict is the ONLY circular dial; Q1/Goldilocks is a KPI chip, never a second hero card; no mid-page composite gauges.
2. Upper fold (~1000px) = hero + TODAY band; density resumes below the fold.
3. Catalysts split into two actionability tiers: TODAY (breaking-slug, hot) vs THIS WEEK (muted rail).
4. Policy-lever/repricing/flip-confirmation: labeled rows + delta chips, not raw tables.
5. Cross-asset strip: level + direction arrow + one-word context per tile (never color-only checks).
6. AI Daily Brief carries a visible badge: "display-only synthesis of existing signals — not a signal source" (house law: LLMs never originate signals).
7. News rows carry date + impact chips.
8. One chip vocabulary (color-mix tints), one gauge idiom (bar fill), theme.css tokens, aurora, 900px collapse — identical to `templates/macro_context.html.j2`.

## Implementation constraints (recon'd)
- Producer is `scripts/build_site.py` (~line 3446+, writes macro.html directly; also caches a VM for `scripts/render_macro_fast.py` — use that DEV harness for fast template iteration).
- `scripts/check_ms_board_coherence.py` guards the market-state boards on this page (verdict/score/thesis invariants) — keep board data contracts intact.
- Page hosts live overlays (`live.js`/`live_config.js`), the release-radar modal + tab strip, and alert popovers — all must survive the reskin.
- Bilingual EN/ZH throughout; no CJK/t() in `title=`; `check_nav_gap` requires ≥14px top gap (body padding-top).
- macro.html is also hit by the `-X theirs` render-resurrection failure mode — hand-transplant deltas, never regen intraday from stale data (see memory `render-resurrects-stale-site-text`).

## OPERATOR RULING — 2026-07-10 (supersedes parts of the hybrid contract above)
Deep integration, not overhaul, SHIPPED on this basis:
- The ORIGINAL Market State board — verdict hero with score progress bar, six-factor Evidence rows, multi-timeframe tape, Macro Backdrop/Goldilocks card — is RETAINED in original form. Do not re-propose compacting/demoting it.
- The heatmap (`#heatmap-scorecard`) is retained untouched.
- NO KPI chip strip in the hero (mx-kpi-strip removed). The mx hero = gradient headline + single dial + legs grid + flip-condition strip only.
- Everything else (policy band, release-radar chrome, AI brief card + display-only badge, sector heat, sentiment band, cross-asset tiles, index health grid, news chips, link-out strip) uses the mx framework.

## OPERATOR RULING — 2026-07-11 (v2 FULL TRANSITION — supersedes the deep-integration ruling above)
Operator: the old dashboard "has too much data, is too crowded, is too wordy, and is a layout mess with many useless data points. Do a full transition to yours instead... front end should be simplistic... advanced technical data hidden away through hover options or pressing."
BINDING DESIGN = `v2_final.html` in this directory (judged 43/50 over a hover-first variant; expand-first, touch-native):
- ONE-screen collapsed row-ledger front: hero (gradient headline = thesis · score panel containing the big numeral + progress bar + tick · dominant-driver card) then one-line rows: EVIDENCE / EVENTS / MARKETS / RISK / POLICY / AI BRIEF / NEWS / DEEP CONTEXT.
- ALL advanced data lives in press-to-expand trays (250ms choreography, staggered entrances, Expand-all pill w/ rotating chevron, localStorage state, Escape, keyboard Enter/Space, visible chevrons).
- NO "Hover for…" copy anywhere (touch-honest); one affordance verb.
- The old Market State board layout is RETIRED; its content maps to: score panel (verdict+score+bar+tick), EVIDENCE tray (six factors), RISK tray (radar+sentiment), hero context (dominant driver). The "board is the hero" ruling of 2026-07-10 is superseded.
- Heatmap lives inside the MARKETS tray (legible, labeled, as-of stamped).
- Every tray carries as-of stamps; AI brief keeps the display-only-synthesis badge; drawdown ladder keeps its measurement caveat.
