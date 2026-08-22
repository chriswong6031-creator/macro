# P1 — natural-run receipt and 145-candidate reconciliation (2026-08-21)

Records-only. This file states what the first natural post-#6142 Asia-close run
did; it changes no code, no schema, and no product surface.

Adjudication under which it was captured: Sol P1 NATURAL-RUN ADJUDICATION,
2026-08-21 — "Do not substitute `n_candidates=145`, health=`ok`, workflow
success, or aggregate row counts for this reconciliation."

---

## 0. Immutable pointers

| Thing | Value |
|---|---|
| Workflow run | [32460910383](https://github.com/mastermindx-market-intelligence/macro/actions/runs/32460910383) (`asia-close`, event `schedule`) |
| Run head SHA | `1ab485789d446d202c8da600edb81f6416e8871f` |
| Run conclusion | `success`; **`asia` job** `success` (08:45:24Z → 10:36:17Z) — a real lane, not a gated-off no-op |
| Natural collection commit | `324c9ca7ab989794810579d40a35b83c5e78f9e5` — `data: asia collection 2026-08-21` |
| Natural engine commit | `927fb6a780466c9a0c7b21cecd9f8c7dcf463d9a` — `engine: asia dashboards 2026-08-21` |
| P1-R1 under test | PR #6142, squash `650be4dfe6d5dff774abdc5b5cfee083aaa11596` |

Ancestry verified with `git merge-base --is-ancestor`:
`650be4df` ⊂ run head `1ab48578`; `650be4df` ⊂ collection commit `324c9ca7`;
collection commit `324c9ca7` ⊂ engine commit `927fb6a7`. The page proved below
is therefore rendered from this run's own collection.

## 1. Same-invocation execution order (run log, `asia` job 96713913690)

```
09:13:49.6808950Z  collect INFO === running china_filings ===
09:13:49.6813540Z  collect INFO === running china_einteraction ===     <- other host group, same instant
09:21:50.1195250Z  china_filings WARNING exchange=sse  hit 480s budget at page 215/290 — keeping 6450 partial rows
09:29:53.1968500Z  china_filings WARNING exchange=szse hit 480s budget at page 226/291 — keeping 6780 partial rows
09:29:55.1579610Z  china_filings INFO 13230 raw rows collected, 2860 net-new stored ({'sse': 6450, 'szse': 6780})
09:29:55.1700800Z  collect INFO china_filings -> ok (1 rows, last 2026-08-21) [965.5s]
09:29:55.1718800Z  collect INFO === running china_visits ===           <- 2.0 ms after china_filings returned
09:29:55.1889610Z  china_visits INFO china_visits: 145 candidate rows, 145 net-new stored
09:29:55.1939000Z  collect INFO china_visits -> ok (1 rows, last 2026-08-21) [0.0s]
09:29:55.1940010Z  collect INFO === running china_irm ===
09:37:30.1007360Z  create mode 100644 data/china_visits/visits.parquet
```

Four things this proves, in the production process:

1. **Same cycle.** `china_visits` began 2.0 ms after `china_filings` returned, in
   the same `collect` invocation — the P1-R1 contract.
2. **Registry order held live**: `china_filings → china_visits → china_irm`
   inside the `cninfo` host group.
3. **Zero network.** `china_visits` cost `[0.0s]`; it is an ordering member of
   the group, not a second CNInfo ingester.
4. **CNInfo concurrency intact.** `china_einteraction` (a different host group)
   started at the same instant as `china_filings`; the nightly-timings line
   reports "concurrent host-groups overlap" with the collector band at 50.8 m
   against 52.1 m of summed adapter time. C0 was not serialized or lengthened.

## 2. Health, as persisted at the collection commit

`data/china_visits/health.json`

```json
{"status": "ok",
 "detail": "145 candidate row(s) this run",
 "last_attempt_utc": "2026-08-21T09:29:55.187926+00:00",
 "last_success_utc": "2026-08-21T09:29:55.187926+00:00"}
```

`data/china_visits/coverage.json` → `{"coverage_start": "2026-08-20"}` — stamped
once on first light, not rewritten by this run.

**Upstream filing health, stated honestly.** Both exchanges hit the 480 s
per-exchange page budget (`sse` 215/290, `szse` 226/291) and kept partial rows.
Budget truncation is deliberately *not* a degradation signal in
`china_filings.LAST_RUN_OUTCOME` (the 3-day re-pull heals the tail), so
`ok: True` propagated and `china_visits` typed the run `ok` rather than
`upstream_degraded`. That is the frozen design, and it is a statement about
**upstream page coverage**, not about the candidate→visit contract: every filing
that *did* arrive in this invocation is accounted for below.

## 3. The 145-candidate reconciliation

Source of truth: `data/china_filings/filings.parquet` @ `324c9ca7` filtered
exactly as the collector filters it (`category == "institutional_visit"`,
`collectors/china_visits.py`), reconciled against
`data/china_visits/visits.parquet` @ the same commit. Per-candidate rows:
[`p1_candidate_reconciliation_2026-08-21.tsv`](p1_candidate_reconciliation_2026-08-21.tsv)
(145 data rows, one per candidate).

| Quantity | Count |
|---|---|
| Candidates (`category=institutional_visit`, post-run store) | **145** |
| Distinct `announcementId` among them | 145 (no duplicates) |
| Candidates with a falsy/absent `announcementId` | **0** |
| **`represented_downstream`** (present in the visit plane) | **145** |
| **`named_typed_exclusions`** | **0** |
| Unrepresented for any other reason | **0** |
| `represented_downstream + named_typed_exclusions` | **145 == 145** ✅ |

Origin split (Sol requirement 4):

| Origin | Count |
|---|---|
| Newly persisted in this invocation | **145** (every row stamped `system_recorded_at = 2026-08-21T09:29:55.173073+00:00`) |
| Valid pre-existing append-only rows | 0 — `data/china_visits/visits.parquet` did **not exist** at the parent commit `6590e678c604`; this run created it (`create mode 100644`) |
| Visit-plane rows with no current candidate (orphans) | 0 |

Freshness split — the number that actually falsifies the one-cycle latency:

| Filing cohort | Count | Represented in the same invocation |
|---|---|---|
| Filings **new in this run's own store delta** (2,860 net-new filings overall) | **72** | **72 / 72** |
| Filings carried from the 2026-08-20 bootstrap night | 73 | 73 / 73 |

**Zero next-cycle deferrals.** All 72 institutional-visit filings that this
invocation itself fetched became `china_visits` rows in that same invocation.
The 73 that the bootstrap night structurally could not surface
(`DSC:CHINA-VISITS-FIRST-CYCLE-ZERO-IS-BOOTSTRAP-NOT-QUIET`) were surfaced in
the same run — 72 + 73 = 145, and that DSC's armed falsifier
(`n_candidates >= 68`) is satisfied at 145 without being treated as acceptance.

Classifier-loss cross-check (the amplification note on that DSC): of the 2,860
filings new in this run's delta, **72** titles raw-match the
`institutional_visit` keyword family (投资者关系活动记录表 / 特定对象调研 /
分析师会议 / 业绩说明会 / 调研) and **72 of 72** are stored
`category=institutional_visit`. Zero filings were lost to a higher-priority
category this run.

### Residual risk, named and NOT repaired

`collectors/china_visits.py` drops a candidate whose `announcementId` is falsy
with a bare comprehension guard (`... for f in candidates if f.get("announcementId")`)
— there is no typed exclusion, no counter, and no health note for that path. On
this run it fired **zero** times (0 of 145), so the reconciliation is exact and
the falsifier passes on the evidence rather than on the absence of a hole. The
hole is real for a future run. Per Sol's instruction — *"Do not independently
widen the implementation"* — nothing was changed. Recorded as
`DSC:CHINA-VISITS-UNTYPED-ANNOUNCEMENT-ID-DROP` for Sol's ruling.

## 4. Production product acceptance

Surface: <https://www.mastermind-x.com/china_intel.html> § *Institutional visits*
(`templates/china_intel.html.j2` K2c), served from engine commit `927fb6a7`,
loaded **anonymously** — no credential entered, read, or synthesized.

| Requirement | Evidence |
|---|---|
| Desktop crop | `verify_shots/china_p1_visits_desktop_2026-08-21.png` (1280 px viewport, 2× DPR) |
| Mobile crop | `verify_shots/china_p1_visits_mobile_2026-08-21.png` (375 px viewport, iPhone UA) |
| Real covered company, block populated | **601328.SS 交通银行** — "2026-08-20 · earnings briefing" / "first seen since coverage start (2026-08-20)" |
| Coverage semantics visible | Section subhead "Investor-relations visit filings · coverage begins 2026-08-20"; every card repeats the coverage-start date |
| Truthful null semantics | The other 14 cards read "No investor-relations visit filings since coverage start (2026-08-20)." — a measured null in plain words, never a bare zero |
| No fabricated visitor identity | "Visitors not yet identified in the filing" — `visitor_raw`/`visitor_class` are both `not_yet_available`, never guessed from the title (RUL-4 holds; PDF bodies are still never fetched) |
| No score / rank / directional treatment | The block reuses the discovery-card idiom with no score, no rank, no directional hue — descriptive only |

## 5. Production capability statement

As of 2026-08-21, the China dossier states, for each name in the China Command
List, whether a CNInfo investor-relations visit-class filing exists for that
company since coverage began on 2026-08-20 — derived within the same Asia-close
invocation that fetched the filing, from CNInfo filing metadata only, with the
filing's own publication date as its point-in-time clock. It reports the visit's
date and plain-word filing kind; it does **not** claim who visited, and says so
on the card. A name with no such filing is shown as a measured null against a
stated coverage start; an upstream refresh that degrades is typed
`upstream_degraded` and suppresses the absence claim rather than presenting a
quiet tape. Nothing in this plane is scored, ranked, or given a direction.

## 6. What this receipt does not claim

- Not a claim about visit filings before 2026-08-20 — coverage is forward-only
  and no backfill exists or is planned.
- Not a claim of complete CNInfo page coverage for 2026-08-21: both exchanges
  truncated on the 480 s page budget (§2), healed by the 3-day re-pull.
- Not a claim about visitor identity, and not a signal — P1 is a tape.
