# MARKET_ONTOLOGY_F13_PRODUCT_SPECS_057_058_2026-09-06

**Lane:** F13 (Operations / Learning / Product Reliability) · **Wave:** B2 · **Packet:** B-F13-2 · **Kind:** records
**Live surface:** **no live surface** — records only. Nothing in this packet renders, deploys, or changes a byte of `site/`.
**Closes:** ledger rows `MO-PAID-057` and `MO-PAID-058` in
`research/market_intelligence_productization/MARKET_ONTOLOGY_F00C_GRANULAR_CLOSURE_LEDGER_2026-09-02.csv` (cited by id, never row number, per CLAUDE.md House laws), each dispositioned `DEFER — needs a product spec that does not exist` / `DEFER — needs a dedicated-channel product decision`.

## 0. Availability findings (measured in this checkout, 2026-09-06)

| Named source | Status | Proof |
|---|---|---|
| `lib/help_directory.py`, `templates/help.html.j2` | **EXISTS, merged** | `lib/help_directory.py:42` `HelpLink`; `:56` `HELP_CATEGORIES`; `:64` `HELP_LINKS`; `:177` `validate_help_directory`; `:214` `help_directory_view_model`; `templates/help.html.j2:85-88` hero block |
| `app/mailer.py` | **EXISTS, merged** | `:80` `CLASSES = ("transactional", "marketing")`; `:121` `support_to`; `:126` `is_configured`; `:139` `DuplicateKey`; `:181` `_ledger_insert`; `:342` `send(...)`; `:701` `render_email` |
| `app/support.py` | **EXISTS, merged** | `:289` `_tier_for`; `:301` `ticket_ref`; `:334` `_mail_configured`; `:349` `_notify_operator`; `:391` `_ack_submitter`; `:469` `_send_ticket_mail`; `:505` `create_ticket` |
| `engine/capability_health.py`, `config/capability_health.yml` | **DOES NOT EXIST** | `git ls-tree -r --name-only HEAD \| grep -c capability_health` → `0` against `87157` tracked paths (re-measured at this head, round-3 fix; supersedes the round-2 `87156` figure) |
| `alert_outbox` drain (an F08 delivery path) | **DOES NOT EXIST AS CODE** | repo-wide grep across `*.py/*.sql/*.j2/*.md` returns exactly one hit, a plan document: `research/MARKET_ONTOLOGY_F08_SLICE1_VERTICAL_HANDOFF_2026-09-05.md` |
| A release/changelog producer | **DOES NOT EXIST** | no `CHANGELOG*` anywhere in the tree |

**Consequence, printed not hidden:** the ONLY notification channel that exists is `app/mailer.py`. There is no second channel to choose between and no release-truth producer to read. Both specs are written against that fact. **No builder may create one** — the F13 handoff's `do_not_redo` (`agentos/handoffs/MARKET-ONTOLOGY-F13-OPS-LEARNING-RELIABILITY-FABLE-COO-2026-08-26.md:32`) forbids a second observability platform, evaluation ledger, release truth, support case system, or source scheduler; `:35`'s `danger_areas` adds false-green health, privacy leakage, vanity usage metrics.

## 0.5 Ruling amendments (Meta-CEO B, round-3 fix, 2026-09-06, 17:05Z)

The round-2 review (checked_head `f5dc21714541dc4016a9953b552fbf89b15df598`) found the A7 email
notification unbuildable as written. The binding ruling resolves it as follows; this section is
the amendment record the ruling asked for.

