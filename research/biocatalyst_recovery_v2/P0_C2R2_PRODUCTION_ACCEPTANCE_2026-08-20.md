# P0-C2R2 production acceptance — BioCatalyst entitled hydration

**Date:** 2026-08-20
**Probe window:** 12:18:03Z–12:29:30Z
**Scope:** entitled production proof of merged #6052. No P1 parity, no UI redesign, no source-roster change, no ContractRegistry reuse, no JWT minting/printing/persistence.

#6052 squash: `427d676de1a3ba086e4b63480018ecd733dd666e` (`Retain request-local validated BioCatalyst artifacts after the generation proof.`). Adversarial review verdict was **PASS**. The author's original `DO NOT MERGE` hold was released in PR comment `5355409048` before squash-merge at 12:15:14Z.

## Conclusion

BIOCATALYST P0 — PROVEN_LIVE

A real entitled Chrome session against the deployed production process (`macro-api` MainPID **2529475**, `/api/health.commit` **427d676de1a**) completed the primary `_read_bundle()` journeys with HTTP **200**, real nonzero Trial Screen rows, and no EdgeOne 524. Unsigned callers remain HTTP **401**. Invalid-sort discriminator remains HTTP **400** in 352 ms.

This closes the 2026-08-18 P0-C2 generation-read hang (`P0_C2_ENTITLED_PRODUCTION_ACCEPTANCE_2026-08-18.md`) and the 2026-08-19 `DEEP_VALIDATION_AMPLIFICATION` profile (`P0_C2R0_PUBLIC_GENERATION_READ_PATH_PROFILE_2026-08-19.md`) on the live path. It does **not** mean BioCatalyst product parity is complete. The visible workbench is still the current ClinicalTrials.gov 4-NCT cohort. Post-P0 slices require a separate Sol commission.

## Serving identity

| Item | Value |
|---|---|
| GitHub squash of #6052 | `427d676de1a3ba086e4b63480018ecd733dd666e` |
| production `/api/health.commit` (running process) | `427d676de1a` |
| production `/api/health.checkout` at restart | `427d676de1a` (later skip-ci ticks advanced checkout; process did not) |
| `macro-api` MainPID | **2529475** (prior PID **2348523** on commit `c8e5638dbc3`) |
| restart | `update.sh` MACRO_API_RESTART_TRIGGER matched `engine/biocatalyst/*.py`; journalctl shows stop of 2348523 then start of 2529475 |
| live bytes | `/opt/macro/engine/biocatalyst/publication.py` contains `class ValidatedGenerationArtifacts` and `def _materialize_validated_generation` |
| public generation | `ctgov_run_20260820T120032611932Z_e679bb3d2518` |
| schema | `1.6.0` / `coverage_class=current_only` / configured **4** / observed **4** |
| NCT cohort | `NCT04528082`, `NCT05020236`, `NCT06602479`, `NCT07218380` |
| published_at | `2026-08-20T12:00:33.210681Z` |
| source dataset | ClinicalTrials.gov `2026-08-19T09:00:06` |
| health.state | `fresh` |
| live `biocatalyst.js` | `/biocatalyst.js?v=4b52db10` HTTP 200 (resource timing) |

`commit` is the process under test. Later `checkout` movement is skip-ci main and does not reload uvicorn.

## Authentication

Drive method: operator Google Chrome already signed into `www.mastermind-x.com`. Page-world script used the production `withAuth` shape (`MDXAuth.client().then(client => client.auth.getSession())`) and recorded only booleans (`hasToken`, `hasUser`, `featuresSiteFull`). No access token, cookie, email, name, or user id was printed, persisted, or committed.

| Probe | Result |
|---|---|
| signed-out `GET /api/biocatalyst/v1/health` | HTTP **401** 0.71s `{"detail":"missing bearer token"}` `Cache-Control: private, no-store` `Vary: Authorization` |
| signed-out screen / milestones | HTTP **401** same fence |
| entitled `GET /api/me` | HTTP **200** 2459 ms; `features` contains `site_full`; `Cache-Control: private, no-store` |
| entitled invalid sort `GET /api/biocatalyst/v1/trials?sort=__P0C2_INVALID__` | HTTP **400** 352 ms `{"detail":"invalid sort"}` `private, no-store` `Vary: Authorization` |
| signed-in unentitled | **not live-probed** this window |
| auth-bootstrap failure | **not live-probed** this window |

