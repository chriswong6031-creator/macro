# MomoEdge browser companion — observe-only runbook

## Status and boundary

This companion is **observe-only**. It preserves private evidence needed to
freeze a future producer contract, but it is not a producer and cannot count a
capture as cohort coverage. It does not import or write the prospective NBBO
cohort registry, event ledger, capture ledger, or unavailable-cycle runner.
Every envelope and journal fixes `coverage_eligible=false` and every authority
flag to false.

The extension uses an already authenticated user tab at
`https://momoedge.ai/terminal` or `https://momoedge.ai/terminal.html` (the two
current paths serve the same terminal asset). It never logs in and never reads, copies,
serializes, or persists cookies, browser storage, passwords, tokens, request
headers, response headers, or authentication objects. Authentication remains
inside the page's own runtime.

## Topology

```text
Chrome user session
  -> origin-scoped MV3 service worker (300-second grid)
  -> MAIN-world temporary fetch wrapper around one loadSignals() call
  -> exact matched 2xx response body/status + request/response clocks
  -> Chrome Native Messaging (no localhost port or local bearer)
  -> /Users/chriswong/options-nbbo-ops-wt/scripts/momoedge_browser_receiver.py
  -> /Users/chriswong/.mastermind_private/momoedge_browser_observe_v1
```

The native host and private root are deliberately separate from the future
cohort producer. A later reviewed integration may consume a frozen projection;
this slice must not be wired into that path.

## What constitutes a fresh observation

The page bridge installs a temporary `window.fetch` wrapper, invokes the public
`window.MomoEdge.signals.loadSignals()` runtime, and restores the original
function in `finally`. A response is accepted only when all of these hold:

- exactly one GET targets the frozen signals origin and `/rest/v1/signals`;
- the only query parameters are the exact active plus source-defined
  today-closed predicate and `order=sort_order.asc`;
- the decoded cutoff exactly matches the page's lexical source contract for the
  current New York date: `T00:00:00-04:00` in March through November and
  `T00:00:00-05:00` in December through February;
- the response is 2xx, strict UTF-8 JSON, within 600,000 bytes, and an array;
- every row has a unique source ID, boolean lifecycle state, exact issued clock,
  and every closed row has an exact closed clock at or after that cutoff;
- the page runtime IDs exactly reconcile to the response and no fallback row is
  present;
- no normalized sensitive key occurs at any depth; and
- the original fetch function was restored.

A cached runtime array, retained browser-storage fallback, DOM card, missing
tab, login wall, timeout, 401, malformed/oversized body, second matching
request, or schema drift records `unavailable`. Absence is never interpreted as
zero calls. DOM cards are not a lifecycle-clock source.

### Frozen source cutoff limitation

The public bundle inspected on 2026-08-12 for this contract was
`https://momoedge.ai/dist/terminal.min.js?v=momoedge-v5.537`, SHA-256
`8e50889204ca52795e4c9b7bfd51758f93c585427e103c6b3e65827c1812f553`
(ETag `e9ae463acfeab968fc8ed7e23eb21e5b-ssl`). Its `loadSignals()` derives the
calendar date in `America/New_York`, but chooses the UTC offset by month rather
than by the real DST transition date. The observer therefore binds the exact
source string as `source_closed_cutoff_at` and fixes
`complete_new_york_day_proven=false`. Equivalent timestamp spellings are
rejected. March and November transition windows are not evidence of complete
New York-day coverage.

## Private evidence

The receiver validates the envelope again and rejects duplicate JSON keys,
non-finite values, clock disagreement, duplicate signal IDs, sensitive keys,
and unexpected fields before any response body is written.

- Directories are owner-only `0700`; files are owner-only `0600`.
- Symlinks, foreign owners, hardlinks, broad/repository/cohort roots, mode drift,
  and unknown staging shapes fail closed.
- Exact source bodies are content-addressed below `raw/sha256/` and never enter
  Git or a public artifact.
- `journal/` contains a debranded projection: domain-separated stable ID hash,
  source-row hash, active/closed clocks, ticker/direction, and exact option
  root/type/right/strike/expiry/premium fields when supplied.
- A slot is immutable. Exact retries are idempotent; different bytes for the
  same slot create only a bounded metadata receipt in `quarantine/` and fail.
- Native Messaging is bounded to 950,000 bytes. ACK is written only after raw
  and journal objects and their parent directories have been fsynced.
- Browser delivery retries the exact same envelope once when the ACK is missing,
  which repairs an interrupted raw or journal link without inventing new clocks.
- If both native deliveries fail, the absent five-minute journal is an explicit
  transport gap. The extension stores no browser-side queue or authentication
  state, so that slot is never backfilled or interpreted as unavailable,
  zero-call coverage, or producer coverage.
- Storage stops rather than deletes evidence at 10,000 raw objects / 5 GB,
  20,000 journals, or 1,000 quarantine receipts. Archival is an operator action.

## Install on the local Mac/M1

Install only from a clean dedicated checkout at
`/Users/chriswong/options-nbbo-ops-wt` whose commit is the companion merge or a
verified descendant.

1. Confirm `ops/native_messaging/run_momoedge_browser_host.sh` is executable and
   the configured Python exists at
   `/opt/homebrew/Caskroom/miniconda/base/bin/python`.
2. Create
   `/Users/chriswong/Library/Application Support/Google/Chrome/NativeMessagingHosts`
   as the user, mode `0700`, then copy
   `ops/native_messaging/com.mastermind.optionsnbbocohort.momoedge_observe.json`
   there as mode `0644`.
3. In `chrome://extensions`, enable Developer mode and choose **Load unpacked**
   for `/Users/chriswong/options-nbbo-ops-wt/browser/momoedge_capture`.
4. Verify the displayed extension ID is
   `hgplipfmplcbbkjmhaijacaanmiljfdi`. The committed manifest contains only the
   public key that fixes this ID; no private signing key exists or is required.
5. Open `https://momoedge.ai/terminal` and authenticate manually. Keep that
   subscribed page open. The first attempt occurs on the next five-minute grid.

Steps 3 and 5 are unavoidable user-controlled browser actions. Login/session
consent cannot be automated. Session expiry requires the user to authenticate
again; intervening slots remain unavailable.

## Verification and rollback

After a grid boundary, verify the private root and newest journal locally. A
fresh journal must include the exact raw digest and byte count, precise request
and response clocks, `coverage_eligible=false`, and all-false authority. Closing
the tab or signing out must yield unavailable evidence when Chrome can still
reach the native host.

Rollback is simply disabling the unpacked extension or removing its user-level
Native Messaging manifest. This stops future observations; it does not delete,
rewrite, backfill, arm, or promote existing private evidence.

## Gate before any future producer integration

Do not arm from this observe-only history. First verify live authenticated bytes
prove the full active plus today-closed universe, pagination/completeness, exact
issued and closed clocks, and exact option contract fields. Then freeze the
source schemas and mapping-rule digests in a separate reviewed PR. Accrual begins
prospectively after that merge and installation; observe-only rows are never
retrospectively eligible.

That later gate must independently repair or prove the source's March/November
transition-day completeness. The observe-only `source_closed_cutoff_at` receipt
cannot satisfy that gate by itself.