1. **A7's email send is DROPPED from V1 (BLOCKERS B1/B2).** A7 claimed `scripts/build_public_pages.py`
   "already runs every night as part of `.github/workflows/daily.yml`'s site-build step". Re-measured
   in this checkout:
   - `git grep -n "build_public_pages" -- .github/workflows/` → only `.github/workflows/public-render.yml:21`,
     a `push` **path filter**, not an invocation.
   - `.github/workflows/public-render.yml`'s `on:` (lines 6-36) = `workflow_dispatch: {}` +
     `push(branches:[main], paths:[...])`; that file has no `schedule:` block at all.
   - The one real invoker of `build_public_pages` is `scripts/ci/public_render.sh:13`
     (`python -m scripts.build_public_pages`), itself only reached by that push-triggered workflow.
   - `.github/workflows/daily.yml` does carry its own `schedule:` (`:7`), but
     `grep -n "build_public_pages\|build_site\|public_pages\|public-render" .github/workflows/daily.yml`
     returns **zero hits** — the nightly pipeline never calls this builder.
   - Repo-wide: no `.github/workflows/*.yml` combines a `schedule:` block with `mailer`,
     `marketing_emails`, `drain_campaigns`, `drain_parked`, or `refresh_digest` (checked every file).
   The chosen call site is push-triggered, not nightly, and not scheduled at all. Making the digest
   nightly needs a NEW `schedule:` block — a second scheduler, banned by the F13 handoff's
   `do_not_redo` (`:32`, cited above). **The ONLY lawful send host would be an EXISTING scheduled
   GitHub Actions invocation of the mailer; none exists in `.github/workflows/`.** (Scoped claim,
   round-4 fix: a scheduled *non-Actions* mailer caller does exist —
   `scripts/freshness_sentinel.py:2156` calls `mailer.send(...)`, VPS-cron'd per
   `.github/workflows/nightly-liveness.yml:8`'s "The VPS freshness_sentinel" comment — but it sends
   an *operator* dead-man alert, not a user-facing digest, and piggybacking a user digest onto an
   ops watchdog is not this packet's call to make. The DROP holds either way.) So A7's send is
   dropped rather than hosted on an invented lane. See the rewritten A7 below for the DEFERRED
   child this becomes.
2. **Independent second DROP reason (MAJOR-2).** A7 also named `app/email_segments.py:273 get()`
   as something a builder could "iterate ... members" from. Measured: `get()` (`:273`) returns a
   `Segment` **definition**, not a recipient iterable; the membership predicate (`:258`) is a SQL
   fragment consumed only by `where_sql()` (`:286`). The one caller that actually executes it is
   `app/marketing_emails.py:375 segment_page()`, against Supabase via the service-role credential
   path in `lib/user_prefs.py:118-123` (`SUPABASE_SERVICE_ROLE_KEY`) — and `segment_page` itself is
   invoked only from the campaign/parked-row drains in `app/marketing_emails.py`, which (per point 1)
   have no scheduled workflow host either. So even naming the real query owner does not restore a
   lawful nightly call site.
3. **`idem_key`, amended on record — supersedes the round-2 form.** The round-2 ruling's
   `sha256('release:<release_id>:<user_id>')` referenced a `release_id` this packet's own §0
   records as non-existent (no release-truth producer, no `CHANGELOG*`). Amendment:
   - That exact string, `idem_key = sha256('release:<release_id>:<user_id>')`, binds the **deferred
     child** the day a `release_id` producer exists — not before, and not to this packet.
   - **V1 (this packet) sends no email at all, so V1 carries no `idem_key`.**
   - If a later V1' ships a send on a genuinely scheduled mailer host with still no `release_id`,
     its key is day-granular: `sha256('digest:<user_id>:<YYYY-MM-DD>')` — never a raw timestamp —
     and that child's own acceptance test must assert exactly that string form.
4. **MAJOR-4 (opt-in/opt-out header contradiction) resolved by removal**, not by a wording fix:
   the contradictory header lived only in A7's now-dropped prose. The rewritten A7 below carries
   no "opt-in" language anywhere; the standing rule everywhere else in this packet (A2, B-side) is
   the existing **opt-OUT** membership rule — no new consent surface.
5. **MAJOR-1 (mailer.py:352 vs :355) resolved by removal for the same reason** — the coercion
   citation lived only in A7's dropped mailer-return-contract prose (verified: `app/mailer.py:355`
   is `cls = cls if cls in CLASSES else "marketing"`; `:352` is a docstring line). Recorded here so
   a reviewer does not go looking for a citation this rewrite deliberately removed.
6. **MINOR fixes carried through below:** A4's kwargs-span citation corrected to `:122-123`
   (`:121` is the `.render(` call opener, `:124` is the closing `),`); B3's `add_task` citation
   corrected to `app/support.py:619`; B2's mailer citation split into `:342` (`send()` def) and
   `:343` (`headers` param, not `:342`); §0's tracked-path denominator re-measured to `87157`.
