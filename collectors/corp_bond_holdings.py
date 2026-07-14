"""Corporate bond holdings collector — CCW W1 (data spine).

Fetches daily SSGA bond-fund holdings XLSX files for 5 funds:
  SPSB (IG 1-3y), SPIB (IG 1-10y), SPLB (IG long), JNK (HY broad), SPHY (HY broad)

Writes PIT parquet snapshots:
  data/corp_bonds/holdings/<FUND>/<YYYY-MM-DD>.parquet

Schema: [isin, cusip6, name, coupon, par_value, market_value, weight_pct, maturity,
          currency, fund, as_of]

After writing snapshots, computes a match-rate stat against the issuer registry at
data/corp_bonds/issuer_themes.json and logs:
  - matched par % (across IG+HY funds)
  - top 10 unmatched issuers by par
  - CCW-UNMATCHED-HIGH-PAR warning when any single unmatched name-group exceeds $5B par

Reuses SSGA_XLSX URL constant + browser-UA idiom from collectors/etf_holdings.py.
The bond parser is a NEW ISIN-keyed implementation — the equity _normalize path is
NOT used (it requires a ticker column and filters non-equity rows, dropping everything).
"""
from __future__ import annotations

import io
import json
import logging
import re as _re
import time
from datetime import date
from pathlib import Path

import pandas as pd

from collectors.base import Adapter
from collectors.etf_holdings import SSGA_XLSX, _BROWSER_UA
from lib import config

log = logging.getLogger(__name__)

# CCW W1: 5 SSGA bond funds (IG short/blend/long + two HY broad)
# Masterplan §2.1: SPSB/SPLB were pattern-inferred; live-verified in this build
# (both returned HTTP 200 with expected bond-column schema 2026-07-14).
FUNDS = ["SPSB", "SPIB", "SPLB", "JNK", "SPHY"]

# Output schema column order
OUT_COLS = ["isin", "cusip6", "name", "coupon", "par_value", "market_value",
            "weight_pct", "maturity", "currency", "fund", "as_of"]

# Unmatched-high-par alarm threshold (masterplan §3-P1)
UNMATCHED_HIGH_PAR_THRESHOLD = 5_000_000_000  # $5B


