# W1 RE-VERIFY — three-shelf lifecycle wave, post-fix gate (adversarial)

**Verdict: SHIP.** The B1 blocker from `_VERIFY.md` is fixed exactly per the adjudicated F6 design.
The build-aborting input-level assert is gone; buy_now/partial + overextended rule-2 rows now carry
`muted_entry=True` and render a neutral amber "gauge open but extended — not actionable" line with
no green banding, no BUY-family words, no Buy-now tooltip, and no green act-dot. Verified on the
LIVE artifact (002896.SZ / 002472.SZ), on a hostile synthetic render, and against all six exemplars.

Date: 2026-07-03. Panel/artifact: `site/factordata/china_standouts.json` (pre-W1, 110 buy rows).
Method: `PYTHONPATH=$PWD python3`, engine + template extracted-block render (no full site render).

---

## 1. Hostile diff review of the fix — PASS

**Input-level assert removed.** `scripts/build_china_library.py` — the old `assert not _r2_bad`
(which crashed the build on buy_now+extended RAN_LATE rows, and missed `partial`) is GONE. Replaced
by RENDER-LEVEL invariants (build_china_library.py:1568-1586):
- (i) every rule-2 RAN_LATE row has a sublabel (assert, 1576);
- (ii) rule-2 rows with entry_status in {buy_now, partial} MUST carry `muted_entry=True` (assert, 1584);
- both read `entry_sig` — the same dict the stage assignment reads (1454-1455) — so no source drift.

**muted_entry wiring correct.** `engine/setup_tier.py:280-299` — Rule 2 fires on
`overextended OR entry_status=='hold' OR entry_status not in (buy_now,partial,None)`. It sets
`_muted = overextended and entry_status in ('buy_now','partial')` and emits
`detail.muted_entry = _muted`, with sublabel **"entry gauge open — but extended; wait for pullback"**
(exact adjudicated wording) in the muted case, else "signal live — entry passed; wait for pullback".
`build_china_library.py:1471-1478` propagates `stage_detail.muted_entry` up to the row dict for Jinja.

**RAN_LATE never renders green / BUY.** `templates/china.html.j2:1490-1510` branches:
`{% if n.get('muted_entry') %}` → renders `nbe-wait_pullback` (amber, CSS 175) + `nbe-dot a1`
(warn, CSS 184) + neutral dual-span line, NO `nbe-buy_now`/`nbe-partial`, NO Buy-now tooltip.
`{% else %}` → `nbe-{{ es.status }}` for non-actionable statuses (hold/extended/topping — all amber/red).

