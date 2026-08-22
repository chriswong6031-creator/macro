# XPV2-SC-R3B.1 — EN/ZH copy ledger, Lane A (authority hero repair)

Commission: `research/reference_integrity/mastermind-xpv2-sector-r3b-1/COMMISSION.md`
Fix packet items covered by this lane: **R3B1-01 · 02 · 03 · 04 · 05 · 06 · 07 · 13**.

This ledger records **every EN/ZH pair Lane A rendered into the successor
artifact**, whether restored from a producer field, restored verbatim from a
production template, or authored by this lane. It supplements — it does not
replace — `research/reference_integrity/mastermind-xpv2-sector-r3b/copy_ledger.md`,
which still governs every string the predecessor cycle minted.

Every pair below was read back out of the **built** artifact
(`proposal/MASTERMIND_SECTOR_CENTRAL_R3_CANDIDATE.html`) with headless Chromium
on 2026-08-22 — the "rendered" column quotes `innerText`, not source — so no row
is retyped from memory.

**Provenance vocabulary** (same three values the predecessor ledger uses, plus one):

- **producer-field** — the whole string is a value read out of a fixture
  artifact at the frozen epoch. The reference supplies no words at all.
- **bound-from-production (verbatim)** — the words are copied unchanged from a
  named production template/JS file; the numbers inside them are producer values.
- **bound-from-production (recomposed)** — production's own words, re-punctuated
  or re-ordered for the R3 grammar, with **no semantic change**. Every instance
  is itemised in §4.
- **authored-new** — this lane wrote both halves; no production string exists.

---

## 1 · R3B1-01 — the position-sizing directive

Producer: `basketdata/baskets.json → theme_intel.regime_sizing`
(`schema vol_regime.sizing.v2`; at the frozen fixture `active: true`,
`gross_scalar: 0.81`, `mech_scalar: 0.81`, `regime_caution: 1.0`,
`scored_cut: 1.0`, `regime: "normalizing"`,
`caution_passport.verdict: "display-only"`).
Render site: `build/views/overview.html`, `sizingHTML()`, marker `data-r3b1="01"`.
Inert-when-calm rule reproduced from **`templates/sector_central.html.j2:2888`**
(`if(!rs||!rs.active||(rs.gross_scalar||1)>=1.0) return '';   // inert when calm`).

| EN | ZH | provenance | note |
|---|---|---|---|
| `positions sized to 81%` | `仓位缩至 81%` | bound-from-production (verbatim), `sector_central.html.j2:2919` | `81` is `Math.round(gross_scalar*100)` — production's own rounding, no other arithmetic. |
| `How position sizing is set` | `仓位如何设定` | authored-new | Accessible name for the receipt control (`.r3-vh`). Production's chip has no accessible name at all; house law forbids `title=` and a single-language `aria-label`. |
| `How it's set: volatility target 81% → 81%` | `计算方式：波动率目标 81% → 81%` | bound-from-production (verbatim), `:2905-2912` | Receipt line 1. `risk regime` / `signal mix` legs and the `N theme(s) eased to hold-only` clause carry production's guards and are correctly inert on this fixture (`regime_caution` and `scored_cut` are both 1.0; zero themes carry `regime_demoted`). |
| `Read from US volatility, applied on every market page. Volatile markets get smaller position sizes. This does not change the basket ranking.` | `依据美国波动率读数，各市场页面同用此读数。波动加大时降低仓位；不改变篮子排序。` | bound-from-production (verbatim), `:2907` / `:2911` | Receipt line 2. Production joins lines 1 and 2 with ` \| `; the reference separates them with a newline (§4, R-1). |

Not rendered, correctly: production's `showNote` branch (the risk-off shadow
caution and its Tier-2 caution-passport receipt) requires
`regime_caution_shadow < 100` **and** a mapped `regime` label. This fixture has
`regime_caution_shadow: 1.0` and `regime: "normalizing"` (unmapped), so the
branch is inert and **no stand-in copy was invented for it**.

---

## 2 · R3B1-02 — the leadership methodology caveat

Producer: none — this is production template copy governing
`si_handoff.json → theme_context.leadership`.
Render site: `overview.html`, `paintContext()`, marker `data-r3b1="02"`.
Source: **`templates/sector_central.html.j2:2155`**.

| EN | ZH | provenance | note |
|---|---|---|---|
| `How this works` | `原理说明` | bound-from-production (verbatim), `:2155` | The control's **visible** label. Production renders it as `ⓘ How this works`; the glyph is dropped because §9.3 of the design spec forbids typed marks (the receipt's `?` ring is drawn in CSS). |
| `Shape read only — not a forecast.` | `仅为形态读数，非预测。` | bound-from-production (verbatim), `:2155` | Clause 1 of the disclosure. Promoted to **first** line (§4, R-2). |
| `Trailing-momentum rank names Memory, HBM & Storage first; skips the most recent ~3 weeks by construction; suggested weights unchanged.` | `趋势动量排名以内存、HBM 与存储居首；设计上跳过最近约3周数据；建议权重不变。` | bound-from-production (verbatim), `:2155` | Clause 2. The theme name is the producer's `trailing_leader.name` / `.name_zh`, interpolated exactly as production interpolates it. |

