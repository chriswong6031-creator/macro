"""Build the 同花顺 (THS) thematic-baskets page -> site/baskets_china_ths.html
(+ chinabasketdata/baskets_ths.json).

The machine-maintained sibling of scripts/build_baskets_china.py. Reads
data/baskets_china_ths/membership.json (seeded by scripts.seed_china_ths_baskets from THS concept
boards) + the china_search close cache + the CSI 300 ETF via
engine.baskets_china.compute_china_ths_baskets(), then renders the SAME FactorWatch baskets view
(templates/baskets_china.html.j2 in `lite` mode — perf table, overlay chart, category cards with
inline member drill), benchmarked to the CSI 300. The lite render drops the curated page's
theme-rotation desk / forming-narratives / allocation scorecard (those are tied to the curated set).

Additive — any failure logs and returns 0 so it can never break the rest of the site.

Usage: python -m scripts.build_baskets_china_ths
       python -m scripts.build_baskets_china_ths --snapshot   (PIT membership side-car only)

--snapshot (CN-SYS W1 side-car): append a dated point-in-time snapshot of THS concept
membership to data/baskets_china_ths/snapshots/YYYY-MM-DD.json so membership history accrues
(any future theme study is look-ahead-dead without it). Content-deduped: a new dated file is
written only when membership differs from the most recent snapshot; PIT read = most recent
snapshot ≤ date. Skips the full page render entirely.
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import config  # noqa: E402
from lib.pages import write_page  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("build_baskets_china_ths")


def snapshot_membership() -> int:
    """Append a dated PIT snapshot of THS concept membership (content-deduped, never fatal)."""
    import hashlib

    try:
        src = config.data_dir() / "baskets_china_ths" / "membership.json"
        if not src.exists():
            log.warning("ths snapshot: membership.json missing — skipping")
            return 0
        snap_dir = config.data_dir() / "baskets_china_ths" / "snapshots"
        snap_dir.mkdir(parents=True, exist_ok=True)
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        dest = snap_dir / f"{today}.json"
        if dest.exists():
            log.info("ths snapshot: %s already stamped — skipping", today)
            return 0
        raw = src.read_bytes()
        prior = sorted(p for p in snap_dir.glob("????-??-??.json"))
        if prior:
            last = prior[-1]
            if hashlib.sha256(last.read_bytes()).hexdigest() == hashlib.sha256(raw).hexdigest():
                log.info("ths snapshot: membership unchanged since %s — dedup skip", last.stem)
                return 0
        dest.write_bytes(raw)
        log.info("ths snapshot: wrote %s (%d bytes)", dest.name, len(raw))
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("ths snapshot failed (%s)", e)
    return 0


def main() -> int:
    if "--snapshot" in sys.argv[1:]:
        return snapshot_membership()
    site = config.ROOT / "site"
    try:
        from engine.baskets_china import compute_china_ths_baskets
        data = compute_china_ths_baskets()
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("china THS baskets engine failed: %s", e)
        return 0
    if not data:
        log.warning("no china THS baskets (need data/baskets_china_ths/membership.json — run "
                    "scripts.seed_china_ths_baskets) — skipping")
        return 0

    # Validated sleeve-size chip (W6-CN Fix 1) — thread risk_radar_intl gross_factor into the
    # THS baskets JSON header as a DISPLAY chip. Regime sizes sleeves, never vetoes names.
    try:
        from engine.risk_radar_intl import cn_sleeve_chip
        data["sleeve_chip"] = cn_sleeve_chip()
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("china THS baskets: sleeve chip failed (%s)", e)

    # Validated AI-semis slice confirmer (W6-CN Fix 3 — #773) — wire global AI-semis
    # (SMH/SOXX/TSM 4w-mom) → next-week CN CPO/PCB/storage_chip tailwind chip.
    # Display chip + JSON field; no name-level gating. t=3.27, horse-race stable.
    try:
        from engine.cn_ai_semis_confirmer import compute as _semis_compute, is_target_basket
        semis_chip = _semis_compute()
        data["ai_semis_confirmer"] = semis_chip
        # Also annotate each AI-supply basket row with the chip
        for b in data.get("baskets", []):
            if is_target_basket(b.get("id", "")):
                b["ai_semis_confirmer"] = semis_chip
        log.info("THS baskets AI-semis confirmer: %s (mom_4w=%s)",
                 semis_chip.get("state"), semis_chip.get("semis_mom_4w"))
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("china THS baskets: AI-semis confirmer failed (%s)", e)

    fdir = site / "chinabasketdata"
    fdir.mkdir(parents=True, exist_ok=True)
    (fdir / "baskets_ths.json").write_text(json.dumps(data, separators=(",", ":"), default=str))

    chart = data.pop("chart")
    built = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    env = Environment(loader=FileSystemLoader(str(config.ROOT / "templates")), autoescape=True)
    html = env.get_template("baskets_china.html.j2").render(
        baskets_json=json.dumps(data, separators=(",", ":"), ensure_ascii=False),
        chart_json=json.dumps(chart, separators=(",", ":")),
        lite=True, basket_base="",
        bench_en="CSI 300", bench_zh="沪深300",
        generated_utc=built)
    write_page(site / "baskets_china_ths.html", html)
    # the page uses the TradingView Lightweight Charts runtime (Apache-2.0); the curated china
    # build also ships it, but emit it here too so this page works even if built standalone.
    lwc = config.ROOT / "templates" / "lightweight-charts.js"
    if lwc.exists():
        (site / "lightweight-charts.js").write_text(lwc.read_text())
    log.info("wrote %s/baskets_china_ths.html (%d baskets, %d categories, %d KB)",
             site, len(data["baskets"]), len(data.get("categories", [])), len(html) // 1024)

    # W3.8 — FREEZE China THS basket levels + membership hashes (append-only, PIT).
    # chart was popped from data above and is still in scope.
    try:
        from engine.basket_freeze import freeze_domain, FreezeSkipped
        from engine.baskets_china import _ths_membership, _closes as _cn_closes_ths
        _ths_mem_data = _ths_membership()
        try:
            _ths_cl = _cn_closes_ths()
        except Exception:  # noqa: BLE001
            _ths_cl = None
        _freeze_result = freeze_domain("china_ths", {"chart": chart}, _ths_cl, _ths_mem_data)
        log.info("basket_freeze[china_ths]: %s", _freeze_result)
    except FreezeSkipped as e:
        log.error("basket_freeze[china_ths]: SKIPPED (churn guard): %s", e)
    except Exception as e:  # noqa: BLE001
        log.error("basket_freeze[china_ths]: failed: %s", e)

    # Emit a minimal latest.json for signal_archive accrual.
    # Per-basket: id, ret_60d (perf['60d']['ret'] — 60 TRADING days, engine HORIZONS),
    # above_200d (the engine's own EW basket level vs its 200d SMA). Levels come from
    # `chart` (popped above, still in scope) — the same series the page plots, no extra fetch.
    try:
        _lvl_map = chart.get("baskets", {}) if isinstance(chart, dict) else {}
        _snap_baskets = []
        for _b in data.get("baskets", []):
            _bid = _b.get("id", "")
            _ret60 = None
            _perf = _b.get("perf") or {}
            _p60 = _perf.get("60d") or {}
            if _p60.get("ret") is not None:
                _ret60 = round(float(_p60["ret"]), 4)
            _above200 = None
            _lvls = [v for v in (_lvl_map.get(_bid) or []) if v is not None]
            if len(_lvls) >= 200:
                _above200 = bool(_lvls[-1] > sum(_lvls[-200:]) / 200.0)
            _snap_baskets.append({"id": _bid, "ret_60d": _ret60, "above_200d": _above200})
        _latest = {
            "as_of": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "baskets": _snap_baskets,
        }
        _latest_path = config.data_dir() / "baskets_china_ths" / "latest.json"
        _latest_path.parent.mkdir(parents=True, exist_ok=True)
        _latest_path.write_text(json.dumps(_latest, separators=(",", ":")))
        log.info("china THS baskets: wrote latest.json (%d baskets)", len(_snap_baskets))
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("china THS baskets: latest.json emit failed (%s)", e)

    return 0


if __name__ == "__main__":
    sys.exit(main())
