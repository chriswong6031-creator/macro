# Intraday Flow Tracker v2 — upgrade ruling (spec of record)

Status: DESIGN RULING (2026-07-12). Display-tier build — ships freely per house epistemics
(gauntlet = promotion gate, not build gate). Amends `INTRADAY_FLOW_TRACKER_DESIGN.md` (the v1
spec of record, still binding for the 7-leg confluence and the three-cadence architecture).

Trigger: operator ask — "full upgrade of intraday_flow.html to be much stronger, higher
visibility and signal levels; assess the Terminal options suite and bring that engine use here;
make intraday data actionable and derive/rank signals; institutional-level intraday flow tracker."

Grounded in a 5-lane census (2026-07-12) of the GEX production path (`build_gex_board.py` →
`site/gex/<T>.json`), the options_entry state table (`data/options_entry/state.parquet`), the
live R2 flow schema (`engine/live_flow.py`), the current builder/Terminal idioms, and the binding
constraint ledger (`DO_NOT_REBUILD.md`, `DESIGN_DOCTRINE.md`, `OPTIONS_SENSOR_CONTRACT.md`).

## 1. What the census found (the three gaps this upgrade closes)

1. **The dealer-gamma intelligence never reaches the board.** `site/gex/<T>.json` (nightly,
   committed, all 116 leaders covered) carries the full dealer surface — `net_gex_bn`,
   `gamma_flip`/`dist_to_flip_pct`, `call_wall`/`put_wall` with strength bands + `*_hard` +
   `*_dist_sigma`, `magnet_up`/`magnet_down`, `max_pain`, `expected_move.{daily_pct,weekly_pct}`,
   `vol_hole.{state,bias,upper,lower,compression,pos}`, `skew.tone` (fear/balanced/greed),
   `iv_rank.{band,rank_pct,low_confidence}`, `tilt.read`, `opex_days`, `tier`. The nightly builder
   currently folds only `{gamma_regime, dist_to_flip_pct, walls:null}` into `base.json`, and the
   page renders only a single `GEX:regime` chip. **State.parquet is NOT the source** — its `walls`
   column reads null through the builder and its `iv_rank_252` is structurally null (0/403 until
   the W-E0 backfill). The gex JSON is the source of record for the dealer layer.
2. **The live options-flow read is broken.** The page fetches `live_flow/tide_current.json` and
   reads `tide.tickers[root].cum_ncp / flow_dur / vel_arrow` — but `tide_current.json` has **no
   `.tickers` object** (its per-root data is `top_net_impact[]`; per-root minute series live in
   `live_flow/tickers/{ROOT}.json`; badges/session_tier live in `enrich_current.json` keyed by
   event id). Result: `~NCP` is ~always "—" during RTH and leg L5 never fires. Real bug.
3. **The page violates the user-first doctrine.** `intraday_flow` is a named Tier-1 surface, yet
   the glance tier is raw jargon ("K/7", "RVOL", "vs VWAP", "~NCP") with **no plain-word stance**.
   The doctrine's stance vocabulary is exactly the "make it actionable" upgrade the operator wants.

## 2. Product v2 — a stance-first intraday desk

Same page (`site/intraday_flow.html`, rendered from `templates/intraday_flow.html.j2`; `.j2` is in
`_SKIP_SUFFIXES` so there is **no** byte-paired plain-copy site file to sync). Restructured:

- **"What's set up now" strip** (new glance tier): live counts per stance lane, click-to-filter —
  🟢 Buy now · 🔵 Almost ready · 🏃 In favour · 🟠 Take profits · 👀 Watch · ⚪ Stand aside.
- **Leaders table v2, stance-first columns:** Name · **Stance** (plain-word lane pill, primary) ·
  Price/day · Volume (plain "2.3× normal, holding") · Tape vs VWAP · Options flow (~soft lean +
  badges, from the FIXED fetch) · **Dealer map** (the ported GEX layer, compact) · Levels ·
  Signals (K/7 + legs, demoted to a Tier-2 expandable row).
- **Row expand = Tier-2 depth** (full precision, no jargon budget): exact RVOL×, VWAP $, vol
  durability %, higher-lows, the seven legs with plain names + technical hover, the full ported
  dealer-gamma panel (net GEX, flip, walls+bands+hardness, IV rank, skew tone, expected move,
  long/short-gamma posture sentence, OPEX-pin caution), IV-spread lean, `net_doi` as inert
  context, `evidence_quality` receipt, reference levels + ATR%.
