"""scripts/build_flow_surface.py — intraday Flow-Surface snapshot store.

Materializes the per-strike net-premium surface store consumed by the Terminal
"Flow Surface" pane (charting-app terminal/lib/surfaceContract.ts + flowSource.ts).
This is the DATA half of the feature; the renderer half already shipped.

Store contract (RECON.md §2, MASTERPLAN §3 Lane T item 5; shapes pinned by the
Terminal fixtures public/data/surface_idx_fixture.json + surface_fixture.json):

  R2 key  live_flow/surface/{ROOT}/idx.json        → SurfaceIndex
          live_flow/surface/{ROOT}/{HHMM}.json     → SurfaceFrame

  SurfaceIndex = {date, stamps:["HHMM",…] ascending, latest, cadenceSec, cadence?, root?, source?}
  SurfaceFrame = {spot, price_levels:[…] ascending, time_steps:["HH:MM",…],
                  grids:{netprem:[[levelIdx][timeIdx]]}, asof, cadence,
                  metrics?, session_date?, root?}

  Grid orientation (surfaceContract.ts buildHeatBars): grids[metric][levelIdx][timeIdx].
  Rows = price_levels (one per strike, ascending); columns = time_steps realized so far
  today (one per written stamp). Dimensions are len(price_levels) × len(time_steps).

Column semantics — the honest, well-defined per-strike signal the poller can supply:
  The live_flow poller accumulates root_strikes[root][strike] = {call_prem, put_prem, vol}
  as a CUMULATIVE day-to-date rollup (engine/live_flow.py). It does NOT retain per-strike
  per-minute history. So each stamp's netprem column = per strike (call_prem - put_prem),
  i.e. the cumulative session net premium at that strike as of the stamp. Appending one
  column per stamp builds the levels×time matrix the surface pane replays — matching the
  competitor's per-strike-session model (RECON §2: replay & live share one path, one
  immutable snapshot per stamp, server does the math). Nothing is forward-filled.

Cadence honesty (surfaceContract.ts header law — "never pretend a cadence it doesn't have"):
  cadenceSec / cadence are carried verbatim from the ACTUAL write interval. Wired into the
  live_flow poller main loop, that interval is live_flow.cadence_sec (config.yml; 120s = the
  "2-min" label). The poller's full-day re-pull means every cycle's root_strikes is the
  true cumulative to-now, so a 120s cadence is honest for these cumulative columns; we never
  claim a finer cadence than the loop that calls us.

Ledger law: this is a live intraday artifact (like feed_current / tide_current) — it writes
  ONLY to the gitignored staging dir data/live_flow_out/surface/ and uploads to R2. It never
  advances a forward ledger; nightly remains the sole advancer of those.

Idempotency: writing the same stamp twice overwrites that stamp's column in place (the frame
  is keyed by stamp position in time_steps), never duplicating it. Safe to re-run a cycle.

Usage:
  # Dry-run against a synthetic session (prints one idx + snapshot, validates shapes, no IO)
  python -m scripts.build_flow_surface --dry-run
  python -m scripts.build_flow_surface --dry-run --root SPY --stamps 8

  # Programmatic (wired in live_flow_poller.main): build_and_stage_surfaces(...)
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

log = logging.getLogger(__name__)

# Stdlib zoneinfo — repo convention (engine/options_flow.py, live_flow_poller.py).
ET = ZoneInfo("America/New_York")

# R2 prefix for the surface store (under the existing live_flow/ TTL prefix so the
# poller's 48h archive-prune conventions and the Terminal's r2Key both resolve it).
R2_SURFACE_PREFIX = "live_flow/surface/"

# Local staging dir name under data/live_flow_out/ (gitignored — .gitignore:318).
SURFACE_OUT_SUBDIR = "surface"

# Default roots for the store (config live_flow.surface_roots overrides / extends).
DEFAULT_SURFACE_ROOTS = ["SPY", "QQQ", "IWM"]

# The only metric grid Wave 1 fills; the structure stays open (named keys) for
# gex/vanna/charm later — a materializer that computes those appends grids["gex"] etc.
METRIC_NETPREM = "netprem"

# Human cadence labels for the honesty stamp, keyed by the true write interval (seconds).
_CADENCE_LABELS = {60: "1-min", 120: "2-min", 300: "5-min", 600: "10-min", 900: "15-min"}


def cadence_label(cadence_sec: int) -> str:
    """Human cadence label for an interval in seconds (honesty stamp).

    Falls back to "<n>-min" (rounded) for uncommon intervals, or "<n>s" under a minute.
    Never invents a finer cadence than the caller's true write interval.
    """
    try:
        s = int(cadence_sec)
    except (TypeError, ValueError):
        return ""
    if s <= 0:
        return ""
    if s in _CADENCE_LABELS:
        return _CADENCE_LABELS[s]
    if s < 60:
        return f"{s}s"
    return f"{round(s / 60)}-min"


def stamp_hhmm(dt: datetime) -> str:
    """'HHMM' stamp (index key) for an ET-localized datetime."""
    return dt.astimezone(ET).strftime("%H%M")


def stamp_hhcolonmm(dt: datetime) -> str:
    """'HH:MM' time-step label (frame time axis) for an ET-localized datetime."""
    return dt.astimezone(ET).strftime("%H:%M")


def hhmm_to_hhcolonmm(hhmm: str) -> str:
    """'HHMM' → 'HH:MM'. The index carries stamps as HHMM; the frame's time_steps as HH:MM."""
    hhmm = str(hhmm)
    if len(hhmm) == 4 and hhmm.isdigit():
        return f"{hhmm[:2]}:{hhmm[2:]}"
    return hhmm


