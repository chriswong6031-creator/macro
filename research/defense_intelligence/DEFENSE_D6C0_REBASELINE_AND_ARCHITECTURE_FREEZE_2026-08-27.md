# D6-C0 — Remaining-rail rebaseline and architecture freeze

**Operation** `defense-procurement-v3-d6c0-rebaseline-20260827-sol-coo-001`
**Parent program** `defense-procurement-v3-program-control-20260827-sol-coo-001`
**Wave class** records/research only. No runtime, product, data, or source mutation.
**Returns** HOLD-FOR-SOL. This document recommends; it does not authorize.

## 0. Pins, and what moved

| pin | value at pickup | delta vs dispatch |
|---|---|---|
| Macro `main` | `4ac1c60e408f6cd36af5295444ac6f290942e33f` | +2 vs `d84468e41f40` |
| Sol Skillpack repo | `Mastermind@b901dee0272a99b8a1d60385848b99b7273e8261` (branch `master`) | +2 vs `d508e30c` |
| Skillpack **content** | `docs/sol_skills/` byte-identical to `d508e30c` | **unchanged** |

`git diff d508e30c..origin/master -- docs/sol_skills/` is empty; the two Mastermind commits
touch `docs/superpowers`, `ops/executive_os`, and `tests/test_c1_installer_control_config.py`
only. The protected skillpack surface did not move. Mastermind's default branch is `master`.

Neither Macro commit (`61f2f7eeb8cb` gh-quota guard shape 7, `4ac1c60e408f` Market Memory
MM-G0 records) touches any Defense/GovRev path.

## 1. Method and its bounds

Archaeology was read-only and ran against current `main` `4ac1c60e408f`. This worktree is a
sparse checkout (`data`, `site`, `mockups`, `verify_shots` not materialized), so artifact
claims were read from the git object store via `git ls-files` / `git show` rather than from
working-tree files. That is stated at each claim that depends on it.

Every null in this document was positive-controlled before it was trusted:

| instrument | positive control | result |
|---|---|---|
| `gh pr list --json files` | PR 6587=3 files, 6586=4, 6585=8 | populated, so a Defense null is real absence |
| `git ls-files data/` in a sparse tree | 35 `fms_*`/`dod_budget_*` artifacts listed | lists omitted trees, so an SBIR null is real absence |
| filename+content grep for rails | `fms` returns workflow+DEC+handoffs+collectors+contract+data | fires on a known-present rail |
| HTTP feasibility probe | **FAILED its control — see §5** | conclusions from it are void and were withdrawn |

## 2. Capability ledger — remaining D6 rails

Read against current main, not against the 2026-08-16 plan. One rail the plan treats as
remaining is in fact built.

| rail | status | evidence |
|---|---|---|
| SBIR / STTR progression | **DARK_OR_DISCONNECTED** | collector + engine + full registration exist; zero artifacts, zero consumers, zero contract files (§3) |
| DoD / service contract announcements | **REJECTED_BY_DESIGN** (as population authority) | D0R registry row 13: "Public news, not a ledger", "publication date ≠ obligation", "miss ≠ no award" → verdict **ADAPT join-only** |
| GAO protest / program assessment | **NOT_BUILT** | zero tracked files; zero content hits outside an allowlist mention |
| DOT&E / IG findings | **NOT_BUILT** | zero tracked files; zero content hits |
| DLA / DIBBS industrial demand | **NOT_BUILT** | zero tracked files; D0R verdict **DEFER** ("noisy") |
| DIU / AFWERX / OTA | **SPEC_ONLY** | D0R verdict **RESEARCH_ONLY** ("prototype ≠ P&P") |

Absence bounds: filename grep over the full tracked-file list, plus content grep for
`gao.gov|bid.protest|dote.osd|dot&e|dodig|oig\.|dla.mil|dibbs|defense.gov|contracts.mil`
across `collectors/ engine/ scripts/ app/ contracts/ config/ .github/ templates/`. The single
hit is `engine/government_revenue/program_ontology.py:100-101`, which lists `www.gao.gov` and
`www.defense.gov` in a **known-official-domain allowlist**. That is rights preparation, not a
rail: no collector, no artifact, no consumer.

### Substrate the rails would extend (re-read, not re-litigated)

| component | status | evidence |
|---|---|---|
| D6-A DoD budget | PROVEN_LIVE (accepted) | `dod_budget_{line_snapshots,collection_receipts,projection_state}` committed; 24 builder references |
| D6-B FMS | PROVEN_LIVE (Sol accepted) | 83 observations / 83 receipts, `observed_at 2026-08-26T11:01:35Z`, `http_status 200`; 22 builder references; `site/government-revenue-data/fms-cases.json` |

## 3. The SBIR finding — a shipped collector-only wave

This is the load-bearing discovery of the wave, and the reason the dispatch's
"do not assume NOT_BUILT" instruction mattered.

