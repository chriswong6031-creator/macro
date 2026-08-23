# XPV2-SC-R3B.2 — EN/ZH copy ledger, Lane A (authority / copy identity)

Commission: `research/reference_integrity/mastermind-xpv2-sector-r3b-2/COMMISSION.md`
Fix packet items covered by this lane: **B2-01 · B2-04 · B2-08 · B2-09**, plus the
orchestrator-adjudicated **DA1-02** chip re-label
(`ORCHESTRATOR_ADJUDICATIONS_R3B2.md` §1 ruling 1).

This ledger records **every EN/ZH pair Lane A changed or minted in the R3B.2
successor artifact**. It supplements — it does not replace —
`../mastermind-xpv2-sector-r3b-1/copy_ledger_r3b1.md` and
`../mastermind-xpv2-sector-r3b/copy_ledger.md`, which still govern every string
those cycles minted and which this lane did not touch.

Every pair below was read back out of the **built** artifact
(`proposal/MASTERMIND_SECTOR_CENTRAL_R3_CANDIDATE.html`) with headless Chromium
on 2026-08-23 — the rendered values quote `innerText`, not source. Receipts:
`build/lane_crops_a2/` (crops, `DA102_CHIP_RECEIPT.txt`, `LANG_OF_PARTS.txt`).

**Provenance vocabulary** — the four values the predecessor ledgers use, plus one
this lane needs:

- **producer-field** — the whole string is a value read out of a fixture artifact
  at the frozen epoch. The reference supplies no words.
- **bound-from-production (verbatim)** — words copied unchanged from a named
  production template/JS file.
- **bound-from-production (recomposed)** — production's own words, re-punctuated
  or re-ordered, no semantic change.
- **authored-new** — this lane wrote both halves.
- **display projection (new to R3B.2)** — the EN half is producer bytes rendered
  verbatim; the ZH half is authored by this lane to carry the *identical governed
  meaning* of those bytes, and is keyed to them. Used once, for B2-04.

**Standing constraint honoured throughout: a rename changes the LABEL, never the
VALUE.** Every figure below still resolves to the same producer path at the same
frozen epoch, and no rank, state, count, class or ordering moved.

---

## 1 · B2-01 — one producer measure, one customer term

**Producer path:** `basketdata/baskets.json → theme_intel.themes[].score`.

**The amended law.** R3B1-06 carved the Overview action-board header out of the
Strength rename on the premise that it painted "a separate producer field
(`action_board.json`)". The Data/Authority seat tested that premise and it is
false: `scripts/build_site.py:1774-1785` constructs each `kind: "theme"` board
item with `"score": th.get("score")` — a byte copy off the same
`theme_intel.themes[]` element. Cross-joined on ticker against the embedded
fixtures, **33 of 33 identical, 0 differing, 0 unmatched** (DA1-01). Sol amended
the carve-out in the R3B.1 verdict: the customer term for this path is
**Strength / 强度** on every surface that paints it, action board included.

| EN | ZH | site | provenance | note |
|---|---|---|---|---|
| `Strength` | `强度` | `build/views/overview.html:766` — `paintPanel()` action-board column legend, marker `data-r3b2="01"` | bound-from-production (verbatim), the same pair the Map already used | **CHANGED from `Score` / `评分`.** Rendered values unchanged: Gold Miners `76`, AI Agents `71`, Non-AI Software `70` — the same numbers the Map's Strength column paints for the same groups. |
| `20d vs market` | `20日对比市场` | same span, `<em>` unit line | unchanged (R3B1-11) | Recorded only to show the two-line header's second line was not disturbed. |
| `Strength` | `强度` | `build/views/map.html:98` — text-equivalent table `<th data-r3b1="06">` | unchanged | Already compliant; the false-independence source comment above it was withdrawn. |
| `Strength ` + value | `强度 ` + value | `build/views/map.html:601` — scatter tooltip | unchanged | Already compliant. |
| `Strength` | `强度` | `build/views/map.html:658` — selected-object `<dt>` | bound-from-production (recomposed), `sector_central.html.j2:2991` | **CHANGED from `Strength score` / `强度评分`.** Production's own dt carries a trailing noun; it is dropped so the path answers to exactly one string and a producer-path→label uniqueness check resolves uniquely. Value `77` (Big Pharma) unchanged. |
| `…where it sits, its strength, its 20-day move…` | `…所处位置、强度、20日相对标普涨跌…` | `build/views/map.html:73` — table `<caption class="r3-vh">` | bound-from-production (recomposed) | **CHANGED from `its strength score` / `强度评分`.** Same reason: a screen-reader user hears the caption immediately before the column header, so the two must not disagree. |