def net_prem_by_strike(root_strikes: dict) -> dict[float, float]:
    """Cumulative net premium per strike from a root's strike rollup.

    root_strikes: {strike_str → {call_prem, put_prem, vol}} (engine/live_flow.py rollup).
    Returns {strike_float → call_prem - put_prem}. Non-numeric strikes/values are skipped
    (never fabricated). Empty in → empty out.
    """
    out: dict[float, float] = {}
    for stk_str, sv in (root_strikes or {}).items():
        try:
            strike = float(stk_str)
        except (TypeError, ValueError):
            continue
        if not isinstance(sv, dict):
            continue
        call = float(sv.get("call_prem", 0.0) or 0.0)
        put = float(sv.get("put_prem", 0.0) or 0.0)
        out[strike] = call - put
    return out


def append_stamp(
    prior: dict | None,
    *,
    stamp: str,
    time_step: str,
    net_by_strike: dict[float, float],
    spot: float | None,
    asof: str,
    cadence_sec: int,
    session_date: str,
    root: str,
    round_ndigits: int = 0,
) -> dict:
    """Return a new full-day SurfaceFrame with this stamp's column appended (idempotent).

    `prior` is the previously-staged frame for this root today (or None on the first stamp).
    The strike grid (price_levels) is the UNION of all strikes seen across stamps, kept
    ascending; a level absent from an earlier stamp reads 0.0 in that earlier column (the
    strike simply had no cumulative premium yet). Re-appending an existing stamp overwrites
    that column in place — never duplicated (idempotent per stamp).

    Grid is grids["netprem"][levelIdx][timeIdx], dimensions len(price_levels) × len(time_steps).
    """
    prior = prior or {}
    prior_levels: list[float] = [float(x) for x in (prior.get("price_levels") or [])]
    prior_steps: list[str] = list(prior.get("time_steps") or [])
    prior_stamps: list[str] = list(prior.get("stamps") or [])
    prior_grid: list[list[float]] = list(
        (prior.get("grids") or {}).get(METRIC_NETPREM) or []
    )
    prior_spot_path: list = list(prior.get("spot_path") or [])

    # Column index for this stamp: reuse if the stamp already exists (idempotent overwrite),
    # else append a new trailing column.
    if stamp in prior_stamps:
        col_idx = prior_stamps.index(stamp)
        stamps = list(prior_stamps)
        time_steps = list(prior_steps)
    else:
        col_idx = len(prior_stamps)
        stamps = prior_stamps + [stamp]
        time_steps = prior_steps + [time_step]

    n_cols = len(stamps)

    # Union of strikes: prior levels ∪ this stamp's strikes, ascending.
    level_set = set(prior_levels) | set(net_by_strike.keys())
    price_levels = sorted(level_set)
    lvl_index = {lvl: i for i, lvl in enumerate(price_levels)}

    # Rebuild the grid at (len(price_levels) × n_cols), copying prior columns and writing
    # this stamp's column. Missing cells default to 0.0 (honest: no premium there yet).
    grid: list[list[float]] = [[0.0] * n_cols for _ in price_levels]

    # Copy prior columns into the (possibly widened) grid.
    for old_li, old_lvl in enumerate(prior_levels):
        new_li = lvl_index.get(old_lvl)
        if new_li is None:
            continue
        old_row = prior_grid[old_li] if old_li < len(prior_grid) else []
        for cj in range(min(len(old_row), n_cols)):
            grid[new_li][cj] = old_row[cj]

    # Write this stamp's column (overwriting if it already existed).
    for lvl, val in net_by_strike.items():
        li = lvl_index.get(float(lvl))
        if li is not None:
            grid[li][col_idx] = round(float(val), round_ndigits)

    # spot_path tracks the spot at each column (materializer detail; the fixture uses it to
    # resolve a per-stamp spot on replay). Keep it column-aligned.
    spot_path = list(prior_spot_path)
    while len(spot_path) < n_cols:
        spot_path.append(None)
    spot_path[col_idx] = spot

    return {
        "spot": spot,
        "price_levels": price_levels,
        "time_steps": time_steps,
        "grids": {METRIC_NETPREM: grid},
        "asof": asof,
        "cadence": cadence_label(cadence_sec),
        "metrics": [METRIC_NETPREM],
        "session_date": session_date,
        "root": root,
        # Materializer bookkeeping (harmless extras — the Terminal validator ignores them
        # and the fixture path reads `stamps`/`spot_path` for replay truncation):
        "stamps": stamps,
        "spot_path": spot_path,
    }


