# W1 frozen spec — trust strip, changed-today, absolute-vs-relative truth

`child: macro-flow-observatory-v2-w1-trust-change-20260902-fable-001`
`governing freeze: research/FLOW_OBSERVATORY_V2_MASTERPLAN_BY_FABLE.md (§4 contract, §6 vocabulary, §7 experience)`
`design authority: this spec (pinned by Fable main loop). Builders implement; they do not redesign.`

## 0. Not done unless (wave gates)

1. All new tests below written FIRST and failing, then green; the two mutation checks
   demonstrably fail when the old semantics are restored.
2. Fresh end-to-end: canonical rebuild from real data produces a page where the Autos-class
   row shows quadrant "still selling, pressure easing" with abs −0.9% AND rel +1.9σ both
   at rest, and the Southbound chip shows "+¥7.1B / below-norm pace, fading" semantics
   (live values may differ — the SEMANTICS must hold for whatever the data says).
3. Zero "big money"/"institutions"/大资金/机构买入 unqualified strings anywhere in the
   rendered page (order-size/seat proxies use §6 language).
4. Browser evidence matrix posted in the PR body: dark/light × EN/ZH × 1440/390, zero
   console errors, no horizontal page scroll, no clipped dates/labels.
5. `python3 -m scripts.build_flow_velocity` + `python -m scripts.check_template_site_sync`
   clean; existing test suites green after consumer updates; agentos validate 0 errors.
6. Committed site/ bytes rebuilt through the canonical path (builder + asset sweeps land
   via the render lane post-merge; do NOT hand-edit site/flow_velocity.html).

## 1. Engine changes (`engine/flow_velocity.py` + new `engine/flow_observatory/`)

### 1.1 Vocabulary migration (flow_velocity.py `_classify`, :147-156)

Replace returned strings exactly per masterplan §6 table:
`above norm, rising`/`高于常态·升温` · `above norm, cooling`/`高于常态·降温` ·
`below norm, worsening`/`低于常态·加剧` · `below norm, easing`/`低于常态·趋缓` ·
`near its norm`/`接近常态` · `no data`/`无数据`.

### 1.2 Quadrant (new helper in flow_velocity.py or contract.py)

```python
def quadrant(abs_dir: str, rel_dir: str, sufficient: bool) -> str:
    # abs_dir/rel_dir in {"positive","negative","neutral","unknown"}
    # returns one of: true_accumulation | improving_but_still_selling |
    #   weakening_but_still_buying | true_distribution | neutral_or_unknown
```
`sufficient=False`, any `unknown`, or either axis `neutral` → `neutral_or_unknown`.
Axis directions: rel from vel_primary vs ±0.5σ (provisional until W5); abs from the
20-session raw mean net rate (themes: `rate_4wk` sign with de-minimis |x| < 0.1pp →
neutral; southbound: `flow_1m_b` sign with de-minimis |x| < 0.5 ¥B → neutral).
EN/ZH display strings: masterplan §6 quadrant table, emitted as `quadrant_en`/`quadrant_zh`.

### 1.3 Per-row additive fields (ashare_sectors.rows[], hk rows where computable)

`abs: {period:"20d", value: rate_4wk, unit:"pct_rate", direction}` ·
`rel: {value: vel, unit:"sigma", direction, reference_window:126}` ·
`quadrant`, `quadrant_en`, `quadrant_zh` · `rank` (1-based by |vel| within lens) ·
`rank_change` (vs previous valid session, null if no log) · `state_started`,
`state_age_sessions`, `prior_state` (from state_log; null+`"first tracked session"` note
when absent). Existing fields unchanged. Southbound aggregate gains the same
abs/rel/quadrant treatment (`abs.value=flow_1m_b, unit:"cny_b"`).

### 1.4 market_read (new top-level, assembled in contract.py)

