from __future__ import annotations

import hashlib
import runpy
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import reconcile_prophet_live as RC  # noqa: E402

LEDGER = ROOT / RC.LEDGER_REL
EXPECTED_BEFORE_SHA = '6c54fb8a92d43f44b5acc3999696217d6523abac0d684a9473b1f71ff0e25843'
EXPECTED_AFTER_SHA = 'fb25fcc6b1935d9fdd5e7e2a6e8a5981411acda6825784afb241eceba968c5e0'

# Generate the corrected text/receipt surfaces from exact old-text tripwires.
runpy.run_path(str(ROOT / '.github/prophet_closeout_patch.py'), run_name='__main__')
out = Path('/tmp/final')

before_bytes = LEDGER.read_bytes()
if hashlib.sha256(before_bytes).hexdigest() != EXPECTED_BEFORE_SHA:
    raise SystemExit('baseline forward.parquet sha drifted')
before = pd.read_parquet(LEDGER)
if len(before) != 598 or int(before.duplicated(RC.KEY).sum()) != 0:
    raise SystemExit('baseline ledger identity drifted')
if int(before['next_close_fill'].isna().sum()) != 86:
    raise SystemExit('baseline open-fill cardinality drifted')
if sorted({str(v) for v in before.loc[before['next_close_fill'].isna(), 'date']}) != ['2026-08-25']:
    raise SystemExit('baseline open-fill session drifted')

before_first = before.set_index(RC.KEY)[list(RC.FIRST_WINS)].sort_index()
before_entered = before.set_index(RC.KEY)['entered'].sort_index()
open_pairs = RC.open_rows(LEDGER)
want = {ticker for _day, ticker in open_pairs}
closes, adjustment = RC.load_closes(want)
missing = sorted(want - set(closes))
if missing:
    raise SystemExit(f'missing canonical close series: {missing}')

# Pin the exact already-reviewed deterministic result timestamp from workflow
# 33043568440 so the final parquet is byte-identical to the sealed artifact.
now = datetime(2026, 8, 27, 5, 48, 1, 61874, tzinfo=timezone.utc)
pair_updates = RC.maturing_rows(LEDGER, closes=closes, now=now, close_adjustment=adjustment)
updates = RC._expand_maturing(LEDGER, pair_updates)
matured = RC.merge_ledger(LEDGER, updates)

after_first = matured.set_index(RC.KEY)[list(RC.FIRST_WINS)].sort_index()
after_entered = matured.set_index(RC.KEY)['entered'].sort_index()
changed = []
for col in RC.FIRST_WINS:
    a, b = before_first[col], after_first[col]
    same = (a == b) | (a.isna() & b.isna())
    if not bool(same.all()):
        changed.append(col)
entered_same = (before_entered == after_entered) | (before_entered.isna() & after_entered.isna())

if len(pair_updates) != 38 or len(updates) != 86:
    raise SystemExit('unexpected maturation cardinality')
if len(matured) != 598 or int(matured.duplicated(RC.KEY).sum()) != 0:
    raise SystemExit('post-maturation ledger identity failed')
if int(matured['next_close_fill'].isna().sum()) != 0:
    raise SystemExit('post-maturation open fill remained')
if sorted({str(v) for v in matured.loc[matured['date'].astype(str).eq('2026-08-25'), 'next_close_date'].dropna()}) != ['2026-08-26']:
    raise SystemExit('unexpected next-close date')
if changed or not bool(entered_same.all()):
    raise SystemExit(f'immutable evidence changed: FIRST_WINS={changed}, entered_same={bool(entered_same.all())}')

staged = Path('/tmp/final-forward.parquet')
matured.to_parquet(staged, index=False)
actual_after_sha = hashlib.sha256(staged.read_bytes()).hexdigest()
if actual_after_sha != EXPECTED_AFTER_SHA:
    raise SystemExit(f'generated ledger sha drifted: {actual_after_sha}')

# Only these five durable paths are changed. No runtime/config/workflow surface lands.
shutil.copyfile(staged, LEDGER)
shutil.copyfile(out / 'prophet_live_journal_recovery.py', ROOT / 'scripts/prophet_live_journal_recovery.py')
shutil.copyfile(out / 'PROPHET_US_LIVE_FORCE_MAJEURE_2026_08_26_EVIDENCE.md', ROOT / 'research/PROPHET_US_LIVE_FORCE_MAJEURE_2026_08_26_EVIDENCE.md')
shutil.copyfile(out / 'WS-PROPHET-US-AVAILABILITY-2026-08-26-live-force-majeure.md', ROOT / 'agentos/handoffs/WS-PROPHET-US-AVAILABILITY-2026-08-26-live-force-majeure.md')
shutil.copyfile(out / '_closeout_receipt.json', ROOT / 'data/pit_replay/prophet_live_recovery/_closeout_receipt.json')

print('FINALIZE_OK rows=598 duplicates=0 fills=598/598 pair_updates=38 row_updates=86')
print(f'FINAL_LEDGER_SHA256={actual_after_sha}')
