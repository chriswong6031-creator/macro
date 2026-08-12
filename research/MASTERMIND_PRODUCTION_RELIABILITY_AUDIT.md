# Mastermind-X — Production Reliability Audit

**Audit date:** 2026-08-12
**Covers:** Parts VII (market data), VIII (timezone), IX (pipelines), X (schedulers/workers),
XI (vendors), XII (cost), XIII (scale), XIV (caches), XV (database), XIX (observability),
XX (failure UX), XXI (deployment), XXII (backups), XXIII (AI), XXIV (trust), XXIX (chaos).

**Headline:** the *data* side of this product is mature — freshness is surfaced honestly,
schedulers are properly bounded, caches are correctly scoped, timezone hygiene is excellent.
The reliability risk is concentrated in three places: **no tested recovery path**,
**cost controls that concurrency defeats**, and **a single process with a synchronous
vendor call on its hot path**.

---

## 1. Market data correctness (Part VII)

### 1.1 The "last known value shown as current" test — **PASSED**

This is the question that matters most for a financial product, and the product handles it
correctly. Degraded reads are labelled, not disguised:

- API layer: R2 read-throughs merge `{"stale": true}` into the response when a refresh fails
  and a cached copy exists. `503` is returned **only** when the object was never successfully
  fetched — so "never had it" and "have an old one" are distinct states, not both rendered
  as an empty card (`app/main.py:32`, `app/hub.py:11,73`, `app/research.py:135`).
- UI layer: `templates/live.js` carries a dedicated `.stale` class and a staleness chip, with
  session-aware clocks per region, and explicitly leaves baked last-close numbers untouched
  when a live payload is stale (`live.js:38,107-143`).
- Crypto is handled separately because it trades 24/7 and goes stale on a different cadence
  (`live.js:80`).

This satisfies Part XX's requirement that *unavailable*, *no signal*, *zero*, *stale*, and
*still computing* be distinguishable. That distinction is implemented, not aspirational.

### 1.2 Timezone (Part VIII) — **strong, with three exceptions**

| Measure | Count |
|---|---|
| Timezone-aware `datetime.now(tz=…)` / `ZoneInfo` | **762** |
| `datetime.utcnow()` (naive, deprecated) | **0** |
| Bare `datetime.now()` | 10 — of which **7 are comments forbidding it** |

The three real call sites are `engine/special_arb.py:194`, `engine/congress_members.py:155`
(both `datetime.now().date()`) and `engine/signal_sanity.py:344`. On a UTC server these
resolve to **tomorrow's date after 20:00 ET** — the classic "signal one day early" defect
(MMX-010).

The codebase clearly knows this: `engine/neuralweb/world_state.py` goes as far as making
`datetime.now()` *raise* while a pinned `now` is in scope, and several modules carry comments
explaining that a `datetime.now()` there would be a determinism bug. The convention is right;
three sites missed it.

### 1.3 Not verified

Corporate actions, splits, dividends, symbol changes, delistings, ticker reuse, options
expiry, and multi-vendor disagreement resolution were **not traced end-to-end** in this audit.
The repo shows substantial machinery aimed at exactly these problems — a
`lib.ticker_aliases` resolver, a `identity.stable_key_vendor_alias_boundary` CI guard for
symbol-rename drift, and point-in-time membership snapshot cadence guards
(`docs/HOUSE_LAW_CI_GUARD_SUITE.md`). That is more investment than most products of this age
make. Confirming it works is a dedicated workstream, not a red-team sample.

---

## 2. Schedulers and workers (Part X)

**18 systemd timers** on the VPS (live bars, snapshots, close pass, prophet, seven
market-memory lanes, biocatalyst, sentinel).

