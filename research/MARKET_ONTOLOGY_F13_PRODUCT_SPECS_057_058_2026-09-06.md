# MARKET_ONTOLOGY_F13_PRODUCT_SPECS_057_058_2026-09-06

**Lane:** F13 (Operations / Learning / Product Reliability) · **Wave:** B2 · **Packet:** B-F13-2 · **Kind:** records
**Live surface:** **no live surface** — records only. Nothing in this packet renders, deploys, or changes a byte of `site/`.
**Closes:** ledger rows `MO-PAID-057` and `MO-PAID-058` in
`research/market_intelligence_productization/MARKET_ONTOLOGY_F00C_GRANULAR_CLOSURE_LEDGER_2026-09-02.csv` (rows 2 and 3 of that CSV, ids `MO-PAID-057`/`MO-PAID-058`), each dispositioned `DEFER — needs a product spec that does not exist` / `DEFER — needs a dedicated-channel product decision`.

## 0. Availability findings (measured in this checkout, 2026-09-06)

| Named source | Status | Proof |
|---|---|---|
| `lib/help_directory.py`, `templates/help.html.j2` | **EXISTS, merged** | `lib/help_directory.py:42` `HelpLink`; `:56` `HELP_CATEGORIES`; `:64` `HELP_LINKS`; `:177` `validate_help_directory`; `:214` `help_directory_view_model`; `templates/help.html.j2:85-88` hero block |
| `app/mailer.py` | **EXISTS, merged** | `:80` `CLASSES = ("transactional", "marketing")`; `:121` `support_to`; `:126` `is_configured`; `:139` `DuplicateKey`; `:181` `_ledger_insert`; `:342` `send(...)`; `:701` `render_email` |
| `app/support.py` | **EXISTS, merged** | `:289` `_tier_for`; `:301` `ticket_ref`; `:334` `_mail_configured`; `:349` `_notify_operator`; `:391` `_ack_submitter`; `:469` `_send_ticket_mail`; `:505` `create_ticket` |
| `engine/capability_health.py`, `config/capability_health.yml` | **DOES NOT EXIST** | `git ls-tree -r --name-only HEAD \| grep -c capability_health` → `0` against `87156` tracked paths |
| `alert_outbox` drain (an F08 delivery path) | **DOES NOT EXIST AS CODE** | repo-wide grep across `*.py/*.sql/*.j2/*.md` returns exactly one hit, a plan document: `research/MARKET_ONTOLOGY_F08_SLICE1_VERTICAL_HANDOFF_2026-09-05.md` |
| A release/changelog producer | **DOES NOT EXIST** | no `CHANGELOG*` anywhere in the tree |

**Consequence, printed not hidden:** the ONLY notification channel that exists is `app/mailer.py`. There is no second channel to choose between and no release-truth producer to read. Both specs are written against that fact. **No builder may create one** — the F13 handoff's `do_not_redo` (`agentos/handoffs/MARKET-ONTOLOGY-F13-OPS-LEARNING-RELIABILITY-FABLE-COO-2026-08-26.md:32`) forbids a second observability platform, evaluation ledger, release truth, support case system, or source scheduler; `:35`'s `danger_areas` adds false-green health, privacy leakage, vanity usage metrics.

**Title reconciliation.** The ledger rows read narrower than the packet's framing: `MO-PAID-057` asks for a priority-tier SLO / differentiated refresh (`acceptance_test`: "a PRO-tier refresh measurably completes first, logged"; `real_producer`: `.github/workflows/daily.yml` — no priority tiers); `MO-PAID-058` asks for tier-differentiated support routing/queue/SLA (`acceptance_test`: "a PRO ticket provably routes to a different queue/alert"). This spec answers the ledger rows because they are the closure target: 057's honest product is a **refresh/release disclosure**, not a sold-faster refresh; 058's honest product is **one channel, labelled**, not a second queue.

**Governing copy law:** `agentos/decisions/DEC-CHAIRMAN-FRONTEND-PLAIN-LANGUAGE-LAW-2026-09-06.md` and the measured empty-state grammar in `research/MARKET_OS_UNIFIED_DASHBOARD_PATTERN_STUDY_2026-09-06.md` §1.12: **[what is absent, as a fact] → [the rule that explains why] → [the one action that would change it]**, three sentences max, one action only, three-way null vocabulary (em dash = no number yet; a plain two-word state = cannot be produced, with the reason; a real zero = a digit).

