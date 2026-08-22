# XPV2-SC-R3B — Fresh Critic Review: Data / Authority

Reference ID: `mastermind-xpv2-sector-r3b` · Surface: `sector_central.html`
Role: Data / Authority Critic · Finding prefix: `DAC-1xx` (see §0.1 — deliberate deviation)
Review date: 2026-08-22 · Reviewer: Claude Opus 5 (`claude-opus-5`), fresh seat.

**FINAL VERDICT: BLOCK** — two HIGH findings (`DAC-101`, `DAC-102`) are producer/authority
regressions on the Overview hero that must be corrected in the reference before it becomes
production migration law. Five further findings ride as CONDITIONS.

---

## 0. Seat, method, disclosures

### 0.1 Identity and independence

- Model: Claude Opus 5. Session opened cold on this commission; no participation in R3B
  design, build, QA, fix wave, or adjudication, and no prior R3B artifact was read before
  the first-pass freeze except as disclosed in §0.3.
- Work performed in a fresh worktree off `origin/main` (`a595964520da`), branch
  `claude/xpv2-sc-r3b-critic-data-authority`.
- **Finding-ID deviation (deliberate, disclosed).** The commission assigns `DAC-001, DAC-002, …`.
  I use `DAC-101…` instead because the `DAC-00N` namespace is *already occupied and actively
  cited* inside this program: `ADJUDICATIONS.md` §A3 cites R2's `DAC-001/002`, §A4 refutes
  R2's `DAC-005`, and `ORCHESTRATOR_ADJUDICATIONS.md` §9 carries R2's `DAC-005`/`DAC-008`.
  Minting a second `DAC-001` would make the identifier ambiguous in the same governance
  record. If Sol prefers strict compliance, renumber `DAC-101→001` etc.; the content is
  unaffected.

### 0.2 Method

Two-pass with rationale quarantine, per the shared review law.
First pass used only: the frozen candidate, `BUILD_MANIFEST.json`, the R3A pack
(fixture/receipts/provenance, `ADJUDICATIONS.md`, producer binding matrix, capability
disposition ledger, routing contract, access/hydration contract), and current production
producer code/tests. First-pass verdict and finding IDs were **written to disk at
`2026-08-22T13:05:05Z`** (`reviews/evidence_data_authority_fresh/FIRST_PASS_FROZEN.md`)
before any quarantined file was opened.

The candidate was rendered and probed independently (headless Chromium via a scratchpad
Playwright venv, 1440×1000, `file://` load of the frozen artifact). Author screenshots and
the QA report were not used as proof of anything.

### 0.3 Quarantine breach — disclosed

One row of `build/QA_ATTACK_REPORT.md` (row `QA3-03`) was exposed pre-freeze by a
`grep -rn 'factor_z'` over `build/`, because the report lives inside the code directory.
**Materiality: nil.** I had already (a) byte-scanned the fixture and found the two bare
`NaN` tokens, (b) traced them to `factor_z`, and (c) identified the
production-unreachable-render consequence, before the grep ran. The leaked row confirmed my
own note; it did not seed it. All later searches ran through a quarantine-excluding wrapper.
Full record: `reviews/evidence_data_authority_fresh/BREACH_LOG.md`.

### 0.4 No repair work performed

No candidate, fixture, build script, manifest, baseline, proposal, continuity, verdict,
production, or design-system file was modified. No `approval.yml` was produced. No authority
verdict was issued. R3C was not started. **Only this review file and my own review-evidence
directory were written.**

---

## 1. Artifact verification (all PASS)