| Risk from the brief | Finding |
|---|---|
| **Can two workers run the same job?** | **No.** systemd will not start a `.service` that is already active, so a timer firing while its unit runs is a no-op. Overlap protection is structural. |
| **Can the scheduler overlap itself?** | **No** — same mechanism. |
| **Runaway processes** | **Bounded.** All 18 timer-driven units declare `RuntimeMaxSec`/`TimeoutStartSec`. The only three units without a timeout are `macro-api`, `marketing-press-feeds`, and `marketing-reply-desk` — long-running daemons, where no timeout is correct. |
| **Infinite retries → vendor spend** | `Restart=always` on the API is correct for a daemon. I found no unbounded retry loop against a paid vendor in the timer units. |
| **Poison tasks** | Not systematically verified. The per-unit `RuntimeMaxSec` caps blast radius: a malformed symbol crashes or times out one lane rather than wedging a shared queue. There is no shared queue to poison — the architecture is timers over artifacts, not a broker. |
| **Memory leaks** | Timer-driven units are short-lived processes, so leaks self-clear. `macro-api` is long-lived and **is** a leak candidate — its in-process caches (`_AUTH_CACHE`, `_ENT_CACHE`, flow/hub/research TTL dicts) are dicts with size-based clears (`if len(_AUTH_CACHE) > 5000: clear()`), which is crude but bounded. |
| **Partial transaction state** | See §7 — the file-based ledgers are the weak spot. |

**Assessment:** choosing systemd timers over a Celery/Redis broker was a good call for this
scale. It removes the entire class of queue failures the brief asks about (duplicate delivery,
poison messages, unbounded queue growth) in exchange for coarser scheduling.

---

## 3. Caches (Part XIV) — **no leakage found**

| Cache | Key | TTL | User-scoped? | Verdict |
|---|---|---|---|---|
| `_AUTH_CACHE` (paywall) | `sha256(token)` | 45s, hard-capped 60s | Yes — by token | Correct. uid+email cached **together** so the halves can never disagree. |
| `_ENT_CACHE` (paywall) | `user_id` | 60s (+24h positive grace) | Yes | Correct; invalidated on every entitlement mutation. |
| `_FLOW_CACHE` (main) | R2 object key | 30s | No — global artifact | Correct: the data has no user dimension. |
| `_HUB_CACHE` | R2 object key | 30s | No — global | Correct. |
| `_CATALOG_CACHE` (research) | object key | 60s | No — global | Correct. |
| Gov-revenue artifact | path + `mtime_ns` | mtime-invalidated | No — global | Correct, and mtime keying means a re-baked artifact invalidates immediately. |
| Admin API cache | namespace + full path | generation-scoped | Admin-only | Correct. |

Checked specifically for the brief's cache failure modes:

- **Cross-user leakage (key missing user id):** none — every user-varying cache is keyed by
  token hash or user id.
- **Cross-tier leakage (Pro response served to Free):** none — paywalled responses carry
  `Cache-Control: private, no-store` and `Vary: Cookie` (`paywall._headers`), and the global
  `_NoStoreAPI` middleware keeps API errors no-store.
- **Wrong ticker (symbol missing from key):** none — hub/flow caches key on the full object
  key including root.
- **Deployment mismatch (old schema cached after deploy):** structurally impossible — all
  caches are in-process and die with the single process on restart. (This is the one upside
  of MMX-006.)

**This section is a clean pass.** Cache bugs produce the most convincing wrong data, and I
went looking for them specifically.

---

## 4. Vendor failure (Part XI)

| Vendor | Failure behavior | Cascade risk |
|---|---|---|
| **Supabase Auth** | `require_user` raises **502** on any non-HTTP error, uncached, blocking, 5s timeout | **TOTAL PRODUCT OUTAGE.** This is the one vendor whose degradation takes everything down, including unauthenticated routes via thread-pool exhaustion. See MMX-004. |
| **Supabase PostgREST** (entitlements) | Graceful — 24h positive grace, fail-closed for negatives | Well handled |
| **Stripe** | Checkout/portal routes 503 cleanly when unconfigured; webhook 503s without a secret; nightly reconciler backstops missed webhooks | Well handled |
| **Anthropic** | `ANTHROPIC_API_KEY` absent ⇒ `mode='memo-quote'`, `degraded=True`, serving an excerpt from `data/neuralweb/cortex/memo.json` instead of erroring | **Exemplary graceful degradation** |
| **R2 (artifacts)** | Read-through with TTL + `{"stale": true}` + 503-only-if-never-fetched | Well handled |
| **SMTP** | Inside `_handle_event`, with one retry, off the event loop via `run_in_threadpool` | Adequate; contributes to the webhook TOCTOU window |
| **EdgeOne CDN** | Not verifiable from the repo | Unknown — operator question |

