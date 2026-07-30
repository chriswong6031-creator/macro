# Intelligence Desk V2 — robustness, bilingual depth, actionable queue (upgrade masterplan)

**Program:** Agentic Media / Intelligence Suite (IS) · **Author:** Fable · **Date:** 2026-07-29 · **Status:** BUILD (this session)
**Extends:** `INTELLIGENCE_SUITE_MASTERPLAN_BY_FABLE.md` (IS-W1/W3 slices), PR #3959 (Intelligence Desk v1), Hot Tape P2 LLM desk (#3937), Content Studio LLM-first ruling (#3945).
**Scope law:** everything here is **display-tier context infrastructure** — no promotion to authority, no new scores, rank calibration stays dark (no labeled set exists). LLMs phrase engine facts and translate; they never originate a number, signal, or escalation.

---

## §0 ACCEPTANCE GATES (top of file by law)

**A — desk core robustness, not done unless:**
1. Cross-source story merge works **with `datasketch` absent and no semantic encoder**: a claim-key registry (entity+event_class anchored, token-overlap-confirmed, TTL-bounded) aliases spine-fragmented or spine-absent items onto one desk story. Test proves: (a) Reuters + AP items about the same anchored claim within the window merge into ONE story with `source_count ≥ 2`; (b) two *different* same-ticker stories with disjoint wording stay SEPARATE; (c) spine wholly unavailable still yields stable story ids.
2. Snapshot-time honesty: `context.pace` is recomputed **at snapshot** from evidence timestamps (`New`/`Rising`/`Active`/`Cooling`); a `market` block whose `as_of` is older than `market_stale_min` is served as `null`. Test pins both.
3. Canonical drafts: at most ONE draft per (story, shape); a re-arriving draft with drifted text **replaces** its shape-mate (id may change, list length may not grow). Test pins no-churn across 5 ticks of tape-stamp drift.
4. SQLite self-heal: a corrupt/locked-beyond-retry DB is quarantined (renamed aside) and recreated; the tick continues; a start-of-line `::warning` names it. Test corrupts the file and proves recovery.
5. Desk zh: packet `headline_zh`/`brief_zh` attached daemon-side through the existing cached `translate_to_zh` seam, per-tick budget, fail-soft to EN (client keeps 英文原文 marker); merge drops a stale zh when the EN headline moved on without a fresh twin. Dark-safe when DEEPSEEK_API_KEY absent.
6. Timeline: bounded per-story `timeline` (first report / new source / stage change), cap 12, deterministic EN+zh labels, in the public payload.
7. Public-payload leak guard goes **recursive**: no key starting with `_`, no `salience`, `rank_score`, `_components`, or numeric source tier anywhere in the served JSON. Existing 12 desk tests stay green; new tests wired into the same CI pack.

**B — Content Studio approve flow, not done unless:**
1. `POST /api/marketing/intelligence/approve` exists behind the existing admin auth, takes `{story_id, draft_id}`, re-reads the served desk snapshot server-side (never trusts client text), and runs the FULL outbox chain: `banned_language` → `make_item` → `validate_item` → story-lock check → value gate → `enqueue` (id/text/near-dup guards live). Refusals return the gate name.
2. The human click IS the review gate; nothing auto-approves. Provenance records `intelligence_desk` + story_id. Publishing arm state is untouched — a queued item still waits on the sentinel/publisher exactly like every other outbox item.
3. Content Studio queue UI gains the Queue-for-X button with honest per-outcome feedback (queued / refused-by-<gate>), replaces nothing else; copy-draft stays.
4. Endpoint + gates covered by tests (auth required, gate refusal surfaces, success enqueues exactly one item, double-click idempotent via outbox id-dedup).

**C — Alpaca provider, not done unless:**
1. `press_providers` gains an `alpaca` poller: REST `https://data.alpaca.markets/v1beta1/news`, headers from `ALPACA_API_KEY_ID`/`ALPACA_API_SECRET_KEY`, cursor persisted in provider state, politeness interval ≥60s, page cap, mapped to the FeedItem shape (`id="alpaca:<id>"`, `corroboration_class="wire"`).
2. No-key or disabled → silent skip with ONE preflight notice per process, zero network. Fixture tests (recorded JSON) prove mapping, cursor advance, and dedupe against re-served items. NEVER a scraping path; official API only.
3. Config-armed but harmless: shipping `enabled: true` with keys absent must be a no-op (the VPS/Actions decide by env presence).