**Built and fully registered** (PR #5012, landed `ec28d15709fe`, 2026-08-09):

- `collectors/sbir_awards.py`, `engine/government_revenue/sbir_progression.py`
- `config/synapse.yml:17269` — declares `data/government_revenue/sbir_award_observations.parquet`, `storage: git`, `freshness_sla_hours: 168`
- `config/dag.yml:3991` — reads/writes five artifacts
- `scripts/collect.py:199` and `:398` — registered adapter, nightly-only set
- `config/append_only_artifacts.json:39` — append-only fence
- `.github/ci/legacy-jobs.yml:9189` — unit suite, run twice

**Produces nothing and is consumed by nothing:**

| declared artifact | tracked in git? |
|---|---|
| `sbir_award_observations.parquet` | **ABSENT** |
| `sbir_collection_receipts.jsonl` | **ABSENT** |
| `sbir_projection_state.json` | **ABSENT** |
| `sbir_ingest_status.json` | **ABSENT** |
| `sbir_collector_heartbeat.parquet` | **ABSENT** |

Nineteen days from landing to this census with zero committed observations against a declared
168-hour freshness SLA. Consumers: zero in `scripts/build_government_revenue.py`,
`scripts/build_government_revenue_candidates.py`, `app/government_revenue.py`, or any site
JS — the only importers are `tests/`. No `site/government-revenue-data/sbir-*.json` exists.

**Contracts declared in code but absent as files.** `collectors/sbir_awards.py:70-74` names
five contracts — `government_revenue.sbir_award_observation.v1`, `.sbir_projection_state.v1`,
`.sbir_collection_receipt.v1`, `.sbir_ingest_status.v1`, `.sbir_coverage_manifest.v1`. None
exists in `contracts/government_revenue/`, which does carry
`government_fms_case.v1.schema.json` for the accepted FMS rail. SBIR's contract is a string
constant, not a validated schema.

**The green is cosmetic.** SBIR's only CI presence is `pytest tests/test_sbir_awards.py`,
added as an unrun-suite backfill (`legacy-jobs.yml:9184`: the lane "landed named by no `run:`
step — the unrun-suite gate reds main on it"). A unit suite over a collector that has never
persisted a row is exactly the "cosmetic green that hides stale/partial coverage" the
dispatch's hard boundaries forbid.

**Why it is dark is NOT established.** A single read-only request to
`api.www.sbir.gov/public/api/awards` from this host returned HTTP 403 `{"message":"Forbidden"}`.
That is suggestive and it is *not* a diagnosis — see §5. The collector is designed so that
"a source failure leaves the accrued ledger, activation state, and status exactly as they
were", so a persistently refusing source and a never-activated collector are observationally
identical from the repository. Resolving which is the first gate of any SBIR wave.

## 4. The page fence — the dispatch figure is correct, and the risk is larger than it reads

The dispatch cites 302,713 B against a 303,104 B fence. That figure is **real and current**,
not stale. I initially measured 277,217 B at HEAD and suspected the dispatch was out of date;
tracing the artifact across its last 60 changes refuted that.

`RAW_HTML_BUDGET_BYTES = 303_104` (`scripts/build_government_revenue.py:118`,
`tests/test_fms_ui.py:39`) is enforced on `site/government_revenue.html` as written.

| commit class | size | headroom |
|---|---|---|
| `govrev: SAM opportunity evidence` (`f5f11112da45`) | **302,890 B** | **214 B** |
| `govrev: SAM opportunity evidence` (`5d9628af92c2`) | 302,713 B | 391 B |
| `render-sync` / `engine-render` (`8229cce709af`, HEAD) | 277,217 B | 25,887 B |
| minimum observed in last 60 changes | 264,727 B | 38,377 B |

The page oscillates by **38,163 bytes** between the live SAM-evidence bake and the render-lane
bake. The fence-relevant number is the **peak, 214 bytes**, not HEAD's 25,887.

**Consequence for architecture, and it is a trap.** A new user-facing rail sized against a
render-lane reading would pass every local check and then blow the fence on the next
`SAM opportunity evidence` commit — an intermittent, lane-dependent failure whose green is
produced by measuring at the trough. Any D6 rail that adds bytes to `government_revenue.html`
must be sized against 302,890 B, or must not land on that page at all. This is independent
support for the roadmap's G2 instruction to shrink/split rather than bump the fence.

## 5. Source feasibility — a withdrawn conclusion, and what replaced it

Read-only HTTP probes from this host returned:

```
403  https://www.gao.gov/bid-protest-docket/search        403  https://www.dote.osd.mil/
403  https://www.gao.gov/legal/bid-protests               403  https://www.dodig.mil/Reports/
403  https://www.gao.gov/api/products                     403  https://api.www.sbir.gov/public/api/awards
200  https://www.gao.gov/rss/reports.xml                  403  https://www.dsca.mil/press-media/major-arms-sales
```

The obvious reading — "these rails are WAF-blocked and infeasible" — is **withdrawn**. The
probe failed its positive control:

```
200  api.usaspending.gov        200  federalregister.gov/api      200  example.com
403  www.dsca.mil               403  www.sec.gov
```

`dsca.mil` and `sec.gov` are sources this repository **provably collects in production**, and
both refuse the same bare probe. Egress is healthy. Therefore a 403 to an unauthenticated
`curl` with a browser user-agent carries no information about whether a source is collectable
by this repo's actual collectors, and every feasibility conclusion drawn from those 403s is
void. What survives is narrower and still useful: **`.mil`/WAF-class official sources refuse
naive server-side acquisition**, so any rail targeting them must budget for the acquisition
discipline below rather than assuming a plain HTTP GET.

### The transferable capability this exposed

`collectors/fms_notifications_live.py` — the accepted, PROVEN_LIVE D6-B collector — already
solves exactly this, and its shape is the reusable asset:

- a `requests.Session()` carrying full browser headers (`User-Agent`, `Accept`,
  `Accept-Language`) for `state.gov` (`:503-507`);
- a **bounded browser-transport archival replay** for DSCA, recorded as
  `transport="browser_in_page_fetch_staged"` (`:255`, `:312`, `:334`), with the fetched objects
  staged and committed under `data/government_revenue/fms_staged_objects/`;
- **the Federal Register API as the population authority** (`FR_API_DOCUMENTS_URL`,
  probe 200, open and machine-readable), with the WAF-protected web surface used only as
  observational enrichment.

That last line is the binding D6-B official-union law expressed as architecture, and it is the
correct lens for choosing the next rail.

## 6. Rail selection under the official-union law

The D6-B law is binding: **web presence is observational, never population authority.** So a
rail is only lawful if it has an *open, machine-readable population authority*; WAF-protected
web may enrich it but may never define its population.

| rail | investor/machine value | open population authority? | correction/PIT | verdict |
|---|---|---|---|---|
| GAO protest | **highest** — adverse events, CICA stay, direct program-delay causality; feeds G5/D13 | **none proven.** Docket is web-only; `gao.gov/rss/reports.xml` (200) carries *reports*, not the protest docket. D0R gate 6 already recorded "DSCA/GAO dockets unverified this close" | revisions exist (good) | **blocked at the law**, not merely at feasibility |
| DOT&E annual | moderate — test risk | none; annual PDF | annual, lagging; next release ~Jan 2027 | cadence cannot demonstrate a live rail this wave |
| DoD/service IG | moderate — adverse | none proven | event | same blocker as GAO |
| DoD contract announcements | low as truth | **explicitly not a ledger** (D0R) | pub date ≠ obligation | D0R already ruled ADAPT join-only |
| DLA / DIBBS | moderate — bottleneck | operational HTML | noisy | D0R already ruled DEFER |
| **SBIR / STTR** | **lowest of the set, stated plainly** | **yes** — documented public API, official Award data dictionary, exact source-native unique key `agency_tracking_number` | observation-bound `known_at`, never backdated; A-B-A reversion retained | **recommended** |

**Recommendation: complete the SBIR/STTR rail from `DARK_OR_DISCONNECTED` to `PROVEN_LIVE`.**

This is deliberately the boring answer, and it is chosen on the dispatch's own scoring
(value × source authority/coverage × correction/PIT feasibility × owner compatibility). It
wins three of four factors decisively and loses the first, and the three it wins are the ones
that are *law-bearing*. It requires no new source rights, no new plane, no new contract family,
no WAF fight, and no page-fence pressure. Above all it repairs the exact defect the completion
law names — "never ship collector-only waves" — using the repository's own live instance of
that defect.

**The honest case against it, stated rather than buried.** SBIR Phase I/II awards are
small-dollar, early-stage, and by the collector's own law "progression evidence only and never
production conversion". No one will trade on an SBIR award. Its value is *graph* value:
earliest observable evidence of industrial-base capability formation, joinable to the reviewed
recipient graph by exact UEI, years upstream of the programs D5 already models. If Sol scores
investor value above architectural lawfulness here, the answer changes — see the flip
condition in §9.

## 7. Proposed wave (frozen shape; NOT authorized by this document)

**Real-data journey.** `api.www.sbir.gov/public/api/awards` (DoD-scoped, paced 63 s/request,
hard cap 8 requests/run, off-render collect lane) → append-only
`sbir_award_observations.parquet` keyed by exact `agency_tracking_number`, with
`sbir_collection_receipts.jsonl` carrying per-request `http_status`/`bytes`/`final_url`/
`observed_at` in the FMS receipt shape → `sbir_progression.py` payload → a **canonical read
model consumed by a real consumer** → production proof.

**Consumer — and the fence.** The consumer must **not** add bytes to
`site/government_revenue.html` (§4: 214 B peak headroom). Two lawful options, for Sol to pick:
(a) a separate `site/government-revenue-data/sbir-progression.json` read model consumed by the
existing dossier/briefcase JS without new page markup, or (b) an off-page consumer only. A
third option — bump the fence — is forbidden by the roadmap's G2 non-goal and is not offered.

**Contracts.** Author the five declared-but-absent schema files under
`contracts/government_revenue/`, mirroring `government_fms_case.v1.schema.json`. Shipping a
sixth undocumented contract string is not acceptable.

**Clocks.** Four separate and never collapsed: source award date, effective, observed_at,
known_at. SBIR.gov publishes no record-publication timestamp, so `known_at` is
observation-bound and **never backdated to the award date** — already the collector's law and
it must survive the wave.

**Nulls.** A row lacking `agency_tracking_number` is counted and refused, never given a
synthesized key. The source publishes no pagination total, so exhaustion is claimed only on a
short page; a filled page cap is recorded as a complete *bounded sample* and displayed as
such. A dark source is displayed as dark, never as zero.

**Corrections.** Append-only with semantic versioning; a re-run never rewrites or deletes
accrued history and must retain an A-B-A reversion. Enforced by
`config/append_only_artifacts.json`.

**Method: deterministic, not statistical.** Exact-key identity, exact-UEI issuer join against
the reviewed recipient graph, deterministic Phase I→II progression from the source's own
phase field. No model, no score, no inference. Authority all-false: no rank, gate, size, entry,
or execution authority; emits no candidates; no Prophet contribution.

**Tests.** Extend `tests/test_sbir_awards.py` with: contract-file validation for all five
schemas; a fixture proving the four clocks stay separate and `known_at` is not backdated; an
A-B-A reversion case; a missing-`agency_tracking_number` refusal case; a bounded-sample-vs-
exhaustion assertion; and a page-fence assertion that the consumer adds **zero** bytes to
`government_revenue.html` measured against 302,890 B, not against HEAD.

**Real production proof.** Not a green suite. A committed
`sbir_award_observations.parquet` with a non-zero row count, a
`sbir_collection_receipts.jsonl` line carrying `http_status: 200` and a real `observed_at`
inside the wave, the derived read model present in `site/government-revenue-data/`, and the
consumer rendering it — the same standard D6-B met with its 83 receipts.

**Gate 0, before any code.** Reproduce the SBIR.gov response *from the runner*, not from a
developer host, using the FMS collector's header discipline. If the source refuses the runner
under documented terms, the lawful outcome is to record SBIR as
**REJECTED_BY_DESIGN with evidence** and return to Sol — which closes a D6 rail honestly and is
a legitimate wave outcome under G1. A blind retry or failover is forbidden.

**Stop condition.** The wave stops at a proven consumer for SBIR observations. It does not
touch Prophet, does not extend the theme/graph engines, does not open D7, and does not add a
second identity, event, budget, FMS, market-data, or Neural Web plane.

**Non-goals.** No page-fence bump. No new source plane. No rank/gate/size/entry/execution
authority. No elapsed-time lifecycle inference. No treating an SBIR award amount as revenue,
backlog, bookings, or funded value. No persistence of PoC/PI names, phones, emails, street
address, ZIP, or abstracts — already the collector's law.

## 8. Collision risk

Zero of 37 open PRs touch any `WS-DEFENSE-PROCUREMENT-V3` `owns_paths` entry. Verified twice
against `origin/main 4ac1c60e408f`, with the instrument positive-controlled.

Two soft adjacencies, neither a rebaseline collision: the `agentos/` records surface (18 open
PRs, add/add only on distinct new filenames), and the Agent OS validator itself
(PRs 6546, 6564 touch `scripts/agentos.py`, `agentos/schema/`, `tests/test_agentos_schema.py`)
— a schema change landing first would move the gate this carrier must pass.

## 9. What would flip the recommendation

Stated so Sol can rule against it cheaply:

1. **An open, machine-readable GAO protest population authority exists** that I did not find —
   a bulk export, a documented API, or a Federal-Register-class publication of protest
   dockets. GAO then outranks SBIR on every factor and should be built instead.
2. **Sol rules that observational web MAY serve as population authority for adverse-event
   rails**, amending the D6-B official-union law. GAO becomes lawful and wins.
3. **SBIR.gov refuses the runner** under Gate 0. SBIR is then recorded REJECTED_BY_DESIGN and
   selection returns to the GAO/DOT&E set under whatever law then applies.

## 10. Boundary of this document

D6-C0 is records/research only. Nothing here authorizes the SBIR wave, and no implementation
rail is self-authorized. D7 is not started. The recommendation is a recommendation.