## Entitled API matrix (PID 2529475)

All times are Chrome `fetch` elapsed on the entitled tab. Origin access log lines completed on MainPID **2529475** (uvicorn writes that line when the request finishes).

| Surface | HTTP | ms | Payload |
|---|---:|---:|---|
| `/api/me` | **200** | 2459 | `featuresSiteFull=true` |
| `/api/biocatalyst/v1/health` | **200** | 4561 | `state=fresh` `coverage 4/4` `schema=biocatalyst_api.v1` |
| `/api/biocatalyst/v1/trials:screen?limit=25` | **200** | 6564 | **4 rows**; first `NCT05020236`; matched 4/4 |
| `/api/biocatalyst/v1/trials:screen/facets` | **200** | 7927 | 3 facet dimensions; matched 4/4 |
| `/api/biocatalyst/v1/trials/milestones?limit=25` | **200** | 5226 | **0 rows** (lawful empty for default `next_90d` / `primary_completion` on this 4-NCT cut) |
| `/api/biocatalyst/v1/trials/change-tape?limit=25` | **200** | 6210 | **25 rows** |
| `/api/biocatalyst/v1/trials/prospective-changes?limit=25` | **200** | 4846 | **0 rows** (schema 1.6.0 `baseline_not_established`) |
| invalid sort discriminator | **400** | 352 | `invalid sort` |
| `/api/biocatalyst/v1/trials/NCT05020236` | **200** | 4715 | covered dossier |
| `POST /api/biocatalyst/v1/trial-peer-sets:resolve` `{NCT05020236, NCT00000001}` | **200** | 5243 | exact-cohort: requested 2 / covered 1 / uncovered 1 |

No 524. No 5xx. All entitled BioCatalyst responses carried `Cache-Control: private, no-store` and `Vary: Authorization, Accept-Encoding` (400 discriminator: `Vary: Authorization`).

Page-init resource timing for the default milestones request after deploy: `/api/biocatalyst/v1/trials/milestones?...` **7685 ms HTTP 200** (PID 2529475 at 12:20:36Z). That is the first live entitled `_read_bundle` 200 since the 08-18 524 matrix.

## Browser journey

| Step | Result |
|---|---|
| default URL (`field=primary_completion&window=90`) | workspace `data-state=empty` then stays empty because milestone rows are 0; **not** `source_outage`; API 200 |
| `?mode=screen` | workspace `data-state=ready`; visible rows include NCT05020236 (Pfizer, Phase 3, Multiple Myeloma), NCT06602479 (AbbVie, Phase 2, Migraine), NCT07218380 |
| dossier API | covered trial NCT05020236 HTTP 200 |
| Peer Matrix API | exact-cohort uncovered NCT00000001 (not in live generation) + covered NCT05020236 |
| unsigned control after deploy | still 401 |
| language switch / back-forward / refresh | **not fully driven** this window |
| pageerror / unexpected console | none observed on the resource timeline; no generic “Registry page unavailable” |

A CGWindow screenshot was not captured (host `screencapture` TCC denied this agent). The bound substitutes are: page `innerText` of the ready Trial Screen, Chrome resource timings with HTTP status, and uvicorn completion lines on PID 2529475.

## Performance vs EdgeOne ~30 s

Isolated entitled `_read_bundle` routes completed in **4.5–7.9 s**. Default init is one milestones read (~7.7 s). Trial Screen URL fires screen + facets; sequential entitled pair here was 6.6 s + 7.9 s. No request approached 30 s. A further ContractRegistry process-lifetime PR is **not** required to call this P0 packet green.

## Rollback

`git -C /opt/macro log` / squash parent of `427d676de1a` is the pre-repair main. Revert the squash (or restore `engine/biocatalyst/publication.py` to #5934) and let `macro-update` restart `macro-api`. Unsigned 401 and invalid-sort 400 do not depend on this repair.

## Explicit non-claims

- BioCatalyst is not a BioPharmCatalyst-parity product yet.
- Source soak (`2026-08-12`→`2026-08-26`) and `biopharmcatalyst_jv_snapshot` runtime registration were not touched.
- BCI #5821 remains draft architecture.
- Agent OS work identity for this program is still the in-flight records PR #6079; this packet does not mint a second workstream.