---

## 3 · R3B1-03 · 04 · 05 · 06 · 07 · 13

### 3.1 R3B1-03 — migration note

| EN | ZH | provenance | note |
|---|---|---|---|
| `Money is moving into Software and out of Semiconductors.` | `资金正流入软件，流出半导体。` | **producer-field** — `si_handoff.json → theme_context.migration.note_en` / `note_zh` | Rendered verbatim, escaped, `data-r3b1="03"`. Production's site is `sector_central.html.j2:2130`. Absent field renders as absence. |

### 3.2 R3B1-04 — the working destination

| EN | ZH | provenance | note |
|---|---|---|---|
| `Open the playbook` | `打开操盘手册` | bound-from-production (verbatim), `sector_central.html.j2:2163` | Real `href="allocation.html"` + `data-ref-nav` (the recorder path every other off-page destination on this board uses). Production types a trailing `→`; the R3 system draws the chevron as a CSS border (`.r3-more::after`), so the arrow character is dropped — §4, R-3. |

### 3.3 R3B1-05 — hero enrichment

Producer: `baskets.json → theme_intel.themes[].perf.<win>.rel`,
`themes[].pulse_rank_delta_5d`, `baskets[]`, `categories[]`. Looked up through
`REF.themeById()`, the shim's mirror of production's `themeById()`
(`sector_central.html.j2:2877`). Production sites: `:2926`, `:2928-2933`.

| EN | ZH | provenance | note |
|---|---|---|---|
| `was #1` | `原第一` | bound-from-production (verbatim), `:2143`, `:2929` | Pre-existing in the predecessor; now the head of the enriched line. `data-r3b1="05a"`. |
| `-9.6% 20d` | `-9.6% 20日` | **producer-field** (`memory_storage.perf.20d.rel = -0.0959`) | Unit deviation recorded in §4, R-4. |
| `+11.5% 20d` | `+11.5% 20日` | **producer-field** (`big_pharma.perf.20d.rel = 0.1154`) | `data-r3b1="05b"`. |
| `climbing fast` | `快速上行` | bound-from-production (verbatim), `:2933` | Guarded on `pulse_rank_delta_5d > 0` (here `9`). |
| *(5d clause)* `-N.N% 5d` | `-N.N% 5日` | **producer-field**, guarded | Production renders the outgoing leader's 5d **only when it is negative** (`:2930`). This fixture's `memory_storage.perf.5d.rel` is `+0.0433`, so the clause is correctly inert — **NOT_EXERCISED on this fixture**, code path present. |
| `· 49 themes · 15 categories` | `· 49 个主题 · 15 个分类` | bound-from-production (verbatim), `:2926` | `.length` over two full producer lists — the same mirror production performs. `data-r3b1="05c"`. |

### 3.4 R3B1-06 — context score terminology