**The single-vendor cascade is Supabase Auth**, and it is the only one. Every other
dependency degrades rather than cascades. Fixing MMX-004 (cache + semaphore) converts the
last cascade into a degradation.

---

## 5. Cost explosion (Part XII)

### 5.1 What scales with users, and what does not

The architecture gets the expensive part right: **market data cost is O(1) in users.**
Flow, hub, research, and gov-revenue all serve from shared TTL/mtime caches over R2 or local
artifacts, so 10 users and 10,000 users generate roughly the same upstream vendor load.
Only two things scale per-user:

| Action | Cost driver | 10 users | 100 | 1,000 | 10,000 |
|---|---|---|---|---|---|
| **Supabase auth call** — 1 per authenticated request, uncached | Supabase Auth rate limit | fine | fine | **at/over project limits** | **hard fail** |
| **LLM chat** — per message, quota-capped in principle | Anthropic tokens | fine | fine | fine **if caps hold** | **unbounded if caps don't** |
| Market data / charts | shared cache | flat | flat | flat | flat |
| DB queries | 1–2 per request | fine | fine | fine | needs pooling review |

Assuming ~50 authenticated requests per user-session, 5,000 daily users produce on the order
of **250,000 Supabase auth calls/day** — every one of them a blocking 5s-timeout network hop
on the request path. A 45-second cache collapses that by roughly one to two orders of
magnitude, which is why MMX-004 is both the scale fix and the cost fix.

### 5.2 The uncapped path

The quota system is the *only* thing standing between an anonymous visitor and your Anthropic
bill, and it can be defeated three ways (MMX-002/003/005):

1. **Concurrency** — unlocked read-modify-write means *N* parallel requests cost 1 quota unit.
2. **Torn write** — non-atomic `write_text` + `except: return {"count": 0}` silently resets the cap.
3. **I/O failure** — quota dir unavailable ⇒ explicit `fail-open` with `limit: -1`.

There is **no global spend ceiling** independent of the per-user ledger, and **no alert on
spend rate**. The first signal would be the vendor invoice.

**Mitigations already present, to be fair:** a burst throttle (`_brain_throttle_check`),
dual cookie+IP guest keying, a 12-turn history cap, a monthly token-ceiling backstop
(`_record_token_usage`), and guest access being **off by default** and fail-closed if the
config can't be read. The ceiling exists; its enforcement is not concurrency-safe.

---

## 6. Performance and scale cliffs (Part XIII)

Ranked by where the product actually breaks first:

1. **~40 concurrent authenticated requests** — FastAPI's default thread pool, each thread
   parked on a 5s Supabase call. This is the first cliff and it is far below launch scale.
2. **Single uvicorn process** — no horizontal capacity, no rolling deploy, cold caches on
   every restart (MMX-006).
3. **Blocking calls in sync handlers** — `require_user`, `_pg`, `_store_entitlement`, and the
   R2 read-throughs are all synchronous `urllib`. The webhook correctly uses
   `run_in_threadpool`; the auth path does not have that excuse since it *is* the threadpool.
4. **Not a cliff:** N+1 queries, full-table scans, and huge JSON responses. The artifact-cache
   architecture avoids per-request DB work almost entirely — most reads are a dict lookup.

**Fix order matters:** adding `--workers` before fixing the quota ledger makes MMX-002/003
strictly worse, because separate processes contend on the same unlocked files.

---

## 7. Database (Part XV)

- **Constraints:** RLS on all 7 user tables; `stripe_events` has a primary key used for
  `on_conflict=id` idempotency. Migration surface is small (one init migration in
  charting-app).
- **Transaction boundaries:** the webhook's DB writes go through PostgREST as discrete
  upserts, not a single transaction. Acceptable because `_handle_event` recomputes from live
  Stripe state and is idempotent — a partial write self-heals on the next event or the
  nightly reconciler.
- **The real gap is not schema, it is recovery** — see §9.
- **Durable counters on the local filesystem** is the structural mistake: quota, token
  ceilings, and free-credit pools are JSON files with non-atomic writes on a single box.
  Money-adjacent counters belong in Postgres where an atomic `UPDATE … RETURNING` gives
  correctness for free.

---

## 8. Observability (Part XIX)

