# MARKET ONTOLOGY F13 — Personal Accuracy Ledger Spec

## §0 Header

- Date: 2026-09-06
- Lane: F13-OPS-LEARNING
- Kind: records / spec freeze

Ledger row: MO-DELTA-007 (F13-OPS-LEARNING) — authority ceiling: learning_only.
DATA NULL (2026-09-06): no user-claim store exists in this repository; nothing can be scored today and nothing may be fabricated.

## §1 The scored unit — `UserClaim` (data contract)

A JSONL record, one line per claim, append-only. Frozen field table:

| field | type | rule |
|---|---|---|
| `claim_id` | str | stable id, `sha256` of `(user_id, subject, condition, stated_at, resolves_at)` first 16 hex — `resolves_at` is included so two claims sharing a `stated_at` tick (same user, subject, condition) still mint distinct ids; same digest discipline as `engine/trial_ledger.py:61 _hash` |
| `user_id` | str | Supabase auth uid ONLY (identity gate: Stock Identity + Data OS + Supabase auth; the browser client is the bundled `templates/supabase.js`). Never an email, never a display name |
| `subject` | obj | `{"kind": "security"\|"macro_series"\|"basket", "id": "<Stock Identity id or canonical series key>"}` — resolved through Stock Identity, never a free-text ticker |
| `stated_at` | str | RFC-3339 UTC, **millisecond precision**, set server-side at submission. Immutable |
| `resolves_at` | str | RFC-3339 UTC date, **required, in the future at `stated_at`**. Immutable |
| `claim_text` | str | the user's own words, ≤280 chars, display-only, never parsed for meaning |
| `condition` | obj | `{"metric": "<owner-defined key>", "comparator": ">="\|"<="\|">"\|"<", "threshold": <float>, "owner": "<module path that produces metric>"}` — the falsifiable condition. If any field is absent the claim is `void_unscorable` |
| `stated_probability` | float\|null | `[0,1]`, **entered by the user or absent**. Never model-supplied, never model-adjusted, never defaulted |
| `evidence` | list | zero or more K1 reference/block ids validated by `lib/evidence_foundation.validate_block()` (`lib/evidence_foundation.py:1479`); an ordered multi-block composition uses a recipe validated by `validate_recipe()` (`:1695`) |
| `status` | enum | `open` → `matured` → `resolved`; plus terminal `void_unscorable`, `withdrawn`. Typed states only — a correction is a new typed state, never an in-place edit |
| `resolution` | obj\|null | `{"outcome": 1\|0\|null, "observed": <float\|null>, "resolved_at": <RFC-3339>, "resolver": "<module path>", "note": "<plain words>"}`. `outcome: null` = undetermined (data missing at maturity) and is EXCLUDED from both scores while still counting in the printed "not scorable" tally |

Corrections: an amended claim is appended as a NEW record with `supersedes: "<claim_id>"`; the superseded record keeps its own row and its own verdict. Nothing is overwritten (`engine/trial_ledger.py:253` precedent: append, never overwrite).

## §2 The score

- **Per-episode Brier contribution** — one pair per **episode** (§3), never per claim: only when the episode's carried `stated_probability` (the earliest still-live member's `stated_probability`, the same member whose outcome the episode carries) `is not None` and the episode's `resolution.outcome in (0, 1)`: `(p - y) ** 2`. Re-stating the same call ten times buys one Brier pair, exactly as it buys one hit-rate episode.
- **Aggregate Brier** — computed by `engine.validation.brier_reliability(p, y)` (`engine/validation.py:525`) over the episode-level pairs above, which returns `{}` below **30** episode pairs; the display floor mirrors `_BRIER_MIN_PAIRS = 10` (`engine/explanation_memory.py:69`), so between 10 and 29 episode pairs the surface prints the null note, not a number.
- **Hit-rate** — `resolved_hits / resolved_episodes`, episode-denominated (§3).
- **Verdict vocabulary is REUSED, not reinvented**: the six strings at `engine/explanation_memory.py:32-39`. Attribution beyond hit/miss (right-for-right-reason vs right-wrong-reason) is detail tier only.
- **No composite.** Brier and hit-rate are printed side by side, never blended into one "accuracy score" — `research/DO_NOT_REBUILD.md:51` (`DNR:KILL-FUSED-COMPOSITE`).

do_not_redo (MO-DELTA-007): no universal analyst score conflating quality, retention, alpha, or P&L.