**Unreachability of the else-branch green leak (hostile).** The else branch renders
`nbe-dot a{{ es.act_level }}`; `act_level==3` would be a green dot. But in `engine/entry_signal.py`
`_ACT_LEVEL` gives `act=3` only when `urg=='now'`, and `_STATUS_BY_URGENCY['now']=='buy_now'`
(→ `partial` via HALF-SIZE, urg stays "now"). So `act_level==3` co-occurs ONLY with status in
{buy_now, partial}; any such RAN_LATE row is overextended (else it'd be ENTRY via rule 1) →
`muted_entry=True` → muted branch (a1 dot). The else branch never sees a3 on real data. Confirmed by
rendering a muted-only card: dot is `a1`. (A synthetic hold-row with a forced act_level=3 does paint
a3 in the else branch, but that input is unreachable — status=hold implies urg!=now implies act=1.)

**Dual-span + attributes.** Muted status line has both `l-en` ("gauge open — but extended; not
actionable") and `l-zh` ("量表打开 — 但已延伸；当前不可操作"). Whole-file scan: no `t()`/`td()`
inside any HTML attribute; no non-ASCII attribute delimiters (curly quotes / guillemets) — em-dashes
and CJST punctuation appear only inside attribute VALUES (accepted idiom), never as delimiters.

**F3 discipline.** No `_cn_bonus` / `blend_sorted` change in the diff. Muting is display-only.

**Exemplar-b gap closed.** `build_china_library.py:1503` now attaches `hold_summary` for
`state in ('intact','launched')` (was `intact` only). Rule 3 in `setup_tier.py:319-321` emits
`launched_chip="launched from {anchor}, +X%"`, rendered by `china.html.j2:1582-1583` (green line).
So 603129 (launched) now shows its hold/launched line — the minor spec gap flagged in _VERIFY.md.

---

## 2. Previously-FAILED render fixture, re-run — PASS

Rendered the extracted W1-C three-shelf block against a synthetic context with: an ENTRY control row
(buy_now, not overextended), TWO muted RAN_LATE rows (002896.SZ buy_now + 002472.SZ partial, both
overextended, muted_entry=True), a non-muted RAN_LATE hold row, a RIPENING row, and a rule-3 RAN row.

RAN_LATE cards (grep of the RAN-shelf region):
- `nbe-buy_now`  → **absent**
- `nbe-partial`  → **absent**
- `nbe-dot a3`   → absent on realistic rows (a1 on both muted rows)
- "Buy now" tooltip → **absent**
- `nbe-wait_pullback` → present ×2 (both muted rows); muted status line present ×2
- `stg-entry` (green stage badge) → **absent** on RAN cards, present only on the ENTRY control

Control: ENTRY shelf DOES render `nbe-buy_now` + `stg-entry` (green stays where it belongs).
Zero BUY-family words / green banding on any card outside the ENTRY shelf gauge.

---

## 3. Live crash check — PASS

Ran `assign_stage` over the LIVE 110-row buy set, then replicated the builder's render-level
invariant block:
- Both flagged names route correctly and safely:
  - `002896.SZ` status=buy_now, extended=True → **RAN_LATE, muted_entry=True**,
    sublabel "entry gauge open — but extended; wait for pullback".
  - `002472.SZ` status=buy_now, extended=True → **RAN_LATE, muted_entry=True**, same sublabel.
- 96 RAN_LATE rows total; all have a sublabel; all buy_now/partial ones carry muted_entry.
- **No AssertionError** — the old build-abort landmine is gone; the new asserts pass on live data.

Exemplar a: live 300725.SZ (status=partial, not overextended) → **ENTRY**.

---

## 4. Test sweep — PASS (honest counts)

Targeted sweep (all 7 files):
`test_setup_tier.py test_china_alpha_w1b.py test_china_stocks_w1c_render.py test_china_alpha_w0.py
test_w0_5_10_8.py test_china_stocks_copy_w09.py test_china_standout_track.py`
→ **174 passed, 1 warning** (pytest8 class-fixture deprecation, benign).

Bounded china smoke `pytest tests -q -k "china"`:
→ **503 passed, 1 failed, 1 skipped, 5933 deselected** (105s).
- The 1 failure — `tests/test_china_news.py::test_adapter_is_registered_without_akshare` —
  is **PRE-EXISTING and unrelated**: `ImportError: cannot import name 'all_adapters' from
  scripts.collect`. No W1 file touches `scripts/collect.py` or the news adapter
  (`git diff --name-only HEAD | grep -iE 'collect|news'` = NONE). Not a W1 blocker.

---

## 5. Exemplar spot-checks — ALL PASS

| # | Case | Result | Evidence |
|---|---|---|---|
| a | 300725.SZ → ENTRY | PASS | live row status=partial, overext=False → ENTRY |
| b | 603129.SS → RAN_LATE + hold line | PASS | rule-3 → RAN_LATE "signal fired 2026-06-24 (7 sessions ago), +8.9%"; **launched_chip "launched from 2026-06-26, +8.9%"** now present (fix) |
| c | 688306.SS → RIPENING (historical cutoff) | PASS | gate-ineligible + no recent cross + setup_live(2W stoch washout) → RIPENING "2W stoch washout" |
| d | muted 002896/002472 | PASS | RAN_LATE + muted_entry=True + adjudicated sublabel (§3) |
| e | ENTRY control keeps green | PASS | nbe-buy_now + stg-entry render on ENTRY shelf only (§2) |
| f | 3-shelf render, no leak | PASS | zero BUY-family / green outside ENTRY gauge (§2) |

---

## 6. Hygiene — PASS

`git status --short`: only the expected wave files (4 modified: china_standout_track.py,
build_china_library.py, shadow_pit_china.py, china.html.j2; untracked: setup_tier.py, the two new
test files, research/china_alpha/w1/). No tracked DATA file dirtied
(`git status --short -- data/` shows only the pre-existing untracked
`data/vector/regime_calibration.json`). `data/china_standout_track/ripening.parquet` NOT created
(tests used tmp paths). `data/vector/regime_calibration.json` remains PRE-EXISTING /
uncommitted / referenced by no W1 file — must NOT be committed with W1. No git write ops performed.

---

## Bottom line

The fix implements the adjudicated F6 design verbatim: extension beats the timing gauge, buy_now/
partial + overextended is a legitimate input that routes to RAN_LATE (rule 2) with sublabel
"entry gauge open — but extended; wait for pullback" and `muted_entry=true`; the crashing input-level
assert is replaced by render-level invariants; the template mutes the entry gauge (amber, a1 dot,
neutral dual-span line) with zero green/BUY leakage; every buy row still has a stage. Verified on live
data (both blocker names), a hostile render, and all six exemplars. **SHIP.**

### Non-blocking notes (owner's discretion, not ship gates)
- The RAN-card conviction SCORE (`nb-cscore band-{{c.band}}`, china.html.j2:1479) can carry
  `band-high` (green text via `var(--up)`) but is muted to opacity .45 by `.nb-stage-ran-card
  .nb-cscore` (CSS 314) and titled "Score muted — RAN/LATE shelf". This is the score, not the entry
  gauge; it pre-dates the fix, was not the B1 blocker, and is intentionally muted. If a stricter
  reading of render-invariant (i) ("green banding on ENTRY only") is desired, force `band-neutral`
  on RAN cards — but that is a polish call, not a correctness blocker.
- `hold_summary` is now attached to RAN rows (builder 1502-1509) but the template renders
  `launched_chip`/`basing_chip` from the stage detail instead; `hold_summary` is currently an unused
  additive field (harmless, may feed a future card). Cosmetic.