**The strongest single piece of operational engineering in this repo** is
`macro-sentinel.service`: an external freshness dead-man switch that deliberately runs
**outside GitHub Actions**, is stdlib-only so it cannot be broken by a bad venv, fetches the
live pages' bake stamps, compares them against freshness budgets, alerts via
Telegram/Discord/email, and publishes machine-readable `staleness.json` by atomic rename.

Its header states why it exists: *"The 2026-08-06 outage froze the boards for six days
because every alarm lived inside GitHub Actions — the thing that was failing."* That is the
correct lesson, correctly institutionalized.

**"How would we know it broke?" — honest answers:**

| Condition | Detection today |
|---|---|
| Stale market data / ingestion stopped | **Good** — sentinel alerts, `staleness.json`, `/api/status` per-check `age_min` |
| Site publish broken | **Good** — sentinel |
| API down | **Good** — `/api/health`, `/healthz` |
| Prophet output stopped | **Good** — covered by sentinel freshness budgets |
| Login failures spike | **No alarm** — logged only |
| Checkout failures | **No alarm** |
| Webhook failures | **Partial** — nightly reconciler corrects state, but nothing pages on a webhook outage |
| **LLM spend rate** | **No alarm** — the biggest gap |
| Vendor rate limiting (Supabase) | **No alarm** |
| DB latency | **No alarm** |
| Error-rate spike | **No alarm** — no error tracker (no Sentry or equivalent found) |

**Pattern:** *data freshness* is very well monitored; the *commercial* path (auth, checkout,
webhooks, spend) is not monitored at all. That asymmetry reflects the product's history as a
data platform, and launching to paying users changes which half matters.

---

## 9. Deployment, rollback, recovery (Parts XXI, XXII)

### 9.1 Deployment

VPS pulls `main` every 3 minutes and runs `app/deploy/update.sh`, which reconciles unit files
and restarts services on a trigger regex. Static site and plain-copy assets go live via the
same pull. Render lanes re-stamp assets.

- **What SHA is deployed:** tracked — `/opt/macro` checkout SHA, `_PROCESS_COMMIT` reported
  by `/api/health` and `/api/status`, and `.deployment-id` markers for the Terminal.
  `docs/PRODUCTION_RUNTIME_TRUTH.md` is explicit that a GitHub SHA, a deployed marker, a
  process SHA, a health probe, and a data receipt answer **different questions** and must stay
  separate. That is the right model.
- **Version incompatibility:** possible in the window between a static-site pull and an API
  restart, since they land independently. Mitigated by 3-minute pull granularity, not by design.
- **Rollback:** `git revert` + the 3-minute pull is the real path. `live-rollback.sh` exists
  for the live plane and is non-destructive (timestamped artifact backup, falls back to last
  `site.served`).

**Answer to the brief's question — "if tonight's deploy breaks production, how fast can we
get back?":** for code and content, roughly **3–6 minutes**, procedurally, via revert-and-pull.
That is a real answer, not an aspirational one. **For data, there is no answer at all.**

### 9.2 Backups — **the launch blocker (MMX-001)**

A precise search for `pg_dump`, `pg_restore`, `PITR`, and `point-in-time` across
`docs/ ops/ app/ scripts/ .github/` returns **zero database-recovery hits**. Every
"point-in-time" match is market-data PIT semantics.

| Question from Part XXII | Answer |
|---|---|
| What is backed up? | Artifacts (R2, git). **User/billing data: unknown — nothing in-repo.** |
| Frequency? | Unknown — depends on the Supabase plan |
| Retention? | Unknown |
| Location? | Supabase-managed, if enabled |
| Encryption? | Supabase-managed |
| **Has restoration ever been tested?** | **No evidence anywhere.** |

The brief's own framing applies exactly: *"Backups that have never been restored are
hypotheses."* Here there is not yet a hypothesis — there is an assumption about a vendor
setting nobody has checked.

---

## 10. AI-specific failure modes (Part XXIII)

