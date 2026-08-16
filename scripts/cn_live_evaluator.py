"""scripts/cn_live_evaluator.py — CN Breathing Platform 5-minute pass (CN-PR-1).

Product clock is the VPS timer ``macro-live-cnprophet.timer``. This script
self-gates on :func:`engine.prophet_live.cn_clock.is_evaluable` — a holiday tick
exits in <1s. ``.github/workflows/cn-prophet-live.yml`` is a self-disabling
backstop (never the product clock; GitHub cron is disqualified for cadence).

    python -m scripts.cn_live_evaluator [--dry-run] [--now ISO] [--root PATH]

QUOTE SOURCE (spec §3), preference order:
  1. VPS local plane (``quotes_full.json`` + ``live/quotes.json``, freshest-wins)
  2. direct ``engine.live_quotes.fetch_quotes`` for armed names the plane lacks
     or serves stale — bounded ≤9 Yahoo spark batches.

LEDGER LAW (G0.2). No ``data/`` writes, no git. Kill switch
``CN_PROPHET_LIVE_NO_PUBLISH=1`` is separate from the US one.

NO PANDAS ON THIS PATH. The backstop workflow installs ``pyyaml boto3`` only.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_CODE_ROOT = str(Path(__file__).resolve().parent.parent)
sys.path.insert(0, _CODE_ROOT)

from engine.prophet_live import cn_clock  # noqa: E402
from engine.prophet_live import cn_states as CS  # noqa: E402
from engine.prophet_live import live_states as LS  # noqa: E402
from engine.prophet_live import r2io  # noqa: E402

log = logging.getLogger("cn_live_evaluator")

LOCAL_SOURCE = "vps_local"
LOCAL_QUOTE_PATHS: tuple[str, ...] = (
    "/var/lib/macro-live/state/quotes_full.json",
    "/var/lib/macro-live/public/live/quotes.json",
)
SERVED_PATH = "/var/lib/macro-live/public/live/cn_prophet_live.json"
MAX_FETCH_BATCHES = 9
BATCH_SIZE = 20


def cfg_block(conf: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(conf, dict):
        return {}
    block = conf.get("cn_prophet_live")
    return block if isinstance(block, dict) else {}


def local_quote_paths(block: dict[str, Any]) -> list[Path]:
    raw = block.get("local_quote_paths", None)
    if raw is None:
        raw = list(LOCAL_QUOTE_PATHS)
    if isinstance(raw, (str, Path)):
        raw = [raw]
    if not isinstance(raw, (list, tuple)):
        raw = list(LOCAL_QUOTE_PATHS)
    return [Path(str(p)) for p in raw if str(p).strip()]


def served_path(block: dict[str, Any]) -> Path | None:
    raw = block.get("served_path", SERVED_PATH)
    text = str(raw or "").strip()
    return Path(text) if text else None


def _read_local_json(path: Path) -> dict | None:
    try:
        if not path.is_file():
            return None
        obj = json.loads(path.read_text(encoding="utf-8"))
        return obj if isinstance(obj, dict) else None
    except Exception as exc:  # noqa: BLE001
        print(f"::warning title=cn-prophet-live::local quote file {path} unreadable "
              f"({exc})", flush=True)
        return None


def load_local_quotes(block: dict[str, Any]) -> dict[str, Any] | None:
    """Freshest-wins merge of the VPS plane. None when the host has no plane."""
    try:
        from engine.marketing import live_verify as LV  # noqa: PLC0415
    except Exception:  # noqa: BLE001
        LV = None
    quotes: dict[str, dict] = {}
    asof: str | None = None
    used: list[str] = []
    feed_delay = 0.0
    for path in local_quote_paths(block):
        obj = _read_local_json(path)
        if not obj:
            continue
        q = obj.get("quotes") if isinstance(obj.get("quotes"), dict) else None
        if LV is not None:
            parsed = LV._quotes_from_snapshot(obj)  # noqa: SLF001
            if parsed:
                q = parsed
        if not q:
            continue
        for tkr, row in q.items():
            prev = quotes.get(tkr)
            if prev is None:
                quotes[tkr] = row
                continue
            # freshest-wins: prefer the row with the newer ts_ms
            try:
                a = float((row or {}).get("ts_ms") or 0)
                b = float((prev or {}).get("ts_ms") or 0)
            except (TypeError, ValueError):
                a = b = 0
            if a >= b:
                quotes[tkr] = row
        used.append(path.name)
        try:
            feed_delay = max(feed_delay, float((obj.get("meta") or {}).get("delayed_min") or 0))
        except (TypeError, ValueError):
            pass
        asof = obj.get("asof") or asof
    if not quotes:
        return None
    return {"quotes": quotes, "asof": asof, "source": LOCAL_SOURCE,
            "feed_delay_min": feed_delay, "local_files": used}


def _fill_missing(quotes: dict[str, Any], pack: dict[str, Any] | None,
                  *, now: datetime, delay_min: float) -> tuple[dict[str, Any], int]:
    """Direct Yahoo spark for armed names the plane lacks or serves stale."""
    if not pack or not isinstance(pack.get("names"), dict):
        return quotes, 0
    need: list[str] = []
    for tkr, entry in pack["names"].items():
        if not entry.get("probed"):
            continue
        q = quotes.get(tkr) or {}
        ts = CS._quote_ts(q)  # noqa: SLF001
        age = cn_clock.quote_age_min(ts, now, delay_floor_min=delay_min) if ts else None
        if q.get("price") is None or age is None:
            need.append(tkr)
        elif age > (delay_min + 10.0):
            need.append(tkr)
    need = need[: MAX_FETCH_BATCHES * BATCH_SIZE]
    if not need:
        return quotes, 0
    try:
        from engine.live_quotes import fetch_quotes  # noqa: PLC0415
        fetched = fetch_quotes(need)
    except Exception as exc:  # noqa: BLE001
        print(f"::warning title=cn-prophet-live::fetch_quotes failed ({exc})",
              flush=True)
        return quotes, 0
    n = 0
    for tkr, row in (fetched or {}).items():
        if isinstance(row, dict) and row.get("price") is not None:
            quotes[tkr] = row
            n += 1
    return quotes, n


def publish_served(path: Path, payload: dict[str, Any]) -> bool:
    if os.environ.get("CN_PROPHET_LIVE_NO_PUBLISH", "").strip() not in ("", "0", "false"):
        print("::warning title=cn-prophet-live::CN_PROPHET_LIVE_NO_PUBLISH is set — "
              f"refusing to write {path}", flush=True)
        return False
    parent = path.parent
    if not parent.is_dir():
        print(f"::notice title=cn-prophet-live::{parent} is absent — no VPS live plane",
              flush=True)
        return False
    tmp_name: str | None = None
    try:
        body = json.dumps(payload, allow_nan=False, separators=(",", ":")).encode("utf-8")
        fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=parent)
        with os.fdopen(fd, "wb") as fh:
            fh.write(body)
            fh.flush()
            os.fsync(fh.fileno())
            os.fchmod(fh.fileno(), 0o644)
        os.replace(tmp_name, path)
        tmp_name = None
        print(f"cn-prophet-live served {path} ({len(body)} bytes)", flush=True)
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"::warning title=cn-prophet-live::served copy {path} not written ({exc})",
              flush=True)
        return False
    finally:
        if tmp_name:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass


def load_config(root: Path) -> dict[str, Any]:
    try:
        import yaml  # noqa: PLC0415
        return yaml.safe_load((root / "config.yml").read_text(encoding="utf-8")) or {}
    except Exception as exc:  # noqa: BLE001
        print(f"::warning title=cn-prophet-live::config.yml unreadable ({exc})",
              flush=True)
        return {}


def quote_ager(now: datetime, delay_min: float):
    def _age(q: dict[str, Any]) -> float | None:
        ts = CS._quote_ts(q)  # noqa: SLF001
        return cn_clock.quote_age_min(ts, now, delay_floor_min=delay_min)
    return _age


def run(root: Path, *, now: datetime | None = None, dry_run: bool = False,
        cfg: dict[str, Any] | None = None) -> int:
    ts = now or datetime.now(timezone.utc)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    conf = cfg if cfg is not None else load_config(root)
    lc = LS.live_cfg(conf)
    block = cfg_block(conf)

    if not cn_clock.is_evaluable(ts):
        print(f"::notice title=cn-prophet-live::phase={cn_clock.phase(ts)} "
              f"({ts.strftime('%Y-%m-%dT%H:%MZ')}) — standing down", flush=True)
        return 0

    s3 = r2io.client()
    if s3 is None:
        print("::warning title=cn-prophet-live::no R2 credentials — public read, "
              "no publish this pass", flush=True)

    pack = r2io.get_json(r2io.CN_PACK_KEY, s3=s3)
    prev = r2io.get_json(r2io.CN_LIVE_KEY, s3=s3, allow_public=False)

    try:
        delay_min = float(((conf.get("live") or {}).get("delayed_min")))
    except (TypeError, ValueError):
        delay_min = 15.0

    local = load_local_quotes(block)
    quotes: dict[str, Any] = {}
    source = "fetch"
    asof = None
    if local:
        quotes = dict(local.get("quotes") or {})
        source = str(local.get("source") or LOCAL_SOURCE)
        asof = local.get("asof")
    quotes, n_fetched = _fill_missing(quotes, pack, now=ts, delay_min=delay_min)
    if n_fetched:
        source = f"{source}+spark" if quotes else "spark"

    art = CS.evaluate(pack, quotes, prev, now=ts, cfg=lc,
                      quote_asof=asof, delay_min=delay_min,
                      quote_age_of=quote_ager(ts, delay_min))
    art["quote_source"] = source
    art["liveness"]["source"] = source
    art["meta"]["quote_source"] = source
    art["liveness"]["artifact_written_at"] = None

    m = art.get("meta") or {}
    if art.get("status") == "dark":
        print(f"::warning title=cn-prophet-live::artifact dark ({art.get('reason')}) — "
              f"{m.get('detail') or 'no evaluable pack'}", flush=True)
    else:
        print(f"cn-prophet-live pass={m.get('pass_ts')} phase={art.get('market_phase')} "
              f"pack_as_of={m.get('pack_as_of')} quotes={m.get('quotes_n')} "
              f"src={source} states={m.get('states')} "
              f"coverage={art.get('coverage')}", flush=True)

    events = art.pop("events", [])
    if dry_run:
        print(json.dumps({"artifact_meta": art.get("meta"), "liveness": art.get("liveness"),
                          "events": events}, indent=2, default=str), flush=True)
        return 0

    if s3 is None:
        return 0
    written = datetime.now(timezone.utc)
    art["liveness"]["artifact_written_at"] = written.isoformat(timespec="seconds").replace(
        "+00:00", "Z")
    ok = r2io.put_json(r2io.CN_LIVE_KEY, art, s3=s3)
    dest = served_path(block)
    if dest is not None:
        publish_served(dest, art)
    if events:
        stamp = ts.strftime("%H%M%S")
        r2io.put_json(r2io.events_key(art.get("session") or "unknown", stamp,
                                     prefix=r2io.CN_EVENTS_PREFIX),
                      {"session": art.get("session"), "events": events}, s3=s3)
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--now", default=None)
    p.add_argument("--root", default=_CODE_ROOT)
    args = p.parse_args(argv)
    now = None
    if args.now:
        now = datetime.fromisoformat(args.now.replace("Z", "+00:00"))
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
    return run(Path(args.root), now=now, dry_run=args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
