# Mastermind-X — Red Team Remediation Plan

**Audit date:** 2026-08-12
**Design goal:** multiple Codex/Fable sessions execute these concurrently without colliding.

Each workstream is scoped to a **disjoint file set** so parallel sessions do not conflict.
Collisions are called out explicitly where they exist.

**Model routing** follows `CLAUDE.md` §Model routing: `builder` (Opus) implements,
`reviewer` (Opus) verifies, `Explore`/`general-purpose` with explicit `model: 'sonnet'` for
mechanical census. Per §Spawn-handoff law, every acceptance criterion below is stated
**inline** and phrased "not done unless" — a session receives only its prompt plus the target
repo's `CLAUDE.md`, so nothing load-bearing may live behind a pointer.

---

## Dependency graph

```
WS-1 (backups)      ──────────────── independent, start immediately
WS-2 (quota safety) ──┬───────────── blocks WS-6
WS-3 (auth cache)   ──┘              independent of WS-2 (different files)
WS-4 (alerting)     ──────────────── independent
WS-5 (secret scan)  ──────────────── independent, start immediately
WS-6 (multi-worker) ←── REQUIRES WS-2 (workers worsen an unlocked file ledger)
WS-7 (rate limits)  ──────────────── independent
WS-8 (webhook TOCTOU)─────────────── independent
WS-9 (isolation test)─────────────── independent
WS-10 (datetimes)   ──────────────── independent
```

**Safe to run fully in parallel, wave 1:** WS-1, WS-2, WS-3, WS-4, WS-5, WS-9.
**Wave 2 (after WS-2 merges):** WS-6.
**Any time:** WS-7, WS-8, WS-10.

**Only real file collision:** WS-2 and WS-6 both change how quota state is accessed.
WS-3 touches `app/main.py`; WS-9 adds a new `scripts/check_*.py` and touches no handler —
they can co-exist, but should rebase in that order.

---

## WS-1 — Backup and restore capability

| Field | Value |
|---|---|
| **Priority** | **P0 — launch blocker** (MMX-001, GATE-1) |
| **Scope** | Establish and *prove* a recovery path for customer data. |
| **Dependencies** | None. Start first — it has an operator-action component with latency. |
| **Model/agent** | Operator action + `builder` (Opus) for the dump job |
| **Files/systems** | New `scripts/backup_user_tables.py`; new systemd unit + timer in `app/deploy/`; new `docs/RESTORE_RUNBOOK.md`; Supabase dashboard (operator) |
| **Validation** | An actual restore into a scratch Supabase project, with measured RTO |

**Acceptance criteria — not done unless:**
1. The active Supabase plan's backup/PITR setting is captured in `docs/RESTORE_RUNBOOK.md`
   with its retention window.
2. A nightly job dumps `profiles`, `watchlists`, `watchlist_symbols`, `chart_layouts`,
   `saved_scripts`, `alerts`, `favorites`, `user_entitlements`, `stripe_events` to R2 with
   ≥30-day retention, following the existing timer idiom (`RuntimeMaxSec` set, like all 18
   current units).
3. **A restore has actually been performed once** into a scratch project, and the measured
   RTO and RPO are written in the runbook. A documented-but-untested procedure does **not**
   pass this gate.
4. The runbook names exact commands, not descriptions of commands.

---

## WS-2 — Quota ledger: atomicity, locking, fail-closed guests

| Field | Value |
|---|---|
| **Priority** | **P0 for launch** (MMX-002/003/005, GATE-2) |
| **Scope** | Make the LLM spend cap survive concurrency, crashes, and I/O failure. |
| **Dependencies** | None. **Blocks WS-6.** |
| **Model/agent** | `builder` (Opus) — money-adjacent concurrency, not mechanical |
| **Files/systems** | `engine/neuralweb/brain_gateway.py` (`_read_quota`, `_write_quota`, `_check_and_increment_quota`, `_check_and_increment_guest_quota`, `_record_token_usage`) |
| **Validation** | Concurrency test + fault injection |

**Acceptance criteria — not done unless:**
1. Check-and-increment is **atomic** — `fcntl.flock` held across the read *and* the write, or
   the counter relocated to Postgres with `UPDATE … RETURNING`.
2. Writes are atomic — `tmp` + `os.replace`. A truncated ledger must **not** read as
   `{"count": 0}`; corrupt state alarms rather than silently granting a fresh allowance.
3. Guest quota **fails closed** when the state dir is unavailable. Authenticated paying users
   keep the existing fail-open (this asymmetry is deliberate — preserve it and say so in a
   comment).
4. A new test fires ≥50 concurrent check-and-increment calls against a limit of 10 and
   asserts **at most 10** succeed. **The test must fail against the current code** — prove
   the guard can see the failure before claiming the fix.
5. A global daily spend ceiling exists, independent of per-user ledgers.

**Note for the implementer:** the existing fail-open is *intentional and correct* for payers
("a broken ledger must never lock out paying users"). Do not remove it wholesale — make it
asymmetric.

---

## WS-3 — Cache and bound the Supabase auth call