**Deliberately NOT renamed — different producer fields, different measures:**

| EN | ZH | producer path | why it keeps its name |
|---|---|---|---|
| `Conviction` | `信心` | `conviction.score` (Overview trace card, `overview.html:1018`) | A genuinely separate producer field with its own label ladder. |
| `Conviction` | `综合把握` | `double_gated.double_buy[].combined_score` (Confluence picks, `confluence.html:778`) | Production's own header for that exact field (`templates/subsectors.js:330`); R3B1-13's binding. |
| `Conviction` | `信心` | `conviction.score` (Map group-read figure, `map.html:830`) | Same field as the trace card. |

**Copy removed as false:** `build/views/map.html`, the source comment claiming
"The graded action-board figure on Overview is a separate producer field
(action_board.json) and is deliberately not renamed." No customer-facing string
made that claim; the claim lived only in the shipped source comment, and shipped
source comments are artifact bytes. It is replaced by the producer citation.

---

## 2 · B2-12 (was DA1-02) — the row-level reliability chip

> RECONCILED 2026-08-23 per Sol FINAL CONTINUATION HANDOFF §5 B2-12: the canonical
> low-reliability label is `Low confidence / 低置信度`; Lane A's earlier causal wording
> (`Few live members — read with caution / 实时成分股很少 — 请谨慎解读`) is superseded —
> causal copy is permitted only as an optional addition and Sol's stated default wins.
> The producer-contract analysis below remains the audit trail for WHY the old 'thin'
> word was unlawful.

**Producer path:** `subsector_confluence.json → subsectors[].reliability`.

**Contract, read before choosing a word** — `engine/subsector_confluence.py:73-82`:

```
def reliability(n_priced: int | None) -> str:
    """HIGH/MED/LOW breadth-confidence tier from the count of PRICED members."""
```

with `RELIABLE_MIN = 12` (high) and `RELIABLE_MED = 6` (med), documented at
:62-71 as *"An equal-weight index on very few PRICED members is dominated by 1-2
names… an honest breadth flag, not a validated reliability number."*

So `low` means **fewer than six priced members**. It is a MEMBER-COUNT fact.

**Why the old word had to go.** The same Confluence screen carries the corrected
R3B1-07 coverage sentence, whose "thin" is `coverage.n_thin` — the **48
gate-dropped** groups that never enter `subsectors[]` at all. The chip's "thin"
was `reliability == "low"` — an **in-table** flag on 31 rows that did pass the
gate. One customer word, two producer paths, and the two statements contradict:
"48 are omitted as too thin", then 31 rows inside that very table stamped "Thin
data".

**Label chosen, and the one rejected.** The commission offered `Sparse history /
历史数据较少` *if it matched the field*. It does not — `reliability` never reads a
history length, only `n_priced` — so it was rejected as untrue to the producer.
The label below names the member count instead. `read with caution /
请谨慎解读` is kept verbatim: the stance is unchanged, only the reason is now
correct.

| EN | ZH | site | provenance | note |
|---|---|---|---|---|
| `Low confidence` | `低置信度` | `build/views/confluence.html:646-647` — `relDot()`, `.r3-vh` accessible name beside the `.r3-thin` dot, marker `data-r3b2="da102"` | bound-from-production (recomposed), `templates/subsectors.js:58` | **CHANGED from `Thin data — read with caution` / `数据稀疏 — 请谨慎解读`.** The word "thin"/"稀疏" is now used by the coverage sentence alone. `live` matches the sentence's own `enough live data to time` / `实时数据足够`; `成分股` is this build's established ZH for members (`confluence.html:687`). |

