# MM-G0 — 2026-08-25 W2C M0D natural gate: production receipt adjudication

Date: 2026-08-27
Wave: `MM-G0` (read-only production receipt archaeology)
Parent operation: `market-memory-full-capability-20260827-sol-001` (seat `MM-F00`)
Child operation: `market-memory-mm-g0-receipt-archaeology-20260827-fable-001`
Mode: **READ-ONLY.** No writer/timer started, enabled, restarted or stopped; no store mutated; no
opportunity or abstention created or backfilled; no validator weakened; no defect repaired.
Adjudication authority: Sol. This record proposes a classification; it does not accept it.

## 0. Verdict

**`ABSTAINED`**

The natural experience-v2 invocation ran on schedule and terminated in a lawful typed no-admit
state. This is Sol's `ABSTAINED` branch exactly: *"writer ran and lawfully terminated in a typed
no-admit state."*

`NEVER_RAN` is **positively refuted** — not merely unsupported. `RECEIPT_UNRESOLVED` is **not**
retained: the terminal disposition is unambiguous in both journal and store bytes.

Confidence in the classification: **high**. Two independent evidence classes agree (systemd journal
for the boot covering the window, and immutable store bytes written at the window), and the prior
`RECEIPT_UNRESOLVED / BUILT_NOT_PROVEN` state was an artifact of searching GitHub/Slack/Linear
rather than the production host.

Separately and importantly: **the *cause* of the abstention is not recoverable from production
receipts.** See §4. The gate is resolved; the causal question behind it is not, and cannot be with
the evidence the current code retains.

## 1. Host and revision binding

| Fact | Value | How bound |
|---|---|---|
| Production host | `ubuntu-s-mastermindx` / `146.190.142.17` | `ssh -i ~/.ssh/macro_dashboard_deploy_v2 root@…`, `hostname`, verified `2026-08-28T01:00:57Z` |
| Boot covering the gate | boot `6b85ac7630fd497ba20cc383a2aa4ae3`, first entry `2026-07-24 13:26:29 UTC` | `journalctl --list-boots` |
| Journal retention floor | `2026-07-09T21:26:33+00:00` (3.3G archived+active) | `journalctl --disk-usage`, oldest entry |
| Journal covers the gate window? | **Yes**, with ~46 days of margin | retention floor ≪ 2026-08-25 |
| Installed revision at `04:00:00.900Z` (source seal start) | `eed0ed1ebc0…` (reflog entry `2026-08-25 03:48:04`; the next reset landed `2026-08-25 04:00:05`, i.e. **after** process start) | `/opt/macro` `git reflog --date=iso` |
| Installed revision at `04:07:00Z` (technicals-v2) | `dce7d940553…` (reflog `2026-08-25 04:06:04`) | same |
| Installed revision at `04:32:00Z` (experience-v2) | `1ec78241552283015d1892ab9d2c12b8a588a37b` (reflog `2026-08-25 04:24:03`; next reset `04:33:21`) | same, **independently corroborated** by the v1 run's own `deployed_commit` field emitted at `04:30:14Z` |
| Reflog depth | 5,932 entries back to `2026-07-26` | `git reflog | wc -l` |

`/opt/macro` is reset to `FETCH_HEAD` roughly every 3 minutes, so "installed revision" is
instant-specific. Each row above is pinned to the reflog entry in force at that instant, not to
current `HEAD` (`d84468e41f40…`).

## 2. The three chain units — schedule and terminal state

All three timers are `enabled`, `OnCalendar=*-*-* HH:MM:SS UTC`, **`Persistent=no`** (a missed fire
is not made up later — relevant to any future `NEVER_RAN` reasoning; not engaged here, because all
three did fire).

| Unit | OnCalendar | Fired 2026-08-25 | Terminal state |
|---|---|---|---|
| `macro-market-memory-source-spy-rest.service` | `04:00:00 UTC` | `04:00:00Z` → `04:05:00Z` | **exit 0**, `Deactivated successfully` / `Finished` |
| `macro-market-memory-technicals-v2.service` | `04:07:00 UTC` | `04:07:00Z` → `04:07:01Z` | **exit 1 FAILURE**, `TechnicalsV2SourceError` |
| `macro-market-memory-experience-v2.service` | `04:32:00 UTC` | `04:32:00Z` → `04:32:03Z` | **exit 0**, `Deactivated successfully` / `Finished` |

### 2.1 Source seal — verbatim terminal payload

