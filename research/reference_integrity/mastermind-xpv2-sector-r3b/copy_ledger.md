# XPV2-SC-R3B — EN/ZH copy ledger (Deliverable 4)

Commission: `research/reference_integrity/mastermind-xpv2-sector-r3b/COMMISSION.md`
§21 deliverable 4: "EN/ZH copy ledger for new display copy." Written for
Sol's four fresh independent critics and a future R3C session. Cold-stranger
rule: every row cites the exact view partial and, where present, an inline
build-comment provenance note; every EN/ZH string pair below was grepped
directly against `mockups/refs/reference_integrity/mastermind-xpv2-sector-r3b/build/views/*.html`
on 2026-08-21 and is quoted verbatim from that grep — not retyped from
memory or from `ORCHESTRATOR_ADJUDICATIONS.md`'s prose summaries.

**Provenance vocabulary used below:**
- **authored-new** — no producer string exists for this; the reference
  lane wrote both the EN and the ZH copy.
- **bound-from-production (verbatim)** — the string(s) are copied unchanged
  from a named production template/JS file.
- **bound-from-production (partial)** — some of the string set is bound
  from a production source, the rest is authored-new to fill a gap the
  production source does not cover (each sub-string is marked individually).

Scope note on `ORCHESTRATOR_ADJUDICATIONS.md`'s "R3C must decide whether to
carry these fallback behaviors" line (§7, R3C handoff draft §5.4 item 3):
the two never-fires-on-this-fixture fallback strings it describes (ZH
falling back to EN instead of a raw slug; an unmapped enum printing the raw
producer value instead of an em-dash) are **behaviors**, not new copy — no
new EN/ZH string pair is minted by either fallback, so neither has a row
here. They are documented in `design_notes.md` §4 (§7 ruling) instead.

---

## 1. New display copy authored by this cycle (production had no equivalent string)