**Kept, not reverted** (DA seat condition C2 explicitly asks for this): the
promotion off production's EN-only `title=` to a bilingual accessible name, and
the ZH twin. Production renders a bare coloured dot with an English `title=` and
no ZH at all.

**Untouched, verified byte-identical:** the R3B1-07 coverage sentence
(`confluence.html:590-598`). Read back from the built artifact —
EN `65 of 113 subsectors have enough live data to time. 48 are too thin to time
and are omitted from the timed table.`;
ZH `113 个子行业中，65 个实时数据足够，可用于计时。另有 48 个数据过于稀疏，无法计时，未列入下方计时表。`

**Truthfulness cross-check available to the reader on the same row:** the timed
table's own `N` column is the priced-member count. Every chipped row on this
fixture carries `N` of 3, 4, 5 or 4; unchipped rows carry 6+
(`lane_crops_a2/da102-confluence-timed-table-chips-1440-dark-en.png`). The label
and the number beside it now say the same thing.

---

## 3 · B2-04 — WITHDRAWN (Sol FINAL CONTINUATION HANDOFF §4)

> The candidate-authored ZH projection of `grader.pre_freeze_note` was WITHDRAWN:
> English-only grader strings are upstream producer-owned (PRC1R-U02); the reference
> may not mint producer translations. The projection, its `lang="en"` fallback rung,
> and `lang_of_parts_audit.py` were removed in the reconciliation commit; the note
> renders producer bytes verbatim again (predecessor behavior). The pairs below are
> retained STRUCK-THROUGH as history only — they ship nowhere.

### (withdrawn pairs — historical record)

**Producer path:** `sector_central grader → grader.pre_freeze_note`
(embedded fixture; rendered by `paintGrader()`).

**The defect, reproduced in the frozen bytes before repair.** Under
`<html lang="zh-CN" data-lang="zh">` this note painted as three English
sentences — 38 Latin word tokens, 31 of them lowercase running words — inside a
panel whose every other line twins. Pre-fix crop:
`lane_crops_a2/04-grader-note-zh-PREFIX-english-prose.png`; pre-fix scanner
output: `RESULT: FAIL`, 1 finding, 4,281 nodes scanned.

**The repair is a display projection, not a rewrite.** The producer bytes are
unchanged and still render verbatim under EN
(`lane_crops_a2/04-grader-note-en-producer-bytes-verbatim.png`).

| EN (producer bytes, verbatim) | ZH (authored projection) | site | provenance |
|---|---|---|---|
| `Basket grading accruing from 2026-07-02 (W3.8 freeze date). Pre-freeze basket calls are not graded: the series before this date is permanently survivorship-contaminated (D4-N3). Basket return math re-anchored 2026-08 after the moving-base freeze defect; grades accrue from the chain anchor (2026-08-06).` | `篮子评分自 2026-07-02（W3.8 冻结日）起累积。冻结日之前的篮子判断不予评分：该日期之前的序列存在无法消除的幸存者偏差（D4-N3）。篮子收益算法在出现移动基期冻结缺陷后已于 2026-08 重新锚定；评分自链条锚点（2026-08-06）起累积。` | `build/views/overview.html:1340-1352` — `preFreezeNote()`, rendered into `<p class="r3-gr-note" data-r3b2="04">` | **display projection** |

**Governed-meaning source: the producer string itself**, clause for clause —

