# National Team Radar — build spec & view-model contract

Status: build spec, 2026-07-22. Owner: main session. Consumed by `china_policy_watch`.

## Purpose

Detect Chinese **state market intervention** ("national team" / 国家队 — Central Huijin, China
Reform/Chengtong, CSF, state insurers, PBOC facilities) from the *loud, public footprint* it
leaves, and surface it as one display-tier read on `china_policy_watch.html`.

The premise "we can't see state buying without direct state sources" is false-in-a-useful-way:
intervention is **loud by design** (the point is to restore confidence), so it leaves footprints
in free data we already collect. The killer example is already in our files — on 2026-07-21
`data/china_flows/etf_shares.parquet` shows `sh_510300` (CSI 300 ETF) units +12% and `sh_588000`
(STAR 50 ETF) units +22% in two sessions: net ETF *unit creation* = net buying = the national
team's fingerprint, on exactly the tech/broad ETFs the news said they bought.

## Epistemics (HOUSE LAW — non-negotiable)

- **Display-tier / `is_context_only: True`.** This is context/detection infrastructure. It ships
  **freely** — a null NEVER blocks it, and it needs no gauntlet. (CLAUDE.md epistemics.)
- **Not a scored buy signal.** `may_originate=False, may_escalate=False`. The composite is a
  deterministic *intensity* read, NOT an alpha score, NOT a rank/size/gate input. Never wire it
  into a trade gate. It is a "what is the state doing right now" context gauge.
- **Nulls printed, not hidden.** Every tell that lacks data reads `state:"null"` and is shown in
  the Tier-2 receipt as "no reading" — compliant "nulls printed."
- **Plain-word stance.** Every band answers "so what do I do", even when the honest answer is
  "watch — don't chase." Glance tier: state + plain-word stance; no internal state/study names,
  no untranslated stats, no raw slugs. Technicals demoted to hover/popover.
- **Never the word "validated"** in user-facing text (CI-enforced).
- **LLM may not originate** — the news classifier uses deterministic keyword rules over an
  already-collected tape; it de-noises, it does not originate a signal or escalation.

## Data sources (all verified on disk 2026-07-22)

| Tell input | Path / call | Notes |
|---|---|---|
| ETF unit creation | `data/china_flows/etf_shares.parquet` via `engine.china_participation.etf_participation()` → cross-fund median 5d z (`etf_share_chg`) | 21 ETF cols incl `sh_510300/510050/510500/588000`; ~5wk history (thin, disclosed) |
| Policy impulse | `engine.china_policy_transmission.snapshot()['policy_impulse']` | values: `market_rescue`, `targeted_support`, `easing`, `tightening`, `neutral` |
| Large-cap vs small-cap divergence | `data/china/510050.SS`, `510300.SS` (large) vs `510500.SS`, `159915.SZ` (small), `[close]` cols | compute 5d return spread (large avg − small avg). Positive+large = "pulling the index" |
| State-media drumbeat + facility watch | `data/china_news_vector/events.parquet` cols `title, source, source_tier, theme, seendate, score` | filter `source_tier==1` + `theme in {markets,monetary,policy}` + keyword regex (below) over trailing 7d (drumbeat) / 30d (facility) |
| PBOC posture | `engine.china_pboc_stance.snapshot()` stance + `data/china_pboc/repo_rates.parquet` FR007 z | "easing into stress" = stance easing/neutral AND FR007 z ≤ −1.0 |
| Buyback cascade | NEW ledger `data/china_national_team/buyback_daily.parquet` (append-only), sourced from existing `data/china_buyback/buyback.parquet` | records daily `n_active`, `n_board_proposal` (progress==董事会预案), `plan_amt_yi_sum`; w/w acceleration = cascade. Forward-accruing (thin on day 1, disclosed) |
| Margin recovery | `data/china_margin/balance.parquet` cols `fin_balance, net_fin_buy` | full history 2010→. 5d inflection after a drop = leverage returning |
| Block-trade stress (optional) | `data/china_block_trades/detail.parquet` | discount cluster = distressed supply |

Keyword regex (deterministic, EN+ZH), for `events.parquet.title`:
- **stability drumbeat:** `维护|稳定|平准|国家队|长期投资价值|增持|回购|稳市|信心|resolute|stabiliz|national team`
- **facility watch:** `互换便利|SFISF|再贷款|回购增持|swap facility|relending`

## Tells (8) — each: key, tier, firing rule, weight, receipt

Tier ∈ {leading, coincident, confirming}. `strength` ∈ [0,1] when firing (else 0). Composite
weights renormalize over tells with `have_data=True`.

| key | tier | fires when | strength | weight | receipt (EN) |
|---|---|---|---|---|---|
| `etf_creation` | coincident | cross-fund median 5d z ≥ +1.0 | clamp(z/3, 0, 1) | 0.28 | "CSI 300 units {+x%}, STAR 50 {+y%} ({Nd})" |
| `largecap_divergence` | coincident | 5d (large−small) spread ≥ +1.5pp | clamp(spread/5, 0, 1) | 0.16 | "Index heavyweights +{a}% vs small-caps {b}% (5d)" |
| `market_rescue` | coincident | impulse ∈ {market_rescue, targeted_support} | 1.0 rescue / 0.6 targeted | 0.14 | "Policy impulse: {market rescue / targeted support}" |
| `state_media_drumbeat` | leading | ≥2 tier-1 stability hits in 7d | clamp(hits/6, 0, 1) | 0.14 | "{N} state-media stability signals (7d)" |
| `facility_watch` | leading | ≥1 facility hit in 30d | clamp(hits/3, 0, 1) | 0.10 | "PBOC support facility flagged ({N}, 30d)" |
| `pboc_posture` | leading | stance easing/neutral AND FR007 z ≤ −1.0 | clamp(−z/3, 0, 1) | 0.06 | "PBOC easing into tight liquidity (FR007 z {z})" |
| `buyback_cascade` | confirming | n_board_proposal w/w accel ≥ +20% | clamp(accel, 0, 1) | 0.08 | "SOE buyback proposals accelerating (+{p}% w/w)" |
| `margin_recovery` | confirming | fin_balance 5d inflection up after drop | clamp(slope, 0, 1) | 0.04 | "Margin balance turning up (leverage returning)" |