- **Default sort:** `RVOL_tod desc` (ratified single-measured-quantity precedent). Optional
  "group by stance" view (categorical partition + measured sort within — the doctrine lane model,
  NOT a weighted composite). All columns user-sortable.
- **Playbook accordion:** retained, extended to explain the stances + dealer map in plain words.

Word budgets (hard): title ≤4 words, subtitle ≤14, one row line, one as-of, one merged footnote.
Every technical (K/N, RVOL, VWAP, gamma, %, σ, z) gets plain-word Tier-1 + precise Tier-2 hover via
`data-tip-en/zh` (never `title=` with CJK / `t()` / `_zh` — `check_title_i18n`).

## 3. Stance derivation — deterministic, boolean, NO weights (composite-law compliant)

A pure function maps `(legs L1..L7, K, live quote/flow state, dealer context, personality)` → one
stance lane. Every rule is a boolean combination of existing booleans/thresholds — there is **no
weighted score, no fused composite, no positioning fusion** (Signal Commons R3 / mtf_upturn
precedent). Implemented once in `engine/intraday_flow.py::stance()` (tested, used by the nightly
ledger) and mirrored verbatim in the page JS (as `confluence_legs` already is).

Legs (unchanged, v1 §2.5): L1 washout_recent · L2 reclaim(px>VWAP & px>prevClose) · L3
rvol_elevated(≥1.30×) · L4 vol_durable(≥0.60) · L5 flow_bid(~soft: cum_ncp>0 & flow_dur≥0.60) ·
L6 upturn_organ(mtf_upturn∈{WATCH,CONFIRMED}) · L7 leader_quality(not failed_breakout_trap).

Derived helpers used by stance (all deterministic, from dealer context):
- `extended_up` = `vwap_delta_pct >= 1.5 × expected_move_daily_pct` (spot stretched vs today's
  IV-implied 1σ) OR (`call_wall_hard` AND `call_wall_dist_sigma <= 0.5` AND price above VWAP).
- `pin_watch` = `opex_days <= 5` AND single-name `gamma_regime == 'long'` AND
  `min(wall dist, magnet dist) <= ~1%` (dealer-pin zone; carries the `structurally_constant`
  caveat — display context only, never a leg).
- `into_ceiling` = `call_wall_hard` AND `call_wall_dist_sigma <= 0.5` (a hard ceiling is close).

Precedence (first match wins):

1. **🟠 Take profits / protect** — an up-move is stretched into resistance: price above VWAP AND
   (`extended_up` OR `pin_watch`). Stance copy: "Take profits — stretched into the call wall / pin;
   expect mean-reversion, don't chase." (Risk-off is evaluated first so a full setup that has
   already run into the wall is not mislabeled "Buy now".)
2. **🟢 Buy now (act)** — full continuation setup, not into a ceiling: L1 ∧ L2 ∧ L4 ∧ L7 ∧ (L3 ∨ L5)
   ∧ NOT `into_ceiling`. Copy: "Buy now — washout reclaimed on durable volume; structure supports
   continuation. Stop below the base."
3. **🔵 Almost ready (get_ready)** — base in place, trigger not yet fired: L1 ∧ (L6 ∨ squeeze
   coiled) ∧ L7 ∧ NOT L2. Copy: "Almost ready — washout base built; waiting for a reclaim above
   VWAP on volume."
4. **🏃 In favour** — trending and holding, but no fresh washout (ride, don't initiate): L2 ∧ L6 ∧
   (L3 ∨ L4) ∧ L7 ∧ NOT L1. Copy: "In favour — trending above VWAP; ride it, no fresh entry here."
5. **👀 Watch — don't chase** — active without structure, or trap-prone: (L3 ∨ price up on the day)
   AND (NOT L1 OR L7 == false). Copy: "Watch — don't chase — moving without a washout base (or
   trap-prone); wait for structure."
6. **⚪ Stand aside** — quiet, no setup (default). Copy: "Stand aside — quiet tape, no setup."

Off-hours / null tape (live quote or flow absent): compute the nightly-known skeleton only —
L1∧(L6∨squeeze) ⇒ 🔵 "Base in place — waiting for the open"; else ⚪ "Stand aside". Plain-word null
disclosure ("Live tape not flowing yet") + Tier-2 receipt (as-of, evidence_quality). This IS the
compliant "nulls printed" form.

