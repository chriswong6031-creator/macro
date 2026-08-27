from __future__ import annotations

import json
from pathlib import Path

OUT = Path('/tmp/final')
OUT.mkdir(parents=True, exist_ok=True)


def patch(src_path: str, dst_name: str, replacements: list[tuple[str, str]], append: str = '') -> None:
    text = Path(src_path).read_text(encoding='utf-8')
    for old, new in replacements:
        n = text.count(old)
        if n != 1:
            raise SystemExit(f'{src_path}: expected exactly one match, found {n}: {old[:100]!r}')
        text = text.replace(old, new)
    if append:
        text = text.rstrip() + '\n\n' + append.strip() + '\n'
    (OUT / dst_name).write_text(text, encoding='utf-8')


SCRIPT_OLD = '''WHY THE JOURNAL IS A SOUND SOURCE. Each pass logs its own event count and then its
event lines. Those two are independent statements by the same process, so they check
each other: across the whole outage, 672 passes and 672 exact matches, zero mismatched,
zero orphaned event lines. A truncated log could not produce that.'''
SCRIPT_NEW = '''WHY THE COMMITTED JOURNAL IS A SOUND ROW SOURCE. The committed recovery corpus is
content-addressed by ``_recovery_receipt.json``. Within that exact corpus, every
captured pass logs its own event count and then its event lines: 588 pass records —
exactly 84 in each of the seven Class-R sessions — declare 25,958 events and carry
25,958 EVENT lines, with zero mismatched passes and zero orphaned lines. The production
timer is ``:03/5`` and the sole ET window is ``09:25`` through ``16:15 + 10m`` grace,
which admits exactly 84 ticks in an EDT session (13:28Z through 20:23Z). Together the
per-session census and per-pass count equality close both whole-pass and intra-pass
completeness for this committed corpus. Earlier #6484 prose said 672 passes; that
number is not reproducible from the committed gzip and is superseded for source-
integrity claims.'''
NAMES_OLD = '              Measured on this incident: 168 of 333 names determined, 0 contradictions.'
NAMES_NEW = ('              Measured on the committed corpus: 141 of 294 name-sessions determined '
             '(118 board, 23 cross), 153 genuinely undetermined, 0 contradictions.')
patch(
    'scripts/prophet_live_journal_recovery.py',
    'prophet_live_journal_recovery.py',
    [(SCRIPT_OLD, SCRIPT_NEW), (NAMES_OLD, NAMES_NEW)],
)

RESEARCH_OLD = '''The journal is sound as a source because it self-checks: each pass independently
declares `events=N` and then prints its event lines. Across the whole outage —
**672 passes, 672 exact matches, 0 mismatched, 0 orphaned event lines**. A truncated
log cannot produce that. `scripts/prophet_live_journal_recovery.py` refuses (exit 3)
on any mismatch, orphan, or branch contradiction rather than accruing a partial pass.'''
RESEARCH_NEW = '''The committed recovery corpus is the source boundary, not an unscoped host-journal
count. Its immutable gzip contains **588 pass records: exactly 84 on each of the seven
Class-R sessions**. Those passes declare **25,958 events** and the gzip carries exactly
**25,958 `EVENT` lines**, with 0 mismatched passes and 0 orphaned lines. The producer
timer is `:03/5`; the single canonical ET window is 09:25 through 16:15 plus 10 minutes
of end grace, which admits exactly 84 scheduled ticks per EDT session (13:28Z through
20:23Z). The per-session census therefore closes whole-pass completeness, while the
`events=N` equality closes intra-pass completeness. The earlier **672 passes** claim in
#6484 prose is not reproducible from the committed gzip and is superseded for recovery
source-integrity claims. `scripts/prophet_live_journal_recovery.py` still refuses
(exit 3) on any mismatch, orphan, or branch contradiction.'''
REPRO_OLD = '''The committed journal (`journal_2026-07-30_2026-08-25.txt.gz`, 197 KB,
sha256 `d3812a0cec8f50dff57523ffa7163c65d3a3f058da56286fa368185b74156a52`) plus the
recovery tool regenerate the pending input byte-for-byte. The 10 MB expanded pending
is deliberately NOT committed — stage-and-absorb, not a persistent queue (§14).'''
REPRO_NEW = '''The committed journal (`journal_2026-07-30_2026-08-25.txt.gz`, 197 KB) plus the
recovery tool regenerate the pending input byte-for-byte. `_recovery_receipt.json`
records sha256 `d3812a0cec8f50dff57523ffa7163c65d3a3f058da56286fa368185b74156a52`
for the **uncompressed source text** supplied to the recovery tool; the committed gzip
archive bytes hash to sha256
`2d1f429993fd555482ff3887f5dca13eb8825313be9dcbd702f091d52636884e`.
The two hashes name different representations and must not be conflated. The 10 MB
expanded pending is deliberately NOT committed — stage-and-absorb, not a persistent
queue (§14).'''
RESEARCH_APPEND = '''## 15.6 Final maturation — 2026-08-27

The initial absorption in §15.3 was intentionally honest about 86 rows from the
2026-08-25 session whose `next_close_fill` was still null. The ordinary nightly had
already run before #6484 created the ledger, so those rows missed that one normal
maturation pass; this was a sequencing residue, not missing market data.

Sol re-ran the **existing canonical reconciler logic** (`maturing_rows` →
`_expand_maturing` → `merge_ledger`) against the committed Aug-26 close series. All 38
open ticker/session pairs had a 2026-08-26 close. The deterministic closeout produced:

- 38 pair updates → exactly **86 row updates**;
- **598 rows before and after**;
- **0 duplicate `(date,ticker,kind)` keys**;
- `next_close_fill`: **512/598 → 598/598**;
- every matured Aug-25 row has `next_close_date=2026-08-26`;
- **0 `FIRST_WINS` fields changed** and `entered` did not change;
- the 153 undetermined name-sessions remain unknown (`entered=null`), never cross;
- final ledger sha256
  `fb25fcc6b1935d9fdd5e7e2a6e8a5981411acda6825784afb241eceba968c5e0`.

The durable machine receipt is
`data/pit_replay/prophet_live_recovery/_closeout_receipt.json`. Class D remains
refused; no replay, pack reconstruction, board/rank/plan/site mutation, or third ledger
writer was introduced.'''
patch(
    'research/PROPHET_US_LIVE_FORCE_MAJEURE_2026_08_26_EVIDENCE.md',
    'PROPHET_US_LIVE_FORCE_MAJEURE_2026_08_26_EVIDENCE.md',
    [(RESEARCH_OLD, RESEARCH_NEW), (REPRO_OLD, REPRO_NEW)],
    append=RESEARCH_APPEND,
)