| Risk | Finding |
|---|---|
| AI triggering privileged operations | **Structurally prevented.** Write tools are absent from the schema, not merely disabled ("read tools only; write tools structurally absent — Article 1"). The house constitution (A7) forbids the LLM from originating signals, scores, or escalations; it may only de-escalate calibrated keys. |
| Prompt injection via user input | Partially mitigated — chat context reads product artifacts only, never repo internals (CXI-R23). Untrusted market/news text entering prompts was **not** traced end-to-end. |
| Data exposure through prompts | Guest email is forced to `''` so operator/unlimited allow-lists can never match a guest — a deliberate injection-resistance measure. |
| Provider outage | Graceful: `mode='memo-quote'`, `degraded=True`. |
| Runaway token consumption | **The weak point** — MMX-002/003/005. |
| Response parsing / schema failure | Not traced. |
| AI vs authoritative data | **Well separated.** This is a core doctrine of the codebase, not an afterthought: the LLM never originates signals; computed artifacts are the authority. |

---

## 11. Financial-product trust failures (Part XXIV)

Actively searched for the brief's list. Findings:

- **Two prices on two pages:** low risk. Live values flow from one overlay/live path with a
  shared session clock; baked pages hold last-close until a live payload arrives, and stale
  payloads explicitly leave baked numbers untouched.
- **Old news labelled new:** defended by the freshness/staleness machinery and the sentinel.
- **Confidence displayed without data:** defended by doctrine — nulls are printed, not hidden;
  "validated" is CI-enforced language (`scripts/check_validated_claims.py`).
- **Zero used instead of missing:** the `{stale:true}` / `503`-never-fetched split exists
  precisely to avoid this.
- **Backfilled intelligence presented as live prediction:** the point-in-time machinery and
  the `prophet_management` PIT guarantee ("this function never calls `datetime.now()` or
  `date.today()`") are aimed exactly here.
- **Actual residual risk:** MMX-010's three naive `datetime.now().date()` sites, which can
  attribute a signal to the wrong trading day in the evening window. That is the one place
  where this product could show a trader a date they can prove is wrong.

---

## 12. Proposed chaos tests (Part XXIX)

Small, high-information, runnable in a staging environment in under a day.

| # | Test | Predicted outcome from code | What it would prove |
|---|---|---|---|
| 1 | **Block Supabase Auth at the firewall** | Every authenticated route 502s; thread pool saturates; unauthenticated routes stall too | Confirms MMX-004 is a total-outage cascade — the single most important test here |
| 2 | **Fire 50 concurrent brain requests from one guest identity** | Far more than the daily cap succeeds | Confirms MMX-002 quantitatively; gives the real bypass ratio |
| 3 | **`chmod 000` the quota state dir** | All requests allowed, `limit: -1`, `::error::` logged, nobody paged | Confirms MMX-005 fail-open and the missing alert |
| 4 | **`kill -9` uvicorn mid-quota-write** | Truncated JSON ⇒ cap silently resets to 0 | Confirms MMX-003 |
| 5 | **Deliver the same Stripe webhook twice, concurrently** | Both pass `_event_seen`; duplicate billing email; DB state still correct | Confirms MMX-007 scope — proves it is an email bug, not an entitlement bug |
| 6 | **Delay all webhooks 6 hours** | Nightly reconciler restores correct entitlement | Validates the backstop actually works |
| 7 | **Return malformed JSON from the LLM provider** | Unverified — parsing path not traced | Genuinely unknown; worth running |
| 8 | **Stop a market-data timer for 30 hours** | Sentinel alerts on the freshness budget; `staleness.json` flips; UI shows stale chips | Validates the best-built subsystem end to end |
| 9 | **Restore a `pg_dump` into a scratch Supabase project** | Unknown — never attempted | **The most valuable test on this list.** Converts MMX-001 from an assumption into a measured RTO. |

---

## 13. Summary

| Area | Verdict |
|---|---|
| Market-data freshness honesty | **Strong** — stale/missing/never-fetched are distinct states |
| Timezone | **Strong** — 762 aware vs 0 `utcnow()`; 3 sites to fix |
| Schedulers | **Strong** — systemd prevents overlap structurally; all 18 units bounded |
| Caches | **Clean** — no cross-user or cross-tier leakage found |
| Vendor degradation | **Strong except Supabase Auth**, the one true cascade |
| Observability (data) | **Strong** — external dead-man sentinel |
| Observability (commercial) | **Absent** — no alarm on auth, checkout, webhooks, or spend |
| Cost control | **Defeated by concurrency** — the likeliest source of financial damage |
| Deployment / rollback | **Real and fast** (~3–6 min) for code and content |
| **Data recovery** | **Untested and undocumented — the launch blocker** |