7. **Round-4 review fixes (this head, precision-only, no spec-content redesign):** scoped item 1's
   negative claim to GitHub Actions and named the VPS-cron'd `scripts/freshness_sentinel.py`
   non-Actions mailer caller as an out-of-scope operator watchdog (DROP outcome unchanged); fixed
   A5's key count from six to seven and documented the previously-unspecified `root` parameter
   (reserved, unread in V1, parity with `help_directory_view_model`); added the `age_hours == 0`
   sub-hour copy rule to A5/A6 so a build under an hour old never renders "Updated 0 hours ago";
   corrected A3's `scripts/build_site.py:3741-3742` claim so it matches A4's exact `:3742` citation
   (`:3741` only computes the view-model; `:3742` alone threads the stamp); tightened B3's hedged
   `templates/help.html.j2:113`-ish citation to the exact `:112-114` span.

**Title reconciliation.** The ledger rows read narrower than the packet's framing: `MO-PAID-057` asks for a priority-tier SLO / differentiated refresh (`acceptance_test`: "a PRO-tier refresh measurably completes first, logged"; `real_producer`: `.github/workflows/daily.yml` — no priority tiers); `MO-PAID-058` asks for tier-differentiated support routing/queue/SLA (`acceptance_test`: "a PRO ticket provably routes to a different queue/alert"). This spec answers the ledger rows because they are the closure target: 057's honest product is a **refresh/release disclosure**, not a sold-faster refresh; 058's honest product is **one channel, labelled**, not a second queue.

**Governing copy law:** `agentos/decisions/DEC-CHAIRMAN-FRONTEND-PLAIN-LANGUAGE-LAW-2026-09-06.md` and the measured empty-state grammar in `research/MARKET_OS_UNIFIED_DASHBOARD_PATTERN_STUDY_2026-09-06.md` §1.12: **[what is absent, as a fact] → [the rule that explains why] → [the one action that would change it]**, three sentences max, one action only, three-way null vocabulary (em dash = no number yet; a plain two-word state = cannot be produced, with the reason; a real zero = a digit).

**Provenance, printed not hidden (same rule as §0):** measured 2026-09-06 via `git ls-tree origin/main -- agentos/decisions/DEC-CHAIRMAN-FRONTEND-PLAIN-LANGUAGE-LAW-2026-09-06.md research/MARKET_OS_UNIFIED_DASHBOARD_PATTERN_STUDY_2026-09-06.md` → empty against `origin/main` at `8addc55cbd509a053abbd65e7f823e8ae479c98a`; both files exist only on `claude/marketontology-meta-ceo-b-20260906`. PR #6919 (this packet) does not carry them. **Merge-order note:** the DEC and the pattern-study §1.12 grammar must land on `main` no later than this packet, or a builder picking up Spec A/B post-merge cannot resolve the citation. **Self-contained restatement** (so the grammar does not depend on that merge landing first): the full rule is the three-arrow grammar already spelled out above, plus the three-way null vocabulary already spelled out above — nothing else from either source document is load-bearing for A6/B6/B2 below.

---

# SPEC A — MO-PAID-057 · "Refresh & release truth, disclosed not sold"

## A1. User job
"Is what I'm reading current, and did anything change since I last looked? If it's stale, say so in words I understand and tell me the one thing that would fix it."

## A2. The decision (what is NOT built)
**The tier-differentiated refresh in the ledger row is REFUSED.** A priority queue over `.github/workflows/daily.yml` is a source scheduler, banned by the F13 `do_not_redo`. Selling a faster refresh also manufactures the false-green `danger_areas` failure — a paying user believing their data is fresher than it is. Also not built in V1: a changelog generator, release ledger, version manifest, in-app notification centre, web-push, second delivery path, **or an email digest** — see A7, DROPPED from V1 (no lawful scheduled mailer host exists in this repo; see Ruling amendments §0.5). **V1 ships PULL-only**: disclosure of the refresh truth that already exists, read on `/help.html` — the user sees it by visiting the page; V1 pushes nothing to anyone by email.

## A3. Existing owner extended
1. The nightly build stamp already threaded through every public page: `scripts/build_public_pages.py:121-124` (the `.render(` call opens at :121; `generated_utc=generated` and `**help_vm` are the two kwargs, spanning :122-123; the call closes at :124) passes it into `help.html.j2`. `scripts/build_site.py` does the analogous work in two steps, not one line: `:3741` computes the view-model consumed by the render call (`vm = help_directory_view_model(config.ROOT)`), and `:3742` is the line that actually threads the stamp (`generated_utc=generated`) — matching A4's citation of `:3742` alone as the one-line addition site.
2. The frozen, source-validated help directory: `lib/help_directory.py:64` `HELP_LINKS`, validated at `:177`, projected at `:214`.
3. `app/mailer.py:342` `send(...)` remains the one mail path in the repo, used by Spec B (support ticket mail) — V1 of Spec A does not call it (A7).