**Provenance, printed not hidden (same rule as §0):** measured 2026-09-06 via `git ls-tree origin/main -- agentos/decisions/DEC-CHAIRMAN-FRONTEND-PLAIN-LANGUAGE-LAW-2026-09-06.md research/MARKET_OS_UNIFIED_DASHBOARD_PATTERN_STUDY_2026-09-06.md` → empty against `origin/main` at `8addc55cbd509a053abbd65e7f823e8ae479c98a`; both files exist only on `claude/marketontology-meta-ceo-b-20260906`. PR #6919 (this packet) does not carry them. **Merge-order note:** the DEC and the pattern-study §1.12 grammar must land on `main` no later than this packet, or a builder picking up Spec A/B post-merge cannot resolve the citation. **Self-contained restatement** (so the grammar does not depend on that merge landing first): the full rule is the three-arrow grammar already spelled out above, plus the three-way null vocabulary already spelled out above — nothing else from either source document is load-bearing for A6/B6/B2 below.

---

# SPEC A — MO-PAID-057 · "Refresh & release truth, disclosed not sold"

## A1. User job
"Is what I'm reading current, and did anything change since I last looked? If it's stale, say so in words I understand and tell me the one thing that would fix it."

## A2. The decision (what is NOT built)
**The tier-differentiated refresh in the ledger row is REFUSED.** A priority queue over `.github/workflows/daily.yml` is a source scheduler, banned by the F13 `do_not_redo`. Selling a faster refresh also manufactures the false-green `danger_areas` failure — a paying user believing their data is fresher than it is. Also not built: a changelog generator, release ledger, version manifest, in-app notification centre, web-push, or second delivery path. The product is **disclosure of the refresh truth that already exists**, plus an email of the same truth gated by the existing marketing opt-out preference (see A7 — this is the standing `cls="marketing"` opt-OUT model every other marketing mail already uses, not a new opt-in list).

## A3. Existing owner extended
1. The nightly build stamp already threaded through every public page: `scripts/build_public_pages.py:121-122` (the `.render(` call opens at :121; `generated_utc=generated` is the kwarg on :122) passes it into `help.html.j2`; `scripts/build_site.py:3741-3742` does the same.
2. The frozen, source-validated help directory: `lib/help_directory.py:64` `HELP_LINKS`, validated at `:177`, projected at `:214`.
3. The one mail path: `app/mailer.py:342` `send(...)`.

## A4. Files a builder touches
| File | Change |
|---|---|
| `lib/help_directory.py` | add `refresh_disclosure(root, generated_utc)` → dict (contract A5); add the EN/ZH copy tuples as module constants beside `HELP_CATEGORIES` (`:56`); no change to `HelpLink` (`:42`) or `HELP_LINKS` (`:64`) |
| `templates/help.html.j2` | one `<p class="help-refresh" data-refresh-state="{{ refresh.state }}">` inside `<header class="help-hero">` (`:85-89`), after `help-owners` (`:88`); no new section |
| `templates/_public_chrome_css.html.j2` | `.help-refresh` rule only (A8) |
| `scripts/build_public_pages.py` | inside the `.render(` call opened at `:121` (kwargs span :121-124), add `refresh=refresh_disclosure(config.ROOT, generated)` alongside the existing `generated_utc=generated` kwarg (:122) |
| `scripts/build_site.py` | same one-line addition at `:3742` |
| `scripts/build_public_pages.py` | **also** the new call site for the refresh-digest send (A7): after computing `refresh` (row above), iterate `email_segments.get("marketing_eligible")` members and call `mailer.send(template="refresh_digest", ...)` once per recipient — this is the file's existing nightly invocation via `.github/workflows/daily.yml`'s site-build step, not a new lane |
| `app/mailer.py` | no change — `render_email` (`:701`) and `send` (`:342`) as they stand; called with new args from the new site above |
| `app/email_segments.py` | no change — `get("marketing_eligible")` (`:253-258` membership rule) is the recipient source read by the new call site |
| `tests/test_help_directory.py` | extend (A9) |
| `tests/test_refresh_disclosure.py` | new (A9) |