**D — LLM enrichment + engine context, not done unless:**
1. Draft phrasing follows the **#3937 pattern exactly**: engine facts in, model phrases, `numeric/call/hedge`-class gates reject, deterministic existing draft is the fallback; never raises; budget-capped per tick; dark-safe with no key. Only `confirmed`/`high_impact` stories spend. Output shapes: `wire` (≤280) and `analysis` (≤2 sentences, no entry/exit/sizing language). LLM drafts carry `origin:"llm"`, `requires_review: true`, and enter the same canonical per-shape slot.
2. Story-specific `why_it_matters` lines ride the same gated pass; canned per-class line remains the fallback. No new numbers may appear that are not in the packet.
3. `engine_context` lines join story tickers against repo-committed engine artifacts (congress/insider/earnings) **only when the artifact's own as_of is fresh** (stale ⇒ skip, never a stale fact); ≤3 lines, plain words, each carries its as_of. Engine-originated facts only — the LLM never writes these.
4. Tests: numeric-invention rejected, call-language rejected, no-key dark path, stale-artifact skip, zh fallback.

**E — surface v2, not done unless:**
1. news.html desk section renders: timeline (in the details fold), zh headline/brief when present, `Cooling` pace vocabulary, market chip absent when `market` is null — against the §2 contract only, textContent-only DOM writes preserved, no `.innerHTML` in the desk block (test already pins).
2. Verified with a local render: light + dark + zh + 390px screenshots; no console errors; the section's existing visual language (nxi tokens) extended, not replaced.
3. Bilingual law: every new user-facing string has EN+ZH; no raw slugs; no falsifier/refutation vocabulary anywhere.

**Ship gate (whole session):** marketing-engine pack green locally; template guards (title attr, inline JS) green; PR → `merge-on-green` label; live verification after merge; VPS daemon restart flagged to operator (systemd unit holds pre-merge code until restarted).

---

## §1 Review verdict on #3959 (what V1 got right, what it missed)

**Right:** clean speed-layer/durable-layer split; atomic snapshot; registered-gate + true 404; no score leakage (top-level); review-only drafts; XSS-safe client; publish decoupled from collection; 12 contract tests wired into CI.

