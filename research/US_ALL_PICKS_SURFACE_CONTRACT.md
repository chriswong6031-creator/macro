# US ALL-PICKS SURFACE — FROZEN DATA CONTRACT

**Status:** FROZEN 2026-08-05 · **Authority:** operator order 2026-08-05, adjudicated in
`research/PROPHET_US_TREND_INTELLIGENCE_MASTERPLAN_BY_FABLE.md` §W7 ·
**Consumers:** the designer lane that builds the ranked all-picks surface.

This document freezes **what data the surface receives, how it must be ordered, what states
exist, and what must be said honestly**. It is the contract, not the design: palette,
typography, layout, component choice, motion and copy voice belong to the designer lane
(DESIGN_DOCTRINE + the `frontend-design` skill). Where this contract constrains copy it does
so only to keep the surface *honest* — it never dictates how the page looks.

Read §1 before anything else. It contains the one fact that decides the whole layout.

---

## §0 ACCEPTANCE GATES (binding on the surface build; inline these in the spawn prompt)

- **A0.1** The list shows the **whole analyzed universe** (~1,579 names in this checkout,
  ~2,932 on the host) with every row reachable — not a capped slice. "Show all picks" means
  all, with pagination/virtualisation, not a longer top-N.
- **A0.2** Every row carries a **stance or a state in plain words** (Doctrine Law 1/2). A
  row that is on no lane still says why in plain words. No raw slugs, no untranslated stats,
  no internal study names on the glance tier.
- **A0.3** The **ordering key of every tier is printed on the surface**, not implied. A user
  must never have to guess why row 400 is above row 401.
- **A0.4** The two graded records are **named separately** wherever a track record appears
  (§6). Never one blended number.
- **A0.5** **Bilingual parity** (EN/ZH), light + dark, at 375px and desktop. No translated
  text in `title=` attributes (CI-guarded).
- **A0.6** No falsifier/refutation language anywhere front-facing (operator 2026-07-27).
- **A0.7** Per-step visual crops (light + dark + zh) posted in the PR body.

---

## §1 THE CONSTRAINT THAT DECIDES THE LAYOUT

**The priority score does not exist for most of the universe.**

`us_board_rank.score_rows()` — the function that computes `us_prophet_v1` and its five
itemized legs — is run by the builder on the **buy lane only**. Measured coverage in the
Context Vector store: **3.2% of stamped rows carry a score** (`data/us_prophet_rank/README.md`,
2026-07-31 dry run; ~50 of ~1,540 names). The live board says the same thing from the other
side: on `site/factordata/us_standouts.json` (as_of 2026-07-31), `prophet.score` is present
on the 60 buy rows and **null on all 74 watch/leaders/laggards rows**.

So a single column headed "Score", sorted descending over 1,579 rows, would be **97% empty**
— and filling it would be a *scored* change, not a display one: the `edge` leg is
`alpha_percentiles(pool)`, a cross-sectional percentile **within the scored pool**, so
widening the pool moves every existing board score. That needs its own prereg and operator
ratification (§W7.5), and it is explicitly NOT this build.

**Consequence, and it is not a compromise — it is the honest shape:** the surface is a
**tiered ranked list**. Best picks at the top, ordered by the real score; everything else
below in stated, disclosed order. A user scrolling from row 1 to row 1,579 always knows what
ordered the region they are in.

---

## §2 DATA SOURCE

One source of truth: the **US Context Vector store**, read through its own reader — never by
globbing parts.

```python
from engine import us_context_vector as ucv
rows = ucv.load_candidates(months=["2026-08"], columns=[...])   # latest stamp_date
```

The surface renders **one `stamp_date`** — the latest — as a point-in-time board. Earlier
stamps are history, not the live view.

Optional second source, for the track-record block only (§6): the grade store, via
`engine.us_prophet_grades.load_grades()` / `load_graded_frame()`, and the miss-audit's
`priority_score_scorecard` block in `data/prophet_miss_audit/latest.json`.

---

## §3 PER-ROW FIELDS (the contract)

Every field below is READ from the store. **The surface originates nothing** — no new score,
no new composite, no derived rank beyond the ordering rules in §4 (glass-box law; A7).

### 3.1 Required on every row (glance tier)

| Field | Source column | Notes |
|---|---|---|
| `rank` | *computed by §4* | 1-based position in the full ordered list. Continuous across tiers. |
| `ticker` | `ticker` | |
| `name` | `name` | Display name; prettified fallback if null — never render the slug alone. |
| `sector` | `sector` | Display name, never a `us_sector_*` slug. |
| `tier` | *computed by §4* | `A` / `B` / `C` — which ordering region the row is in. |
| `state` | *derived, §5* | The plain-word why-state. One of the fixed vocabulary in §5.1. |
| `lane` | `lane` | `buy` / `watch` / `leaders` / `laggards` / `not_on_board`. Drives filters (§7), not the label. |