## A4. Files a builder touches
| File | Change |
|---|---|
| `lib/help_directory.py` | add `refresh_disclosure(root, generated_utc)` → dict (contract A5); add the EN/ZH copy tuples as module constants beside `HELP_CATEGORIES` (`:56`); no change to `HelpLink` (`:42`) or `HELP_LINKS` (`:64`) |
| `templates/help.html.j2` | one `<p class="help-refresh" data-refresh-state="{{ refresh.state }}">` inside `<header class="help-hero">` (`:85-89`), after `help-owners` (`:88`); no new section |
| `templates/_public_chrome_css.html.j2` | `.help-refresh` rule only (A8) |
| `scripts/build_public_pages.py` | inside the `.render(` call opened at `:121`, add `refresh=refresh_disclosure(config.ROOT, generated)` as a new kwarg alongside the existing two kwargs, which span `:122-123` (`generated_utc=generated,` at `:122`, `**help_vm,` at `:123`; the call closes at `:124`) |
| `scripts/build_site.py` | same one-line addition at `:3742` |
| `tests/test_help_directory.py` | extend (A9) |
| `tests/test_refresh_disclosure.py` | new (A9) |

**Not touched by V1:** `app/mailer.py`, `app/email_segments.py` — the email call site A7 originally proposed is dropped (see A7).

## A5. Data contract (frozen)
```python
# lib/help_directory.py
RefreshState = Literal["fresh", "stale", "unknown"]

def refresh_disclosure(root: Path, generated_utc: str | None,
                       *, now: datetime | None = None,
                       stale_after_hours: int = 36) -> dict[str, Any]:
    """Project the one stamp the builder already has into a plain-word disclosure.

    Pure: no network, no Supabase, no git. `now` is injected for a deterministic test.
    `root` is accepted for signature parity with `help_directory_view_model(root, ...)`
    (`lib/help_directory.py:214`) and is reserved for a future on-disk release-truth read;
    V1 does not read anything under it — passing any `Path`, including one that does not
    exist, must not change the return (see A9's acceptance test for this).
    Always returns all seven keys, never a partial dict:
      state: "fresh" | "stale" | "unknown"
      stamp_utc: str | None       # raw stamp, echoed unmodified; None when unparseable
      age_hours: int | None       # None when state == "unknown" — NEVER 0
      line_en: str                # one plain sentence, <= 20 words
      line_zh: str
      action_en / action_zh: str | None   # the one action, or None when none would help
    """
```
- `generated_utc` absent/empty/unparseable → `state="unknown"`, `age_hours=None`. **`age_hours` is never `0` for an unknown stamp** — an unreadable stamp must not land on the same value as a stamp read one minute ago.
- When the real elapsed time is under one hour, `age_hours` legitimately reports a true integer `0` (not a null) for `state="fresh"`; `line_en`/`line_zh` then read **"Updated less than an hour ago."** / **"不到一小时前更新。"** rather than interpolating `{n}=0` — the `{n}` form in A6 applies only once `age_hours >= 1`. A real `0` stays a digit (permitted by the three-way null vocabulary), it is just not spoken as "0 hours ago".
- Nothing is ever branched on a formatted string; the template reads `refresh.state`, never `refresh.line_en`.
- No tier is read here — one refresh truth, same for every user.

## A6. Plain-language copy (EN/ZH, all three states)
| state | EN | ZH | action |
|---|---|---|---|
| `fresh` | "Updated {n} hours ago. Pages refresh once a day, overnight." | "{n} 小时前更新。页面每天夜间刷新一次。" | none |
| `stale` | "Last updated {n} hours ago. The overnight refresh has not completed since then, so figures may be behind." | "上次更新在 {n} 小时前。此后夜间刷新尚未完成，数据可能滞后。" | "Check back after tomorrow's refresh." / "请在下次夜间刷新后再查看。" |
| `unknown` | "Update time not recorded for this page. Pages carry a stamp only after a completed overnight build." | "本页未记录更新时间。页面仅在夜间构建完成后才带有时间戳。" | "Check back after tomorrow's refresh." / "请在下次夜间刷新后再查看。" |

