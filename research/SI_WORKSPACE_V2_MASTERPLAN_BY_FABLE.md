# Sector Intelligence Workspace V2 — masterplan (by Fable)

Status: ACTIVE, 2026-08-02. Operator redesign order on the shipped V1 merge (scored
3/10, verbatim): "all you did was clump all the pages into one… just as messy as
before… use same page sub-pages, sub-dashboards… possible left sidebars that lead to
different pages like our Terminal charting app… You also didnt optimize it for light
mode. And this page doesn't seem very intelligent either."

Ruling accepted in full. V1 (#4237/#4299) remains the correct DATA consolidation —
one URL, one payload, stubs, one vocabulary, healed data defects. V2 is the missing
ARCHITECTURE: the same organs inside a workspace shell instead of one long scroll.
Scope: US (`sector_central.html`) first; China port follows after #4299 lands (same
shell, same contract). No engine, payload, stub, or nav changes — shell + IA + light
mode + synthesis copy only.

## §0 ACCEPTANCE GATES (not done unless)

1. **A workspace, not a page.** Persistent left sidebar (Terminal AppNav idiom:
   compact icon rail, label + tooltip, `.on` active state, aria-current) driving
   FIVE hash-routed same-page views. No full-page scroll spine: exactly one view
   mounted/visible at a time; switching is instant (display toggling, zero reloads,
   zero refetches — the payload is already client-side).
2. **Overview is the whole product for a casual user.** View 1 renders ONLY: verdict
   hero → the four action lanes (with trace-expands) → one "what changed" strip
   (see gate 6). Nothing else. A user who never opens the sidebar gets the complete
   gated read above the fold and leaves.
3. **The five views** (ids pinned; sidebar order fixed):
   `#overview` Overview 总览 · `#map` The Map 全景图谱 (cycle clock + rvx rotation
   map + scope pills + sectors board) · `#moving` What's Moving 正在轮动 (SRR app +
   turns + rotation events + desk watch) · `#money` Money & Breadth 资金与广度
   (internals + flows + heatmap + leadership) · `#explore` Explore 深入探索
   (table + chart + Time Machine + track record + forming narratives + links).
4. **Every legacy anchor keeps resolving.** A hash router maps old deep links —
   `#actnow-section`, `#si-movement`, `#read-<id>`, `#theme-…` handled upstream by
   the stub — to (view, intra-view scroll target). The stubs' redirect anchors and
   every inbound link on the estate (chat, dashboards, detail back-links, alerts)
   land on the right view scrolled to the right organ. CI-pinned mapping table.
5. **Per-view intelligence header.** Every view opens with ONE synthesized plain-word
   line stating what the view sees right now, computed from data already in the
   payload (display-tier composition only — no new scores; A7 intact). Examples of
   the register: Map → "Semis and Software sit far right and still climbing — the
   rotation's destination." Moving → "Quiet tape: no live handoff events; 3 groups
   turned up this week." Empty states collapse to ONE honest quiet line per view —
   never two dialects of "nothing to do" stacked (V1 defect, operator screenshot).
6. **"What changed" strip** on Overview: max 3 chips diffing today vs the prior
   session from data the payload already carries (lane moves, handoff state, new
   turn confirmations). Display-tier diffing, no new artifacts; absent data → the
   strip renders nothing (no fabricated novelty).
7. **Light mode is a first-class design surface.** Both themes get deliberate panel
   definition, border/chip contrast, and state colors (红涨绿跌 in ZH preserved);
   PR body carries screenshot pairs (light+dark × EN+ZH) for EVERY view, and the
   review checklist marks light-mode contrast explicitly. No "dark-first, light
   inherits" shortcuts.
8. **Weight and speed budgets hold.** No payload duplication; lazy-mount heavy
   organs on first view activation (map embed, TM, heatmap); rendered page stays
   ≤ V1 +15KB; view switch < 100ms perceived (no spinner).
9. **Mobile: the sidebar becomes a bottom/top segmented switcher** (same five views,
   same router) — never a hamburger that hides the product; the Overview view is
   the landing state everywhere.
10. **Epistemic line unchanged.** Lanes remain the only gated reads; display-only
    postures, receipts, and the grader chip survive verbatim; no falsifier register.
