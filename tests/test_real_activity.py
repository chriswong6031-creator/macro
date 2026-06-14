"""Real-activity nowcast collectors — pure parsing on inline fixtures, no network.

Covers the Treasury DTS withheld-tax flow and the SF Fed Daily News Sentiment
xlsx. See research/REAL_ACTIVITY_NOWCAST.md.

Run: .venv/bin/python -m tests.test_real_activity
"""
from __future__ import annotations

import io
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collectors.frbsf import NewsSentimentAdapter  # noqa: E402
from collectors.treasury import TreasuryAdapter  # noqa: E402


def test_withheld_tax_parse_and_dedupe() -> None:
    a = TreasuryAdapter.__new__(TreasuryAdapter)  # skip __init__/config
    a.cfg = {}                                    # _fetch_withheld uses .get defaults
    rows = [
        {"record_date": "2026-06-09", "transaction_catg": "Taxes - Withheld Individual/FICA",
         "transaction_today_amt": "3084"},
        {"record_date": "2026-06-10", "transaction_catg": "Taxes - Withheld Individual/FICA",
         "transaction_today_amt": "11249"},
        # same day split across two rows must SUM, not drop
        {"record_date": "2026-06-11", "transaction_catg": "Taxes - Withheld Individual/FICA",
         "transaction_today_amt": "4000"},
        {"record_date": "2026-06-11", "transaction_catg": "Taxes - Withheld Individual/FICA",
         "transaction_today_amt": "938"},
    ]
    a._paged = lambda *args, **kw: rows  # type: ignore[assignment]
    df = a._fetch_withheld("2026-06-01")
    assert list(df.columns) == ["withheld_tax_mn"]
    assert df.loc["2026-06-10", "withheld_tax_mn"] == 11249
    assert df.loc["2026-06-11", "withheld_tax_mn"] == 4938   # 4000 + 938
    assert df.index.name == "date"


def _make_news_xlsx() -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        pd.DataFrame({"hdr": ["methodology blurb"]}).to_excel(
            w, sheet_name="Methodology", index=False)
        pd.DataFrame({
            "date": pd.to_datetime(["1980-01-01", "1980-01-02", "1980-01-03"]),
            "News Sentiment": [-0.0379, -0.1065, None],   # trailing NaN must drop
        }).to_excel(w, sheet_name="Data", index=False)
    return buf.getvalue()


def test_news_sentiment_parse_picks_data_sheet() -> None:
    df = NewsSentimentAdapter._parse(_make_news_xlsx())
    assert list(df.columns) == ["news_sentiment"]
    assert len(df) == 2                                   # NaN row dropped
    assert abs(df["news_sentiment"].iloc[0] + 0.0379) < 1e-9
    assert df.index[0].year == 1980


if __name__ == "__main__":
    test_withheld_tax_parse_and_dedupe()
    test_news_sentiment_parse_picks_data_sheet()
    print("ok")
