# Prophet-program decision packet — §J.9(c) + §J.10, stage semantics

**Decision owner:** the Prophet program lane (it owns `build_prophet.py` and the live card).
**Prepared by:** Fable (design lane), 2026-08-12. **Requested by:** Sol's §J.9 ruling.
**Resolves:** P0 packet §J items 9(c) and 10 — jointly, per that ruling.

Sol deferred §J.9 clause 3 (minting the six-state enum) and coupled it to §J.10, directing the
Prophet lane to determine: **(i)** whether the shipped Bottoming/Turning/Ready/Trend construct
is a separate `price_phase` dimension from the proposed
Early/Confirming/Confirmed/Aging/Extended/Invalidated `lifecycle_state`; **(ii)** whether both
dimensions deserve to survive; **(iii)** which belongs on each surface. Standing law from that
ruling: **two different concepts may not both ship under the semantic name `stage`.**

This packet answers (i) with receipts, and reframes (ii)/(iii) around a finding that changes
the question. **The design lane does not decide any of it** — §5 states plainly what is ours
and what is yours.

---

## 1. Question (i) is answered by the code: they are two dimensions

`stage` is derived from **price shape**, never from conviction:

| Link | Evidence |
|---|---|
| the card's rail reads `stage` | `templates/_prophet_card.html.j2:374,418-419` |
| `stage` is a lane lookup | `scripts/build_prophet.py:312` — `stage = _STAGE_BY_LANE.get(row.get("lane") or "", 0)` |
| the lane map | `build_prophet.py:237` — `{"bottoming":1,"recovery":2,"continuation":3,"trend":4}` |
| `lane` comes from MA/price alignment + weekly phase | `scripts/build_stock_library.py:1407-1440` (`_lane_for(align_tier, weekly_phase)`) |
| conviction exists on the same row and does **not** feed it | `build_prophet.py:364` — `edge = c.get("score_edge")` fills a separate "Edge" slot |

So Bottoming/Turning/Ready/Trend is a **price_phase**. A conviction lifecycle is a different
axis. **(i) = yes, separate dimensions — this is settled by construction, not by opinion.**

---

## 2. The finding that reframes (ii) and (iii): the estate already has FOUR stage taxonomies

The proposal was to mint a fifth. What already exists:

| # | Name | Vocabulary | Where | Status |
|---|---|---|---|---|
| 1 | `stage` (the rail) | Bottoming · Turning · Ready · Trend / 筑底 · 转向 · 就绪 · 趋势 | `build_prophet.py:237,312,383` → `_prophet_card.html.j2:418-419` | computed, **rendered to users** |
| 2 | `stage_key` | `live` · `setting_up` · `ran` · `blocked` | `_prophet_card.html.j2:375` (`data-stage`) → filters in `dashboard.html.j2:839-849,18829-18885`, `hk.html.j2:378-395` | computed, **shipped as filter state** |
| 3 | **`phase`** | `pre_trigger` · `triggered_pre_t1` · `at_t1` · `between_t1_t2` · `post_t1_failed_hold` · `at_t2` · `overtime` · `invalidated` | `engine/prophet_management.py:42-60`; humanised by `_human_state()` `:1074-1111`; published via `build_prophet.py:1257,1298` | computed, **already published** |
| 4 | Weinstein `stage_detailed` | classic 1–4 | `engine/weinstein_stage.py:303,470-586`; gates `prophet_bridge.py:152` | computed, never rendered |

**Taxonomy 3 is, semantically, the lifecycle the packet proposed to invent.** Its
`_human_state()` output includes *"High Conviction"*, *"Advancing Cleanly"*,
*"Extended — Watch Giveback"*, *"Overtime Stall"*, and *"Invalidated"* — a maturity/conviction
progression with an explicit invalidated terminal, already computed and already published.
The design packet asserted "the engine has no EARLY/CONFIRMING/CONFIRMED field"; that is true
of those **literal names**, and misleading about the **dimension**, which exists as `phase`.

Consequence: minting the six-state enum as specified would create a **fifth** vocabulary
alongside a live one that already covers the same axis. The cheaper and more honest path is to
**derive the ladder's cells from `phase`** rather than mint anything — but whether `phase`'s
cell set is the right *public* partition is a Prophet-lane call, not ours.

---

## 3. Two constraints the ruling must respect