| governed claim | EN clause | ZH clause |
|---|---|---|
| grading accrues from the W3.8 freeze date | `accruing from 2026-07-02 (W3.8 freeze date)` | `自 2026-07-02（W3.8 冻结日）起累积` |
| pre-freeze calls are not graded | `Pre-freeze basket calls are not graded` | `冻结日之前的篮子判断不予评分` |
| because that series is permanently survivorship-contaminated (D4-N3) | `permanently survivorship-contaminated (D4-N3)` | `存在无法消除的幸存者偏差（D4-N3）` |
| return math re-anchored 2026-08 after the moving-base freeze defect | `re-anchored 2026-08 after the moving-base freeze defect` | `在出现移动基期冻结缺陷后已于 2026-08 重新锚定` |
| grades accrue from the chain anchor 2026-08-06 | `grades accrue from the chain anchor (2026-08-06)` | `评分自链条锚点（2026-08-06）起累积` |

Both receipt keys (`W3.8`, `D4-N3`) and every date survive: they are the handles
a reader uses to look the claim up, and a projection that dropped them would be
a softer statement, not the same one. House ZH is reused rather than invented —
`评分` for grading and `判断` for calls are this build's existing pairs
(`overview.html:1366`, `:1362`).

**Fallback pair, keyed and not shipped on this fixture.** The projection is bound
to the exact producer bytes it was authored against. If the producer ever emits a
different note, the reference does not guess a translation: it keeps the English,
marks it `lang="en"` so assistive tech switches voice, and identifies it in the
reader's own language.

| EN | ZH | site | provenance | note |
|---|---|---|---|---|
| *(no EN counterpart — the EN document needs no marker)* | `数据提供方原文（英文）` | `build/views/overview.html:1350` — `.r3-gr-src` label preceding the `lang="en"` span | authored-new | Inert on this fixture (the bytes match, so the projection path renders). Exists so an unmatched producer string degrades to a *marked* source-language quotation rather than to unmarked English prose. |

---

## 4 · B2-08 — rank scope in the rank header

No new words: the orphan note's exact EN string is folded into the column header
and given a native ZH twin in place of the previous literal-order translation.

| EN | ZH | site | provenance | note |
|---|---|---|---|---|
| `Rank` + `across all groups` (two-line header) | `排名` + `在全部分组中` | `build/views/map.html:85` — `<th class="num" data-r3b2="08">` with `<em>` second line | bound-from-production (recomposed) for EN; **ZH re-authored** | The EN string is the orphan note's own wording, unchanged, now placed where it is read. **ZH CHANGED from `排名范围：全部分组`** — that reads as a standalone label ("rank scope: all groups"); as a header's second line the natural Chinese is the adverbial `在全部分组中` ("among all groups"), so the header's accessible name reads `排名 在全部分组中` rather than two stacked labels. |

**Deleted:** the orphan `<p class="r3-note">Rank across all groups / 排名范围：全部分组</p>`
that sat 1,075px below the column it explained (VTC1-004). Its information is not
lost — it moved up, into the header row directly above the non-contiguous ranks
`1, 3, 4, 6, 7…` that raise the question.

---

## 5 · B2-09 — recently-wrong ink

**No copy change.** Recorded here because the ledger is the lane's complete
account and a reader of it should not have to wonder whether the row's words
moved. `Recently wrong (logged)` / `近期误判（已记录）` is unchanged; only the ink
bound to the figures beside it changed, from `.up`/`.dn` (reserved direction ink,
selected off the call's stage — so six of eight logged misses painted in the
reserved up-green) to the neutral `--muted` rung.

Measured on the painted `--panel`: **5.57:1 dark, 5.43:1 light**, identical EN and
ZH because the rung is achromatic and therefore untouched by the 红涨绿跌 swap.
`--muted` is not `--ink-up`, `--ink-down`, `--ink-ok` or `--fill-up`
(`lane_crops_a2/` — `09-*` crops; probe output quoted in the lane return).

An error-red family was considered and rejected: `--act` does not participate in
the ZH direction swap, so red under ZH would read as *up* — the same defect
mirrored. No token was minted; `DESIGN_SYSTEM_SPEC.md:373` forbids one, and
`--muted` is already the ink this block's own label, note and disclaimer carry.

---

