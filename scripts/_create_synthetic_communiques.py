#!/usr/bin/env python3
"""Create a realistic synthetic communiques.parquet for the F-C study.

This creates a synthetic file with:
  - ~68 PBoC MPC quarterly readouts (2009 Q1 → 2025 Q4)
  - Realistic phrase transitions matching the known policy arc
  - Deterministic (seeded) content for reproducibility

NOT a substitute for the real backfill (use scripts/backfill_china_communiques.py
for production use). This is for the F-C study runner when the real parquet is
unavailable, and for CI/tests.

The phrase transitions in this synthetic data reflect the known policy arc:
  2009-2012: post-GFC easing → tightening (适度宽松 → 稳健)
  2013-2017: 稳健中性 era
  2018-2019: LPR reform, 逆周期调节 introduced
  2020-2021: COVID response, 灵活适度
  2022-2023: 稳增长 amid property crisis, 房住不炒 intact
  2024-2025: 适度宽松 reintroduced (Dec 2024 Politburo), 超常规逆周期调节

These transitions are based on publicly known PBoC policy language history, not
backtested outcomes. Polarity remains UNSIGNED.
"""
from __future__ import annotations

import hashlib
import pathlib
import sys
from datetime import date, datetime, timezone

import pandas as pd

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT_PATH = REPO_ROOT / "data" / "china_official" / "communiques.parquet"
OUT_PATH.parent.mkdir(parents=True, exist_ok=True)

SCHEMA_COLS = [
    "doc_id", "family", "meeting_year", "meeting_quarter",
    "meeting_date", "publish_date", "title", "body", "body_sha256",
    "url", "source", "_fetched_at",
]

# Known PBoC MPC quarterly meeting dates (approx; from public PBoC records)
# Format: (year, quarter, meeting_date_str, publish_date_str)
# publish_date is typically 1-3 days after meeting closes
MPC_MEETINGS: list[tuple[int, int, str, str | None]] = [
    # 2009 - post-GFC easing era
    (2009, 1, "2009-03-24", "2009-03-26"),
    (2009, 2, "2009-06-23", "2009-06-25"),
    (2009, 3, "2009-09-22", "2009-09-24"),
    (2009, 4, "2009-12-15", "2009-12-17"),
    # 2010 - policy normalization begins
    (2010, 1, "2010-03-23", "2010-03-25"),
    (2010, 2, "2010-06-25", "2010-06-27"),
    (2010, 3, "2010-09-14", "2010-09-16"),
    (2010, 4, "2010-12-14", "2010-12-16"),
    # 2011 - tightening
    (2011, 1, "2011-03-25", "2011-03-27"),
    (2011, 2, "2011-06-23", "2011-06-25"),
    (2011, 3, "2011-09-22", "2011-09-24"),
    (2011, 4, "2011-12-15", "2011-12-17"),
    # 2012 - easing resumes
    (2012, 1, "2012-03-27", "2012-03-29"),
    (2012, 2, "2012-06-26", "2012-06-28"),
    (2012, 3, "2012-09-18", "2012-09-20"),
    (2012, 4, "2012-12-18", "2012-12-20"),
    # 2013 - 稳健 becomes 稳健中性 era
    (2013, 1, "2013-03-26", "2013-03-28"),
    (2013, 2, "2013-06-25", "2013-06-27"),
    (2013, 3, "2013-09-24", "2013-09-26"),
    (2013, 4, "2013-12-24", "2013-12-26"),
    # 2014
    (2014, 1, "2014-03-25", "2014-03-27"),
    (2014, 2, "2014-06-24", "2014-06-26"),
    (2014, 3, "2014-09-23", "2014-09-25"),
    (2014, 4, "2014-12-23", "2014-12-25"),
    # 2015 - growth pressure, 降准降息
    (2015, 1, "2015-03-31", "2015-04-02"),
    (2015, 2, "2015-06-30", "2015-07-02"),
    (2015, 3, "2015-09-22", "2015-09-24"),
    (2015, 4, "2015-12-22", "2015-12-24"),
    # 2016
    (2016, 1, "2016-03-29", "2016-03-31"),
    (2016, 2, "2016-06-28", "2016-06-30"),
    (2016, 3, "2016-09-27", "2016-09-29"),
    (2016, 4, "2016-12-20", "2016-12-22"),
    # 2017 - 稳健中性 explicit, 防范化解风险
    (2017, 1, "2017-03-28", "2017-03-30"),
    (2017, 2, "2017-06-27", "2017-06-29"),
    (2017, 3, "2017-09-26", "2017-09-28"),
    (2017, 4, "2017-12-19", "2017-12-21"),
    # 2018 - 跨周期, 稳增长
    (2018, 1, "2018-03-27", "2018-03-29"),
    (2018, 2, "2018-06-26", "2018-06-28"),
    (2018, 3, "2018-09-25", "2018-09-27"),
    (2018, 4, "2018-12-25", "2018-12-27"),
    # 2019 - 逆周期调节, LPR reform
    (2019, 1, "2019-03-26", "2019-03-28"),
    (2019, 2, "2019-06-25", "2019-06-27"),
    (2019, 3, "2019-09-24", "2019-09-26"),
    (2019, 4, "2019-12-24", "2019-12-26"),
    # 2020 - COVID: 灵活适度, 超常规
    (2020, 1, "2020-03-31", "2020-04-02"),
    (2020, 2, "2020-06-23", "2020-06-25"),
    (2020, 3, "2020-09-22", "2020-09-24"),
    (2020, 4, "2020-12-22", "2020-12-24"),
    # 2021 - exit COVID support, 跨周期
    (2021, 1, "2021-03-30", "2021-04-01"),
    (2021, 2, "2021-06-29", "2021-07-01"),
    (2021, 3, "2021-09-28", "2021-09-30"),
    (2021, 4, "2021-12-28", "2021-12-30"),
    # 2022 - 稳增长 priority, property stress
    (2022, 1, "2022-03-29", "2022-03-31"),
    (2022, 2, "2022-06-28", "2022-06-30"),
    (2022, 3, "2022-09-27", "2022-09-29"),
    (2022, 4, "2022-12-27", "2022-12-29"),
    # 2023 - 扩大内需, 民营经济
    (2023, 1, "2023-03-28", "2023-03-30"),
    (2023, 2, "2023-06-27", "2023-06-29"),
    (2023, 3, "2023-09-26", "2023-09-28"),
    (2023, 4, "2023-12-26", "2023-12-28"),
    # 2024 - 适度宽松 reintroduced Dec Politburo
    (2024, 1, "2024-03-26", "2024-03-28"),
    (2024, 2, "2024-06-25", "2024-06-27"),
    (2024, 3, "2024-09-24", "2024-09-26"),
    (2024, 4, "2024-12-24", "2024-12-26"),
    # 2025 - 适度宽松, 超常规逆周期调节
    (2025, 1, "2025-03-25", "2025-03-27"),
    (2025, 2, "2025-06-24", "2025-06-26"),
    (2025, 3, "2025-09-23", "2025-09-25"),
    (2025, 4, "2025-12-23", "2025-12-25"),
]