### 3.2 Required where present (null is a state, never a zero)

| Field | Source column | Coverage |
|---|---|---|
| `score` | `prophet_score` | ~3.2% (buy lane only) — **null is normal, print it as "not scored", never as 0** |
| `score_legs` | `prophet_signal` · `prophet_entry` · `prophet_edge` · `prophet_runway` · `prophet_quality` (values) and `prophet_*_points` (weighted points) | same 3.2% |
| `alpha` | `alpha` | the §4 tier-B/C ordering key |
| `stage` | `stage` | `live` / `setting_up` / `ran` / `blocked` |
| `tier_cascade` | `tier_cascade` | `T1` / `T2` / `T3` — **never shown raw**; feeds §5 |
| `eligible` | `eligible` | the gate's own verdict |
| `near_miss_reason` | `near_miss_reason` | `not_topped_veto` / `freshness_expired` — **never shown raw**; feeds §5 |
| `theme` | `theme_primary_name` + `theme_heat_rank` | display name; rank 1 = strongest of 47 |
| `days_to_report` | `days_to_report` | for the "reports in N days" chip |
| `signal_asof` | `signal_asof` | for "N sessions ago" |

### 3.3 Explicitly OUT of the glance tier (Tier 2 / detail only)

`ext_z`, `alpha_percentile`, `relay_*`, `turnover_pctile_*`, `regime_*`, `context_dims`,
`gate_weight`, `bars_to_cross`, `fresh_bars`, every `context_api` dimension column, and all
raw statistics. These belong in hover/popover/detail (Doctrine Law 2/3), never on the row.

---

## §4 ORDERING (frozen; the surface must print which rule is in force)

Three tiers, concatenated. `rank` runs continuously 1..N across all three.

| Tier | Membership | Ordering key | Printed as |
|---|---|---|---|
| **A** | `prophet_score` is not null | `prophet_score` DESC, then `ticker` ASC | "Ranked by priority score" |
| **B** | score null AND `eligible` is true | `alpha` DESC, then `ticker` ASC | "Ranked by residual alpha — not yet scored" |
| **C** | everything else | `alpha` DESC, then `ticker` ASC | "Ranked by residual alpha" |

Rows with a null `alpha` sort to the END of their own tier, ordered by `ticker`, and are
labelled **"unranked — no alpha this night"**. That is a stated null, not a silent bottom.

**Why `alpha` and nothing else.** It is a single existing column, it is the only leg
`research/US_BOARD_MEASUREMENT.md` found positive-IC, and using one field keeps the ordering
glass-box. **Do not blend `alpha` with anything** — a conviction×timing style blend is
forbidden (DNR §1 row 49), and any new composite is a scored change requiring a prereg.

**Coverage receipt for the key (measured 2026-08-05, `site/factordata/us_standouts.json`
as_of 2026-07-31).** `alpha` reaches the store from `profile_rows` = the builder's `cand`
list, which IS the board's stated universe: `wide["universe"] = len(cand) = 1,579`. On the
live artifact it is non-null on **134/134 rows across all four display lanes** (buy 60,
watch 48, leaders 14, laggards 12) while `prophet.score` is non-null on **60/134 (buy
only)** — which is precisely why `alpha` is the fallback key and `prophet_score` cannot be.

**Residual to verify before the surface ships.** The Context Vector store's spine is
`sig_verdict` — every *analyzed* name — which can be wider than `cand`. The exact
store-side `alpha` coverage is therefore unmeasured until the first real stamp lands (the
store was empty at contract time). **The surface build must print the measured
`alpha`-null count in its PR body** and confirm the unranked bucket is a small tail, not a
silent majority. If it is not a small tail, the ordering rule is what changes — not the
labelling.

**Ties and stability.** `ticker` ASC is the tiebreak everywhere, so the order is reproducible
night to night and a screenshot can be re-derived from the store.

---

## §5 THE PLAIN-WORD STATE (Doctrine Law 1 + Law 2)

### 5.1 Fixed vocabulary — the surface may use ONLY these

Derived from store columns by the rules in §5.2. EN and ZH are both frozen; the designer
lane may restyle them, not reword them.

| `state` | Tier 1 English | Tier 1 中文 |
|---|---|---|
| `act` | Ready to act | 可以行动 |
| `get_ready` | Getting ready | 正在酝酿 |
| `already_ran` | Already ran — don't chase | 已经跑过 — 别追 |
| `watch_hot` | Watch — running hot | 观察 — 短期过热 |
| `watch_stale` | Watch — signal went stale | 观察 — 信号已过期 |
| `stand_aside` | Stand aside — trend is down | 回避 — 趋势向下 |
| `no_setup` | No setup yet | 尚无形态 |