Composite: `score = round(100 * Σ_available(weight_i · strength_i) / Σ_available(weight_i))`.
Band: `score ≥ 68 → on`, `42–67 → elevated`, `18–41 → quiet`, `< 18 → dormant`.

## Color semantics (TRAP — do NOT use direction tokens)

The gauge is a NON-directional intensity read. Do **not** use `--up/--down` or the
`mx5-score-green/red` direction classes — they FLIP in zh (red=up) and would mislead. Use the
non-flipping semantic tokens:
- `on` → `--act` (#e05555 alert red — heavy state hand, market can't stand alone)
- `elevated` → `--warn` (amber)
- `quiet` → `--ok` (calm green — market trading freely)
- `dormant` → `--muted`

These do not flip between EN/ZH, so the gauge reads correctly in both languages.

## Stance text per band (plain words, EN + ZH)

- **on:** "The state is actively defending the floor. Large-cap index levels are being held, but
  breadth is hollow — small caps and growth are left behind. Watch, don't chase: a defended floor
  is not a bull market, and the real risk is the exit, when the hand withdraws."
- **elevated:** "Intervention tells are building — state media is turning supportive and policy is
  leaning in, but broad buying isn't confirmed yet. Watch for the ETF-creation fingerprint to fire."
- **quiet:** "No active state defense right now. The market is trading on its own two feet."
- **dormant:** "The state hand is off the tape. Policy is neutral-to-tightening; no intervention signals."

(ZH translations to be authored by the builder, following the site bilingual pattern.)

## View-model contract — `china_national_team.v1`

`engine/china_national_team.py::snapshot()` returns this dict; `china_policy_watch.snapshot()`
attaches it as `pw.national_team`.

```python
{
  "schema": "china_national_team.v1",
  "is_context_only": True,
  "asof": "2026-07-22",
  "built": "<utc iso>",
  "pressure": {
    "score": 74,                       # int 0-100, display-tier
    "band": "on",                      # on|elevated|quiet|dormant
    "band_en": "Hand on — active defense", "band_zh": "...",
    "accent": "act",                   # act|warn|ok|muted (maps to --act/--warn/--ok/--muted)
    "arc_frac": 0.74,                  # score/100, for gauge arc dasharray
  },
  "stance": {"en": "...", "zh": "..."},
  "tells": [
    {"key": "etf_creation", "tier": "coincident",
     "label_en": "ETF creation surge", "label_zh": "ETF份额激增",
     "state": "firing",                # firing|quiet|null
     "strength": 0.83, "value_fmt": "+12% / +22%",
     "receipt_en": "CSI 300 units +12%, STAR 50 +22% (2d)", "receipt_zh": "...",
     "have_data": True, "weight": 0.28},
    ...
  ],
  "tell_counts": {"firing": 5, "total": 8, "null": 1},
  "top_footprint": { ...the single highest-strength firing tell, for the glance line... },
  "history": [{"date": "2026-07-18", "score": 41}, ...],   # forward-accruing pressure sparkline
  "gaps": ["etf_flows: ~5wk history (thin)", ...],          # honest data-limitation notes
}
```

## Wiring

- `engine/china_national_team.py` — new. `snapshot(asof=None) -> dict` per contract above.
  Pure reads + one append to the daily ledgers. Deterministic. `is_context_only`.
- `engine/china_policy_watch.py::snapshot()` — attach `pw["national_team"] = china_national_team.snapshot()`
  inside a try/except so a failure degrades to `None` (page still renders; template guards on it).
- Ledgers (append-only, forward-accruing), written inside `snapshot()` or the build drip:
  - `data/china_national_team/buyback_daily.parquet` (date, n_active, n_board_proposal, plan_amt_yi_sum)
  - `data/china_national_team/pressure_daily.parquet` (date, score, band) — feeds `history`
  Use the `collectors/_drip.append_snapshot(path, rows, date_col="date")` idiom (see
  `collectors/china_margin_detail.py`). Nightly asia-close lane is the sole advancer.
- `scripts/build_china_policy_watch.py` — no change needed if snapshot attaches it; else pass through.

## Tests (`tests/test_china_national_team.py`)

1. `snapshot()` returns the v1 schema with all contract keys; `is_context_only is True`.
2. Score is in [0,100]; band matches the threshold table.
3. On a synthetic ETF-surge fixture, `etf_creation` fires and score rises (fail-then-pass power).
4. Null handling: with a tell's source absent, that tell reads `state:"null"`, `have_data:False`,
   and is excluded from the renormalized composite (no crash, no NaN).
5. Accent maps to a non-flipping token (never `up`/`down`).
6. No user-facing string contains "validated".
7. Ledgers append idempotently (same-day rerun does not duplicate a row).
