"""S&P 500 internal breadth, computed from constituents (not scraped).

- Constituents: Wikipedia table (current members — survivorship caveat:
  fine for the live signal, biased for backtests; see LIMITATIONS.md).
- Closes: yfinance in batches. The raw close matrix is a local cache
  (data/breadth/_closes_cache.parquet, gitignored — in CI restored via
  actions/cache; on miss it is re-downloaded, ~2 min). Only the small
  computed aggregate series is committed to the repo.
- Outputs (data/breadth/breadth.parquet):
    pct_above_50, pct_above_200  — % of members above 50/200DMA
    nh, nl                       — counts of 252d new highs / lows
    adv, dec, ad_line            — daily up/down counts + cumulative A-D line
    n_members                    — denominator that day
"""
from __future__ import annotations

import io
import logging
import re
import time

import pandas as pd
import yfinance as yf

from collectors.base import Adapter
from lib import config

log = logging.getLogger(__name__)

# A real US listing symbol: a letter, then up to 5 more letters/digits/dashes
# (class shares like BRK-B after the .->- swap). Anything else in the Symbol
# column is vandalism / footnote junk and must not enter the universe.
_TICKER_RE = re.compile(r"^[A-Z][A-Z0-9-]{0,5}$")

# --- split-seam detection (2026-07-10 incident) -----------------------------
# yfinance auto_adjust back-adjusts ONLY the window it downloads, so the tail
# refresh (fresh 1mo window merged over the cached matrix) leaves every cached
# row BEFORE that window on the old price basis after a stock split. The merged
# series then carries a permanent fake step where the refresh window stopped
# rewriting: KLAC's 10:1 split (2026-06-12) left $1,842.80 -> $180.90 across
# 2026-05-11/12 (a fake -90.2% "day"); CRWD's 4:1 left a fake -75% day at
# 2026-06-02. A poisoned column biases pct_above_50/200, 252d NH/NL, adv/dec
# and everything reading the closes/OHLCV caches (trailing vol, beta) until the
# lookback rolls past the seam (~10 months for the 200DMA).
# lib.store.upsert(overwrite_overlap=True) solves this class for STORED series
# but only inside the fresh window — the cache's pre-window history needs the
# per-ticker repair in BreadthAdapter._merge_refreshed.
_BASIS_TOL = 0.05    # cached-vs-fresh overlap disagreeing beyond this = stale basis.
                     # Dividend re-adjustments shift the basis by the yield fraction
                     # (< ~2% a quarter, must NOT trigger); splits shift it 2x-25x.
_SEAM_LO, _SEAM_HI = 0.60, 1.65   # 1-day ratio bounds for the residual-seam scan:
                     # catches every >=2:1 split seam in either direction. Genuine
                     # ±40% news days (CNC -40% 2025-07, SATS +70% 2025-08) DO trip
                     # it — for those the repair re-pull returns identical data, so
                     # a false positive costs one batched download, never data.


def seam_suspects(fresh: pd.DataFrame | None, cached: pd.DataFrame | None,
                  merged: pd.DataFrame) -> list[str]:
    """Tickers whose close history mixes price-adjustment bases (split seams).

    Two independent detectors, union of both:
    (a) basis break at the refresh boundary — cached vs fresh disagree by a
        roughly constant factor over their overlap (a split since the last
        refresh re-based the fresh window but not the cache);
    (b) residual seams from PAST refreshes — a 1-day ratio in the merged
        matrix outside [_SEAM_LO, _SEAM_HI] (scanned on a ffilled frame so a
        seam across a data gap is still visible).
    Pass fresh=None/cached=None to run only (b) on an existing cache."""
    bad: set[str] = set()
    if fresh is not None and cached is not None:
        overlap = fresh.index.intersection(cached.index)
        if len(overlap) >= 3:
            common = fresh.columns.intersection(cached.columns)
            f = fresh.loc[overlap, common]
            ratio = (cached.loc[overlap, common] / f.where(f > 0)).median().dropna()
            bad |= set(ratio.index[(ratio - 1).abs() > _BASIS_TOL])
    filled = merged.ffill()
    r = filled / filled.shift(1)
    sus = ((r < _SEAM_LO) | (r > _SEAM_HI)).any()
    bad |= set(sus.index[sus])
    return sorted(bad)


