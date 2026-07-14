from __future__ import annotations

import numpy as np
import pandas as pd

from scripts.research import intraday_large_cap_tech_leader_study as study


def _synthetic_session(date: str = "2026-01-05") -> pd.DataFrame:
    day = pd.Timestamp(date)
    rows = []
    for minute in range(study.RTH_START, study.RTH_END + 1, 5):
        hour, mins = divmod(minute, 60)
        ts = day + pd.Timedelta(hours=hour, minutes=mins)
        base = 100.0 + (minute - study.RTH_START) * 0.001
        rows.append({
            "epoch": int(ts.tz_localize("UTC").timestamp()),
            "ts": ts,
            "date": day,
            "minute": minute,
            "open": base,
            "high": base + 0.2,
            "low": base - 0.2,
            "close": base + 0.1,
            "volume": 1_000.0,
            "ticker": "TEST",
        })
    return pd.DataFrame(rows)


def test_0945_bar_is_outcome_not_feature() -> None:
    bars = _synthetic_session()
    # A huge 09:45 move must not leak into the first-15 feature.  Its open is the
    # executable anchor and its close belongs to the outcome path.
    bars.loc[bars["minute"] == study.ENTRY_MINUTE, ["open", "high", "low", "close"]] = [
        101.0, 151.0, 100.5, 150.0,
    ]
    row = study.session_row(bars, pd.Timestamp("2026-01-05"), "TEST")
    expected_first = (
        bars.loc[bars["minute"] == study.FEATURE_END, "close"].iloc[0]
        / bars.loc[bars["minute"] == study.RTH_START, "open"].iloc[0]
        - 1.0
    )
    assert row["first15_return"] == expected_first
    assert row["entry_0945"] == 101.0
    assert row["mfe"] > 0.40


def test_last_available_options_are_shifted_two_sessions(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(study, "UNIVERSE", ("TEST",))
    dates = pd.bdate_range("2026-01-02", periods=25)
    frame = pd.DataFrame({
        "premium_mn": np.arange(1.0, 26.0),
        "volume": np.arange(100.0, 125.0),
        "pc_ratio": np.full(25, 0.5),
        "zerodte_share": np.full(25, 0.2),
    }, index=dates)
    frame.to_parquet(tmp_path / "summary_TEST.parquet")
    out = study.load_options_features(tmp_path, dates)
    decision = dates[22]
    row = out[out["date"] == decision].iloc[0]
    assert row["opt_source_date"] == dates[20]
    assert row["opt_source_date"] < row["date"]
    assert row["opt_premium_ratio20"] == 21.0 / np.median(np.arange(1.0, 21.0))


def test_modal_winner_is_frozen_from_development_only() -> None:
    dates = pd.to_datetime(["2026-01-05", "2026-01-06", "2026-01-07"])
    rows = []
    for date, winner in zip(dates, ("AAA", "AAA", "BBB")):
        for ticker in ("AAA", "BBB"):
            rows.append({"date": date, "ticker": ticker, "winner": winner})
    labeled = pd.DataFrame(rows)
    assert study.modal_winner(labeled, dates[:2]) == "AAA"
    assert study.modal_winner(labeled, dates[2:]) == "BBB"


def test_relative_winner_and_economic_tie() -> None:
    panel = pd.DataFrame([
        {"date": pd.Timestamp("2026-01-05"), "ticker": "AAA", "after_resid": 0.0200, "after_return": 0.0210},
        {"date": pd.Timestamp("2026-01-05"), "ticker": "BBB", "after_resid": 0.0185, "after_return": 0.0190},
        {"date": pd.Timestamp("2026-01-05"), "ticker": "CCC", "after_resid": 0.0100, "after_return": 0.0300},
    ])
    labeled = study.add_labels(panel, ("AAA", "BBB", "CCC"))
    assert set(labeled["winner"]) == {"AAA"}
    assert set(labeled["raw_winner"]) == {"CCC"}
    ties = set(labeled.loc[labeled["tie_member"], "ticker"])
    assert ties == {"AAA", "BBB"}
    assert bool(labeled["clear_leader"].iloc[0]) is False
