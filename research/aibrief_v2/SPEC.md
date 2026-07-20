# AI Brief v2 — program spec (ABX)

Chartered 2026-07-19 by operator order: "Conduct a complete AI brief upgrade for all 3
briefs." One PR. Owner: main loop (Fable) — prompts + this spec; sonnet builder — engine
mechanics; opus designer — surfaces. Doctrine: `docs/DESIGN_DOCTRINE.md` binds every
user-visible string, INCLUDING the LLM's own output (the prompt is now a Tier-1
copywriter contract).

## 0. The seven operator complaints → the seven fixes

| Complaint | Root cause found | Fix |
|---|---|---|
| Machine text everywhere ("growth_score -0.143", "-2.5σ", "panel: hk.sector_rs", "cross_asset_confirm", "FR007") | State JSON keys leak straight into prose; prompts even *ask* for citations | VOICE law in every prompt + deterministic style lint + one rewrite retry (§4) |
| Rotation thesis parroted in every brief | `DEFAULT_THESIS` injected every run + `rotation_check` is a REQUIRED schema field | Field becomes conditional; "never restate the thesis wording" rule (§3) |
| "Q1 Goldilocks" black-and-white labels; blind to the reflation drift | `_macro_summary` passes only `transition_state:"TRANSITIONING"` — no direction, no drift, though the engine computes flip_condition/flip_margin/dwell + regime_history.parquet | `regime_path` context block + REGIME=POSITION law (§5a) |
| Transmission / Disagreements incomprehensible | No format contract | "If X → then Y" plain-chain contract, ≤2 items, word caps (§2) |
| Wall-of-paragraph top; What-to-watch too long | Schema has no glance tier | `tldr` bullets (3–5, capped) + stance line; watch items "Trigger: meaning" ≤16 words (§2) |
| No permanent illustration components | All content is free prose | `key_facts` deterministic chip rail — engine-computed, bilingual, tone-tinted (§6) |
| BTC daily is wasteful; US/China/BTC UIs inconsistent | Global `interval_days`; three renderers diverged | Per-lens interval (btc=3) + ONE shared body renderer for all four surfaces (§7) |

## 1. Files & ownership

| Area | Files | Owner |
|---|---|---|
| Prompts + schema constants | `engine/master_brain.py` (constants only) | main loop — ALREADY EDITED, do not rewrite the prompt strings |
| Engine mechanics | `engine/master_brain.py` (functions), `engine/neuralweb/brief_context.py`, `config.yml` | builder |
| Surfaces | `templates/dashboard.html.j2` (dlg-aibrief), `templates/china.html.j2` (cnx-dlg-aibrief), `templates/hk.html.j2` (hkx-dlg-aibrief), `templates/aibrief.html.j2`, NEW `templates/_aibrief_body.html.j2`, `templates/aibrief.js` (+ paired `site/aibrief.js`), `templates/masterbrief.js` (retire if orphaned — verify), `scripts/build_aibrief.py` | designer |
| Tests | `tests/test_master_brain*.py`, `tests/test_brief_context.py`, `tests/test_aibrief_page.py`, `tests/test_aibrief_w4_panels.py` | builder (after both lanes land) |

PAIRED-ASSET LAW: `templates/aibrief.js` ships as `site/aibrief.js` — byte-match in the
same PR (`python -m scripts.check_template_site_sync --fix`). Same for masterbrief.js if
touched. NO other site/ or data/ churn in this PR (source-only; restore any local build
artifacts before commit).

## 2. Schema — `master_brief.v2` (additive; every v1 key retained)

LLM-emitted, zh-translated by the existing `_translate_brief` pipeline:

| key | type | contract |
|---|---|---|
| `tldr` | list[str], 3–5 | NEW. Point-form glance. Each item "Head: rest", head ≤3 words, rest ≤14 words. Item 1 = the single most important thing today. LAST item MUST start "What to do:" + stance vocab (§3 stance law). |
| `summary` | str | kept. ONE sentence ≤22 words, plain words (face teaser). |
| `regime_read` | str | kept. ≤2 short paragraphs; MUST narrate position-within-regime + drift direction (§3 regime law). |
| `conflicts` | list[str], 1–3 | kept. Each "Head: A says X, B says Y — what it implies", ≤30 words. |
| `transmission` | list[str], 0–2 | kept. Each "If <thing that is happening> keeps up → <what follows next>", ≤24 words, zero acronyms. |
| `rotation_check` | str, OPTIONAL | kept key, new semantics: emitted ONLY when evidence meaningfully moved for/against the standing playbook; NEVER restates the thesis wording; ≤40 words. Omitted → UI section absent. |
| `watch_items` | list[str], 2–4 | kept. Each "Trigger: what it means", ≤16 words. |
| `confidence` | low/medium/high | unchanged |
| `theses`, `forward_watch`, `forward_read` | | unchanged (macro only; existing hard rules stand) |

Engine-emitted (deterministic — never from the LLM):

| key | type | contract |
|---|---|---|
| `key_facts` | list[obj], ≤6 | `{key, label_en, label_zh, value_en, value_zh, tone}` — tone ∈ good/warn/bad/neutral/info. Built per lens from calibrated state (§6). Fail-open: missing source → chip omitted, never raises. |
| `refresh_days` | int | the lens's interval (1 or 3) — UI renders the cadence chip honestly |
| `style_flags` | list[str] | banned tokens that survived the rewrite retry (observability; NOT rendered on user tiers) |

`schema` field bumps to `"master_brief.v2"`. Builder greps every consumer of the literal
`master_brief.v1` and fixes string-matches (renderers are `get()`-based fail-open;
`engine/neuralweb/cortex.py` + `brain_gateway.py` read briefs — verify they don't pin).

zh translation: extend `_ZH_SCALARS`/`_ZH_LISTS` with `tldr` (list). `key_facts` is
bilingual at build time from the §6 vocab — never sent to the translator.

## 3. Prompt architecture (constants already written by main loop — wire, don't rewrite)

Shared blocks composed into all three system prompts:
- `_VOICE_LAW` — the no-machine-text writing contract (bans snake_case, σ/z/percentile,
  panel citations, quad codes; number ration; acronym policy; "taxi-driver test").
- `_REGIME_MAP_LAW` — regime = position on a map, drift is the story.
- `_STANCE_LAW` — final tldr line restates the DETERMINISTIC system posture in the
  doctrine stance vocabulary (Act · Get ready · Watch — don't chase · Protect gains ·
  Stand aside · Ignore); may soften, never escalate. (Epistemics: the LLM never
  originates a stance — it translates the system's own posture keys.)
- `_THESIS_RULE` — playbook mentioned ONLY in optional `rotation_check`, only on
  meaningful movement, never restated verbatim, never in tldr/regime_read/conflicts.
- `_SCHEMA_TAIL_V2` — the field contract of §2 with hard word budgets.
- Same-tape rule compressed to 3 lines; stale/absent honesty, no-fabrication,
  no-sizes/no-trades, small-sample honesty all retained.
- `_FORWARD_TAIL` + `_MACRO_THESES_TAIL` retained verbatim (ledger contracts).

## 4. Style lint (deterministic, engine)

`_style_violations(text: str) -> list[str]` over every LLM string field (tldr items,
summary, regime_read, conflicts, transmission, rotation_check, watch_items,
forward_read):
- snake_case token: `\b[A-Za-z]+_[A-Za-z0-9_]+\b`
- sigma/z/percentile: `σ`, `\bz[- ]?scores?\b`, `[+-]?\d+(?:\.\d+)?\s*σ`, `%ile`, `\bpctile\b`, `\bpercentile\b`
- panel citations: `\bpanels?\s*:`, `\bdashboards?\s*:` (colon form only)
- quad codes: `\bQ[1-4]\b` (regime quads; calendar quarters like "Q2 GDP" are a rare
  loss — acceptable, the model is told to write "second-quarter GDP")
- hard-banned tokens (case-insensitive): `cross_asset_confirm, neural_web, nw_synthesis,
  tape_family, cphase, mvrv_z, funding_z, etf_flow_z, oi_mcap, hy_oas, ntfs, display-tier,
  display_only`
- paren-gated tokens (allowed ONLY inside parentheses following plain words, e.g.
  "China's 7-day interbank rate (FR007)"): `FR007, MVRV, NUPL, SSR, DVOL, EBP, SOFR, IORB, LPR, RRR`

Pipeline in `_call_model` (or a wrapper): reply → parse → collect violations across
fields → if any, ONE rewrite call (small system prompt listing the offending tokens,
original reply as user content, "same JSON, same claims, plain language") → re-parse; if
violations persist, keep the reply and record `style_flags`. The reply cache stores the
FINAL post-lint text (cache key unchanged: model‖system‖user of the ORIGINAL call).
Degrade-never-raise everywhere.

## 5. Context integration

a) **`regime_path` (macro state)** — new block in `_macro_summary` output:
   - from `data/regime/latest.json`: `transition_state`, `transition_state_raw`,
     `transition_dwell_remaining`, `flip_condition` (verbatim), `flip_margin`,
     `transition_flags` (names only).
   - from `data/regime/regime_history.parquet` (fail-open if unreadable): growth/inflation
     scores now vs 5 and 20 rows back + plain drift strings the builder composes
     deterministically, e.g. `"growth −0.07 now vs +0.14 20d ago (cooling toward the
     Reflation border)"` — direction word from sign of delta only; no new thresholds.
   - china lens: pass `pending_quad`/`pending_days` (already in state) + same-shape
     drift from china history parquet if one exists under `data/china_regime/`
     (builder verifies; omit silently if absent).
b) **`btc_slice()`** in `engine/neuralweb/brief_context.py` (cap 4 096 bytes, same
   fail-open/stale contract): blocks `market_core`, `liquidity_plumbing`,
   `cross_asset_flows`, `contagion` (when present), `attention` (only items whose text
   mentions btc/bitcoin/crypto, ≤3), `cortex` (tail). Drop order (first-dropped →):
   attention, contagion, cross_asset_flows, cortex, liquidity_plumbing, market_core.
   Wire: `gather_btc_state` sets `state["neural_web"] = btc_slice(root)` (lazy import,
   never fatal). No synapse registration (reads existing artifacts only).
