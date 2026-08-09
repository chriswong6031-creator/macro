# TuShare add-on live entitlement probes — TP-0 witness (2026-08-09)

**Capture clock:** 2026-08-09, two sequential passes at ~22:2x–22:33 and ~22:38–22:41
Asia/Shanghai (14:2x–14:41 UTC), Mac Studio, local `--execute` runs against
`https://api.tushare.pro`. The second pass re-ran every probe under the exact gate
configuration this PR ships; both passes returned identical verdicts.

**Authority basis used:** `TUSHARE_VENDOR_LICENSE_AUTHORITY=operator_attestation_verified`
with `TUSHARE_VENDOR_LICENSE_AUTHORITY_SHA256=ad48d044c8a763435f232fa81f44908817d04b28eb9bc9e6175e2c06fd6265fb`,
the digest of the operator-authored `research/TUSHARE_ADDONS_COLLECTOR_FOUNDATION_2026-08-09.md`
carrying the 2026-08-09 license ruling.

**Headline: TP-0 is BLOCKED, not answered.** Every probe reached the vendor and was
refused at the credential layer. No endpoint's access, schema, or history depth was
observed. Nothing here upgrades any endpoint's access context, and no partition,
receipt, or byte of paid data was written.

## Per-probe result — every probe is `PENDING_CREDENTIAL_REFRESH`

| # | Endpoint | Ticker | Session | State | Access observed | Rows | Schema vs contract |
|---|---|---|---|---|---|---|---|
| P1 | `stk_mins` (1min) | 600519.SS | 2026-08-07 | `PENDING_CREDENTIAL_REFRESH` | no | — | unverified |
| P2 | `stk_premarket` | 000001.SZ | 2026-08-07 | `PENDING_CREDENTIAL_REFRESH` | no | — | unverified |
| P3 | `stk_auction_o` | 000001.SZ | 2026-08-07 | `PENDING_CREDENTIAL_REFRESH` | no | — | unverified |
| P4 | `stk_auction_o` | 000001.SZ | 2023-03-01 | `PENDING_CREDENTIAL_REFRESH` | no | — | unverified |
| P5 | `stk_auction_c` | 000001.SZ | 2026-08-07 | `PENDING_CREDENTIAL_REFRESH` | no | — | unverified |
| P6 | `stk_auction_c` | 000001.SZ | 2023-03-01 | `PENDING_CREDENTIAL_REFRESH` | no | — | unverified |
| P7 | `stk_auction` (realtime) | 000001.SZ | current | `PENDING_CREDENTIAL_REFRESH` **+ window** | not attempted | — | unverified |

Every one of P1–P6 held at the collector's generic
`trade_cal_unavailable_empty_or_unentitled` reason code — the hold fires on the FIRST
calendar call, so no add-on endpoint was ever reached and no per-endpoint conclusion is
available for any of them.

**P7 has a second, independent blocker.** `stk_auction` (doc 369) is same-day capture
only and the collector clock must satisfy `09:26 <= t < 09:30` Asia/Shanghai. The next
occurrence is **Monday 2026-08-10, 09:26–09:29 Asia/Shanghai**. Even with a working
credential it cannot be witnessed before then, so refreshing the token unblocks P1–P6
immediately but leaves P7 waiting on the clock.

Vendor traffic spent: 12 collector `trade_cal` calls across two passes (the second pass
re-ran under the shipped gate configuration) plus 2 transient diagnostic calls — 14
total. Both passes returned byte-identical verdicts. **Probing then STOPPED**: no probe
was retried after its hold, and no further calls were made once the cause was isolated.

## Re-run recipe (one command per probe, after the token is refreshed)

Set the gate once, then run any subset. `--output-root` must point inside a gitignored
`data/tushare_addons/` root; `--execute` is required or the CLI only plans.