# Phrase profile per era — which phrases appear in the body
# This approximates the known policy language arc
def _era_phrases(year: int, quarter: int) -> set[str]:
    """Return the set of phrase-book phrases present in this meeting's readout."""
    phrases: set[str] = set()

    # Monetary stance
    if (year, quarter) < (2010, 4):
        phrases.add("适度宽松")          # post-GFC: 适度宽松 货币政策
    elif (year, quarter) < (2017, 1):
        phrases.add("稳健的货币政策")    # 2011-2016: 稳健
    elif (year, quarter) < (2018, 1):
        phrases.add("稳健中性")          # 2017: 稳健中性
    elif (year, quarter) < (2024, 4):
        phrases.add("稳健的货币政策")    # 2018-2024Q3: back to 稳健
    else:
        phrases.add("适度宽松")          # 2024Q4+: 适度宽松 reintroduced

    # Counter-cyclical
    if (2018, 4) <= (year, quarter) <= (2019, 4):
        phrases.add("逆周期调节")
    if (year, quarter) >= (2020, 1) and (year, quarter) <= (2021, 2):
        phrases.add("逆周期调节")
        phrases.add("灵活适度")
    if (year, quarter) >= (2025, 1):
        phrases.add("超常规逆周期调节")

    # Cross-cyclical
    if (2021, 3) <= (year, quarter) <= (2023, 2):
        phrases.add("跨周期调节")

    # 保持流动性合理充裕
    if (year, quarter) >= (2020, 1):
        phrases.add("保持流动性合理充裕")

    # 稳增长 / growth support
    if year in (2012, 2015, 2016, 2018, 2019, 2022, 2023, 2024):
        phrases.add("稳增长")
    if (year, quarter) >= (2022, 1):
        phrases.add("稳预期")

    # 扩大内需
    if year in (2022, 2023, 2024, 2025):
        phrases.add("扩大内需")

    # 提振消费
    if (year, quarter) >= (2023, 3):
        phrases.add("提振消费")

    # 积极的财政政策
    if year in (2009, 2010, 2015, 2016, 2019, 2020, 2021, 2022, 2023, 2024, 2025):
        phrases.add("积极的财政政策")

    # 更加积极的财政政策 (2024+)
    if (year, quarter) >= (2024, 4):
        phrases.add("更加积极的财政政策")

    # 房住不炒 (2016-2023; dropped 2024)
    if (2017, 1) <= (year, quarter) <= (2023, 4):
        phrases.add("房住不炒")

    # 保交楼 (2022+)
    if (year, quarter) >= (2022, 2):
        phrases.add("保交楼")

    # 止跌回稳 (property stabilization, 2024+)
    if (year, quarter) >= (2024, 3):
        phrases.add("止跌回稳")

    # 防范化解风险 (2017-2020)
    if (2017, 1) <= (year, quarter) <= (2020, 2):
        phrases.add("防范化解风险")

    # 新质生产力 (2024+)
    if (year, quarter) >= (2024, 1):
        phrases.add("新质生产力")

    # 民营经济 (2023+)
    if (year, quarter) >= (2023, 2):
        phrases.add("民营经济")

    # 稳就业 (2020+)
    if (year, quarter) >= (2020, 1):
        phrases.add("稳就业")

    # 高质量发展 (2018+)
    if (year, quarter) >= (2018, 1):
        phrases.add("高质量发展")

    # 科技自立自强 (2021+)
    if (year, quarter) >= (2021, 2):
        phrases.add("科技自立自强")

    # 专项债 (local bonds, episodic)
    if year in (2018, 2019, 2020, 2022, 2023):
        phrases.add("专项债")

    # 特别国债 (2020 COVID bonds, 2024)
    if year in (2020,) or (year, quarter) >= (2024, 2):
        phrases.add("特别国债")

    # 降准降息 (easing episodes)
    if year in (2012, 2014, 2015, 2019, 2020, 2021, 2022, 2023, 2024):
        phrases.add("降准降息")

    # 稳中求进 (general; 2015+)
    if (year, quarter) >= (2015, 1):
        phrases.add("稳中求进")

    return phrases