```
2026-08-25T04:00:00Z  SPY REST seal owner starting: session=2026-08-24
                      window=[2026-08-25T04:00:00+00:00, 2026-08-25T04:05:00+00:00)
2026-08-25T04:05:00Z  seal predicate: opportunity_eligible=False
                      reason=no valid bar observation in seal window
{
  "created": false,
  "generation_id": null,
  "reason": "no valid bar observation in seal window",
  "schema": "market_memory.spy_rest_source_intake_run.v1",
  "session": "2026-08-24",
  "source_id": "massive_rest:SPY:unadjusted_daily",
  "status": "not_eligible"
}
```

The D+1 seal convention is correct: session `D = 2026-08-24` (**Monday**, a real XNYS session) is
sealed at `D+1 = 2026-08-25 04:00–04:05Z`.

### 2.2 technicals-v2 — verbatim failure

```
2026-08-25T04:07:01Z ERROR technicals-v2 capture failed: no opportunity-eligible sealed bar
  for session 2026-08-24 in source root /var/lib/macro-market-memory/state/sources-spy-rest-v1
TechnicalsV2SourceError  (scripts/capture_market_memory_technicals_v2.py:526, via :760)
systemd: Main process exited, code=exited, status=1/FAILURE
```

### 2.3 experience-v2 — the gate's own terminal receipt

```
{
  "message": "no sealed bar for 2026-08-24",
  "registration_id": "mmspyexpreg_ff4151e717d87d4ac32b59c515d677b01bf889feb494245c1ce655918fa875f4",
  "session": "2026-08-24",
  "status": "abstained"
}
```

## 3. Immutable store bytes (the second, independent evidence class)

`/var/lib/macro-market-memory/state/`

| Store | File count | Bearing |
|---|---|---|
| `sources-spy-rest-v1/` | **0** (dir mtime `2026-08-22 06:24:04Z`, i.e. creation) | never written since creation |
| `technicals-v2/` | **0** (dir mtime `2026-08-22 06:24:04Z`) | never written since creation |
| `experience-v2/` | `EXP_V2_HEAD.json`, `.v2_install_verified`, `records/{2026-08-24,2026-08-25,2026-08-26}.json` | three abstentions, one per real trading session |

Gate record — `experience-v2/records/2026-08-24.json`
`sha256 = a7d3fd732c59c905d26dbe44bbadab26497b0096367aee31d6a1b53ad2f06eed`, 290 bytes,
mtime `2026-08-25 04:32:03.081834063 +0000`:

```json
{"disposition":"abstained","reason":"no_opportunity_eligible_sealed_bar",
 "recorded_at":"2026-08-25T04:32:01.078879Z",
 "registration_id":"mmspyexpreg_ff4151e717d87d4ac32b59c515d677b01bf889feb494245c1ce655918fa875f4",
 "schema":"market_memory.spy_experience_v2_record.v1","session":"2026-08-24"}
```

`EXP_V2_HEAD.json` (212 bytes, mtime `2026-08-27 04:32:02Z`):
`{"latest_disposition":"abstained","latest_session":"2026-08-26","registration_id":"mmspyexpreg_ff4151…","schema":"market_memory.spy_experience_v2_head.v1"}`

Journal and store agree on disposition, session, registration id and timestamp. The classification
does not rest on logs alone.

## 4. Causal chain — established, and where it goes dark

The chain is strictly sequential and the failure propagates forward:

```
source seal   opportunity_eligible=False  ->  writes NOTHING          (exit 0)
technicals-v2 no eligible sealed bar      ->  raises, writes NOTHING  (exit 1)
experience-v2 no sealed bar for session   ->  abstains, writes record (exit 0)
```

So the single root input is the source seal's `opportunity_eligible=False`.

The seal predicate (`engine/neuralweb/market_memory_sources_spy.py:216-260`) requires, inside
`[04:00:00Z, 04:05:00Z)`: ≥3 `valid_bar` observations, spanning ≥240s, ≥1 in the opening 60s, ≥1
after 04:04:00Z, all sharing one `results[]` digest. It returned the **first** branch —
`if not valid_obs` — meaning **zero** observations of status `valid_bar`.

**The cause is unrecoverable, by code design rather than by log rotation.**
`_collect_seal_observations` (`scripts/ingest_market_memory_sources_spy.py`) classifies every poll
as `transport_error` / `no_bar` / `malformed` / `valid_bar` and **emits no log line for any of
them**. The only surviving artifact is `seal_state.transcript` — and the `not_eligible` branch
(`scripts/ingest_market_memory_sources_spy.py:474-482`) **returns immediately, discarding the
transcript and persisting nothing**. Confirmed empirically: `grep -icE
"transport|error|timeout|http|401|403|429|500|exception|retry"` over the entire retained journal for
that unit returns **0**, and the store holds **0** files after six days of daily runs.