**Sub-hour edge case (A5):** when `age_hours == 0`, the `fresh` row above is not spoken with `{n}=0` — `line_en` reads "Updated less than an hour ago. Pages refresh once a day, overnight." (ZH: "不到一小时前更新。页面每天夜间刷新一次。"); the `{n}` interpolation shown in the table applies only once `age_hours >= 1`.

Banned words above the fold: `generated_utc`, `stale`, `state`, `SLO`, `tier`, `pipeline`, `render`, `artifact`, any slug, any raw ISO timestamp. The raw `stamp_utc` may appear only in a `title`-free hover/detail line in English only — `title=` must never carry translated text.

## A7. The notification — DROPPED from V1 (deferred)
**Not built in V1.** Round-3 binding ruling (B1/B2): the ONLY lawful send host would be an EXISTING
scheduled invocation of the mailer, and none exists — see Ruling amendments §0.5 for the full
grep evidence (no `schedule:`-bearing workflow invokes `build_public_pages`, `mailer`,
`marketing_emails`, or any drain). Making the digest nightly would require a NEW `schedule:` block,
a second scheduler forbidden by the F13 handoff's `do_not_redo` (`:32`). This spec does not add one.

**V1 ships PULL-only**: the refresh-truth line on `/help.html` (A1-A6, A8, A9), no email
counterpart, no new consent surface, no `idem_key` (there is no send to key).

**The email digest is DEFERRED**, recorded as a child gated on BOTH:
(a) a release-truth producer (§0 confirms none exists today — no `CHANGELOG*`, no version manifest);
(b) a scheduled mailer host (a `schedule:`-bearing workflow already, or separately authorized to,
invoke the mailer — this packet authorizes none).

**`idem_key` for the deferred child (amended, §0.5):** `sha256('release:<release_id>:<user_id>')`,
binding the day a `release_id` producer exists. If a later V1' instead ships a send on a genuinely
scheduled mailer host with still no `release_id`, its key is day-granular —
`sha256('digest:<user_id>:<YYYY-MM-DD>')`, never a raw timestamp.

**Reference notes for the deferred child's future author (non-normative for V1 — verified facts
about the one mail path, kept so the next builder does not re-derive them):**
- Template would be `refresh_digest`; audience source would be `app/email_segments.py:258`
  `marketing_eligible` (`s.email is null and coalesce(p.marketing_opt_out, false) = false`) via
  the query owner `app/marketing_emails.py:375 segment_page()` — the existing opt-OUT membership
  rule every `cls="marketing"` send already reads; no new consent surface.
- `cls="marketing"` would be mandatory: `app/mailer.py:20-22`'s class law says `marketing`
  consults `email_suppression`/`email_prefs.marketing_opt_out` and refuses to send when either
  says no; `transactional` never does. `send()` coerces an unknown class to `marketing` at `:355`
  (`cls = cls if cls in CLASSES else "marketing"`), so the strict path is the default.
- `send()`'s actual return contract (`app/mailer.py:12` module docstring, verified against every
  literal `return` in the function body at `:359,362,371,385,403,406,411,419,426`): exactly one of
  `"sent"`, `"failed"`, `"skipped_no_smtp"`, `"suppressed"`, `"queued"`, `"duplicate"` — never a
  seventh value, never a raised exception a caller must catch. `_ledger_insert` (`:181`) claims
  `idem_key` before SMTP; a unique-violation raises `DuplicateKey` (`:139`), returned verbatim as
  `"duplicate"` (`:371`).
- Degraded path (`app/mailer.py:373-381`): when `_ledger_insert` raises anything other than
  `DuplicateKey`, `send()` sets `ledgered=False` and proceeds without the idempotency guarantee.
- No caller in `app/mailer.py` or `app/marketing_emails.py` (`:779 drain_campaigns`,
  `:918 drain_parked`) inspects one recipient's result before calling `send()` for the next — no
  batch-abort semantics exist to inherit or invent.
- **The body may contain ONLY the seven A5 keys.** No "what changed" list — no release-truth producer
  exists (§0). If every digest would say only "updated", the correct build is not to send at all —
  this is the terminating clause the deferred child inherits unchanged from the round-2 draft.

