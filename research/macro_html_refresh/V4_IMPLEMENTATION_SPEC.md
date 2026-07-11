# macro.html v4 — Scorecard Grid: binding implementation spec

**Status:** ADJUDICATED 2026-07-11 (operator ruling + judged 3-way mockup competition, 2 judges, unanimous).
**Winner:** `v4_state_board.html` (trader-UX 47+45, design 45+43, doctrine PASS ×2). Grafts ratified below.
**Binding mockup:** `v4_final.html` (= state_board + grafts; produced in stage S0).
**Audit basis:** 52-finding 6-lane audit of the shipped v3 page, 16 confirmed critical, 0 refuted
(full JSON: `/tmp/macro_audit_f9101e/audit_results.json`).

## 0. The ruling (what & why)

The v3 one-line ledger is TOO minimal: measured ~53% horizontal dead space per row; every
detail costs a click. v4 = **scorecard grid**: a 3-card verdict band (THE REGIME · THE RISK ·
WHAT TO DO) + an instrument rack of medium-detail cards. Press a card → it expands **in-flow**
to full grid width using the existing v3 island trays (same DOM). The v3 ledger presentation is
RETAINED behind a topbar segmented toggle **[Grid | Ledger]**; **Grid is the default**.
Two presentations, ONE content DOM — no duplicated data markup, no duplicated ids.

