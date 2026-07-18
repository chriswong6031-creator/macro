#!/usr/bin/env python3
"""Reproduce the Grade-A manager Q1-2026 Add/New performance study.

The cohort is read from the current ``smartmoney_tracker.json`` leaderboard.
Position changes are reconstructed from the 2025-12-31 and 2026-03-31 13F
snapshots. Returns use a common 2026-05-15 close anchor, as requested, and
calendar-day checkpoints (10/20/30/40/50/60 days), rolled forward to the first
trading close on or after each target date.

The script also records SEC acceptance timestamps and an investable-entry
sensitivity because many May 15 filings were accepted at or after the close.
It writes only research artifacts and does not feed any live score or product.
"""
from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import quote

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from engine.manager_trades import ClosePanel
from engine.smart_money import (
    diff_snapshots,
    full_cusip_map,
    name_ticker_map,
    resolve_tickers,
)
from lib import config


ANCHOR = pd.Timestamp("2026-05-15")
REPORT_PERIOD = "2026-03-31"
PREVIOUS_PERIOD = "2025-12-31"
HORIZONS = (10, 20, 30, 40, 50, 60)
OUTPUT_DIR = Path("research/artifacts/SMART_MONEY_GRADE_A_2026Q1")
USER_AGENT = "Macro Dashboard 13F research longr2512@gmail.com"

# These are exchange-traded debt, warrants, or preferred/depositary units rather
# than common-equity/ADR/ETF positions. They remain visible in excluded rows.
NON_COMMON_TITLE_PATTERNS = (
    "NOTE ",
    "UNIT 02/",
    "W EXP ",
    "DEP CUM",
)

# The OpenFIGI cache sometimes resolves a US 13F CUSIP to a foreign/exchange
# alias (or misses a foreign-incorporated US listing). These issuer overrides are
# narrow, hand-checked corrections for the Q1 Grade-A cohort only.
ISSUER_TICKER_OVERRIDES = {
    "WAVE LIFE SCIENCES": "WVE",
    "QIAGEN": "QGEN",
    "BBB FOODS": "TBBB",
    "SEAGATE TECHNOLOGY": "STX",
    "JBS N.V": "JBS",
    "LYONDELLBASELL": "LYB",
    "TRANSOCEAN": "RIG",
    "JFROG": "FROG",
    "CELLEBRITE": "CLBT",
    "HELIX ACQUISITION": "HLXA",
    "ICON PLC": "ICLR",
    "BITDEER": "BTDR",
    "WIX COM": "WIX",
    "ELASTIC N V": "ESTC",
    "VERIS RESIDENTIAL": "VRE",
    "GLOBALFOUNDRIES": "GFS",
    "SPRING VY ACQUISITION": "SVII",
    "STELLANTIS": "STLA",
    "AMER SPORTS": "AS",
    "CANTOR EQUITY PARTNERS V": "CEPV",
    "CANTOR EQUITY PARTNERS II": "CEPT",
    "GRAB HOLDINGS": "GRAB",
    "TOWER SEMICONDUCTOR": "TSEM",
    "AMICUS THERAPEUTIC": "FOLD",
    "APELLIS PHARMACEUTICALS": "APLS",
    "ARCELLX": "ACLX",
    "DAY ONE BIOPHARMACEUTICALS": "DAWN",
    "ENHABIT": "EHAB",
    "GOLDEN ENTMT": "GDEN",
    "PEAKSTONE REALTY": "PKST",
    "HOLOGIC": "HOLX",
    "HONEYWELL": "HON",
    "MASIMO": "MASI",
    "ONESTREAM": "OS",
    "SELECT MED": "SEM",
    "SEALED AIR": "SEE",
    "SEMRUSH": "SEMR",
    "TRI POINTE HOMES": "TPH",
    "TERNS PHARMACEUTICALS": "TERN",
    "THERMON GROUP": "THR",
    "UDEMY": "UDMY",
}


