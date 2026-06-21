"""FINRA daily short-VOLUME collector — the fresher cousin of the bi-monthly
short-INTEREST feed (collectors/finra.py).

FINRA publishes a keyless flat file of consolidated daily short-sale volume,
one per trading day, posted by ~6pm ET:

    https://cdn.finra.org/equity/regsho/daily/CNMSshvol<YYYYMMDD>.txt
    Date|Symbol|ShortVolume|ShortExemptVolume|TotalVolume|Market

`short_ratio = ShortVolume / TotalVolume` is the fraction of that day's
consolidated tape that printed on a short-sale order. Unlike bi-monthly short
*interest* (outstanding positions, ~2-week lag) this is *daily* — so a rising
short_ratio surfaces building bearish flow days/weeks before it shows up in the
settlement report. It is NOISY and the academic edge is modest/contested, so it
feeds the stock page as a CONTEXT confirmer (engine/short_volume.py), never a
scored alpha factor.

Append-only, deduped on (date, ticker), written to
data/finra_short_volume/panel.parquet. We backfill a rolling window each run
(cheap, self-healing); the merge keeps only genuinely new (date, ticker) rows.
Keyless — degrades to 'failed' only if FINRA's CDN is unreachable.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone

import pandas as pd

from collectors.base import Adapter, is_connection_error
from lib import config

log = logging.getLogger(__name__)

BASE = "https://cdn.finra.org/equity/regsho/daily"
LOOKBACK_DAYS = 30          # calendar days backfilled per run (dedup-merged)
GROUP = "finra_short_volume"


def _panel_path():
    return config.data_dir() / GROUP / "panel.parquet"


def _universe_tickers() -> set[str]:
    """Our covered names, read from the breadth close-caches — keeps the panel
    lean (~1.5k names) vs FINRA's ~8k symbols. Empty set -> keep everything."""
    out: set[str] = set()
    for grp in ("breadth", "smallcap_breadth", "midcap_breadth"):
        p = config.data_dir() / grp / "_closes_cache.parquet"
        if p.exists():
            try:
                out.update(str(c) for c in pd.read_parquet(p).columns)
            except Exception:  # noqa: BLE001 — best-effort filter
                continue
    return out


def _business_days(n_calendar: int) -> list[date]:
    """Recent business days (Mon-Fri), newest-first, over the lookback window."""
    today = datetime.now(timezone.utc).date()
    out: list[date] = []
    for i in range(n_calendar):
        d = today - timedelta(days=i)
        if d.weekday() < 5:
            out.append(d)
    return out


def _parse(text: str) -> pd.DataFrame:
    """Parse one CNMSshvol file into normalized rows. Tolerates the trailing
    footer line FINRA appends (e.g. 'Total Records ...')."""
    rows: list[dict] = []
    for line in text.splitlines():
        parts = line.split("|")
        if len(parts) < 5 or parts[0] in ("Date", "") or not parts[0].isdigit():
            continue
        try:
            short_v = float(parts[2])
            total_v = float(parts[4])
        except (ValueError, IndexError):
            continue
        if total_v <= 0:
            continue
        rows.append({
            "date": pd.Timestamp(parts[0]),
            "ticker": parts[1].strip().upper(),
            "short_vol": short_v,
            "short_exempt": float(parts[3]) if parts[3].replace(".", "", 1).isdigit() else 0.0,
            "total_vol": total_v,
            "short_ratio": round(short_v / total_v, 4),
        })
    return pd.DataFrame(rows)


class FinraShortVolumeAdapter(Adapter):
    name = "finra_short_volume"
    group = GROUP
    stale_after_days = 4          # daily feed, but tolerate weekends/holidays

    def _have_dates(self) -> set[pd.Timestamp]:
        p = _panel_path()
        if not p.exists():
            return set()
        try:
            return set(pd.read_parquet(p, columns=["date"])["date"].unique())
        except Exception:  # noqa: BLE001
            return set()

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        universe = _universe_tickers()
        have = self._have_dates()
        # Always re-fetch the newest 2 sessions (FINRA can restate same-day), and
        # any window date we don't yet have.
        wanted = _business_days(LOOKBACK_DAYS if not full_history else 120)
        new_frames: list[pd.DataFrame] = []
        fetched = skipped = 0
        for i, d in enumerate(wanted):
            ts = pd.Timestamp(d)
            if ts in have and i >= 2:
                continue
            url = f"{BASE}/CNMSshvol{d.strftime('%Y%m%d')}.txt"
            try:
                r = self.http_get(url, retries=2, timeout=30)
            except Exception as e:  # noqa: BLE001
                if is_connection_error(e):
                    if fetched == 0:
                        raise            # CDN down -> let runner mark failed
                    break                # partial run is fine; keep what we got
                skipped += 1             # 404 = holiday/not-yet-posted
                continue
            df = _parse(r.text)
            if df.empty:
                continue
            if universe:
                df = df[df["ticker"].isin(universe)]
            new_frames.append(df)
            fetched += 1

        if not new_frames:
            # Nothing new to add (cache already current) — emit a heartbeat so the
            # runner sees a successful, fresh run rather than a failure.
            if have:
                hb = pd.DataFrame({"new_rows": [0], "fetched": [0]},
                                  index=[pd.Timestamp(max(have))])
                return {"finra_short_volume__ingest": hb}
            raise RuntimeError(f"finra_short_volume: no data (fetched=0 skipped={skipped})")

        fresh = pd.concat(new_frames, ignore_index=True)
        path = _panel_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            prev = pd.read_parquet(path)
            combined = pd.concat([prev, fresh], ignore_index=True)
        else:
            combined = fresh
        combined = (combined.drop_duplicates(subset=["date", "ticker"], keep="last")
                            .sort_values(["date", "ticker"]).reset_index(drop=True))
        combined.to_parquet(path)

        last = fresh["date"].max()
        log.info("finra_short_volume: +%d rows across %d sessions (%d skipped), panel=%d, latest %s",
                 len(fresh), fetched, skipped, len(combined), last.date())
        hb = pd.DataFrame({"new_rows": [len(fresh)], "fetched": [fetched]}, index=[last])
        return {"finra_short_volume__ingest": hb}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    FinraShortVolumeAdapter().fetch()