class CorpBondHoldingsAdapter(Adapter):
    """CCW W1 bond holdings PIT store. Group 'corp_bonds'."""

    name = "corp_bond_holdings"
    group = "corp_bonds"

    def __init__(self) -> None:
        self.dir = config.data_dir() / "corp_bonds" / "holdings"
        self.retries = 3

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        """Fetch all 5 fund snapshots; write PIT parquets; log match-rate stat."""
        ok, errors = 0, []
        all_snaps: list[pd.DataFrame] = []

        for fund in FUNDS:
            try:
                snap = self._fetch_fund(fund)
                if snap is not None and not snap.empty:
                    self._write_snapshot(fund, snap)
                    all_snaps.append(snap)
                    ok += 1
                time.sleep(0.4)
            except Exception as e:  # noqa: BLE001 — one fund must not kill the rest
                errors.append(f"{fund}: {e}")
                log.warning("corp_bond_holdings %s failed: %s", fund, e)

        if not ok:
            raise RuntimeError(f"corp_bond_holdings: all funds failed: {errors}")
        if errors:
            log.warning("corp_bond_holdings partial (%d ok): %s", ok, errors[:8])

        # Match-rate stat (non-fatal; run even on partial success)
        if all_snaps:
            try:
                self._log_match_rate(pd.concat(all_snaps, ignore_index=True))
            except Exception as e:  # noqa: BLE001 — additive stat, never fatal
                log.warning("corp_bond_holdings match-rate stat failed: %s", e)

        summary = pd.DataFrame(
            {"funds_ok": [ok]}, index=[pd.Timestamp(date.today())]
        )
        return {"corp_bond_holdings_runs": summary}

    # ------------------------------------------------------------------
    # Fetch + parse
    # ------------------------------------------------------------------

    def _fetch_fund(self, fund: str) -> pd.DataFrame:
        url = SSGA_XLSX.format(fund=fund.lower())
        r = self.http_get(
            url,
            retries=self.retries,
            timeout=90,
            headers={"User-Agent": _BROWSER_UA, "Accept": "*/*",
                     "Accept-Language": "en-US,en;q=0.9"},
        )
        raw = pd.read_excel(io.BytesIO(r.content), header=None)
        return _parse_bond_xlsx(raw, fund)

    # ------------------------------------------------------------------
    # Write PIT snapshot (keep-FIRST: never overwrite an existing dated file)
    # ------------------------------------------------------------------

    def _write_snapshot(self, fund: str, snap: pd.DataFrame) -> None:
        asof = str(snap["as_of"].iloc[0])
        d = self.dir / fund
        d.mkdir(parents=True, exist_ok=True)
        target = d / f"{asof}.parquet"
        if target.exists():
            log.info(
                "corp_bond_holdings: %s as_of %s already on disk — keep-FIRST, "
                "skipping overwrite",
                fund, asof,
            )
            return
        snap.to_parquet(target)
        log.info("corp_bond_holdings: wrote %s → %s (%d bonds)", fund, target.name, len(snap))

    # ------------------------------------------------------------------
    # Match-rate stat (masterplan §3-P1 alarm hook)
    # ------------------------------------------------------------------

    def _log_match_rate(self, all_bonds: pd.DataFrame) -> None:
        registry_path = config.data_dir() / "corp_bonds" / "issuer_themes.json"
        if not registry_path.exists():
            log.warning("corp_bond_holdings: issuer_themes.json not found — skipping match-rate")
            return

        with registry_path.open() as f:
            registry = json.load(f)

        # Build flat list of (equity_ticker, name_patterns, id_prefixes)
        matchers: list[tuple[str, list[str], list[str]]] = []
        for _theme_key, theme in registry.get("themes", {}).items():
            for issuer_key, issuer in theme.get("issuers", {}).items():
                patterns = [p.upper() for p in issuer.get("name_match_patterns", [])]
                prefixes = [p.upper() for p in issuer.get("id_prefixes", [])]
                matchers.append((issuer_key, patterns, prefixes))

        # Numeric par_value
        par_vals = pd.to_numeric(all_bonds["par_value"], errors="coerce").fillna(0.0)
        total_par = par_vals.sum()

        # Convert to plain Python strings (fillna first so str accessor doesn't
        # leave NaN pass-throughs that become float on .iat[])
        name_upper = all_bonds["name"].fillna("").astype(str).str.upper().tolist()
        cusip6_upper = all_bonds["cusip6"].fillna("").astype(str).str.upper().tolist()
        isin_upper = all_bonds["isin"].fillna("").astype(str).str.upper().tolist()

        def _matches_row(idx: int) -> bool:
            nm = name_upper[idx]
            cu6 = cusip6_upper[idx]
            isn = isin_upper[idx]
            for _key, patterns, prefixes in matchers:
                for p in patterns:
                    if p and p in nm:
                        return True
                for pfx in prefixes:
                    if pfx and (cu6.startswith(pfx) or isn.startswith(pfx)):
                        return True
            return False

        matched_mask = [_matches_row(i) for i in range(len(all_bonds))]
        matched_par = par_vals[matched_mask].sum()
        match_pct = (matched_par / total_par * 100) if total_par > 0 else 0.0

        log.info(
            "corp_bond_holdings match-rate: %.1f%% of total par matched to issuer registry "
            "(matched=$%.2fB total=$%.2fB)",
            match_pct, matched_par / 1e9, total_par / 1e9,
        )

        # Top 10 unmatched issuers by par
        unmatched_mask = [not m for m in matched_mask]
        unmatched = all_bonds[unmatched_mask].copy()
        unmatched["_par"] = par_vals[unmatched_mask].values

        # Cluster by name prefix (first 3 words of name)
        def _name_group(nm: str) -> str:
            words = str(nm).upper().split()
            return " ".join(words[:3])

        unmatched["_grp"] = unmatched["name"].map(_name_group)
        grp_par = (
            unmatched.groupby("_grp")["_par"].sum()
            .sort_values(ascending=False)
            .head(10)
        )

        top_unmatched_lines = [f"  {grp}: ${par/1e6:.0f}M" for grp, par in grp_par.items()]
        if top_unmatched_lines:
            log.info("corp_bond_holdings top-10 unmatched issuers (by par):\n%s",
                     "\n".join(top_unmatched_lines))

        # High-par alarm
        for grp, par in grp_par.items():
            if par > UNMATCHED_HIGH_PAR_THRESHOLD:
                log.warning(
                    "CCW-UNMATCHED-HIGH-PAR: unmatched issuer group '%s' has $%.2fB par "
                    "— candidate missing registry entry or finance-subsidiary pattern; "
                    "amend data/corp_bonds/issuer_themes.json",
                    grp, par / 1e9,
                )


# ------------------------------------------------------------------
# ISIN-keyed bond XLSX parser (standalone; NOT the equity _normalize path)
# ------------------------------------------------------------------