11. **Proof + ship.** Browser verification per gate 7 with per-view crops; all V1
    invariants/tests retargeted to the shell (anchors table pinned); full ship loop
    to merge-on-green; commissioner (main loop) reviews before merge — no builder
    self-merge (flagship first-pass law).

## §1 Shell contract (pinned; builders implement exactly)

- Grid: `body > .si-shell { display:grid; grid-template-columns: var(--si-rail-w, 200px) 1fr; }`
  Sidebar `<nav class="si-side" aria-label="Sector Intelligence views">` with five
  `<a class="si-view-btn" data-view="…" href="#<view>">` (glyph + label; label
  collapses to tooltip ≤1100px where the rail narrows to 56px). Terminal idiom;
  glyphs from the existing dashboard-icons set (no new icon family).
- Router: `__siRoute()` on `hashchange` + boot — resolves hash → view via the
  LEGACY_ANCHORS table (gate 4), toggles `.si-view.on`, lazy-mounts on first
  activation, updates `aria-current` + document title suffix (" · <View>").
  Unknown hash → `#overview`. `history.replaceState` keeps anchors shareable.
- Views: existing organs move INSIDE `<section class="si-view" data-view="…">`
  wrappers WITHOUT internal rewrites (V1's render-mode law stands); the V1 sticky
  anchor rail dies; section ids inside views are preserved for anchor routing.
- Intelligence headers: one `<p class="si-view-read">` per view, written by a
  `__siViewReads(payload)` composer — plain-word EN/ZH, data-driven, ≤18 words,
  with a `?` receipt naming its inputs. Composition rules live beside the composer
  as comments; banned-vocab list applies (no internal state names, no raw slugs).
- Theme tokens: shell colors exclusively via theme.css vars + `color-mix` — audit
  every organ panel under light; fix contrast at the SHELL level (scoped overrides)
  without forking organ CSS.

## §2 What does NOT change

Engines, payloads, si_handoff, stubs, nav files, detail families, tests' epistemic
pins, the China V1 PR (#4299 lands as-is; the China V2 port is a follow-up wave of
this program reusing the same shell partial).

## §2b W1 view-partition map (measured on post-#4300 main; line refs indicative)

| V1 markup (templates/sector_central.html.j2) | V2 view |
|---|---|
| tape strip + band (~870-894) · rvx-hero both variants (1247/1301) · `#regime` (1315) · `#actnow-section` (1331) + `#grader` | **overview** (+ new what-changed strip) |
| `#si-map` (1347, contains `#sc-cyclemap` 1388 + sectors `#board` + fast-lens footnote) | **map** |
| `#si-movement` (1452: rc-events-mount, rotation-app, desk-watch-mount) | **moving** |
| `#tm-mount` + `{% include "_forming_narratives" %}` (1466) — RELOCATE out of movement | **explore** |
| `#si-money` span (1469) + `#internals-section` (1470: internals, flows, heatmap, `#scc-leadership`) | **money** |
| `#explore-section` (1502: `#table-section` 1507, `#chart-section` 1517, member-sym registry, track record) | **explore** |
| `#si-rail` (1316, the V1 sticky anchor rail) | **dies** — replaced by the sidebar |

LEGACY_ANCHORS (router table; CI-pinned): `#actnow-section`→overview · `#read-<id>`→
overview+trace-open · `#regime`/`#grader`→overview · `#si-map`/`#sc-cyclemap`/`#board`→map ·
`#si-movement`/`#rc-events-mount`/`#rotation-app`→moving · `#si-money`/`#internals-section`/
`#scc-leadership`→money · `#explore-section`/`#table-section`/`#chart-section`/
`#forming-narratives`/`#tm-mount`→explore · unknown→overview.

## §3 Waves

- **W1 (main loop, design):** shell skeleton + router + LEGACY_ANCHORS table +
  light/dark token audit on one view (Overview) — the reference implementation.
- **W2 (opus builder):** remaining four views wrapped + lazy-mount + per-view reads
  wired; mobile switcher.
- **W3 (opus designer):** light-mode contrast pass across every organ panel; crops.
- **W4 (opus builder):** test retargets (anchor table pin, shell invariants, V1 rail
  pins → sidebar pins); ship loop.
- **W5 (post-#4299):** China port of the shell.