| check | result |
|---|---|
| Candidate SHA-256 @ `dc84f78cddf04d9be90e9249126f9767de5725a6` | `19553267d3f51659503fc836da6b6bdaa06afc9cdd607aafb1bb795e46c47dca` — **matches commission** |
| Same hash @ `origin/main` and in worktree | identical (5,442,009 bytes) |
| `BUILD_MANIFEST.json` @ frozen SHA | `a7b9ae8ab3f13f106478f30c7de8b46672662832b09224fb7e182d0cb6b2d396`, identical on main |
| Post-freeze diff, whole R3B mockups+research trees | only `manifest.yml` + `proposal.yml` — the `status: draft→in_review` flip and `frozen_sha` fill-in (PR #6198). No semantic change. |
| R3A fixture receipts recomputed | **18/18 match** |
| `BUILD_MANIFEST` inputs vs source-of-record | **23/23 match** (17 R3A fixture + 6 R3B supplement) |
| Embedded data-registry blobs vs fixture bytes | **22/22 byte-identical** (after the documented `<\/script` escape) |
| R3B supplements vs `git show 4c55fe43:site/...` | **5/5 byte-identical** at the declared capture epoch |
| `templates/si_workspace.js` vs manifest hash | identical at capture epoch, frozen SHA, and `origin/main` — router genuinely verbatim |

**The data substrate invents nothing.** Every rendered value traces to producer bytes that
recompute to their receipts.

---

## 2. POST_FREEZE_DRIFT

Diffing every Sector Central producer, template, and config between the frozen SHA and
`origin/main` (28 paths: `build_sector_central.py`, `build_site.py`, `engine/sector_central.py`,
`engine/subsector_confluence.py`, `narrative_emergence.py`, `thematic_desk.py`, `build_baskets.py`,
`build_rotation_events.py`, `build_subsector_rotation.py`, `oracle_nightly.py`,
`build_sp500_heatmap.py`, `build_index_leadership.py`, `build_sector_cycles.py`,
`oracle/timemachine.py`, `sector_central_grader.py`, `theme_context.py`, `us_act_now.py`,
`sector_central.html.j2`, `_us_act_now_board.html.j2`, `si_workspace.js`, `subsectors.js`,
`config.yml`, …):

**Exactly one diff:** `config.yml` → `notify.site_url`, retiring the GitHub Pages mirror in
favour of the production origin (`DEC:B1-MACRO-PRIVATE-CUTOVER`).

- Not a schema, route, authority, access, producer, or capability change.
- `sector_central_gate: {gated: true, preview_rows: 3}` **unchanged** — A9 still holds.
- The candidate contains **0** `github.io` references, so the cutover cannot strand a baked link.

**POST_FREEZE_DRIFT does not invalidate migration law.**

---

## 3. Producer audit — what holds (verified, not assumed)

These were attacked and survived. Recorded so a later cycle does not re-derive them.

**Overview / the historical R2 failure.** Ledger #26's invariant holds: `HND`
(`si_handoff.json`) is referenced only by `paintContext()`, `factor_season`, and the
`si-read-overview` strip attributes — never by `laneRows()`, `laneCount()`, `fillLane()`, or
`REF.renderActNow()`. **A context leader cannot become Buy now.** The live fixture contains
the exact trap: `leadership.challenger` is **Silver Miners** and it is #3 in
`leadership.strength`, yet the action producer files it under `on_the_run` ("In favour —
don't chase") and the reference renders it there. The reference additionally *adds* a
governed caveat production lacks — "Display only — it does not set a lane below. /
仅供展示 — 不决定下方分组归属。" That is a genuine improvement on the R2 defect class.

*(I first suspected the hero's "Taking the lead ← `strength[0:2]`" was a reference-invented
promotion that discards the producer's own `challenger` field. It is not: it is production's
own construction at `sector_central.html.j2:2148`, ported verbatim. Refuted before filing.)*

**Six keys, five columns.** `LANES` folds `hold`+`avoid` into one `stand_aside` column;
`laneRows('stand_aside')` is `hold.concat(avoid)` — never re-sorted, never re-merged.
Rendered lane counts **4 / 5 / 5 / 3 / 27** equal the producer arrays exactly, computed off
the FULL board in every access state (ledger #3).

**Premium split reproduces `split_actnow()` exactly.** Rendered withheld counts
`1 + 2 + 2 + 0 + 24 = 29` = the producer's own `panels.actnow.locked = 29`; `avoid` correctly
receives zero preview budget because `hold` spends it first. Note for the record: the
producer's `preview: 3` is a **per-lane cap**, not a row count — 15 rows are actually visible
of `total: 44`. The candidate never misprints `preview` as a count.

**Bottoming Watch copy law.** `signal` and `timing_state` appear in the view only inside
comments stating they are never read; both are absent from render. Watch-only language and
`bottoming_authority.null_disclosure_en` render verbatim. The merged "All 3 rows: cycle turn
signal — watch only · may be bottoming" aggregate is **true of all three rows** (verified
against the producer), and the row-specific `gate_conflict` chip correctly stays on the one
row it applies to.

**A2 (Moving).** Binds exactly `rotation_events`, `sector_fragmentation`, `subsector_rotation`,
`oracle_turn_desk`, `oracle_tape_onset`, plus `baskets.json` for the `si-read-moving` strip
(itself a binding-matrix Moving row). The sole `si_handoff` mention is a comment stating it is
not a Moving source. No invented handoff-derived story.

**A3 (Map `reco` CONFLICT field) — de-amplified.** `reco` renders as a tertiary `.r3-tag` in a
column headed **"Noted / 备注"**, under production's verbatim context disclaimer *plus* a
reference-authored caveat: "Noted tags come from the rotation board and carry no graded call —
only the Overview lanes do." Production's `RVX_Q` stance strings ("Hold / add", "Take profits")
are not rendered. `ORCHESTRATOR_ADJUDICATIONS` §5 flagged that de-amplification for this seat:
**I uphold it.** Action vocabulary on a context surface is what A3 exists to restrain, and the
quadrant names/subtitles remain verbatim.

**A4 (Confluence order).** `TABS = ['subsectors','nasdaq','russell','baskets']` — S&P → Nasdaq →
Russell → Baskets, rendered as `S&P 500 65 / Nasdaq-100 12 / Russell-2000 93 / Thematic Baskets 49`.

**Confluence class is read, never recomputed.** `rowsOf()` reads `g['class']` and folds unknown
classes into `neutral` (ledger #69). Rendered distribution `entry_now 1 / tailwind 16 /
neutral 21 / late 18 / headwind 9` equals the producer's S&P distribution exactly. No foreign
rows: `kind` is uniformly `subsector` (S&P/Nasdaq/Russell) and `basket` (Baskets).

**A5 (Baskets disclosure).** The Baskets tab's coverage slot renders **nothing** — the guard is
on `cov.n_gateable`, which `basket_confluence.json` does not emit. No fabricated thin/gateable
disclosure. Verified by render, not by reading the guard.

**A6.** No invented Confluence staleness threshold (only the producer's own `ticks` delta →
"just fired" / "fired N bars ago"). No correction/revision UI: the single `correction` string in
the artifact is inside embedded fixture data.

**A8 (Explore).** `ai_watch` is the only field labelled "Model analysis / 模型分析"; the
deterministic score, its five legs, and the ticker order carry no such label. The
falsifier-register rewrite (`watchEn`/`watchZh`) is label-only and idempotent — the condition
text is untouched. Track Record prints the producer's accrual copy and feeds no live score.

**Client-recomputation audit — clean.** All 12 `.sort()` sites across the six views were traced
to production. Verified verbatim: Confluence `fullRowVals().fresh`
(`ticks ?? 100+bars_to_cross ?? 999`) vs `subsectors.js:462`; picks sort by `combined_score`
vs `:321`; default `{col:'tier',dir:1}` vs `:467`; Map `rvxData()` incl. its
`score==null?50` / `rank||999` coercions and `.sort(score desc)` vs `:2946-2957`; Explore
`initChartDefaults()` vs `:2791-2793`; Money heatmap name-list sorted by `size` matching
`heatmap.js` default `SORT='cap'`. **No rank, lane, state bucket, count, Confluence class, or
producer ordering is derived locally.** Hydration validates `schema === 'tier_payload.v1'` and
`page === 'sector_central'` — the harness does not bypass payload validation.

---

## 4. Findings

Severity: **HIGH** = must be corrected in the reference (blocks). **MEDIUM/LOW** = condition
that can ride into R3C implementation, provided it is carried explicitly.

### DAC-101 — HIGH — Overview hero drops a LIVE position-sizing directive

**Claim.** Production renders a position-sizing statement in the Overview hero chip row,
computed from the very fixture this reference embeds. The candidate renders nothing there.

**Producer.** `basketdata/baskets.json` → `theme_intel.regime_sizing`
(`schema: vol_regime.sizing.v2`, `active: true`, `gross_scalar: 0.81`, `mech_scalar: 0.81`).

**Production.** `sector_central.html.j2:2886-2919 renderRegimeSizing()`, injected into
`#hero-sizing` by `renderVerdictHero()` (:2927), which is a live boot call (:3056) and is
re-invoked on `langchange` (:3070). Executed against the frozen fixture it returns:

> **`positions sized to 81%`** / **`仓位缩至 81%`**
> tip: "How it's set: volatility target 81% → 81% | Read from US volatility, applied on every
> market page. Volatile markets get smaller position sizes. This does not change the basket ranking."

**Candidate.** `hero-sizing`, `pulse-size`, `positions sized`, `仓位缩`, `regime_demoted` →
**0 rendered occurrences**; `regime_sizing` appears only inside the embedded data blob.

**Why this is a data/authority defect, not a composition choice.** Sizing is one of the four
governed authority verbs on this page — the Bottoming Watch producer stamps `may_size: false`
precisely because sizing is authority. Production asserts an active ×81% gross constraint;
the reference asserts nothing. A reader of the reference sees no risk constraint where the
live page shows one, and an implementer following the reference removes a live risk directive
from production.

**Not adjudicated anywhere.** `regime_sizing` / `positions sized` / `hero-sizing` /
`pulse-size` appear in **no file** of the R3B pack — not the adjudications, capability
crosscheck, copy ledger, design notes, QA report, or fix record.

**Remedy.** Restore the sizing chip bound to `theme_intel.regime_sizing`, with production's
inert-when-calm guard (`!active || gross_scalar >= 1.0` → render nothing).

---

### DAC-102 — HIGH — Hero drops a governed caveat while keeping the assertion it governs

**Claim.** Production pairs the leadership-succession assertion with a methodology receipt
carrying an explicit non-forecast caveat. The candidate keeps the assertion and drops the caveat.

**Production** (`sector_central.html.j2:2153`), chip "How this works / 原理说明", tip:

> "Trailing-momentum rank names {leader} first; **skips the most recent ~3 weeks by
> construction**; suggested weights unchanged. **Shape read only — not a forecast.**"

**Candidate.** `How this works`, `原理说明`, `Trailing-momentum`, `skips the most recent` → **0**.
The single `not a forecast` string in the 5.4 MB artifact is inside an embedded fixture JSON
`note_en` value, not rendered copy. Meanwhile the hero *does* render the full succession claim:
"LOSING THE LEAD Memory, HBM & Storage WAS #1 → TAKING THE LEAD Big Pharma · Health Care …
MONEY IS ROTATING … 2 days in".

**Why this is in the copy-authority lane.** Classified against the commission's four
categories, the dropped chip is a **governed caveat**, and the retained hero band is the
market assertion it governs. Removing the caveat while keeping the claim raises the surface's
implied authority: a ranked, dated leadership handoff with a "2 days in" clock and no
disclosure that it is a lagged shape read invites exactly the probability implication the
caveat exists to block. Note the lane demonstrably understood caveat authorship — it *wrote* a
new one for the lane-separation invariant (§3). It simply never inventoried the one production
already had.

**Not adjudicated anywhere** (same search as DAC-101).

**Remedy.** Restore the receipt (or an equivalent Tier-2 receipt) carrying both the
~3-week construction lag and the "shape read, not a forecast" caveat.

---

### DAC-103 — MEDIUM — `theme_context.migration.note_en` producer fact dropped

Production's hero sub-line (`:2130`) renders `theme_context.migration.note_en` when present.
The frozen fixture carries it: **"Money is moving into Software and out of Semiconductors."**
(with a `note_zh` twin). The candidate renders neither, and `migration` is unreferenced in
`overview.html`. This is the producer's own statement of *where* the rotation is going —
the one directional fact behind the "Money is rotating" verdict word the hero does render.
Falls under ledger #24 (RETAIN). **Condition:** restore, or record explicitly for R3C.

---

### DAC-104 — MEDIUM — `allocation.html` working destination silently deleted

`"Open the playbook →" → allocation.html` is the Overview hero's only navigation destination
(producer binding matrix, Overview/"Hero leadership context" row; ledger #86 RETAIN,
"per-view working-destination inventory"). The frozen candidate contains **0** occurrences of
`allocation.html`, `Open the playbook`, or `操盘手册`.

R3A is explicit: *"nothing in this wave is REMOVE or RELOCATE — any candidate for those
requires a new ruling in ADJUDICATIONS.md first."* No such ruling exists. This also removes
the only path from the context reading to the place it becomes actionable.

**Aggravating:** `capability_crosscheck.md` row **#86 is marked VERIFIED**, and its evidence
enumerates the overview destinations as "`basket/*`, `plans.html`, in-page hashes" —
`allocation.html` is simply not in the list, and its absence was read as completeness. See
`DAC-108`.

---

### DAC-105 — MEDIUM — S&P coverage sentence asserts absent rows are "listed in the table"

Rendered live on the S&P tab:

> "**65 of 113 subsectors have enough live data to time · 48 thin (listed in the table, not timed)**"

The S&P table contains **65** rows. `113 − 65 = 48` — the "thin" 48 are the **gate-dropped**
groups, absent from `subsectors[]` entirely. The sentence tells the reader 48 rows are
present-but-untimed when they are not present at all.

**Inherited, not introduced.** Verbatim from `templates/subsectors.js:221-222`. `ADJUDICATIONS`
§A5 diagnoses the semantics correctly ("S&P 'thin' (48) means gate-DROPPED — absent from the
payload array, not 'thin-but-listed'") while ledger #65 RETAINs the contradicting wording, and
`ORCHESTRATOR_ADJUDICATIONS` §9 keeps the coverage-wording sub-claim alive as a known-defect
RETAIN. The builder had no authority to repair it.

**Condition, not block.** But a PASS must not be read as ratifying it: this is a false
coverage statement on an Action-tier surface, and it becomes migration law on approval.
It should be named in the R3C delta list as a production-repair item.

*Related (correct, no action):* `coverage.thin_share` is `n_low_conf / listed`, **not**
gate-dropped share — Nasdaq carries `n_thin: 0` yet `thin_share: 0.667`. The candidate never
renders `thin_share`, which is the right call. (`ADJUDICATIONS` §A5's premise that
`basket_confluence.json` "carries only `n_baskets`" is also imprecise — it carries
`n_high`/`n_med`/`n_low_conf`/`thin_share` too — but the behaviour is right because the guard
is on `n_gateable`.)

---

### DAC-106 — LOW/MEDIUM — Hero handoff enrichment and inventory counts dropped

Production's `renderVerdictHero()` fills `#hero-out-meta` with the outgoing leader's 20d/5d
relative performance, `#hero-in-meta` with the incoming leader's 20d and a "climbing fast"
flag, and `#hero-count` with "· 49 themes · 15 categories". All four ids are absent from the
candidate; the handoff card carries only "was #1". These are producer facts
(`theme_intel.themes[].perf`, `pulse_rank_delta_5d`, `baskets`/`categories` lengths) that
quantify the succession claim the hero makes. **Condition.**

---

### DAC-107 — LOW — One producer field, two column labels

`theme_intel.themes[].score` is rendered under **"Score / 评分"** on Overview and
**"Strength / 强度"** on Map. Verified identical values for all 9 theme rows common to both.
Two names for one measure on one surface invites a reader to treat them as different
instruments. **Condition** — pick one label.

---

### DAC-108 — MEDIUM — Crosscheck rows #24 and #86 are VERIFIED by self-enumeration

This is a finding about the **evidence pack**, filed because Sol will rely on it.

`capability_crosscheck.md` marks ledger #24 (Overview hero context) and #86 (per-view
working-destination inventory) **VERIFIED**. In both cases the evidence quotes *what the
candidate renders* and stops: row #24 lists the five hero elements the candidate has; row #86
lists the hrefs the candidate has. Neither row compares that inventory against production's.
That method cannot detect an omission by construction — and it is precisely how `DAC-101`,
`DAC-102`, `DAC-103`, `DAC-104`, and `DAC-106` passed unnoticed.

A false VERIFIED is worse than a silent gap: it would affirmatively assure R3C that the hero
band and destination inventory are complete. **Condition:** re-run #24 and #86 as
completeness diffs against the production template before R3C consumes the pack.

*Contrast, credited:* row #26 was verified by genuine falsification — deleting
`si_handoff.json` and confirming the five lanes still render 4/5/5/3/27. That is the right
method, and it is the reason I could confirm the R2 invariant quickly.

---

## 5. Notes — inherited or latent, no action against the candidate

- **N1 — cross-artifact contradiction, faithfully inherited.** Expanding a row's `#read-*`
  trace shows the *conviction* artifact (`sectordata/sector_central.json`) beside a lane from
  the *action* artifact. On this fixture that yields **"Buy now" → Non-AI Software →
  "Conviction 25 · Reduce"** and **"Almost ready" → Financials → "21 Reduce"**, plus several
  `avoid`-lane rows reading "Constructive" (Memory HBM 69, Power & Grid 69, Utilities 67).
  The reference keeps the two producers correctly separated and neither blends nor relabels —
  this is production's own behaviour (`sector_central.html.j2:3096-3115`), and ledger #8
  RETAINs it. Flagged only so a PASS is not read as ratifying an unlabelled two-producer
  contradiction on an Action surface.
- **N2 — `REF.parseJSON` NaN→null.** `basketdata/action_board.json` ships two bare `NaN`
  tokens (invalid RFC 8259). Both are `factor_z`, which is rendered by
  `_us_setups_rows.html.j2`/`dashboard.html.j2` but **never on this surface** — `factor_z`
  appears nowhere in the R3B build code. So the harness coercion changes no displayed value
  here. Fixture-hygiene item, not an authority defect. (Independently found pre-freeze; the
  cycle logs it as QA3-03.)
- **N3 — latent null coercions.** `rvxData()`'s `score==null?50` and `rank||999` are verbatim
  production, and the fixture has **zero** nulls across all 49 themes for `score`, `rank`,
  `reco`, and `pulse_rank_delta_5d`. Latent, inherited, unexercised.
- **N4 — Map drops production's `buyable` flag and "buy" filter.** A reduction of action
  authority on a context view; consistent with the §5 de-amplification ruling I uphold. Worth
  one line in the R3C delta so it is a decision, not an accident.
- **N5 — ledger #78's foreign-row detector** relies in part on `universe == "sp500_subsector"`;
  no confluence row in this fixture carries a `universe` field at all. The clause is
  unsatisfiable against this data (the other four parts of the rule still discriminate).

## 6. Limitations / NOT_EVALUABLE

| axis | status | why |
|---|---|---|
| A8 "Model analysis" label rendering | **code-verified only** | `ai_watch` is `null` in the frozen fixture; production's absence path runs. Branch read and correct; never seen painted. |
| `forming` class fold + its 4-cap | **not exercised** | zero `forming` rows in all four universes. |
| Nasdaq/Russell thin-but-listed wording | **not exercised** | `n_thin = 0` in both. |
| Live anonymous production comparison | **impossible** | production 401-gates all non-overview assets (`x-regwall: deny`); confirmed by `ORCHESTRATOR_ADJUDICATIONS` §8. My production comparisons are against committed template/producer source at pinned commits, not live capture. |
| `gh`/CI state, responsive, a11y, taste | **out of lane** | other critics. |
| Hydrated/ungated access states | probed via the harness drawer only | no real auth path exists in a quarantined artifact. |

## 7. Blockers and conditions

**BLOCKERS (must be corrected in the reference before PASS):**
1. `DAC-101` — restore the `regime_sizing` position-sizing statement to the Overview hero.
2. `DAC-102` — restore the methodology receipt and its "shape read, not a forecast" caveat.

**CONDITIONS (may ride into R3C if carried explicitly):**
3. `DAC-103` restore/record `migration.note_en`.
4. `DAC-104` restore `allocation.html` ("Open the playbook →") or obtain an explicit REMOVE ruling.
5. `DAC-105` name the S&P dropped-thin wording in the R3C delta as a production-repair item;
   do not let a PASS ratify it.
6. `DAC-106` restore or record the hero handoff enrichment and inventory counts.
7. `DAC-107` unify the `score` column label across Overview and Map.
8. `DAC-108` re-run capability crosscheck rows #24 and #86 as completeness diffs against production.

## 8. Statement of non-modification

No rank, state, action, or data file was modified by this review. The candidate
(`19553267d3f5…`), `BUILD_MANIFEST.json` (`a7b9ae8ab3f1…`), the R3A fixture and its receipts,
every production file, and the RIG manifest are **byte-untouched**. The only files this seat
created are this review and
`research/reference_integrity/mastermind-xpv2-sector-r3b/reviews/evidence_data_authority_fresh/`.

## 9. Evidence paths

- `reviews/evidence_data_authority_fresh/FIRST_PASS_FROZEN.md` — first-pass verdict + findings,
  frozen `2026-08-22T13:05:05Z`, before any quarantined file was read.
- `reviews/evidence_data_authority_fresh/BREACH_LOG.md` — the single disclosed breach.
- `reviews/evidence_data_authority_fresh/probe_overview.py` — independent render probe
  (lane counts, foot, rows, disclosures, hero text, watch band).
- `reviews/evidence_data_authority_fresh/probe_confluence.py` — independent render probe
  (tab order, per-universe coverage foot, class-tab counts).