**A re-cut of the lane taxonomy is a DATA MIGRATION, not a display change.** The board ledger
persists `lane` per row: `scripts/grade_us_board.py:756` — `"lane": r.get("lane")`, in
`data/us_board_ledger/` (`snapshots.jsonl` + `retro_grades.parquet`, one row per
as_of×lane×ticker×horizon). Historical rows carry the taxonomy as it stood when written.
*Related defect:* that line's own comment reads `# 'trend' | 'recovery' | None`, which is
**stale** — it omits the current `bottoming`/`continuation` values, so the ledger's documented
domain and its real domain already disagree.

**The ladder's partition law needs an exhaustive, disjoint cell set.** Taxonomy 1 is
exhaustive only by `.get(..., 0)` defaulting; lanes `leader` and `watch`
(`build_stock_library.py:1392,1897,4834`) fall through to `stage=0`, i.e. a setup that is on
the board but in no rail state. Any ladder built on taxonomy 1 must say what those rows are.

---

## 4. A live defect found in passing — worth your eyes regardless of the ruling

**The rail's fourth dot may be unreachable.** `stage=4` requires `lane == "trend"`, but a
repo-wide search found no current assignment of `lane="trend"` — the v2 `_lane_for`
(`build_stock_library.py:1407-1440`) returns only `bottoming`/`continuation`, `recovery` is set
explicitly at `:4811`, and the only "trend" hits in that file are a comment (`:4800`) and an
unrelated `sg["trend"]` (`:3085`). `research/entry_intel/P2_4_BOARD_CONTRACT_V2_DESIGN.md:75,83-97`
records that the legacy `lane="trend"` was relabeled by the v2 logic.

If that is right, users have been shown a **four-step tracker whose final step can never
light** — and the ledger comment above suggests the taxonomy moved without every consumer
following. **We did not confirm this against a live payload; `lane` may be set on a path we did
not trace.** Please verify against real `showcase.json` output before treating it as fact —
this is reported as a lead, not a finding.

---

## 5. Boundary — what the design lane decides, and what it does not

**Ours (already ruled by Sol, not reopened here):** the ladder is the Prophet Board's signature
device, scoped to Prophet/lifecycle-derived surfaces; the canonical-count invariant binds on
that board; the ladder's visual form is frozen in `mockups/design_system/specimen.html`.

**Yours, entirely:** whether a new field is minted at all or the ladder derives from `phase`;
what the public cell set is; whether the shipped rail is re-cut, retired, or kept as
`price_phase`; what each dimension is *named* (Sol's law only forbids two concepts sharing
`stage`); which dimension appears on card vs board vs detail; and any ledger migration.

We need exactly one thing from you to proceed: **a cell set that is exhaustive and disjoint
over live setups**, plus its EN/ZH labels. Everything else in the ladder is already frozen.

---

## 6. Options (for (ii)/(iii) — not exhaustive, and not our call)

**Option 1 — derive the ladder from `phase`; mint nothing.** No fifth vocabulary; the ladder
inherits a computed, published field. Requires deciding which `phase` values are public and
whether `pre_trigger`/`overtime` belong in a customer-facing partition.

**Option 2 — mint `lifecycle_state` as specified, and rename the rail to `price_phase`.** Two
named dimensions, both surviving, `stage` retired as a name per Sol's law. Costs a fifth
vocabulary unless `phase` is folded into it, plus §J.10's rail re-cut and a ledger migration.

**Option 3 — keep one dimension on the card, the other on the board.** `price_phase` stays on
the card (it is a price read, and the card is a price surface); the ladder carries the
lifecycle. Satisfies §G.1's one-lifecycle-vocabulary-per-card rule without retiring anything.

**Option 4 — retire the rail.** If `stage=4` is indeed unreachable (§4), the rail is already
partly broken; retiring it removes a vocabulary instead of adding one.

---

## 7. The answer that unblocks work

Please return: **(ii)** which dimensions survive; **(iii)** the surface assignment; and the
**cell set + EN/ZH labels** for the ladder. With those, docket item 6 (the Prophet board
reference) and PR-0(c) both unblock. Nothing else in the design-system chain waits on this —
Sol's re-scope already released PR-0(a)(b)(d).

## 8. Panel completeness

Prepared by the design lane from a read-only census; **not** reviewed by the Prophet program
lane (the deciding party), Handoff D's launch-readiness reviewer, or anyone who has run the
current payload. §4's unreachable-`stage=4` lead in particular is unverified against live data.
