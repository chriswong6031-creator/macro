# A0 — Open questions

**Commission:** MASTERMIND GROK-A0  
Preserved as UNKNOWN / ACCRUING / BLOCKED. Not resolved by inference.

---

## UNKNOWN (this session could not verify)

| ID | Question | Search bound / why unknown | What would close it |
|---|---|---|---|
| Q-U1 | Are live R2 event_workspace / Wire / CI objects still the E1P generation `f709a0a6ec514282d5769e7d`? | Handoff 2026-08-17 recorded HTTP 200. This session did not fetch. | `curl` the public marker + workspace object; compare `generation_id` |
| Q-U2 | Does production BioCatalyst R2 / `/var/lib/macro-biocatalyst/state/operational` hold any live CT.gov/FDA/outcome objects? | `data/biocatalyst/` on this checkout is fixtures only | Inspect those roots on the VPS; do not invent a git copy |
| Q-U3 | Where is `data/government_revenue/opportunities.parquet`? | dag.yml + SIGNAL_BUS name it; directory listing this checkout has no SAM parquet; workspace `opportunity.visible=0` | Confirm collector skip vs sparse vs unpublished |
| Q-U4 | Where is `data/government_revenue/budget_program_graph.json`? | D0R handoff claims git HEAD; not in this checkout’s govrev listing | `git ls-tree origin/main -- data/government_revenue/budget_program_graph.json` |
| Q-U5 | Why is `data/neuralweb/factor_contradictions.jsonl` absent? | Module + synapse name it; health catalogs the path; glob 0 | Nightly skip vs gitignore vs dormant panel floor |
| Q-U6 | Are qledger `evidence_clock_start/` and `control_evidence_clock_start/` created on the nightly host? | Code + WS expect write-once files; not in this `data/qledger/` listing | List those dirs on the runner after a prospective registration |
| Q-U7 | Does `data/earnings_calls/` (scores.parquet / queue) exist anywhere live? | Code references; directory missing on this checkout | VPS / nightly data plane |
| Q-U8 | Are Theme Graph’s 11 evidence rows the intended grain, or is evidence minting behind edges? | `_meta.json` 2026-08-18: 8292 edges, 11 evidence | Read `scripts/build_theme_graph.py` mint path (not fully traced this session) |
| Q-U9 | Is `build_theme_graph.py` actually on the nightly workflow, or only `_meta.json lane=nightly`? | Program yml still says implementation roots absent (stale vs `engine/theme_graph/`) | `grep` workflows for `build_theme_graph` |
| Q-U10 | Live VPS `data/government_revenue` vs this checkout | WS landmine: collection/publish can diverge | Compare `bundle_id` / ledger sha on VPS |
| Q-U11 | OpenFIGI / CUSIP overlay freshness and whether any owner besides 13F/resolver uses it | Overlay exists; not a first-class Mesh type | Owner census if a Mesh `cusip` type is proposed |
| Q-U12 | Whether China `policy_transmission` synthetic `kind=omo_mlf` events collide in production counts | Research note exists; not re-measured | Count synthetic vs communique hashes |

---

## ACCRUING (known in-flight; do not pre-empt)