def build_index(frame: dict, *, session_date: str, cadence_sec: int, root: str,
                source: str = "poller") -> dict:
    """Build the SurfaceIndex from a full-day frame. latest === stamps[-1] (contract law).

    checkIndexFilesContract (surfaceContract.ts) requires: stamps match the written files,
    and latest is the last stamp (or null when empty). We derive both from the frame so the
    idx and the snapshot files can never disagree.
    """
    stamps: list[str] = list(frame.get("stamps") or [])
    return {
        "date": session_date,
        "stamps": stamps,
        "latest": stamps[-1] if stamps else None,
        "cadenceSec": int(cadence_sec),
        "cadence": cadence_label(cadence_sec),
        "root": root,
        "source": source,
        # idx-level as-of (fixture parity — the newest frame's timestamp). Optional per the
        # isSurfaceIndex validator; carried so the UI can stamp the index freshness honestly.
        "asof": frame.get("asof", ""),
    }


def frame_for_stamp(full_frame: dict, stamp: str) -> dict:
    """Truncate a full-day frame to the realized-so-far window for `stamp` (replay view).

    Mirrors the Terminal's flowSource.ts `surface:` fixture logic: time_steps + each grid row
    are sliced to columns up to and including `stamp`; spot resolves from spot_path at that
    column. This is the exact per-stamp SurfaceFrame written to {HHMM}.json. Unknown stamp →
    the full day (never fabricated).
    """
    stamps: list[str] = list(full_frame.get("stamps") or [])
    times: list[str] = list(full_frame.get("time_steps") or [])
    idx = stamps.index(stamp) if stamp in stamps else -1
    upto = idx + 1 if idx >= 0 else len(times)
    grids_full = full_frame.get("grids") or {}
    grids = {m: [row[:upto] for row in g] for m, g in grids_full.items()}
    spot_path = full_frame.get("spot_path") or []
    spot = spot_path[upto - 1] if (spot_path and upto - 1 < len(spot_path) and upto >= 1) else full_frame.get("spot")
    return {
        "spot": spot,
        "price_levels": list(full_frame.get("price_levels") or []),
        "time_steps": times[:upto],
        "grids": grids,
        "asof": full_frame.get("asof", ""),
        "cadence": full_frame.get("cadence", ""),
        "metrics": list(full_frame.get("metrics") or list(grids_full.keys())),
        "session_date": full_frame.get("session_date", ""),
        "root": full_frame.get("root", ""),
    }


# ── validators (mirror surfaceContract.ts, for the dry-run self-check + tests) ──────

def is_surface_index(x: object) -> bool:
    """Port of surfaceContract.ts isSurfaceIndex."""
    if not isinstance(x, dict):
        return False
    return (
        isinstance(x.get("date"), str)
        and isinstance(x.get("stamps"), list)
        and all(isinstance(s, str) for s in x["stamps"])
        and (x.get("latest") is None or isinstance(x.get("latest"), str))
        and isinstance(x.get("cadenceSec"), int)
        and not isinstance(x.get("cadenceSec"), bool)
    )