**Gaps found (ranked):**
1. **Clustering degrades to a no-op silently.** Spine cross-source matching needs `datasketch` (optional dep) or a local encoder (absent by default); without them `_nearest` never fires and every item opens its own story — the desk becomes an arrival log wearing an intelligence UI. The packet fallback id (`truth_status_id|url|headline` hash) has the same failure. The corroboration layer already computes an entity+class claim key that matches differently-worded reports — the desk just never used it for identity.
2. **Frozen context chips.** `pace: "Rising"` and the market stamp freeze at packet-build; a story quiet for two days still serves them. Honesty requires snapshot-time recompute + as_of gating.
3. **Draft churn.** Draft ids hash the text; tape-stamp drift accretes near-duplicate drafts (cap 6/story) and noises the review queue.
4. **No self-heal on the SQLite store**; a corrupt file freezes the desk forever behind a healthy-looking daemon.
5. **EN-only story layer** on a bilingual-by-law site; the rail's cached zh seam was built one function away and not reused.
6. **Copy-only queue.** Content Studio shows drafts but the operator must hand-carry text to the outbox; the sanctioned human-gate click can enqueue through the full gate chain instead.
7. **Thin drafts.** Rail-only stories draft as `headline -- attribution`; the LLM desk pattern (#3937) exists precisely to phrase engine facts better, review-gated.
8. **3 sources online.** Alpaca/Benzinga keys are installed per IS-W1 and the config block exists, disabled; the highest-value corroboration add costs one poller.

## §2 Pinned payload contract (additive; schema strings unchanged)

`intelligence.story_packet/v1` gains (all optional; client must tolerate absence):

```
headline_zh: str            # cached translation of headline; absent = EN fallback
brief_zh: str               # same for brief
context.pace ∈ {New, Rising, Active, Cooling}   # recomputed at snapshot time
market: null | {...as v1}   # null when as_of older than market_stale_min at snapshot
timeline: [ {ts, kind ∈ {first_report,new_source,stage}, label_en, label_zh, source_name?} ]  # ≤12, newest first
engine_context: [ {kind ∈ {congress,insider,earnings}, line_en, line_zh, as_of} ]             # ≤3
drafts[]: {id, shape ∈ {wire,analysis,long_post}, text, status ∈ {review,needs_edit},
           characters, requires_review: true, source_url, origin ∈ {wire,llm}, updated_at}
           # canonical: at most one draft per shape per story
```

`intelligence.desk/v1` unchanged; health unchanged. Nothing user-facing may carry salience/rank/feature values — recursive leak test enforces.

Config home (already edited by Fable in this branch): `config/press_sources.yml` → `wire.intelligence.{zh_enabled, zh_per_tick, market_stale_min, pace, timeline_max, llm, engine_context}` + `alpaca` armed with env-presence guard.

## §3 Claim-registry aliasing (the clustering fix, precise)

Lives in `press_lane` (post-scoring, pre-packet) + daemon state (`state["intel_claims"]`), NOT inside `intelligence_desk` (whose import closure stays stdlib-only) and NOT as spine surgery (spine assigns pre-scoring, before `matched` exists).

```
key = claim:{event_class}:{primary_entity}        # reuses _corroboration_key's anchor
registry[key] = {story_id, first_ts, headline_tokens}
resolve(scored, spine_sid):
    key empty (no anchor)      -> spine_sid or day-bucketed headline-stub id
    key hit within ttl_h (24)  -> token-overlap sanity: Jaccard(title tokens) ≥ 0.15,
                                  RELAXED to ≥ tight_jaccard_min (0.05) inside
                                  tight_window_min (45) — the tight window LOWERS the
                                  bar, it never bypasses it (review N1: a bare OR merged
                                  two different same-ticker stories 10 min apart and
                                  presented the false merge as confirmed/multi-source)
                                  -> alias to registered story_id
                                  else -> keep own sid (two different stories, same ticker)
    SPINE PRIMACY (review N1): when the spine assigned BOTH items real story ids and
    they DIFFER, the registry never aliases them — the registry is the floor under a
    missing spine, not an override of a working one.
    KNOWN LIMIT (review N9, accepted): first_ts never refreshes on a hit, so a story
    running past ttl_h opens a second desk row; refreshing it would let merge chains
    extend unboundedly, which is the worse failure.
    key miss                   -> register current sid
```

Prune with the same TTL discipline as the corroboration ledger. The packet's `id` becomes the RESOLVED sid, so `IntelligenceStore.upsert` merges evidence across sources by construction. Spine remains the primary matcher when its backends exist; the registry is the deterministic floor.

## §4 Routing & sequencing (model law: Opus builds, Fable adjudicates)

| Wave | Files | Lane | Parallel? |
|---|---|---|---|
| A core | engine/marketing/intelligence_desk.py, press_lane.py, scripts/marketing_fastlane_daemon.py, tests | Opus `builder` | yes — with B, C |
| B approve | admin/marketing.py, admin/static/app.js, tests | Opus `builder` | yes |
| C alpaca | engine/marketing/press_providers.py, tests (config pre-edited by Fable) | Opus `builder` | yes |
| D llm+context | new engine/marketing/intelligence_llm.py + desk hook, tests | Opus `builder` | after A |
| E surface | templates/news.html.j2 | Opus `designer` | after A (contract §2 pinned) |
| Review | whole diff | Opus `reviewer` | last |

Collisions checked: no DO_NOT_REBUILD kill touched (CC-News/newsapi.org/Feedly/Google-Trends rejections untouched; Alpaca is the chartered IS-W1 free-spine adopt); publish-time daily read (#3849) untouched; outbox canonical path reused not forked; #3945 LLM-first satisfied (deterministic breaking-wire shape is the sanctioned fallback, not a template bank for planned kinds); rank_ordering stays dark.

## §5 Operator notes

1. ~~VPS daemon restart required after merge~~ — CORRECTED during build: `app/deploy/update.sh`'s press-feeds block already restarts the daemon when `engine/marketing/*` / the daemon script / `engine/news_translate.py` change on main. Code pickup is automatic; no manual step.
2. **DEEPSEEK_API_KEY** still absent in `/etc/macro-live.env` — desk zh (and the existing rail zh) stay in labeled-EN fallback until provisioned. One-line operator step, pre-existing.
3. Alpaca keys: poller arms itself only when both env vars are present — `/etc/macro-live.env` for the daemon, GitHub repo secrets for the Actions wire lane (workflow env already forwards them, inert until set).
4. **Deployed-admin delivery** (discovered during build, B2→B3): the VPS admin checkout has no authenticated git tree AND is reset `--hard` to origin every ~3 min, so approve-flow delivery to main rides the GitHub Contents API (`accounts_toggle` precedent) with sha-retry over the union-merged `items.jsonl`; the gitops rebase-push path serves authenticated local trees only.