## §3 Honest-N (episode rule)

HONEST-N: episode-level count, printed on every surface, never hidden and never rounded away.

Episode rule (frozen): claims sharing the same `user_id` + `subject.id` + `condition.metric` + `condition.comparator` + `condition.threshold` whose `[stated_at, resolves_at]` windows overlap collapse into episodes by **transitive closure**: within one key group, two claims join the same episode if their windows overlap directly, or if a chain of pairwise-overlapping claims connects them (A overlaps B, B overlaps C ⇒ A, B, C are one episode even though A and C need not themselves overlap) — this is the only partition the frozen rule admits; pairwise-only clustering that would split such a chain into two episodes is not conformant. The episode's outcome AND the episode's `stated_probability` (for the Brier pair, §2) are both taken from its earliest **still-live** member — still-live means `status` in `{open, matured, resolved}` (i.e. not `withdrawn` and not `void_unscorable`); if every member of an episode is `withdrawn` or `void_unscorable`, the episode carries no outcome or probability and is counted only in the unscorable tally (§5) — the outcome and the probability always come from the same member, never from different claims in the collapsed set. Re-stating the same call ten times at the same threshold buys one episode for both hit-rate and Brier; re-stating it at a materially different `threshold` mints a distinct episode key, so two falsifiably different calls (e.g. `SPX >= 6000` vs `SPX >= 7000`) are never collapsed. Denominators printed with the score are always **episodes**, and the raw claim count is printed beside them so the two can never be confused.

## §4 The ceiling — what this number may never be used for

CEILING (learning_only): this score never feeds a signal, a rank, a size, or a gate.

NO LEADERBOARD: no cross-user ranking, no percentile against other users, no team or company scoreboard, ever.

DEFERRED, NOT KILLED: MO-DELTA-007's own row (`…F00C_GRANULAR_CLOSURE_LEDGER_2026-09-02.csv:126`) names a second, non-ranking capability — a team-accuracy rollup — distinct from cross-user ranking. This spec permanently forbids ranking/leaderboard use of *this ledger's data* within its own contract (forbidden use 6, above) — a prohibition scoped to this spec's own forbidden-uses list, not a codebase-wide `DNR:KILL-*` registry kill (no such row is minted by this packet, and none is owed for a prohibition that binds only this spec's own contract); it does NOT adjudicate the non-ranking rollup, which stays deferred pending a separate adjudication (a future `DEC-*` or an explicit `DNR:KILL-*` row) rather than being foreclosed by this frozen spec.

DNR:KILL-LLM-CONFIDENCE — no LLM-originated number anywhere in this ledger: the model never states a probability, never grades an outcome, never adjusts a score.

Forbidden uses — the score is:
1. never an input to any signal, factor, organ state, or Neural Web artifact;
2. never an ordering key for any board, ranker, screen, or feed;
3. never a position size, weight, exposure, or allocation input;
4. never a promotion gate, permission gate, access tier, or eligibility test;
5. never an alert, escalation, or notification trigger;
6. never visible to, exported to, or aggregated with any other user's ledger to build a cross-user ranking, percentile, or scoreboard (NO LEADERBOARD, above);
7. never a pricing, billing, retention, or account-standing input.

## §5 Nulls, in plain words

The null ladder (frozen, plain-word, no statistics). Two **independently-keyed** axes — hit-rate is keyed on **resolved episodes**, calibration is keyed on **probability-carrying episode pairs** (§2) — so a user can sit in different bands on each axis at once (e.g. 40 resolved episodes but only 4 stated probabilities: full hit-rate detail, calibration still withheld):

Hit-rate axis (keyed on resolved episodes):
- 0 resolved episodes → *"Nothing has settled yet. Your first call gets checked on the day you set."*
- 1–9 resolved episodes → *"Too early to say — checked 3 of your calls so far."* (integer count only)
- ≥10 resolved episodes → hit-rate stance shown (§6 stance mapping).

