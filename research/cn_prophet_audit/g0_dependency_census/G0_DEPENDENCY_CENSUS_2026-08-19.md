# G0-DEPENDENCY-CENSUS — current-state ledger

**Commission:** `G0-DEPENDENCY-CENSUS`  
**Program named in the commission:** `WS:CN-LIMIT-ALPHA`  
**Governing freeze named in the commission:** `CN_LIMIT_R6_FINAL_ARCHITECTURE_FREEZE_2026-08-19.md`  
**Observation pin:** `f57565ac52bfc48d5bc1539d1112bed87ba36004`  
**Clock:** `2026-08-19T18:27:05Z`  
**Tip subject at observation:** `hot-tape: radar 2026-08-19T18:26Z [skip ci]`  
**PR base after later hot-tape ff:** `ccdb62402eb600c6a383c03638968d0da51f9f2d` (marketing press-wire only; owner-file blobs unchanged)  
**Worktree:** `macro-main/.grok/worktrees/cn-limit-r6-g0-dep-census` on `grok/cn-limit-r6-g0-dep-census`

This packet is a mechanical current-state ledger. It does not merge, does not choose feature signs, does not grant authority, and does not execute G1–G6.

---

## STATUS

`COMPLETE_WITH_SUPERSESSION_FLAG`

G0 ran because the commission id was named. The status gate `AUTHORIZED_AFTER_R6_0` is **not proven open**:

1. The named freeze file `research/CN_LIMIT_R6_FINAL_ARCHITECTURE_FREEZE_2026-08-19.md` is **absent** from `origin/main` at the pin, absent from `git ls-tree`, and absent from `gh search code` in `mastermindx-market-intelligence/macro`.
2. A different freeze is on main: `DEC:CHINA-ALPHA-INTELLIGENCE-ARCHITECTURE-FREEZE` via PR **#5953** (merged `2026-08-19T16:05:16Z`, merge SHA `c617be762ae7dee6af9e96877f946a8bc16a5bb6`). That document **self-declares** the freeze becomes effective at Sol's final freeze review, not at merge.
3. Stop condition hit: **ambiguous supersession**. Grok does not choose whether (a) the named CN-Limit R6 freeze is still unlanded, (b) China Alpha #5953 is the R6 pin, or (c) they are parallel. Fable must name the pin.

Dormant commissions **not executed:** G1 `DORMANT_P0_ST`, G2 `AUTHORIZED_AFTER_OWNER_PLANE_LANDS`, G3 `DORMANT_I1A`, G4 `DORMANT_M2`, G5 `DORMANT_SOURCE_READY`, G6 `DORMANT_POST_MERGE`.

---

## SOURCES AND CLOCKS

| Source | Clock | Command / locator |
|---|---|---|
| `origin/main` tip used as census pin | `2026-08-19T18:27:05Z` | `git fetch origin && git rev-parse origin/main` → `f57565ac52bfc48d5bc1539d1112bed87ba36004` |
| Named freeze blob | same | `git cat-file -e origin/main:research/CN_LIMIT_R6_FINAL_ARCHITECTURE_FREEZE_2026-08-19.md` → fatal, path does not exist |
| GitHub code search for freeze filename | `2026-08-19T18:21:00Z` | `gh search code --repo mastermindx-market-intelligence/macro "CN_LIMIT_R6_FINAL_ARCHITECTURE_FREEZE"` → empty |
| Open PR compact list | `2026-08-19T18:21:00Z` and `2026-08-19T18:23:48Z` | `gh pr list --state open --limit 100 --json number,title,headRefName,headRefOid,mergeable,mergeStateStatus,url,updatedAt,labels` |
| Per-PR mergeability | `2026-08-19T18:23:48Z` | `gh pr view <n> --json number,title,state,mergeable,mergeStateStatus,headRefOid,labels,url,updatedAt` |
| Per-PR check rollup (5945/5947/5951) | `2026-08-19T18:26:00Z` | `gh pr view <n> --json statusCheckRollup` |
| AgentOS / engine / ST file blobs | `2026-08-19T18:22:13Z`–`18:27:05Z` | `git rev-parse HEAD:<path>` and `git log -1 --format='%H %cI %s' -- <path>` |
| `docs/ACTIVE_BUILD_MAP.md` | generated `2026-08-19T15:02:31Z` (stale vs this census) | file header; base `2313bdbd9b73634ced5dd34c41858c7ab25136df` |
| Local non-git search | `2026-08-19T18:06:50Z`–`18:19:22Z` | filename walk of macro-main, Mastermind, charting-app, `.grok/worktrees` → no freeze filename |