def _curl_json(url: str, user_agent: str, attempts: int = 3) -> dict | None:
    """Fetch JSON with curl, retrying transient Yahoo/SEC throttles."""
    for attempt in range(attempts):
        proc = subprocess.run(
            [
                "curl",
                "-A",
                user_agent,
                "-L",
                "--fail",
                "--silent",
                "--show-error",
                "--max-time",
                "25",
                url,
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode == 0:
            try:
                return json.loads(proc.stdout)
            except json.JSONDecodeError:
                pass
        if attempt + 1 < attempts:
            time.sleep(0.6 * (attempt + 1))
    return None


def _sec_filing_manifest(funds: list[str], cfg: dict) -> pd.DataFrame:
    rows: list[dict] = []
    for slug in funds:
        spec = cfg["funds"][slug]
        cik = int(spec["cik"])
        url = f"https://data.sec.gov/submissions/CIK{cik:010d}.json"
        payload = _curl_json(url, USER_AGENT)
        matched = None
        if payload:
            recent = payload.get("filings", {}).get("recent", {})
            forms = recent.get("form", [])
            for idx, form in enumerate(forms):
                if form != "13F-HR":
                    continue
                if recent.get("reportDate", [None] * len(forms))[idx] != REPORT_PERIOD:
                    continue
                matched = {key: recent.get(key, [None] * len(forms))[idx] for key in (
                    "accessionNumber",
                    "filingDate",
                    "reportDate",
                    "acceptanceDateTime",
                    "primaryDocument",
                )}
                break
        row = {
            "fund": slug,
            "fund_name": spec.get("name", slug),
            "cik": cik,
            "submissions_url": url,
        }
        if matched:
            accession = str(matched["accessionNumber"])
            archive = accession.replace("-", "")
            row.update(matched)
            row["filing_index_url"] = (
                f"https://www.sec.gov/Archives/edgar/data/{cik}/{archive}/"
                f"{accession}-index.html"
            )
            accepted = pd.Timestamp(matched["acceptanceDateTime"])
            if accepted.tzinfo is None:
                accepted = accepted.tz_localize("UTC")
            accepted_et = accepted.tz_convert("America/New_York")
            row["accepted_et"] = accepted_et.isoformat()
            row["accepted_after_close"] = accepted_et.hour >= 16
        rows.append(row)
    return pd.DataFrame(rows)


def _is_common_equity(title_class: object) -> bool:
    title = str(title_class or "").strip().upper()
    return not any(pattern in title for pattern in NON_COMMON_TITLE_PATTERNS)


def _issuer_override(issuer: object) -> str | None:
    name = str(issuer or "").strip().upper()
    for prefix, ticker in ISSUER_TICKER_OVERRIDES.items():
        if name.startswith(prefix):
            return ticker
    return None


def _position_changes(
    funds: list[str],
    tracker: dict,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    name_map = name_ticker_map()
    cusip_map, _coverage = full_cusip_map()
    board = {row["slug"]: row for row in tracker["leaderboard"]}
    included: list[pd.DataFrame] = []
    excluded: list[pd.DataFrame] = []

    for slug in funds:
        folder = config.data_dir() / "smart_money" / slug
        prev = pd.read_parquet(folder / f"{PREVIOUS_PERIOD}.parquet")
        current = pd.read_parquet(folder / f"{REPORT_PERIOD}.parquet")
        diff = resolve_tickers(diff_snapshots(prev, current), name_map, cusip_map)
        overrides = diff["issuer"].map(_issuer_override)
        diff.loc[overrides.notna(), "ticker"] = overrides[overrides.notna()]
        title_by_cusip = current.groupby("cusip")["title_class"].first()
        diff["title_class"] = diff["cusip"].map(title_by_cusip)
        buys = diff[diff["action"].isin(["add", "new"])].copy()
        buys["fund"] = slug
        buys["fund_name"] = board[slug]["name"]
        buys["grade"] = board[slug]["grade"]
        buys["is_common_equity"] = buys["title_class"].map(_is_common_equity)
        buys["exclusion_reason"] = ""
        buys.loc[~buys["is_common_equity"], "exclusion_reason"] = "non_common_security"
        buys.loc[buys["ticker"].isna(), "exclusion_reason"] = "unresolved_ticker"

        reject = buys[(~buys["is_common_equity"]) | buys["ticker"].isna()].copy()
        excluded.append(reject)
        keep = buys[buys["is_common_equity"] & buys["ticker"].notna()].copy()
        keep["incremental_book_pct"] = keep["pct_portfolio"]
        add_mask = keep["action"].eq("add")
        delta = keep.loc[add_mask, "shares_change_pct"].astype(float)
        keep.loc[add_mask, "incremental_book_pct"] = (
            keep.loc[add_mask, "pct_portfolio"] * delta / (100.0 + delta)
        )

        # Collapse duplicate CUSIP/class lines that resolve to the same ticker.
        grouped_rows = []
        for ticker, group in keep.groupby("ticker", sort=False):
            actions = set(group["action"])
            action = next(iter(actions)) if len(actions) == 1 else "mixed"
            largest = group.sort_values("value_usd", ascending=False).iloc[0]
            grouped_rows.append({
                "fund": slug,
                "fund_name": board[slug]["name"],
                "grade": board[slug]["grade"],
                "ticker": ticker,
                "issuer": largest["issuer"],
                "title_class": largest["title_class"],
                "action": action,
                "shares_change_pct": (
                    float(largest["shares_change_pct"])
                    if pd.notna(largest["shares_change_pct"])
                    else math.nan
                ),
                "book_pct": float(group["pct_portfolio"].sum()),
                "incremental_book_pct": float(group["incremental_book_pct"].sum()),
                "value_usd_reported": float(group["value_usd"].sum()),
                "cusips": ";".join(sorted(group["cusip"].astype(str).unique())),
                "n_security_lines": len(group),
            })
        included.append(pd.DataFrame(grouped_rows))

    positions = pd.concat(included, ignore_index=True)
    rejects = pd.concat(excluded, ignore_index=True)
    return positions, rejects


def _network_yahoo_series(ticker: str) -> pd.Series | None:
    start = int(pd.Timestamp("2026-05-10", tz="UTC").timestamp())
    end = int(pd.Timestamp("2026-07-19", tz="UTC").timestamp())
    symbol = quote(ticker, safe="")
    url = (
        f"https://query2.finance.yahoo.com/v8/finance/chart/{symbol}"
        f"?period1={start}&period2={end}&interval=1d"
        "&events=div%2Csplits&includeAdjustedClose=true"
    )
    payload = _curl_json(url, "Mozilla/5.0")
    if not payload:
        return None
    try:
        result = payload["chart"]["result"][0]
        timestamps = result["timestamp"]
        indicators = result["indicators"]
        values = indicators.get("adjclose", [{}])[0].get("adjclose")
        if not values:
            values = indicators["quote"][0]["close"]
        index = (
            pd.to_datetime(timestamps, unit="s", utc=True)
            .tz_convert("America/New_York")
            .normalize()
            .tz_localize(None)
        )
        series = pd.Series(values, index=index, dtype=float).dropna().sort_index()
        return series if len(series) else None
    except (KeyError, IndexError, TypeError):
        return None


def _price_series(ticker: str, panel: ClosePanel) -> tuple[pd.Series | None, str]:
    # Pull a fresh, consistently back-adjusted path first. Local Yahoo parquet
    # files can mix pre- and post-dividend adjustment vintages if they were
    # incrementally refreshed; that is harmless for the live close panel but not
    # for a precise multi-horizon total-return study.
    network = _network_yahoo_series(ticker)
    if network is not None and len(network):
        if network.index.min() <= ANCHOR and network.index.max() >= ANCHOR + pd.Timedelta(days=60):
            return network, "yahoo_chart_api"
    local = panel.get(ticker)
    if local is not None and len(local):
        series = local.copy()
        series.index = pd.to_datetime(series.index).tz_localize(None)
        series = series.sort_index().dropna()
        if series.index.min() <= ANCHOR and series.index.max() >= ANCHOR + pd.Timedelta(days=60):
            source = "local_yahoo" if (config.data_dir() / "yahoo" / f"{ticker}.parquet").exists() else "local_breadth"
            return series, source
    return (None, "unpriced")


def _at_or_after(series: pd.Series, date: pd.Timestamp) -> tuple[pd.Timestamp, float] | None:
    eligible = series.index[series.index >= date]
    if len(eligible) == 0:
        return None
    actual = eligible[0]
    return actual, float(series.loc[actual])


def _add_returns(
    positions: pd.DataFrame,
    filing_manifest: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    panel = ClosePanel()
    spy, spy_source = _price_series("SPY", panel)
    if spy is None:
        raise RuntimeError("SPY could not be priced")
    spy_entry = _at_or_after(spy, ANCHOR)
    if spy_entry is None:
        raise RuntimeError("SPY has no filing-date anchor")
    _, spy_p0 = spy_entry

    filing_by_fund = filing_manifest.set_index("fund").to_dict("index")
    price_cache: dict[str, tuple[pd.Series | None, str]] = {}
    rows: list[dict] = []
    unpriced: list[dict] = []
    for idx, record in enumerate(positions.to_dict("records"), start=1):
        ticker = str(record["ticker"])
        if ticker not in price_cache:
            price_cache[ticker] = _price_series(ticker, panel)
            if price_cache[ticker][1] == "yahoo_chart_api":
                time.sleep(0.06)
        series, source = price_cache[ticker]
        if series is None:
            miss = dict(record)
            miss["exclusion_reason"] = "unpriced_ticker"
            miss["price_source"] = source
            unpriced.append(miss)
            continue
        entry = _at_or_after(series, ANCHOR)
        if entry is None:
            miss = dict(record)
            miss["exclusion_reason"] = "missing_anchor_price"
            miss["price_source"] = source
            unpriced.append(miss)
            continue
        entry_date, entry_price = entry
        row = dict(record)
        row.update({
            "anchor_requested": ANCHOR.date().isoformat(),
            "entry_date": entry_date.date().isoformat(),
            "entry_adjusted_close": entry_price,
            "price_source": source,
            "spy_price_source": spy_source,
        })
        complete = True
        for horizon in HORIZONS:
            target = ANCHOR + pd.Timedelta(days=horizon)
            stock_end = _at_or_after(series, target)
            spy_end = _at_or_after(spy, target)
            if stock_end is None or spy_end is None:
                complete = False
                break
            end_date, end_price = stock_end
            spy_date, spy_price = spy_end
            stock_return = end_price / entry_price - 1.0
            spy_return = spy_price / spy_p0 - 1.0
            row[f"target_{horizon}d"] = target.date().isoformat()
            row[f"price_date_{horizon}d"] = end_date.date().isoformat()
            row[f"spy_date_{horizon}d"] = spy_date.date().isoformat()
            row[f"return_{horizon}d"] = stock_return
            row[f"spy_return_{horizon}d"] = spy_return
            row[f"excess_{horizon}d"] = stock_return - spy_return
        if not complete:
            miss = dict(record)
            miss["exclusion_reason"] = "incomplete_60d_price_path"
            miss["price_source"] = source
            unpriced.append(miss)
            continue

        # Investable sensitivity: same-day close only for a before-close filing;
        # otherwise first close strictly after the filing date.
        filing = filing_by_fund.get(record["fund"], {})
        filing_date = pd.Timestamp(filing.get("filingDate", ANCHOR))
        if filing.get("accepted_after_close") is True:
            filing_date += pd.Timedelta(days=1)
        investable_entry = _at_or_after(series, filing_date)
        sensitivity_end = _at_or_after(series, ANCHOR + pd.Timedelta(days=60))
        if investable_entry and sensitivity_end:
            inv_date, inv_price = investable_entry
            sens_date, sens_price = sensitivity_end
            row["investable_entry_date"] = inv_date.date().isoformat()
            row["investable_entry_adjusted_close"] = inv_price
            row["investable_return_to_60d_date"] = sens_price / inv_price - 1.0
            row["investable_end_date"] = sens_date.date().isoformat()
        rows.append(row)
        if idx % 50 == 0:
            print(f"priced {idx}/{len(positions)} position rows")
    return pd.DataFrame(rows), pd.DataFrame(unpriced)


def _weighted_average(values: pd.Series, weights: pd.Series) -> float:
    mask = values.notna() & weights.notna() & weights.gt(0)
    if not mask.any():
        return math.nan
    return float((values[mask] * weights[mask]).sum() / weights[mask].sum())


def _aggregate(
    priced: pd.DataFrame,
    all_positions: pd.DataFrame,
    group_cols: list[str],
) -> pd.DataFrame:
    rows: list[dict] = []
    all_grouped = all_positions.groupby(group_cols, dropna=False, sort=False)
    priced_grouped = priced.groupby(group_cols, dropna=False, sort=False)
    for key, all_group in all_grouped:
        key_tuple = key if isinstance(key, tuple) else (key,)
        try:
            priced_group = priced_grouped.get_group(key)
        except KeyError:
            priced_group = priced.iloc[0:0]
        base = dict(zip(group_cols, key_tuple))
        base.update({
            "n_positions": len(all_group),
            "n_priced": len(priced_group),
            "count_coverage_pct": 100.0 * len(priced_group) / len(all_group),
            "buy_final_book_pct": float(all_group["book_pct"].sum()),
            "buy_incremental_book_pct": float(all_group["incremental_book_pct"].sum()),
            "priced_final_book_pct": float(priced_group["book_pct"].sum()),
            "priced_incremental_book_pct": float(priced_group["incremental_book_pct"].sum()),
        })
        denom = base["buy_incremental_book_pct"]
        base["incremental_book_coverage_pct"] = (
            100.0 * base["priced_incremental_book_pct"] / denom if denom else math.nan
        )
        for horizon in HORIZONS:
            ret = priced_group.get(f"return_{horizon}d", pd.Series(dtype=float))
            excess = priced_group.get(f"excess_{horizon}d", pd.Series(dtype=float))
            inc_weight = priced_group.get("incremental_book_pct", pd.Series(dtype=float))
            final_weight = priced_group.get("book_pct", pd.Series(dtype=float))
            base[f"equal_mean_return_{horizon}d"] = float(ret.mean()) if len(ret) else math.nan
            base[f"median_return_{horizon}d"] = float(ret.median()) if len(ret) else math.nan
            base[f"hit_rate_{horizon}d"] = float(ret.gt(0).mean()) if len(ret) else math.nan
            base[f"decision_weighted_return_{horizon}d"] = _weighted_average(ret, inc_weight)
            base[f"decision_weighted_excess_{horizon}d"] = _weighted_average(excess, inc_weight)
            base[f"final_position_weighted_return_{horizon}d"] = _weighted_average(ret, final_weight)
            base[f"estimated_book_contribution_{horizon}d_pp"] = (
                float((ret * inc_weight).sum()) if len(ret) else math.nan
            )
        if len(priced_group) and "investable_return_to_60d_date" in priced_group:
            base["investable_decision_weighted_return_to_60d_date"] = _weighted_average(
                priced_group["investable_return_to_60d_date"],
                priced_group["incremental_book_pct"],
            )
        rows.append(base)
    return pd.DataFrame(rows)


def _dossier_table(tracker: dict, funds: list[str]) -> pd.DataFrame:
    rows = []
    for row in tracker["leaderboard"]:
        if row["slug"] not in funds:
            continue
        rows.append({key: row.get(key) for key in (
            "rank",
            "slug",
            "name",
            "grade",
            "quality_z",
            "n_buys",
            "n_buys_h",
            "n_trades",
            "median_buy_excess",
            "avg_buy_excess",
            "avg_buy_excess_h",
            "buy_hit_rate",
            "coverage_pct",
        )})
    return pd.DataFrame(rows)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    args = parser.parse_args()

    tracker_path = Path("site/factordata/smartmoney_tracker.json")
    tracker = json.loads(tracker_path.read_text())
    funds = [row["slug"] for row in tracker["leaderboard"] if row.get("grade") == "A"]
    smart_cfg = config.load()["smart_money"]

    output = args.output_dir
    output.mkdir(parents=True, exist_ok=True)
    dossiers = _dossier_table(tracker, funds)
    filing_manifest = _sec_filing_manifest(funds, smart_cfg)
    positions, unresolved = _position_changes(funds, tracker)
    priced, unpriced = _add_returns(positions, filing_manifest)
    exclusions = pd.concat([unresolved, unpriced], ignore_index=True, sort=False)
    fund_summary = _aggregate(priced, positions, ["fund", "fund_name"])
    action_summary = _aggregate(priced, positions, ["fund", "fund_name", "action"])

    dossiers.to_csv(output / "grade_a_dossiers.csv", index=False)
    filing_manifest.to_csv(output / "filing_manifest.csv", index=False)
    positions.to_csv(output / "all_resolved_common_equity_buys.csv", index=False)
    priced.to_csv(output / "position_returns.csv", index=False)
    exclusions.to_csv(output / "excluded_or_unpriced.csv", index=False)
    fund_summary.to_csv(output / "fund_horizon_summary.csv", index=False)
    action_summary.to_csv(output / "fund_action_horizon_summary.csv", index=False)
    metadata = {
        "schema": "smart_money_grade_a_q1_2026.v1",
        "tracker_built": tracker.get("built"),
        "tracker_price_thru": tracker.get("coverage", {}).get("price_thru"),
        "cohort_rule": "grade == A in current smartmoney_tracker leaderboard",
        "funds": funds,
        "report_period": REPORT_PERIOD,
        "previous_period": PREVIOUS_PERIOD,
        "common_return_anchor": ANCHOR.date().isoformat(),
        "horizon_unit": "calendar_days_rolled_to_first_trading_close_on_or_after_target",
        "horizons": list(HORIZONS),
        "benchmark": "SPY",
        "position_weight": "Q1 13F final reported book percentage",
        "incremental_weight": (
            "new=final book pct; add=final book pct * shares_added_pct / "
            "(100 + shares_added_pct)"
        ),
        "n_resolved_common_equity_positions": len(positions),
        "n_priced_positions": len(priced),
        "n_excluded_or_unpriced": len(exclusions),
    }
    (output / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")
    print(json.dumps(metadata, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