Calibration axis (keyed on probability-carrying episode pairs, independent of the resolved-episode count above — this is the axis `engine.validation.brier_reliability` (§2) is actually keyed on):
- 0–29 probability pairs → the calibration reading withheld with *"Not enough settled calls yet to check how well your odds match reality."*
- ≥30 probability pairs → full detail tier available (Brier + calibration reading shown, per §2's floor).

Unscorable/undetermined claims are printed as their own line (*"{n} calls could not be checked — the data they named wasn't there."*), never deleted and never folded into the miss count.

## §6 Copy block — what the later UI packet pastes VERBATIM

<!-- GLANCE-COPY-EN:START -->
Your calls, checked.
We only check what you wrote down first: the call, the day it settles, and what would prove it wrong.
Too early to say
Mostly landing so far
Mixed so far
Not landing yet
Nothing has settled yet. Your first call gets checked on the day you set.
Checked so far: {n} of your calls.
Not enough settled calls yet to check how well your odds match reality.
{n} calls could not be checked — the data they named wasn't there.
This is a learning record. It never changes what we show you, what we rank, or what you can do here.
<!-- GLANCE-COPY-EN:END -->
<!-- GLANCE-COPY-ZH:START -->
你的判断，逐条核对。
只核对你事先写下的：判断本身、结算日期，以及什么情况算判断错了。
还看不出来
目前多数落在正确一边
目前好坏参半
目前还没落在正确一边
还没有到期的判断。第一条会在你设定的那天核对。
已核对：你的 {n} 条判断。
还没有足够的已结算判断来核对你的把握是否准确。
有 {n} 条判断无法核对——所引用的数据不存在。
这只是学习记录。它不会改变我们展示什么、如何排序，也不会改变你能做什么。
<!-- GLANCE-COPY-ZH:END -->

Stance mapping (deterministic, pre-registered, display-only — belongs in this section so the UI packet does not invent it): episodes < 10 → "Too early to say"; hit-rate ≥ 0.60 → "Mostly landing so far"; 0.40 ≤ hit-rate < 0.60 → "Mixed so far"; < 0.40 → "Not landing yet". Bands are a rendering of the user's own resolved episodes and carry no authority (§4 ceiling).

Detail tier (Tier-2 receipt, below the fold or behind a control): Brier, hit-rate, episode N vs claim N, unscorable count, the six attribution verdicts, and per-claim rows with `resolver` and `resolved_at`. Numbers and technical words are allowed **only** here.

Banned in the glance tier: `Brier`, `hit-rate`, any `%`, any p-value, any study or module name (`explanation_memory`, `trial_ledger`, `Calibration Lab`), any raw slug (`right-for-right-reason`), and the word `validated` (`scripts/check_validated_claims.py`).

## §7 Theme treatment for the later UI packet (dark and light are two art directions)

- **Dark (command center):** ledger rows on the elevated instrument surface; the stance line carries the only chromatic accent; settled/unsettled distinguished by restrained luminance depth, never by glow on the state chip; undetermined rows recede to the muted foreground rather than switching hue.
- **Light (research workspace):** white card material on the cool canvas; the same three states separated by hairline rules and a single low-elevation shadow, no glow anywhere; the stance line takes weight, not colour saturation, as its emphasis; the unscorable line stays visible at hairline weight rather than tinted.
- Intentionally different mechanisms: depth (dark: luminance; light: shadow + hairline) and emphasis (dark: accent hue; light: type weight).
- Degraded states named per theme: the "nothing settled yet" empty state must remain legible against both canvases without a bespoke background.
- Evidence matrix the UI packet owes: dark/light × EN/ZH × desktop 1440 / mobile 390.
- This packet ships **no UI**; §7 is instruction to the successor packet, not a claim of shipped pixels.

## §8 Dependencies, and what this packet does NOT do

- Blocking dependency — row key `MO-DELTA-007` (`…F00C_GRANULAR_CLOSURE_LEDGER_2026-09-02.csv:126`), `next_bounded_child` field, quoted verbatim: "DEFER — dependency the Thesis-object vertical (user claim authoring surface) before Eval OS can score it". Until it exists there is no producer, no store, and no number.
- Explicitly out of scope here: any engine module, any template, any Supabase table, any nav row, any `site/` artifact.
- Row state after this packet: MO-DELTA-007 stays `PROJECTION_ONLY` / `learning_only`; the packet closes the **contract** question for the personal ledger: within this spec's own contract, cross-user ranking/leaderboard use of this ledger's score is permanently forbidden (§4) — a prohibition scoped to this spec's own forbidden-uses list, not a `DNR:KILL-*` registry kill of the capability elsewhere in the codebase. The non-ranking team-accuracy rollup capability is explicitly DEFERRED, not killed here (§4) — a separate adjudication owns that question.