| Field | Value |
|---|---|
| **Priority** | **P0 for launch** (MMX-004, GATE-3) |
| **Scope** | Remove the uncached blocking vendor call from every authenticated request. |
| **Dependencies** | None |
| **Model/agent** | `builder` (Opus) |
| **Files/systems** | `app/main.py:735` (`require_user`), `app/paywall.py` (`_fresh_identity`, `_AUTH_CACHE`) |
| **Validation** | Vendor-outage simulation + concurrency test |

**Acceptance criteria — not done unless:**
1. `require_user` reuses the token cache `app/paywall.py:_fresh_identity` **already
   implements** (`sha256(token)` key, TTL clamped 1–60s). Do not write a second cache —
   consolidate onto the existing one. Two divergent identity paths is itself a finding
   (MMX-004 rationale).
2. Concurrent upstream auth calls are bounded (semaphore), so a slow Supabase sheds rather
   than exhausting the ~40-thread pool.
3. `/api/health` still answers while Supabase is unreachable.
4. A cached valid session continues to work for the cache TTL during a simulated Supabase
   outage; an **invalid** token is still rejected (the cache must not become a bypass).
5. Existing auth tests still pass, and a new test proves an expired/invalid token is not
   served from cache.

---

## WS-4 — Commercial-path alerting

| Field | Value |
|---|---|
| **Priority** | **P0 for launch** (GATE-4) |
| **Scope** | Alarms on the money path. Data freshness is already well covered by the sentinel. |
| **Dependencies** | None |
| **Model/agent** | `builder` (Opus) |
| **Files/systems** | `app/deploy/macro-sentinel.service` transport (reuse), `admin/alerts.py`, `admin/key_alerts.py`, `app/billing.py` (emit points) |
| **Validation** | Trigger each condition in staging; confirm delivery |

**Acceptance criteria — not done unless** an alert reaches a human-watched channel for each of:
1. No Stripe webhook received in N hours, or webhook error rate above threshold
2. Checkout creation failures
3. `require_user` 502 rate spike (Supabase degradation)
4. **LLM spend rate above a daily threshold** — the defense-in-depth behind WS-2
5. The existing `::error::brain_gateway: … fail-open` quota line

Reuse the sentinel's existing Telegram/Discord/email transport. **Do not add an observability
vendor** — Part XXX explicitly warns against it and the transport already exists.

---

## WS-5 — Git-history secret scan

| Field | Value |
|---|---|
| **Priority** | **P0 for launch** (GATE-5) |
| **Scope** | The working tree is clean; history is unscanned. |
| **Dependencies** | None. Cheapest item on the list — do it today. |
| **Model/agent** | `general-purpose`, `model: 'sonnet'` — mechanical |
| **Files/systems** | All three repos: `Macro Dashboard`, `charting-app`, `Mastermind` |
| **Validation** | Scanner output |

**Acceptance criteria — not done unless:**
1. `gitleaks detect --log-opts="--all"` (or equivalent) has run against all three repos.
2. Every hit is triaged in a written table: false positive, or real ⇒ **credential rotated**.
3. **Do not paste any live secret into the report** — reference `file:line` and commit SHA
   only.

---

## WS-6 — Multi-worker API

| Field | Value |
|---|---|
| **Priority** | P1 — before scale (MMX-006, S-1) |
| **Scope** | Remove the single-process ceiling and deploy downtime. |
| **Dependencies** | **HARD: requires WS-2 merged first.** Extra worker processes contending on an unlocked file ledger make MMX-002/003 strictly worse. |
| **Model/agent** | `builder` (Opus) + ops |
| **Files/systems** | `app/deploy/macro-api.service:62`, `app/deploy/update.sh` (restart path) |
| **Validation** | Load test + quota-correctness re-test |

**Acceptance criteria — not done unless:**
1. `--workers N` is set and the service starts cleanly.
2. **WS-2's concurrency test is re-run and still passes with N workers** — this is the whole
   reason for the dependency, so it is the acceptance criterion, not a footnote.
3. In-process caches behaving per-worker is documented (auth cache, entitlement cache,
   throttles) with any correctness implication stated.
4. A rolling restart drops zero in-flight requests, or the doc states plainly that deploys
   remain brief downtime.

---

## WS-7 — Uniform rate limiting on open endpoints

| Field | Value |
|---|---|
| **Priority** | P2 — before scale (MMX-008, S-3) |
| **Scope** | 31 unauthenticated routes have no throttle. |
| **Dependencies** | None |
| **Model/agent** | `builder` (Opus); optional `Explore` (`model: 'sonnet'`) census first |
| **Files/systems** | `app/government_revenue.py` (24 routes), `app/hub.py` (7 routes), possibly new middleware in `app/main.py` |
| **Validation** | Flood test |

**Acceptance criteria — not done unless:**
1. Every route in those two modules is rate limited, ideally via one middleware rather than
   26 per-file decisions. Mirror the working `_allow_request` pattern in
   `app/company_intelligence.py` (which already returns 429 + `Retry-After`).
2. Limits are documented per route class, and legitimate product usage is measured against
   them first — do **not** break the dashboard to stop a scraper.