| EN | ZH | surface / where | provenance | why |
|---|---|---|---|---|
| Thin data — read with caution | 数据稀疏 — 请谨慎解读 | Confluence, per-universe thin-data receipt (`confluence.html:609`) | authored-new | Adjudications §4: production's equivalent disclosure is an EN-only `title=` attribute, which house law bans (no translated text in `title=`, CI-guarded per `CLAUDE.md`). |
| No `{noun}` is firing a fresh entry tier right now. | 当前无`{noun}`触发新的入场层级。 | Confluence, Entry-now empty-lane state (`confluence.html:693-697`) | authored-new | Adjudications §4: "empty-lane copy for the four Confluence buckets production ships no list copy for" — this is the Entry-now-specific branch of that new copy. |
| When one crosses, it lands here first. | 一旦有交叉，将最先显示于此。 | Confluence, Entry-now empty-lane "why" line (`confluence.html:696-697`) | authored-new | Same as above — the empty-state `why` clause house law requires (`.r3-empty-why`, spec §9 component vocabulary: "mandatory why"). |
| Nothing reads as `{state}` in this set today | 今日此范围内没有`{state}`的`{noun}` | Confluence, Tailwind/Neutral/Late/Headwind empty-lane state (`confluence.html:699-702`) — one parametrized template applied to all four non-entry-now buckets | authored-new | Adjudications §4: the same "empty-lane copy for the four Confluence buckets" line — this is the shared template covering the four buckets (Entry-now has its own copy above; the other four states share this one). |
| An empty state, not a missing one — every group in this universe carries a reading. | 此为空清单，而非数据缺失 — 此范围内每个组都有读数。 | Confluence, shared empty-lane "why" line for the four non-entry-now buckets (`confluence.html:703-704`) | authored-new | Same as above; the mandatory-why clause for the shared empty-lane template. |
| Rank across all groups | 排名范围：全部分组 | Map, ranked-list clarifier under the rank column (`map.html:104`) | authored-new | Adjudications §5 (D2): "Rank-note clarifier approved and added." |
| The manifest is real; the frames are not carried here. | 目录为真实数据；此处未附带逐帧回放数据。 | Explore, Time Machine no-episode-feed note (`explore.html:1178-1179`) | authored-new | Reference-specific harness disclosure describing the "recorded-not-executed" mechanism unique to this quarantined artifact (`README_BUILD.md` "Time Machine" section); no production equivalent exists because production's real Time Machine does fetch episodes. |
| Full replay reads the episode feed and one file per period. This reference carries the manifest only, so those requests are recorded rather than served — open the harness recorder to see the exact paths a replay asks for(, including `<chunk file>`)... | 完整回放需读取情节数据与各期分片文件。本参考件仅附带目录，因此这些请求被记录而非返回数据——打开工具抽屉的记录器可查看回放实际请求的路径(，包括`<chunk file>`)... | Explore, Time Machine no-episode-feed detail (`explore.html:1180-1183`) | authored-new | Same reference-only mechanism as the row above — quarantine-drawer copy, not a production string. |
| Could not load Time Machine data. | 无法加载时光机数据。 | Explore, Time Machine manifest fetch-fail (`explore.html:1137`) | authored-new (fetch-fail register) | Follows the house "read being updated" fetch-fail register (#3821); no producer twin found in `time_machine.js` for this exact manifest-load failure string — **verify at freeze**: this session did not open `time_machine.js` directly to confirm absence of a producer precedent. |

## 2. Bound-from-production translations embedded/reused verbatim

| EN | ZH | surface / where | provenance | why |
|---|---|---|---|---|
| Replay the full measured history of sector & subsector relative rotation... No predictive claim — this replays measured history. | 回放板块与子行业相对轮动的完整实测历史...无预测性主张——仅回放实测历史。 | Explore, Time Machine standing sub (`explore.html:1117-1119`) | bound-from-production (verbatim) | Inline comment: `time_machine.js:209-212 — the standing sub, verbatim EN + ZH.` |
| In favour — watch for entry | 处于优势——留意入场 | Moving, rotation-event stance (into_strength) (`moving.html:314`) | bound-from-production (verbatim) | Inline comment: `rotation_events.js:181-201, verbatim EN/ZH pairs.` Only `handoff` and `faltering` occur on the frozen fixture; the other three (`into_strength`, `contagion_break`, `correlation_break`) are carried unrendered-on-this-fixture so the capability is not silently dropped (ledger #44 RETAIN per the inline comment). |
| Stand aside — diversification fading | 暂避——分散效果减弱 | Moving, rotation-event stance (contagion_break / correlation_break, shared string) (`moving.html:315-316`) | bound-from-production (verbatim) | Same STANCE map, same citation. |
| Rotation weakening — may close | 轮动转弱——或将关闭 | Moving, rotation-event stance (faltering) (`moving.html:317`) | bound-from-production (verbatim) | Same STANCE map, same citation; this and `handoff` are the only two stances that actually render on the frozen fixture. |
| Watch — don't chase | 观望，不要追高 | Moving, rotation-event stance (handoff, default) (`moving.html:318`) | bound-from-production (verbatim) | Same STANCE map, same citation. When every active event on a row shares one stance, this is hoisted to a shared header line (`sharedStance`, `moving.html:353-357`) instead of repeated per row — a Moving-specific application of the "constant never repeats per row" doctrine law, not new copy. |
| Cycle state → 周期状态 · Regime gate → 市况把关 · Momentum → 动量 · Fragility → 脆弱度 · Heat → 热度 | (as shown) | Map, `#board` reasoning-chain layer labels, `LAYER_ZH` map (`map.html:455-456`) | bound-from-production (verbatim, 5 of 6 entries) | Inline comment (`map.html:446-454`): "Bound from the production China sibling's own twin map (`templates/sector_central_china.html.j2` ~:1425, `LAYER_ZH`) wherever it already carries the word." |
| Trend gate | 趋势把关 | Map, `#board` reasoning-chain layer label, `LAYER_ZH` map (`map.html:456`) | **authored-new** (the one exception inside `LAYER_ZH`) | Same inline comment: "'Trend gate' is absent there [the china sibling map] (that map only has bare 'Trend') so it is authored here" — listed here as instructed by the comment itself. |
| validated | 已验证 | Map, `#board` reasoning-chain tier label (`TIER_ZH`, `map.html:457`) | bound-from-production (verbatim) | Inline comment: "validated from `templates/sector_central.html.j2:3463`, the same 'Validated' the Money view's own tag already renders (QA2-13)." |
| confirmer | 确认项 | Map, `#board` reasoning-chain tier label (`TIER_ZH`, `map.html:457`) | bound-from-production (verbatim) | Inline comment: "Tier words come from the producer's own established twins... confirmer/display from `templates/signal_lab.html.j2:548`'s `tier_labels`." |
| display | 仅展示 | Map, `#board` reasoning-chain tier label (`TIER_ZH`, `map.html:457`) | bound-from-production (verbatim) | Same citation as `confirmer` above. |
| breadth thrust | 广度推进 | Money, `#scc-leadership` rising-star driver leg (`LEG_ZH`, `money.html:912`) | bound-from-production (EN and ZH both) | RESOLVED at freeze (orchestrator, 2026-08-21): `templates/_risk_radar_card.html.j2:205` carries the ZH pair itself — 广度推进 appears verbatim in its help() ZH string, so BOTH halves are bound-from-production. The other two legs (参与广泛 / 回报加速) remain authored, as the inline comment states. |
| broad participation | 参与广泛 | Money, `#scc-leadership` rising-star driver leg (`LEG_ZH`, `money.html:912-913`) | authored-new | Same inline comment: explicitly named as one of "the other two [that] are authored here." |
| return acceleration | 回报加速 | Money, `#scc-leadership` rising-star driver leg (`LEG_ZH`, `money.html:913`) | authored-new | Same inline comment: the second of "the other two [that] are authored here." |

## 3. ARIA / accessible-name copy (bilingual pairs, not visible text)

Distinct from §1/§2 because these are `aria-label`/`aria-labelledby` strings
rather than rendered copy; commission §17 lists "accessible labels" as an
explicit ZH-parity clause, and QA report §3 (QA2-10) previously found these
English-only under `data-lang="zh"`. Grep confirms a ZH-aware code path
exists at each site as of this drafting session — see `design_notes.md` §5
for the caveat that this session did not independently re-run the QA
harness to confirm the fix is live-correct.

| EN | ZH | surface / where | provenance | why |
|---|---|---|---|---|
| Action lanes | 操作分组 | Overview, `[role=tablist]` on the five action lanes, `aria-label` (`overview.html:261,530`) | authored-new | Reference-authored accessible-name copy for a tablist that has no production tab-role equivalent to bind from; language-aware assignment at `overview.html:530` (`isZh ? '操作分组' : 'Action lanes'`). |
| Show themes or sectors on the rotation map | 切换轮动图的主题或板块 | Map, `[role=group]` universe segmented control, `aria-label` (`map.html:871-876`) | authored-new | Same class of reference-authored accessible name for a filter/segment group commission §17 requires `role=group`/`aria-pressed` semantics for. |
| Universe | 范围 | Confluence, universe `[role=tablist]`, `aria-label` (`confluence.html:330,1034`) | authored-new | Reference-authored tablist accessible name. |
| Timing states | 时机状态 | Confluence, timing-state `[role=tablist]`, `aria-label` (`confluence.html:334,1035`) | authored-new | Reference-authored tablist accessible name. |

**Decorative connector, not a copy row.** The Moving "moved to" fragment
QA report QA2-11 flagged (`role="img" aria-label="moved to"` x9, meaningless
in both languages) is **not** listed as a copy pair here: grep of the
current `moving.html:304-308` shows the connector is now emitted as
`<span class="r3-arrow" aria-hidden="true"></span>` — no `role="img"`, no
`aria-label` — i.e. the fix removed the accessible name entirely rather
than translating it, per the inline comment: "this CSS-drawn connector
glyph is decorative — the flanking names carry the meaning" (`moving.html:304-307`
paraphrase quoted at length in `design_notes.md` §5). There is accordingly
no EN/ZH pair to ledger for this surface anymore.

## 4. Explicitly out of scope for this ledger

- **Producer `category` filter values in Explore** (`Software`, `Materials &
  Mining`, `Artificial Intelligence`, `US Sectors (EW)`, ...) — QA report §3
  confirms these render English-only under `data-lang="zh"` in 21 buttons,
  but this is a **recorded producer gap**, not reference-authored copy
  (`ORCHESTRATOR_ADJUDICATIONS.md` §6/§7: the category filter's own summary
  always names the active state, and an unmapped enum's ZH-fallback-to-EN
  behavior is a disclosed fallback, not new copy — see the scope note at the
  top of this file).
- **Finance period tokens** (`1D/5D/20D/60D/MTD/YTD/RS60/W/2W/M`) — QA
  report §3 explicitly notes these "are read as conventional untranslatable
  finance tokens and are not filed" as a ZH-parity finding; this ledger
  follows the same convention and does not carry them as new copy pairs.
  **Verify at freeze**: this session located `W`/`2W`/`M` as column-header
  abbreviations inside the Money `#scc-leadership` LAS table
  (`money.html:945` shows the analogous `Universe/指数域` header pattern for
  that same table) but did not locate an accessible-name pair (as opposed to
  a visible abbreviation) specifically for `W`/`2W`/`M` cells to confirm or
  refute whether an ARIA row is owed here — a fresh session should grep
  `money.html` for `aria-label` near the LAS/momentum column headers before
  relying on this row's absence.

---

## Entry counts by provenance

- **Authored-new (visible copy), §1:** 9 EN/ZH pairs across 5 surfaces
  (Confluence thin-data dot; Confluence entry-now empty lane × 2 strings;
  Confluence shared 4-bucket empty lane × 2 strings; Map rank note; Explore
  Time Machine harness-only notes × 3 strings).
- **Bound-from-production (verbatim), §2:** 11 of 14 rows (5 `LAYER_ZH`
  entries minus the 1 authored exception; 3 `TIER_ZH` entries; 4 STANCE
  entries; the Time Machine standing sub).
- **Authored-new inside a mostly-bound set, §2:** 3 rows (`Trend gate` inside
  `LAYER_ZH`; `broad participation` and `return acceleration` inside
  `LEG_ZH`).
- **Ambiguous provenance: 0 rows** — the one freeze-flagged row (`breadth
  thrust` / 广度推进) was resolved at freeze: both halves bound verbatim from
  `templates/_risk_radar_card.html.j2:205`.
- **Authored-new (ARIA-only), §3:** 4 `aria-label` pairs.
- **Total EN/ZH pairs ledgered:** 24 (9 + 14 + 4, less double-counting none
  — §1 and §2 and §3 are disjoint surfaces).
