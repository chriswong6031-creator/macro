# macro.html v5 wiring — aurora-glass production build (binding)

**Status:** operator-ratified 2026-07-11 ("this is good … You can go ahead and build out").
**Binding visual:** `v5_final.html` (rev2, merged #2328). **Scope:** the GRID view of macro.html
only — the ledger view stays pixel-faithful v3, the island trays stay v3, us_stocks.html stays
byte-identical. This REPLACES the v4 grid skin (mx4 faces/band) with the v5 language.

## 0. Operator mobile addenda (2026-07-11)
- The 60-session path chart is HIDDEN on mobile (≤700px) — the command scorecard shows only the
  gauge cluster there.
- Popovers must NEVER bleed off screen: ≤700px they render as a fixed bottom sheet (left/right
  12px, max-height 70vh, internal scroll, opaque surface, backdrop dim, close affordance).
- Every scorecard fully responsive: 12-col grid ≥1100px, 2-col ≥700px, 1-col below; no
  horizontal scroll at any width in any state.

## 1. Files
| File | Change |
|---|---|
| `templates/dashboard.html.j2` | grid-view reskin: v4 mx4-css/faces/band replaced by v5 layer (all scoped `body.page-macro.mx4-grid`); ledger view untouched |
| `scripts/build_site.py` | two additive VM keys (§4): `ms_history`, `idx_spark` — cheap render-path reads, graceful when absent |
| `templates/risk_state_live.js` + `site/risk_state_live.js` | PAIRED: patchMacro also updates the gauge arc + needle (via data attrs, §3.1) |
| `site/macro.html` | re-render via `python -m scripts.render_macro_fast` (inject new VM keys into the dev pickle per §4.3 for local testing) |
| `site/us_stocks.html`, `site/news.html`, `site/macro_signals.html` | must not ship: restore/checkout after every render |

## 2. Layout mapping (v5 card ⇄ existing DOM)
The eight `.sx` sections + trays REMAIN (one DOM, two views). v4's `.sxg-face` contents are
replaced with v5 faces; v4's verdict band (`.mx4-verdict-band`) is REMOVED (its content moves
per below). Ledger view (`body:not(.mx4-grid)`) must render exactly as today.

1. **Command scorecard** = the hero panel `#regime-radar` restyled (grid view):
   - Left cluster: gauge SVG (§3.1) + `#ms-score`/`#ms-word` (the big numeral/verdict ARE the
     guard-required ids — keep markup + ids; ms-verdict section stays intact; `ms-tick` +
     `mx2-prog-fill` stay in-markup for the coherence guard, CSS-hidden in grid view) +
     regime pill + thesis (`v-thesis`) + flip (`v-flip`) + two popover buttons.
   - Right: 60-session path SVG (§3.2), hidden ≤700px.
   - Popovers (§3.3): "6 signals aligned" → factor breakdown (loop `MS2.components`, six rows);
     amber "Elevated Risk · {{score}}" (render the button ONLY when the radar/froth state is
     elevated — reuse the same condition the v4 band zone-2 used; otherwise a neutral
     "Risk detail" button) → dominant-risk ladder (driver numeral + graded meters, same fields
     as the v4 band). Popover footers: "Full breakdown ↓" → `mx2Toggle('sx-evidence')` /
     "Full risk detail ↓" → `mx2Toggle('sx-risk-v2')` (closes the popover, opens the island).
   - sx-evidence + sx-risk-v2 faces: hidden in grid view (popovers are their glance layer);
     their trays open full-width in the rack as today.
2. **MARKETS tiles row** = face of `sx-markets-v2` (press → markets island): 4 tiles, price
   (`data-bare` live ids preserved) + delta + sparkline (§3.4; graceful flat-line absence).
3. **WHAT TO DO** = static card; KEEP the v4 derivation template rows verbatim (engine fields /
   fixed vocab law), reskin to v5 (icon tiles + two-line rows).
4. **Upcoming Events** = face of `sx-events-v2`: week rail (date-positioned) + impact badges.
5. **Fed Probability Instrument** = static card: donut (84.5%-style no-change odds from the
   same fields the events glance uses) + outcome bars from `prediction_markets.events`
   ("Fed Decision in July?" outcomes; graceful if absent).
6. **Market Sentiment** = static card: big odometer keyed to `fear_greed.dial` (REAL value —
   55 · Neutral today; needle at dial%, zone word from `label_en/label_zh`; disclaimer fields
   exist — one plain footer line, no stacking).
7. **Sector Temperature** = static card from `sector_heat` (hot/cold chips + mini heat strip).
8. **Alerts Centre** = face of `sx-news-v2` (press → full news island): top 3 alerts from the
   `alerts` VM list (severity-sorted, warn first; row = severity tint + `plain_en/zh` +
   one-line `message/message_zh`), footer "Showing {n} of {total} fired · View all →"
   (→ mx2Toggle('sx-news-v2')). The hero's old fired-alerts pill stays functional (it is the
   modal path); Alerts Centre is the at-rest surface.