c) BTC prompt already instructs use of the NW block + stale honesty (main-loop edit).

## 6. `key_facts` vocab (deterministic chips; EXACT strings — builder implements tables as data)

Tone: `good`(green) `warn`(amber) `bad`(red) `neutral`(muted) `info`(accent/blue).
Rule: unknown/missing source value → omit the chip (≤6 shown, order below). Labels are
fixed; values come from the maps below; NEVER pass raw enum text through.

**macro** (sources: regime latest / bonds backdrop / cross_asset_confirm / market_drivers):
1. `regime` — label "Regime/市场格局". value = quad_name EN + (transition_state=="TRANSITIONING" → " · shifting"/" · 转换中"). quad_name zh map: Goldilocks→金发姑娘(不冷不热), Reflation→再通胀, Stagflation→滞胀, Deflation→通缩/放缓. tone: Goldilocks good, Reflation info, Stagflation warn, Deflation bad; any+shifting → warn.
2. `risk` — "Market risk/市场风险". macro_risk.label: low→"Low/低" good; moderate→"Moderate/中等" neutral; elevated→"Elevated/偏高" warn; severe→"Severe/严重" bad.
3. `money` — "Money/资金面". liquidity_overlay contains expand→"Expanding/扩张" good; contract→"Tightening/收紧" warn; else "Neutral/中性" neutral.
4. `bonds` — "Bonds vs stocks/债股关系". cross_asset_confirm.verdict: confirm→"Agree/一致" good; diverge→"Disagree — bonds worried/分歧 — 债市担忧" warn; mixed→"Mixed/好坏参半" neutral.
5. `credit` — "Credit/信用". bonds.credit.distress_band + direction: calm+widening→"Calm, but widening/平静但走宽" warn; calm→"Calm/平静" good; stressed→"Stressed/紧张" bad; else band prettified, neutral.
6. `driver` — "What's moving markets/当前主导". market_drivers.primary_label + direction arrow word ("down"→"— down/走弱", "up"→"— up/走强"). tone info.

