# DeepVue W1-C — visible context compiler + effective-context receipt: production validation receipt

Status: final delivery receipt for the W1-C wave (`WS:DEEPVUE-INTELLIGENCE-WORKSPACE`),
executed under an explicit Sol → Fable COO commission. W2 remains unstarted and
unauthorized.

## 1. Outcome

When a user asks Brain something — from the Terminal or the dashboard — the exact
effective context Brain receives is now resolved deterministically (explicit request →
pinned context → active selection → ambient widget context), represented through one
canonical server-compiled `ai_context_envelope.v1`, emitted as a first-class
`context_receipt` SSE event on every routed run, persisted in the run buffer so resume
replays the original context verbatim, and rendered to the user as an
effective-context strip + "What the Brain used" inspector in the shared Brain widget.
Precedence, dropped context, stale facts, unsupported identities and refusals are all
visible in plain bilingual words. The LLM has zero authority over any of it.

## 2. Immutable source and delivery pins

- Skillpack: `51f9942733b86e550bb9169d2a43462bd28e774f` (matched Sol's review-time pin).
- Pickups: Macro `origin/main` `2c20168df5d9`; Terminal `origin/master` `04f8726` —
  both refreshed again immediately before implementation and before each landing.
- Frozen contract: `research/DEEPVUE_W1C_CONTEXT_ENVELOPE_CONTRACT_2026-08-25.md`
  (amended in-wave by the commissioning session's rulings: precedence vocabulary,
  dropped/unsupported vocabulary split, routed-run receipt scoping, echo-validation law).
- Macro PR [#6421](https://github.com/mastermindx-market-intelligence/macro/pull/6421):
  implementation head `8fcad0a38754` (post-review repair), refreshed head
  `f57d27158dd5` (update-branch over healed main), squash-merge `cdd2b99dcdde`.
- Macro PR [#6428](https://github.com/mastermindx-market-intelligence/macro/pull/6428)
  (heal 1): head `44d911a8a675`, merge `d00ca51e0f0c`.
- Macro PR [#6430](https://github.com/mastermindx-market-intelligence/macro/pull/6430)
  (heal 2): head `0081e84c2421`, merge `e79586728194`.
- Terminal PR [#473](https://github.com/mastermindx-market-intelligence/mastermind-terminal/pull/473):
  reviewed content head `6e919dbfe198`, merged head `cba38b4d84ad` (branch update with
  master; the four W1-C files byte-identical, 0-line diff), squash-merge `580de03e7a75`.
- W1-A registry digest unchanged end to end:
  `7dff09b790f9f789dfeed80781a7fb62bc138ad4bf801d81664d471c4508d4cf` (CI-pinned).
- Deployed identities verified: Macro `/opt/macro` descendant of `cdd2b99dcdde` with
  `macro-api` restart 2026-08-25 23:54:10 UTC (and subsequent pulls through the heals);
  Terminal `live = origin/master @ 580de03e7a75`, `terminal.service` restart
  2026-08-26 00:05:42 UTC (git-gated `terminal-build.sh`).

## 3. What was built

Macro (owns the contract): `engine/intelligence_workspace/context_compiler.py` — pure
deterministic compiler at the W1-A layer reusing the W1-B explicit lexer (one grammar);
`contracts/intelligence_workspace/ai_context_envelope.v1.schema.json`; gateway
compile + `context_receipt` emission for native/instant/deep lanes in stream,
non-stream and the persisted run buffer; `native_fact_receipt.effective_context`
derived from the envelope (cannot disagree); widget strip/pin/inspector in
`templates/mm_brain.js` + paired `site/` copies; deploy restart-regex extension;
CI registration in the existing `unrun-brain-gateway` job.

Terminal (adapts, never rivals): `terminal/lib/aiContext.ts` provider (origin per
mount, monotonic revision incremented exactly once per logical transition, duplicate
suppression, pinned always [] — pin state lives in the widget); TerminalShell wiring
on the exact `[active, tf]` values the Chart Bus host already uses; BrainWidget
`MM_BRAIN_CFG.getAiContext` with singleton write-through/relinquish (route-change
safe). No bus change, no proxy change, no new store.

## 4. Adversarial review and repairs

- Terminal review (Opus): REQUEST_CHANGES → BLOCKER (singleton CFG outlives its React
  owner; frozen wrong-symbol context with fresh `captured_at` would lawfully outrank
  the correct legacy symbol) repaired via live-CFG write-through + relinquish-on-
  unmount; two vacuous tests hardened and mutation-proven (frozen `captured_at`,
  origin ≤64 law). 13/13 provider tests; full vitest 3,079 green; typecheck clean.
- Macro review (Opus): REQUEST_CHANGES → BLK-1 (widget qualified receipts against its
  own minted origin instead of the origin actually sent — Terminal path structurally
  dead) and BLK-2 (native receipt precedence reason recomputed; probe-proven
  disagreement with the envelope) repaired; MAJ-1/2 (unvalidated client echoes
  violating the committed schema and carrying path-like text into run buffers) fixed
  with echo validation + hostile fixtures + leak-law assertions; MAJ-3 duplicate
  receipt double-paint deduped; NB-1 attribute-breakout charset filter; NB-3 honest
  precedence vocabulary; NB-6 docstring; NB-7 plain-word fact statuses. 1,199 tests
  green on the repaired head. All five builder deviations adjudicated ACCEPT.
- Hostile probes executed by the reviewer: forged privileged fields unreachable
  (`authority`/`effective_context` can never be client-set), byte-identical
  determinism, W1-B lane-outcome parity across five representative cases,
  malformed-block fallback never raises.

## 5. Production incidents surfaced by live proof (both healed same-session)

1. **Widget-down outage (heal 1, #6428).** Backticks inside a comment in the CSS
   template literal terminated the string; the tail became a tagged-template call of
   the stylesheet (`TypeError: "…" is not a function`) at load on every page.
   `node --check` and the full CI suite were green on the broken bytes. Caught only
   by real browser verification; healed with quotes + a dependency-free guard test
   (`tests/test_mm_brain_asset.py`) that fails on the pre-heal bytes, registered in
   CI. Admin-merged under the genuine-wedge clause on green fences/authority with the
   pack fan-out still running (packs demonstrably cannot exercise this class — the
   outage shipped through green packs); the post-merge proof run and jsdom
   mount-check are the evidence. Exposure: outage window ~50 minutes; warm caches
   self-heal via the 5-minute revalidating unversioned URL (Terminal) and page
   re-stamps (dashboard; covering render dispatched + nightly backstop).
2. **Receipt dedupe froze the strip (heal 2, #6430).** The strict-duplicate guard
   keyed on `(origin_id, context_revision)` alone; on Terminal one revision lawfully
   spans many asks, so every later receipt at an unchanged revision was discarded —
   the strip never showed a later explicit override while the wire receipt and answer
   were correct (proven live: explicit-INOD receipt at active-AAOI revision 1).
   A strict duplicate now also requires the same `request_id` (covers the SSE/done
   double delivery and resume replays). Merged by the sweeper on concluded green.

## 6. Live production proof matrix (guest principal, in-app browser)

- Explicit-vs-active: "INOD price" with AAOI active → strip "INOD · From your
  question · overrode AAOI"; wire receipt `explicit_entity_wins` /
  `explicit_over_active` with AAOI dropped at active AND ambient levels; proven on
  BOTH dashboard (widget fallback context) and Terminal (host typed context,
  host origin qualifying — post-heal-2).
- Ordinary active path: bare "price" → `active` / `active_selection` / `active_only`,
  empty dropped, receipt applied.
- Pinned path: pin via strip → bare "current stage" → "INOD · Pinned · overrode
  AAOI" with INOD's real Stage fact (Stage 2, `stage_analysis.screener`,
  as-of 2026-08-25, fresh). Explicit-beats-pin is compiler-test-proven (probe P6 and
  the frozen vocabulary); the live phrasing attempted ("AAPL current stage") is not
  in the W1-B proven-slot grammar, so it lawfully deep-routed (see §7).
- Stale: "next earnings date" → `stale (owner_stale)` with the real owner as-of
  (2026-08-06) — transport freshness never freshened the fact.
- Unsupported: "ZZZZZ price" → native `identity_unavailable`, "no fact was
  asserted", no entity minted.
- Real value fact end-to-end (Terminal→proxy→gateway→compiler→resolver):
  INOD `USD 57.17`, canonical `SEC:US-XNAS-INOD`, fingerprint `78b19f5d…`,
  registry digest exact, `envelope_source: explicit`, `ambient_used: false` —
  the five-fact parity field set (identity/value/status/as-of/fingerprint) identical
  across the resolver-built packet, the Brain receipts, and Terminal inspection;
  the CI parity test pins the same equality for all five frozen fields.
- Revision/no-loop: one watchlist click (AAOI→ETH-USD) → provider revision 1→2,
  stable, one strip transition; pin and unpin each produced exactly one transition;
  wire receipts carried the accumulated revision (3 after initial+pin+unpin).
- Inspector: "What the Brain used · Update N", four considered rows with winner and
  "overridden" marks, plain-word conditions, fact list with freshness words, footer
  "Context is resolved by fixed rules, not by the AI." / "No trading authority".
  All bilingual strings ship via the widget's L(en,zh) pairs (ZH spot-verified via
  the live bilingual degraded message; no full ZH walkthrough).
- Responsive (measured geometry, not DOM presence): 1440×900, 820×1180, 390×844 —
  strip visible and adjacent to the prompt box, zero overlap, prompt box on-screen;
  phone renders the widget as a full sheet with the strip directly above the composer.
- Guest: the entire proof ran as a guest; quota, degraded messages, and run-buffer
  behavior intact. SSE order on the wire: `run → meta → context_receipt → status →
  delta → done` with both receipts in `done`.
- Deep lane: receipt emission proven live on Terminal (deep run receipt applied to
  the strip); full deep answers were blocked by the pre-existing intermittent
  deep-provider unavailability (W1-B residual, out of scope) — the honest bilingual
  degraded message rendered.

## 7. Boundaries, residuals and unproven capabilities

1. **Signed-in production persistence/run-resume: NOT PROVEN LIVE** — no authorized
   signed-in production principal exists for this session (same external gate W1-B
   recorded). Resume-preserves-original-context is CI-proven (receipt persisted in
   the run buffer and replayed verbatim with the original revision) and the guest
   run-buffer is the same mechanism, but the signed-in path stays `BUILT_NOT_PROVEN`.
2. **Explicit-entity recognition is bounded by the W1-B proven-slot grammar** (deliberately
   unchanged): "INOD price" lexes explicit; "INOD current stage" does not, and
   lawfully deep-routes rather than guessing. For deep runs the receipt shows the
   deterministic context resolution (lexer-provable explicit only) while the deep
   model reads the full prompt text itself. Widening the grammar is future work, not
   W1-C authority.
3. **No receipt on pre-routing refusals** (empty message, research-mode rejection,
   quota exhaustion, prescreen block) and on the no-providers degraded failure —
   the first four are contract-scoped; the last is a named gap that only omits
   visibility when there is no answer at all.
4. **Cache/stamp hygiene:** `?v=`-stamped assets are HTTP-immutable; the outage
   window's broken copies age out via the Terminal's 5-minute unversioned
   revalidation and the dashboard's page re-stamps (covering render dispatched
   in-wave for heal 1; heal 2's re-stamp rides the nightly render). Fresh clients
   always receive current bytes.
5. The W1-B latency residual (warm live p95, multi-field assembly) was NOT touched —
   no cache, no alternate owner, no waterfall change. Deep-provider availability
   unchanged.
6. Terminal light theme does not exist (product is dark-only); EN/ZH supported and
   shipped bilingual.

## 8. Capability classification

`PROVEN_LIVE` for: deterministic four-level precedence with one canonical envelope;
first-class receipts on routed runs (native/instant/deep) with resume replay; visible
effective context, overrides, staleness, unsupported and refusals on dashboard and
Terminal for guest principals; typed Terminal context feed with loop-safe revisions;
five-fact parity fields across resolver/Brain/Terminal surfaces.
`BUILT_NOT_PROVEN` for: signed-in production persistence/resume (external principal
gate). No new registry, resolver, identity map, owner, rights plane, store, cache,
Brain service or retry plane was created.
