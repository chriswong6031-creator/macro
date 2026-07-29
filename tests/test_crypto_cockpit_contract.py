import json

import pandas as pd

from scripts.build_vector import COCKPIT_AXIS_PRESENTATION, emit_crypto_cockpit_json


def _master():
    rows = []
    for spec in COCKPIT_AXIS_PRESENTATION:
        keys = (spec["primary"], *spec["receipt_members"])
        for key in keys:
            if key == "leverage_cascade":
                continue
            rows.append({
                "key": key,
                "state_en": f"{key} state",
                "state_zh": f"{key} 状态",
                "tone": "neutral",
                "grade": "CONTEXT",
            })
    return {
        "ok": True,
        "band": "NEUTRAL",
        "band_zh": "中性",
        "headline_en": "Evidence is mixed.",
        "headline_zh": "证据分化。",
        "score": 4,
        "board": [{"rows": rows}],
    }


def test_crypto_cockpit_contract_pins_six_axes_and_final_allocation(tmp_path):
    sig = pd.DataFrame(
        {"alloc_optimal": [0.75, 0.0]},
        index=pd.to_datetime(["2026-07-28", "2026-07-29"]),
    )
    regime = {
        "context_legs": {
            "leverage": {
                "ok": True,
                "asof": "2026-07-29",
                "cascade_risk": "low",
            }
        }
    }
    emit_crypto_cockpit_json(
        tmp_path,
        sig,
        _master(),
        regime,
        {"active": True},
        price=63_940.22,
        change_24h_pct=-0.2,
    )
    payload = json.loads((tmp_path / "crypto_cockpit.json").read_text())

    assert payload["schema"] == "crypto.cockpit/v1"
    assert payload["display_only"] is True
    assert payload["hero"]["exposure_pct"] == 0
    assert payload["hero"]["gate_active"] is True
    assert [row["id"] for row in payload["axes"]] == [
        spec["id"] for spec in COCKPIT_AXIS_PRESENTATION
    ]
    leverage = next(
        row for row in payload["axes"] if row["id"] == "leverage_derivatives"
    )
    assert leverage["primary"]["key"] == "leverage_cascade"
    assert leverage["primary"]["state_en"] == "Low"
    assert leverage["spark_source"] == "signals.oi_mcap_ratio"


def test_crypto_cockpit_contract_degrades_missing_leverage_plainly(tmp_path):
    sig = pd.DataFrame(
        {"alloc_optimal": [0.25]},
        index=pd.to_datetime(["2026-07-29"]),
    )
    emit_crypto_cockpit_json(
        tmp_path,
        sig,
        _master(),
        {"ok": False},
        {},
        price=63_940,
        change_24h_pct=0,
    )
    payload = json.loads((tmp_path / "crypto_cockpit.json").read_text())
    leverage = next(
        row for row in payload["axes"] if row["id"] == "leverage_derivatives"
    )
    assert leverage["primary"]["state_en"] == "Unavailable"
    assert leverage["primary"]["state_zh"] == "暂无"
