# PROPHET US — CURRENT STATE, 2026-08-17 (V4-0A)

**Pinned execution main:** `fc0557bb0873f51db5ccbab4b043b26bbc9bb670` (2026-08-17T06:04:45-05:00; Sol's snapshot was `16874921e638` — deltas in §11).
**Method:** six read-only archaeology lanes (production/serving, data/publication, entry, intelligence, evaluation, experience) at the pinned SHA; production surfaces curled 2026-08-17T11:44Z (Monday, pre-open). Every claim carries a file:line or command receipt. No production code was changed and no workflow was dispatched by this session.

## 1. Production truth — the outage is LIVE

**No Prophet checkpoint has landed since 2026-08-14T04:25:52Z** (commit `012fbedc64`, "durable nightly checkpoint 2026-08-14", carrying source session 2026-08-13). All readable serving surfaces agree, byte-identical (1,384,976 bytes):

| Surface | source_asof | Receipt |
|---|---|---|
| git `main` `site/prophet/index.json` | **2026-08-13** | contents API; newest checkpoint commit above |
| R2 public mirror | 2026-08-13 | `Last-Modified: Fri, 14 Aug 2026 04:26:12 GMT` |
| GitHub Pages mirror | 2026-08-13 | deploy LM Mon 17 Aug 11:19Z (deploy clock, not data vintage) |
| VPS `www.mastermind-x.com/prophet/index.json` | auth-gated (HTTP 401) | public `showcase.json` LM Fri 14 Aug 04:27:02 GMT |

Schema `prophet.index/v1`, 206 plans, newest cohort `recorded_at=2026-08-13` (27 plans); **no cohort exists for 2026-08-14 or later anywhere**. The VPS pull loop itself is healthy (`checks.site.commit_time` ~11 min old at check) — Prophet specifically is frozen while other lanes advance main.

- **Friday 2026-08-14's session was never captured**; the gap survived the weekend into Monday.
- The most recent real-compute nightly (run `31977372592`, created Sat 2026-08-16T22:48:50Z) ran collect/factor jobs green, but **job `engine` concluded `failure`** and the run sat `status: queued` on ~8 downstream jobs ~13h after start; `publish` (Pages) concluded success anyway under `if: always()`. Root cause of the engine failure is undiagnosed (out of 0A's read-only scope) — **it is V4-A1's first question**.
- Issue **#5742 is OPEN** ("Prophet US staleness — 2026-08-14", filed by `scripts/prophet_rescue.py` 2026-08-15T09:55:45Z; zero comments — duplicate-verdict suppression, not silence).
- **Detector asymmetry:** `prophet-rescue.yml` (hourly, fine ladder) concluded red on its six most recent wakes (06:03→11:00Z today) — red is its alert semantics; `nightly-liveness.yml` (twice daily, coarser) read green at 08:45Z. The finer instrument is alarming while the coarser one is calm; reconciling them is A2 material (both should read one settlement manifest).
- PR **#5723** (merged 08-15) fixed the DST cron supersede mechanism only; its own handoff forbade recovery-by-redispatch from that session. The staleness has continued **past** the fix: not one successful post-fix nightly checkpoint exists.
- Rescue discipline unchanged: `prophet_rescue.py` is the sole auto-redispatcher (2/night attempt budget counting `max(runs_seen, issue_receipts)`, `scripts/prophet_rescue.py:194-201`); this 0A session dispatched nothing per its non-goals.

## 2. Publication architecture (why Pages/Git/R2 can disagree)

Two independent publish gates inside `daily.yml`'s engine job, plus two mirrors:

- **Git gate** — `prophet_checkpoint` (`daily.yml:2630-2852`): isolated `git worktree` off `origin/main`, closed file allowlist (`:2717-2732` — `site/prophet/{index,showcase,board_read_sparks}.json`, `data/prophet/{ledger.jsonl,ledger_quarantine.json}`, arena scoreboard, origination receipts, legacy_shadow parquets, plans/states), 12 push attempts, fails closed `::error title=Prophet checkpoint NOT pushed` (`:2852`), `continue-on-error: true`.
- **Site gate** — `upload pages artifact` (`:5326`, `if: always()`) uploads the runner's local `site/` unconditionally; `publish` job (`:6888-6895`, `if: always()`) deploys to Pages **regardless of engine's conclusion**.
- **Designed conservatism:** the broad commit step restores Prophet paths to pre-checkpoint HEAD before staging (`git checkout HEAD -- site/prophet data/prophet/…`, `:5062-5070`) so Pages "can serve the prior safe copy for this run" while checkpoint/VPS carry the new publication.
- **Measured violation (2026-08-16, run `31913143619`):** engine failed all 12 checkpoint pushes AND the broad commit's 7 attempts, yet **Pages served the brand-new 71-row `us_prophet_v3` board while git kept the pre-override v2 board** (as_of 2026-08-13). The first v3 board was never committed. Why the restore fence did not keep Pages conservative that night is **not derivable from workflow source alone** (needs that run's job logs) — recorded here as unresolved, and it is the concrete case V4-A3's one-bundle-ID design must make impossible.
- **R2** cannot diverge upward: its publish re-verifies `merge-base --is-ancestor` + byte-hash against current `origin/main` immediately before upload (`:2875-2902`) and no-ops if superseded.
- **Production is the VPS** (Caddy pulls git main every ~3 min; TencentEdgeOne CDN in front; `/prophet/index.json` auth-gated, path allowlists `app/deploy/Caddyfile:343,469,513`). `pages.yml` is a manual-only redeploy of committed main and explicitly not production.
- **Downstream false-green:** `us_prophet_ledgers` (`daily.yml:6234`, `if: always()`, fresh main checkout) can conclude green while accruing nothing on a failed-engine night — it never sees unpushed data.

## 3. Data plane inventory (writers → artifacts → readers)

| Artifact | Path | Writer | Cadence/law |
|---|---|---|---|
| Canonical live board | `site/factordata/us_standouts.json` | `scripts/build_stock_library.py` (ranked by `engine/us_board_rank.py` + `engine/us_prophet_fusion.py` C1 since v3; stamps per-row `board_definition`) | nightly engine job, before Prophet |
| Trade plans/states | `site/prophet/plans/*.json`, `states/*.json` | `engine/prophet_bridge.originate_plans` via `scripts/build_prophet.py` | nightly; git-published only via the checkpoint |
| Prophet index/showcase | `site/prophet/index.json`, `showcase.json` | `scripts/build_prophet.py` | top-level `asof`/`recorded_at` are WALL-CLOCK publication stamps; freshness = `source_asof` + per-plan cohorts (`DSC:PROPHET-ASOF-IS-WALL-CLOCK`) |
| Forward plan ledger | `data/prophet/ledger.jsonl` (42 rows) + corrections/quarantine | `scripts/build_prophet.py` (`:518` "Nightly is the SOLE advancer") | horizon-free closure `T1_HIT/T2_HIT/EXPIRED/INVALIDATED`; **no benchmark field — raw returns only** (EVAL_SPEC §7 remedy unshipped) |
| Candidate store (sensory spine) | `data/us_prophet_rank/candidates/YYYY-MM.parquet` | `engine/us_context_vector.py:append_candidates` (`:1413`), nightly-gated (`:1473`) | PIT, keep-first, schema-union; carries `prophet_shadow_*` (13 cols); **STALLED — no commit since 2026-08-14** |
| All-name grades | `data/us_prophet_rank/grades/YYYY-MM/YYYY-MM-DD.parquet` (`us.prophet_grades/v1`) | `engine/us_prophet_grades.py` via `scripts/grade_us_prophet_candidates.py --nightly` | H=10/21/42/63 excess-vs-SPY; zero authority |
| Board fossil snapshots | `data/us_board_ledger/snapshots.jsonl` (+`_v2`) | `scripts/grade_us_board.py --nightly` | FOSSILS — exact bytes as served, never rewritten |
| Board retro grades | `data/us_board_ledger/retro_grades.parquet` | `scripts/grade_us_board.py` | 5/10/21/63d vs SPY and sector ETF; per-definition blocks (era partition) |
| Legacy shadow (plan grain) | `data/prophet/legacy_shadow/YYYY-MM/YYYY-MM-DD.parquet` | `prophet_bridge.append_legacy_shadow` (`:1785`) | frozen pre-ANTICIPATION rule, zero authority; parts end 08-13 |
| Radar forward store | `data/entry_radar/forward.parquet` | `scripts/reconcile_entry_radar.py --nightly` (sole durable writer) | `mastermind.entry_event.v1` events |
| TURN WATCH deck | `site/turn_watch/turn_watch.json` | `scripts/build_turn_watch.py` (`config/dag.yml:784-790`; `daily.yml:3469-3496`, non-fatal) | **stale: `data_session=2026-08-13`, 4 commits ever; page never built** |

**Two parallel "board history" stores** exist by design: `data/us_prophet_rank/` (candidate intake + all-name grading; feeds origination context) vs `data/us_board_ledger/` (track-record/showcase grading; feeds landing). Pick deliberately; they are not interchangeable.

## 4. Output-width truth (the candidate-volume question)

**There is no hard production cap.** `N_CANDIDATES = 12` survives only as an overridden default (`engine/prophet_bridge.py:146,1147`); the sole production caller passes `n=None` (`:4127`; independently `daily.yml:2270` and disclosed at `:2493`); docstring: "live plan origination always passes `n=None` and applies no positional slice" (`:1176-1177`), the "12→16 with sector cap 4" spec explicitly superseded (`:1276-1280`). `LEGACY_N_CANDIDATES=12` (`:613`) feeds only the frozen shadow comparison. Observed 10–20-name boards are produced by the **gate chain**:

1. Upstream board admission — the confluence admission gate + C1 fusion in `scripts/build_stock_library.py` / `engine/us_board_rank.py` decides `buy[]` membership before Prophet runs ("it never decides who is on the board" — `us_board_rank.py:6-7` on the score; the GATE narrows).
2. `select_candidates()` (`prophet_bridge.py:1145-1282`): `entry_signal` present → tone admitted → `conviction.band != "low"` → `tier_cascade ∈ {T1,T2,T3}` when present (**hardcoded at `:1219-1224`, mirrors `engine/signal_gate.py:104 BUYABLE_TIERS` without importing it — drift risk**) → `admission_class ∈ {patience, confirmation}` (`buy_soon` **excluded**, recorded as having graded poorly). Sort only, no slice (`:1281-1282`).
3. `originate_plans()` survivorship (`:4052-4230`): duplicate plan-ID suppression; one open plan per ticker+direction (`:4191-4199`); options-structure plan validation.
4. Post-selection passes are non-narrowing by design (reclass/annotation only, `:4255-4258`, `:4873-4882`).

V4 consequence: "no producer cap" is already true at the bridge; the V4 work is **episode preservation upstream of the narrow gate chain** (B1) and lane truth (B3/B4), not cap removal. The slow cascade's authority lives in step 2's `tier_cascade` requirement — that is what B3/B4 demote to maturity-expert status.

## 5. Entry estate

**Live Entry Radar waves as of TODAY** (`agentos/workstreams/WS-LIVE-ENTRY-RADAR.md` + `agentos/handoffs/LIVE-ENTRY-RADAR-2026-08-17.md`):

| Wave | State | Receipt |
|---|---|---|
| W0–W3 (contract, probe bus, G0 exact + parity, 1D/4H challengers) | done | #5578, #5625, #5698, #5724 |
| W4 live evaluator (VPS 5-min plane) | **merged, STAGED-NOT-ARMED** | #5768; `ENTRY_RADAR_LIVE_ENABLE=1` in `/etc/macro-live.env` gates systemd timer pairs; absent ⇒ "staged, not armed" (`research/live_entry_radar/W4_DEPLOY_PLAN.md:13-22`) |
| W5 forward evidence + replay | **done — closed THIS MORNING** | #5825 (squash 2026-08-17T10:08:44Z) + records #5827; Panels A/B re-run clean (0 refusals; 7,546 + 212,593 episodes); Q1 UNINFORMATIVE (M14 69.86% < 90%), Q5 PASS_SHAPED, Q2 ACCRUING |
| W6/W7 (priority, outcome model) | todo | WS record |
| W8 UI reference | **todo — #5737 open/unmerged; zero bytes on main** | `git ls-files` empty for entry_radar templates |
| W9 production UI | todo | WS record |

- **The full-RTH activation proof is still OWED** and structurally requires the operator arm step (`W4_DEPLOY_PLAN.md:37-40`). Nothing records it run. Every "Radar live" claim today is staged, not evidenced. (= V4-B6's mission.)
- **Experts preserved:** G0 grey-dot parity adapter (`engine/entry_radar/g0_adapter.py:183,252`), C1 1D washout (`challengers.py:812,857`), C2 with exactly six frozen variants (`:953-1064`), C3 1D+4H recovery (`four_hour.py:267,419`), C4 stratification-only (event-minting refused, `entry_events.py:518-526`, fencing `DNR:KILL-WASHOUT-TURN`), C5 Bottom Watch port (`c5_adapter.py:154,183`). Store: append-only `mastermind.entry_event.v1` (`entry_events.py:44,784`). Grey-dot parity CLOSED at W2 (`research/live_entry_radar/W2_G0_PARITY_RECEIPTS.md` §3, exact-at-vintage true).
- **Lifecycle law exists in Radar:** `PROBING→ARMED→TURNING→CANDIDATE→{RESOLVED,INVALIDATED,EXPIRED}` (`detectors.py:226-265`); re-arm after terminal + (K>50×2 sessions or 15 sessions); provisional bars can never self-finalize (`entry_events.py:541-549`). Radar is contractually forbidden from importing Prophet's `confluence_tiers` (contract §16) — the two provisional systems are distinct.
- **TURN WATCH:** data plane real (`DECK_CAP=40` of 345 triggered, `beyond_cap` published, lane floor fixed same-day); **user surface explicitly deferred and never built** (no template was ever committed); artifact stale at 2026-08-13; **no owning workstream** (absent from every WS `owns_paths`) — an orphan desk. V4-B5 is where it finally reaches the Chairman; this WS takes ownership.
- **B-15…B-19 defect labels** (masterplan §8.3) resolve to the independent audit `research/US_PROPHET_COMMERCIAL_LAUNCH_READINESS_2026-08.md` §5.4/§8 (2026-08-11) against #5370's early-turn union: **B-15** open-3D-bucket repaint at admission; **B-16** manifest scheduled-red/schema-version consistency; **B-17** shipped deck ≠ measured object (union∩confirmed-lane vs naked-union numbers; wiring `prophet_bridge.py:4018,4318-4319`); **B-18** deck⊇plan invariant inverted with un-era-stamped admissions; **B-19** chase verdict off a dead union fire. **At-pin re-resolution (adversarial review): several appear ALREADY CLOSED** — the CONFIRMING/CONFIRMED stage constants the audit flagged were DELETED by the §J.9(c) ruling (`engine/us_early_turn.py:960-963` names it; `lifecycle_state` is now the public lifecycle vocabulary), and the chase leg is now explicitly "gated on a LIVE fire, never on the mere presence of a `fire_date`" (`:1026`) — the source asserts the opposite of B-19. The audit's line numbers no longer resolve at `fc0557bb0873`. **V4-B2 therefore opens by re-resolving each label at its own pin and producing the disposition matrix — do not assume any remain open, and do not cite the audit's line numbers as current.**
- Related open upstream defect: Terminal `confluence_v2` 2D/3D grid is leading-history-phase-dependent (macro ruled its own engine safe; handed to charting-app lanes; `research/prophet_us_audit/EARLY_ADMISSION_BAKEOFF_2026-08-11.md` R4).

## 6. Intelligence estate

- **Conditional Fusion:** live ranker `engine/us_prophet_fusion.py` (`admit_members/aggregate/fuse_board`), 8 families `F1_TECHNICAL_CONFLUENCE…F8_ATTENTION_CROWDING` (`:164-172`); **F3_THEME_STRUCTURE / F6_MACRO_REGIME / F7_QUALITY_FUNDAMENTAL are structurally absent from the board row today** (`:179-192` — "no theme/basket/relay evidence column"). Registry `research/prophet_fusion/families.yml`; called from `engine/us_board_rank.py:1182-1184`; `BOARD_DEFINITION="us_prophet_v3"` (`:100`). PR-3A #5813 MERGED 2026-08-17T04:04Z; **PR-3B = outcome-blind LOFO + full member census, a separate fresh session; its forbidden zone = the Fusion WS `owns_paths` verbatim (8 paths)**. W2B live-acceptance banked 14/14 on the first v3 board — read from Pages because that night's engine failed to push (§2).
- **Context vector:** `engine/us_context_vector.py` — the PIT sensory spine (one flattened block per name per night, zero authority at birth), the natural substrate for `prophet.intelligence_vector/v1`. Its only theme signal reads the OLD curated-basket engine (`theme_pulse_by_ticker`, `:435-465`, from `data/baskets/latest.json`) — **the theme graph and the context vector are two unjoined planes today** (matches F3's absence). Accrual previously stalled silently 08-07→08-13 (logger-prefix swallowed `::warning`), and the store is stalled again now (§1/§3).
- **Theme graph (GMI):** W3A shipped (#5718): `engine/theme_graph/{store,materialize,capability,identity,local_sources,probation,rights}.py`; stores `data/theme_graph/{nodes,edges,capability,evidence}.parquet` + probation proposals; Finviz (268) + THS (373) local-theme nodes, PIT `MEMBER_OF`, capability sidecar (`semantic_only/measurement_candidate/measurable`), rights gate `assert_public_emission_allowed()`. **No `state/` subdir — ThemeState v1 not built** (target `data/theme_graph/state/YYYY-MM-DD.parquet` already spec'd in the GMI masterplan); no ranking authority, no user surface. The stale GMI WS record (still "blocked on the 08-15 scrape") is corrected in this PR from merged evidence.
- **Earnings (EIOS):** E0 in progress (artifact set drafted; not merged per the WS `next_action`), E1/E2 todo. Estate hazard: Wire vs Company-Intelligence planes disagree per-issuer today (`DSC:EARNINGS-WIRE-AND-CI-DIVERGE-ON-THE-SAME-ISSUER`; calendar `fresh_row_fraction=0.1785` under a fresh stamp). V4's earnings family = `ACCRUING` until E1's canonical workspace is live.
- **Alt-data:** 16-family census in `SOURCE_RIGHTS_AND_COVERAGE_REGISTRY.md` §3, with live degradations: insider collector dead since 2026-Q1 (`PRODUCER_DEGRADED`), short interest PIT-lawful but 3 settlements committed (`ACCRUING`, not estimable), analyst revisions 0.67% event coverage.
- **Stock Identity:** W0 #5583, W1 Atlas v0 #5612, W1-A1 correction #5660 all merged; W2 replay in flight; W3–W7 gated. V4 consumes `stock_identity.*` interfaces only.
- **Theia:** no adapter/ingestion code; commented-out registry stub (`config/theme_sources.yml:49-52`); procurement question prepared-not-decided (W3A rights doc §5) — now resolved by `DEC:PROPHET-V4-THEIA-SOURCE-RIGHTS` (default original build; license = Chairman option).

## 7. Evaluation estate

- **Three graded surfaces** (`research/MASTERMIND_PROPHET_EVAL_SPEC.md` §1): A board ranking (`scripts/grade_us_board.py`, 5/10/21/63d vs SPY + sector, per-definition era partition `:1479-1553,1696`), B plan ledger (horizon-free closure; **no benchmark column — raw returns**; 28 closed / 24 honest-N, win 32.1%, t=+0.178 at 08-12 = accrual-status under the 50-obs floor), C live states (detection only, ungraded). Plus all-name grading (H=10/21/42/63 vs SPY) on the candidate store.
- **Nightly-sole-advancer confirmed mechanically** for every Prophet ledger (`ledger_lane.nightly_advance_enabled()` gates; `reconcile_prophet_live.py:735,750` refuses without `--nightly`; pinned by `tests/test_prophet_off_engine_lane.py`).
- **Era discipline is real:** per-row `board_definition` + `published_definition()` (`us_board_rank.py:1289,1773`); `SELECTION_ERA="anticipation-v1-2026-08-08"` deliberately not bumped for the rank change; degraded nights publish `us_prophet_v2_fallback` + degradation receipt; store dedupes on `(stamp_date,ticker,board_definition)`. No pooling defect found. Open risk: `families.yml`'s `champion_baseline` list is definition-unaware (`DSC:CHAMPION-BASELINE-COLUMNS-CARRY-THE-CHALLENGER`).
- **Two shadow grains, deliberately different** — board grain = paired `prophet_shadow_*` columns on the same row (`DEC:PROPHET-SHADOW-GRAIN-IS-A-PAIRED-ROW`, `DEC:US-SHADOW-ACCRUES-UNDER-ITS-OWN-COLUMN-FAMILY`); plan grain = separately-keyed parts `data/prophet/legacy_shadow/`. **V4-C2 must reuse this split**: paired-row for V3-vs-V4 board comparison, keyed parts only if a plan grain is needed. `us_prophet_v3_legacy_shadow` has zero code today.
- **QLedger** (`engine/qledger.py`, 46,630 claims / 59,929 grades) is the general claim/grade substrate; **not wired to Prophet today**; integration pattern already worked out by Radar's Track-E census (`make_claim(desk=…, claim_family=…, horizon_d=21, bench="SPY", control=sector ETF)`). Inherited defect to avoid: **no claim has ever populated `control`** (`DSC:NO-QLEDGER-CLAIM-EVER-CARRIED-A-CONTROL-LEG`) — V4 grading is not "control-matched" until a producer writes the leg. Data-plane corruption fails open outside `--strict` (`DEC:EVAL-OS-BLINDNESS-EXITS-BY-PLANE`).
- **No intraday-episode grader exists for Prophet**; the only prior art (Radar W5 replay/evaluator) is walled off by `DEC:LER-SEPARATE-SYSTEM-NOT-PROPHET-CHANGE` and grades a different thing. V4-C1 builds cohort projection from the common episode plane; the required cohort list (§16.1) is a from-scratch build (today's only split is `tier: curated/scan`).

## 8. Server/client contract (the buy_soon divergence — and it is worse than assumed)

The split is not "server vs browser JS" — it is **four independently-coded readiness readings** over the same underlying fields, plus an upstream population split:

1. **Engine stage** — `engine/us_board_rank.py:418-432`: `_LIVE_STATUSES = frozenset(("buy_now","partial","buy_soon"))` (`:429`) buckets `buy_soon` rows into `STAGE_LIVE` → label **"Live now"** (`:443-448`), with the "entry window is open now" subtitle supplied by the template (`dashboard.html.j2:15929,15957`); drives board headings + `data-stage` filters (`templates/dashboard.html.j2:15968-15981,16207`).
2. **The card's own verb chip** — computed independently in the same template (`dashboard.html.j2:16029-16034`): `buy_soon → 'near'` → renders **"Near"/"临近"** (`templates/_prophet_card.html.j2:371-372`) — the card contradicts its own section heading.
3. **Table-view stage** — a third derivation baked into `us-stocktable-data` (`dashboard.html.j2:15804`): `{'bottoming':'ENTRY',…,'watch':'RAN_LATE'}` keyed on the technical `lane`, **never reads entry timing**; `templates/stocktable.js:647-649,1145-1158` adds its own client-only "KNIFE" bucket. Toggling Grid↔Table can relabel the identical row.
4. **Int-valued stage rail** — the inline lane→int dict at `dashboard.html.j2:16035` (MP-1 calls it the "`_STAGE_BY_LANE` duplicate" — that name exists only in MP-1's text, not as a repo identifier) drives the card's 4-stage "Bottoming→Turning→Ready→Trend" tracker (`_prophet_card.html.j2:11`), also lane-derived.

**Upstream population split:** `engine/prophet_bridge.py` treats `buy_soon` as a deliberate refusal (`:186-188` "it graded WORST of the CN entry statuses; admitting it imports the chase without the evidence"; refusal receipt `:429`; enforced `:1226-1235`) — but `select_candidates()` does not populate the page. `scripts/build_stock_library.py` writes `site/factordata/us_standouts.json` directly (`:6096`); prophet_bridge is a downstream consumer (`build_stock_library.py:1712-1713`). The board the Chairman sees is admitted by a different gate than the plan book.

**A design-ratified fix already exists, unexecuted:** `research/migration_packets/MP-1-prophet-board.md` (2026-08-13, design-authority-authored per #5504/#5505) prescribes a 7-cell plan-lifecycle ladder (watch/ready/entered/delivering/overtime/invalidated/resolved), orders the RIPENING table chip RETIRED and the inline lane→int stage dict REMOVED, and names re-sourcing the card population from `_su.buy` to the plan book (`site/prophet/index.json.plans`) as the migration's "structural act". **Gate status at pin (corrected by adversarial review): G-B satisfied** (`.mx-ladder` live in `theme.css:1940`, Sol §J.9), **G-C satisfied** (frozen R3 crop set, light/dark/zh + 390w, in `mockups/refs/institutionalize/us_stocks/`), **G-A NOT satisfied in production** — its producer (#5506, `build_prophet.py:2482-2484`) merged 2026-08-14 ~17h after the last published checkpoint, so `HEAD:site/prophet/index.json` carries no `lifecycle_state`/`lifecycle_counts` and cannot until V4-A1 lands the first recovered nightly. Nothing in the template reflects MP-1 yet. V4-B3/B5/E2 build against MP-1 rather than re-designing, with B5 dependent on A1's published artifact (reconciliation ruling: `ARCHITECTURE_FREEZE.md` §12.4).

**Auth/delivery gap:** the page is public; tier caps are a DOM-visibility overlay (`templates/tier_preview.js:27` caps — anon 1 row, free 3, paid unlimited — applied via blur/`aria-hidden` at `:198-213`), while the FULL board (cards + table JSON) is unconditionally SSR-baked into page source (`dashboard.html.j2:15796-15825,16001-16002`). Server-side withholding exists as a house pattern (ETF desk `premiumdata/etfs.json`, `scripts/build_site.py:3016,3100,3164`) and MP-1 §7 assumes `premiumdata/us_stocks.json` — which does not exist. Anonymous visitors can read the full board from source today.

**Complete-visibility state:** the card grid has true progressive disclosure ("Show all N", `theme.js:4784-4857` — nothing permanently hidden), the featured cap is honestly disclosed (12, ≤4/sector, `dashboard.html.j2:16394`), but the table view — the closest thing to All Candidates — is built only from `_su.buy` and **excludes** watch/leaders/laggards and the separate `ran` shelf (`RAN_CAP`, `build_stock_library.py:5366-5377`). TURN WATCH has complete bilingual engine copy (`prophet_bridge.py:196-272`) with **zero template consumers**; the only similarly-named live surface is basket-scoped (`basket_detail.html.j2:1135-1145`), not the per-stock desk. Track record shows an era-break disclosure rather than silent overwrite (`_track_record_dlg.html.j2` via `dashboard.html.j2:16424-16438`).

## 9. Vocabulary disambiguation (read before naming anything in V4)

| Term | System 1 | System 2 | Rule |
|---|---|---|---|
| `G0, C1–C5` | **Radar experts** (grey dot, washouts, MTF; `engine/entry_radar/`) | **Fusion arena rungs** (ranking challengers C1=live v3 ranker, C2–C5 future; `research/prophet_fusion/`) | Always prefix: "Radar C2" vs "Fusion C2". They share letters and nothing else. |
| `C0–C6/C7` | `engine/prophet_arena.py` **execution-policy** challengers (`data/prophet_arena/`) | audit-era `C0–C4` bake-off vocabulary (`EARLY_ADMISSION_BAKEOFF_2026-08-11.md`) | Same. |
| "arena" | `prophet_arena` (execution policy) | `prophet_fusion_arena` (rank fusion) | Name the module, never bare "arena". |
| `v2` | `us_prophet_v2` ranker ERA | `us_standouts_v2.json` / `retro_grades_v2.parquet` / `snapshots_v2.jsonl` = SA-W5 SCHEMA version | Never infer era from a `_v2` path. |
| "board history" | `data/us_prophet_rank/` (intake/grading) | `data/us_board_ledger/` (track record/fossils) | Pick by purpose; not interchangeable. |
| "shadow" | board grain: `prophet_shadow_*` paired columns | plan grain: `data/prophet/legacy_shadow/` keyed parts | Two grains by ruling; don't collapse. |
| "provisional" | Radar `bar_state` (contract §5) | Prophet `confluence_tiers` bucket repaint | Separate systems; Radar may not import the latter (§16). |
| "availability" | Radar `AVAILABILITY_STATES` (`engine/entry_radar/contracts.py:106`) = INPUT readability (confirmed/provisional/stale/unavailable) | V4 `availability_state` = trade validity (can I buy it) | Different facts; B1 consumes Radar records so both land adjacent — always qualify which. |
| "episode" | Radar runtime ledger `mastermind.live_entry_episode.v1` (expert-keyed, ephemeral) | V4 `prophet.candidate_episode/v1` (security+anchor-keyed, durable); also `options.signal_episode/v1` and `us_board_rank.py:247-336` calibration vocabulary | Freeze §3 grain reconciliation is binding. |

## 10. Live defects/stalls register (inputs to wave scoping)

1. **Prophet checkpoint stalled since 08-14** (§1) — A1.
2. **Candidate store + legacy-shadow parts stalled since 08-14/08-13** — A1 must recover the full checkpoint manifest, not just the board JSON; C-lane acceptance assumes this store is live.
3. Run `31977372592` engine failure undiagnosed; downstream jobs queued ~13h — A1 first question.
4. 08-16 Pages-newer-than-git violation mechanics unresolved — A3's concrete case.
5. TURN WATCH artifact stale + orphan ownership + no surface — B5 (+ownership lands in this WS now).
6. B-15…B-19 dispositions unknown post-heal — B2 opens with the matrix.
7. Radar W4 activation proof owed (operator arm step) — B6.
8. `tier_cascade` tiers hardcoded at `prophet_bridge.py:1219-1224` vs `signal_gate.BUYABLE_TIERS` — fold into B3 (lifecycle contract removes the duplicated authority).
9. Theme planes unjoined (graph vs curated baskets); F3/F6/F7 structurally absent — D-lane.
10. Insider collector dead since Q1; short-interest depth 3 settlements; revisions 0.67% — D7 rows enter as `PRODUCER_DEGRADED`/`ACCRUING`/`PARTIAL`, never silent zeros.
11. Earnings planes disagree per-issuer — D6 binds to E1's canonical workspace only.
12. QLedger control leg never populated — C1 must wire it or not claim control-matching.
13. Plan ledger lacks benchmark columns — C1 scope.
14. `champion_baseline` definition-unaware in `families.yml` — E1 must not read it literally (Fusion lane owns the fix).
15. Detector asymmetry (rescue red / liveness green simultaneously) — A2 makes both read the manifest.
16. Four-way stage derivation split + board-vs-plan-book population split (§8) — B3's core case; MP-1 prescribes the page-side fix.
17. **Anonymous full-board data leak** (tier caps DOM-only; no `premiumdata/us_stocks.json`) — commercial exposure today; candidate for an early standalone fix using the ETF-desk withholding pattern; at latest E2 acceptance.
18. Table view excludes watch/leaders/laggards/ran — All Candidates (B5/E2) replaces it as the complete surface, building OVER the existing lossless pool (item 19).
19. **Prior-art systems the "new" V4 contracts must reconcile, not rebuild** (surfaced by adversarial review; each is now bound into the owner map §2 / freeze §3): `engine/entry_signal.py` (existing buy-zone/chase/stop semantics → B4), `engine/entry_radar/live_ledger.py` (runtime episode ledger → B1 grain reconciliation), `engine/us_candidate_lanes.py` (lossless candidate pool, operator commission 2026-08-11 → B5/C1), `scripts/freshness_sentinel.py` (reader-visibility + first-fresh settlement receipts → A2), `engine/prophet_doors.py` (preregistered origination doors → B1), `engine/prophet_integrity.py` (`outage_backfill` reconstruction provenance → A1), `engine/neuralweb/market_memory_pit.py` (content-addressed manifest + atomic HEAD pattern → A3 prior art).

## 11. Deltas vs Sol's snapshot (`16874921` → `fc0557bb`)

| Sol §3 ledger row | What changed by execution pin | Receipt |
|---|---|---|
| "Radar W5 … records unwritten; PARTIAL/reconcile" | **SUPERSEDED — W5 closed** the morning of 08-17: replay re-run clean, records written | #5825 (10:08:44Z) + #5827; `agentos/handoffs/LIVE-ENTRY-RADAR-2026-08-17.md` |
| "Current Prophet committed index … stale at review" | Still true and **still live** — no checkpoint since 08-14; outage ongoing | §1 |
| "Aug-14 outage detection — issue #5742 open" | Confirmed open, zero comments, condition active | §1 |
| "PR #5723 merged … future proof incomplete" | Confirmed; zero successful post-fix nightlies yet | §1 |
| "bridge now has `N_CANDIDATES=None`" | Confirmed with nuance: constant=12 survives as an overridden default; production passes `n=None` | §4 |
| "Pages/git split … unresolved architecture debt" | Mechanism now fully mapped incl. designed conservatism AND the unexplained 08-16 violation | §2 |
| "GMI workstream record stale" | Fixed in this PR (W3A row added from merged evidence; blocked→active) | `agentos/workstreams/WS-GMI-THEME-GRAPH.md` |
| "Stock Identity W2 in progress" | Confirmed; W1-A1 correction (#5660) also merged | §6 |
| Fusion "PR-3A #5813 merged; PR-3B next" | Confirmed; PR-3A merged 04:04Z today | §6 |

**AgentOS rows found stale but deliberately left to V4-0B** (records-only wave): `WS-PROPHET-US-AVAILABILITY.md` W0/`next_action` still say "land the hardening PR" while `prophet_rescue.py` + workflows are live on main and firing; no availability handoff exists for the CURRENT staleness episode. The V4-A1 handoff carries the true state inline so the recovery session cannot be misled by the stale record.