def _parse_bond_xlsx(raw: pd.DataFrame, fund: str) -> pd.DataFrame:
    """Parse a SSGA bond XLSX file (header = row where first col == 'Name').

    Bond column layout (masterplan §2.1):
      Name | Identifier (ISIN) | SEDOL | Weight | Coupon | Par Value |
      Market Value | Local Currency | Maturity

    Returns a DataFrame with schema OUT_COLS.  Rows with unparseable par/mv
    are kept with NaN and counted in a log line.
    """
    # Locate header row
    hdr_idx: int | None = None
    for j in range(min(20, len(raw))):
        cell = str(raw.iloc[j, 0]).strip()
        if cell == "Name":
            hdr_idx = j
            break
    if hdr_idx is None:
        raise ValueError(f"{fund}: bond holdings header row ('Name') not found; "
                         f"first 5 col-0 values: "
                         f"{[str(raw.iloc[j, 0]).strip() for j in range(min(5, len(raw)))]}")

    # Extract as_of date from preamble rows (cells above the header)
    asof = _extract_asof(raw, hdr_idx, fund)

    # Build column-named data section
    col_names = [str(raw.iloc[hdr_idx, c]).strip() for c in range(raw.shape[1])]
    data = raw.iloc[hdr_idx + 1:].copy()
    data.columns = col_names

    # Drop footer / empty rows: keep rows where 'Name' cell is non-empty non-NaN text
    name_col = "Name"
    valid = (
        data[name_col].notna()
        & (data[name_col].astype(str).str.strip() != "")
        & (data[name_col].astype(str).str.strip().str.lower() != "nan")
    )
    data = data[valid].copy().reset_index(drop=True)

    if data.empty:
        raise ValueError(f"{fund}: no data rows after header detection")

    # --- Column mapping (bond-specific; no ticker column) ---
    isin_col = _find_col(data, ["identifier"])
    weight_col = _find_col(data, ["weight"])
    coupon_col = _find_col(data, ["coupon"])
    par_col = _find_col(data, ["par value", "par_value"])
    mv_col = _find_col(data, ["market value", "market_value"])
    ccy_col = _find_col(data, ["local currency", "currency"])
    mat_col = _find_col(data, ["maturity"])

    # Secondary footer filter: SSGA disclaimer rows pass the Name check (they have
    # boilerplate text up to 9,416 chars) but have neither a valid 12-char ISIN nor
    # a par value.  Keep a row if (ISIN is exactly 12 alphanumeric chars) OR (par
    # value cell is non-null/non-empty).  This drops the 7 disclaimer rows per fund
    # while retaining all genuine bond rows — including those with null par (e.g.
    # TBA/placeholder positions that carry a valid ISIN).
    def _is_valid_isin(val) -> bool:
        s = str(val).strip()
        return len(s) == 12 and s.isalnum()

    def _has_par(val) -> bool:
        s = str(val).strip()
        return s not in ("", "nan", "NaN", "None", "-", "N/A")

    isin_raw = data[isin_col].fillna("") if isin_col else pd.Series([""] * len(data))
    par_raw = data[par_col].fillna("") if par_col else pd.Series([""] * len(data))
    keep = isin_raw.map(_is_valid_isin) | par_raw.map(_has_par)
    n_dropped = int((~keep).sum())
    if n_dropped:
        log.info(
            "corp_bond_holdings %s: secondary footer filter dropped %d disclaimer row(s) "
            "(non-empty name but no valid ISIN and no par value)",
            fund, n_dropped,
        )
    data = data[keep].copy().reset_index(drop=True)

    if data.empty:
        raise ValueError(f"{fund}: no data rows after secondary footer filter")

    def _num(series: pd.Series) -> pd.Series:
        """Defensively parse numeric: strip commas, dollar signs, dashes → NaN."""
        return pd.to_numeric(
            series.astype(str)
                  .str.replace(r"[,\$%()]", "", regex=True)
                  .str.strip()
                  .replace({"-": None, "": None, "nan": None}),
            errors="coerce",
        )

    # Parse each field
    isins = data[isin_col].astype(str).str.strip() if isin_col else pd.Series([""] * len(data))
    # ISIN validity: must look like an ISIN (12 alphanumeric chars); placeholder codes stay as-is
    names = data[name_col].astype(str).str.strip()
    weights = _num(data[weight_col]) if weight_col else pd.Series([float("nan")] * len(data))
    coupons = _num(data[coupon_col]) if coupon_col else pd.Series([float("nan")] * len(data))
    par_vals = _num(data[par_col]) if par_col else pd.Series([float("nan")] * len(data))
    mv_vals = _num(data[mv_col]) if mv_col else pd.Series([float("nan")] * len(data))
    currencies = data[ccy_col].astype(str).str.strip() if ccy_col else pd.Series([""] * len(data))

    # Maturity: handle MM/DD/YYYY and DD-Mon-YYYY (both observed; live data is MM/DD/YYYY)
    maturities = _parse_maturities(data[mat_col] if mat_col else pd.Series([None] * len(data)))

    # cusip6: US ISINs embed the CUSIP in chars [2:8] (0-based: positions 2..7 of the 12-char ISIN)
    def _cusip6(isin: str) -> str:
        if isinstance(isin, str) and isin.startswith("US") and len(isin) >= 8:
            return isin[2:8]
        return ""

    cusip6s = isins.map(_cusip6)

    # Diagnostic: count NaN par/mv rows
    n_nan_par = int(par_vals.isna().sum())
    n_nan_mv = int(mv_vals.isna().sum())
    if n_nan_par or n_nan_mv:
        log.info(
            "corp_bond_holdings %s: %d rows with NaN par_value, %d with NaN market_value "
            "(kept with NaN per spec)",
            fund, n_nan_par, n_nan_mv,
        )

    out = pd.DataFrame({
        "isin": isins.values,
        "cusip6": cusip6s.values,
        "name": names.values,
        "coupon": coupons.values,
        "par_value": par_vals.values,
        "market_value": mv_vals.values,
        "weight_pct": weights.values,
        "maturity": maturities.values,
        "currency": currencies.values,
        "fund": fund,
        "as_of": asof,
    })

    return out[OUT_COLS].reset_index(drop=True)


