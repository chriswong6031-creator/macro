"""Build the 同花顺 (THS) thematic-baskets page -> site/baskets_china_ths.html
(+ chinabasketdata/baskets_ths.json and the chinabasketdata/baskets_ths_hydrate.json side-car
the page fetches for its member rows + per-basket level history).

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

The same flag also stamps BOTH CN basket suites into the queryable per-suite PIT parquets
data/<suite>/membership_history.parquet (engine/basket_membership_pit.py) — CN Prophet
masterplan §5 W-C, the prerequisite for any relay-construction promotion. Same lane, same
content-dedup, keep-first per snapshot_date.
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
    """Append a dated PIT snapshot of THS concept membership (content-deduped, never fatal).

    Two stores plus one stamp, one lane.  The dated JSON side-car below is the
    original (2026-06-30 / 2026-07-08 were its only rows until GMI W1a wired an
    actual producer); ``_snapshot_membership_pit`` stamps the SAME membership into
    the queryable per-suite parquet the relay program needs, and does the curated
    suite at the same time.  Both are content-deduped and keep-first, so a same-day
    re-run is a no-op in either.

    ``_cadence.json`` is rewritten UNCONDITIONALLY, including on every early return
    above — and that is the point of it.  This step ran green ~35 nights in a row
    writing nothing at all, because it hashes today's membership.json against the
    newest side-car, matches, and skips; membership.json had been frozen since
    2026-06-30 because nothing was refreshing it (the scraper and seeder appeared in
    no workflow).  A deduping writer and an unwired writer leave the identical trace
    on disk: nothing.  The cadence stamp is what tells them apart, and
    ``scripts/check_membership_snapshot_freshness.py`` is what reads it.
    """
    import hashlib

    from engine import basket_membership_pit as _pit  # noqa: PLC0415

    suite = _pit.SUITE_THS
    _snapshot_membership_pit()
    sha = None
    try:
        src = config.data_dir() / "baskets_china_ths" / "membership.json"
        # NO early return on any path below: each one falls through to the stamp, so a
        # writer that ran and found nothing looks different from a writer nobody wired.
        if not src.exists():
            log.warning("ths snapshot: membership.json missing — nothing to stamp")
        else:
            snap_dir = config.data_dir() / "baskets_china_ths" / "snapshots"
            snap_dir.mkdir(parents=True, exist_ok=True)
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            dest = snap_dir / f"{today}.json"
            raw = src.read_bytes()
            sha = hashlib.sha256(raw).hexdigest()
            if dest.exists():
                log.info("ths snapshot: %s already stamped — skipping", today)
            else:
                prior = _pit.dated_snapshots(suite)
                if prior and hashlib.sha256(prior[-1].read_bytes()).hexdigest() == sha:
                    log.info("ths snapshot: membership unchanged since %s — dedup skip",
                             prior[-1].stem)
                else:
                    dest.write_bytes(raw)
                    log.info("ths snapshot: wrote %s (%d bytes)", dest.name, len(raw))
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("ths snapshot failed (%s)", e)
    _pit.write_cadence_stamp(suite, writer="scripts.build_baskets_china_ths",
                             membership_sha=sha)
    return 0


def _membership_pit_lane() -> str | None:
    """The collection lane this process runs in, resolved FAIL-CLOSED from ``CN_LANE``.

    Deliberately NOT ``os.environ.get("CN_LANE", "asia")`` — the permissive form this
    call site shipped with, which made the gate behind it dead: with an "asia" default
    every context that leaves ``CN_LANE`` unset arrived at
    ``basket_membership_pit._lane_ok`` claiming to BE the asia lane, so the lane check
    never fired on anything.

    The default cannot be safe here.  The PIT store is append-only, keep-FIRST per
    ``(snapshot_date, basket_id, ticker)`` and content-deduped (CN Prophet masterplan
    §5 W-C), so the FIRST lane to stamp a date owns that snapshot forever — a second
    lane's view of the same membership is discarded in silence.  Whoever ran first
    would decide the published point-in-time answer for every date after it.

    Only .github/workflows/asia-close.yml sets ``CN_LANE: asia`` (band A, "CN/HK
    builder band A" — the only lane that commits ``data/``), so every other context —
    a hand-run, a future render-lane adopter — resolves None here and appends nothing.
    No workflow change: the lane is derived from what the workflows already pass.
    """
    import os  # noqa: PLC0415 — local to the side-car path

    return (os.environ.get("CN_LANE") or "").strip() or None


def _snapshot_membership_pit() -> None:
    """Stamp BOTH CN basket suites into their append-only PIT parquets.

    CN Prophet masterplan §2.12 / §5 W-C: the THS membership behind the 12-month
    ignition study was ONE snapshot applied backward, and the two PIT snapshots
    that exist differ by 7.7% of member-slots in 8 days.  A queryable PIT store
    is the stated prerequisite for promoting any relay construction, so it
    accrues from the lane that already owns membership side-cars rather than
    waiting on the study that needs it.

    LANE: ``--snapshot`` is invoked only by the asia collection lane
    (.github/workflows/asia-close.yml, step "CN/HK builder band A", CN_LANE=asia)
    — the only lane that commits ``data/``.  The gate is resolved FAIL-CLOSED by
    ``_membership_pit_lane`` (no default), so a hand-run from a render lane writes
    nothing.  Never fatal.
    """
    try:
        from engine import basket_membership_pit as _pit  # noqa: PLC0415

        res = _pit.append_all(lane=_membership_pit_lane())
        for suite, r in res.items():
            snap = r.get("snapshot") or {}
            log.info("membership PIT [%s]: %s (+%d rows, backfill +%d)", suite,
                     snap.get("snapshot_date") if snap.get("written")
                     else f"skipped — {snap.get('reason')}",
                     int(snap.get("rows_added") or 0),
                     int((r.get("backfill") or {}).get("rows_added") or 0))
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("membership PIT snapshot failed (%s)", e)


HYDRATE_REL = "chinabasketdata/baskets_ths_hydrate.json"


def split_for_page(data: dict, chart: dict) -> tuple[dict, dict, dict]:
    """Page-weight split (SEO audit 2026-08-03): heavy planes -> out-of-line payload.

    Returns (slim_data, slim_chart, hydrate). Never mutates its inputs. Row-preserving:
    every member row and every chart series lands in `hydrate`, keyed by basket id.
    The payload ships beside baskets_ths.json under site/chinabasketdata/, which is
    deliberately UNDECLARED in config/site_access.yml -> it inherits the same
    default-premium (regwalled) class as the page itself; do not add it to any
    public/free list.
    """
    slim_data = {k: v for k, v in data.items() if k != "baskets"}
    slim_data["baskets"] = [
        {k: v for k, v in b.items() if k != "members"} for b in data.get("baskets", [])
    ]
    slim_data["hydrate"] = HYDRATE_REL
    slim_chart = {
        "dates": chart.get("dates", []),
        "bench": chart.get("bench", []),
        "baskets": {},
    }
    hydrate = {
        "schema": "ths_hydrate.v1",
        "as_of": data.get("as_of"),
        "members": {b["id"]: b.get("members", []) for b in data.get("baskets", [])},
        "chart_baskets": chart.get("baskets", {}),
    }
    return slim_data, slim_chart, hydrate


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
    # Page-weight split (SEO audit 2026-08-03): the inline document keeps the summary planes for
    # first paint; member rows + per-basket level history move to a fetched same-plane payload.
    # split_for_page does not mutate data/chart, so the freeze / latest.json / turn-annotation
    # blocks below still see the full objects.
    slim_data, slim_chart, hydrate = split_for_page(data, chart)
    hydrate_txt = json.dumps(hydrate, separators=(",", ":"), ensure_ascii=False, default=str)
    # written BEFORE the page so a payload failure fails the run rather than shipping a slim
    # page whose data never arrives.
    (site / HYDRATE_REL).write_text(hydrate_txt)

    built = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    env = Environment(loader=FileSystemLoader(str(config.ROOT / "templates")), autoescape=True)
    # China SI consolidation (2026-08): baskets_china.html.j2 became a redirect stub; the
    # full FactorWatch template was extracted byte-identically to this name for the THS page.
    html = env.get_template("baskets_china_factorwatch.html.j2").render(
        baskets_json=json.dumps(slim_data, separators=(",", ":"), ensure_ascii=False),
        chart_json=json.dumps(slim_chart, separators=(",", ":")),
        lite=True, basket_base="",
        bench_en="CSI 300", bench_zh="沪深300",
        generated_utc=built)
    write_page(site / "baskets_china_ths.html", html)
    # the page uses the TradingView Lightweight Charts runtime (Apache-2.0); the curated china
    # build also ships it, but emit it here too so this page works even if built standalone.
    lwc = config.ROOT / "templates" / "lightweight-charts.js"
    if lwc.exists():
        (site / "lightweight-charts.js").write_text(lwc.read_text())
    log.info("wrote %s/baskets_china_ths.html (%d baskets, %d categories, %d KB) "
             "+ %s (%d KB: %d member rows, %d chart series)",
             site, len(data["baskets"]), len(data.get("categories", [])), len(html) // 1024,
             HYDRATE_REL, len(hydrate_txt.encode("utf-8")) // 1024,
             sum(len(v) for v in hydrate["members"].values()), len(hydrate["chart_baskets"]))

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

    # W8-R5 — CN basket turn-watch organ: annotate THS baskets_ths.json with turn states.
    # The artifact was already written by build_baskets_china.py (curated builder runs first
    # in the asia lane — see dag.yml). Here we re-read the committed artifact and annotate
    # the THS basket rows, then re-write baskets_ths.json. Additive — never fatal.
    try:
        _ths_fdir = site / "chinabasketdata"
        _ths_turn_path = _ths_fdir / "basket_turn_cn.json"
        if _ths_turn_path.exists():
            _ths_turn_art = json.loads(_ths_turn_path.read_text())
            _ths_turn_states = _ths_turn_art.get("baskets", {})
            _ths_bj_path = _ths_fdir / "baskets_ths.json"
            if _ths_bj_path.exists():
                _ths_bj = json.loads(_ths_bj_path.read_text())
                for _b in (_ths_bj.get("baskets") or []):
                    _bid = _b.get("id")
                    if _bid and _bid in _ths_turn_states:
                        _b["turn_state"] = _ths_turn_states[_bid].get("state", "NONE")
                        _b["turn_dd_252"] = _ths_turn_states[_bid].get("dd_252")
                        _b["turn_evidence"] = _ths_turn_states[_bid].get("evidence", [])
                _ths_bj_path.write_text(json.dumps(_ths_bj, separators=(",", ":"), default=str))
                log.info("china_basket_turn: annotated %d THS baskets with turn states",
                         len(_ths_bj.get("baskets") or []))
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("china_basket_turn: THS baskets.json annotation failed: %s", e)

    return 0


if __name__ == "__main__":
    sys.exit(main())