```bash
export TUSHARE_VENDOR_LICENSE_AUTHORITY=operator_attestation_verified
export TUSHARE_VENDOR_LICENSE_AUTHORITY_SHA256=ad48d044c8a763435f232fa81f44908817d04b28eb9bc9e6175e2c06fd6265fb
ROOT="$PWD/data/tushare_addons"

# P1
python -m scripts.collect_tushare_addons stk_mins \
  --trade-date 2026-08-07 --ticker 600519.SS --frequency 1min \
  --output-root "$ROOT" --execute
# P2
python -m scripts.collect_tushare_addons stk_premarket \
  --trade-date 2026-08-07 --ticker 000001.SZ --output-root "$ROOT" --execute
# P3 / P4 — recent session, then deep history for the backfill-depth answer
python -m scripts.collect_tushare_addons stk_auction_o \
  --trade-date 2026-08-07 --ticker 000001.SZ --output-root "$ROOT" --execute
python -m scripts.collect_tushare_addons stk_auction_o \
  --trade-date 2023-03-01 --ticker 000001.SZ --output-root "$ROOT" --execute
# P5 / P6
python -m scripts.collect_tushare_addons stk_auction_c \
  --trade-date 2026-08-07 --ticker 000001.SZ --output-root "$ROOT" --execute
python -m scripts.collect_tushare_addons stk_auction_c \
  --trade-date 2023-03-01 --ticker 000001.SZ --output-root "$ROOT" --execute
# P7 — ONLY inside 09:26-09:29 Asia/Shanghai on the requested day
python -m scripts.collect_tushare_addons stk_auction \
  --trade-date "$(TZ=Asia/Shanghai date +%F)" --ticker 000001.SZ \
  --output-root "$ROOT" --execute
```

The token is read from `TUSHARE_TOKEN` only and must never be echoed, logged, or
committed. A `held_fail_closed` result writes nothing, so a re-run after a failure is
always safe.

## Cause: credential rejection, NOT an entitlement gap

The collector's fail-closed reason code (`..._unavailable_empty_or_unentitled`) is
deliberately generic and does not persist vendor error text, so the cause was isolated
with a transient out-of-band diagnostic that printed HTTP status and the numeric vendor
code only:

- `trade_cal` → HTTP 200, no redirect, **vendor code 40101**
- `stk_auction_o` → HTTP 200, no redirect, **vendor code 40101**