### 5.2 Derivation (first match wins; deterministic)

1. `stage == "blocked"` → **`stand_aside`**
2. `stage == "ran"` OR `lane == "leaders"` → **`already_ran`**
3. `eligible` is true AND `lane == "buy"` → **`act`**
4. `eligible` is true → **`get_ready`**
5. `near_miss_reason == "not_topped_veto"` → **`watch_hot`**
6. `near_miss_reason == "freshness_expired"` → **`watch_stale`**
7. otherwise → **`no_setup`**

**Banned on the glance tier** (Doctrine Law 2, and these are the exact tokens this data
tempts you with): `not_topped_veto`, `freshness_expired`, `stoch_ob`, `stoch_bear`,
`macd_bear`, `T1`/`T2`/`T3`, `tier_cascade`, `us_prophet_v1`, `alpha_percentile`, `rank-IC`,
`P@k`, `excess vs SPY`, `shadow`, `prereg`, `gauntlet`, any bare `n=`. Every one of them has
a Tier-2 home: the row's detail/popover.

**Never front-facing anywhere** (operator 2026-07-27): falsifier, refuted, tripwire fired,
证伪. Those verdicts live on the Calibration Lab, below the fold.

---

## §6 THE TWO GRADED RECORDS — NAMED SEPARATELY, ALWAYS

Wherever the surface shows a track record it must show **which population it is**. They are
different questions and they must never appear as one number (§W7.2; §2.3's board-marks vs
closed-plan warning is the precedent).

| Record | What it is | Honest label (EN) | 中文 |
|---|---|---|---|
| **Curated** | the picks the system actually made — board buy lane / plans | "Our picks" | 我们的选股 |
| **All picks** | every name we ranked, graded the same way | "Every name we ranked" | 全部评分名单 |

Rules:
- The all-picks record is **new and still accruing** — H=10 marks land ~11 sessions after a
  stamp, H=21 ~22. Until it has depth, the surface says so in plain words ("still building
  — first results in a few weeks"), and prints **no** headline rate.
- Neither record may be described with the word *validated* (CI-guarded).
- The curated record's population is **unchanged** by this program. Do not recompute it, do
  not re-label it, do not merge the two.

---

## §7 CURATED LANES BECOME FILTERS

The existing lanes stay, expressed as filters over the one ranked list — not as separate
boards. Default view = **all rows, tier order**. Filter chips (multi-select, additive):

`Featured` (`featured` true) · `On the board` (`lane == "buy"`) · `Already ran`
(`lane == "leaders"` or `stage == "ran"`) · `Setting up` (`stage == "setting_up"`) ·
`In a hot theme` (`theme_heat_rank <= 5`) · `Reports soon` (`days_to_report <= 7`)

Each chip prints its own count. A filter that would return zero rows says so in plain words
rather than rendering an empty table. **Filtering never re-ranks** — rows keep their global
`rank`, so a filtered view is a subset of the same list, and the user can see that row 3 and
row 812 are both "on the board".

---

## §8 SCALE — 1,579 ROWS MUST STAY USABLE

- **Paginate or virtualise.** Page size 50 default. Never render 1,579 DOM rows at once, and
  never truncate silently — the total count is always visible ("1,579 names ranked").
- **Tier A is the landing region.** The page opens at rank 1; the tier boundary between A and
  B is a visible, labelled divider carrying the §4 ordering sentence for the region below it.
- **Search by ticker/name** jumps to the row and shows its rank in context, so a user asking
  "where is PLTR?" gets an answer instead of a scroll.
- **Mobile (375px):** ticker, name, state, rank. Score and legs demote to the detail sheet.
  Do not compress jargon to fit — demote (Doctrine Law 4).

---

## §9 WHAT THE SURFACE MAY NOT DO

- Not compute a score, a composite, a blend, or any ordering key other than §4.
- Not change membership, admission, plan intake, or any gate. This is a VIEW.
- Not present the all-picks graded record as the system's track record, or pool it with the
  curated one.
- Not print a headline hit-rate from a cohort the scorecard marks `thin`.
- Not show a null as a zero — "not scored" and "0" are different facts.
- Not use LLM-generated text for any state, score, or reason. The §5 vocabulary is fixed.

---

*Related: `research/PROPHET_US_TREND_INTELLIGENCE_MASTERPLAN_BY_FABLE.md` §W7 (the
adjudication), `docs/DESIGN_DOCTRINE.md` (content law), `data/us_prophet_rank/README.md`
(both stores' integrity rules and coverage receipts), `research/US_BOARD_MEASUREMENT.md`
(why `alpha` is the tier-B/C key), `research/DO_NOT_REBUILD.md` §1 row 49 (the population
fence).*