Stance is a **categorical label**, never a number. Grouping by stance is a partition; ranking stays
by a single measured quantity (RVOL_tod) or by K. No stance is ever summed or weighted.

## 4. base.json enrichment (nightly builder)

`build_intraday_flow.py`: replace the three-field `options_entry` with a superset that keeps the
old keys (back-compat) and adds a `dealer` sub-object read from `site/gex/<T>.json` (present both
nightly and for the committed fixture — a pure site→site join, fail-soft to `dealer:null`):

```
options_entry: {
  gamma_regime, dist_to_flip_pct, walls,              # v1 keys (unchanged)
  dealer: {                                            # NEW — from site/gex/<T>.json summary
    regime, structurally_constant,                     # display context + caveat flag
    net_gex_bn, gamma_flip, dist_to_flip_pct,
    call_wall, put_wall, call_wall_band, call_wall_hard, call_wall_dist_sigma,
    put_wall_band, magnet_up, magnet_down, max_pain,
    expected_move_daily_pct, expected_move_weekly_pct,
    vol_hole_state, vol_hole_bias, vol_hole_upper, vol_hole_lower, vol_hole_compression,
    skew_tone, skew_rr25, iv30, iv_rank_band, iv_rank_pct, iv_rank_low_confidence,
    opex_days, tier, top_oi_share, tilt_read
  },
  # supplementary context from state.parquet (display-only, inert):
  ivspread_rel, ivspread_lean,    # lean label per options_ivspread band language
  net_doi,                        # inert context chip, NO directional claim, NEVER a leg
  evidence_quality
}
```

Fastpath (`--mode fastpath`) cheap adds to `flow_pulse.json` per ticker (no new data pulls):
`rvol_tod`, `session_high`, `session_low`, `bars_above_vwap`. Zero `data/` writes (HOUSE-U5).

Nightly ledger (`data/intraday_flow/ledger.parquet`): add a `stance` column (EOD stance from the
engine `stance()` over the settled legs). A9 single-writer, nightly-only, display-tier.

## 5. Compliance (binding — every item verified before PR)

- **Composite-law:** stance = deterministic boolean rules; no weighted/fused score; sort by
  RVOL_tod or K only; MomoEdge weighted rank NOT reused; `dt_contra`/DannyTrades excluded (DT-R11b).
- **gamma_regime / dealer layer = DISPLAY-ONLY** with the `structurally_constant` (regime_passport)
  caveat surfaced; never a K leg or a sort key.
- **Direction ~soft** everywhere (RUL-F3.12; `production_ready=false`, no flip path exists) +
  signing-honesty footnote; magnitude leads; multi-leg discounts direction.
- **Kills respected:** no DOI/net_doi/skew-decel/charm **leg**; `net_doi` survives only as an inert
  context chip with no directional claim; no sector washout; no W-F options fusion.
- **Debrand / 0DTE bucket-only / no "money routing" framing (TOP3-O2 → "tape activity & options-flow
  persistence") / the word "validated" never appears** (`check_validated_claims`).
- **User-first:** plain stance vocab, word budgets, technicals→Tier-2 hover, plain-word null
  disclosure + Tier-2 receipt.
- **CI:** `check_title_i18n` (no CJK/`t()`/`_zh` in `title=` — use `data-tip-en/zh`), bilingual
  EN/ZH pairs, nav checks; `inline-js` checks `site/*.html` only so the rendered page is
  hand-verified in a real browser with prod-shaped fixtures (UI quality law).
- **CONST-ART1** every metric/leg/stance is a deterministic rule, zero LLM. **CONST-ART2** the board
  annotates only; reorders no authority surface.

## 6. Sequencing

Single PR (same-day squash-merge): engine `dealer_context()`+`stance()`+tests · builder gex
enrichment + fastpath adds + ledger stance column · template/JS v2 (stance strip, dealer map, fixed
flow fetch, Tier-2 depth, doctrine compliance) · this ruling. Browser-verified with the enriched
base.json + real flow_pulse.json + synthetic RTH flow fixtures before push. Come-back: first live
read next RTH; promotion prereg no earlier than 2026-10 (unchanged from v1 §7).