def is_surface_frame(x: object) -> bool:
    """Port of surfaceContract.ts isSurfaceFrame."""
    if not isinstance(x, dict):
        return False
    return (
        isinstance(x.get("price_levels"), list)
        and isinstance(x.get("time_steps"), list)
        and isinstance(x.get("grids"), dict)
        and isinstance(x.get("asof"), str)
        and isinstance(x.get("cadence"), str)
    )


def check_index_files_contract(index: dict, available_stamps: list[str]) -> dict:
    """Port of surfaceContract.ts checkIndexFilesContract.

    {ok, missing, extra, latestOk}: missing = stamps promised by the index with no file;
    extra = files present the index doesn't list; latestOk = latest is the last stamp.
    """
    idx_stamps = list(index.get("stamps") or [])
    idx_set = set(idx_stamps)
    avail_set = set(available_stamps)
    missing = [s for s in idx_stamps if s not in avail_set]
    extra = [s for s in available_stamps if s not in idx_set]
    if not idx_stamps:
        latest_ok = index.get("latest") is None
    else:
        latest_ok = index.get("latest") == idx_stamps[-1]
    return {
        "ok": not missing and not extra and latest_ok,
        "missing": missing,
        "extra": extra,
        "latestOk": latest_ok,
    }


def validate_frame_dims(frame: dict) -> None:
    """Assert the grid is exactly len(price_levels) × len(time_steps) for every metric.

    Raises ValueError on any mismatch — a materializer self-check the caller can gate on.
    """
    n_levels = len(frame.get("price_levels") or [])
    n_steps = len(frame.get("time_steps") or [])
    for metric, grid in (frame.get("grids") or {}).items():
        if len(grid) != n_levels:
            raise ValueError(
                f"grid[{metric}] has {len(grid)} rows, expected {n_levels} (price_levels)"
            )
        for li, row in enumerate(grid):
            if len(row) != n_steps:
                raise ValueError(
                    f"grid[{metric}][{li}] has {len(row)} cols, expected {n_steps} (time_steps)"
                )


# ── staging + upload (mirror live_flow_poller conventions) ─────────────────────────

def _surface_out_dir(root: str) -> Path:
    """data/live_flow_out/surface/{ROOT}/ (gitignored staging; created on demand)."""
    from lib import config  # local import — keeps pure functions importable without config
    p = config.data_dir() / "live_flow_out" / SURFACE_OUT_SUBDIR / root.upper()
    p.mkdir(parents=True, exist_ok=True)
    return p


def _write_json_atomic(path: Path, obj: dict) -> Path:
    """Atomic JSON write (tmp + rename), mirroring live_flow_poller._write_json."""
    tmp = path.with_suffix(".tmp.json")
    tmp.write_text(json.dumps(obj, default=str))
    tmp.rename(path)
    return path


def _load_prior_full_frame(root: str) -> dict | None:
    """Load the staged full-day frame for this root today, or None.

    The full frame (with `stamps`/`spot_path`) is kept in a private staging file
    `_full.json` alongside the per-stamp public files, so the next cycle can append a
    column without re-reading every {HHMM}.json. Session rollover (a new date) is handled
    by the caller passing session_date; a stale-date full frame is ignored.
    """
    try:
        f = _surface_out_dir(root) / "_full.json"
        if f.exists():
            return json.loads(f.read_text())
    except Exception as e:  # noqa: BLE001
        log.debug("surface: prior full-frame load failed for %s: %s", root, e)
    return None