_SEAM_SCAN_DAYS = 550   # residual-seam scan window for PERPETUAL caches (repair_seams):
                        # a new seam can only form at a refresh boundary, i.e. within days
                        # of the split, so ~18 months catches every operational seam with
                        # margin — while keeping genuine deep-history crash days (1987/
                        # 1997/2008 in the 40y hk_search matrix, one-off -50% earnings
                        # days in the 5y+ search caches) from triggering a re-pull every
                        # night forever. Legacy seams beyond the window are healed one-
                        # shot by scripts/heal_breadth_split_seams.py (full-file scan).


def repair_seams(merged: pd.DataFrame, fresh: pd.DataFrame | None,
                 cached: pd.DataFrame | None, downloader, period: str | None = None,
                 *, name: str = "closes",
                 scan_days: int | None = _SEAM_SCAN_DAYS) -> tuple[pd.DataFrame, list[str]]:
    """Split-seam repair for a merged wide-closes matrix; returns (merged, healed).

    The reusable core of BreadthAdapter._merge_refreshed for the collectors that
    merge an auto-adjusted fresh window over a cached matrix OUTSIDE the breadth
    cache (canada/intl/china search closes.parquet, hk_search closes_deep):
    every ticker flagged by seam_suspects gets its full window re-downloaded in
    one batched ``downloader(tickers, period)`` call and its column replaced
    WHOLESALE in ``merged`` (mutated in place and returned). period=None derives
    the re-pull window from the merged span ("max" beyond 10y, else "<span>y"
    like the one-shot healer). Correct whether the flag was a real seam or a
    genuine ±40% news day (the re-pull returns identical data). Never fatal: on
    a failed re-pull the poisoned columns are LEFT IN PLACE (loud warning) so
    the scan re-flags them next run. ``healed`` lists the columns actually
    replaced — empty when nothing was flagged or the re-pull failed."""
    scan = merged
    if scan_days is not None and len(merged.index):
        scan = merged[merged.index >= merged.index.max() - pd.Timedelta(days=scan_days)]
    bad = seam_suspects(fresh, cached, scan)
    if not bad:
        return merged, []
    if period is None:
        span_years = max(1, (merged.index.max() - merged.index.min()).days // 365 + 1)
        period = "max" if span_years > 10 else f"{span_years}y"
    log.warning("%s: %d ticker(s) with mixed adjustment basis in the closes cache "
                "(split seam) — re-pulling %s: %s", name, len(bad), period, bad[:12])
    try:
        repull = downloader(bad, period)
    except Exception as e:  # noqa: BLE001 — repair must never kill the run
        log.warning("%s: seam re-pull failed (%s) — cache kept as-is; the seam "
                    "scan retries next run", name, e)
        return merged, []
    if repull is None:
        repull = pd.DataFrame()
    healed = [t for t in bad if t in repull.columns and repull[t].notna().any()]
    for t in healed:
        merged[t] = repull[t].reindex(merged.index)
    if missed := sorted(set(bad) - set(healed)):
        log.warning("%s: seam re-pull returned no data for %s — kept as-is, "
                    "retried next run", name, missed[:12])
    return merged, healed


def compute_updown(closes: pd.DataFrame, volume: pd.DataFrame) -> pd.DataFrame:
    """Market-wide up/down volume and up/down points aggregates.

    Accruing store for the Lowry/Desmond 90%-day family (masterplan W2).
    Deep history is impossible: the volume cache is a ~35-row tail accrued nightly
    from the breadth OHLCV extras. The store grows forward from first collection;
    no backfill claim is made (label honesty). All history is this-panel-derived,
    never sourced from third-party Desmond/Lowry event rosters (universe differs).

    Columns returned (all float64, date-indexed):
      up_vol      — total share volume on members with a positive close-to-close change
      down_vol    — total share volume on members with a negative close-to-close change
      up_pts      — sum of positive close-to-close price changes (Desmond points; NOT volume-weighted)
      down_pts    — sum of |negative| close-to-close price changes
      n_reporting — member count with both a price change and non-NaN volume

    Rows where n_reporting < 300 are dropped (S&P panel with <300 reporting = data gap).

    Args:
        closes:  Wide date×ticker close-price matrix (any adjustment basis; only diff used).
        volume:  Wide date×ticker share-volume matrix; must share the closes index/columns layout.

    Returns:
        DataFrame indexed by date; empty if inputs are empty or produce no qualifying rows.
        Never raises; caller should wrap in try/except for extra safety.
    """
    if closes is None or closes.empty or volume is None or volume.empty:
        return pd.DataFrame(columns=["up_vol", "down_vol", "up_pts", "down_pts", "n_reporting"])

    dpx = closes.diff()  # price change vs prior close
    vol = volume.reindex(columns=closes.columns)  # align columns

    up_mask = dpx > 0
    dn_mask = dpx < 0
    both_present = dpx.notna() & vol.notna()

    up_vol = (vol.where(up_mask & both_present)).sum(axis=1, min_count=1)
    down_vol = (vol.where(dn_mask & both_present)).sum(axis=1, min_count=1)
    up_pts = (dpx.where(up_mask & both_present)).sum(axis=1, min_count=1)
    down_pts = ((-dpx).where(dn_mask & both_present)).sum(axis=1, min_count=1)
    n_reporting = both_present.sum(axis=1)

    out = pd.DataFrame({
        "up_vol": up_vol,
        "down_vol": down_vol,
        "up_pts": up_pts,
        "down_pts": down_pts,
        "n_reporting": n_reporting.astype(float),
    })
    out = out[out["n_reporting"] >= 300]
    return out.dropna(how="all", subset=["up_vol", "down_vol"])


class BreadthAdapter(Adapter):
    name = "breadth"
    group = "breadth"

    def __init__(self) -> None:
        self.cfg = config.load()["breadth"]
        self.ycfg = config.load()["yahoo"]
        self.cache_path = config.data_dir() / "breadth" / "_closes_cache.parquet"

    def constituents(self) -> pd.DataFrame:
        r = self.http_get(self.cfg["constituents_url"], retries=3,
                          headers={"User-Agent": "Mozilla/5.0 (macro-dashboard research)"})
        tables = pd.read_html(io.StringIO(r.text))
        for t in tables:
            if "Symbol" in t.columns:
                t = t.rename(columns={"Symbol": "symbol", "Security": "name",
                                      "GICS Sector": "sector"})
                return self._repair(t[["symbol", "name", "sector"]])
        raise ValueError("constituents table not found on Wikipedia page")

    def _repair(self, members: pd.DataFrame) -> pd.DataFrame:
        """Clean a freshly-scraped constituents table before it becomes the universe.

        Wikipedia is community-edited and intermittently ships a *plausible-looking*
        but wrong symbol — vandalism (Marsh & McLennan shown as the non-existent
        "MRSH") or a stale pre-rename ticker (Fiserv as "FISV", renamed "FI" in
        2023) — plus the occasional non-ticker junk cell. Left unrepaired those
        silently drop the real name from the searchable universe and can mint a
        bogus page for the garbage symbol. This normalises symbols, drops
        non-ticker junk, and applies the config ``ticker_fixups`` repair map
        (bad -> real current ticker). Pure + logged; never raises."""
        df = members.copy()
        df["symbol"] = (df["symbol"].astype(str).str.strip().str.upper()
                        .str.replace(".", "-", regex=False))         # BRK.B -> BRK-B
        # drop non-ticker junk (vandalism, footnote artefacts) before it poisons ratios
        ok = df["symbol"].str.match(_TICKER_RE)
        if not ok.all():
            log.warning("%s constituents: dropping %d non-ticker row(s): %s",
                        self.name, int((~ok).sum()), df.loc[~ok, "symbol"].tolist()[:10])
            df = df[ok]
        # repair known-bad symbols (vandalism / stale renames) -> the real ticker
        fixups = {str(k).strip().upper(): str(v).strip().upper()
                  for k, v in (self.cfg.get("ticker_fixups") or {}).items()}
        if fixups:
            hit = df["symbol"].isin(fixups)
            if hit.any():
                log.info("%s constituents: repaired %d Wikipedia ticker(s): %s",
                         self.name, int(hit.sum()),
                         {s: fixups[s] for s in sorted(df.loc[hit, "symbol"].unique())})
                df["symbol"] = df["symbol"].map(lambda s: fixups.get(s, s))
        # a repair can collide with an already-correct row -> keep one
        df = df.drop_duplicates(subset="symbol", keep="first").reset_index(drop=True)
        return df[["symbol", "name", "sector"]]

    def _download_closes(self, tickers: list[str], period: str) -> pd.DataFrame:
        bs = self.ycfg["batch_size"]
        parts: list[pd.DataFrame] = []
        # ADDITIVE OHLCV capture: yfinance already downloads high/low/volume — keep them
        # (instead of discarding all but Close) so the stock library can compute
        # volume-based signals (engine/bottom_radar) for the full universe, not just the
        # ~114 deep names. Stashed on self for fetch() to cache; never affects closes.
        extras: dict[str, list] = {"high": [], "low": [], "volume": []}
        for i in range(0, len(tickers), bs):
            batch = tickers[i:i + bs]
            for attempt in range(self.ycfg["retries"]):
                try:
                    df = yf.download(batch, period=period, auto_adjust=True,
                                     progress=False, group_by="column", threads=True)
                    lvl0 = (df.columns.get_level_values(0)
                            if isinstance(df.columns, pd.MultiIndex) else df.columns)
                    parts.append(df["Close"] if "Close" in lvl0 else df)
                    for k, F in (("high", "High"), ("low", "Low"), ("volume", "Volume")):
                        if F in lvl0:
                            extras[k].append(df[F])
                    break
                except Exception as e:  # noqa: BLE001
                    wait = self.ycfg["backoff_base_s"] * (2 ** attempt)
                    log.warning("breadth batch %d failed (%s); retry in %.0fs", i // bs, e, wait)
                    time.sleep(wait)
            time.sleep(1)
        if not parts:
            raise RuntimeError("no constituent closes downloaded")

        def _wide(plist: list) -> pd.DataFrame:
            w = pd.concat(plist, axis=1)
            return w.loc[:, ~w.columns.duplicated()].sort_index()

        self._last_extras = {k: _wide(v) for k, v in extras.items() if v}
        return _wide(parts)

    def _merge_refreshed(self, fresh: pd.DataFrame, cached: pd.DataFrame) -> pd.DataFrame:
        """``fresh.combine_first(cached)`` + split-seam repair (see module comment).

        Flagged tickers get their FULL live window re-downloaded (one batched
        call) and the column replaced wholesale — correct whether the flag was
        a real seam (stale basis replaced by a coherent adjusted history) or a
        genuine ±40% news day (the re-pull returns identical data). The
        re-pulled tickers' OHLCV extras are grafted over the fresh-window
        extras so the _high/_low/_volume caches heal on the same run. If the
        re-pull fails the poisoned columns are LEFT IN PLACE (loud warning):
        the scan re-flags them next run, whereas truncating them would erase
        the evidence and silently orphan the seam in the extras caches."""
        merged = fresh.combine_first(cached)
        bad = seam_suspects(fresh, cached, merged)
        if not bad:
            return merged
        days = self.cfg["lookback_days_live"]
        log.warning("%s: %d ticker(s) with mixed adjustment basis in the closes cache "
                    "(split seam) — re-pulling full window: %s",
                    self.name, len(bad), bad[:12])
        fresh_extras = getattr(self, "_last_extras", {}) or {}
        try:
            repull = self._download_closes(bad, f"{max(1, days // 365 + 1)}y")
        except Exception as e:  # noqa: BLE001 — repair must never kill the run
            log.warning("%s: seam re-pull failed (%s) — cache kept as-is; the seam "
                        "scan retries next run", self.name, e)
            self._last_extras = fresh_extras
            return merged
        repull_extras = getattr(self, "_last_extras", {}) or {}
        self._last_extras = fresh_extras
        healed = [t for t in bad if t in repull.columns and repull[t].notna().any()]
        for t in healed:
            merged[t] = repull[t].reindex(merged.index)
        if missed := sorted(set(bad) - set(healed)):
            log.warning("%s: seam re-pull returned no data for %s — kept as-is, "
                        "retried next run", self.name, missed[:12])
        for k, w in list(fresh_extras.items()):
            rw = repull_extras.get(k)
            cols = [t for t in healed if rw is not None and t in rw.columns and t in w.columns]
            if not cols:
                continue
            # union index: the grafted column must span the extras CACHE's rows,
            # not just the 1mo fresh window, so combine_first in fetch() overrides
            # the poisoned cached rows instead of keeping them
            w = w.reindex(w.index.union(rw.index)).sort_index()
            for t in cols:
                w[t] = rw[t].reindex(w.index)
            fresh_extras[k] = w
        return merged

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        members = self.constituents_checked(self.constituents())
        tickers = members["symbol"].tolist()

        if full_history:
            closes = self._download_closes(tickers, "max")
        else:
            closes = None
            if self.cache_path.exists():
                cached = pd.read_parquet(self.cache_path)
                # refresh tail; full re-pull if cache is stale beyond the overlap
                age = (pd.Timestamp.utcnow().tz_localize(None) - cached.index.max()).days
                if age <= 14:
                    fresh = self._download_closes(tickers, "1mo")
                    closes = self._merge_refreshed(fresh, cached)
            if closes is None:
                days = self.cfg["lookback_days_live"]
                closes = self._download_closes(tickers, f"{max(1, days // 365 + 1)}y")
            cutoff = closes.index.max() - pd.Timedelta(days=self.cfg["lookback_days_live"] + 30)
            closes = closes[closes.index >= cutoff]

        # coverage sanity: a half-empty matrix silently poisons every ratio
        live_cols = closes.dropna(axis=1, how="all").shape[1]
        if live_cols < len(tickers) * 0.8:
            raise RuntimeError(f"breadth closes too sparse: {live_cols}/{len(tickers)}")

        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        if not full_history:
            closes.to_parquet(self.cache_path)
            # ADDITIVE: persist the OHLCV extras the download already captured, with the
            # SAME tail-refresh + window logic as closes. Never fatal — breadth itself
            # only needs closes; the stock library falls back to close-only when absent.
            try:
                cutoff_e = closes.index.max() - pd.Timedelta(days=self.cfg["lookback_days_live"] + 30)
                for k, w in (getattr(self, "_last_extras", {}) or {}).items():
                    ep = self.cache_path.parent / f"_{k}_cache.parquet"
                    if ep.exists():
                        w = w.combine_first(pd.read_parquet(ep))
                    w[w.index >= cutoff_e].to_parquet(ep)
            except Exception as e:  # noqa: BLE001
                log.warning("breadth OHLCV extras cache failed (%s) — volume signals close-only", e)
        # constituents list is reference data, not a time series — written directly.
        # Log membership churn vs the prior committed list so a vandalised / partial
        # scrape that silently drops real members is visible in the run output.
        cpath = self.cache_path.parent / "constituents.parquet"
        try:
            if cpath.exists():
                prior = set(pd.read_parquet(cpath).index)
                new = set(members["symbol"])
                added, dropped = new - prior, prior - new
                if added or dropped:
                    log.info("%s constituents churn: +%d -%d (added %s; dropped %s)",
                             self.name, len(added), len(dropped),
                             sorted(added)[:8], sorted(dropped)[:8])
        except Exception as e:  # noqa: BLE001 — observability only, never fatal
            log.warning("%s constituents churn log failed (%s)", self.name, e)
        members.set_index("symbol").to_parquet(cpath)

        out = {"breadth": self.compute(closes)}
        # per-GICS-sector breadth (rotation-tensor breadth-migration gap,
        # 2026-07-02 incident handoff H5): same closes matrix, split by the
        # sector labels already on the constituents table. Never fatal —
        # market-wide breadth must ship even if the sector split fails.
        try:
            sb = self.compute_sectors(closes, members)
            if sb is not None and not sb.empty:
                out["sector_breadth"] = sb
        except Exception as e:  # noqa: BLE001 — additive, never fatal
            log.warning("breadth sector split failed (%s) — market-wide only", e)
        # W2: up/down volume + points aggregate — accruing nightly into updown.parquet.
        # Volume comes from the OHLCV extras cache written earlier in this run; the cache
        # is gitignored and runner-local so it is absent in fresh worktrees — fail-soft.
        try:
            vcache = self.cache_path.parent / "_volume_cache.parquet"
            if vcache.exists():
                vol_df = pd.read_parquet(vcache).reindex(index=closes.index,
                                                          columns=closes.columns)
                new_updown = compute_updown(closes, vol_df)
                if not new_updown.empty:
                    udpath = self.cache_path.parent / "updown.parquet"
                    if udpath.exists():
                        old_updown = pd.read_parquet(udpath)
                        # combine_first by date: new rows win, old history preserved (no-regress)
                        merged_ud = new_updown.combine_first(old_updown)
                        merged_ud = merged_ud.sort_index()
                    else:
                        merged_ud = new_updown.sort_index()
                    merged_ud.to_parquet(udpath)
                    log.info("breadth updown: %d total rows (W2 accrual)", len(merged_ud))
            else:
                log.info("breadth updown: volume cache absent — updown.parquet not updated "
                         "(accrues once _volume_cache is populated by a full breadth run)")
        except Exception as e:  # noqa: BLE001 — updown must never break the breadth build
            log.warning("breadth updown accrual failed (%s) — breadth.parquet unaffected", e)
        return out

    def compute_sectors(self, closes: pd.DataFrame,
                        members: pd.DataFrame) -> pd.DataFrame | None:
        """pct_above_50 / pct_above_200 / n_members per GICS sector, wide frame
        with flat '<sector>|<metric>' columns (parquet-friendly). Same MA windows
        and partial-row discipline as the market-wide compute()."""
        if "sector" not in members.columns:
            return None
        w50, w200 = self.cfg["ma_windows"]
        sec_map = members.set_index("symbol")["sector"].dropna()
        ma50 = closes.rolling(w50, min_periods=w50).mean()
        ma200 = closes.rolling(w200, min_periods=w200).mean()
        cols = {}
        for sector, syms in sec_map.groupby(sec_map).groups.items():
            tick = [t for t in syms if t in closes.columns]
            if len(tick) < 5:  # a sector this thin would print noise
                continue
            c, m50, m200 = closes[tick], ma50[tick], ma200[tick]
            n50 = m50.notna().sum(axis=1)
            n200 = m200.notna().sum(axis=1)
            cols[f"{sector}|pct_above_50"] = (
                100 * (c > m50).sum(axis=1) / n50.where(n50 > 0)).astype(float)
            cols[f"{sector}|pct_above_200"] = (
                100 * (c > m200).sum(axis=1) / n200.where(n200 > 0)).astype(float)
            cols[f"{sector}|n"] = c.notna().sum(axis=1).astype(float)
        if not cols:
            return None
        out = pd.DataFrame(cols).dropna(how="all")
        p50 = [c for c in out.columns if c.endswith("|pct_above_50")]
        return out.dropna(subset=p50, how="all")

    def compute(self, closes: pd.DataFrame) -> pd.DataFrame:
        w50, w200 = self.cfg["ma_windows"]
        nhw = self.cfg["nhnl_window"]
        valid = closes.notna()
        ma50 = closes.rolling(w50, min_periods=w50).mean()
        ma200 = closes.rolling(w200, min_periods=w200).mean()
        out = pd.DataFrame(index=closes.index)
        out["n_members"] = valid.sum(axis=1)
        out["pct_above_50"] = 100 * (closes > ma50).sum(axis=1) / ma50.notna().sum(axis=1)
        out["pct_above_200"] = 100 * (closes > ma200).sum(axis=1) / ma200.notna().sum(axis=1)
        roll_hi = closes.rolling(nhw, min_periods=nhw).max()
        roll_lo = closes.rolling(nhw, min_periods=nhw).min()
        out["nh"] = (closes >= roll_hi).sum(axis=1)
        out["nl"] = (closes <= roll_lo).sum(axis=1)
        chg = closes.diff()
        out["adv"] = (chg > 0).sum(axis=1)
        out["dec"] = (chg < 0).sum(axis=1)
        out["ad_line"] = (out["adv"] - out["dec"]).cumsum()
        out = out.dropna(subset=["pct_above_50"])
        # partial rows (e.g. an in-progress trading day where only a handful of
        # tickers have printed) would poison every ratio — drop them
        return out[out["n_members"] >= out["n_members"].rolling(20, min_periods=1).max() * 0.8]

    def constituents_checked(self, members: pd.DataFrame) -> pd.DataFrame:
        if members.empty or len(members) < 400:
            raise ValueError(f"constituents list suspicious: {len(members)} rows")
        return members


def breadth_summary(br: pd.DataFrame | None, full: bool) -> dict | None:
    """Latest-row breadth read for the regional dashboard cards (China / HK / Canada).

    Pure function of a computed breadth frame (the 8-column output of
    ``BreadthAdapter.compute``). Returns the fields the cards already used plus a
    plain-language participation read — ``state`` (broad / thin / mixed), ``tone``,
    and ``net_nh`` — mirroring the US S&P-1500 scorecard's thresholds so the regional
    pages answer the same "how many stocks are actually participating" question.
    DISPLAY-ONLY (never scored). ``full`` flags whether the source was the full
    searchable universe (True) or the curated large-cap gauge (False)."""
    if br is None or br.empty:
        return None
    last = br.iloc[-1]
    pa50 = float(last.get("pct_above_50", float("nan")))
    nh, nl = int(last.get("nh", 0) or 0), int(last.get("nl", 0) or 0)
    net_nh = nh - nl
    # same thresholds as build_site._breadth_read (the US scorecard) — % above the
    # 50-day line is normalized 0-100 so the bands port across markets unchanged
    if pa50 >= 60 and net_nh >= 0:
        state, tone = "broad", "pos"
    elif pa50 <= 40 or net_nh < 0:
        state, tone = "thin", "neg"
    else:
        state, tone = "mixed", "muted"
    try:
        chg20 = round(float(br["pct_above_50"].diff(20).iloc[-1]), 1)
    except Exception:  # noqa: BLE001 — short history → no 20d change
        chg20 = 0.0
    return {
        "pct_above_50": round(pa50, 1),
        "pct_above_200": round(float(last.get("pct_above_200", float("nan"))), 1),
        "nh": nh, "nl": nl, "net_nh": net_nh,
        "adv": int(last.get("adv", 0) or 0), "dec": int(last.get("dec", 0) or 0),
        "ad_trend": "up" if br["ad_line"].diff(20).iloc[-1] > 0 else "down",
        "n_members": int(last.get("n_members", 0) or 0),
        "pct50_chg20": chg20,
        "state": state, "tone": tone, "full": bool(full),
        "asof": pd.Timestamp(last.name).strftime("%Y-%m-%d"),
    }
