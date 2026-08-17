# AD-1 Implementation Handoff — Daily EOD Options Intelligence Brief
## Advanced Data: Options EOD + Off-Exchange Intelligence OS · 2026-08-17

**Wave:** AD-1 (first implementation slice; authorized only after Chairman review of AD-0)
**Evidence base:** `research/ADVANCED_DATA_OPTIONS_EOD_AD0_CURRENT_STATE_AND_CAPABILITY_LEDGER_2026-08-17.md` (all path/clock/liveness claims below are proven there; section references `AD0:§n`)
**Masterplan:** `ADVANCED_DATA_OPTIONS_EOD_DARK_POOL_INTELLIGENCE_OS_MASTERPLAN_2026-08-17.md` (operator-held)
**Stop condition:** production acceptance packet (§7) returned for review. AD-2 does not begin.

---

## §0 Acceptance gates (inline, binding — "not done unless")

1. A fresh end-to-end happy path runs with **zero manual workarounds**: nightly/closing-bell lane → brief JSON → served board, on a real current session, with no hand-run steps.
2. The proof's ranked signal symbol is **selected by the production algorithm** — never hard-coded, never cherry-picked after the fact.
3. A **liquid, complete-data symbol shows `NO_SIGNAL`** on the same board, same session.
4. A **degraded/withheld case** is demonstrated (real or induced in staging by withholding an input artifact — never by faking data in production).
5. Per-viewport **visual crops (light + dark + zh)** of the board are posted in the PR body.
6. UI and machine projection are **byte-derived from the same artifact** (parity test §6.11).
7. Front-facing copy passes house language law: no "falsifier/refuted/validated" vocabulary (`scripts/check_validated_claims.py` is CI-enforced); bilingual EN/ZH; no translated text in `title=` attributes.
8. Design: the board is a flagship user-facing surface — design-spec-first per the Design lane (doctrine `docs/DESIGN_DOCTRINE.md`, constitution `research/MASTER_PRODUCT_DESIGN_SYSTEM_V1.md`, specimen `mockups/design_system/specimen.html`); glance tier = state + plain-word stance under word budgets; technicals demoted to hover/detail.
9. No first-pass self-merge of the flagship UI by a child builder — the commissioning session reviews the PR + visual artifact, then owns the normal merge chain.

---

## §1 Exact outcome (one sentence)

> After every completed US market session, the Options Workspace's first viewport opens with a **Daily EOD Options Intelligence Brief**: a machine-built, receipt-backed board showing the market derivatives regime, up to N ranked anticipation/event-pricing opportunity cards each carrying direction-or-type, horizon, asymmetry, confidence, actionability, why-now evidence families, contradiction, trigger, invalidation-as-watch-condition, expected move, fresh-until, source state, and Prophet state — plus explicit `NO_SIGNAL` / degraded states — so a user can answer "what matters now and what would make it wrong" in under one minute without opening a raw chain.

## §2 Exact files allowed

**New files (owned by AD-1):**
- `engine/options_intel_brief.py` — feature computation + composer (families §4.2; contract §5).
- `scripts/build_options_intel_brief.py` — producer CLI; reads §4 inputs, writes the §5 artifacts; no network calls.
- `contracts/options/OPTIONS_INTEL_BRIEF_V1.md` — the frozen schema/contract document.
- `tests/test_options_intel_brief.py` (+ `tests/test_options_intel_brief_js.py` if board JS warrants it).

**Bounded edits (smallest possible diff, no drive-by changes):**
- `templates/options.html.j2` — insert the Brief board at the top of the Daily Brief tab ONLY; no other section may change.
- `.github/workflows/daily.yml` — one step invoking the producer after the collect/engine phase (daily runs 7 days — this is what closes the weekend settle gap, AD0:§1.1-1).
- `.github/workflows/closing-bell.yml` — one step so the T+0 evening board exists before the nightly.
- `config/synapse.yml` — one registry entry for the new artifact (producer/consumer declaration, `tier: display`).

**Explicitly NOT granted:** broad directory authority. If implementation reveals a needed file outside this list, stop and return the gap — do not widen scope in-flight.

