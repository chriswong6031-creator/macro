# Capital Structure W2B carrier-capacity qualification — 2026-08-23

This receipt is the mandatory W2B-0 stop/go gate. It qualifies one capacity
change on the existing natural `daily.yml` collector carrier. It does not
authorize another SEC source, queue, store, cadence, job, carrier, publication
plane, identity rule, or authority plane.

## Exact bases

- `main_at_start`: `f3f618c2c783b2d8604036e54f79b1c553b2e0a6`
- W2A implementation PR/head/merge: `#6220` /
  `5c2c7b4a5b611dc6f6fc8e685a6a59ef7f930ce5` /
  `7ea3dc5b421d081a7b04d3cc670a89b915e320a9`
- W2A closeout PR/head/merge: `#6282` /
  `7992f532027f9e2e04ca0481e9dff69283e9c247` /
  `df11f6757e3db82e98be18f46ffe0cb6327f919d`
- first natural W2A proof: `daily.yml` run `32603557988`, checkout
  `fa73271632a7cf5eb214e4e68bdfcb96c22422b0`, collect job `97105275976`,
  Capital Structure job `97119200594`
- natural W2A generation: `73d9810fe3f94fc8c3aafaa9b1716ff100aa1e17`
- protected Sol Skillpack pin loaded atomically from Mastermind/master:
  `db0bac5fe3f72348262d42c8bd26b836bda9f61d`

No newer Capital Structure owner decision, implementation, open pull request,
or generation changes the W2A capacity finding at this base.

## Latest completed-session capacity census

The eight pre-W2A completed-session policy-discovery cohort counts were `334,
353, 446, 485, 217, 190, 229, 199`. The first natural W2A run completed the
2026-08-21 session and its receipt reported 202 current-run LIVE arrivals. The
resulting conservative latest-nine capacity census is:

| Statistic | Value |
| --- | ---: |
| counts | 334, 353, 446, 485, 217, 190, 229, 199, 202 |
| p50 | 229.0 |
| p90 | 453.8 |
| p95 | 469.4 |
| maximum | 485 |
| newest | 202 |

No newer completed session exceeds the commissioned 500-arrival envelope. The
envelope therefore remains an observed-production bound, not a claim that SEC
can never publish more than 500 policy-discovery rows in a session.

The maximum raw cohort is materially unbalanced across the seven retrieval
lanes: issuer_periodic 190, issuer_current_report 168, prospectus 82, state 19,
registration 13, issuer_proxy 8, and reg_a 5. An anchor-correct replay retained
the full preceding discovery history needed by issuer reconciliation. It found
484 of the 485 raw rows policy-eligible and selected all 484 with the unchanged
W2A scheduler; one unanchored raw issuer row was correctly excluded before the
queue and was never an admitted LIVE arrival. A contrary 204-of-485 replay was
rejected because its reduced discovery fixture had removed those older issuer
anchors. W2B therefore requires no scheduling change: it changes capacity only.
The hostile unit fixture conservatively makes all 485 rows policy-eligible and
proves all 485 land while RECOVERY and HISTORICAL retain protected service.

## Natural cap-200 baseline

The existing timing ledger and GitHub job receipts report:

| Run | runner | collect wall | `sec_capital_structure` | collect cap |
| --- | --- | ---: | ---: | ---: |
| 32426513915 | mac-builder-5 | 146.5m | 1,201.5s | 240m |
| 32534736736 | mac-builder-5 | 137.5m | 1,291.6s | 240m |
| 32603557988 | mac-builder-5 | 126.0m | 994.2s | 240m |

For the qualifying natural W2A run, the 126.0 minutes were startup 386s,
collectors 6,988s, market-commit-push 138s, and R2 publish 47s. The existing
last step invokes `scripts/ci/nightly_timings_finish.sh 240`, which records the
same timing ledger and emits the established warning above 85% of the 240-minute
cap. The warning boundary is 204 minutes.