## A5. Data contract (frozen)
```python
# lib/help_directory.py
RefreshState = Literal["fresh", "stale", "unknown"]

def refresh_disclosure(root: Path, generated_utc: str | None,
                       *, now: datetime | None = None,
                       stale_after_hours: int = 36) -> dict[str, Any]:
    """Project the one stamp the builder already has into a plain-word disclosure.

    Pure: no network, no Supabase, no git. `now` is injected for a deterministic test.
    Always returns all six keys, never a partial dict:
      state: "fresh" | "stale" | "unknown"
      stamp_utc: str | None       # raw stamp, echoed unmodified; None when unparseable
      age_hours: int | None       # None when state == "unknown" — NEVER 0
      line_en: str                # one plain sentence, <= 20 words
      line_zh: str
      action_en / action_zh: str | None   # the one action, or None when none would help
    """
```
- `generated_utc` absent/empty/unparseable → `state="unknown"`, `age_hours=None`. **`age_hours` is never `0` for an unknown stamp** — an unreadable stamp must not land on the same value as a stamp read one minute ago.
- Nothing is ever branched on a formatted string; the template reads `refresh.state`, never `refresh.line_en`.
- No tier is read here — one refresh truth, same for every user.

## A6. Plain-language copy (EN/ZH, all three states)
| state | EN | ZH | action |
|---|---|---|---|
| `fresh` | "Updated {n} hours ago. Pages refresh once a day, overnight." | "{n} 小时前更新。页面每天夜间刷新一次。" | none |
| `stale` | "Last updated {n} hours ago. The overnight refresh has not completed since then, so figures may be behind." | "上次更新在 {n} 小时前。此后夜间刷新尚未完成，数据可能滞后。" | "Check back after tomorrow's refresh." / "请在下次夜间刷新后再查看。" |
| `unknown` | "Update time not recorded for this page. Pages carry a stamp only after a completed overnight build." | "本页未记录更新时间。页面仅在夜间构建完成后才带有时间戳。" | "Check back after tomorrow's refresh." / "请在下次夜间刷新后再查看。" |

Banned words above the fold: `generated_utc`, `stale`, `state`, `SLO`, `tier`, `pipeline`, `render`, `artifact`, any slug, any raw ISO timestamp. The raw `stamp_utc` may appear only in a `title`-free hover/detail line in English only — `title=` must never carry translated text.

