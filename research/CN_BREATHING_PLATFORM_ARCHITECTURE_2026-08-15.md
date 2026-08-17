# CN Breathing Platform — architecture ruling (CN-W-L3, 2026-08-15)

Program: `research/BREATHING_PLATFORM_MASTERPLAN_BY_FABLE.md` §4 W-L3 (operator-ratified
2026-08-08), expanded by the 2026-08-15 chairman directive (mainland same-day/intraday
revival). Sister program: Breathing Platform Production Revival US (concurrent session).
This doc is the build spec: every CN-PR builder is pinned to it.

Census inputs (2026-08-15, four independent sweeps): US prophet-live core, CN engine
chain, live plane, sentinel/rescue + CN-LIMIT-ALPHA boundaries. Key citations inline.

---

## §0 ACCEPTANCE GATES (program, "not done unless")

1. **Intraday**: during mainland trading (09:30–11:30, 13:00–15:00 CST) the CN
   provisional per-name Prophet state updates ≤5 min from lawful quotes; lunch
   (11:30–13:00 CST) shows an explicit `session_break`, never "stale".
2. **Close**: a provisional mainland close board is user-visible within ~5 min of the
   15:00 CST close being lawfully observable; hard SLO ≈15:15 CST under normal upstream
   conditions, measured by `first_close_board_at` in the CN liveness record — never by
   a workflow conclusion.
3. **Decoupling**: no user-visible CN artifact waits on HK auction/vendor settlement
   (the 08:25 UTC floor) or on the asia-close batch. asia-close remains settlement +
   sole `data/` ledger writer.
