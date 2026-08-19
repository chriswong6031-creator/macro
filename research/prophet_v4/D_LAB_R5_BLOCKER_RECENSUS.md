# D-LAB-R5 — blocker re-census against CURRENT production

**Authored:** 2026-08-18, by the D-LAB-R5 design session (LAB-0 §6.2.B).
**Base:** `origin/main` at `d772fbd6f884` (branch cut point).
**Why this exists:** LAB-0 §6.2.B requires the R5 cycle's production blockers to be
**re-censused, not copied from R4**. R4's prose was written on 2026-08-13; it is now five days
and several merged PRs old, and two of the items it held open have since closed. Copying it
forward would have carried a stale picture into the record a migration builder reads.

**Scope of the re-census:** the ten blocking findings of the R3 verdict as dispositioned in
`research/reference_integrity/prophet-board-5514-r4/R4_CLOSURE_LEDGER.md`, plus the two items that
cycle explicitly did **not** waive (`.../README.md` §"Not waived by this cycle").

**Verdict vocabulary.** `CLOSED` = the defect no longer exists and a merged change is named.
`OPEN` = the defect is present on `origin/main` today, with a receipt. `PARTIAL` = the closure
landed in part. `ARTIFACT-CLOSED` = the item was about the reference document/artifact rather
than production, and is closed there. `INSUFFICIENT` = not determinable from the receipts
gathered; named rather than guessed.

---

## 0. The headline

**Both of the two blockers R4 refused to waive are now closed on main.** They were the two hard
dependencies standing between the frozen reference and the MP-1 production migration:

- **G-D (#5541)** — the plan book's actionability axis and enrichment publication gap — closed by
  `5c9f31af1f1a` (`engine/prophet_board_read.py`). Coverage went from the axis reaching **61/179**
  and enrichment **45/179** to **204/229 available with 0 `blocked_data`**, and name/sector/spark
  at **229/229**.
- **`overtime_producer_contradiction` (#5540)** — closed by `444f80d62774`
  (`engine/prophet_bridge.py:811 plan_clock_date()` now anchors both `phase` and horizon expiry).
  Measured today: **0** open rows are past their horizon on the clock the phase uses, and **0**
  carry `phase=overtime` — the two now agree by construction rather than by coincidence.

**And one blocker the R4 reference closed inside its own stylesheet is still live in production
templates:** `--pv-buy` resolves **byte-identical to `--up`** in `templates/theme.css` in both
themes, so a BUY stance chip and a positive live change still paint one value on a production
card. That is the DA-002 defect, unfixed where it actually ships. Two more (PRC-303, VTC-301) are
open or partial in production. None of the three is caused by this cycle, and none is a reason to
weaken the reference — they are named here so the MP-1 shell wave inherits an accurate list.

---

## 1. Verdict table

### 1a. Production-scoped items

| # | Item | Verdict | One-line basis |
|---|---|---|---|
| 1 | **PRC-301** card routes to the name's detail surface | **CLOSED** | the whole production card is an `<a href="stock.html#TICKER">` |
| 2 | **PRC-302** anon gate promises levels the card never renders | **CLOSED** | the shipped gate copy makes no entry/target/void promise |
| 3 | **PRC-303** chase-caution can co-occur with no-read / no-zone | **OPEN** (code path) | the caution's gate never consults the zone state |
| 4 | **PRC-305** degraded-freshness disclosure | **CLOSED** | producer + banner both ship, bilingual |
| 5 | **PRC-306** every plan row reachable as a card | **PARTIAL / unverified** | no render cap found in the templates; end-to-end reachability not traced |
| 6 | **VTC-301** chartless hero geometry + printed null | **PARTIAL** | heights are equalised; the **printed absence label is absent** |
| 7 | **VTC-302** chart-stroke salience | **INSUFFICIENT** | not separately measured this pass |
| 8 | **DA-002** stance ink ≡ direction ink | **OPEN** | `--pv-buy` is byte-identical to `--up` in both themes |
| 11 | **G-D (#5541)** actionability + enrichment publication gap | **CLOSED** | `board_read_coverage`: 204/229 status, 0 `blocked_data` |
| 12 | **overtime producer contradiction (#5540)** | **CLOSED** | 0 rows past horizon on the phase's own clock; 0 `phase=overtime` |

### 1b. Artifact-scoped items (the reference document, not production)

| # | Item | Verdict | One-line basis |
|---|---|---|---|
| 9 | **DA-001** a document asserting repealed law as current | **ARTIFACT-CLOSED** | the repealed paragraph is struck, blockquoted as repealed, and carries an amendment record |
| 10 | **DA-003** `compare.html` advocacy defects | **ARTIFACT-CLOSED** (one residual unchecked) | production-column styles scoped into `.cmp-prod`; the chartless specimen and the costs sections exist |

---

## 2. Receipts

### 1 · PRC-301 — card → name-detail link · **CLOSED**

- R3 finding / R4 disposition: `R4_CLOSURE_LEDGER.md:29,33,35,37`.
- Production locus: `templates/_prophet_card.html.j2:376` — the card root is
  `<a class="pvcard pv-…" href="{{ cx.href|e }}" data-ticker="{{ cx.tk|e }}" …>`.
- The href's producer: `templates/_us_board_cards.html.j2:246` — `'href': 'stock.html#' ~ n.ticker`.
- Read: the capability exists in production today, on the house cross-market convention.
  **CONFIDENT.**

### 2 · PRC-302 — anonymous gate copy · **CLOSED**

- Ledger: `R4_CLOSURE_LEDGER.md:41,45,47,49`.
- Production locus: `templates/tier_preview.js:103-165` (`surfaceFor()` maps `#us-standouts` →
  `"prophet"`; `gateCopy()` returns the anon and free copy), mounted at `:257-264`.
- Shipped anon copy: *"Expand the Prophet shortlist" / "More model-ranked setups, with the same
  signal detail and discipline."* Free tier: *"See the complete Prophet ranking" / "Every
  model-ranked setup, in one signal book."* Neither promises entry, target or void levels.
- Residual: `tier_preview.js` was searched, not the whole estate. If duplicate gate copy exists on
  another surface it was not found. **CONFIDENT for this locus.**

### 3 · PRC-303 — the chase caution and the zone state · **OPEN (code path)**

- Production locus: `templates/_us_board_cards.html.j2:84-99`, and the zone branch at `:231-232`.
- The gate, verbatim (`:96`):
  `{% set _entry_ok = not (es and es.get('status') in ['extended','topping','exit','avoid','blocked']) %}`
  When `es` is `None` — no entry signal at all — `es and …` is falsy and `_entry_ok` is **True**.
- The caution emit (`:99`) is conditioned on `(_vs_fired or n.get('alpha_entry') == 'extended')`
  and `_entry_ok`. **It never consults `_bz` or `_zk`.** Meanwhile `_zk` becomes `'none'`
  (rendered "No zone — stand aside", `_prophet_card.html.j2:435`) whenever `_bz` is falsy and the
  verb is not `wait`/`near`.
- `grep -rn "Don't chase above the buy zone" templates/ scripts/ engine/` → exactly one
  occurrence, at `:99`. No suppressed or rewritten variant exists.
- Read: the R4 disposition describes a suppression/rewrite that is **not present at this
  file:line**. Whether a live card exhibits the pairing tonight was not checked against the
  payload's real `entry_signal` / `vol_squeeze` data. **Code path OPEN — CONFIDENT; live
  incidence — UNCERTAIN.**

### 4 · PRC-305 — behind-the-tape / degraded freshness · **CLOSED**

- Ledger: `R4_CLOSURE_LEDGER.md:53,57,59,61`.
- Producer: `scripts/build_stock_library.py:1524` — `_compute_board_staleness(…)`, majority-based
  and fail-closed.
- Render: `templates/dashboard.html.j2:1448` (`.nb-stale-note` styling) and `:15832-15837` (the
  conditional banner, bilingual, carrying the vintage, the sessions-behind count, and
  "check a live quote before you act"). **CONFIDENT.**

### 5 · PRC-306 — full-book card reachability · **PARTIAL / unverified**

- Production locus: `templates/dashboard.html.j2:15897` — `{% set _board = _su.buy %}`, the whole
  buy lane with no slice; `:16031-16089` builds `_render_list.items` by iterating the entire
  `_board`; `:16083` `<div class="nbgrid" data-showmore-rows="3">`; `:16090` includes
  `_us_board_cards.html.j2` over the full item list. The show-more machinery is at `:18861-18921`
  and `:19313`; the card↔table toggle at `:1578-1579`.
- `grep -n "GRID_CAP\|\[:40\]"` across `dashboard.html.j2` and `_us_board_cards.html.j2` → **0
  hits**. (`engine/us_board_rank.py:1414-1415,2516` carry `FEATURED_CAP` / `SECTOR_CAP` /
  `RAN_CAP`, none of which is a grid ceiling.)
- Read: no numeric render cap exists in the current template path, which is consistent with the
  capability being present. **The end-to-end claim — that clicking through reaches every plan row
  as a card — was not traced.** UNCERTAIN; treat as unverified rather than closed.

### 6 · VTC-301 — the chartless hero · **PARTIAL**

- Production locus: `templates/_prophet_card.html.j2:156` (`.pv-chart svg{height:74px}`), `:165`
  (`.pv-nochart{height:74px}`), `:378` (the branch: `{% if cx.get('spark') %}{{cx.spark|safe}}{%
  else %}<div class="pv-nochart"></div>{% endif %}`).
- **The heights are equalised** — the R4 finding's geometric half is closed in production.
- **The printed absence label is not there.** `grep -n "pv-nochart::before\|pv-nochart::after"` →
  no hits, and the div is emitted empty. Production communicates the null with a hue-tinted void;
  the R4 reference prints `No chart yet` / `暂无图表` in it.
- Narrower override, correctly scoped: `templates/dashboard.html.j2:1039` sets
  `#us-standouts .nbgrid[data-provboard] .pv-nochart { height: 36px; }` for the evening/provisional
  board only, explicitly scoped away from the canonical morning grid per its own comment
  (`:1020-1038`).
- Read: geometry CLOSED, printed null OPEN. The R5 reference inherits R4's printed null (see
  `mockups/refs/prophet_lab/DESIGN_NOTES.md` §2.6) and MP-1 will therefore carry it into
  production. **CONFIDENT on both halves.**

### 7 · VTC-302 — chart-stroke salience · **INSUFFICIENT**

Not separately measured this pass; the stance-ramp half (DA-002) was, and is reported below.
To settle it: compare the production spark's stroke weight and ink against the card plane in both
themes, at the `.pv-chart svg *` rule, and against the R4 reference's values.

### 8 · DA-002 — stance ink is direction ink · **OPEN**

The one item where the R4 reference is *ahead of* production, and the gap matters at migration.

- `templates/theme.css:80-81` (dark `:root`) — `--pv-buy: #45b873` and `--up: #45b873`:
  **byte-identical.**
- `templates/theme.css:152-153` (`html[data-theme="light"]`) — `--pv-buy: #1f9a55` and
  `--up: #1f9a55`: **byte-identical.**
- `templates/theme.css:185` (`html[data-lang="zh"]`) — `--pv-buy: var(--up)`: identical by
  explicit declaration.
- The chip's *text* ink routes through a separate family: `_prophet_card.html.j2:77`
  (`.pv-buy{--pvh:var(--pv-buy);--pvh-ink:var(--ink-pv-buy,…)}`) with `theme.css:333`
  `--ink-pv-buy: var(--pv-buy)` in dark — a pass-through. So the dark BUY chip ink resolves to
  `#45b873`, which is `--up`.
- `grep -n "pv-noread" templates/theme.css` → **0 hits**: production has no `--pv-noread` token at
  all; the no-read state falls through to `--pv-hold`'s grey via
  `_us_board_cards.html.j2:91-92`.
- Read: on a production card a BUY chip and a positive live change still paint one value, which is
  precisely the defect. R4 fixed it **inside its own `board.css`** (a deliberate ramp at 82% dark
  / 54% light off `--up`, plus a separate `--pv-noread` rung); production never received it.
  **CONFIDENT.**
- Note for the migration: `--ink-mix-up` in dark `:root` (`theme.css:250`,
  `templates/_state_inks.html.j2:30`) is still literally `100%`, which does **not** corroborate the
  wording of the R4 disposition note about that token. The chip ink travels the `--ink-pv-*`
  family, not `--ink-up`. The defect is real either way; the mechanism in the note is imprecise.

### 9 · DA-001 — repealed law asserted as current · **ARTIFACT-CLOSED**

- `mockups/refs/institutionalize/us_stocks/DESIGN_NOTES.md:184-185` — the heading is struck:
  *"SUPERSEDED at R3 by PRC-203; struck at R4 under DA-001. DO NOT REBUILD."*
- `:185-191` — the repealed text survives only as a labelled blockquote ("retained only so the
  repeal is legible"). `:194-210` states what is law instead (one universe, no view exemption).
  `:216-218` carries the amendment record citing DA-001.
- Read: no unmarked repealed-law paragraph remains at §0b.1 or §7. **CONFIDENT.**

### 10 · DA-003 — `compare.html` · **ARTIFACT-CLOSED (one residual)**

- `mockups/refs/institutionalize/us_stocks/compare.html:12` — the RIO modal-row specimen (no
  chart, no name, no sector, no price, no read) is present.
- `:128-140` — `.cmp-prod .pv-trg` and `.cmp-prod .pv-nochart` carry production's own explicit
  values, i.e. the production-column styles are scoped rather than leaking.
- `:617-623` — the explicit list of classes scoped into `.cmp-prod`.
- `:462,493,525` — a "What it costs / 代价是什么" section exists for all three columns.
- Residual: FTI's rendered stance value (`wait` vs a hardcoded `hold`) was not re-verified.
  **CONFIDENT on the named defects; one point UNCHECKED.**

### 11 · G-D (#5541) — actionability + enrichment publication · **CLOSED**

- R4 held it open at: axis **61/179**, enrichment **45/179**
  (`R4_CLOSURE_LEDGER.md:465`, `README.md:78-79`).
- Producer that closes it: `engine/prophet_board_read.py`, whose own header states the gap it was
  written against ("the axis reached **61/179** … and the enrichment **45/179**. This module
  publishes the join that closes that gap").
- Merged as: `5c9f31af1f1a prophet(G-D): publish the plan book's actionability axis (#5541)`
  (`git log --oneline --since=2026-08-13 --grep=5541`; the same commit is the only one touching
  `engine/prophet_board_read.py`).
- Published today, from `git show origin/main:site/prophet/index.json` → top-level
  `board_read_coverage` (schema `prophet.board_read_coverage/v1`, `rows: 229`):

  ```
  status:  available=204  blocked_data=0  not_applicable=25  (reason: plan_closed=25)
  name:    available=229  blocked_data=0  not_applicable=0
  sector:  available=229  blocked_data=0  not_applicable=0
  spark:   available=229  blocked_data=0  not_applicable=0
  lane:    available=58   blocked_data=0  not_applicable=171
                          (not_on_board=169, board_bucket_carries_no_lane=2)
  blocked_data_rows: 0
  ```

  An independent per-row recount over `plans[].board_read.fields[k].state` reproduced
  name/sector/spark at 229 each.
- Reading it honestly: the axis is **not** 204/204 of everything — 25 rows are
  `not_applicable: plan_closed`, which is a real category, not a hidden gap. `lane` is sparse by
  design (`not_on_board` on 169 rows). What changed materially is that **`blocked_data` is now
  zero**: the "60% of the live book has no stance" condition the R4 reference was built around no
  longer describes the payload.
- **Denominator caveat, recorded because it will confuse the next reader:** the payload carries
  top-level `plan_count = 251` while `len(plans) = 229`. They count different things —
  `scripts/build_prophet.py:2031-2033,2462` sets `plan_count = len(all_plans)`, a cumulative
  id-keyed map carrying historical/closed entries forward, while `:2625` emits
  `"plans": active_entries`. Coverage ratios should be quoted against **229**, the row set
  `board_read_coverage` itself measures. **CONFIDENT.**

### 12 · overtime producer contradiction (#5540) · **CLOSED**

- R4 held it open as a vocabulary defect: `age_days` anchored to `signal_date` while
  `days_elapsed`/`tau` and horizon expiry anchored to `plan_clock_date()`, so "past its horizon"
  computed by a reader disagreed with `phase=overtime` **by construction**
  (`R4_CLOSURE_LEDGER.md:466`, `README.md:80-83`).
- Merged as: `444f80d62774 prophet: reconcile Overtime with the horizon clock (ruling §13) (#5540)`;
  the suite was wired by `d8a52b369a7a` (#5671).
- `engine/prophet_bridge.py:811` defines `plan_clock_date()`, consumed at
  `scripts/build_prophet.py:852,1013`, `engine/prophet_management.py:199`,
  `engine/prophet_arena.py:486`.
- Measured today on `git show origin/main:site/prophet/index.json`:

  ```
  open rows (not closed):                       204
  open rows with clock_age_days > horizon_days:   0
  open rows with phase == 'overtime':             0
  open-row phase counter: triggered_pre_t1 130 · pre_trigger 72 · invalidated 2
  (open rows with the OLD misanchored reading, age_days > horizon_days: 28)
  ```

- Read: the producer and a reader now compute "past its horizon" on the same clock, and both say
  zero. The 28 is the artefact of the retired anchor and is exactly the discrepancy #5540 named.
  **CONFIDENT.**

---

## 3. What this changes, and what it does not

**For the MP-1 shell wave (LAB-0 §6.4):** the two hard data dependencies that R4 refused to waive
are closed. MP-1's own gate language should be re-read against §2.11 and §2.12 rather than against
R4's prose, and the "60% BLOCKED_DATA" framing that shaped several R4 design decisions no longer
describes the payload. The R4 reference's own fixture is deliberately frozen at 2026-08-13 and is
**not** rebaked by this cycle — a reference may not replace the population a critic is judging it
on — so the reference and the current payload legitimately disagree, and this document is the
record of how.

**For the R5 reviewers:** three items are live in production and none of them is caused by this
cycle — **DA-002** (stance ink ≡ direction ink in `theme.css`), **PRC-303** (the chase caution
never consults the zone state), and the printed-null half of **VTC-301**. The R5 reference does
not depend on any of them; the Lab plane carries no stance ink at all (`DESIGN_NOTES` §2.2), and
it inherits R4's printed null. They are listed so the migration inherits an accurate list rather
than a five-day-old one.

**Not determined, and what would settle it**

| Gap | What would settle it |
|---|---|
| VTC-302 (chart-stroke salience) | measure the production `.pv-chart svg *` stroke and ink against the card plane in both themes, and against the R4 values |
| PRC-306 end-to-end reachability | drive the production board: click `Show all` on `#us-standouts` and count visible `.pvcard` against `live_total` |
| PRC-303 live incidence | join the caution's trigger conditions against `site/prophet/index.json` `entry_signal` / `alpha_entry` and count rows that would render both |
| PRC-302 estate-wide | search the whole template estate for duplicate gate copy, not just `tier_preview.js` |
| DA-003 residual | re-verify FTI's rendered stance in `compare.html` |
| G-D archaeology depth | only #5541 and #5540 were traced through `git log`/`gh`; the other ten items rest on current-state receipts alone |

---

## 4. Method

Receipts were gathered by two read-only census passes over `origin/main` at `d772fbd6f884` in a
sparse worktree (`site/` and `data/` read via `git show`, never from disk). Every integer above
carries the command that produced it. The verdict column is this session's; the census passes were
instructed to gather evidence and to mark anything undeterminable as insufficient rather than
guess it, and six of the twelve items came back with an explicit uncertainty that survives into
§3's gap table rather than being resolved by assertion.