`40101` is the AUTH-class code this repo already documents in
`collectors/tushare_client.py` (`_AUTH_CODES = frozenset({40101})`, "the token VALUE is
rejected, so every endpoint fails identically and no amount of retrying or waiting
helps"). It is deliberately distinguished there from `40203`, which is the
rate-limit/entitlement code. **The observed code is the credential one, not the
permission one.**

**Independently corroborated.** The Lane C session reached the same conclusion
account-wide from this host by a disjoint route: `cyq_chips` (premium) and a control
`trade_cal` (regular, unlimited tier) both returned 40101 through the same `.env`
token. Two lanes, different endpoints, same signature — the credential is dead, not the
entitlement.

The decisive discriminator: `trade_cal` is a REGULAR-tier endpoint that the operator
attestation records as 常规数据无上限 (unlimited). It fails identically to the premium
add-on. An entitlement gap cannot make a regular endpoint the account indisputably
holds return 40101. Therefore:

- **No conclusion may be drawn about `stk_mins`, `stk_premarket`, `stk_auction_o`, or
  `stk_auction_c` access.** Their declared access context is unchanged and no
  `access_observed_at_request_time` observation exists anywhere in the store. The
  licensing question and the *does the credential work right now* question are
  independent: the operator ruling answers the first, and this witness reports that the
  second is currently NO.
- This is the same failure signature as the 2026-07-27 → 2026-08-06 dark period recorded
  in `tushare_client.py`. It has recurred.

Ruled out locally, so the fault is not on this side:

| Hypothesis | Check | Result |
|---|---|---|
| Token missing | env presence | present |
| Token mangled by shell sourcing | raw vs file bytes | identical; 56 chars, hex-only, no CR, no quotes |
| Transport/TLS failure | HTTP status | 200, JSON parsed |
| Redirect swallowed by `allow_redirects=False` | `is_redirect` | False |
| Wrong date / closed session | n/a | never reached — auth precedes calendar semantics |
| Tier-1 gate misconfigured | reason code | gate PASSED; failure is downstream at the vendor call |

**Operator action required:** re-issue or refresh `TUSHARE_TOKEN` (the value in the
project `.env` is rejected as of 2026-08-09 22:41 Asia/Shanghai). P1–P6 then re-run in
under a minute via the recipe above; P7 additionally waits for its Monday window. The
GitHub Actions secret may hold a different value — nightly-lane freshness is being
checked separately, and a working CI secret would make "sync `.env` from the secret"
the fix rather than "re-issue the token".

Nothing else in Lane A is blocked: the gate, contracts, CLI, store lines, and tests all
ship without a live credential, and the sequencing law is satisfied precisely because
the probe receipts do NOT exist — no bulk backfill can start until they do.

## What DID get proved

1. **The attested-license gate works end to end.** Every run passed
   `_license_authority_receipt()` under `operator_attestation_verified` and failed
   downstream at the vendor call. Under the previous single-basis gate they would have
   held at the license check and never reached the network, so the fact that the failure
   is a *vendor* refusal is itself the proof that the new basis opens the path. The
   dormant vendor-authorization allowlist remains empty and unreachable.
2. **Fail-closed holds leave no residue.** `data/tushare_addons/` contains zero files
   after six held `--execute` runs: the collector mutates nothing before clock, calendar,
   schema, and row checks all pass.
3. **No vendor error text, token byte, or raw row entered the repo.** The diagnostic that
   recovered code 40101 ran out of band in a scratchpad and printed a numeric code only.

## History-depth question: UNANSWERED

The takeover doc's §"Sequencing law" asks whether `stk_auction_o` supersedes the §8.5
realtime 09:25 auction-snapshot collector. That question needs the P3/P4 pair (recent
session + deep-history 2023-03-01) to return rows. Both were refused at the credential
layer, so **the supersession question stays open** and the §8.5 collector must not be
retired or descoped on the strength of this witness.

What the official documents (captured 2026-08-09, pinned in the contracts) claim, still
unverified by observation:

- doc 353 `stk_auction_o` — 股票开盘9:30集合竞价数据，每天盘后更新; ≤10,000 rows/request;
  input accepts `trade_date` **and** `start_date`/`end_date`, which is what a backfill
  would need. Requires separate permission authorization.
- doc 354 `stk_auction_c` — 股票收盘15:00集合竞价数据，每天盘后更新; same limits and inputs.

Neither page states a history start date, so depth is a probe question either way.

## Contract digests pinned by this PR

No collection receipt was minted (nothing was collected), so the digests below are the
endpoint-contract hashes — the deterministic record of exactly what field list, row cap,
document, and unit disclosure this PR admitted.

| Endpoint | Doc | `contract_source` | `contract_sha256` |
|---|---|---|---|
| `stk_mins` | 370 | `official_doc_page` | `94f20769dc4f4420ce322e835a2ac0b40a7d4eddec7197c9812749704574a445` |
| `stk_premarket` | 329 | `official_doc_page` | `33ac554cdba4b6af0330a4c387bd86d83e7312efa6b568adf0185748f4dc4358` |
| `stk_auction` | 369 | `official_doc_page` | `fb40afded9a7448fcab5e8314627bf910089d998e74d559f0e2fb63848feb1a1` |
| `stk_auction_o` | 353 | `official_doc_page` | `0c265b905832052d1eb0bb1d64bd6902ced51dc55acf7d472a191bd3ed2b3297` |
| `stk_auction_c` | 354 | `official_doc_page` | `fb151f3d4b7eb82621c7ce8cadee19af05388fa4384717adb3786c0f238cfa60` |

The o/c field lists were read off the live doc pages
([353](https://tushare.pro/document/2?doc_id=353),
[354](https://tushare.pro/document/2?doc_id=354)), which were reachable from this
environment — nothing was inferred from a probe response, and nothing was invented. The
three pre-existing digests changed in this PR only because `contract_source` was added
to every contract payload; the field lists of `stk_mins`, `stk_premarket`, and
`stk_auction` are byte-for-byte untouched.

## Open item for Lane B / Lane C

Docs 353/354 give 成交量 and 成交额 with **no unit**. TuShare is inconsistent here across
its own planes (`daily` reports volume in 手, the minute plane in 股), so the o/c schema
records the unit as `vendor-reported; docs 353/354 state no unit` rather than asserting
one. Any turnover ratio, participation rate, or float-normalized figure derived from
these two columns must first resolve the unit against a same-session reference — a
guessed unit is a silent 100× error.

## What this witness does and does not say

It records **refusals, not entitlements**. Licensing is settled elsewhere — by the
operator ruling in `research/TUSHARE_ADDONS_COLLECTOR_FOUNDATION_2026-08-09.md`, which
this PR pins as the authority — and nothing here adds to or subtracts from it. What this
document reports is narrower and purely operational: as of 2026-08-09 22:41
Asia/Shanghai the configured credential is rejected, so no endpoint has an access
observation, no schema has been confirmed against its contract, and the o/c history
depth is unmeasured.

The epistemic limits survive a working credential too, and are worth restating because
they are what the eventual receipts will and will not support: a non-empty response
proves access **at that request time** and nothing about future access; a short
minute-day may be suspension or vendor coverage rather than a complete session; and
none of these endpoints carry Level-2, order-book, or queue-position information. No
signal or strategy authority is created here — promotion happens at the gauntlet, not
at a collector.
