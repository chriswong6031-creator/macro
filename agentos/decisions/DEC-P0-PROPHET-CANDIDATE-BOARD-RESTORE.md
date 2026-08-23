---
key: P0-PROPHET-CANDIDATE-BOARD-RESTORE
question: >
  P-MP1-SHELL (#6076) re-sourced the principal US Prophet grid from the candidate
  screener to the plan book and deleted the rich candidate card grid, leaving live
  users with no way to reach tonight's candidate population. How is candidate
  visibility restored without merging the two record kinds, and what does that
  change about MP-1's presentation sequencing and P-MP1-DENSE's remaining scope?
answer: >
  The principal board becomes an explicit TWO-SOURCE view — `Candidates | Plans`
  — with Candidates the baked default. Candidates renders the existing
  `us_standouts.buy` population through the existing `_us_board_cards.html.j2`
  partial into its own container `#us-cand-grid`; Plans keeps the migrated
  `#us-life-grid` plan book and its seven-cell lifecycle ladder, unchanged, inside
  a new `#us-plan-block`. This is a SOURCE switch, never a population merge: no
  candidate row gains a lifecycle state or a synthetic plan id, and the two grids
  share no id and no ancestor below `.nb-grid-section`.
  Four production-truth defects are repaired in the same slice, because a board
  whose numbers disagree with itself is not a restored board: the escaped
  `<b>55</b>` heading (t() escapes its arguments, so `t('<b>'~n~'</b>')|safe`
  prints the tags), the mixed-unit `N shown · M setups` subtitle, the candidate
  census that added the separate `us_standouts.ran` array into a `buy`-only total,
  and a "Showing X of Y" bar that counted stage HEADINGS as records.
  MP-1's presentation sequencing is AMENDED for this slice only: the packet
  assumed the plan book would be the sole principal population until P-LAB-UI and
  P-MP1-DENSE landed. It is not, and was not allowed to be, while candidates are
  the only live discovery surface users have.
  P-MP1-DENSE's remaining obligation is answered as PLANS ONLY. The dense table
  the packet owes does not need to be built twice: the existing `USStockTable`
  ALREADY renders the candidate population from `payload.rows`, and this slice
  scopes it to Candidates mode so it can no longer appear under a Plans label.
  What is missing is the plan-book half.
rationale: >
  The decisive fact is that nothing server-side had to change. `_split_us_board`,
  `gate`, `_us_board_group_items` and `_write_us_payload` all still run, and the
  real production payload on the live VPS (production HEAD da336ec61f8) still
  carries the entire locked candidate remainder — 326,143 bytes of `cards_html`
  holding 57 cards and 5 stage headings, plus 57 flat `rows` — which every
  entitled session has been downloading and DISCARDING since #6076, because
  `hydrate()` never read `cards_html`. The producer was never dead; only its
  consumer was. That makes restoration a presentation change of the smallest
  possible blast radius, which is the right shape for a P0 on a live surface.
  Separate containers are not stylistic. They are what makes cross-hydration
  structurally impossible rather than merely avoided: `initShowMore` counts the
  children of ONE element, so a candidate count and a plan count cannot be
  confused once the two populations are in two elements; and the W-L1 repaint
  selector already excludes `[data-mp1-grid]`, so a candidate grid without that
  marker re-acquires live-quote repaint with no selector change and still cannot
  reach the plan grid.
  The census fix is the one with a real judgment in it. `us_standouts.ran` is a
  DIFFERENT array with its own section and its own tier gate; folding it into the
  candidate total made the heading (72) disagree with the gate note (60) on the
  live page tonight. Quoting the population the grid actually renders is the only
  total that can reconcile with the five state counts, and a residual "Other"
  shelf is rendered when and only when a stage-less row exists, so the arithmetic
  can never be silently wrong instead of visibly wrong.
alternatives:
  - option: Merge candidates and plans into one population with a synthesized lifecycle state for plan-less candidates.
    why_not: >
      Forbidden by DNR:KILL-PROPHET-POP-MERGE at the data-authority layer, and
      false on its face — the plan-card renderer's own header records that the
      candidate join is absent for ~75% of plan rows. A fabricated zone or plan id
      would be the worst possible repair for a board whose defect is that its
      numbers do not reconcile.
  - option: Revert #6076 and put the candidate grid back as the sole principal board.
    why_not: >
      Throws away the plan book, the lifecycle ladder, and the Day-5 production
      proof of 269 canonical plans. The plan view is not wrong; it was wrong as
      the ONLY view.
  - option: Leave the plan grid principal and just fix the Candidates section's copy and counts.
    why_not: >
      Repairs the labels on a surface that still cannot show a single candidate
      card. The Chairman's observable mission is the population, not the caption.
  - option: Build the dense plan Table now so Plans mode has its own table view.
    why_not: >
      That is P-MP1-DENSE, explicitly excluded by #6185's stop condition. Scoping
      the existing candidate table to Candidates mode removes the false label
      without building the missing half, which keeps this slice reversible.
evidence:
  - "GitHub issue #6185 (binding implementation packet); Linear MAS-111."
  - "Live production page, anonymous, 2026-08-22: 4 `class=\"pvcard\"` occurrences — 3 are PLAN cards inside `#us-life-grid`, the 4th is a JS string inside `_pvcPaint`. ZERO candidate cards rendered."
  - "Live production page: `<span class=\"mx-sec-total\">` prints the literal text `&lt;b&gt;72&lt;/b&gt; screened tonight`; `#us-board-sub` prints `60 shown · 76 setups`; the gate note beside them prints `first 3 of 60`. Three numbers, three denominators."
  - "Both `t()` implementations in this repo escape their argument, so the mechanism does not depend on which one a file gets: 147 templates define a local `{% macro t(en, zh='') %}` whose `{{ en }}` escapes under `autoescape=True` (templates/dashboard.html.j2:14 — this is the one dashboard.html.j2 uses, since scripts/build_site.py registers td/tr/t_pctile but NOT t), and engine/i18n.py:34 returns `Markup(...).format(en, zh)` whose `Markup.format` escapes too (registered as a global by build_aibrief.py, build_ai_desk_page.py, build_canada.py, build_btc_strategy.py). `|safe` then seals the already-escaped entities, which is what makes them render as visible tags."
  - "templates/dashboard.html.j2:16355 `_cand_total = (gate.total if gate else _board|length) + _ran_rows|length` and :16193 `_sc.update({'ran': _sc['ran'] + (_ran_rows|length)})` — the two sites that conflated `us_standouts.ran` with the `buy` population."
  - "Real production premium payload, /opt/macro/site/premiumdata/us_stocks.json at production HEAD da336ec61f8: gated=True total=60 preview=3 locked=57; cards_html=326,143 bytes with 57 cards and 5 nb-stage-hd headings; rows=57 with 57 distinct tickers; plan_cards_html=466,528 bytes."
  - "`grep -n '\\.cards_html\\b' templates/dashboard.html.j2` returned zero matches before this change — the payload key was written on every build and never consumed."
  - "templates/dashboard.html.j2:19697 `mergeBoardCards(grid, html)` exists with no call site; it is the pre-#6076 heading-aware candidate merge, revived here."
  - "templates/dashboard.html.j2:19205 W-L1 selector `.nbgrid[data-showmore-rows]:not([data-provboard]):not([data-mp1-grid])` — unchanged; a candidate grid without the marker is re-acquired by it automatically."
  - "templates/theme.js:4841 initShowMore counts `grid.children`; `_us_board_cards.html.j2:65,77` emit `.nb-stage-hd`/`.nb-lane-hd` as grid children, so an unfixed bar would have reported 65 for 60 candidates."
  - "Removal commit for the candidate include: 31ca4971ba4a (P-MP1-SHELL central act, PR #6076)."
affects:
  - "WS:PROPHET-US-V4-RECOVERY"
  - "research/migration_packets/MP-1-prophet-board.md"
  - "templates/dashboard.html.j2"
  - "templates/_us_board_cards.html.j2"
  - "templates/theme.js"
confidence: high
reversibility: easy
decided_by: chairman
decided_at: 2026-08-22
---