def build_and_stage_surfaces(
    *,
    root_strikes_by_root: dict,
    roots: list[str],
    session_date: str,
    asof: str,
    cadence_sec: int,
    now: datetime | None = None,
    spot_by_root: dict | None = None,
) -> list[tuple[Path, str]]:
    """Build + stage the surface store for each root; return [(local_path, r2_key), …].

    Called from the live_flow poller main loop AFTER ticker JSONs are built, with the
    cycle's tide_day_state["root_strikes"]. For each root it:
      1. computes this stamp's net-premium column from the cumulative strike rollup,
      2. appends it to the staged full-day frame (idempotent per stamp),
      3. writes the per-stamp {HHMM}.json (truncated replay frame) + idx.json,
      4. re-writes the private _full.json staging frame,
    and returns the (local_path, r2_key) pairs for the caller to upload via _upload_r2.

    Roots with an empty strike rollup this cycle are skipped (no column written) so an
    empty cycle never blanks a good prior frame — mirrors the ticker "skip empty" guard.
    Never raises for a single root; a bad root is logged and skipped.
    """
    now = now or datetime.now(timezone.utc)
    stamp = stamp_hhmm(now)
    time_step = stamp_hhcolonmm(now)
    spot_by_root = spot_by_root or {}
    out: list[tuple[Path, str]] = []

    for root in roots:
        root_u = root.upper()
        try:
            rstk = (root_strikes_by_root or {}).get(root_u) or (root_strikes_by_root or {}).get(root) or {}
            net = net_prem_by_strike(rstk)
            if not net:
                log.info("surface: skip %s (no strike rollup this cycle)", root_u)
                continue

            prior = _load_prior_full_frame(root_u)
            # Session rollover guard: drop a prior frame from a different session date.
            if prior and prior.get("session_date") not in (None, "", session_date):
                prior = None

            spot = spot_by_root.get(root_u, spot_by_root.get(root))
            full = append_stamp(
                prior,
                stamp=stamp,
                time_step=time_step,
                net_by_strike=net,
                spot=spot,
                asof=asof,
                cadence_sec=cadence_sec,
                session_date=session_date,
                root=root_u,
            )
            validate_frame_dims(full)

            index = build_index(full, session_date=session_date, cadence_sec=cadence_sec, root=root_u)
            snap = frame_for_stamp(full, stamp)

            out_dir = _surface_out_dir(root_u)
            # Private staging frame (full day + bookkeeping) — never uploaded.
            _write_json_atomic(out_dir / "_full.json", full)
            # Public files (uploaded to R2).
            idx_path = _write_json_atomic(out_dir / "idx.json", index)
            snap_path = _write_json_atomic(out_dir / f"{stamp}.json", snap)

            out.append((idx_path, f"{R2_SURFACE_PREFIX}{root_u}/idx.json"))
            out.append((snap_path, f"{R2_SURFACE_PREFIX}{root_u}/{stamp}.json"))
            log.info("surface: staged %s stamp=%s levels=%d steps=%d",
                     root_u, stamp, len(full["price_levels"]), len(full["time_steps"]))
        except Exception as e:  # noqa: BLE001
            log.warning("surface: build failed for %s: %s", root_u, e)
            continue

    return out


def resolve_surface_roots(cfg: dict, root_gross_today: dict | None = None) -> list[str]:
    """Resolve the surface root list: config live_flow.surface_roots (or defaults) + top-N actives.

    config live_flow.surface_roots overrides the base list; surface_top_n (default 0) appends
    that many additional roots by day gross premium (cheap: reuses the cycle's root_gross_today,
    no extra fetch). Deduped, order-preserving.
    """
    base = [r.upper() for r in (cfg.get("surface_roots") or DEFAULT_SURFACE_ROOTS)]
    top_n = int(cfg.get("surface_top_n", 0) or 0)
    extra: list[str] = []
    if top_n > 0 and root_gross_today:
        ranked = sorted(root_gross_today.items(), key=lambda kv: kv[1], reverse=True)
        extra = [r.upper() for r, _ in ranked[: top_n * 3]]  # oversample, dedup below trims
    seen: set[str] = set()
    outl: list[str] = []
    for r in base + extra:
        if r not in seen:
            seen.add(r)
            outl.append(r)
        if top_n > 0 and len(outl) >= len(base) + top_n:
            break
    return outl


# ── dry-run: synthetic session, printed + validated, zero IO ────────────────────────