**china** (sources: china/hk regime latest, china_intel policy):
1. `cn_regime` — "China regime/A股格局". quad_name map as macro + pending_quad non-null → " · shifting/ · 转换中" warn.
2. `policy` — "Policy/政策". policy impulse easing→"Cutting rates/在降息" info; tightening→"Tightening/在收紧" warn; else "On hold/按兵不动" neutral.
3. `cn_money` — "System money/系统流动性". liquidity_overlay map as macro `money`.
4. `hk_risk` — "Hong Kong/香港". hk risk_state: risk_on→"Risk-on/偏积极" good; risk_off→"Risk-off/避险" warn; else prettified neutral.
5. `peg` — "HK dollar/港元". peg_state normal/mid→"Steady/稳定" good; strong side→"At strong edge/贴近强方" info; weak side→"At weak edge — watching/贴近弱方 — 需留意" warn.
6. `cn_leader` — "Leading sector/领涨板块". top of sector_rs by rank (display name EN; zh via existing sector zh names if trivially available, else same EN name). tone info.

**btc** (sources: `_btc_signals_row` rich columns):
1. `system` — "System stance/系统姿态". composite_state: ACCUMULATE→"Accumulate/系统偏多" good; HOLD/NEUTRAL→"Hold/持有" neutral; DISTRIBUTE→"Distribute/系统减持" warn; + when alloc_optimal==0 → value suffix " · allocation 0%/ · 仓位 0%" and tone bad. override_active true → append " (override)/（人工覆盖）".
2. `cycle` — "Cycle clock/周期时钟". cycle_phase markup/markdown/accumulation/distribution → "Early rise/上行早段" good, "Late decline/下行后段" warn (markdown), "Bottoming/筑底" info, "Topping/筑顶" warn; + cphase_pct present → " · ~{pct}% through/ · 约{pct}%进度" (integer).
3. `value` — "On-chain value/链上估值". valuation_state cheap→"Cheap/偏便宜" good; fair→"Fair/中性" neutral; rich→"Expensive/偏贵" warn.
4. `leverage` — "Leverage/杠杆". leverage_stress high or funding_z>2 → "Crowded longs/多头拥挤" warn; low→"Light/清淡" good; else "Normal/正常" neutral.
5. `etf` — "ETF flows/ETF资金". etf_flow_state inflow→"Money coming in/资金流入" good; outflow→"Money leaving/资金流出" warn; else "Flat/持平" neutral.
6. `liquidity` — "Global money/全球流动性". global_liq_regime expanding→"Expanding/扩张" good; contracting→"Contracting/收缩" warn; else neutral.

Builder: implement as `LENS_KEY_FACTS: dict[str, callable]`, pure functions over the
gathered state dict (so tests can feed fixtures), attached in `run()` after `synthesize`
(brief["key_facts"] = ...). Value-map misses → prettify (`str.replace('_',' ').title()`)
+ neutral tone, never raise, never block.

## 7. Cadence

- config.yml `master_brain:` gains `interval_days_by_lens: {btc: 3}` (global
  `interval_days: 1` stays the default for macro/china).
- `run()` resolves `_interval_for(lens, cfg)` = by-lens override → global → 1, clamp 1..7.
  The existing `_brief_age_days` gate logic is reused unchanged.
- Brief payload gains `refresh_days`. All surfaces show the cadence chip:
  "Updated daily/每日更新" or "Updated every 3 days/每3天更新" — plus the existing as-of.
- Page copy updates (aibrief.html header, tab help text, dialog helpers): stop claiming
  "regenerated each day" for BTC; per-lens truthful copy.

## 8. UI contract (designer lane — doctrine + frontend-design skill both loaded)