```json
"market_read": {
  "absolute_breadth":     {"positive":0,"negative":0,"neutral":0,"missing":0,"denominator":0},
  "relative_breadth":     {"positive":0,"negative":0,"neutral":0,"missing":0,"denominator":0},
  "acceleration_breadth": {"strengthening":0,"cooling":0,"easing":0,"worsening":0,"neutral_or_unknown":0,"denominator":0}
}
```
Computed for the theme lens (n=22) AND names (n=1518+unscored). `missing` INCLUDES the
previously-silent unscored names — flow_velocity.py must count kin-None drops
(engine :306-316) into a new `n_unscored`, and denominator = scored + unscored.

### 1.5 sources[] (new top-level; W1 = identity/dates/coverage; W2 adds status machine)

One block per masterplan §3 leg: `source_id`, `source_kind`, `provider`, `market`,
`effective_date` (the leg's own as_of), `expected_availability`
("T+0 after CN close" / "T+0 after HK close" / "expected T−1" / "discontinued 2024-08-16"
/ "event-window"), `coverage` (`n_observed`, `n_sized` where applicable, `pct_names`),
`first_known_at` (build instant this leg's date first appeared — from state_log, null on
first run), `status`: W1 emits only `HISTORICAL_ONLY` (northbound) vs `null` (machine
states land in W2 — do not fake them).

### 1.6 change_summary + state_log (`engine/flow_observatory/changes.py`)

`data/flow_observatory/state_log.jsonl` — one line per valid market session:
`{"session":"YYYY-MM-DD","written_at":iso,"themes":{id:{"quadrant","state","vel","rank","abs":x}},"aggregate":{...},"market_read":{...}}`.
`append_state_log()` idempotent per session (re-run same session → replace own line,
byte-stable otherwise). Advance gate (verified API): `engine.ledger_lane.asia_advance_enabled()
or engine.ledger_lane.nightly_advance_enabled()` — asia-close (CN_LANE=asia) is the
fresh-data lane, US-nightly (COLLECT_LANE=nightly) the rebuild backstop; idempotence
makes the double-advance day safe. Intraday/manual lanes never append (the gate returns
False there by construction). Do not invent a new guard.
`compute_changes(current, log)` → `change_summary`: `previous_valid_session`,
`material_change` bool, `transitions[]` ({id, from_quadrant, to_quadrant}),
`rank_movers[]` (|Δrank| ≥ 3), `source_revisions:[]` (always [] in W1). Missing log →
all-null + `"no_previous_snapshot"` reason, NEVER zero-change.

### 1.7 contract.py assembly + validation

`build_v2(panels, changes) -> dict` merges §1.3-1.6 into the desk payload additively and
sets `schema:"flow_observatory.v2"`, `authority:"context_only"`, `generated_at`,
`market_session`. `validate(desk)` raises on: missing denominators, quadrant
inconsistent with abs/rel directions, top-level as_of imitating a leg date, absolute and
relative fields disagreeing with their direction enums. Builder calls validate before
writing; tests call it on fixtures.

### 1.8 Consumer migration

Update `engine/cn_theme_tape.py` (reads state/state_zh verbatim, :247-249,:460-467) +
`tests/test_cn_theme_tape.py:110-111` to the new vocabulary. Apply the consumer-sweep
packet (appended to the W1 commission) for any additional verbatim consumers.
`docs/site_semantics/china.md` flow-velocity entries updated to the new vocabulary and
two-axis semantics.

## 2. Template changes (`templates/flow_velocity.html.j2`)

Keep the existing fv-* idiom, tokens, t() macro, LENS tips, JS-off behavior, reveal
motion. No new fonts/colors outside theme.css tokens. Sections after W1 (order):

### 2.1 Hero (evolve existing, :422-500)

- Title stays "Capital Flow Velocity / 资金流速" (page identity unchanged in W1).
- Thesis line REPLACED with the two-axis verdict, generated from market_read (themes):
  EN: `Large-order pressure ran above its norm in {relpos} of {n} themes; {abspos} saw
  positive absolute 4-week flow. {stance}` ZH: `主力大单压力高于常态的主题 {relpos}/{n}；
  4周绝对净流入为正的主题 {abspos} 个。{stance_zh}`
  Stance vocabulary (doctrine Law 1): default `Watch — don't chase / 观察，勿追高` unless
  no material change → `No material shift — nothing to chase / 无重大变化`.
- The 大资金/"big money" strings at :434-444 and :506 are REMOVED (§6 language law).
- Southbound vitals chip becomes two-fact: `Southbound {sign}{abs}¥B / 1m · pace {rel}σ
  vs norm, {trend-word}` — never a lone "accelerating out".
- The old single breadth gauge is replaced by the split breadth line (2.4).

### 2.2 Trust strip (NEW section, directly under hero)

```html
<section class="fv-sec fv-trust fv-reveal" id="sources" aria-label="{{ t('Data sources','数据来源') }}">
  <div class="fv-trust-row">
    {% for s in snap.sources %}
    <div class="fv-src fv-src--{{ s.ui_state }}" data-tip-en="..." data-tip-zh="...">
      <span class="s-name">{{ t(s.name_en, s.name_zh) }}</span>
      <span class="s-meta tnum">{{ s.effective_date or '—' }} · {{ s.coverage_line }}</span>
      <span class="s-state">{{ t(s.state_word_en, s.state_word_zh) }}</span>
    </div>
    {% endfor %}
  </div>
</section>
```

W1 `ui_state` ∈ `current` | `expected_lag` | `behind` | `historical` (derived from the
leg's effective_date vs newest session using desk_guard's existing lag logic; W2 replaces
with the binding machine). State words: `current`→"current/最新" ·
`expected_lag`→"expected T−1/预期T−1" · `behind`→"behind — showing {date}/滞后 · 显示
{date} 数据" · `historical`→"historical only — ended {date}/仅历史 · 止于{date}".
LENS tip per chip: kind in plain words + provider + method line (§6 language; e.g.
"large & super-large order-size proxy — order-size classification, not identified
investors / 大单+超大单口径，非机构身份"). CSS (new, in-page style block per existing
page convention):

```css
.fv-trust-row{display:flex;gap:10px;flex-wrap:wrap}
.fv-src{border:1px solid var(--line);border-radius:10px;padding:8px 12px;
  display:flex;flex-direction:column;gap:2px;min-width:150px;flex:1 1 150px;max-width:230px}
.fv-src .s-name{font-size:12px;font-weight:600}
.fv-src .s-meta{font-size:11px;color:var(--muted);font-variant-numeric:tabular-nums}
.fv-src .s-state{font-size:10px;letter-spacing:.08em;text-transform:uppercase;color:var(--muted)}
.fv-src--current .s-state{color:var(--up)}
.fv-src--behind{border-color:color-mix(in srgb,var(--warn,#c90) 45%,var(--line))}
.fv-src--behind .s-state{color:var(--warn,#c90)}
html[data-theme="light"] .fv-src--behind{background:color-mix(in srgb,var(--warn,#c90) 6%,transparent)}
@media (max-width:640px){.fv-src{min-width:calc(50% - 5px);max-width:none}}
```
(Adapt token names to theme.css actuals; light theme gets its OWN behind-treatment —
tinted paper + deepened ink, not the dark glow.)

### 2.3 What changed today (NEW section)

Renders change_summary: list of transitions ("{name}: {from} → {to}"), rank movers,
new-degradation lines (W2). Quiet state REQUIRED exactly:
EN "No material flow-state transition since the previous valid market session ({date})."
ZH "自上一有效交易日（{date}）以来，资金状态无重大变化。"
First-run state: EN "Change tracking begins today — no prior tracked session." ZH
"变化追踪自今日开始——暂无历史对比。" Max 8 rows visible; overflow behind
`<details>` ("all {n} changes").

### 2.4 Absolute × relative market read (NEW section — the page's signature device)

Split breadth lines (from market_read, one-integer law — these are THE canonical counts):
EN `Pressure vs norm: {p} above · {nn} near · {ng} below — of {d} themes` /
`Actual 4-week flow: {ap} positive · {an} negative · {am} neutral — {miss} unscored`
(ZH equivalents). Then the quadrant board:

```html
<section class="fv-sec fv-reveal" id="quadrant">
  <h2>{{ t('Pressure vs actual flow','相对压力 × 绝对流向') }}
      <span class="sub">{{ t('four honest states — themes placed by both axes','按两轴划分的主题分布') }}</span></h2>
  <div class="fv-quad">
    <div class="q-cell q-acc"><h3>{{ t('real inflow, above norm','真实流入·高于常态') }}</h3>{chips}</div>
    <div class="q-cell q-imp"><h3>{{ t('still selling, pressure easing','仍净流出·压力改善') }}</h3>{chips}</div>
    <div class="q-cell q-weak"><h3>{{ t('still buying, pace fading','仍净流入·动能转弱') }}</h3>{chips}</div>
    <div class="q-cell q-dist"><h3>{{ t('real outflow, below norm','真实流出·低于常态') }}</h3>{chips}</div>
  </div>
  <p class="q-neutral">{{ t('quiet / insufficient','平静/数据不足') }}: {names or t('none','无')}</p>
</section>
```

Chip = `<span class="q-chip"><b>{name}</b> <span class="tnum">{abs:+.1f}% · {rel:+.1f}σ</span></span>`
(both axes on every chip — the anti-conflation device). CSS:

```css
.fv-quad{display:grid;grid-template-columns:1fr 1fr;gap:10px}
.q-cell{border:1px solid var(--line);border-radius:12px;padding:12px 14px;min-height:96px}
.q-cell h3{font-size:11px;letter-spacing:.06em;text-transform:uppercase;margin:0 0 8px;color:var(--muted)}
.q-acc{border-left:3px solid var(--up)} .q-dist{border-left:3px solid var(--down)}
.q-imp{border-left:3px solid color-mix(in srgb,var(--up) 40%,var(--line))}
.q-weak{border-left:3px solid color-mix(in srgb,var(--down) 40%,var(--line))}
.q-chip{display:inline-flex;gap:6px;align-items:baseline;border:1px solid var(--line);
  border-radius:8px;padding:3px 8px;margin:0 6px 6px 0;font-size:12px}
.q-chip .tnum{color:var(--muted);font-size:11px}
@media (max-width:820px){.fv-quad{grid-template-columns:1fr}}
```
Directional inks via --up/--down tokens ONLY (zh 红涨绿跌 flip rides the tokens).
Accessible text alternative: a visually-hidden ordered list summarizing cell membership.

### 2.5 Groups board (evolve existing rotation board + flow map)

- Row primary chip = quadrant label; velocity-state (new vocabulary) moves into the row's
  LENS tip with the exact-arithmetic line (existing rate() tooltip contract preserved).
- Add at-rest columns: `abs 4wk` (raw, signed, muted) beside `vs norm` (rel, signed) —
  both visible without hover (kills the tooltip-only raw rate).
- Add `rank Δ` column (▲n/▼n/–, from rank_change; "—" with "first tracked session" tip
  when null).
- Section h2 re-copied: EN "Theme flow board — large-order pressure by theme" ZH
  "主题资金板 — 按主力大单压力排序". Sub: "curated overlapping themes — not official
  sectors / 精选主题（可重叠），非官方行业分类".
- Momentum + confluence sections DEMOTE: render as two collapsed `<details class="fv-disc">`
  blocks under the board (summary lines carry their true counts), full contents unchanged
  inside. Their h2s drop out of the L1 outline.

### 2.6 Cross-border channels (truth repair only)

- Southbound card: abs + rel + accel co-rendered (2.1 chip form), state word from new
  vocabulary.
- HK holdings panel header gains its OWN date + expected-T−1 chip (its as_of was never
  rendered — fix): `{{ t('as of','截至') }} {{ snap.hk_names.as_of }} ·
  {{ t('expected T−1','预期T−1') }}`.
- Northbound card unchanged (already honest).

## 3. Builder (`scripts/build_flow_velocity.py`)

Compose through contract.py (`build_v2`, `validate`); append state_log under the lane
guard; keep the additive never-fatal shape (a state_log/contract failure logs + skips the
v2 extensions rather than killing the page build).

**Ratified deviation (W1 repair round, ratified by the program principal):** the line
above originally read "...but validate() failure on the FINAL payload blocks the desk.json
write and annotates, because publishing a contract-violating payload is the defect class
this program exists to kill." As BUILT, `scripts/build_flow_velocity.py` does not block the
write on a `ContractError`: it logs `log.error(...)`, emits a `::error` annotation, and
falls back to publishing the PRE-v2 (plain) payload — `desk.json`/`flow_velocity.html`
still get written every run, just without the v2 extensions on the run that failed
validation. This is the correct behavior and supersedes the block-the-write line: a v2
payload that fails `validate()` is worth refusing, but the EXISTING plain flow-velocity
page (which has shipped reliably for months) must never go dark because a new, additive
extension had a bad night — that would make the v2 program itself a new source of outage
risk for a page that worked before it existed. The `::error` annotation still fires so the
failure is visible and actionable; it just does not take the whole desk down with it.

## 4. Tests (write failing FIRST; file: tests/test_flow_observatory_contract.py + edits)

1. test_absolute_negative_relative_positive_is_improving_but_still_selling
2. test_absolute_positive_relative_negative_is_weakening_but_still_buying
3. test_quadrant_insufficient_or_unknown_is_neutral
4. test_autos_fixture_cannot_render_unqualified_inflow (build template with the frozen
   Autos-shape fixture; assert quadrant label present and no bare "inflow"/"流入" state
   without the qualifier pair)
5. test_southbound_fixture_keeps_absolute_and_relative_visible
6. test_market_read_counts_include_neutral_and_unscored (denominator = scored+unscored)
7. test_rank_and_state_changes_compare_previous_valid_snapshot_only
8. test_missing_previous_snapshot_yields_null_not_zero
9. test_no_material_transition_yields_quiet_message (rendered HTML contains the §2.3
   string)
10. test_source_leg_dates_stay_distinct (hk leg date ≠ top as_of in sources[])
11. test_order_size_copy_carries_proxy_disclosure (rendered page contains the §6 proxy
    line; contains NO unqualified 大资金/big money/institutions-buying strings)
12. test_en_zh_parity_for_new_labels (every new EN string has a ZH twin via t())
13. test_state_log_append_is_idempotent_per_session
14. test_added_top_level_keys_do_not_break_known_consumers (cn_theme_tape over a v2
    fixture)
15. test_validate_rejects_quadrant_axis_mismatch
16. Existing suites updated: test_flow_velocity.py label expectations,
    test_cn_theme_tape.py:110-111 vocabulary, test_flow_desk_staleness.py untouched
    (desk_guard unchanged in W1).

Mutation checks (documented in PR body with the failing output):
M1 revert `_classify` to old strings → tests 11/12/16 fail.
M2 render only rate_rel at rest (drop abs column) → test 4/5 fail (assert both-axes-at-rest
via the template fixture render).

## 5. Real proof (PR body obligations)

Canonical rebuild from real current data; browser matrix dark/light × EN/ZH × 1440/390
(verify_shots/ convention); interaction proof (sort, drilldown, LENS tips, market toggle,
mobile scroll); zero console errors; performance note (build wall-time before/after —
budget: no regression >10% on the builder step); limitations + authority boundary
(context_only) stated.