def _synthetic_session(root: str, n_stamps: int, cadence_sec: int) -> dict:
    """Build a full-day frame over `n_stamps` synthetic cycles (dense enough that the paint
    look is visible). Deterministic; no randomness, no network, no filesystem.

    Sinusoidal per-strike net premium with a moving hot pocket near spot — the shape the
    Terminal fixtures use so the shader's two-band signature shows in crops.
    """
    import math

    session_date = "2026-07-06"
    spot0 = 600.0
    strikes = [spot0 - 25 + 5 * i for i in range(11)]  # 575..625 step 5
    open_min = 9 * 60 + 30  # 09:30 ET
    full: dict | None = None
    for k in range(n_stamps):
        minute = open_min + k * (cadence_sec // 60)
        hh, mm = divmod(minute, 60)
        stamp = f"{hh:02d}{mm:02d}"
        time_step = f"{hh:02d}:{mm:02d}"
        spot = spot0 + 6 * math.sin(k / 6.0)
        # Cumulative net premium per strike: grows over the day (∝ k), signed by moneyness,
        # with a hot pocket that drifts with spot.
        net: dict[float, float] = {}
        for s in strikes:
            dist = abs(s - spot)
            hot = math.exp(-((s - spot) ** 2) / (2 * 8.0 ** 2))  # gaussian near spot
            sign = 1.0 if s >= spot else -1.0
            net[s] = round(sign * (k + 1) * 1_000_000 * (0.3 + hot) - dist * 5_000, 0)
        asof = f"{session_date}T{hh:02d}:{mm:02d}:00-04:00"
        full = append_stamp(
            full, stamp=stamp, time_step=time_step, net_by_strike=net, spot=round(spot, 2),
            asof=asof, cadence_sec=cadence_sec, session_date=session_date, root=root,
        )
    return full or {}


def dry_run(root: str = "SPY", n_stamps: int = 6, cadence_sec: int = 120) -> dict:
    """Produce a sample idx + a mid-session snapshot + the latest snapshot, validate them
    against the ported contract, and return a report dict. No filesystem, no network.
    """
    full = _synthetic_session(root, n_stamps, cadence_sec)
    index = build_index(full, session_date=full.get("session_date", ""), cadence_sec=cadence_sec, root=root)
    stamps = list(full.get("stamps") or [])
    latest = stamps[-1] if stamps else ""
    mid = stamps[len(stamps) // 2] if stamps else ""
    latest_frame = frame_for_stamp(full, latest)
    mid_frame = frame_for_stamp(full, mid)

    # Contract self-checks (mirror the Terminal validators).
    checks = {
        "isSurfaceIndex": is_surface_index(index),
        "isSurfaceFrame(latest)": is_surface_frame(latest_frame),
        "isSurfaceFrame(mid)": is_surface_frame(mid_frame),
        "indexFilesContract(full)": check_index_files_contract(index, stamps)["ok"],
        "latest===stamps[-1]": index.get("latest") == (stamps[-1] if stamps else None),
        "cadenceHonest": index.get("cadenceSec") == cadence_sec and bool(index.get("cadence")),
    }
    # Dim checks throw on failure; capture as booleans.
    try:
        validate_frame_dims(latest_frame)
        checks["dims(latest)=levels×steps"] = True
    except ValueError:
        checks["dims(latest)=levels×steps"] = False
    try:
        validate_frame_dims(mid_frame)
        checks["dims(mid)=levels×steps"] = True
    except ValueError:
        checks["dims(mid)=levels×steps"] = False

    return {
        "root": root,
        "cadenceSec": cadence_sec,
        "index": index,
        "latest_stamp": latest,
        "mid_stamp": mid,
        "latest_frame": latest_frame,
        "mid_frame": mid_frame,
        "checks": checks,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Flow-Surface snapshot store materializer")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print + validate a synthetic idx/snapshot; no IO. (default action)")
    parser.add_argument("--root", default="SPY", help="Root for the dry-run sample")
    parser.add_argument("--stamps", type=int, default=6, help="Synthetic stamp count for the dry-run")
    parser.add_argument("--cadence-sec", type=int, default=120,
                        help="True write interval for the honesty stamp (default 120 = poller cadence)")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    # Default (and only) CLI action is the dry-run — the live path is invoked in-process
    # from the poller loop, never as a standalone cron (no second, unrelated cadence).
    report = dry_run(root=args.root, n_stamps=args.stamps, cadence_sec=args.cadence_sec)

    print("=== SurfaceIndex (live_flow/surface/{}/idx.json) ===".format(args.root))
    print(json.dumps(report["index"], indent=2))
    print("\n=== SurfaceFrame @ mid stamp {} (live_flow/surface/{}/{}.json) ===".format(
        report["mid_stamp"], args.root, report["mid_stamp"]))
    print(json.dumps(report["mid_frame"], indent=2, default=str))
    print("\n=== SurfaceFrame @ latest stamp {} — shape summary ===".format(report["latest_stamp"]))
    lf = report["latest_frame"]
    print(json.dumps({
        "spot": lf["spot"],
        "n_price_levels": len(lf["price_levels"]),
        "n_time_steps": len(lf["time_steps"]),
        "grid_dims(netprem)": [len(lf["grids"]["netprem"]), len(lf["grids"]["netprem"][0]) if lf["grids"]["netprem"] else 0],
        "cadence": lf["cadence"],
        "metrics": lf["metrics"],
    }, indent=2, default=str))
    print("\n=== contract self-checks (mirror surfaceContract.ts) ===")
    print(json.dumps(report["checks"], indent=2))

    all_ok = all(report["checks"].values())
    print("\nALL CHECKS PASS" if all_ok else "\nCHECKS FAILED")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