# Lane B (responsive / a11y geometry) — appended 2026-08-23

Fix packet items covered by this lane: **B2-05 · B2-06 · B2-07 · B2-10 · B2-11**,
plus the orchestrator-adjudicated in-lane a11y closures **PRC1R-001**
(`aria-controls`) and **MAC1-002** (ZH `收起` target floor). Lane A's rows above
are unchanged; nothing in this section rewrites them.

**Lane B minted no new vocabulary.** Every pair below is a string this artifact
already renders in a column legend, moved so that it also reaches the reader the
legend does not: the screen-reader user at every width, and the sighted phone
user below 641px, where `@media (max-width:640px){ .r3-cols{display:none} }`
removes the legend outright. A figure column's name is now carried by the figure
itself (`.r3-figlab`, `shell.html`) — visually hidden while the legend is
painted, a compact caption once it is gone. One node, two presentations: never
absent from the accessible tree, never painted twice.

**Line-number note (no Lane A row is rewritten).** Lane B's insertions moved the
lines under two citations in the sections above. Lane A's rows stand as written;
the current locations are `views/overview.html:796` for the B2-01 action-board
column legend (cited above as `:766`) and the
B2-04 `preFreezeNote()` (cited above as `:1340-1352`; the function now opens at
`:1385` and its render site is `:1422`). Marker attributes
(`data-r3b2="01"`, `data-r3b2="04"`) are the stable handles and are unchanged.

Receipts: `build/lane_crops_b2/` (crops + `B2_LANE_B_RECEIPT.txt`),
`build/fig_naming_audit.json`, `build/treemap_labels_audit.json`,
`build/mobile_geometry_audit.json`.

## 6 · B2-05 — the label travels with the figure

| EN | ZH | site | provenance | note |
|---|---|---|---|---|
| `Strength` | `强度` | `build/views/overview.html:697` — `rowHTML()` per-row `.r3-figlab`, marker `data-r3b2="05"` | **relocated**, byte-identical to Lane A's B2-01 column header (now `overview.html:796`) | New SITE, not a new string. Asserted equal to the rendered header by `fig_naming_audit.py` (`label_mismatch` must be empty), so this producer path cannot acquire a second, softer synonym on the way to a phone. Rendered: `强度 76` / `STRENGTH 76` at 320 and 390. Values unchanged. |
| `20d vs market` | `20日对比市场` | `build/views/overview.html:686` — `.r3-vh` inside `.r3-delta` | **relocated**, byte-identical to the same header's `<em>` second line | Visually hidden at EVERY width by design: two painted captions over one 74px column would breach the density budget and set the strength score competing with its own footnote. A signed percentage is self-evident to the eye and anonymous to a screen reader, so the name goes only where it is needed. Closes MAC1-001's second column. |
| `Entry tier` | `入场层级` | `build/views/confluence.html:684` — `groupRow()` per-row `.r3-figlab`, marker `data-r3b2="05"` | **relocated**, byte-identical to the subsector list legend (`confluence.html:714`) | New site. An absent tier renders as absence and takes no caption. Closes MAC1-001's third column. |
| `Conviction` | `综合把握` | `build/views/confluence.html:810` — `paintPicks()` per-row label | unchanged (R3B1-13) | **String untouched; carrier re-classed `.r3-vh` → `.r3-figlab`.** The pair was already correct and already per-row — it was simply never painted, at any width, so R3B1-13's commissioned label reached sighted mobile users nowhere (PRC1R-002) and VTC-006's bare `0.60` was fully reinstated at 390/320 (VTC1-001). Rendered visible at 320/390 in both languages over `0.60` and `0.54`. |