REST remaining after the census reads: `3530` at `2026-08-19T18:27:05Z` (`gh api rate_limit --jq '.resources.core.remaining'`).

---

## METHOD

1. Session start: `git fetch origin && git merge --ff-only origin/main` in `/Users/chriswong/Documents/Cluade/macro-main` (succeeded; tip then moved under hot-tape). Feature work in a new sparse worktree off `origin/main`.
2. Prove the G0 gate from the named freeze file, AgentOS, and GitHub. Gate not proven; census continued as a current-state table with a supersession flag (stop = do not pick a winner).
3. Inventory owner paths from `WS:CN-LIMIT-ALPHA`, `WS:CHINA-ALPHA-INTELLIGENCE`, `WS:STOCK-IDENTITY`, exact-plane charter, ST/risk-warning collectors, and the four engine files the commission forbids Grok from editing.
4. Resolve every claimed PR to `gh pr view` state + SHA + URL. Resolve every claimed file to `git rev-parse <pin>:<path>` or record `ABSENT_MAIN`.
5. Diff the named R6 pin (missing) against what is actually on the census pin, including freeze-cited GROK-CN evidence files.
6. Dedup owner paths: one row per path; PRs listed once even when they also appear as file last-writers.

No outcomes were read. No production helpers were patched. `engine/china_board_rank.py` and `engine/china_prophet_shadow.py` were read for SHA/last-commit only.

---

## OUTPUT FILES

| File | Role |
|---|---|
| `research/cn_prophet_audit/g0_dependency_census/G0_DEPENDENCY_CENSUS_2026-08-19.md` | this packet |
| `research/cn_prophet_audit/g0_dependency_census/G0_DEPENDENCY_LEDGER_2026-08-19.csv` | machine table: owner/path/status/mergeability/SHA/URL/next gate/clock |
| `research/cn_prophet_audit/g0_dependency_census/G0_R6_PIN_DIFF_2026-08-19.md` | named-freeze vs current pin |
| `research/cn_prophet_audit/g0_dependency_census/G0_COLLISIONS_2026-08-19.md` | collision list |

GitHub blob URLs are `https://github.com/mastermindx-market-intelligence/macro/blob/f57565ac52bfc48d5bc1539d1112bed87ba36004/<path>`.

---

## TEST RECEIPTS

Anti-vacuity:

1. **Every claimed PR/file has a resolvable URL/SHA.** Positive control: `git rev-parse HEAD:research/CHINA_ALPHA_INTELLIGENCE_MASTERPLAN.md` → `ebe8f4c6f816b2de0f0d73d1033ddf36cd75df9d`. Negative control: named freeze path fails `git cat-file -e` (recorded as `ABSENT_ON_ORIGIN_MAIN`, not invented). Open PRs have `headRefOid` from `gh pr view`. Merged PRs have `mergeCommit.oid` from `gh pr view`.
2. **No stale-state claim without timestamp.** Every row in the CSV carries `clock_utc`. `docs/ACTIVE_BUILD_MAP.md` is labeled stale because its generated clock is `2026-08-19T15:02:31Z` vs census `2026-08-19T18:27:05Z`.
3. **Owner paths deduped.** `engine/china_board_rank.py` appears once as ENGINE_AUTHORITY; PR #5808 is its last writer, not a second owner. `collectors/china_st.py` appears once as ST_PARITY; PR #5975 is listed as last writer. China Alpha G0 slot (#5943/#5955) is separate from this commission id.

Instrument positive control for “no open PR on `china_board_rank.py`”: `gh pr list --state open --search "china_board_rank.py"` returned `[]` at `2026-08-19T18:23:48Z`. The same search shape returned the GROK-CN open set when the query was `china OR cn-limit`.

---

## GAPS