def _build_body(year: int, quarter: int, phrases: set[str]) -> str:
    """Build a synthetic readout body containing all the required phrases."""
    lines = [
        f"中国人民银行货币政策委员会{year}年第{quarter}季度例会",
        f"会议于{year}年召开。",
        f"会议认为，当前中国经济运行总体平稳，",
    ]

    # Add phrase content
    phrase_list = sorted(phrases)
    for ph in phrase_list:
        lines.append(f"会议强调要坚持{ph}，推动经济高质量发展。")

    lines.append("会议要求，做好下一阶段货币政策工作。")
    lines.append("会议指出，要统筹兼顾内外均衡，促进金融市场平稳运行。")

    return "\n".join(lines)


def create_synthetic_communiques(out_path: pathlib.Path | None = None) -> pd.DataFrame:
    """Create and write synthetic communiques.parquet. Returns the DataFrame."""
    fetched_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    rows = []

    for (year, quarter, meeting_date, publish_date) in MPC_MEETINGS:
        phrases = _era_phrases(year, quarter)
        body = _build_body(year, quarter, phrases)
        title = f"中国人民银行货币政策委员会{year}年第{quarter}季度例会"
        url = f"https://www.pbc.gov.cn/synthetic/mpc_{year}_Q{quarter}/index.html"
        doc_id = hashlib.sha256(f"{url}|{title}".encode()).hexdigest()
        body_sha256 = hashlib.sha256(body.encode()).hexdigest()

        rows.append({
            "doc_id": doc_id,
            "family": "pboc_mpc",
            "meeting_year": year,
            "meeting_quarter": quarter,
            "meeting_date": meeting_date,
            "publish_date": publish_date,
            "title": title,
            "body": body,
            "body_sha256": body_sha256,
            "url": url,
            "source": "synthetic_for_study",
            "_fetched_at": fetched_at,
        })

    df = pd.DataFrame(rows, columns=SCHEMA_COLS)
    path = out_path or OUT_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, compression="zstd", index=False)
    print(f"Created synthetic communiques.parquet: {len(df)} rows → {path}")
    return df


if __name__ == "__main__":
    create_synthetic_communiques()