ONE shared renderer: NEW `templates/_aibrief_body.html.j2` exposing
`{% macro aibrief_body(brief, lens, labels_ctx) %}` used by ALL FOUR surfaces
(macro dlg-aibrief, china cnx-dlg-aibrief, hk hkx-dlg-aibrief, aibrief.html tabs —
aibrief.html moves to SERVER-rendered bodies; `build_aibrief.py` loads the three brief
JSONs and passes them in; `aibrief.js` slims to the cortex panel only).
`masterbrief.js`: grep its `#master-brief` mount — if no live page mounts it, delete
template+site copies and drop any build copy references; if something mounts it, port
that surface to the shared macro instead.

Layout order (v2 body):
1. Header row (existing aib-hdr pattern) + NEW cadence micro-chip + as-of. The mandatory
   badge text "A read-through of existing signals — not a signal source /
   仅为现有信号的汇总解读 — 非独立信号源" is HOUSE LAW — never delete or alter.
2. **The gist / 要点** — tldr tick-list, large type (≥14.5px), "Head" bold-split on
   first ":" (reuse watch-row splitting idiom). The final "What to do:" item renders as
   a STANCE PILL (accent-tinted container, stance word bold) — this is the signature
   element; spend the boldness here, keep everything else quiet.
3. **Key readings / 关键读数** — the key_facts chip rail. Tone tints via
   color-mix with --up/--down/amber/--info/--muted (match existing chip idioms; light+dark
   theme safe). Chips wrap; 390 px bleed-checked.
4. Confidence meter (existing 3-seg) + as-of (ONE as-of per panel — remove dupes).
5. The full read / 完整解读 — regime_read prose (unchanged type scale).
6. Two-up grid ≥760px: "Where signals disagree/信号分歧" (amber left border) ·
   "Chain reactions/连锁反应" (blue left border) — items bold-split on first ":".
7. "Playbook check/剧本对照" full-width card — ONLY when rotation_check present.
8. "What to watch/关注事项" checklist (existing marker rows, bold-split).
9. Upcoming catalysts (macro only — existing chips; keep).
10. Footer: degraded notice (existing), disclaimer line, link-out (existing per surface).

Rules: dual-span `l-en/l-zh` everywhere; NO translated text in `title=` (CI); no `t()`
inside `<svg><text>`; CSS lives in NEW shared include `templates/_aibrief_css.j2`
(namespace `.aib2-*`; may absorb/alias existing `.aib-*` where identical) included by
china/hk/aibrief templates; dashboard.html.j2 keeps its scoped block but MUST converge to
identical rules (designer's call: either include the shared block unscoped or update the
scoped copy to byte-similar rules — pick ONE and say so in the PR body).
Word budgets are enforced upstream by the prompt; the renderer never truncates with
ellipsis on Tier 1 (wrap, don't clip). Screenshots at 1280 and 390 px, light+dark, EN+ZH
before hand-back (browser-verified against the committed site/*.json payloads — which are
still v1-shaped; every v2 field must fail-open to absent so v1 payloads render cleanly
until the first nightly).

## 9. Back-compat & failure honesty

- v1 payloads (current committed briefs) MUST render correctly in the v2 UI (no tldr →
  glance section absent, falls back to summary lead; no key_facts → no rail; no
  refresh_days → no cadence chip). The first v2 payload appears on the first nightly.
- Degraded brief (`degraded_reason`, no regime_read) renders the existing explicit
  degraded state — unchanged behavior.
- Nothing in this PR may raise into the pipeline: every new engine path wraps in the
  existing degrade-never-raise idioms.
- LLM epistemics: unchanged — the brief never feeds a score/signal/allocation; stance is
  a restatement of deterministic posture keys; key_facts are engine-computed.

## 10. Verification gate (before PR)

1. `pytest tests/test_master_brain.py tests/test_master_brain_producer.py
   tests/test_brief_context.py tests/test_aibrief_page.py tests/test_aibrief_w4_panels.py
   tests/test_master_brain_policy.py` green.
2. Template render smoke over committed JSONs (v1 payloads) — all four surfaces.
3. `python -m scripts.check_template_site_sync --fix` clean.
4. If DEEPSEEK key present: one `persist=False` forced synthesis per lens; eyeball
   style-lint pass + tldr shape. (No data/ or site/ commits from this.)
5. `git status` shows SOURCE-ONLY diff.