HANDOFF_OLD = '''Executed as RECOVERY, not replay: every row was emitted by the production evaluator
at the time and read back verbatim from its journal. Nothing was reconstructed, so
the §24.2 no-surviving-pack blocker never applied. The journal self-checks — each
pass declares `events=N` then prints its lines; 672 passes, 672 matches, 0 orphans.
Count agreed three independent ways before any effect landed.'''
HANDOFF_NEW = '''Executed as RECOVERY, not replay: every row was emitted by the production evaluator
at the time and read back verbatim from its journal. Nothing was reconstructed, so
the §24.2 no-surviving-pack blocker never applied. The **committed recovery corpus**
has 588 pass records — exactly 84 in each of the seven Class-R sessions, matching the
`:03/5` timer inside the sole 09:25–16:25 ET inclusive window — and 25,958 declared
events exactly equal 25,958 EVENT lines, with 0 mismatches/orphans. The earlier 672
pass count is not reproducible from the committed gzip and is superseded for source-
integrity claims. The 598 distinct ledger-key count still agreed independently via
journal census, recovery-tool distinct keys, and reconciler dedupe before absorption.'''
NEXT_OLD = '''  4) The 86 Aug-25 rows carry next_close_fill=null and mature on an ordinary
     nightly. Confirm they fill, then the ledger is fully matured for this incident.'''
NEXT_NEW = '''  4) DONE 2026-08-27: the 86 Aug-25 rows were matured through the existing
     canonical reconciler against the Aug-26 close. Final ledger: 598 rows, 0
     duplicate keys, 598/598 next_close_fill, no FIRST_WINS or entered mutation;
     receipt data/pit_replay/prophet_live_recovery/_closeout_receipt.json.'''