## A8. Theme treatment
`.help-refresh` is one line of text inside the existing public-chrome hero (anonymous/corporate nav family — no third header).
- **DARK (command center):** renders at the existing muted body token, one step below `.help-owners`; `stale`/`unknown` add a 2px left hairline in the existing warning token at ~60% alpha. No glow, no badge, no pill — a factual line, not an alert.
- **LIGHT (research workspace):** same geometry and words; the left rule becomes a 1px hairline in the light warning token on the white surface, and the muted text steps one level darker to clear 4.5:1 on the cool canvas. Light does not inherit the dark alpha value — an alpha-muted rule that reads as depth on dark reads as "unloaded" on white.
- **Intentionally different:** dark carries the state on a luminance step; light carries it on hairline weight plus text darkness. Never color alone — the words carry the state, which is why `unknown` and `stale` have distinct sentences rather than distinct colors.
- Evidence matrix required of the implementing builder (not of this records packet): dark/light × EN/ZH × 1440 / 390, `/help.html`.

## A9. Acceptance tests
1. `tests/test_refresh_disclosure.py::test_unparseable_stamp_is_unknown_not_zero` — `refresh_disclosure(root, "")["age_hours"] is None`, `state == "unknown"`, no returned line contains a digit `0` for age.
2. `…::test_states_are_exhaustive_and_bilingual` — all three states return non-empty `line_en` and `line_zh`, and `line_zh != line_en`.
3. `…::test_copy_carries_no_machine_words` — none of `{"generated_utc","stale","SLO","tier","pipeline","artifact","refresh_disclosure"}` appears in any EN/ZH line.
4. `tests/test_help_directory.py::test_help_page_prints_refresh_state` — builds the page via the real builder, asserts `data-refresh-state=` present with one of the three literals, and the raw ISO stamp does NOT appear in the hero text.
5. `…::test_missing_stamp_still_renders_the_page` — `generated_utc=None` still renders with the `unknown` sentence, never a blank/crash/false "just now".
6. `…::test_root_parameter_is_unread` — calling `refresh_disclosure(root=<nonexistent Path>, generated_utc=<same fixed stamp>)` and `refresh_disclosure(root=<real repo root>, generated_utc=<same fixed stamp>)` return byte-identical dicts — `root` is accepted but never read in V1.
7. `…::test_sub_hour_age_reads_as_less_than_an_hour` — `age_hours == 0` with `state == "fresh"` renders the literal "Updated less than an hour ago." / "不到一小时前更新。" sentence, never "Updated 0 hours ago."
8. Reviewer confirms **no** file under `.github/workflows/` gains a `schedule:` block, tier, priority, or queue concept; that `app/mailer.py` and `app/email_segments.py` are byte-unchanged by this packet; and that `scripts/build_public_pages.py` / `scripts/build_site.py` gain only the `refresh=` kwarg — no new mailer call site, no new consent surface. The A2/A7 refusal (email dropped from V1) is itself the acceptance line.

---

# SPEC B — MO-PAID-058 · "One support channel, tier-labelled not tier-queued"

## B1. User job
"Something is wrong or I don't understand something. I want one obvious place to ask, a reference I can quote back, and an honest statement of what happens next — including if the honest answer is 'we don't promise a time'."

