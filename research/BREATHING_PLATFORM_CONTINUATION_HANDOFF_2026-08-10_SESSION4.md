# Breathing Platform — continuation handoff (2026-08-10, session 4 close)

**Program:** `research/BREATHING_PLATFORM_MASTERPLAN_BY_FABLE.md` (operator-RATIFIED
2026-08-08). Prior: session 3 `…HANDOFF_2026-08-09_SESSION3.md` (#5134 + #5155).
Run the program as a session chain over the masterplan + this doc.

Session 4 charter: **build the card renderer** (session 3's §1.1 ruling) and finish
out W-L1.

---

## §0 START HERE

1. **Four PRs are built, reviewed, and DELIBERATELY UNARMED. Re-arm them as a wave.**
   They were disarmed at 05:54 in one batch by **another session repairing GitHub**
   (operator-confirmed). Nothing is wrong with any of them. Re-arm once that repair
   lands:
   ```
   gh pr edit 5217 --add-label merge-on-green   # payload  (engine)
   gh pr edit 5220 --add-label merge-on-green   # receipt  (nightly wiring)
   gh pr edit 5222 --add-label merge-on-green   # SLA      (sentinel)
   gh pr edit 5223 --add-label merge-on-green   # renderer (client, flagship UI)
   ```
   **#5223 was armed AFTER that sweep and I disarmed it myself** to match, rather
   than leave one exception for the repairing session to clean up. It is reviewed
   and approved (review comment on the PR); it is not held on quality.

2. **#5217 and #5220 both edit `tests/test_close_pass_lane.py`.** Whichever merges
   second will likely need a conflict resolution. Expect it; it is not a defect.

3. **Merge order matters exactly once.** #5223 (renderer) is INERT until #5217
   (payload) lands — it reads `board.cards`, which nothing emits today. So #5223
   cannot show anything wrong on its own, but **#5217 must not land without the
   runway fix it now carries** (§3). Landing all four together is simplest.

---

## §1 What shipped this session

| PR | What | State |
|---|---|---|
| **#5213** | Spec **§10** — the provisional CARD contract | **MERGED** |
| **#5217** | Payload: `cards[]` on `board_state` + CAS + the runway fix | OPEN, unarmed |
| **#5220** | The confirmation receipt reaches the render (State 2) | OPEN, unarmed |
| **#5222** | The 18:30 SLA measures what the reader sees | OPEN, unarmed |
| **#5223** | The client-side card renderer (flagship UI) | OPEN, unarmed, **reviewed** |

### §1.1 The renderer, in one line
The evening board now renders real cards client-side off the already-paywalled
`live/prophet_live.json`, with **no number in the score slot** — `ROOM
Ample/Some/Thin/Not checked` carries the stance instead. 17 committed crops in
`mockups/refs/breathing-platform/wl1d_shots/`.

---

## §2 The three rulings that shaped it (spec §10, now on main)

1. **Publication mechanism — client-side, settled by measurement not preference.**
   Server-side re-render is closed: `closing-bell.yml` is the only evening render
   lane, measures **109 min behind an 81-min spine landing ~17:55 ET against an
   18:30 SLA**, and deliberately excludes `build_prophet`. `close-pass.yml`'s own
   header already reasoned this out.
2. **The live plane is already gated** — verified three ways (absent from
   `@vps_public_live`, absent from `@reg_asset`'s exemption list, absent from the
   Caddyfile entirely ⇒ falls inside `@reg_asset`'s "registration + paywall
   checks"). This retires #3391 **for this path only**. The full
   `us_board_provisional.json` stays non-public. **If anyone ever adds a top-level
   `/live/*` file_server, this reasoning dies with it.**
3. **No 100-scale number on a provisional card.** The board scores **40 of 100**
   weight points. The partial's existing `edge`/`edge_txt` fallback expresses that
   with zero new markup. Renormalising 40→100 fabricates the authority the lane
   disclaims.

**Sparklines were ruled OFF** and it was the right call by a wide margin: they were
**86% of the payload** (265,173 B raw with, 33,358 B without), on a key that changes
**once a day** riding a **120 s** poll. The evening spark is also *bandless* (its
buy-zone comes from the omitted `entry` leg), so it was 86% of the payload for a
degraded copy of the morning chart. Final delta: **+32,351 B raw / +3,869 B gzip**.
Escalation if design ever needs them: a **separate one-shot artifact** fetched only
when the stamp qualifies (~15-min break-even vs the poll), NOT a top-N cap.

**`name_zh` ruled OFF** for a different reason — consistency, not cost. The *nightly*
passes no `name_zh` for US cards, so filling it evening-only would show a ZH reader
苹果 at 17:30 and *Apple Inc* at 09:00, on exactly the readers this stamp exists to
orient. **The nightly ZH gap is real and now a follow-up**:
`scripts/build_stock_library.py:74` loads `_US_NAMES_ZH` and wires it only into
`search_name_zh()`, never onto the board row. Fixing it changes every US card, so it
needs its own PR and its own visual proof.

---

## §3 The bug that would have shipped a false statement

The renderer's adversarial review caught it: `runway` must be **`null`** when
unmeasured, never `0.0`. `engine/us_board_rank.py:628` collapses **three** facts
into `0.0` — unmeasured, antichase-blocked, and genuinely extended. Correct for
*scoring*; false as *display*: the card would have said **"Room: Thin" about a name
nobody measured** (~5 of 79 rows).

Fixed in `close_legs`, **not** in `us_board_rank` — `0.0` is the right score for all
three and changing that function moves the nightly's own arithmetic.
`tests/test_us_board_rank.py` (322) green as proof it didn't move.

Two things the fix turned up that the diagnosis missed:

- **`runway` was in `CARD_REQUIRED`**, so `null` would have *dropped* those rows from
  the board — silently deleting the exact names the fix exists to serve. The bug
  behind the bug.
- **Antichase is not a third fact in this lane.** `close_legs` derives it locally as
  `ext_z > EXT_Z_FULL`, so it is a restatement of "genuinely extended", not an
  independent signal. Pinned by
  `test_the_antichase_case_is_not_a_third_fact_in_this_lane`, which **fails if a real
  upstream antichase signal is ever piped in** rather than letting it inherit
  today's answer silently.

---

## §4 Findings — three dark halves and a lie-shaped gate

W-L1 was darker than session 3 recorded. Everything below was verified, not inferred.

1. **State 1 had no cards** — the payload carried ticker + admission state only and
   self-declared `card_complete: False`. (Fixed: #5217 + #5223.)
2. **State 2 had no receipt** — the reconciler published
   `live_flow/us_board_confirmation.json` to R2 and **nothing in the repo read that
   key**, while `build_site.py:4499` read `doc["board_state"]`, which **nothing
   wrote**. (Fixed: #5220.)
3. **The per-card `Adjusted` mark was a third dead half** — `dashboard.html.j2:15917`
   fences on `n.get('adjusted')`, a boolean nothing set. Wiring only the receipt line
   would have left the marks permanently dark. (Fixed in #5220, stamped only after
   the interpreter vouches for the line, so publish-together holds in the data too.)
4. **The 18:30 SLA measured the wrong artifact.** `freshness_sentinel` watched
   `/live/us_board_provisional.json` — what the lane *publishes* — but the reader
   consumes the `board_state` key on `prophet_live.json`, written by a separate step
   whose `False` return is **discarded**, after which `run()` exits 0 silently. Four
   ways to diverge, confirmed by probe. So the gate could score **green while the
   surface is blind**. (Fixed: #5222.)

**The receipt ordering was a structural impossibility, not a scheduling miss.**
Session N's receipt cannot exist until session N's board lands, which is *after* the
render that would show it. No arrangement lets a render *read* a published receipt
and get the right one — hence in-process computation, with the `workflow_run` job
deleted rather than left racing.

---

## §5 The evening lane has NEVER RUN — correct this if you inherited otherwise

`close-pass.yml`'s `publish` job has **never fired.** Total history: two
`workflow_run` events, **both FAILED** with
`ModuleNotFoundError: No module named 'pandas'` — the job installs only `boto3`, but
`scripts/close_pass_reconcile.py` → `engine/close_pass/__init__.py` →
`board.py` → `engine.signal_gate` → pandas. It failed 100% of every run it ever had,
and downstream that read as *absent data*, not as a fault.

#5154 merged Sunday 08-09; the cron is weekdays-only, so **the first weekday firing
is Monday 2026-08-10 at 20:25 UTC / 16:25 ET.** #5220 fixes the pandas failure
incidentally by moving that step into `daily.yml`'s engine job (which installs
`requirements.txt`, carrying both pandas and `boto3>=1.34` — verified).

**Consequence: W-L1 is entirely unproven end-to-end, and the five-session SLA clock
has not started.** Watch the first firing.

---

## §6 What W-L1 still needs

Gate: *fresh US picks live by 18:30 ET on five consecutive green sessions, measured
by the sentinel's stamps; provisional→nightly delta published per name; no `data/`
writes from the close-pass lane.*

- Per-name delta — **built** (#5220), unproven until the lane fires.
- No `data/` writes — **held** (`contents: read`).
- Five consecutive green sessions — **cannot be built; it accrues.** Earliest
  possible completion is five weekdays after the four PRs land AND the lane fires.

**Residual the SLA fix does NOT close** (flagged by its builder, correctly): once the
renderer ships, `_bsQualify` can still refuse on a post-mount identity mismatch and
tear the board down. The reader then correctly sees the nightly board — but the
sentinel would still score that session green. Closing it means teaching the sentinel
the rendered grid's ticker list. Narrow; decide after the first real firings show
whether it ever happens.

---

## §7 Loose ends, with locations

- **`--ink-pv-near` fails AA at 3.83:1 in ZH light** on a bare shipped card — that is
  **every `Near` card on every Prophet board today**, not this surface. The evening
  board renders ~50% Near, so it amplifies it. Needs its own PR: `theme.css` is a
  **paired** asset (`python -m scripts.check_template_site_sync --fix`), and the ZH
  红涨绿跌 flip must not be collapsed while fixing contrast. A task chip is filed.
- **Nightly `name_zh`** — §2 above.
- **`href` shape** — the producer's `stock.html#AAPL` is correct and matches the
  nightly. The `stocks/AAPL.html` in the renderer's brief was a commissioning error;
  the renderer accepts both so no board is ever hard-refused.
- **R2 on the nightly critical path** (#5220) — bounded, not a hang: `connect_timeout=15`,
  `read_timeout=60`, 4 attempts, plus a 20 s public fallback ⇒ ~5 min worst case per
  call site against a ~24-min `build_site`, only on a total R2 outage.
- **Two design constants upheld deliberately**, do not "tidy" them: `Zone sets on
  confirmation` on every row (a structural slot's honest value, not Law 4 ornament —
  and moving it to the note line would widen `note.ahead`, which spec §8 item 10 names
  as the way to break the measured 0.00px height equality), and the hidden priority
  footnote (two false descriptions beat a two-hour gap).

---

## §8 Method notes worth keeping

- **A red job nobody watches reads downstream as absent data, not as a fault.** The
  pandas failure was invisible for a day because its only symptom was "the feature is
  dark". Memory: `import-closure-guard-blind-to-package-init` (now records this as its
  third instance — a narrow `pip install` is an import-closure claim, exactly like a
  restart regex).
- **Measure an SLA on what the CONSUMER reads, not what the producer publishes.**
  Memory: `sla-measured-on-the-producer-artifact-scores-green-while-readers-see-nothing`.
- **Prove divergence from the code path, never from production history** — here there
  *was* no history, so any argument from observed artifacts would have been vacuous.
- **Check for a sibling heal before writing one.** Main's `ci-pack-1` red this session
  (`build_options_issue_desk.py` unpinned) was already fixed by #5209; the check saved
  a duplicate PR.
