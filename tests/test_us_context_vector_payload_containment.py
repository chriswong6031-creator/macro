"""No entitlement-gated payload may reach the committed candidates store.

`data/us_prophet_rank/candidates/*.parquet` is tracked in a PUBLIC repository.
`engine.neuralweb.context_api.context_frame` flattens each Context Snapshot
dimension's whole ``value`` dict into columns with no allowlist, and
`engine.us_context_vector.context_dimension_frame` merges the result into the
row that gets committed. That pair put the compact Filing Forensics findings —
the same rows `/api/forensics/state` serves only behind `require_site_full_user`
— into a tracked parquet for 722 tickers, where `git clone` reads them.

Two guards here, and the second is the one that lasts:

1. the named paid columns are dropped at the committing seam; and
2. EVERY non-scalar column in the stamped frame is explicitly classified as
   either forbidden or reviewed. The flatten is generic, so without (2) the next
   dimension to grow a paid body leaks in exactly the way forensics did — the
   defect would recur under a different column name and this file would still
   pass.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytest.importorskip("pandas")
pytest.importorskip("pyarrow")

import pandas as pd  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.us_context_vector import (  # noqa: E402
    STAMP_FORBIDDEN_COLUMNS,
    STAMP_REVIEWED_NONSCALAR_COLUMNS,
    context_dimension_frame,
)

ROOT = Path(__file__).resolve().parents[1]


def _fake_context_frame(monkeypatch, columns: dict) -> None:
    """Stand in for context_api.context_frame with an exact column set."""
    import engine.us_context_vector as ucv

    class _FakeContextApi:
        @staticmethod
        def context_frame(tickers, date=None, root=None):
            del date, root
            rows = {"ticker": list(tickers), "date": ["2026-07-31"] * len(tickers)}
            for name, value in columns.items():
                rows[name] = [value] * len(tickers)
            return pd.DataFrame(rows)

    real_import = __import__

    def _fake_import(name, *args, **kwargs):
        if name == "engine.neuralweb":
            class _Mod:
                context_api = _FakeContextApi
            return _Mod
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", _fake_import)
    return ucv


def test_the_paid_forensics_body_is_dropped_at_the_committing_seam(monkeypatch) -> None:
    ucv = _fake_context_frame(
        monkeypatch,
        {
            "forensics__findings": [{"id": "x", "title": "PAID TITLE", "summary": "PAID SUMMARY"}],
            "forensics__disclosure_changes": [{"accession": "0000-00-000000"}],
            "forensics__action": "review_now",
            "forensics__latest_period": "FY2026Q2",
            "forensics__absent": False,
        },
    )
    frame = ucv.context_dimension_frame(["AAPL"], "2026-07-31")

    assert "forensics__findings" not in frame.columns
    assert "forensics__disclosure_changes" not in frame.columns
    rendered = frame.to_json()
    assert "PAID TITLE" not in rendered
    assert "PAID SUMMARY" not in rendered

    # The zero-authority telemetry survives: this must not become a blanket
    # "drop everything forensics", which would remove the seam's whole value.
    for kept in ("forensics__action", "forensics__latest_period", "forensics__absent"):
        assert kept in frame.columns


def test_every_forbidden_column_is_actually_dropped(monkeypatch) -> None:
    """Pins the drop to the declared set rather than to two hard-coded names."""
    ucv = _fake_context_frame(
        monkeypatch, {name: [{"leak": True}] for name in sorted(STAMP_FORBIDDEN_COLUMNS)}
    )
    frame = ucv.context_dimension_frame(["AAPL"], "2026-07-31")
    assert not (set(frame.columns) & STAMP_FORBIDDEN_COLUMNS)


def test_an_unclassified_payload_column_is_a_hard_failure(monkeypatch) -> None:
    """The durable guard: a NEW paid body must not ride in unclassified.

    This is what makes the fix survive. Dropping two names by hand protects
    against today's leak; the flatten in context_api is generic, so the next
    dimension to carry a payload would reproduce it under a different name.
    """
    ucv = _fake_context_frame(
        monkeypatch,
        {"somenewdim__records": [{"secret": "payload"}], "scalar__ok": "fine"},
    )
    frame = ucv.context_dimension_frame(["AAPL"], "2026-07-31")

    unclassified = []
    for column in frame.columns:
        series = frame[column].dropna()
        if not len(series):
            continue
        if isinstance(series.iloc[0], (list, dict)):
            if (
                column not in STAMP_FORBIDDEN_COLUMNS
                and column not in STAMP_REVIEWED_NONSCALAR_COLUMNS
            ):
                unclassified.append(column)

    assert unclassified == ["somenewdim__records"], (
        "the classification sweep must SEE an unclassified payload column; "
        f"got {unclassified}"
    )


def test_the_committed_store_is_swept_for_unclassified_payloads() -> None:
    """Every non-scalar column already on disk must be classified.

    Skips when the store is absent (thin CI lanes do not check out data/).
    This intentionally reports the CURRENT state: the historical part still
    holds the forensics payload until it is purged, which is a separate
    operator decision — so this asserts CLASSIFICATION, not absence.
    """
    store = ROOT / "data" / "us_prophet_rank" / "candidates"
    parts = sorted(store.glob("*.parquet")) if store.is_dir() else []
    if not parts:
        pytest.skip("candidates store not present in this checkout")

    unclassified: list[str] = []
    for part in parts:
        frame = pd.read_parquet(part)
        for column in frame.columns:
            series = frame[column].dropna()
            if not len(series):
                continue
            if isinstance(series.iloc[0], (list, dict)):
                if (
                    column not in STAMP_FORBIDDEN_COLUMNS
                    and column not in STAMP_REVIEWED_NONSCALAR_COLUMNS
                ):
                    unclassified.append(f"{part.name}:{column}")

    assert not unclassified, (
        "unclassified payload column(s) in the committed store — classify each as "
        "forbidden (paid body) or reviewed (deliberately carried) in "
        f"engine/us_context_vector.py: {sorted(set(unclassified))}"
    )