## B2. DEC-shaped decision block (liftable into `agentos/decisions/` verbatim)
```yaml
key: F13-SUPPORT-CHANNEL-IS-THE-EXISTING-TICKET-ROUTE
question: >
  MO-PAID-058 asks for a "dedicated channel" with tier-differentiated routing, queue and SLA.
  Which channel is it, and what is built?
answer: >
  The dedicated channel IS the support ticket route that already exists —
  POST /api/support/ticket (app/support.py:505) rendering to /support.html, reached from the
  Help card in the anonymous nav family and from the help directory (lib/help_directory.py:64).
  Nothing new is stood up. The only change is that the tier already captured at submission
  time (app/support.py:289 _tier_for, stored in the ticket row) becomes VISIBLE to the operator
  as a routing LABEL on the notification mail — a subject prefix and an X-MX-Queue header via
  the headers= parameter of app/mailer.py:343 (send() def opens at :342) — and the user is told, in plain words, what
  actually happens next. No second queue, no SLA promise, no response-time number.
rationale: >
  The F13 handoff's do_not_redo forbids a support case system. A second queue with an SLA
  IS that system: it needs assignment, escalation, breach tracking and an on-call rota, none
  of which exist, and a promised response time we cannot measure is a vanity metric. A label
  costs one header and is true on the day it ships. The user-visible half — one channel, one
  quotable reference (MX-XXXXXXXX, app/support.py:301), one honest sentence about what happens
  next — is the whole product benefit; the queue was never the benefit.
alternatives:
  - option: "A separate PRO inbox / second mailbox."
    why_not: "Two mailboxes with one operator is one mailbox with a sorting bug; the tier label achieves the same triage with zero new surface."
  - option: "Third-party helpdesk (Zendesk/Intercom/Front)."
    why_not: "Literally the banned support case system; also exports customer email + tier to a new processor (privacy leakage)."
  - option: "Live chat / in-app messaging centre."
    why_not: "Implies a staffed response we cannot honour; no second delivery channel exists (alert_outbox does not exist) and no presence model."
  - option: "Publish an SLA (e.g. 'PRO: 4 business hours')."
    why_not: "Unmeasurable today — there is no response-time instrument. An unverifiable promise is the false-green failure this lane exists to prevent."
evidence:
  - "app/support.py:289 _tier_for; tier snapshot read but never routed (matches ledger MO-PAID-058 missing_contract)"
  - "app/mailer.py:342 send() def; :343 headers: dict | None = None — the label carrier already exists"
  - "agentos/handoffs/MARKET-ONTOLOGY-F13-OPS-LEARNING-RELIABILITY-FABLE-COO-2026-08-26.md:32,:35"
confidence: high
reversibility: easy
```

## B3. Existing owner extended
- `app/support.py:505` `create_ticket` — the one route.
- `:349` `_notify_operator` (operator mail), `:391` `_ack_submitter` (user ack), `:469` `_send_ticket_mail` (the background pair), `:619` `background_tasks.add_task` scheduling that pair.
- `:301` `ticket_ref` — the `MX-` + 8 hex reference already printed on the success slip, the ack subject, and the admin thread.
- `app/mailer.py:121` `support_to()`, `:342` `send(...)` def / `:343` `headers: dict | None`, `:701` `render_email`.
- `lib/help_directory.py:64` `HELP_LINKS` and `templates/help.html.j2:112-114` the card grid (`:112` the entry loop, `:113` the `entry.state == 'complete'` branch, `:114` the card anchor).

## B4. Files a builder touches
| File | Change |
|---|---|
| `app/support.py` | in `_notify_operator` (`:349`) compute `queue = _queue_label(tier)` and pass `headers={"X-MX-Queue": queue}` plus a `[{queue}]` subject prefix to `mailer.send`. Add `_queue_label(tier: str \| None) -> str` near `_tier_for` (`:289`). `_send_ticket_mail` (`:469`) already carries `tier` in its signature — thread it through to `_notify_operator`'s call site. |
| `app/support.py` | in `_ack_submitter` (`:391`) add ONE plain sentence (B6) to the ack body. No tier is named to the user. |
| `lib/help_directory.py` | add one `HelpLink` for the support channel to `HELP_LINKS` (`:64`), category `"account"` |
| `templates/help.html.j2` | no change — the existing card loop renders both the `complete` and `unknown` shapes already |
| `tests/test_support_api.py`, `tests/test_help_directory.py`, `tests/test_mailer.py` | extend (B7) |
| Anything else | not touched — no new route, no new table, no new template, no third nav header |

## B5. Data contract (frozen)
```python
# app/support.py
_QUEUE_LABELS = {"pro": "PRO", "plus": "PLUS"}

def _queue_label(tier: str | None) -> str:
    """Operator-facing triage label. NEVER shown to the user, never an SLA.

    Unknown/missing/unresolvable tier -> "STANDARD". A failed lookup and a genuinely
    standard user land on the same operator label on purpose: the operator must not read
    a lookup failure as a paying customer. The failure is already visible in the ticket
    row's tier column, which stays None.
    """
```
The help-directory entry:
```python
HelpLink(id="contact-support", category="account",
         label_en=<exact string present in templates/support.html.j2>,
         label_zh=<exact ZH string present in the same file>,
         source_template="templates/support.html.j2",
         href="support.html")
```
**Constraint the builder must satisfy, not work around:** `lib/help_directory.py:146` `_validate_source_labels` requires both labels to appear in the named source template, `:159` `_validate_local_target` requires the target to resolve, `:128` `_is_approved_href` permits only a relative href or the frozen sign-in URL. `site/support.html` is a real, public build output, so `href="support.html"` is legitimate. **If the exact label strings are not present in `templates/support.html.j2`, the builder does NOT edit the validator and does NOT invent a label** — it either uses the strings that ARE there, or ships the entry as `state="unknown"` with `status_en`/`status_zh` (also forbidding an href on an unknown entry).