No new pair. `theme_intel.themes[].score` already carries exactly one name on
every context surface of this build — **Strength / 强度** (`map.html:84`, marker
`data-r3b1="06"`), **Strength / 强度** in the scatter tooltip (`map.html:576`)
and **Strength score / 强度评分** in the selected-object list (`map.html:628`,
production's own label at `sector_central.html.j2:2991`). See §5 for the residual
exposure this leaves on Overview.

### 3.5 R3B1-07 — S&P thin-coverage sentence

Producer: `marketdata/subsector_confluence.json → coverage`
(`n_subsectors: 113`, `n_gateable: 65`, `n_thin: 48`). Render site:
`confluence.html`, `paintFoot()`, marker `data-r3b1="07"`.

| EN | ZH | provenance | note |
|---|---|---|---|
| `65 of 113 subsectors have enough live data to time.` | `113 个子行业中，65 个实时数据足够，可用于计时。` | bound-from-production (recomposed), `templates/subsectors.js:220-221` | Only the sentence boundary changed (a full stop replaces the ` · ` that joined it to the thin clause). Noun swaps per universe, unchanged. |
| `48 are too thin to time and are omitted from the timed table.` | `另有 48 个数据过于稀疏，无法计时，未列入下方计时表。` | bound-from-production (recomposed), `templates/subsectors.js:220-221` | **This is the corrected clause.** Production says `48 thin (listed in the table, not timed)`; the 48 are gate-dropped and never enter `subsectors[]` at all (113 − 65 = 48, and the table renders exactly 65 rows). §4, R-5. |

Renders on S&P only at this fixture: Nasdaq and Russell carry `n_thin: 0`, so
the thin clause is inert there; `basket_confluence.json` emits no `n_gateable`,
so the Baskets tab renders **nothing** here — the BLOCKED_DATA ruling stands and
no Baskets thin disclosure was invented.

### 3.6 R3B1-13 — the Stock-picks figure label

Producer: `marketdata/subsector_confluence.json → double_gated.double_buy[].combined_score`.
Contract: **`engine/subsector_confluence.py:322-324`** — *"combined_score = stock
cascade weight × subsector buyability factor"* — value written at **`:347`**
(`round((m["stock_weight"] or 0.0) * sub_factor, 4)`).
Production's own header for that exact field: **`templates/subsectors.js:330`**.
Render site: `confluence.html`, `paintPicks()`, marker `data-r3b1="13"`.

| EN | ZH | provenance | note |
|---|---|---|---|
| `Conviction` | `综合把握` | bound-from-production (verbatim), `templates/subsectors.js:330` | Used as the `.r3-cols` column header **and** as a `.r3-vh` accessible name inside every picks row, so the figure is never a naked decimal to a screen reader either. Not "Score", "Probability", "Confidence" or "Strength" — none of those is a claim the contract makes. |
| `Stock` | `个股` | bound-from-production (verbatim), `templates/subsectors.js:330` | Column 1 header. |
| `Why it is here` | `入选原因` | pre-existing in this build (`overview.html:676`, `confluence.html:669`; picks header at `confluence.html:753`) | Column 3 header — reused, not minted. |

---

## 4 · Recomposition register — every departure from production's exact wording

| # | What changed | Why | Semantic change? |
|---|---|---|---|
| R-1 | The sizing receipt's two halves are separated by a **newline** instead of production's ` \| ` pipe. | Commission R3B1-02/§"no paragraph tooltip": a receipt reads as short statements, not a run-on. `.r3-tipbox` gained `white-space:pre-line`; every pre-existing single-clause tip carries no newline and is byte-unchanged. | None. |
| R-2 | The caveat's two clauses are **re-ordered** — `Shape read only — not a forecast.` leads, the construction-lag clause follows. | The non-forecast caveat is the clause that governs how the whole band may be read (DAC-102). A reader who reads one line must read that one. | None — both clauses render, verbatim, in one disclosure. |
| R-3 | Trailing `→` dropped from `Open the playbook →`; trailing `ⓘ` dropped from `ⓘ How this works`. | DESIGN_SYSTEM_SPEC §9.3: marks are drawn (CSS borders/pseudo-elements), never typed. Both controls draw their mark. | None. |
| R-4 | `perf.<win>.rel` is rendered **×100** (`-9.6%`), not through production's `fmtPct()` (which appends `%` to the raw fraction and prints `-0.10%`). | The identical producer byte (`-0.0959`) is already rendered `-9.6%` by the action board **on this same view** (`overview.html` `rowHTML()`, from `action_board.json`'s `perf_20d_rel`, which `scripts/build_site.py:1784` copies from the same theme record). Printing one number at two magnitudes on one screen would make the reference teach a production unit defect as migration law. | The producer byte is unchanged; only its scale is stated once, consistently. **Flagged for Sol** — see §5. |
| R-5 | `48 thin (listed in the table, not timed)` → `48 are too thin to time and are omitted from the timed table.` | Commissioned repair R3B1-07 / DAC-105. Production's wording is false against its own payload. | Yes — deliberately. This is the commissioned correction, and it is a **production-repair delta for R3C**, not a licence for the reference to re-word producer copy generally. |

---

## 5 · Open items this ledger hands forward

1. **R-4 unit deviation (§4).** Lane A rendered the hero's relative performance at
   the same magnitude the board uses. If Sol wants byte-identical fidelity to
   `fmtPct()` instead, the change is one helper in `overview.html`
   (`relTxt()`), and the correct home for the repair is then production's
   `fmtPct` call sites, not the reference.
2. **R3B1-06 residual.** The Overview action board's figure column is headed
   `Score / 评分` (reference-authored — production renders the number bare,
   `_us_act_now_board.html.j2:490`). Its value is `action_board.json`'s `score`,
   which `scripts/build_site.py:1784` sets to `th.get("score")` — i.e. it **is**
   `theme_intel.themes[].score`, verified identical for all 33 theme rows in this
   fixture. The commission's R3B1-06 explicitly carves that column out
   ("Do not rename the independent action-board score"), so Lane A did not touch
   it, and DAC-107's one-measure-two-names exposure therefore survives on
   Overview. Sol's call.
3. **`Conviction` collides across two artifacts.** `Conviction / 综合把握`
   (Confluence picks, `combined_score`) and `Conviction / 信心`
   (Overview trace card, `sectordata/sector_central.json → conviction.score`) are
   two different measures sharing one EN word. Both labels are production's own,
   so neither is the reference's to rename. Producer-side naming item for R3C.