Ratified grafts into state_board:
1. (command_grid) flip-trigger tick on the score bar **with visible caption** "tick = flip trigger at 59" (plain words, EN/ZH).
2. (command_grid) raw internal tokens confined strictly to expand-tray receipts — never on card faces.
3. (cockpit) 3px **left** accent edge per card keyed to the existing `--isle-*` domain tokens (replaces state_board's top border).
4. (cockpit) Fed-odds meeting-path row (e.g. 84.5% / 77.5% / 53.5% as labeled inline bars) → POLICY face, degrade gracefully to next-meeting-only if VM lacks the path.
5. (cockpit) sibling dim on expansion: `opacity:.55; filter:saturate(.5)` (align with the v3 island dim which already exists — reuse, don't duplicate).
6. MARKETS face gains one hot/cold sectors line (from `sector_heat`).
7. Evidence = **six** factors — the mockups' five was a bug. Faces LOOP over engine data (`MS2.components`); never hardcode factor counts or names.

## 1. Files touched

| File | Change |
|---|---|
| `templates/dashboard.html.j2` | all template work (macro-mode gated) |
| `templates/risk_state_live.js` + `site/risk_state_live.js` | PAIRED asset — live score patch must also update `.mx2-prog-fill` width (and only these two files, byte-matched; run `python -m scripts.check_template_site_sync --fix` after editing) |
| `site/macro.html` | re-render via `python -m scripts.render_macro_fast` (VM pickle already in `data/`) |
| `site/us_stocks.html` | must stay **byte-identical** to HEAD — verify with `git diff --stat site/us_stocks.html` after every render; if it changed, your CSS/JS additions leaked outside macro gating — fix the gating, re-render. `git checkout` alone is NOT the fix. |
| `site/news.html`, `site/macro_signals.html` | fast-render rewrites them as a side effect — ALWAYS `git checkout -q site/news.html site/macro_signals.html` after rendering (nightly owns them) |
| `research/macro_html_refresh/v4_final.html` | binding mockup (S0) |

Iteration loop: edit template → `python -m scripts.render_macro_fast` → serve `site/` on port 0 →
Playwright screenshot → LOOK at it → fix → repeat. Never verify by curl/status only.

## 2. Architecture

### 2.1 View system
- Body already gets `page-macro`. Template adds ` mx4-grid` to the body class **for macro mode only** (grid = server-side default → zero FOUC).
- Immediately after `<body>` content for macro mode (top of the regime-radar panel region), a tiny macro-gated inline script:
  `try{if(localStorage.getItem('mx4_view')==='ledger')document.body.classList.remove('mx4-grid')}catch(e){}`
- Topbar segmented control (next to Expand-all): two buttons Grid/Ledger (`l-en`/`l-zh`: Grid/网格, Ledger/列表), `aria-pressed` synced, calls `mx4SetView(v)`: toggles the body class, persists `localStorage.mx4_view`, re-syncs button states. Keyboard focusable, ≥44px touch target on mobile.
- ALL new CSS lives in a NEW `{% if mode != 'stocks' %}<style id="mx4-css">…</style>{% endif %}` block; every selector scoped under `body.page-macro`. Grid-view styles scoped under `body.page-macro.mx4-grid`. Ledger view (no `.mx4-grid`) must render **pixel-identical to current HEAD** (only deliberate audit fixes may alter it).
- ALL new JS in the existing macro-gated script region (grep `_mx2Ids` — extend that block).

### 2.2 The band (inside the existing hero panel `#regime-radar`)
The v2 hero markup (`.mx2-hero`, template ~3050-3164) is NOT moved. In grid view it becomes a
3-zone band via CSS grid on `.mx2-hero` + two NEW grid-only sibling cards appended after the
existing hero content, inside the same panel:

- **Zone 1 — THE REGIME** (existing content, CSS-restyled): `ms-verdict` section stays VERBATIM
  (coherence guard regexes: `<section class="ms-verdict">`, `id="ms-word"`, `id="ms-score"`,
  `id="ms-tick"`, `.v-thesis`, `.v-override`, `.v-flip` — DO NOT alter this markup, ids, or the
  Jinja that fills it). Score numeral + `/100` + progress bar + tick + thesis + flip line +
  goldilocks sub-line + fired-alert chips. Add ONE grid-only caption under the bar: the
  flip-tick caption (graft 1) — derive the threshold from the same `MS.flip_en` data the flip
  line uses; if no numeric threshold is available, caption reads "tick = current score" (never invent numbers).
- **Zone 2 — THE RISK** (new grid-only face, `.mx4-band-risk`, accent `--isle-risk`): dominant
  driver headline (reuse the exact Jinja fields of the existing hero driver card:
  froth/bubble-blow-off headline + note), then top-4 scare ladder rows (name + numeric level +
  micro-bar; reuse the same variables the RISK tray's scare ladder renders), then the
  "What faded" line (the de-escalation chips the RISK tray already renders — reuse fields).
  Entire face is `role="button"` → `mx2Toggle('sx-risk-v2')`, aria-expanded synced.
  In grid view, the old in-hero driver card element is hidden (its content now lives here);
  in ledger view this face is hidden and the old driver card shows as today.
- **Zone 3 — WHAT TO DO** (new grid-only card, `.mx4-band-todo`, accent = verdict color):
  3-5 action rows, each dot + one plain sentence. **Derivation is deterministic — engine fields
  or fixed vocabulary keyed to engine enums ONLY (house law: no originated advice):**
  1. `MS.posture_en/zh` verbatim (dot = `MS.color`).
  2. Weakest leg: from `MS2.components` min-score → EN `Watch {name} — the weakest leg ({score}/100).` ZH `关注{name_zh} — 最弱一环（{score}/100）。`
  3. If `event_risk.show` and it is near-dated (reuse the tray's own condition): fixed vocab
     EN `Expect noise around {label} ({when}) — don't read the first move as trend.`
     ZH `{label}（{when}）前后波动加大 — 首个走势未必是趋势。`
  4. Froth/driver note: the engine's existing note (`stay normal, just watch it` line) verbatim.
  5. `policy_lever` state mapping: QUIET → EN `Policy is quiet — nothing to position for.` ZH `政策面平静 — 无需布局。` (other enums: reuse `framing`/`framing_zh` fields).
  Rows render only when their source field exists; card never renders empty (fallback = posture row alone).
- Band collapses to 1-col stack on mobile; in ledger view zones 2/3 are `display:none`.

### 2.3 The rack (inside the ledger panel)
Wrap the eight existing `.sx` sections in a new `<div class="mx4-rack">` (topbar stays above,
footer below). Grid view: 12-col grid, `gap:14px`. Ledger view: block flow (current look).

Each `.sx` gains a **face**: `<div class="sxg-face" role="button" tabindex="0" aria-expanded="false" onclick="mx2Toggle('<id>')">…</div>`
inserted between `.sx-sum` and `.sx-tray`. Grid view shows `.sxg-face`, hides `.sx-sum`; ledger
view vice-versa. `mx2Toggle`/`mx2ToggleAll`/restore/Escape must sync `aria-expanded` on BOTH
(`el.querySelectorAll('.sx-sum,.sxg-face')`).

Spans (desktop ≥1100px): evidence 6 · events 3 · markets 3 · policy 3 · aibrief 3 · news 3 ·
deep-context 3. `sx-risk-v2`: face hidden in grid view (the band zone-2 is its face), `order:-1`,
so its opened island appears at the TOP of the rack, directly under the band. Expanded:
`.mx4-grid .sx[data-open]{grid-column:1/-1}`. Non-open siblings dim (graft 5, reuse v3 dim).
≤1100px: all span 6; ≤700px: span 12.

Face content (all values via the SAME Jinja expressions/variables the corresponding tray already
uses — grep the tray first, reuse; every string `l-en`+`l-zh`; no `title=` text):
- **EVIDENCE**: headline stance line derived in-template: `{n_good} of {total} signals aligned — {weakest name} lagging` (counts from the components loop; ZH twin). Then SIX factor rows: name · direction glyph · strength bar (score-width) · score. Footer micro-line: flip trigger (reuse `_weakest`).
- **EVENTS**: headline `{n} high-impact prints this week` (count from the loop; ZH twin) + up to 4 rows: date chip · label · impact chip; + Fed odds row in plain words (`Fed: no change priced at 84.5%` / ZH `美联储：按兵不动概率 84.5%`) — fix audit COPY-05 (no naked `No change 84.5%`, and ZH-translate it).
- **MARKETS**: 2×2 quote tiles SPY/QQQ/DJI/RUT: symbol · price (consistent format: thousands commas, uniform $-treatment — fix VIS-03/INT-02dt at the SOURCE expression) · %chg colored; + one line `Hot: {a}, {b} · Cold: {c}` from `sector_heat` (display names, ZH twins).
- **POLICY**: state line in plain words (never a naked enum chip): `Quiet — no active jawboning` / `平静 — 无官方吹风`; last-flip date row; fed-stance row; Fed-odds meeting path (graft 4).
- **AI BRIEF**: 1-line synthesis headline (dominant theme translated via a small dict — fix slug leaks `stock_wire`→"stock wire"/ZH 个股快讯 etc, audit COPY-03/BIL-01/BIL-03); count row `{n} high-impact items`; top tickers row; the required badge in plain words: EN `A read-through of existing signals — not a signal source.` ZH `仅为现有信号的汇总解读 — 非独立信号源。` (fix VIS-02 clipping: no fixed-width chip; let it wrap).
- **NEWS**: top 3 headlines: impact dot · headline (CSS `-webkit-line-clamp:1`) · age. ZH rows must not leak EN classification labels (audit BIL-02 — translate or omit the label in ZH).
- **DEEP CONTEXT**: existing link chips (keep); this face may equal the current sx-sum content restyled.
- Faces NEVER contain raw enums/slugs/untranslated stats (graft 2; doctrine Law 2). Numbers carry meaning words.

### 2.4 Data health + footer
Data-health strip stays below the ledger in both views. Copy fix: `Mostly live — 7 of 154 sources need attention` pattern (plain-word null, count from existing variables). Ledger footer hint becomes view-aware: grid → EN `press a card for detail` ZH `点按卡片查看详情`; ledger → current copy. (Swap via CSS on `body.mx4-grid`, two spans.)

## 3. Audit fixes (ride in this PR; ids from audit_results.json)

**P0/P1 (mandatory):**
- COPY-01 (P0): RISK glance EN=`BUBBLE/BLOW-OFF UNWIND` vs ZH=`观察` divergent meanings → make both languages carry the same meaning (plain words both).
- INT-01: the mx2 close-all Escape handler must no-op while a modal/overlay is open: guard on `#rr-modal-overlay.open` and `.rr-tr-overlay.is-open` (NOTE: `.is-open`, not `.open`, for the tr overlay).
- INT-03: Release-radar modal focus management: on open, focus the dialog (`tabindex="-1"` + `.focus()`); trap Tab within; restore invoker focus on close.
- VIS-01: light-theme thesis gradient mid-stop ≥4.5:1 contrast (adjust the light-theme gradient stops only).
- VIS-02: AI-brief badge un-clipped (see §2.3 AI BRIEF; fix in BOTH tray and new face).
- MOB-01: ledger view glance rows at ≤560px: single line + ellipsis (`.sx-glance` min-width:0 + nowrap/ellipsis on the text span) — detail lives in the tray.
- MOB-02: fired-alerts pill: add click/tap toggle (not hover-only).
- MOB-03: the 12 `?` help tips: tap-to-toggle popover on touch (click handler + outside-tap close; keep hover for pointer devices).
- COPY-04/VIS-08: hero alert chip ZH truncated mid-word with unclosed paren — if the VM field carries the full string, render full + CSS-ellipsis; never bake a string-sliced ellipsis.
- BIL-02, COPY-03, BIL-01, BIL-03: ZH parity in AI-brief + news (see §2.3).

**P2/P3 (fold in, cheap):**
- INT-02: cancel the expand-all stagger timers (store ids + clearTimeout at every state-changing entry point) — or drop the JS stagger for a CSS-only reveal; also fixes INT-06 (reduced-motion).
- INT-04: `details ↓` link must open the data-health `<details>` (set `.open=true` then scroll).
- INT-05: gate `scrollIntoView({behavior:'smooth'})` on `prefers-reduced-motion`.
- INT-07: Expand-all ZH label — render the JS-canonical ZH in the template so first paint matches.
- VIS-04/COPY-02: `risk_state_live.js` `patchMacro` also sets `.mx2-prog-fill` width = score% (both file copies, byte-matched).
- VIS-05: score-panel glow color keyed to verdict color (green/yellow/red), not hardcoded green.
- VIS-06: light-theme pill/`+%` tokens ≥4.5:1 (darken the light-theme `--up`-tinted text tokens where used on pills).
- VIS-10: score-bar axis labels consistent order (`0 Risk-off · 50 Mixed · 100 Risk-on`).
- VIS-11: normalize one-off font sizes in mx/mx2/sx/mx4 layers to the scale {10,11,12,13,14,17,…} (do not touch non-macro layers).
- MOB-04: Expand-all + segmented control ≥44px touch targets ≤700px.
- MOB-05: heatmap mobile: hide sub-labels below a tile-width threshold instead of 4px text.
- MOB-07: `@media (hover:none)`: pause the island infinite animations (bob/pulse/aurora).
- COPY-06: kill raw `h21` slug at glance (plain `21 days` like the tray).
- COPY-07: as-of consolidation: topbar stamp is THE page stamp; remove the footer duplicate; hero keeps only the live-freshness stamp (`ms-date`) + regime as-of (different semantics, allowed — one per panel).
- COPY-08: stance-per-card — satisfied by the v4 faces (each face has a stance/read line).
- COPY-09: `TRANSITIONING` enum in goldilocks sub-line → plain words (EN `shifting` / ZH `转换中`), keep it short.
- BIL-04/05: translate `OFF` badge + `Dominant: rates` channel values (small dict, both spots).
- BIL-06: data-health status pills bilingual (`ok/stale/no_creds/no_key` → plain EN/ZH words).
- INT-08/09dt + INT-07dt: remove the CSS-hidden v2-retired elements and the duplicated news block (`#now-board-legacy`) inside sx-deep-context; AI-brief summary should render once per language pair, not 3×.
- INT-01dt: dead link `oracle.html` in the deep-context tray → point at the real oracle surface if one exists in `site/` (grep other pages for the canonical oracle link) else remove the link.

**Out of scope (do NOT touch):** finra/china_credit staleness (data-ops), the 815-orphan CSS purge (only remove orphans you created or the v2-retired blocks named above), ledger-view content enrichment (later "sync" pass per operator), engine/*.py (no engine changes — template + paired JS only).

## 4. Guards & invariants (verify before declaring any stage done)
1. `python scripts/check_ms_board_coherence.py site/macro.html` → exit 0.
2. `{# MX2-SENTIMENT-START #}…END` block: byte-untouched.
3. `git diff --stat site/us_stocks.html` → empty after render (see §1).
4. No CJK in `title=` attributes; every new user string has `l-en`+`l-zh` (or `data-tip-en/zh`).
5. The word `validated` must not appear in new user-facing copy.
6. No new external requests; no new libraries.
7. `body.page-macro` top gap ≥14px preserved (check_nav_gap).
8. Both views × both themes × both languages × 1440/390px: no console errors, no horizontal scroll, no overlap — screenshot ALL of it and LOOK.
9. Keyboard: face Enter/Space toggles; Escape (no modal open) closes islands; modal focus trap works.
10. `localStorage` keys: `mx4_view` (new), `mx2_state` (existing, unchanged semantics).
