"""Refresh the W0 Regime Tape prototypes from the committed BTC timeline."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lib.illus import regime_tape  # noqa: E402

HERE = Path(__file__).resolve().parent
TIMELINE = ROOT / "site" / "vector_timeline.json"


def _regime_runs(dates: list[str], states: list[str]) -> list[dict]:
    runs = []
    start = dates[0]
    state = states[0]
    for current_date, current_state in zip(dates[1:], states[1:]):
        if current_state != state:
            runs.append({"start": start, "end": current_date, "tone": state})
            start, state = current_date, current_state
    runs.append({"start": start, "end": dates[-1], "tone": state})
    return runs


def _replace(path: Path, marker: str, fragment: str) -> None:
    text = path.read_text(encoding="utf-8")
    pattern = re.compile(
        rf"(<!-- {marker}:START -->).*?(<!-- {marker}:END -->)",
        re.DOTALL,
    )
    rendered, count = pattern.subn(
        rf"\1\n          {fragment}\n          \2",
        text,
    )
    if count != 1:
        raise RuntimeError(f"{path}: expected one {marker} marker pair, found {count}")
    path.write_text(rendered, encoding="utf-8")


def main() -> int:
    tape = json.loads(TIMELINE.read_text(encoding="utf-8"))
    window = 1100
    dates = tape["dates"][-window:]
    price = tape["price"][-window:]
    allocation = tape["alloc"][-window:]
    states = tape["regime"][-window:]
    regimes = _regime_runs(dates, states)
    events = [
        {
            "date": "2024-04-20",
            "label_en": "Fourth Bitcoin halving",
            "label_zh": "第四次比特币减半",
        }
    ]
    projection = {
        "start": "2026-10-01",
        "end": "2027-02-01",
        "label_en": "Projected cycle window",
        "label_zh": "预测周期窗口",
    }
    vector = regime_tape(
        {"dates": dates, "vals": price},
        allocation={"dates": dates, "vals": allocation},
        regimes=regimes,
        events=events,
        projection=projection,
        height=252,
        max_points=220,
        aria_en="Bitcoin price, market regimes, model exposure, halving and projected cycle window",
        aria_zh="比特币价格、市场状态、模型仓位、减半与预测周期窗口",
    )
    crypto = regime_tape(
        {"dates": dates, "vals": price},
        allocation={"dates": dates, "vals": allocation},
        regimes=regimes,
        events=events,
        height=178,
        max_points=160,
        aria_en="Real Bitcoin history proving the reusable crypto class Regime Tape form",
        aria_zh="以真实比特币历史验证可复用的加密市场周期轨迹",
    )
    _replace(HERE / "vector.html", "REGIME_TAPE", vector)
    _replace(HERE / "crypto.html", "CRYPTO_TAPE", crypto)
    print(f"refreshed Regime Tape prototypes from {dates[0]} through {dates[-1]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