def _find_col(df: pd.DataFrame, tokens: list[str]) -> str | None:
    """Return the first column name that contains any of the given tokens (case-insensitive)."""
    for col in df.columns:
        col_lower = col.lower()
        for t in tokens:
            if t in col_lower:
                return col
    return None


def _extract_asof(raw: pd.DataFrame, hdr_idx: int, fund: str) -> str:
    """Scan preamble rows for an as-of date cell.

    SSGA bond files carry:  'Holdings:' | 'As of DD-Mon-YYYY'
    or a cell containing 'As of ...' anywhere in the first 4 columns.
    Fallback: today-1 business day with a WARNING (masterplan §2.1).
    """
    for j in range(hdr_idx):
        for c in range(min(4, raw.shape[1])):
            cell = str(raw.iloc[j, c]).strip()
            if "as of" in cell.lower():
                # Try to parse the date from this cell
                date_str = _re.sub(r"(?i)as of\s*[:：]?\s*", "", cell).strip()
                date_str = _re.sub(r"(?i)holdings\s*[:：]?\s*", "", date_str).strip()
                if date_str:
                    try:
                        return str(pd.to_datetime(date_str).date())
                    except Exception:  # noqa: BLE001 — try next cell
                        pass
                # Try the adjacent cell (col 1 when col 0 says 'Holdings:')
                if c + 1 < raw.shape[1]:
                    neighbor = str(raw.iloc[j, c + 1]).strip()
                    if "as of" in neighbor.lower():
                        inner = _re.sub(r"(?i)as of\s*[:：]?\s*", "", neighbor).strip()
                        try:
                            return str(pd.to_datetime(inner).date())
                        except Exception:  # noqa: BLE001
                            pass

    # Fallback: most-recent prior business day
    today = pd.Timestamp(date.today())
    prior = today - pd.tseries.offsets.BDay(1)
    asof = str(prior.date())
    log.warning(
        "corp_bond_holdings %s: 'As of' cell not found in preamble; "
        "falling back to prior business day %s",
        fund, asof,
    )
    return asof


def _parse_maturities(series: pd.Series) -> pd.Series:
    """Parse maturity dates to ISO format (YYYY-MM-DD).

    Handles:
      MM/DD/YYYY  — observed in all live SSGA bond files (2026-07-14)
      DD-Mon-YYYY — alternative SSGA format (e.g. 15-Mar-2029)
      YYYY-MM-DD  — already ISO
      Unparseable / missing → None (NaT)
    """
    def _parse_one(val) -> str | None:
        s = str(val).strip()
        if not s or s.lower() in ("nan", "none", "nat", "-"):
            return None
        try:
            return str(pd.to_datetime(s, dayfirst=False).date())
        except Exception:  # noqa: BLE001 — try dayfirst=True for DD-Mon-YYYY
            pass
        try:
            return str(pd.to_datetime(s, dayfirst=True).date())
        except Exception:  # noqa: BLE001
            return None

    return series.map(_parse_one)
