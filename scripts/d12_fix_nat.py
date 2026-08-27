"""ONE-SHOT D12 malformed-tip patcher. Deleted by its workflow after use."""
from pathlib import Path

p = Path("scripts/build_prophet_live_pack.py")
s = p.read_text()
old = "if day > bound or not is_session(day):"
new = "if pd.isna(day) or day > bound or not is_session(day):"
assert s.count(old) == 1
p.write_text(s.replace(old, new, 1))