UNVERIFIED_OLD = '  - "The 86 Aug-25 rows have next_close_fill=null pending the next close; they mature in place on an ordinary nightly."\n'
STALE_STATE_OLD = '''## What was proven vs merely built

`PR #6464` is BUILT_NOT_PROVEN until it is merged, deployed to `/opt/macro`, and
a real in-window pass advances the served and R2 objects. CI green is not
production proof and must not be reported as such.

The restoration precondition IS proven: authenticated PUT/GET/DELETE against the
production bucket succeeded with the now-seeded credentials, and today's armed
pack (`as_of=2026-08-25`) is correctly stamped, so the lane is not exposed to D12
for this session.'''
STALE_STATE_NEW = '''## What is proven now

PR #6464 + #6482 are **PROVEN_LIVE**, not merely built: they are merged, deployed,
and were exercised during the real 2026-08-26 NYSE session with advancing R2 + served
objects and the external dead-man demonstrated both red and green states. CI remains
supporting evidence, not the acceptance proof.

The force-majeure recovery ledger is now fully matured for its seven lawful Class-R
sessions: 598 rows, 0 duplicate keys, 598/598 next-close fills. The 11 Class-D sessions
remain refused by design. D12 itself remains visible but unrepaired and separately
owned from this closeout.'''
HANDOFF_APPEND = '''## FINAL EVIDENCE MATURATION — 2026-08-27

The one remaining backfill closeout gate is closed. The existing reconciler matured all
86 Aug-25 rows against the 2026-08-26 close: 38 ticker/session pairs → 86 row updates,
598 rows remain, duplicate keys remain 0, `next_close_fill` is 598/598, and no
`FIRST_WINS` or `entered` value changed. Final ledger sha256:
`fb25fcc6b1935d9fdd5e7e2a6e8a5981411acda6825784afb241eceba968c5e0`.
Machine receipt: `data/pit_replay/prophet_live_recovery/_closeout_receipt.json`.

Do not reopen a replay/backfill wave from this incident. Remaining items are separate:
D12 ownership/repair, attribution of the 2026-08-26T07:43:28Z credential seeding, and
the unclassified partial 2026-07-30 tail. Class D stays refused. #6296 is unrelated
and remains HOLD-FOR-SOL.'''
patch(
    'agentos/handoffs/WS-PROPHET-US-AVAILABILITY-2026-08-26-live-force-majeure.md',
    'WS-PROPHET-US-AVAILABILITY-2026-08-26-live-force-majeure.md',
    [(HANDOFF_OLD, HANDOFF_NEW), (NEXT_OLD, NEXT_NEW), (UNVERIFIED_OLD, ''),
     (STALE_STATE_OLD, STALE_STATE_NEW)],
    append=HANDOFF_APPEND,
)

RECEIPT = {
    'schema': 'prophet_live.force_majeure_closeout/v1',
    'generated_from_workflow_run': 33043568440,
    'baseline_macro_main': '23007eea2f2b3070093a7fcd9df577844ebabb8c',
    'reconciliation_code': 'scripts/reconcile_prophet_live.py:maturing_rows+_expand_maturing+merge_ledger',
    'reconciled_at': '2026-08-27T05:48:01.061874+00:00',
    'ledger_before_sha256': '6c54fb8a92d43f44b5acc3999696217d6523abac0d684a9473b1f71ff0e25843',
    'ledger_after_sha256': 'fb25fcc6b1935d9fdd5e7e2a6e8a5981411acda6825784afb241eceba968c5e0',
    'rows_before': 598, 'rows_after': 598, 'duplicate_keys_after': 0,
    'open_fills_before': 86, 'open_fills_after': 0,
    'maturing_pair_updates': 38, 'maturing_row_updates': 86,
    'next_close_date_for_matured_rows': '2026-08-26',
    'first_wins_changed': [], 'entered_changed': False,
    'entered_null_name_sessions': 153, 'entered_null_rows': 306,
    'recovery_source_text_sha256': 'd3812a0cec8f50dff57523ffa7163c65d3a3f058da56286fa368185b74156a52',
    'recovery_gzip_sha256': '2d1f429993fd555482ff3887f5dca13eb8825313be9dcbd702f091d52636884e',
    'journal_pass_lines': 588, 'expected_pass_lines': 588,
    'expected_passes_per_class_r_session': 84,
    'timer': 'Mon..Fri *-*-* 13..21:03/5:00 UTC',
    'window_et_inclusive_with_grace': '09:25-16:25',
    'journal_event_lines': 25958, 'journal_declared_event_sum': 25958,
    'journal_passes_by_et_session': {
        '2026-07-31': 84, '2026-08-07': 84, '2026-08-11': 84,
        '2026-08-14': 84, '2026-08-20': 84, '2026-08-21': 84, '2026-08-25': 84,
    },
    'class_d_status': 'REJECTED_BY_DESIGN',
    'class_d_sessions': [
        '2026-08-03','2026-08-04','2026-08-05','2026-08-06','2026-08-10',
        '2026-08-12','2026-08-13','2026-08-17','2026-08-18','2026-08-19','2026-08-24',
    ],
}
(OUT / '_closeout_receipt.json').write_text(
    json.dumps(RECEIPT, indent=2, sort_keys=True) + '\n', encoding='utf-8'
)

for name in (
    'prophet_live_journal_recovery.py',
    'PROPHET_US_LIVE_FORCE_MAJEURE_2026_08_26_EVIDENCE.md',
    'WS-PROPHET-US-AVAILABILITY-2026-08-26-live-force-majeure.md',
):
    text = (OUT / name).read_text(encoding='utf-8')
    if '168 of 333' in text:
        raise SystemExit(f'{name}: stale 333/168 counter survived')

print('generated:', ', '.join(sorted(p.name for p in OUT.iterdir())))