## A7. The notification (opt-in, mailer only)
One template, `refresh_digest`. **No existing per-user nightly digest lane exists** — measured: the marketing-class senders are `app/marketing_emails.py:562` (welcome) and `:876` (campaign), both request/campaign-driven, not a nightly step; `scripts/freshness_sentinel.py:2156` is an operator sentinel, not a user mailer. The one new call site is inside `scripts/build_public_pages.py` (A4) — that file already runs every night as part of `.github/workflows/daily.yml`'s site-build step, so this extends an EXISTING nightly step rather than standing up a new lane, scheduler, or workflow file. **Audience source:** `app/email_segments.py:253-258` `marketing_eligible` (`s.email is null and coalesce(p.marketing_opt_out, false) = false`) — the existing opt-OUT membership rule every `cls="marketing"` send already reads; no new consent surface is built.
```python
mailer.send(template="refresh_digest", cls="marketing",
            to_email=addr, subject=subj, html=html, text=text,
            idem_key=f"refresh_digest:{user_id}:{stamp_utc}", user_id=user_id)
```
- **`cls="marketing"` is mandatory.** A "what changed" email is not transactional: `app/mailer.py:20-22`'s class law says `marketing` consults `email_suppression`/`email_prefs.marketing_opt_out` and refuses to send when either says no; `transactional` never does. Mislabelling this transactional would mail people who opted out — the privacy `danger_areas` failure. `send()` also coerces an unknown class to `marketing` (`:352`), so the strict path is the default.
- **`send()`'s actual return contract (`app/mailer.py:12`, its own module docstring, verified against every literal `return` in the function body at `:359,362,371,385,403,406,411,419,426`):** exactly one of `"sent"`, `"failed"`, `"skipped_no_smtp"`, `"suppressed"`, `"queued"`, `"duplicate"` — never a seventh value, never a raised exception a caller must catch. Idempotency is per-user, per-stamp: `_ledger_insert` (`:181`) claims `idem_key` before SMTP, and a unique-violation raises `DuplicateKey` (`:139`), which `send()` returns verbatim as `"duplicate"` (`:371`) — a second call with the same key sends nothing, while the ledger is reachable.
- **Degraded path, printed not hidden:** `app/mailer.py:373-381` — when `_ledger_insert` raises anything other than `DuplicateKey` (no service-role key, network, table absent), `send()` sets `ledgered=False` and proceeds WITHOUT the idempotency guarantee, by the function's own comment, for "a support reply, an operator alert" — the same low-volume, human-facing risk this nightly digest inherits by reusing that one send path.
- **There is no batch-abort semantics, and this spec does not invent one.** Verified: no caller in `app/mailer.py` or `app/marketing_emails.py` (the campaign drain `:779` `drain_campaigns`, the parked-row drain `:918` `drain_parked`) ever inspects one recipient's `send()` result to decide whether to call `send()` for the NEXT recipient — each iterates its own membership independently, and one recipient's `"failed"` or degraded `"sent"` never stops delivery to the rest of the run. The new call site follows the same pattern: it sends to every eligible recipient in the run regardless of an individual result.
- **A failed or degraded send is retried by the next drain run, not by an abort-and-resume design.** The idem_key is `refresh_digest:{user_id}:{stamp_utc}` (A5) — tomorrow's `stamp_utc` is a fresh key, not a retry of tonight's, so a recipient missed or degraded-sent tonight is simply evaluated again tomorrow under a different key; nothing is ever double-counted as a `"duplicate"` of last night's send. Separately, the ONE queued-row case this call site can produce — a suppression-lookup failure (`_finish("queued", "suppression_lookup_failed")`, `:403`, DRAIN CONTRACT comment `:395-400`) — is completed by the existing W4 drain (`app/marketing_emails.py:918 drain_parked`) without any new code; that path already exists for every other `cls="marketing"` sender and needs no change here.
- **The body may contain ONLY the six A5 keys.** No "what changed" list — no release-truth producer exists (§0). If every digest would say only "updated", the correct build is **not to send at all**.

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
6. `tests/test_mailer.py::test_refresh_digest_is_marketing_class` — the digest call uses `cls="marketing"`; a suppressed address yields no SMTP attempt.
7. `…::test_refresh_digest_is_idempotent_per_stamp` — a second `send` with the same `idem_key` returns `duplicate` and sends nothing.
8. `…::test_refresh_digest_continues_the_run_on_ledger_failure` — with `_ledger_insert` forced to raise a non-`DuplicateKey` exception for one recipient, the build-step loop still calls `send()` for every remaining eligible recipient in the same run (no batch-abort); and `…::test_refresh_digest_key_changes_nightly` — the same user_id sent under two different `stamp_utc` values produces two distinct `idem_key`s and two independent sends, neither returning `"duplicate"` of the other.
9. Reviewer confirms **no** file under `.github/workflows/` gains a tier, priority, or queue concept — the refusal in A2 is itself an acceptance line.

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
  the headers= parameter of app/mailer.py:342 — and the user is told, in plain words, what
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
  - "app/mailer.py:342 send(..., headers: dict | None) — the label carrier already exists"
  - "agentos/handoffs/MARKET-ONTOLOGY-F13-OPS-LEARNING-RELIABILITY-FABLE-COO-2026-08-26.md:32,:35"
confidence: high
reversibility: easy
```

## B3. Existing owner extended
- `app/support.py:505` `create_ticket` — the one route.
- `:349` `_notify_operator` (operator mail), `:391` `_ack_submitter` (user ack), `:469` `_send_ticket_mail` (the background pair), `:620`-area where it is scheduled via `background_tasks.add_task`.
- `:301` `ticket_ref` — the `MX-` + 8 hex reference already printed on the success slip, the ack subject, and the admin thread.
- `app/mailer.py:121` `support_to()`, `:342` `send(..., headers=)`, `:701` `render_email`.
- `lib/help_directory.py:64` `HELP_LINKS` and `templates/help.html.j2:113`-ish the card grid.

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
1. Every claim about existing code above cites `file:line` and was read in the checkout on 2026-09-06.
2. Each spec names the existing owner it extends; neither creates an observability platform, a release-truth producer, a source scheduler, or a support case system.
3. The only notification channel used is `app/mailer.py`; `alert_outbox` and `engine/capability_health.py` are recorded as non-existent, not assumed.
4. Nulls are printed in plain words in every state table; no number, no SLA, no changelog is fabricated.
5. No product code ships in this packet. **Live proof: records only — merged path is the proof.**