## §3 Exact files forbidden

- Collectors and stores: `collectors/*` (all), `scripts/collect.py`, `scripts/build_polygon_gex.py`, `data/*` write paths other than those the producer owns under §5.
- Existing options builders/engines: `engine/options_flow.py`, `scripts/build_options_flow.py`, `scripts/build_gex_board.py`, `engine/gex_confirm.py`, `scripts/build_darkpool_desk.py`, `engine/darkpool_*`, `scripts/build_options_command.py` (the Brief is additive; the Workspace's existing modules are not rewritten), `scripts/build_options_skew.py`, `build_options_ivspread.py`, `build_options_dislocation.py`, `scripts/build_options_prophet.py`.
- Prophet planes: `engine/us_prophet_fusion.py`, `engine/us_board_rank.py`, `engine/prophet_bridge.py`, `scripts/build_prophet.py`, `scripts/grade_us_board.py` — **no new family, no delta, no score logic** (AD-5/AD-7 territory).
- Neural Web: `engine/neuralweb/*`; Sector: `engine/sector*`; Terminal bridge: `scripts/export_signal_contracts.py`.
- Sparse-selector / W1A estate: `engine/options_sparse_selector.py`, `engine/options_market_memory_local_*`, `ops/launchd/*` (all units; nothing is armed or installed in AD-1).
- Episode/outcome ledgers: `engine/options_signal_episode.py`, `scripts/build_options_signal_*` (adapter work is AD-2/AD-6).
- Shared chrome/nav/auth: `templates/_site_nav.html.j2`, `templates/_navlinks.html.j2`, `app/*`.

## §4 Exact source inputs

All inputs are read through their **existing loaders**; AD-1 adds zero ingestion.

| # | Input | Path / schema | Source clock | PIT rule | Coverage threshold | Degraded behavior |
|---|---|---|---|---|---|---|
| 1 | EOD option chains | `data/polygon_gex/chains/{session}.parquet` (per-contract: OI, IV, gamma/delta, volume; session-stamped) | collected ~18:30 ET T+0 (`daily.yml`); OI is next-morning PIT | **no same-day OI**: OI for session S is usable only from S+1 ("positions counted" convention, AD0:§6.2); ΔOI vs immediately prior distinct snapshot day | brief publishes ranked cards only if session chain files cover ≥90% of the Workspace universe (408 names, AD0:§1); below → board_state `INSUFFICIENT_COVERAGE`, cards withheld | latest session chains absent >36h after session close → board_state `STALE_SOURCE`, cards withheld, stamp shows last good session |
| 2 | GEX summaries | `data/polygon_gex/summary_{SYM}.parquet` | as #1 | as #1 | n/a (per-name optional) | missing name → that name's positioning family contributes nothing (family absent, not zero-filled) |
| 3 | Flow accrual | `data/options_flow/summary_{SYM}.parquet` | massive.com EOD aggs | direction is tick-rule **inferred** (~77–83%) — may only feed hedged evidence-family text, never a card's direction on its own (AD0:§6.3) | n/a | missing → demand family absent for that name |
| 4 | Vol-surface display stores | `data/options_ivspread/`, `data/options_skew/` (as read by their live builders) | closing-bell EOD | same-session lawful | n/a | absent → volatility families reduced; card confidence caps lower |
| 5 | Underlying prices / realized vol | the exact price loaders already used by `scripts/build_options_flow.py` / `scripts/build_gex_board.py` (pin the function names in `contracts/options/OPTIONS_INTEL_BRIEF_V1.md` during implementation — reuse, never re-ingest) | EOD T+0 | same-session lawful | n/a | absent → implied-vs-realized family off |
| 6 | Event calendar | `data/earnings/earnings.parquet`, `data/event_windows/forward_log.jsonl` | calendar (known in advance) | forward-known; event-conditioning lawful same-session | n/a | absent → event families off; affected cards carry `null_reason: EVENT_STATE_UNKNOWN`; no event-pricing board section |
| 7 | Prophet state (display echo only) | `site/prophet/index.json` (`prophet.index/v1`, `asof`, plans) | nightly EOD | display-only echo; **no delta computed, no score read into ranking** | n/a | absent/stale → card Prophet field shows "unavailable (as of <date>)" — never blank |

## §5 Exact output contract

**Machine projection:** `site/options_intel_brief.json`, schema `options.intel_brief/v1` (auth-gated in production like sibling data JSONs — AD0:§1; the served page carries the board server-rendered).

Header (all required): `schema`, `as_of_session`, `built_at_utc`, `source_watermarks{chains_session, oi_counted_date, flow_session, surface_session, events_loaded, prophet_asof}`, `coverage{names_present, names_universe, pct}`, `board_state ∈ {OK, NO_SIGNAL, INSUFFICIENT_COVERAGE, STALE_SOURCE, DEGRADED}`, `model_version`, `receipt_id` (hash of input watermarks + model_version — deterministic, §6.10).

`opportunities[]` — each card (field names follow masterplan §6.2 where present):
`signal_id`, `canonical_instrument_id` (via `engine/stock_identity/`), `as_of_session`, `direction ∈ {LONG, VOLATILITY, RISK_ONLY, NEUTRAL}`, `horizon`, `asymmetry_score`, `confidence`, `actionability`, `why_now` (plain-word), `evidence_family_contributions[]` (family name + capped contribution + observed-vs-inferred tag), `contradictions[]`, `trigger`, `invalidation` (front-facing copy = "what would change this read" watch-condition phrasing — operator 2026-07-27 language law), `expected_move_range`, `fresh_until`, `source_state`, `prophet_state`, `null_reason` (null on ranked cards), `what_would_make_this_wrong`.

**Direction enum note (binding):** `SHORT` is intentionally absent. Options Confluence law 17 (AVOID-not-SHORT) forbids bear/short origination anywhere in the options program; bearish evidence expresses as `RISK_ONLY` warnings. If the Chairman wants a SHORT lane, that is a masterplan amendment, not an AD-1 choice.

`event_board[]` — event candidates where implied move and event-conditioned historical distribution diverge: `symbol, event_type, event_date, implied_move, conditioned_move_reference, divergence, direction=VOLATILITY, fresh_until`.

`risk_warnings[]` — crowding/extension/fragility contexts (RISK_ONLY cards).

`no_signal_exemplar` — required whenever `board_state=OK`: one liquid, coverage-complete symbol with `NO_SIGNAL` and its `null_reason` (§4.3 law below).

**UI:** one new board at the top of the Daily Brief tab of `options.html`, rendering exclusively from this artifact (regime strip may continue to come from the existing tiles — the Brief adds the opportunity/event/risk/no-signal layer, it does not duplicate the tiles). Raw chain detail stays in existing tabs (drill-down, not first viewport).

### §5.1 Feature families (only proven fields — AD0:§4)
ATM IV; IV percentile conditioned by symbol/liquidity tier/regime; skew; term structure; implied-vs-realized; implied-vs-event-conditioned move; OI concentration + ΔOI (lawful clock only); DTE/moneyness/liquidity/event-conditioned volume anomalies; strike/expiry concentration; multi-session persistence. Family caps per masterplan §8.3 (correlated fields never become independent votes). All scoring mappings without outcome evidence are labeled `heuristic` in the artifact and cap `confidence` accordingly (masterplan §8.2). Off-exchange families are **excluded** (AD-3 owns them; nothing in the current architecture forces them into AD-1).

### §5.2 No-signal law
`NO_SIGNAL` on liquid complete-data names is a first-class output; the board is allowed to be empty; there is no activity quota; raw-volume leaders are never backfilled into the opportunities list to make it look active.

## §6 Exact tests (minimum; all in `tests/test_options_intel_brief.py`)

1. **Contract identity:** adjusted/nonstandard vendor contract tickers are excluded by rule and counted in a named exclusion stat (never silently aggregated) — AD0:§6.1.
2. **Adjusted contract:** a synthetic adjusted-contract row cannot enter any feature family.
3. **DTE:** DTE computed against `as_of_session` (not wall clock); 0DTE evidence expires with its session.
4. **OI PIT:** using session-S OI for session-S scoring raises; ΔOI uses prior distinct snapshot day.
5. **Quote quality:** null/absent IV and degenerate values are excluded per family and counted; a name below per-name field coverage produces family-absent, not zero.
6. **Event conditioning:** an earnings-window name routes to event families; absent calendar → `EVENT_STATE_UNKNOWN` path.
7. **Incomplete chain:** coverage below threshold → `INSUFFICIENT_COVERAGE`, zero ranked cards.
8. **No-signal:** a liquid complete-data fixture with unremarkable conditioned features yields `NO_SIGNAL` with a `null_reason`.
9. **Stale source:** chains older than the freshness rule → `STALE_SOURCE`, cards withheld, last-good stamped.
10. **Deterministic replay:** same inputs → byte-identical artifact (stable ordering, no wall-clock leakage except `built_at_utc`, `receipt_id` reproducible).
11. **UI/API parity:** the rendered board's cards are exactly the artifact's cards (count + key fields), via the template-render test pattern already used by `tests/test_render_options_workspace_scope.py`.
12. **Correction placeholder:** artifact carries `supersedes_signal_id: null` + `corrected_at: null` on every card and the contract doc states correction semantics are implemented in AD-2 — the fields exist now so AD-2 is additive.
13. Build inputs for fixtures **through the production builder path** with production dtypes (house law: synthetic harnesses must not pick easier dtypes).

## §7 Exact production proof (AD-1 may not pass without all of these)

```text
deployed SHA                      (/api/health checkout, reconciled to the merge SHA)
real latest completed source session   (chains session + oi_counted_date, from the served artifact watermarks)
real source watermark             (source_watermarks block, verbatim)
real ranked signal                (algorithm-selected; symbol + signal_id + card contents from production)
real liquid NO_SIGNAL             (no_signal_exemplar from the same production artifact)
real degraded or withheld case    (a production STALE_SOURCE/INSUFFICIENT_COVERAGE occurrence, or a staging run with an input withheld — never faked data)
signal receipt                    (receipt_id + input watermarks reproducing it)
API output                        (the served/committed artifact; auth-gated fetch or committed copy + served-page parity)
production UI output              (screenshot of the served board, light+dark+zh crops)
freshness display                 (visible as-of/fresh-until on the served board)
```

The proof symbol must be selected by the production algorithm. Auth note (AD0:§1): data JSONs are 401 in production — the lawful proof path is the server-rendered page + the committed artifact + R2 mirror, exactly as AD-0 audited the existing surfaces.

## §8 Stop

After the production acceptance packet is posted, the AD-1 operator stops and returns for Chairman review. AD-2 (receipts/corrections/lifecycle) does not begin. The AD-1 session writes `agentos/handoffs/ADVANCED-DATA-OPTIONS-<date>.md` and updates `WS:ADVANCED-DATA-OPTIONS` wave state in the same PR as its final docs.

---

### Appendix — standing constraints the AD-1 session must load before writing code
- `AD0:§2.4` REJECTED_BY_DESIGN list and the DNR rows quoted there (`KILL-POSITIONING-FUSION` + Amendment 1 scope, `KILL-DOI-FAMILY`, `KILL-SKEW-DECELERATION`, `PSS-AF1`, `HOLD-WF-OPTIONS`).
- Options Confluence binding laws 1–18 (`research/OPTIONS_CONFLUENCE_PROGRAM_BY_FABLE.md` §3): inferred direction, no same-day OI, GEX-as-proxy, correlated-transformations-are-not-confluence, abstention allowed, AVOID-not-SHORT.
- Fleet law: ship loop (commit→push→PR→CI→same-day squash-merge→live verification, one session owns all of it), sparse-worktree opt-in before touching `site/` (`python3 scripts/worktree_sparse.py full`), paired plain-copy rule does not apply to `.j2` templates, GitHub-annotation line-start law, quota discipline.