3. **Operator question answered in the PR description:** does EdgeOne provide edge rate
   limiting? If yes, the app-layer limit is defense in depth and can be looser.
4. A product decision is recorded on which of these surfaces are intentionally public
   marketing vs. subscriber value.

---

## WS-8 — Webhook claim-before-handle

| Field | Value |
|---|---|
| **Priority** | P2 (MMX-007, S-2) |
| **Scope** | Close the TOCTOU window that duplicates webhook side effects. |
| **Dependencies** | None |
| **Model/agent** | `builder` (Opus) |
| **Files/systems** | `app/billing.py` (`webhook`, `_event_seen`, `_record_event`) |
| **Validation** | Concurrent duplicate delivery test |

**Acceptance criteria — not done unless:**
1. The event id is **inserted first**; the unique-constraint rejection is what identifies a
   duplicate. Handle only after the claim succeeds.
2. A store exception means "cannot verify" ⇒ return non-2xx so **Stripe retries**. It must
   no longer fall through to processing (`_event_seen` currently returns `False` on any
   exception).
3. Two concurrent identical deliveries produce **one** set of side effects — specifically
   **one** billing email. Test it concurrently, not sequentially; sequential already works.
4. Signature verification, the threadpool hop, and recompute-from-live-Stripe are all
   preserved unchanged. **Do not refactor the reducer** — `_entitlement_from_state` is
   correct and is what makes out-of-order events safe.

---

## WS-9 — CI guard for the isolation invariant

| Field | Value |
|---|---|
| **Priority** | **P0 for launch** (GATE-6) |
| **Scope** | Protect the invariant that makes service-role DB access safe. |
| **Dependencies** | None |
| **Model/agent** | `builder` (Opus) |
| **Files/systems** | New `scripts/check_no_client_supplied_identity.py`; register in the house-law guard suite per `docs/HOUSE_LAW_CI_GUARD_SUITE.md` |
| **Validation** | Mutation test |

**Acceptance criteria — not done unless:**
1. An AST check asserts no route handler derives `user_id` (or equivalent identity) from
   request body, query params, or path params.
2. It follows the repo's existing `scripts/check_*.py` idiom and is **registered** in the
   guard suite — an unregistered guard does not run.
3. **Mutation-tested:** add a deliberately offending handler, confirm the guard goes red,
   then remove it. Registering a guard is not proof the guard works — the repo's own memory
   records this exact trap.
4. The rationale is in the script docstring: `_pg()` uses `SUPABASE_SERVICE_ROLE_KEY`, which
   bypasses RLS, so token-derived identity is the *only* thing preventing cross-tenant access.

---

## WS-10 — Naive datetime cleanup

| Field | Value |
|---|---|
| **Priority** | P2 — post-launch (MMX-010, H-1) |
| **Scope** | 3 sites resolving dates in server-local (UTC) time. |
| **Dependencies** | None |
| **Model/agent** | `builder` (Opus) — small but semantically load-bearing for signal dates |
| **Files/systems** | `engine/special_arb.py:194`, `engine/congress_members.py:155`, `engine/signal_sanity.py:344` |
| **Validation** | Test at 21:00 ET / 01:00 UTC boundary |

**Acceptance criteria — not done unless:**
1. Each site takes an explicit timezone (`ZoneInfo("America/New_York")`) or an injected
   `now`, matching the house pattern in `engine/neuralweb/world_state.py`.
2. A test pins a clock at 21:00 ET (= next-day UTC) and asserts the **ET** trading date is
   returned. The test must fail against current code.
3. Confirm whether these paths run in the evening render lane — that determines whether this
   is latent or live, and the answer belongs in the PR description.

---

## Suggested execution order

**Day 1 (parallel):** WS-5 (2h, trivial) · WS-1 (operator action started early) ·
WS-3 (0.5d) · WS-9 (3h)
**Day 2 (parallel):** WS-2 (1d) · WS-4 (1d)
**Day 3:** WS-1 restore drill executed and measured · WS-6 (after WS-2 lands)
**Post-launch:** WS-7 · WS-8 · WS-10

---

## Standing instructions for every remediation session

1. **Do not re-architect what works.** Auth (secretless verification), the entitlement model
   (one table, one writer, one reader), the billing reducer (recompute-from-live-state), the
   systemd timer architecture, and the freshness sentinel are all **verified sound**. Changes
   to them need a specific defect, not a preference.
2. **Prove the guard can see the failure.** Every fix ships with a test that **fails against
   the pre-fix code**. A green test that was green before proves nothing.
3. **Preserve deliberate fail-open decisions.** Several fail-opens here are correct and
   documented (entitlement grace for payers, quota fail-open for paying users). Make them
   *asymmetric* where guests are involved; do not delete them.
4. **Follow the ship loop** in `CLAUDE.md`: fresh worktree off `origin/main`, commit → push →
   PR → `merge-on-green` → `scripts/ci_handoff.py` → stop.
5. **Reference findings by ID** (MMX-00N) in commit messages and PR descriptions so the
   register stays traceable.
