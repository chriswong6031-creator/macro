# Mastermind Alpha Intelligence Expansion — Wave-c0 Adjudication (Wave-0 census returns)

**Date:** 2026-08-19 (UTC) · **Seat:** Fable Program Integration COO (FABLE-00, wave c0) · **Session:** `claude/alpha-intel-c0-adjudication`
**Baseline:** PASS-0 packet `MASTERMIND_ALPHA_INTELLIGENCE_EXPANSION_PASS0_2026-08-18.md` (pin `47aaa6036846`) · **This adjudication's pin:** `origin/main` @ `fe313751eeef`
**Authority of this document:** NONE. Dated adjudication snapshot under `WS:ALPHA-INTELLIGENCE-INTEGRATION` (runtime authority NONE, permanently). Canonical ownership stays in `config/mastermind_programs.yml`, sibling WS records, and DNR.

Per the PASS-0 handoff's binding `do_not_redo`, this wave did **not** re-run the estate census. It delta-checked the snapshot against fresh `origin/main` and adjudicated the Wave-0 census returns.

---

## 0. K-packet header (c0)

| Field | State |
|---|---|
| WHAT IS NOW TRUE | Five of six Wave-0 censuses have returned and are MERGED: A0 (#5912, `research/evidence_mesh/`), B0 (#5911, `research/alpha_intelligence/censuses/B0/`), D0 (#5913, `research/economic_propagation/`), E0 (#5914, `research/opportunity_evidence/`), F0 (#5915, `research/path_survival/`). All five adjudicated below. Two PASS-0 wait-conditions have cleared: **#5894 MERGED** (theme-graph/identity surface free; V4-D2A bridge landed) and **#5902 MERGED** (PIT replay harness is landed prior art). Lane-B perishability is now receipt-settled (§3): no emergency capture clock exists anywhere in the program. |
| WHAT REMAINS FALSE / ACCRUING | G0 (post-event reinterpretation census) has NOT returned — the commission file exists in the operator pack, undispatched or in flight. FABLE-A has not been dispatched (ruling: §5). Sol rulings on FIF-1R3 (#5889, DO NOT MERGE) and the FF-1P2 STOP (#5898) remain pending — fundamentals/filings coupling stays frozen. |
| CONTRACTS FROZEN | None by this wave. A0's `mesh_ref.v1` sketch is adopted as the **draft input** to the FABLE-A contract wave — a recommendation, not a minted contract. |
| PRODUCTION PROOF | n/a — no runtime touched. Verification receipts in §3 are read-only `git ls-tree` / collector-code reads. |
| AUTHORITY STATUS | NONE, unchanged. Every future lane starts Display/Research/Accruing. |
| PIT / LINEAGE STATUS | n/a for this wave (no data written). |
| COLLISIONS / DEBT | §2 (delta) and §6 (updated lane table). New since PASS-0: Radar/Prophet-Lab surfaces occupied (#5924 recut → open PRs #5925/#5928/#5929); B0 surfaced a standing look-ahead collision in `engine/altdata_models.py` (§3.4). |
| NEXT WAVES | Operator: dispatch G0; dispatch FABLE-A under §5 conditions. Next session: K1 packet adjudication when FABLE-A returns; `c0g` wave when G0 returns. |
| CEO DECISIONS NEEDED | **NONE.** (FIF/FF Sol reviews were already queued by their own workstreams; nothing new is escalated here.) Program continues automatically per commission. |

---

## 1. What this wave adjudicated

Inputs: the five merged census bundles; four read-only fleet censuses commissioned by this session (AgentOS inventory; build-maps/PRs/DNR; reality-side A–D capabilities; belief-side E–J capabilities); one adversarial review of A0's recommendation (opus reviewer); three analysis packets on D0/E0/F0 (opus analysts); direct main-loop reads of A0's recommendation + open questions, B0's decision files, and the FABLE-A commission. Final rulings are this seat's.

---

## 2. Delta since the PASS-0 pin (`47aaa6036846` → `fe313751eeef`)

**Merged (changes PASS-0 state):**

| Change | Effect on the program |
|---|---|
| **#5894 MERGED** (V4-D2A GMI→Data OS identity bridge) | PASS-0 landmine "no D-lane or mesh work touches `engine/theme_graph/*`, `contracts/theme_graph/*`, `config/identity_seams.yml` until it concludes" has **cleared by its own terms**. D-lane wait-condition "#5894 concluded" satisfied. |
| **#5902 MERGED** (general PIT session replay harness) | FABLE-A condition 3's replay leg is now **landed prior art** — the mesh's replay semantics adopt it as merged code, not an armed PR. |
| **#5910–#5915 MERGED** | PASS-0 record itself + five census returns (A0/B0/D0/E0/F0) — the subject of this adjudication. |
| **#5921 MERGED** (prophet-fusion PR-3D-R1) | Fusion arena same-stamp revision + atomic W3 persist; fusion surface remains exclusively `WS:PROPHET-CONDITIONAL-FUSION`'s. |
| **#5924 MERGED** (LAB-0: B5A/B5B recut + Radar W4.1) | Prophet V4-B5 recut into B5A Operator Lab (read-only projection over canonical Radar output, zero Prophet authority) + B5B Early Entry Desk; Radar wave W4.1 minted under `WS:LIVE-ENTRY-RADAR` (`DEC:PROPHET-LAB-B5A-RECUT`). **F-lane collision list updated** (§6). |
| **#5856, #5897 MERGED** | Govrev D1.1F PIT agency labels; Radar W4 hermetic sink fix — routine owner-lane progress, no program impact. |
| **#5923 MERGED** | `WS:PROPHET-HK-CA-REVAMP` minted — outside A–J scope; no collision with any lane here. |

**New/changed open PRs occupying program-adjacent surfaces:** #5929 (radar W4.1 transport), #5925 (entry-radar `live_pack.py` ProbeSet), #5928 (prophet-lab P-LAB-API — touches Radar spool fixtures), #5926 (Canada Prophet board, unarmed), #5927 (biocatalyst read-path profile, docs-only). Standing freezes unchanged: **#5889 FIF-1R3 (DO NOT MERGE, Sol review)**, **#5898 FF-1P2 STOP (do not merge)**, #5737 radar W8 (merge-blocked), #5822 CN institutional masterplan (draft, must be reconciled before any B ontology freeze).

**Unchanged:** all nine forbidden-duplicate classes and their canonical homes; the CRITICAL FIREWALL (OpportunityCase prose never feeds Prophet ranking); DNR kill set relevant to the program (verified live this session — see the fleet-census receipts in §7).

---

## 3. B0 adjudication (GROK-B0, #5911) — **ACCEPTED, rider-compliant**

Rider compliance: B0 re-affirms the FF-1P2 STOP and `DEC:FF-1-BROAD-SUBMISSIONS-USES-SEC-BULK-ARCHIVE` as binding (`B0_COLLISION_AND_ADOPTION_MAP.md` §1, §2); cites `DSC:13F-ATOM-POLL-BUDGET-IS-700-FILINGS` as settled rather than re-deriving it; reconciles #5822 as a K2 gate; authorizes no capture. Compliant.

### 3.1 Perishability — settled this session with fresh receipts

B0 left five verdicts "could not verify" (sparse worktree). This session verified them read-only against `origin/main` tree metadata and collector code:

| Series | B0 fear | **c0 verdict (receipted)** |
|---|---|---|
| P1 IBKR borrow | Collector merged but nightly persistence unknown | **ACCRUING.** `data/ibkr_borrow/daily/` on `origin/main`: 9 dated parquets, 2026-08-05→08-17. Two weekday gaps (08-11, 08-14) are permanently lost; the lane is live. No recovery build. Reliability note routed to the collector's owner. |
| P2 sponsor ETF holdings | Nightly completeness unknown | **ACCRUING at scale.** 3,445 dated files under `data/etf_holdings/` on `origin/main`. Per-sponsor gap audit (e.g. XTN missing 08-10, 08-13) is owner-lane hardening, not a program build. |
| P3 ARK | Coverage gaps | **ACCRUING** (`data/holdings/ARKW/` through 08-17). Vehicle expansion (ARKG/Q/F/X) is rights-gated — Grok side quest. |
| P5 yfinance analyst consensus | Silent perishable if single overwritten row | **REFUTED.** `collectors/yf_analyst.py` appends dated snapshot rows (`data/narrative/analyst_snapshots.parquet`, dedup on ticker+snapshot_date; concat at `collectors/yf_analyst.py:305`, append contract at `:408-431`). Not perishable. |
| P9 ProShares NAV/SO | Best new candidate, rights unread | Stands as B0 wrote it: **rights-gated research candidate** — Grok side quest (ToS read), no capture. |

**Ruling: no emergency capture clock exists anywhere in lane B.** PASS-0 §8's conditional ("the census is the clock instrument") is now closed with receipts. Any later capture PR still needs: source-rights verdict, Data OS routing, off-render R2 placement, its own PR.

### 3.2 Traffic-jam classification of B0's recommendations

| B0 recommendation | Class | Routing |
|---|---|---|
| Verify P1/P2 nightly completeness per sponsor; harden gaps | Nonblocking dependency | Owner lanes (smart-money / etf collectors). Recorded; not this program's build. |
| ARK + ProShares ToS reads (P3 expansion, P9 SO history) | Grok side quest | Safe to dispatch as bounded source-rights research; no capture authority. |
| Fix P5 storage shape | Moot | Refuted — already dated-append (§3.1). |
| Quiver key/heartbeat check (P6) | Nonblocking dependency | Owner ops check (production env; unverifiable from a session checkout). |
| Manager ontology / intent contract / casebook accession fill | Future backlog (K2) | Gated on #5822 reconciliation; no B workstream minted until the K2 contract wave actually starts (PASS-0 do_not_redo). |
| Retire/re-clock the `engine/altdata_models.py` Quiver 13F kernel (§3.4) | **Blocking-dependency ROUTE to canonical owner** | Not B's build. Routed as a defect report to the altdata/Eval-OS owner (below). |

### 3.4 Standing collision surfaced by B0 (routed, not adopted)

`engine/altdata_models.py` still weights a Quiver-fed 13F tape (`CHANNEL_WEIGHTS["smart_money_13f"]=0.85`, `["13f_add"]=0.40`) clocked on **`ReportPeriod` (quarter-end)** rather than `accepted_at` — the look-ahead construction `OWNERSHIP_SIGNALS_CASE_STUDY_REVIEW.md` (2026-06-21) already flagged, and its marquee list includes SM2-R6-excluded names. Per Traffic-Jam law this is a **defect routed to its canonical owner** (altdata / Eval OS surface), not scope for any B lane. It is recorded here so the K2 wave does not silently inherit or grow it.

---

## 4. D0 / E0 / F0 adjudications

Each lane was analyzed by a commissioned opus analyst (rider compliance, load-bearing claim spot-checks against production state, Traffic-Jam classification proposals); rulings below are this seat's.

### 4.1 E0 (GROK-E0, #5914) — **ACCEPTED with conditions on K3-E**

**Rider compliance:** no-composite and no-rank-weights PASS unambiguously (five of seven files end in explicit no-build warnings; "What weights should an Opportunity Score use? Not asked. Do not answer." `E0_OPEN_QUESTIONS.md:55`). Citation half of the cite-don't-fork rider MISSED: #5901, #5872, and `DNR:KILL-FUSED-COMPOSITE` are never named, though the substance forks neither PR. E0's production numbers were independently re-derived and matched exactly (context-vector absence rates, DRL coverage block, 13F census counts, radar ledger state — an unusually high accuracy standard).

**Rulings:**
1. **The dislocation decomposition identity (`E0_DISLOCATION_RESEARCH_SPEC.md:30-37`) is LAWFUL** — it is a regression decomposition emitting named per-term components with mandatory coverage abstention, barred by its own text from timer/gate/ranker use. It is not a `DNR:KILL-FUSED-COMPOSITE` construction. **Condition:** the K3-E contract pins per-term emission and forbids any reconstituted scalar, in one sentence, so the strict reading is closed permanently.
2. **The impairment axis has NO owner** — the commissioning assumption "DRL owns dislocation-vs-impairment" is corrected: DRL owns residual-shock harvest + a filing-*coverage* family (`engine/price_pressure/context.py:36-47`); zero "impair" constructs exist in its masterplan or code. E0's Cell A–E is a lawful extension into unowned space. K3-E must state this ownership vacancy explicitly rather than inherit the assumption.
3. **LSR adjacency affirmed lawful on both grounds:** the analyst-revision firewall E0 walks toward is the reopener `DNR:KILL-LIQUIDITY-SHOCK-REVERSAL-CLASSIFIER` itself names as coverage-blocked-not-null (accrual since 2026-06-16), and E0 proposes no mean-reversion/veto consumer. **Condition:** K3-E cites that DNR row — including its peer-basis-retune clause — by name.
4. **Adopted as blocking (into the K3-E contract):** evidence vector = view/join over `data/us_prophet_rank/candidates/` (no new store); neither Radar nor Prophet consumes the vector; residuals imported from the DRL seam + `engine/residual_alpha.residuals` (never re-derived); the two-object split (statistical vector ≠ economic-cause hypothesis, never computed from ε); the typed slot schema `{construct, state, asof, known_at, value_or_null, coverage_flag}`; the W5-Radar-table score-search prohibition.
5. **Measured defect adopted as a contract rule:** SPY `so_mn` is constant over five weeks (collector carry-forward) — the "shares-outstanding is the honest flow proxy" rule is unsafe as written. K3-E rule: an ETF-flow slot's `state` derives from **observed variation in the artifact**, defaulting `stale`, never from the field's nominal meaning.
6. **K3-E's largest gap to close:** the fusion-family map. Every census slot must be typed as (i) research-only, (ii) a read of an existing family member (F2/F3/F4/F5/F7/F8 homes per the fusion masterplan), or (iii) a candidate NEW member — and (iii) routes through K5 / Eval OS, never through lane E. One-column-one-family is registry-enforced.
7. **Mesh dependency ruling:** E0's boring-baseline answer (a view over an existing store, referencing no mesh objects) substantially discharges the PASS-0 §5 "K1 mesh objects" gate for lane E — **K3-E contract prep may proceed in parallel with K1**, adopting A0's clock/subject vocabulary where it references observations.
8. **Grok side quest cleared:** E0's four cheapest-next-measurements (revisions↔t0 join; DRL stratification by `peer_basis`×`edgar_covered`; PIT excess for same-t0 winner pairs; the `stockdata` peek closing Q9) — read-only, bounded, no store, no score.

### 4.2 D0 (GROK-D0, #5913) — **ACCEPTED with a rider-repair condition on K3-D**

**Rider compliance:** three-graph separation STRONGLY complied (a whole deliverable enforces it object-by-object, `earnings_readthrough_hypothesis/v1` named as the only lawful join). Kill-receipt rider PARTIAL: `DNR:KILL-CAUSAL-DAG-ALPHA` cited and honored ×5; but `DNR:KILL-PSS-SR2-PEER-DIFFUSION` and `DNR:KILL-CN-SUPPLY-ABSORPTION` are never named, and `DNR:KILL-PSS-SR3-PARTICIPATION` is mis-summarized as "participation is display-tier" — the actual row closes a specific construction and demands a future species measure an **orthogonal** source, which matters because D0's Graph 3 is precisely the participation/breadth substrate SR2/SR3 died on. The census's *substance* independently reproduces those lessons (common-cause failure catalog; generator refusals). **Ruling: repairable rider defect, no re-census.** K3-D's contract header must carry the two unnamed kills by key, the corrected SR3 summary, and a generator-refusal row closing peer-participation/breadth-as-target-generator.

**Rulings:**
1. **D0's central negative ACCEPTED and now production-verified past its own reach:** no firm-level customer/supplier economic-relationship graph exists anywhere; `data/theme_graph/edges.parquet` has **zero** Graph-1-type rows ever written (8,292 rows: MEMBER_OF/EXPRESSES/TRACKS only; exposure axes null in all rows); the join object is architecture-only.
2. **Adopted as blocking:** no new graph store — GMI W4 + GR3b + Defense D5/D10 are the ramps and EP is a consumer/honesty layer, never a fourth spine; CHF/TXI/CSP stay off firm-level economic edges; the Demand Desk `ai_datacenter` scored-thesis chain is named **out-of-scope** for EP (the estate's one live scored propagation path — absorbing it silently imports a scored path); the `defense19-v1` pin stands (`DNR:LAW-REVIEWED-MANIFEST-CENSUS`).
3. **EP ownership presumption adopted:** economic propagation is a **record class, not a program key** — K3-D is the act that decides ownership and must not mint a `economic-propagation` registry entry that reads as a fourth spine.
4. **Watch-items converted to K3-D conditions:** the six-state bottleneck vocabulary's fence ("in this lane") becomes unconditional until an owner (D10 nominated) accepts it; "its PIT grade ledger" is struck — grading routes through `engine/grading.py` + existing forward ledgers, period.
5. **K3-D must inherit what D0 predates:** the GMI W2 verdict's binding constraints (`economic_share` has no minted formula — blocked until segment-grain ingestion; W4 charters only from MEASURABLE-NOW cells; `DNR:HOLD-TICKER-EXPOSURE-TAGS` adjacency); the post-#5894 identity clause (Data OS spine is the exact-identity authority; **only ~25% of GMI company nodes currently resolve** — 701 RESOLVED vs 1,869 NOT_IN_MASTER — so an exact-identity propagation contract has a D2B-shaped queue in front of it and must abstain typed, not guess); the corrected GR3b premise (8-K counterparties now populate — 1,949 non-null — but are dominated by financing agents, not supply-chain relations).
6. **Casebook sufficiency ruling:** 43 rows with zero new PIT-rebuilt primaries is **sufficient for a display/research-tier contract freeze** (per epistemics law a null never blocks display-tier building); the PIT rebuild preconditions D0 names are **promotion-gate** conditions, inherited at K5/gauntlet time, not K3 blockers.
7. **Registry heals routed to owners (nonblocking):** `earnings-intelligence.owns` "read-through context" wording (already prescribed by `DEC:EARNINGS-INTELLIGENCE-PROGRAM-OWNERSHIP`) and the stale `gmi-theme-graph.implementation: []` note — both are those programs' registry PRs, cited not performed here.

### 4.3 F0 (GROK-F0, #5915) — **ACCEPTED; K4-F scope narrowed to the safe core**

**Rider compliance:** CLEAN on both riders (no control-matched-grading claim anywhere — the census explicitly defers the control leg to QLedger's owner; docs-only PR, no Radar surface touched). Three factual defects found, all conservative (under-claims): QLedger's grade rows carry a **populated `bench_ret`** on all 59,929 rows (F0 reports "no relative leg" — wrong map for a market-relative path read); `capture` is dimensionless, not percent (Q7's dichotomy is malformed — same object); `day0_samples` has a pass-through producer hop. K4-F inherits the corrected facts.

**Rulings (per-recommendation):**
1. **RATIFIED as standing law:** no `engine/path_survival/grader.py` — the spine extends, never forks; `capture` stays owned by `engine/track_scoring.py` (spine may re-export, never recompute); no MFE/MAE columns on `grades.jsonl`; the minute-plane/auction exclusions stand.
2. **AUTHORIZED as the K4-F smallest real unit:** persist `stopped_at_bar` / `cushion_at_bar` / `liftoff_at_bar` on board/track rows — the values are computed today and dropped at `scripts/grade_us_board.py:1172-1174`; pure schema-union write, no new definition, no gauntlet. Plus the plane/basis stamps (`price_plane_id`/`fill_convention`/`return_basis`/`path_basis`) **once the refusal rule has a named enforcement seat** (the spine is a library that writes nothing; three writers exist — un-seated, the rule becomes three implementations).
3. **DENIED this wave (Radar seam):** making Radar `replay/outcomes.py` a caller of spine OHLC helpers. F0's own draft bans unevaluable-as-negative (`gap_through` None-not-False), but Radar's shipped code emits `False` when the ATR barrier is unevaluable — on a **frozen W5 prereg surface**. Changing that value is a Radar wave with its own prereg amendment, owned by `WS:LIVE-ENTRY-RADAR`, never a Path-Survival side effect. Likewise the OHLC first-passage plane (§2.2) stays un-authorized until a named consumer needs one row carrying both close-path and OHLC-path — F0's own off-ramp.
4. **DENIED as written:** any `WS-PATH-SURVIVAL` whose `owns_paths` includes `engine/grading.py` — that hands a research lane the estate's shared grading spine (~10 callers). If a WS is minted at K4 it owns `research/path_survival/` only.
5. **Deferred until definitions are picked at commission time:** `close_location` (three candidates, unratified), `time_underwater_from_fill` (three candidates), the censoring convention. Each unresolved definition at commission time is a place a builder mints a second one.
6. **K4-F must cite what F0 omitted:** `engine/entry_radar/replay/controls.py` + `assembly.control_forward_return` — the estate's one working matched-control implementation is invisible in F0's reuse map; a K4 wave reading only F0 would rebuild it.
7. **Collision surface correction (post-#5924):** the F-lane's actual reuse targets (`engine/entry_radar/replay/*`, `engine/grading.py`) are collision-free — the live occupation moved to the transport plane (#5929 armed, #5925 unarmed, colliding on `live_pack.py` — a Radar-lane matter, noted to that owner) and the new Prophet Lab consumer (#5928). **F never routes holdability numbers through the Lab** — the Lab is a zero-authority read-only projection (`DEC:PROPHET-LAB-B5A-RECUT`); a path metric arriving via it is the named authority leak. F0's `forward_rows_total=0` data-basis finding **expires when #5929 lands** and the W4→W5 spool starts accruing; K4 re-reads it then. Cheap pre-condition before any OHLC work: settle whether `data/baskets/ohlcv` O/H/L columns are dividend-adjusted (a wrong answer invalidates every gap-through number).

---

## 5. FABLE-A dispatch ruling

**A0 (GROK-A0, #5912) — ACCEPTED as prior art; recommendation adopted AS AMENDED. FABLE-A: CONDITIONAL GO, contract-first, with the §5.1 binding amendment rider.** Recorded as `DEC:ALPHA-INTEL-FABLE-A-CONTRACT-FIRST-DISPATCH`.

The dispatch gate ("FABLE-00 explicitly confirms the ownership/collision check is clean") is hereby confirmed **with conditions**: the surface collisions PASS-0 named have cleared (#5894, #5902 merged); the remaining freezes (FIF-1R3 #5889 Sol review; FF-1P2 STOP #5898) are handled by rider rather than by waiting, because FABLE-A's contract wave does not touch them. An adversarial review of A0's recommendation (opus reviewer; verdict "GO with a binding amendment list, not GO as written") found one blocker and four majors — every one an omission or over-permissive clause in an otherwise correct frame; the census half of A0 (5 of 7 files) is sound and consumed unchanged.

### 5.1 Binding amendment rider (embed in the FABLE-A dispatch)

1. **STRIKE A0 §5's `or` branch** on the `cik ↔ ticker_store_key` join. A cik↔listing join goes ONLY through earnings `company_identity.v1` PIT alias. The "dated symbol-directory + cik_map pair" route is forbidden by contract constant (`contracts/symbol_directory/symbol_directory_completion_receipt.v1.schema.json` — `listing_sec_identity_binding_eligible: const false`); A0's own three sibling files list the same join as forbidden.
2. **Complete the adoption inventory.** A0's packet never mentions `engine/institutional_census/` (whose amendment-lineage dedup is THE precedent the mesh generalizes), `KnowledgeClock`/`VintagePolicy` (including the live duplicate `VintagePolicy` definition in `engine/fundamental_forensics/` that archaeology must surface), `engine/qledger_evidence_clock.py` (disambiguated by name from the Neural-Web display evidence clock), or the merged #5902 replay harness. FABLE-A's archaeology covers all four; the `owner_store` enum gains an `institutional_census` row; #5902's six-clock chronology is mapped onto `clock_class` or the loss is reported.
3. **Add an `object_class` discriminator** (`world_observation | derived_view | system_belief | forward_claim`) — or drop `qledger.claim` and `txi.episode` from v0. The Reality-vs-Market-Belief separation the program exists for must exist at the row level; instrument verdicts are not market verdicts.
4. **Identity per PASS-0 §7.3, not a minted type.** No `ticker_store_key` (its claimed backing is a two-row Yahoo vendor-alias helper, not an identity plane); `theme_node` grammar carries the `#<epoch>` suffix (`engine/theme_graph/identity.py` mints epoch node ids precisely to stop cross-break joins); `engine/stock_identity/` and `engine/ledger_identity.py` are adopted, not dismissed; Data OS `ISS:`/`SEC:` stays future-typed until the stored master is authority (unchanged from A0).
5. **Persistence stays undecided until decided properly.** No `data/evidence_mesh/` path presumption; any physical persistence decision is part of the contract wave, routes through Data OS conventions, and registers in `config/synapse.yml` (producer, `asof_field`, freshness SLA, owner program named in the K1 packet). The un-minted program key is a K1-packet question for Sol, not a silent default.
6. **Bind `clock_class` to synapse `asof_field` names** — otherwise the 7-value enum becomes a fifth PIT vocabulary by default (A0 left this open as its own question).
7. **The flip condition becomes operator-decidable** (see `DEC:ALPHA-INTEL-FABLE-A-CONTRACT-FIRST-DISPATCH`): the physical pointer store builds only for a NAMED PR/workstream committed to consume ≥3 owner_stores in one query — A0 §7's hypothetical Brain consumer does not self-certify it.
8. **Name the object honestly.** `mesh_ref.v1` is a pointer index, not an observation log: content-hash identity with the write clock excluded makes re-observation unrecordable and carries no outcome — the actual observation-log construction `DNR:LAW-RUN-CLOCK-IN-CONTENT-IDENTITY` prescribes (one object per run, digest + clock + outcome) is a separate object if ever wanted. Canonicalize the field-name set (`native_digest`/`join_recorded_at` vs the provenance matrix's `observed_digest`/`join_as_of`) before freeze; give `native_digest`/`coverage_class` explicit UNKNOWN discriminators and `authority_class` a stated default-on-absence.
9. **Unchanged PASS-0 §7 conditions:** FIF leg on fixture packets only until Sol rules on FIF-1R3; no adapter builds (C) before the freeze; golden fixtures (absent from A0 — FABLE-A supplies, per its commission's hostile-case list) and zero rank/gate/size consumers required for K1 acceptance.

---

## 6. Updated lane table (supersedes PASS-0 §5–§7 where they differ)

| Lane | c0 state | Conditions |
|---|---|---|
| **FABLE-A / K1** (mesh contract) | **GO NOW** — operator dispatches with the §5.1 rider appended | Contract-first; store build gated on the operator-decidable flip condition; FIF fixture-only |
| **K3-E** (opportunity evidence vector contract) | **READY to commission** — may run in parallel with K1 (mesh dependency discharged by E0's view-over-existing-store answer) | §4.1 rulings 1–6 embedded in the commission; no commission file exists yet (operator/Sol authors it) |
| **K3-D** (propagation contract) | **READY to commission** — #5894 cleared; identity abstention rule mandatory (75% of GMI company nodes unresolved to the spine) | §4.2 rulings, incl. the kill-receipt repair paragraph and GMI-W2 inheritances; no commission file exists yet |
| **K4-F smallest unit** (persist bar-indices + plane stamps) | **AUTHORIZED** as scoped | §4.3: enforcement seat named first; Radar seam DENIED; OHLC plane gated on a named dual-basis consumer |
| **K2-B** (manager ontology/intent contract) | WAIT | #5822 reconciliation first (unchanged) |
| **B capture builds** | REMAIN STOPPED — **no emergency clock exists** (§3.1, receipted) | Side quests cleared: ARK + ProShares ToS reads (rights research only) |
| **G lane** (post-event reinterpretation) | WAIT | G0 outstanding (operator dispatches it); any G build is an Earnings-OS wave after E2 (unchanged) |
| **H** (OpportunityCase) | WAIT (K5) | Unchanged; firewall intact |
| **I** (families into fusion arena) | WAIT (K5, via Eval OS gauntlet) | Unchanged |
| **J** (expert/complementarity ledgers) | WAIT (K6) | Unchanged; K4-F inherits the corrected QLedger map (`bench_ret` live, `control_ret` never populated) |

**Nonblocking defect routes recorded (owners', not this program's):** `engine/altdata_models.py` Quiver 13F look-ahead kernel (retire/re-clock — altdata/Eval-OS owner, §3.4); `earnings-intelligence.owns` registry wording + `gmi-theme-graph.implementation: []` staleness (those programs' registry PRs); #5925/#5929 two-PR collision on `engine/entry_radar/live_pack.py` (Radar owner); P1/P2 collector gap-hardening (collector owners); census placement drift (A0/D0/E0/F0 landed outside `research/alpha_intelligence/censuses/<lane>/` — recorded here as the actual homes; no file moves).

---

## 7. Evidence trail

- Delta: `git log 47aaa6036846..origin/main` (236 commits; non-wire set quoted in §2), `gh pr list --state open --limit 100` (18 rows, run this session).
- Fleet censuses (this session, read-only): AgentOS inventory (26 WS records opened; `python3 scripts/agentos.py validate` exit 0, 224 records); build-maps/PRs/DNR census (both build maps + DNR §1–4 opened; program-owner table from `config/mastermind_programs.yml` + `docs/MASTERMIND_SYSTEM_MAP.md`); reality-side A–D capability census; belief-side E–J capability census.
- Perishability receipts: `git ls-tree origin/main -- data/ibkr_borrow/daily/` (9 files), `git ls-tree -r origin/main -- data/etf_holdings/` (3,445 files), `git ls-tree -r origin/main -- data/holdings/` (ARKW through 08-17), `collectors/yf_analyst.py:305,408-431`.
- Census bundles adjudicated: `research/evidence_mesh/A0_*.md` (7), `research/alpha_intelligence/censuses/B0/*.md` (8), `research/economic_propagation/D0_*.md` (7), `research/opportunity_evidence/E0_*.md` (7), `research/path_survival/F0_*.md` (6).
- FABLE-A commission: operator pack `mastermind_fanout_FABLE-A_evidence_mesh.md` (read in full).