4. **Honesty**: a name with no lawful current observation shows `unavailable` (never
   yesterday's price); limit-locked and suspended are distinct states; coverage is
   published; yesterday's board never masquerades as today's (session stamps + client
   feed-floor).
5. **Reliability**: content-level CN liveness record (§7) + phase-aware sentinel
   surface + bounded rescue classifier; process-green ≠ product-healthy anywhere.
6. **Acceptance**: replay battery (18 chaos cases, §9) green; browser proof with the
   static board frozen at N−1 while runtime shows N (desktop/mobile 390px/EN/ZH);
   then ≥3 consecutive live mainland sessions meeting the operational contract.
7. **Isolation**: zero imports from CN-LIMIT-ALPHA research (`research/cn_prophet_audit/`,
   washout program, China-Intelligence composites). Displayed score authority traces to
   `engine/china_board_rank.py` v3 + `engine/signal_gate.py` only. No new scoring
   authority is granted by this program.

---

## §1 Before → after

**Before:** one lane. `asia-close.yml` holds to an 08:25 UTC floor (HK auction ~08:10,
mainland vendor EOD ~08:00–08:30), then runs collect (41–45m) + build_china (23–26m) +
bands (~9m) + publish — measured 76–88m total, start 08:25 (asia.jsonl 08-10..08-14).
Today's mainland board lands ~09:45–09:55 UTC ≈ **17:45–17:55 CST**, ~3h after the
15:00 close; between opens, nothing per-name moves (only the 11-symbol index-level
`china_risk_state` hero gauge is live). GH cron fire lag measured +86..+233 min.

**After:** three clocks, one engine.

```
ARM (asia-close, canonical, unchanged clock)
  build_cn_live_pack: probes per-name trigger/fade edges from settled adjusted closes
  → R2 live_flow/cn_prophet_live_armed.json           (next session's contract)

BREATHE (VPS systemd, mainland session, 5-min)
  cn_live_evaluator: armed pack + lawful delayed quotes → per-name provisional states
  → R2 live_flow/cn_prophet_live.json + served live/cn_prophet_live.json (gated)
  → event spool live_flow/cn_prophet_live_events/<session>/*.json (append-only)

CLOSE (same VPS service, post-close phase 07:00–07:15 UTC)
  close-observability detection → provisional close board (armed set at observed closes)
  → close_board section on the same artifact; SLO stamp first_close_board_at

SETTLE (asia-close, hours later)
  canonical rebuild + china_standout_track ledgers (single writer, unchanged)
  + reconcile_cn_live --asia: grades the event spool → data/cn_prophet_live/forward.parquet
  + cn_board_confirmation receipt: provisional close board vs canonical board
```

The client (`china_stocks.html`) polls the served artifact, fills the already-reserved
`.pv-live` chip slot per card, renders the provisional close-board stamp, and falls
closed to the SSR-baked nightly board on any refusal — the `feedIsCurrent()` /
`_bsQualify` doctrine ported from `china_risk_state_live.js` + `dashboard.html.j2`.

---

## §2 CN session-state contract (first-class, tested)

Module: `engine/prophet_live/cn_clock.py` (new; stdlib + `lib.cn_calendar`).
All boundaries in Asia/Shanghai (no DST); UTC equivalents fixed year-round.

| phase | CST | UTC | evaluator behavior |
|---|---|---|---|
| `holiday` / `weekend` | — | — | no passes; sentinel expects nothing |
| `pre_open` | 09:10–09:30 | 01:10–01:30 | one warmup pass allowed; states carry over from prior session close, marked `pre_open` |
| `opening_auction` | 09:15–09:25 | 01:15–01:25 | no state transitions off auction indications; folded into `pre_open` handling |
| `morning` | 09:30–11:30 | 01:30–03:30 | full evaluation, transitions armed |
| `session_break` | 11:30–13:00 | 03:30–05:00 | passes may run but states FREEZE (no transitions, no fades); artifact stamps `market_phase: session_break`; quote-age ceiling anchored to 11:30, not wall clock |
| `afternoon` | 13:00–14:57 | 05:00–06:57 | full evaluation |
| `closing_auction` | 14:57–15:00 | 06:57–07:00 | evaluation continues; no new transitions confirmed in the auction window (debounce carries) |
| `post_close` | 15:00–15:15 | 07:00–07:15 | close-observability detection + close board pass(es); then stand down |
| `closed` | 15:15–next 09:10 | — | no passes |

Quote-age law: the staleness ceiling (delay floor 15m + slack) is measured against
`expected_latest_quote_time(now)` = `min(now, current-or-last segment end)` — at 13:02
CST a quote stamped 11:29 is FRESH (age vs 11:30 anchor), at 14:30 a quote stamped
10:15 is STALE. This is the CN-specific correctness detail the US single-window model
cannot express; `tests` must pin lunch-boundary cases both sides.

Per-name `market_status` (presentation + gating overlay, orthogonal to the state
machine's public states): `trading | session_break | limit_up_locked |
limit_down_locked | unavailable | suspended_suspected`. Limit-lock detection:
`|price − prev_close·(1+limit)| ≤ max(0.01, prev_close·0.0005)` with the per-class
limit below. A limit-locked price is a REAL price — the state machine still evaluates
it; the overlay names the regime (one-price session ≠ missing).

Per-class daily limit (ticker-derived, mainland only):
`688*.SS` (STAR) ±20% · `300*.SZ` (ChiNext) ±20% · other `.SS/.SZ` main-board ±10%
(ST names are already excluded by `_tradability_ok`; `.BJ` not in universe). These
also size the pack's probe span (§4) — probing beyond the daily limit band wastes
budget on unreachable prices.

---

## §3 Price plane ruling (measured, not assumed)

**Primary: Yahoo spark via `engine.live_quotes.fetch_quotes()`** — the same routed
path every non-US symbol already takes (batched 20/req, keyless). Grounds:
- Already in production during CN hours: the display lane polls ~133 A-share
  `data-sym`s off `china_stocks.html` every ~60s all day; `china_risk_state` has run
  on it in the 01:00–09:00 UTC window for months (health-enforced ≤6 min age).
- Carries the §5-required fields per quote today: `price, quote_ts, source,
  price_basis (trade|minute|day|prev|regular), delay_min, prev_close, currency,
  day_volume, day_high, day_low` (`engine/live_quotes.py` parse_yahoo_spark).
- Honest delay floor: `config.yml live.delayed_min: 15` — stamped, never hidden. The
  freshness ceiling derives from it (15 + slack), per the US W-L0 lesson.
- No entitlement, no token, no CN-LIMIT-ALPHA contact. TuShare is DARK (07-27) and
  gates nothing here by construction.

Alternatives rejected for the primary: TuShare realtime (token dark; authority
decision pending elsewhere); eastmoney push2 (token-gated legs, scrape fragility,
no basis fields); a new vendor (violates "smallest lawful plane"; nothing measured
demands it). CN-PR-1 ships a measurement receipt (coverage/missing-rate/latency over
the armed universe across ≥1 replayed + ≥1 live session) rather than prose — if spark
under-measures, the seam (`fetch_quotes`) is already the router where a second source
would slot.

**Acquisition order (evaluator):** (1) VPS local plane freshest-wins merge
(`state/quotes_full.json` + `live/quotes.json`) — free, already ticking; (2) direct
`fetch_quotes()` for armed names the plane lacks or serves stale — bounded ≤⌈180/20⌉=9
batches/pass. Coverage counters (`universe_n/observable_n/coverage_pct`) publish every
pass; a name with no lawful quote is `unavailable`, never carried at yesterday's price.

**Basis seam (ONE PRICE BASIS, W-L0 gate 3 inherited):** pack side =
`data/china_stocks` (yfinance `auto_adjust=True`, split+dividend adjusted;
`overwrite_overlap=True` re-owns the refresh window — collectors/china_stock_prices.py);
feed side = raw vendor prints. `engine/prophet_live/interval.py`'s vocabulary and
`basis_audit` transfer unchanged: pack stamps `price_adjustment:
split_and_dividend_adjusted` per name (new CN helper mirroring
`build_stock_library.universe_price_adjustment()` — the CN library has none today);
evaluator compares pack `as_of_close` vs feed `prev_close` per name with the 0.25%
tolerance; mismatch (corporate action overnight, bad splice, wrong listing) → that
name goes `dark` with `basis_mismatch`, never silently mixed. `data/china_stocks_raw`
(auto_adjust=False) is NOT read by this lane — raw-plane limit analytics stay where
they live.

Parity battery (CN-PR-1 tests, §5 of the commission): normal name · recent
split/dividend name (mismatch → refuse) · suspended (no quote → unavailable) ·
limit-up locked · limit-down locked · missing bar · reopen-after-suspension ·
thin/late observation (age > ceiling → dark) · lunch-boundary ages.

---

## §4 CN armed pack (arm at settlement, evaluate next session)

Builder: `engine/prophet_live/cn_pack.py` + driver `scripts/build_cn_live_pack.py`,
running as a new step in `asia-close.yml` AFTER the library rebuild (store is fresh),
`timeout-minutes: 12`, `continue-on-error: true` (advisory lane — its failure never
reds settlement; its absence is what the evaluator's `stale_pack` honesty catches).

- Universe: `scripts.build_china_library.universe()` rows minus Sector ETF/Index,
  through `_tradability_ok` (ST fail-closed, cap floor, ADV floor, staleness) — the
  same pool the nightly board scores. Probe priority: tonight's board lanes
  (featured → more_actionable → forming) then T1/T2/T3-adjacent cross candidates,
  under the same `max_probe`/`max_seconds` budget discipline as the US pack
  (`meta.skipped` names what the budget cut — never silently relabeled dormant).
- Gate calls: `engine.signal_gate.gate(ticker, close, event_latch=EventLatch("CN").load())`
  — the T2 latch is MANDATORY pack-side (repaint class: trailing-bucket un-fires,
  the measured 300363.SZ incident). The evaluator never calls gate() live; it reads
  armed edges, so latch discipline lives entirely in the arm.
- Probe semantics: APPEND next-session bar (the W-L0 #4982 fix, inherited unchanged);
  next-session stamp resolved via `lib.cn_calendar` (additive `calendar` threading in
  `armed_pack.py` helpers — default stays NYSE so the US lane is byte-unchanged).
- Probe span: per-class limit band from §2 (±10/±20) instead of the US 15% — exact,
  not tighter and not wider than what tomorrow's tape can lawfully print.
- Frozen cross-sectional context rides the pack per name (display + close board, zero
  recompute): `prophet_score`, `prophet_rank`, lane, and the frozen legs
  (`rev_z`-bearing profile bits, reversal_member, theme_timing, relay, liquidity,
  microstructure flags) — projected, not recomputed. The pack self-describes which
  legs are frozen-as-of vs live-derived, and the surface discloses it (the US
  close-pass 40/100 disclosure idiom).
- Self-check: `verify_edges` fail-closed parity (G0.1 inherited) — a mismatching name
  is withheld, never published wrong.
- Keys: R2 `live_flow/cn_prophet_live_armed.json` (+ `--out` local copy for the
  reconciler). Schema `cn_prophet_live.armed/v1`.

Pack staleness law: evaluator requires `pack.as_of == cn_calendar.last completed
session`; else the artifact ships `dark_artifact(stale_pack)` with `prev_states`
carried (debounce preserved) — settlement failure degrades the NEXT session honestly
instead of evaluating against N−2 thresholds. (asia-close's own gate retries
same-day; §8's classifier names the stage.)

---

## §5 Evaluator + close pass (host-native; GH cron is disqualified for cadence)

`scripts/cn_live_evaluator.py` (driver) + `engine/prophet_live/cn_states.py` (pure
state logic reusing `live_states.py`'s debounce/hysteresis/SINCE-clock machinery with
the §2 clock; public states unchanged: `dormant near forming faded at_risk unknown
dark` + per-name `market_status` overlay).

Scheduling: **own systemd pair** `app/deploy/macro-live-cnprophet.{service,timer}` —
`OnCalendar=Mon..Fri *-*-* 01..07:03/5:00 UTC`, script self-gates by §2 phase (a
holiday pass exits in <1s). Lowest resource tier (CPUQuota=60%, MemoryMax=512M,
Nice=10 — the US evaluator's measured envelope ~0.5 CPU-s/95MB fits 2-vCPU VPS).
Ships IN THE SAME PR as: the `update.sh` self-arming regex block (the live-breadth
lesson: a runbook without a unit is a dark lane), the `check_vps_live_health.py`
phase-aware clause (fresh ≤6 min during morning/afternoon; ≤20 min through lunch;
close_board present by 07:20 UTC on sessions), and the GH backstop workflow
`cn-prophet-live.yml` (ubuntu-latest, coarse cadence, self-disabling on
`vars.VPS_LIVE_PRIMARY == 'true'` — the prophet-live.yml idiom; rescue/backstop only,
never the product clock).

Pass shape: load pack (R2, prev artifact for debounce) → quotes (§3 order) → per-name
basis audit → §2 phase + quote-age law → state machine → publish R2 whole-artifact +
served copy (atomic tmp+`os.replace`, the estate idiom) → event spool append on
transitions only. No `data/` writes, no git (G0.2). `CN_PROPHET_LIVE_NO_PUBLISH=1`
kill switch, separate from the US one.

**Close pass (same service, `post_close` phase):** close-observability detection per
name = quote with `quote_ts ≥ 07:00 UTC` and basis ∈ {regular, day} (the vendor's
settled regular-market print), OR price stable across two passes post-07:00. First
pass where the armed set clears a coverage floor (≥80% of armed names close-observed)
→ compute provisional close states at observed closes, assemble `close_board`:
ordered membership = frozen nightly lanes re-stated at close states + any armed cross
name whose confirmed state is forming/confirmed at close, each row carrying frozen
score legs + live state + `revision: close_provisional`. Publish + stamp
`first_close_board_at`. Below the floor by 07:15 → publish what is observable with
`close_coverage_pct` + `close_pending: true` and KEEP intraday semantics — never
manufacture a close (§18). Later passes (to 07:15) revise upward; asia-close later
supersedes with `canonical` via §8's receipt. HK is nowhere in this path.

---

## §6 Runtime artifact contract — `live/cn_prophet_live.json`

Schema `cn_prophet_live.states/v1`. Top level: `schema, session (CN date), built_at,
market_phase, pack_as_of, revision (intraday_provisional | close_provisional),
close_pending, quote_source, delay_floor_min, coverage {universe_n, armed_n,
observable_n, coverage_pct}, repaint_disclosure {t2_repaint_pct: 15.1}, names {…},
close_board {…|null}, liveness {…}, prev_states (on dark), dark {reason}|null`.

Per name: `state, since_ts, market_status, price, quote_ts, quote_age_sec,
price_basis, prev_close_feed, as_of_close_pack, trigger_px|fade_px, band_lo_px,
band_hi_px, frozen {score, rank, lane}, dark_reason|null`.

`liveness` (§12 of the commission, written every pass): `expected_session,
market_phase, source, source_asof, quote_age_sec_p50, universe_n, observable_n,
candidate_n, coverage_pct, evaluation_started_at, artifact_written_at,
close_observed_at, first_close_board_at, provisional_revision, canonical_revision,
confirmation_status, failure_stage, failure_reason`. (`runtime_visible_at` /
`browser_visible_at` are measured by the sentinel reader + browser acceptance, not
self-reported — the #5222 lesson: never let the producer grade its own visibility.)

Gating: served under `/live/` ⇒ registration+paywall by default (absent from
`@vps_public_live` and `@reg_asset` allowlists — no Caddy change). Anonymous readers
keep the static board; the page shell stays open.

---

## §7 Delivery — runtime board on the China stock page (no rebuild)

`templates/china.html.j2` `mode == 'stocks'` block gains a CN live module (new
`templates/cn_prophet_live.js` or inline block, mirroring `china_risk_state_live.js`
discipline):

1. Poll `live/cn_prophet_live.json` every 120s (visibility-aware; no-cache).
2. Feed floor: refuse to patch if feed `session` < page-rendered session
   (`feedIsCurrent()` port) — yesterday's feed can never overwrite today's render,
   and today's feed upgrades yesterday's static page.
3. Per-card `.pv-live` chip fill (slot already reserved in `_prophet_card.html.j2`):
   state word + since + market_status, bilingual (`盘中暂歇` session_break ·
   `一字涨停` limit_up_locked · `停牌` suspended · `暂无行情` unavailable), 红涨绿跌
   convention respected via existing ink tokens.
4. Board-level strip: session + phase + as-of + coverage + provisional wording
   (windows-not-certainties house copy; repaint disclosure in the tooltip), and the
   close-board banner once `revision == close_provisional` (later `confirmed` via §8
   receipt on the next nightly render).
5. Fail-closed: any refusal (schema, session, age > 15 min×3, gated 401) leaves the
   SSR board untouched; a previously-painted live layer tears down to SSR cleanly.
6. No client-side scoring/ranking — ordered membership and states come from the
   payload only.

Static `china_stocks.html` remains the durable confirmed fallback; nothing here
requires a site render to change a state.

---

## §8 Settlement, reconciliation, rescue

- **Reconciler** `scripts/reconcile_cn_live.py --asia` (asia-close step, after
  arming): joins the session's event spool → `data/cn_prophet_live/forward.parquet`
  (keep-first, session-vintage confirmed verdicts, basis-anchored fills — the
  reconcile_prophet_live idiom with cn_calendar). Sole writer of that path; lane-gated
  on `CN_LANE=asia`. This parquet + the append-only spool IS the §10 research-safe
  PIT substrate: first-seen stamps, no backdating, no intraday ledger advance.
- **Confirmation receipt**: `engine/close_pass/reconcile.confirmation_receipt` idiom,
  CN sibling — compare `close_board` tickers vs canonical `china_standouts.json`
  lanes in the SAME asia run that renders (in-process, the #5220 structural lesson),
  publish `live_flow/cn_board_confirmation.json` + rendered stamp:
  confirmed/adjusted/dropped (+`added` beside), causes named.
- **Sentinel surface** (`freshness_sentinel.SURFACES` entry, CN-PR-4): kind
  `live_file` on `/live/cn_prophet_live.json`, `absent_ok` until first ship;
  phase-aware budget via new `lib.cn_calendar.sessions_behind()` + Asia/Shanghai SLA
  clock (`by_cst`) checking `first_close_board_at ≤ 15:20 CST` on sessions; lunch and
  holidays expect quiet (no false outage). Alert transport reused verbatim.
- **Rescue classifier** `scripts/cn_live_rescue.py --classify` (CN-PR-4): bounded,
  read-only diagnosis mapping a miss to its stage — `pack_missing (arm step) |
  evaluator_dead (no artifact tick) | quotes_stale (artifact ticking, quote_age flat)
  | publish_failed (R2 fresh, served stale or vice versa) | route_broken (served
  fresh, reader 4xx/5xx) | client_stale (route fresh, page shows N−1 — browser
  acceptance instrument) | settlement_late (asia-close no success by 12:00 UTC)`.
  Each stage names its lever; alert-only in v1 (asia-close's own gate already
  self-retries; the §0.4 no-blind-dispatch invariants inherited). vps-live-heartbeat
  (10-min GH dead-man) covers the evaluator process via the health clause.

---

## §9 Acceptance instruments

- **Replay battery** (CN-PR-1/2 tests): the commission §14 matrix — ordinary day ·
  lunch · holiday · suspended · limit-up · limit-down · partial close coverage ·
  missing ticker · source timeout · stale-but-alive source · kill-during-write
  (atomicity) · duplicate pass (idempotent) · reboot recovery (timer+state) · static
  frozen N−1 vs runtime N · route broken · runtime-vs-canonical divergence ·
  settlement never arrives · settlement hours late. Honesty guards mutation-tested
  (flip the guard, assert red).
- **Browser acceptance** (CN-PR-3): freeze `site/china_stocks.html` at N−1, serve a
  synthetic session-N artifact locally, prove chips + close banner + stamps on
  desktop/390px/EN/ZH with zero horizontal overflow and zero stale/provisional
  contradictions; committed crops.
- **Live acceptance** (accrues from next mainland session, 3 consecutive):
  open/lunch/close/settlement receipts per §16 of the commission, filed in the
  program handoff.

---

## §10 PR map (collision-audited)

| PR | Contents | Files (new unless noted) |
|---|---|---|
| **CN-PR-1** engine+service | cn_clock, cn_pack, cn_states, evaluator+close pass, basis helper, replay battery, systemd pair, update.sh block (edit), health clause (edit), GH backstop workflow, `armed_pack.py` calendar param (small edit), `cn_calendar.sessions_behind` (small edit) | `engine/prophet_live/cn_{clock,pack,states}.py`, `scripts/{build_cn_live_pack,cn_live_evaluator}.py`, `app/deploy/macro-live-cnprophet.*`, `.github/workflows/cn-prophet-live.yml`, tests |
| **CN-PR-2** settlement wiring | asia-close arming + reconciler + confirmation receipt steps; `reconcile_cn_live.py`; receipt module | `.github/workflows/asia-close.yml` (edit), `scripts/reconcile_cn_live.py`, `engine/prophet_live/cn_reconcile.py`, tests |
| **CN-PR-3** runtime board | client module + template wiring + bilingual copy + crops | `templates/china.html.j2` (edit), `templates/cn_prophet_live.js`, tests + crops |
| **CN-PR-4** watchdog | sentinel surface + rescue classifier + latency receipts | `scripts/freshness_sentinel.py` (edit, additive), `scripts/cn_live_rescue.py`, tests |
| docs | this ruling + continuation handoff + memory | `research/*` |

Serialized merges off fresh main (stacked PRs get zero CI). Shared-file collision
watch: `freshness_sentinel.py` (commercial-alerts program active), US sister session
(prophet_live core, update.sh, vps health) — diffs additive, rebase before push.
In-flight CN research PRs #5730/#5729 own `agentos` CN-LIMIT-ALPHA records + 5
collectors — untouched here.

## §11 Non-negotiables (inherited verbatim from the commission §18)

No duplicate CN engine · no second price control plane · no raw/adjusted mixing · no
yesterday-price fills · no manufactured close · no HK dependency · no GH-cron product
clock · no intraday forward-ledger writes · no CN-LIMIT-ALPHA imports · no full-site
render on a state change · no weakened identity/freshness guards · no weekend-replay
"live" acceptance · no workflow-green = product-healthy · no new scoring authority.