## B6. Plain-language copy (EN/ZH, every state)
| Surface / state | EN | ZH |
|---|---|---|
| Help card, entry available | "Contact support" + existing `Available` chip | "联系支持" + "可用" |
| Help card, entry unknown | status: "Not available yet" | "暂未开放" |
| Ack email, what happens next | "Your message reached us. Quote {MX-XXXXXXXX} in any reply and we can find it. A person reads every message; we do not promise a response time." | "我们已收到您的留言。回复时请附上 {MX-XXXXXXXX}，我们即可找到它。每条留言都有人阅读；我们不承诺回复时限。" |
| Mail relay off (`_mail_configured` false) | "Your message was saved with the reference {MX-XXXXXXXX}, but our email is not sending right now, so you will not get a confirmation email. The reference still works." | "您的留言已保存，编号 {MX-XXXXXXXX}；但我们的邮件当前无法发送，因此您不会收到确认邮件。该编号仍然有效。" |
| Rate-limited (`_rate_ok`) | "Too many messages from this connection in the last hour. Wait an hour and send again; nothing you already sent was lost." | "过去一小时内来自此连接的留言过多。请一小时后再试；已发送的内容不会丢失。" |

**"We do not promise a response time" is the required null** — the plain-word disclosure that replaces the SLA the ledger row asked for. It may not be softened into "we aim to reply quickly" — that is an unmeasured promise. The word `tier`, the tier value, and the queue label are never shown to the user in any language.

## B7. Acceptance tests
1. `tests/test_support_api.py::test_operator_mail_carries_the_queue_label` — a ticket from a PRO-entitled user produces operator mail whose `headers` contain `X-MX-Queue: PRO` and whose subject starts with `[PRO]`; the user's ack contains neither string.
2. `…::test_tier_lookup_failure_labels_standard_not_pro` — forcing `_tier_for` to raise yields queue label `STANDARD` and a persisted `tier` column of `None` — a failed lookup must never be upgraded into a paying label.
3. `…::test_no_second_queue_exists` — `mailer.support_to()` is the only destination for every tier: one address, one channel.
4. `…::test_ack_states_no_response_time_promise` — the ack body contains the exact null sentence in the request language and none of `{"SLA","hours","business day","priority","tier","PRO"}`.
5. `…::test_mail_off_still_returns_a_reference` — with `_mail_configured()` false, the route still returns a valid `MX-` reference and the degraded sentence; the ticket is never silently dropped.
6. `tests/test_help_directory.py::test_support_entry_is_source_validated` — the new `HELP_LINKS` entry passes `validate_help_directory` unmodified and the rendered page contains `id="help-contact-support"`.
7. Reviewer confirms zero new routes in `app/`, zero new tables, zero third-party support integrations, and `templates/_public_nav.html.j2` is unchanged — no third header, no new nav item.

## B8. Theme treatment
No new component. The support entry renders through the existing `.help-card` shapes under the existing public chrome. **DARK:** existing card material, existing `Available`/status chip. **LIGHT:** existing light card material; the `unknown` status chip must read as a factual label on white, not a disabled ghost — if the inherited light chip is illegible the builder **stops and escalates** rather than inventing a new token. Evidence matrix if any pixel moves: dark/light × EN/ZH × 1440/390 on `/help.html`.

---

## C. Packet-level acceptance (records)
1. Every claim about existing code above cites `file:line` and was re-read in this checkout on 2026-09-06 for the round-3 fix (head after this commit).
2. Each spec names the existing owner it extends; neither creates an observability platform, a release-truth producer, a source scheduler, or a support case system.
3. V1 ships no notification email at all — Spec A's digest is DEFERRED (A7/§0.5), gated on a release-truth producer and a scheduled mailer host, neither of which this packet builds. `app/mailer.py` remains the one channel used elsewhere in this packet (Spec B's ticket mail, unchanged); `alert_outbox` and `engine/capability_health.py` are recorded as non-existent, not assumed.
4. Nulls are printed in plain words in every state table; no number, no SLA, no changelog is fabricated.
5. No product code ships in this packet. **Live proof: records only — merged path is the proof.**