Therefore these three remain permanently indistinguishable for the Aug-25 gate:

1. the vendor genuinely returned `no_bar` in the window (a market/vendor fact, lawful abstention);
2. every poll was a `transport_error` (a source-plane failure wearing an abstention's clothes);
3. responses were `malformed`.

Credentials were present and readable at `/etc/macro-market-memory-spy-rest/{MASSIVE_API_KEY,POLYGON_API_KEY}`
(33 bytes each, mode `-r--------`, mtime `2026-08-22 16:06`) — so branch (2) is not excluded by a
missing-secret argument. Values were not read.

## 5. This is not a one-day event

`macro-market-memory-source-spy-rest.service`, every retained run:

| Ran at (UTC) | Session sealed | Weekday | Outcome | Correct? |
|---|---|---|---|---|
| 2026-08-23 04:00 | 2026-08-22 | Saturday | `not_eligible` | **yes** — no session |
| 2026-08-24 04:00 | 2026-08-23 | Sunday | `not_eligible` | **yes** — no session |
| 2026-08-25 04:00 | 2026-08-24 | **Monday** | `not_eligible` | **suspicious** |
| 2026-08-26 04:00 | 2026-08-25 | **Tuesday** | `not_eligible` | **suspicious** |
| 2026-08-27 04:00 | 2026-08-26 | **Wednesday** | `not_eligible` | **suspicious** |

`created=false`, `generation_id=null` on all five. **The v2 chain has never once admitted.** Three
consecutive real XNYS sessions produced no valid bar observation.

`macro-market-memory-technicals-v2.service` splits cleanly on the same axis — and this is the
health-signal defect in its sharpest form:

- weekend sessions → `{"status": "no_session"}`, **exit 0** (lawful, quiet);
- real trading sessions (08-25, 08-26, 08-27) → `TechnicalsV2SourceError`, **exit 1 FAILURE**.

The unit raises rather than lawfully abstaining when its upstream is not eligible. A lawful no-admit
day is therefore reported to the health layer as a hard unit failure, and is indistinguishable there
from a genuine crash.

## 6. v1 control arm — context only, and deliberately not load-bearing

`v1_control_unavailable` **does not apply**: the v1 arm was available and admitting on the exact
gate session. `macro-market-memory-experience.service` ran `2026-08-25 04:30:02Z → 04:30:15Z`,
**exit 0**, and admitted:

```json
{"schema":"market_memory.spy_experience_accrual_run.v1",
 "deployed_commit":"1ec78241552283015d1892ab9d2c12b8a588a37b",
 "opportunity_ids":["mmspyexpopp_41baac2abbf1b342ce87e14ff8be614baec13ae88a355a040960cdc0b4c7bf4e"],
 "population_receipt_id":"mmspyexppop_ed7139675ea7de92eced067480757d69dc714d57d380c4583057f1a489f00011",
 "registration_id":"mmspyexpreg_e00ffc1d34b57ce3b011955a8662dae8f7e069b7f5f07417c428a5815c6dd6e3",
 "outcome_revision_ids":[]}
```

`experience-v1/opportunities/` holds `2026-08-17,18,19,20,21,24,25,26` — every trading session, no
weekend files. 41 files in `experience-v1/`, 134 in `technicals-v1/`.

**This does not upgrade or downgrade the v2 result, and must not be read as proving v2 should have
admitted.** v1 is the arm M0B classified `A — SOURCE_CLOCK_IMPOSSIBLE`, and its own Aug-24
opportunity says so in its bytes: `"external_clock_authenticated": false`,
`"clock_model": "session_ordinal_only_no_fabricated_market_close_timestamp"`,
`"authority": {"tier":"display","context_only":true, may_* : false}`, with
`actual_cutoff_at = 2026-08-25T04:30:07.790301Z` — i.e. v1 observes **26 minutes after** the v2 seal
window closed, under a clock v2 exists precisely to replace.

The honest reading, and the limit of it: v1's admission is evidence that **session-2026-08-24 market
data was obtainable from somewhere by 04:30Z**. It is **not** evidence that a lawful v2 REST seal
was obtainable inside `[04:00:00Z, 04:05:00Z)`. It raises the prior on §4 branch (2) over branch (1)
without settling it.

## 7. Falsifier

This classification is wrong if any of the following is produced:

1. an `experience-v2` store record or HEAD generation for session `2026-08-24` whose disposition is
   anything other than `abstained` — the byte at
   `sha256 a7d3fd732c59c905d26dbe44bbadab26497b0096367aee31d6a1b53ad2f06eed` is the whole claim;
2. journal evidence, from the same boot `6b85ac7630fd497ba20cc383a2aa4ae3`, of a **second**
   `macro-market-memory-experience-v2.service` invocation in the eligible window with a different
   terminal state;
3. proof that the natural-gate definition is not the `04:32:00 UTC` `experience-v2` timer — i.e.
   that some other unit is the authentic M0D writer;
4. proof that `exit 0 / Deactivated successfully` on `experience-v2` does not constitute "lawfully
   terminated", which would move the verdict from `ABSTAINED` toward `FAIL`.

What would **not** falsify it: the `technicals-v2` exit-1 failure. That unit is upstream of the
writer and its own failure is downstream of an already-`not_eligible` seal; the natural chain was
never eligible, so it does not meet Sol's `FAIL` branch ("natural **eligible** chain attempted and
causally failed before a lawful terminal result"). The writer did reach a lawful terminal result.

## 8. Defects established by this evidence — NOT repaired here

Frozen for Sol to open (or decline to open) as separate modifying child operations. MM-G0 does not
touch them.

**D1 — the source seal discards its own causal evidence.**
`scripts/ingest_market_memory_sources_spy.py:474-482` returns on `not_eligible` without persisting
`seal_state.transcript`, and `_collect_seal_observations` logs no observation. Every abstention is
therefore causally unauditable forever. This is the mechanism that turned the Aug-25 gate into
`RECEIPT_UNRESOLVED` in the first place, and it will do it again on every future abstention.
Severity: this is the concrete instance of the recharter's `Production source-clock observability /
abstention audit = BROKEN` row.

**D2 — `technicals-v2` reports a lawful no-admit as a hard failure.**
It raises `TechnicalsV2SourceError` (exit 1) on real trading sessions when upstream is not eligible,
while correctly emitting `{"status":"no_session"}` (exit 0) on weekends. A lawful abstention day is
therefore red at the systemd/health layer, so the health signal cannot distinguish "nothing to do"
from "broken" — and a real breakage would be camouflaged by the standing red.

**D3 — the v2 chain has never admitted (0 admits / 3 real sessions retained).**
`sources-spy-rest-v1/` and `technicals-v2/` hold zero files since creation on 2026-08-22. Whether
this is lawful (vendor truly had no bar in-window) or a defect (transport/window/clock) **cannot be
determined** until D1 is fixed. This is the honest blocker on M0D ever passing, and it is a
source-plane question — MM-S1 territory, not MM-G0's.

Ordering note for Sol: D1 gates the diagnosis of D3. Until the transcript is persisted, any D3
investigation is guesswork; after one fix, the next abstention answers it from its own receipt.

## 9. Durable-state reconciliation deliberately withheld

`agentos/workstreams/WS-MARKET-MEMORY-W2C.md` still projects the 2026-08-25 gate as future and M0D
as `BUILT_NOT_PROVEN`. Per Sol's MM-G0 stop condition — classify, then return for adjudication —
this record does **not** mutate that workstream's `status`, `waves` or `next_action`. Reconciling
W2C is a post-`RULING` act.

## 10. Commands (all read-only, reproducible)

```
ssh -i ~/.ssh/macro_dashboard_deploy_v2 root@146.190.142.17
journalctl --list-boots --no-pager
journalctl --disk-usage
journalctl -o short-iso --utc --no-pager \
  -u macro-market-memory-source-spy-rest.service \
  -u macro-market-memory-technicals-v2.service \
  -u macro-market-memory-experience-v2.service \
  --since "2026-08-25 03:45:00 UTC" --until "2026-08-25 05:05:00 UTC"
journalctl -o short-iso --utc --no-pager -u macro-market-memory-experience.service \
  --since "2026-08-25 04:25:00 UTC" --until "2026-08-25 04:40:00 UTC"
systemctl show macro-market-memory-{source-spy-rest,technicals-v2,experience-v2}.timer \
  -p TimersCalendar -p Persistent
find /var/lib/macro-market-memory/state/{sources-spy-rest-v1,technicals-v2,experience-v2} -maxdepth 3
sha256sum /var/lib/macro-market-memory/state/experience-v2/records/2026-08-24.json
cat /var/lib/macro-market-memory/state/experience-v2/EXP_V2_HEAD.json
cd /opt/macro && git reflog --date=iso | grep "2026-08-25 0[0-4]:"
```
