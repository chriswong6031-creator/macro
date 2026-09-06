# Market Ontology F11 — post-vertical contract (2026-09-06)

Lane: marketontology-b4-f11-post-vertical (wave B4). Closes F00C ledger rows
MO-PAID-031, MO-PAID-032, MO-PAID-054. Records only: this document changes no
product code. It freezes the contract the F11 slices must implement AFTER the
Thesis-object vertical (MO-PAID-046/047/053) exists.

Standing law this document inherits and does not re-litigate: A7 origination ban
(`engine/neuralweb/constitution.py:95-107`), DNR:KILL-PUBLIC-INTERNALS
(`research/DO_NOT_REBUILD.md:64`), DNR:KILL-LLM-CONFIDENCE
(`research/DO_NOT_REBUILD.md:54`), CXI-R23 (chat context reads product artifacts
only), K1 evidence primitives, and the house rule (#3821) that user-facing text
never says "falsifier" or its untranslated Chinese equivalent.

## MO-PAID-031 — grounded research answers

**Scope:** a research-mode question returns an answer grounded in what the desk
already published, distinct from the Research Vault PDF library and from general
chat. It creates no new retrieval surface.

**Allowed grounding corpora (closed list — anything not named here is forbidden):**

1. **Shipped product artifacts.** Whatever the site/Terminal already serves to
   this caller: the Live Market State Packet
   (`engine/neuralweb/market_packet.py:1135` `build_packet`, resolved through the
   `MACRO_LIVE_DIR` ladder at `:86-93`) and the published JSON artifacts it
   aggregates (e.g. `site/intelligence/briefing.json`, produced by
   `scripts/build_briefing.py:27`).
2. **Tier-2 receipts and on-page disclosure** already published beside those
   artifacts (coverage, asof, correction state, null disclosure).
3. **The user's own objects.** F11 theses, versions, notes and monitors in the
   Terminal/Supabase User Plane, read under the caller's own identity with
   owner-only RLS (`MARKET_ONTOLOGY_POST_TIMEOUT_COMPLETION_ARCHITECTURE_2026-09-02.md`
   §7.2). Never another tenant's objects; never a service-role read.

The Research Vault PDF library (`app/research.py`) stays a DISTINCT surface and is
NOT merged into this corpus by this packet (F00C ledger MO-PAID-031 names it a
false-positive nearest organ).

**Forbidden corpora, by DNR key:**

- `DNR:KILL-PUBLIC-INTERNALS` (`research/DO_NOT_REBUILD.md:64`) — repo internals in
  any public/subscriber-facing answer: `context_search` / `context_open`, the
  site-semantics glossary, engine source, research documents, or any new endpoint
  serving them. The SOLE exception is the existing CXI-R23a env-only operator
  allowlist already implemented at `engine/neuralweb/brain_gateway.py:406-424`
  (`BRAIN_INTERNALS_ALLOWLIST`) with tools listed at `:346`. F11 inherits that gate
  unchanged and MAY NOT widen it, mirror it, cache it, or add a second allowlist.
- `DNR:KILL-LLM-CONFIDENCE` (`research/DO_NOT_REBUILD.md:54`) — no model-emitted
  numeric confidence anywhere in the answer: no percentage, no 0-1 score, no star
  rating, no "high/medium/low conviction" rendered as a rankable field.
- A7 (`engine/neuralweb/constitution.py:106-107`) — the answer may not originate a
  signal, score, rank, size, gate, or escalation, and may not restate a
  display-tier reading as an authoritative one.

**Authority ceiling:** `non_authoritative_assistant`. In plain words, shown to the
user: "This is a reading of what we already published. It is not a signal, not a
rating, and not advice — nothing here changes any board, rank, or alert."

**Null disclosure (printed, never fabricated):** when no allowed corpus covers the
question, the answer says so in plain words — "We don't publish anything that
answers this yet" — names what was checked, and stops. It never substitutes model
general knowledge for a missing artifact, and never says "falsifier" or
"refuted".

**Acceptance:** a research query returns a non-authoritative grounded answer,
distinct from the PDF library and from general chat, that cites only corpora 1-3,
carries the ceiling sentence, and prints the plain-word null when coverage is
absent.

## MO-PAID-032 — recurring briefs

**Single scheduling owner (no second scheduler):** the existing nightly job owner
`.github/workflows/daily.yml` (DST cron pair at `:36-37`), which already runs the
brief producers `scripts.build_session_digest` (`daily.yml:3236`) and
`scripts.build_briefing` (`daily.yml:3946`); the weekly cadence owner is
`.github/workflows/weekly.yml:4` (`0 14 * * 6`). A recurring brief is a
SUBSCRIPTION over those jobs' completion, never a new cron, never an app-side
timer or background thread, never a Supabase `pg_cron` job, never a per-user
schedule executor.

**Cadence contract.** A subscription row is
`{subscription_id, user_id, target (thesis_id | watchlist_id), cadence, delivery,
state, created_at}` where `cadence ∈ {daily_after_us_close, weekly_saturday}`
bound to the owner cron above (UTC anchors, DST handled by the owner, not by F11)
and `delivery = in_product_inbox` for v1. The producing job's completion is the
ONLY trigger; a brief is emitted at most once per user per cadence slot, keyed
idempotently on `(subscription_id, slot_asof)`.

**Failure disclosure.** When a slot cannot produce — the owner job failed or was
skipped, the artifact it reads is stale, or the user's objects are unreadable —
the brief row is written in a typed degraded state and shown with a plain-word
line: "Tonight's brief didn't run — the market read it uses wasn't rebuilt.
Nothing has been recalculated." The last good brief stays visible with its own
asof date. A missing slot is never silently skipped and never back-filled with a
synthesized brief.

**NULL — email delivery does not exist (printed, not fabricated).** There is no
wired send path: `engine/portfolio_digest.py:5` states "THE SEND PATH IS NOT WIRED,
DELIBERATELY" and `:15` that no mailer is imported; `app/mailer.py:342`
`send()` exists but is not wired to any digest. Preference UI/API + mailer wiring
is F00C row **MO-PAID-085** (ceiling `notification_only`), a separate F08 child.
Therefore MO-PAID-032 is scoped in this contract to the in-product cadence and
disclosure contract only; email/push delivery is an OPEN DEPENDENCY on MO-PAID-085
and this document claims no delivery capability.

**Authority ceiling:** `workflow_only`. The recurring brief schedules and
delivers existing published readings; it originates no signal, score or
escalation, and carries no trading authority.

**Acceptance:** a scheduled recurring brief arrives on cadence without manual
re-trigger, produced by the existing nightly/weekly owner with no second
scheduler; a slot that cannot produce shows the typed degraded state and its
plain-word line instead of a brief.

## MO-PAID-054 — chat-to-Thesis binding (write-back contract)

**Propose-only write-back.** A chat turn MAY create exactly one row class, an
amendment proposal:

```text
thesis_amendment_proposal
  proposal_id        UUID (server-generated)
  thesis_id          UUID (owner-only RLS; caller must own it)
  amended_from       UUID  -- the thesis_version_id the turn actually read
  body               text  -- prose only
  evidence_refs      list<EvidenceRef>  -- K1 pointers, never copied payload
  proposed_by        "assistant"
  state              "proposed" | "accepted" | "rejected" | "superseded"
  created_at         timestamptz (server clock)
```

`amended_from` is mandatory: a proposal that cannot name the version it read is
rejected, not written. `evidence_refs` carry K1 `EvidenceRef` pointers only
(`FABLE_A_K1_EVIDENCE_FOUNDATION_COMMISSION_WITH_AUTHENTICATED_MO_RIDER_2026-08-23.md:223-243`);
the proposal never copies a fact payload.

**Never in place.** A chat turn may not UPDATE or DELETE a `theses` head row, a
published thesis version, or any evidence row. `current_version_id` moves only
when the human publishes a new version (`…ARCHITECTURE_2026-09-02.md` §7.3).
History is immutable; a correction is a typed state on a new row, never an edit.

**Never a score.** No proposal field may carry a model-originated numeric or
ordinal judgement — no conviction, confidence, probability, rank, size, target, or
escalation (A7 `engine/neuralweb/constitution.py:106-107`;
`DNR:KILL-LLM-CONFIDENCE`). Condition monitoring rides the existing tripwire state
machine (F00C MO-PAID-047, `engine/falsifier_tripwires.py`) and no second engine
is built; user-facing text never says "falsifier" or the untranslated Chinese
term for it.

**Identity.** Reads and proposals resolve only through Stock Identity + Data OS +
Supabase auth under the caller's own session. No service-role write on behalf of a
chat turn.

**Authority ceiling:** `non_authoritative_assistant` (A7). Plain words for the
user: "The assistant can suggest a change to your thesis. Only you can publish
one."

**Acceptance:** a chat turn cites a durable user Thesis by `amended_from` and
writes at most a `proposed` amendment row; no in-place edit and no model-originated
score is reachable from any chat path; a proposal without `amended_from` is
refused with a plain-word reason.

## Open dependencies (nulls, not omissions)

| Dependency | Row | State today |
|---|---|---|
| Thesis object model (head/versions, RLS) | MO-PAID-046/047/053 | SPEC_ONLY / PARTIAL — this contract is unimplementable until it lands |
| Email/push delivery + preference sink | MO-PAID-085 | NOT_BUILT — send path deliberately unwired (`engine/portfolio_digest.py:5`) |
| Team tenancy / sharing | F12 | Not frozen; v1 is user-scoped only |