## SEC request and storage behavior

- `MAX_FILINGS_PER_RUN=200` was the natural baseline. The adapter is serial,
  sleeps `PACE_SECONDS=0.12` after each filing attempt, sends the configured
  identifiable email-bearing SEC User-Agent plus `gzip, deflate`, and adds no
  concurrency at 540.
- Daily-index reads use one attempt with a 30-second timeout. Submission reads
  use three attempts with a 60-second timeout and the shared 3s/6s exponential
  sleeps between attempts.
- The natural run had one SEC filing HTTP 404. It made three attempts, paid the
  3s and 6s retry sleeps, and became a visible transient retrieval failure. It
  had zero SEC 429 responses and zero SEC rate-limit responses.
- The `HTTP 403 AccessDenied` was not SEC behavior. It came from the dedicated
  `r2_capital_structure` write/readback probe. The already-existing deterministic
  fallback selected `r2_research` about 0.904 seconds after that probe failed.
  Successful filings were retained there; W2B does not change this fallback.
- Current official SEC policy caps automated access at 10 requests per second
  in aggregate and asks automated clients to identify themselves. The unchanged
  serial 0.12-second pacing alone bounds the no-latency attempt rate below that
  ceiling; observed end-to-end filing work is materially slower. Raising the
  bounded row count changes run duration, not request rate.

Official policy read during qualification:

- `https://www.sec.gov/about/developer-resources`
- `https://www.sec.gov/about/privacy-information`
- `https://www.sec.gov/about/webmaster-frequently-asked-questions`

## Bounded cap-540 projection

The conservative projection uses the slowest of the latest three natural
cap-200 collector runtimes rather than the faster qualifying run:

1. slowest recent per-filing baseline = `1,291.6s / 200 = 6.458s`;
2. cap-540 SEC band = `6.458s * 540 = 3,487.32s = 58.122m`;
3. worst recent non-CS collect work = `146.5m - 1,201.5s = 126.475m`;
4. conservative whole-collect projection = `126.475m + 58.122m = 184.597m`.

| Budget boundary | Projected use | Remaining headroom |
| --- | ---: | ---: |
| existing 85% warning, 204m | 184.6m (90.5%) | 19.4m |
| existing hard cap, 240m | 184.6m (76.9%) | 55.4m |

The first percentage is use of the 204-minute warning budget; the second is use
of the 240-minute hard cap. No timeout, watchdog, schedule, runner label, or
carrier change is required or authorized.

The downstream Capital Structure job is also observed rather than hidden: its
latest wall time was 65.0 of 90 minutes and its direct-document compiler was
63m27s. That compiler revalidates all 550 existing fee-form roots and processed
57 new roots in the natural run. A read-only replay of the exact current queue
under the unchanged W2A scheduler selects the same 57 fee-form roots at cap 200
and cap 540; the current-state downstream delta is therefore zero.
Conservatively, the 65.0-minute observed job baseline remains 11.5 minutes below
the existing 76.5-minute warning line and 25.0 minutes below the 90-minute hard
cap. The natural proof
must report both job runtimes and existing 85% tripwires; a timeout or a new
resource-bound breach is a W2B failure, not permission to add a carrier.

## Verdict and falsifiers

`W2B-0: PASS` for exactly one configuration change:

- global retrieval ceiling 540;
- `LIVE_TAIL=500`, `RECOVERY=20`, `HISTORICAL_BACKFILL=20`;
- global ceiling derived from that one reservation map.

This qualification is falsified if a completed session admits more than 500
LIVE arrivals, SEC starts returning pacing/rate-limit responses under unchanged
pacing, collect reaches its existing 85% warning or hard cap because of the
capacity change, a runner resource bound is breached, or the downstream
generation fails to compile/publish. A falsifier returns to Sol. It does not
authorize a larger cap, second daily, new source, new carrier, weaker fence, or
easier freshness claim.