- Named CN-Limit R6 freeze file is not in git, GitHub code search, Mastermind, charting-app, or local worktrees scanned this session.
- Sol's “final freeze review” of #5953 is not an observable GitHub object in this census. The workstream `next_action` still waits on it.
- GROK-CN evidence files cited as binding freeze inputs by the merged China Alpha freeze are **not on main** except CN-F (#5950). See collisions.
- `data/china_st/*.parquet` blob SHAs are recorded; row contents were **not** opened (G1 is dormant; sparse worktree omits `data/` checkout).
- Open-PR check rollups were sampled on #5945/#5947/#5951 only. Other GROK-CN opens were `MERGEABLE` + `UNSTABLE` at `2026-08-19T18:23:48Z` without a full pack list.
- `mergeable: UNKNOWN` on some already-merged PRs is GitHub's post-merge field, not a live mergeability claim.
- `origin/main` is a hot-tape. Owner-file blobs for the China Alpha masterplan and `china_board_rank.py` were unchanged between `ab4b50a1` and `f57565ac`; later tips may move.

---

## DEVIATIONS

- Commission non-goal “no code” honored: no engine, collector, or test edits. Census artifacts are research markdown/CSV only.
- Commission non-goal “no merge decision” honored: no `gh pr merge`.
- Commission “do not touch `engine/china_board_rank.py`, `engine/china_prophet_shadow.py`, exact-plane authority constants, or AgentOS decisions” honored: SHA reads only; no AgentOS `DEC-*` minted.
- Output lives under `research/cn_prophet_audit/g0_dependency_census/` (WS:CN-LIMIT-ALPHA `owns_paths`) rather than `research/alpha_intelligence/censuses/CN-G0/` (occupied by PR #5943).
- Gate `AUTHORIZED_AFTER_R6_0` was not proven; the census still shipped as a flagged ledger rather than inventing a freeze pin.

---

## COLLISIONS

See `G0_COLLISIONS_2026-08-19.md`. Headline collisions:

1. **G0 name collision.** This commission is `G0-DEPENDENCY-CENSUS` under `WS:CN-LIMIT-ALPHA`. `WS:CHINA-ALPHA-INTELLIGENCE` wave `g0` is already `done` as CN-G0 #5943 + US G0 #5955. Different id, different path, same letter.
2. **Freeze collision.** Named CN-Limit R6 freeze absent; China Alpha architecture freeze present and self-not-yet-effective.
3. **Freeze-cites-unmerged-evidence.** #5953 on main cites CN-A…CN-G artifacts whose files are still only on open PRs #5944/#5945/#5946/#5947/#5949/#5951, except CN-F #5950 which is merged.
4. **WS:STOCK-IDENTITY W2 status stale.** File still says `in_progress` after #5643 merged `2026-08-16T18:48:33Z`.
5. **ST 2026-07-06 is two facts, not one.** `collectors/china_st.py` comments a push2 502 freeze at 2026-07-06. `config/cn_limit_rules.yml` splits BSE *ordinary* (not main-board ST) at 2026-07-06 at the same ±30% width. G1 is the repair census; Grok did not collapse them.

---

## EXACT HANDOFF TO FABLE

Fable, not Grok, must answer these before any later G commission or builder spawn:

1. **What is the R6 pin?** Land `CN_LIMIT_R6_FINAL_ARCHITECTURE_FREEZE_2026-08-19.md`, or declare in a DEC that #5953 / `DEC:CHINA-ALPHA-INTELLIGENCE-ARCHITECTURE-FREEZE` is the pin, or declare they are parallel. Grok will not choose.
2. **Is `AUTHORIZED_AFTER_R6_0` open?** Until (1) is named, treat G0 as a current-state snapshot, not as proof the gate opened.
3. **Open GROK-CN PRs vs freeze citations.** #5944, #5945, #5946, #5947, #5949, #5951 are OPEN, labeled `merge-on-green` and `merge-blocked`, `mergeable=MERGEABLE`, `mergeStateStatus=UNSTABLE` at `2026-08-19T18:23:48Z`. The merged freeze already treats their verdicts as adopted. Merging, closing, or rewriting those PRs is a Fable reconciliation, not a Grok merge.
4. **Do not spawn G1** until Fable names the frozen P0 repair branch. `collectors/china_st.py` last landed on #5975; that is not a G1 receipt.
5. **Do not spawn G2** until the owner plane lands. PR-0D / RIGHTS-0 remain gated on Sol's final #5953 review per the China Alpha workstream.
6. **Do not spawn PR-0B from this packet.** The commission file is on main; the spawn gate in `WS:CHINA-ALPHA-INTELLIGENCE` is still Sol's final review. Grok did not touch `china_board_rank.py` / `china_prophet_shadow.py`.
7. **Identity next gate** is PR-0D coordinated with `WS:STOCK-IDENTITY`, extending the canonical Data OS master. No `china_company_master`. W2 is merged; the workstream YAML still says otherwise.
8. **Exact-plane** remains a requirements charter (`research/CN_LIMIT_EXACT_PLANE_LEDGER_PREREG_REQUIREMENTS_2026-08-11.md`). No ledger, no imported rows. `DNR:KILL-CN-ADJUSTED-TAPE-LEGAL-LIMIT` in force.

If Fable wants this ledger on main, squash-merge the census PR after reviewing the supersession flag. Grok does not merge it.

---

## Compact human table (deduped)

Full machine rows: `G0_DEPENDENCY_LEDGER_2026-08-19.csv`.

| Owner | Path | Status | Mergeability | Head SHA | Next gate |
|---|---|---|---|---|---|
| NAMED_R6_FREEZE | `research/CN_LIMIT_R6_FINAL_ARCHITECTURE_FREEZE_2026-08-19.md` | ABSENT_ON_ORIGIN_MAIN | n/a | — | Fable names or lands the pin |
| WS:CN-LIMIT-ALPHA | `agentos/workstreams/WS-CN-LIMIT-ALPHA.md` | active_on_main | n/a | `55da1d756935add56fc9bb16d34ed9c936e3c9a7` | P-A2/P-C/exact-plane; P-D last |
| EXACT_PLANE | `research/CN_LIMIT_EXACT_PLANE_LEDGER_PREREG_REQUIREMENTS_2026-08-11.md` | requirements_charter_only | n/a | `77e61101da37b1bff820f1583a6de00b06f1167f` | §5 gates + fresh prereg |
| CHINA_ALPHA | `DEC:CHINA-ALPHA-INTELLIGENCE-ARCHITECTURE-FREEZE` | on_main, self-not-effective | merged #5953 | `c617be762ae7dee6af9e96877f946a8bc16a5bb6` | Sol final review of #5953 |
| CHINA_ALPHA | PR-0B / RIGHTS-0 / PR-0D commissions | todo_gated | n/a | blob via #5953 | after that review |
| CHINA_ALPHA_G0_SLOT | #5943 CN-G0 / #5955 US G0 | MERGED | merged | `be6c477c3d80…` / `c2f3f7da8bbb…` | closed; not this G0 |
| ENGINE_AUTHORITY | `engine/china_board_rank.py` | on_main, no open PR | none_open | `5b51575f2cbc0834c19bc3208e45f853bb982cf7` | Grok must not touch |
| ENGINE_AUTHORITY | `engine/china_prophet_shadow.py` | on_main, no open PR | none_open | `67183dc11557d07d434f650297846dbce7b9ef19` | PR-0B later; Grok must not touch |
| IDENTITY | `WS:STOCK-IDENTITY` | active; W2 YAML stale | #5643 merged | `fa2f3d2161881b17b279cc79c2798cb1c83181f3` | Fable reconcile YAML; PR-0D coord |
| IDENTITY | #5894 GMI→Data OS / #5965 D2B1 | MERGED | merged | `a8b9b0c208c1…` / `860cbd782d4c…` | PR-0D for China/HK gap |
| ST_PARITY | `collectors/china_st.py` | on_main | none_open | `e72880babb46c24dc22fe8a27d7a0756a3b9a023` | G1 dormant |
| ST_PARITY | `config/cn_limit_rules.yml` | on_main | n/a | `9eec691c45a308f01b58538b51085cc66dfe0e93` | Grok does not interpret |
| GROK_CN_OPEN | #5944 #5945 #5946 #5947 #5949 #5951 | OPEN | MERGEABLE / UNSTABLE | see CSV | Fable reconcile vs #5953 citations |
| GROK_CN_MERGED | #5950 CN-F | MERGED | merged | `179dee1474b3f8eed226ec5d4b2de04520a94e43` | artifacts on main |
| CENSUS_PIN | `origin/main` | moving hot-tape | n/a | `f57565ac52bfc48d5bc1539d1112bed87ba36004` | re-pin before later waves |