9. **Policy Monitor** = face of `sx-policy-v2`; **AI Brief** = face of `sx-aibrief-v2`
   (keep the v4/v5 structured bilingual lines + required not-a-signal-source note).
10. **Deep context** = slim link-chip row above the health strip (face of `sx-deep-context`,
    minimal). **Health strip** unchanged (plain-word null).

## 3. Instruments (ALL static SVG/CSS rendered by Jinja — JS never draws; no emoji; ≥11px text)
### 3.1 Gauge
Arc geometry fixed; fill length = Jinja-computed: `stroke-dasharray="{{ '%.1f' % (MS.score/100*ARC_LEN) }} {{ '%.1f' % ARC_LEN }}"`;
needle rotation Jinja-computed from score. Bake `data-gauge` attrs (arc-len, radius, center) on
the SVG so `risk_state_live.js` patchMacro can move arc + needle + numeral together on live
updates (paired file, byte-matched, `check_template_site_sync`). Verdict-color tokens.
### 3.2 60-session path
From `ms_history` (§4.1): polyline+area over up to 60 sessions, y-domain 0-100 with 42/60 band
hairlines; label honestly: "{{n}}-session path" when n<60 else "60-session path". Hidden when
`ms_history` missing/len<2 AND on mobile. Score values are integers from the engine log — no
smoothing that invents shape (straight polyline segments).
### 3.3 Popovers
Port from v5_final rev2 WITH its three baked lessons: (1) toggle fn named `mx5TogglePop` (NEVER
a native HTMLElement method name — inline handlers resolve element methods first); (2) opening
lifts the containing `.card` (`pop-open` class, z above the fixed dim layer) — every glass card's
backdrop-filter is its own stacking context; (3) near-opaque surface (`--pop-bg`). Esc/outside
close; `aria-expanded`; reduced-motion = no animation; ≤700px = bottom sheet (§0). Escape
handler must respect the existing modal guards (rr-modal `.open`, `.rr-tr-overlay.is-open`) and
close popovers BEFORE islands.
### 3.4 Sparklines
From `idx_spark` (§4.2): 20-point polyline per index, stroke + 25%-opacity gradient area,
tinted by sign of period change. Absent → tile renders without a sparkline (no empty box).

## 4. Render-path additions (scripts/build_site.py — additive, never fatal)
1. `ms_history`: read `data/market_state/forward_log.jsonl` (exists, ~3KB), last 60 rows →
   `[{"asof","score"}]`; missing file → key absent. De-dup by asof (keep last).
2. `idx_spark`: last 20 daily closes for SPY/QQQ/^DJI/^RUT from the price store the
   index-health builder already reads (find its loader and reuse — do NOT add a network call);
   → `{"SPY":[...],...}` floats; any failure → key absent.
3. Dev testing: `scripts/render_macro_fast` reads the stale pickle — for local verification,
   inject both keys into `data/_dev_macro_vm.pkl` with a small python snippet (load, compute
   from the same sources, dump). NEVER commit the pickle. Template must render cleanly when
   both keys are absent (production pickle-lag tolerance + first nightly).

## 5. Aurora + tokens
Fixed-position backdrop div (`.mx5-aurora`, `position:fixed; inset:0; z-index:0;
pointer-events:none`) with 2-3 static radial gradients ≤12% — NOT `background-attachment:fixed`
(mobile Safari + capture artifacts). Content stacks above (`.page` z≥1). Glass tokens from
v5_final (`--glass-bg/--glass-border/--pop-bg` dark+light). ALL new CSS in a
`{% if mode != 'stocks' %}<style id="mx5-css">` block scoped under `body.page-macro.mx4-grid`;
delete the superseded v4 mx4 face/band CSS rather than layering over it (no dead layers).
Bloom restraint: one text-glow (hero numeral); no decorative motion.

## 6. Guards & invariants (every stage; same as v4 §4 plus)
ms-board coherence exit 0 · MX2-SENTIMENT block byte-untouched · us_stocks byte-identical
(restore from origin/main after render) · news/macro_signals checked out · no CJK in title= ·
every new string l-en+l-zh · no "validated" · nav gap ≥14px · both views × both themes ×
EN/ZH × 1440/390: zero console errors, zero horizontal scroll · keyboard: popovers + faces +
Escape ordering (popover → island → modal guards intact) · localStorage keys unchanged
(`mx4_view`, `mx2_state`) · v4 audit fixes must survive (Escape modal guard, focus trap,
alerts-pill tap, help-tip tap, live fill sync — now gauge sync) · ledger view pixel-faithful.