| ID | Item | Owner | Mesh implication |
|---|---|---|---|
| Q-A1 | FIF-1R2 packet contract awaiting Sol review; FIF-2 stopped | `WS:FINANCIAL-INTELLIGENCE-FABRIC` | Mesh may point at fixture packets; no production issuer packet store yet |
| Q-A2 | Earnings E2 (render workspace in Terminal + dossier) | `WS:EARNINGS-INTELLIGENCE-OS` | Do not replace `read_event_workspace` / `event_id_adapter` |
| Q-A3 | Defense D1 rescue; D3 temporal event v3 + Change Tape todo | `WS:DEFENSE-PROCUREMENT-V3` | Do not mint a Mesh “change tape” that pre-empts D3 |
| Q-A4 | Theme Graph TRANSMISSION / contagion layer todo; zero registered consumers | `WS:GMI-THEME-GRAPH` | Do not invent company→theme derived edges |
| Q-A5 | Attested-history production issuer blocked on writer credential | `WS:CALCBENCH-FILING-FORENSICS-PARITY` | No live `ffqsv2_` to join |
| Q-A6 | FF-1 not PROVEN_LIVE (first incremental `universe_invalid`) | `WS:FUNDAMENTAL-FORENSICS` | Broad-SEC objects may be incomplete |
| Q-A7 | Data OS identity spine designed; qledger/boards still ticker-keyed | `lib/dataos/identity.py` | Do not re-key ledgers; Mesh `ISS:` type waits on stored master |
| Q-A8 | TIL promotion-eligible read 2026-10-15 | synapse note | Theme composed state is not promotion evidence |
| Q-A9 | BioCatalyst operating packet identity/regulatory families declared unavailable | packet_producer | Mesh must not treat those families as present |
| Q-A10 | Eval OS T1 107/109 curated; T4 commits nothing | `WS:EVAL-OS-*` | Health is a view, not a store |

---

## BLOCKED (authority / owner conflict — stop rather than duplicate)

| ID | Conflict | Who already owns it | What a Mesh session must not do |
|---|---|---|---|
| Q-B1 | Company Facts bytes | FF ledger + CS snapshots + FIF witness | Do not create a fourth CF store or implicit `revision_of` |
| Q-B2 | Transcript bodies | Terminal `mastermind.tx/v1` | Do not copy bodies into Macro `data/transcripts*` (that tree does not exist on purpose) |
| Q-B3 | Theme lifecycle vs graph composition | TIL vs GMI Theme Graph | Do not merge `theme_state` into `evidence.parquet` |
| Q-B4 | Award graph vs theme USAspending series | GovRev vs thematic `data/usaspending/` | Do not type ticker-month obligations as `govrev.event.v2` |
| Q-B5 | NCT current vs history vs theme collector | BioCatalyst two planes + `collectors/clinicaltrials.py` | Do not collapse namespaces; do not join NCT→ticker |
| Q-B6 | CI v1 listing keys vs E1 issuer keys | Live contradiction recorded in E0 freeze | Adapter exists; do not rewrite history |
| Q-B7 | Listing ↔ CIK binding | Symbol directory receipt: binding **ineligible** | Do not offer a Mesh join that claims it |
| Q-B8 | Universal contradiction store | Five+ typed systems (see capabilities file) | Do not mint `contradiction_id` that picks a winner |
| Q-B9 | Strategic / control plane | Mastermind `strategic_state.yml` + Macro fleet hooks | Mesh is a knowledge join, never a gate (`duplicate_control_planes`) |
| Q-B10 | BioPharmCatalyst scrapes | unclaimed repo-root files | Do not launder into BioCatalyst contracts |

If any of Q-B1–B10 is the only way a proposed Mesh feature works, **stop and report the conflict**. That is this commission’s stop rule.

---

## Questions a later Mesh design must answer (not this census)

1. Who is the **program key** for a Mesh if it is built? Not invented here. Candidates (all already exist): `neural-web` (catalog + clock), `gmi-theme-graph` (receipt law), a new program — the last requires a program-map PR, not a silent store.
2. Is there a funded consumer that fails the boring baseline in `A0_MINIMAL_EVIDENCE_MESH_RECOMMENDATION.md` §8?
3. When Data OS `ISS:`/`SEC:` becomes the stored master, does earnings `cik:` become an alias row or remain a parallel issuer grammar?
4. Should synapse `asof_field` become the Mesh `clock_field` registry (likely yes) or stay documentation?
5. How to version `owner_store` when Defense D3 / FIF-2 / Theme TRANSMISSION ship — additive enum only, same as Theme Graph v1 law.

---

## Out of scope (explicitly not opened)

- Rights / redistribution beyond Theme Graph `licensing_*` mint-time snapshots and earnings `blocked_rights` (non-mintable).
- Primary-source HTTP to SEC / USAspending / SAM / CT.gov / FDA.
- Production verification of VPS vs git.
- Any implementation, schema file under `contracts/`, or synapse entry.