**Valueless figures take no caption.** Overview sector rows carry no blended
score (ledger #7); a caption over nothing is a name for a value that does not
exist. `fig_naming_audit.py` counts them (4 per cell, asserted) rather than
exempting them silently.

## 7 · B2-06 / B2-07 / B2-10 / B2-11 / MAC1-002 / PRC1R-001 — no copy changed

Recorded so a later seat does not go looking for rows that do not exist:

- **B2-06** drops a sector header that cannot be painted inside its own section,
  and its aggregate before that. No string is rewritten, abbreviated or
  ellipsized — this system permits no cut on a primary name. Every dropped name
  remains, in full, in the mandatory accessible table in the same view.
- **B2-07** re-orders the Money heat band below 641px and makes the tiles
  non-interactive. `Read the map as a table` / `以表格阅读该图` and
  `Browse the names` / `浏览个股` are unchanged in wording and in DOM order.
- **B2-10** removes `.r3-spread` where the ledge stops being a five-track row.
  It carries no text of its own and is `aria-hidden="true"`; its accessible
  equivalent has always been the cells, which all remain on screen.
- **B2-11** changes one margin so the Overview hero receipt flows to the end of
  the statement it governs. `How this works` / `原理说明` and the seasonal
  producer chip are untouched.
- **MAC1-002** floors `.r3-textbtn` on the inline axis. `Show fewer` / `收起` is
  unchanged; only the box stopped being sized off the glyph count.
- **PRC1R-001** adds `aria-controls="r3-receipt"`. No user-visible text.

## 8 · B2-05 STRENGTHENING (Sol FINAL CONTINUATION HANDOFF §5) — the delta's label becomes VISIBLE

Sol's amended B2-05 law: *"At ≤640, every figure whose visual header disappears
gets a visible inline mobile label"*, with the required meanings naming
`20d vs market +27.2% / 20日对比市场 +27.2%` explicitly. That **overrides §6 row 2
of this ledger**, which recorded the 20-day delta's name as *"visually hidden at
EVERY width by design"* on a density argument. §6 is left exactly as written —
it is the record of what was decided then; this section is what supersedes it.

**No string changed.** The pair `20d vs market` / `20日对比市场` is byte-identical
to what §6 recorded and to the legend `<em>` it was taken from. What changed is
the CARRIER and therefore the presentation.

| EN | ZH | site | provenance | note |
|---|---|---|---|---|
| `20d vs market` | `20日对比市场` | `build/views/overview.html:722` — `rowHTML()`, `.r3-figlab` inside `.r3-delta`, marker `data-r3b2="05"` on the delta | **carrier re-classed `.r3-vh` → `.r3-figlab`**; string unchanged and still byte-identical to the column header's `<em>` second line (`overview.html:835`) | Now PAINTED at ≤640 and still clipped at >640, where the legend names the column. Asserted equal to that `<em>` by `fig_naming_audit.py` (`delta_label_mismatch` must be empty), so the delta cannot acquire a shortened synonym on the way to a phone. Rendered: `20D VS MARKET +27.2%` / `20日对比市场 +27.2%` at 320 and 390. Values unchanged. |
| `Strength` | `强度` | `build/views/overview.html:734` — unchanged site, unchanged string | unchanged (§6 row 1) | Recorded only to note the guard around it moved: the caption is now emitted on `sc` alone rather than on `sc || p20`, so a row carrying a delta but no score can no longer inherit the score's name. Inert on this fixture (all 11 valued theme rows carry both). |

**No duplicate spoken label.** The delta previously carried a `.r3-vh` twin *and*
would now carry a `.r3-figlab`; only one node exists, so the accessible name is
`20d vs market +27.2%` exactly once — the same single-node rule §6 row 4 applied
to Conviction.

**Composition, not abbreviation.** Two named figures now share one cell. The
label sits *over* its figure rather than inline before it: inline is one line
shorter but costs ~130px of a 320 viewport's 288px, taken out of the name
column, where a primary name wraps and never ellipsizes. Stacked, the cell is
~94px (EN) / ~62px (ZH) and the row grows by one micro line instead. Nothing is
shortened in either language — `20d vs market` is the whole meaning, and
`20d` alone would change what the number is measured against.

## 9 · B2-15 — context-only / 5d evidence disclosure beside the track-record badge

Closes the candidate-owned half of `DA1-03`. The badge itself is **untouched**:
`Forward track record: Validated` / `前瞻战绩：已验证` still reads exactly as
production authors it (`templates/sector_central.html.j2:3460-3468`), because the
badge's broader `Validated` semantics and its 21d pairing are an R3C owner
repair. What is added is the qualification the embedded payload already carried
and the surface never painted.

**Producer binding — verified before painting.** Fixture
`research/reference_integrity/mastermind-xpv2-sector-r3/fixture/marketdata/index_leadership.json`
(sha256 `d95fe2e7b28fda138f9834e424b358d590e514d2484cde9da90bf4260b20b50b`),
JSON path `track_record`:

```
"schema": "index_leadership.track_record.v1",
"is_context_only": true,
"verdict": "validated",
"proven": { "5": true, "10": false, "21": false, "63": false }
```

Every clause is derived, none asserted. The block renders only while
`is_context_only === true`; the horizon it names is read out of `proven` itself
(`build/views/money.html:1260-1276`, `trQualHtml()`). Flip the flag and the
sentence disappears; mark `proven["21"]` true and the sentence says `5 / 21d`.
It does **not** translate or restate the producer's English `note` — producer
strings stay upstream-owned (Sol §4 / `PRC1R-U02`). These are reference-authored
strings and therefore take a native ZH twin like every other authored string here.

| EN | ZH | site | provenance | note |
|---|---|---|---|---|
| `Context only` | `仅为背景` | `build/views/money.html:1272` — `.lead-tr-cl` inside `.lead-tr-qual`, marker `data-r3b2="15"` | **authored-new**, bound to `track_record.is_context_only === true` | ZH is not a new coinage: `仅为背景` is this view's own established idiom for the same claim (`money.html:460`, `仅为背景 — 本视图不给出操作判断`), so the two context-only statements on one view speak with one voice. |
| `evidence proven at 5d` | `仅 5 日周期有实测证据` | `build/views/money.html:1266-1267` — `ev`, rendered into `.lead-tr-cl` | **authored-new**, bound to `track_record.proven` (the `true` horizons, ascending) | `5` is not a literal — it is `Object.keys(proven).filter(v => v === true)`. ZH re-authored, not calqued: `实测` is the build's own word for measured-rather-than-asserted (`money.html:1299`, `实测而非断言`), and `周期` is the Horizon column's own noun (`moving.html`). The clause deliberately avoids `已验证` / `验证` so it cannot be read as extending the badge's word to this horizon. |
| `never sizes decisions` | `从不用于仓位决策` | `build/views/money.html:1274` | **authored-new**, gated on `is_context_only` | `仓位` is this build's established ZH for position sizing (`overview.html:1250` `仓位缩至`, `:1254` `仓位如何设定`). |
| *(null path, inert on this fixture)* `no horizon has cleared the bar yet` | `尚无周期达到实测证据` | `build/views/money.html:1268` | **authored-new**, the `proven` map with no `true` entry | Never renders against these bytes; exists so an all-false `proven` degrades to a plain-word null disclosure rather than to a missing clause. |
| `21d hit-rate: ` | `21日命中率：` | `build/views/money.html:1297` — `.lead-tr-h21` | unchanged | **String untouched; carrier re-classed to `.lead-tr-h21`.** The 21d statistics keep their explicit horizon label and are now forced onto their own line under a hairline, so they can never sit beside the qualification and read as its evidence. `running` / `coiling` remain producer bytes and are not translated. |
| `grades mature at 5 / 10 / 21 / 63d — measured, not asserted` | `5 / 10 / 21 / 63 日后成熟评级——实测而非断言` | `build/views/money.html:1298` | unchanged | Same re-class, same reason. Inert on this fixture (`any_matured` is true). |

**What this does NOT say.** It does not claim the 21d horizon is validated, it
does not contradict or reword the badge, and it does not use falsifier or
refutation vocabulary. It states which horizon the evidence reaches, and that the
reading never sizes anything — both straight out of the payload.
