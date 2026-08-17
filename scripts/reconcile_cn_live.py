"""scripts/reconcile_cn_live.py — asia-close CN breathing-platform settlement.

    python -m scripts.reconcile_cn_live --asia [--pack PATH] [--events PATH]
                                        [--close-board PATH] [--standouts PATH]
                                        [--out PATH]

SOLE WRITER of ``data/cn_prophet_live/forward.parquet``. The VPS evaluator
writes R2 only. Keep-first on (date, ticker, kind). Lane-gated: ``CN_LANE=asia``
is required — a render lane must not persist the ledger.

Non-fatal by construction: every failure prints ``::warning`` and returns 0.
The spool is durable in R2; the next asia-close picks the day back up.

Also writes the confirmation receipt (``live_flow/cn_board_confirmation.json``
when R2 is configured; always printed) from the same-session close_board vs
``site/factordata/china_standouts.json``. No receipt after a behind night.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_CODE_ROOT = str(Path(__file__).resolve().parent.parent)
sys.path.insert(0, _CODE_ROOT)

from engine.prophet_live.cn_reconcile import (  # noqa: E402
    FORWARD_SCHEMA,
    confirmation_receipt,
    events_to_rows,
    merge_rows,
)
from lib import cn_calendar  # noqa: E402

LEDGER_REL = Path("data") / "cn_prophet_live" / "forward.parquet"
STANDOUTS_REL = Path("site") / "factordata" / "china_standouts.json"


def _utc(now: datetime | None) -> datetime:
    t = now or datetime.now(timezone.utc)
    return t.replace(tzinfo=timezone.utc) if t.tzinfo is None else t.astimezone(timezone.utc)


def _warn(title: str, msg: str) -> None:
    print(f"::warning title={title}::{msg}", flush=True)


def _load_json(path: Path) -> dict[str, Any] | None:
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        _warn("reconcile_cn_live", f"cannot read {path}: {exc}")
        return None
    return doc if isinstance(doc, dict) else None


def _read_parquet(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        import pandas as pd  # noqa: PLC0415 — optional; CI lane has it
    except ImportError:
        _warn("reconcile_cn_live", "pandas missing — starting from an empty ledger")
        return []
    try:
        return pd.read_parquet(path).to_dict(orient="records")
    except Exception as exc:  # noqa: BLE001
        _warn("reconcile_cn_live", f"cannot read ledger {path}: {exc}")
        return []


def _write_parquet(path: Path, rows: list[dict[str, Any]]) -> None:
    import pandas as pd  # noqa: PLC0415
    path.parent.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame(rows)
    if "schema" not in frame.columns:
        frame["schema"] = FORWARD_SCHEMA
    tmp = path.with_suffix(path.suffix + ".tmp")
    frame.to_parquet(tmp, index=False)
    tmp.replace(path)


def _session(now: datetime) -> str:
    return cn_calendar.expected_last_session(now).isoformat()


def run_asia(*, pack_path: Path | None, events_path: Path | None,
             close_board_path: Path | None, standouts_path: Path,
             out_path: Path, now: datetime) -> int:
    if os.environ.get("CN_LANE") != "asia":
        _warn("reconcile_cn_live", "CN_LANE is not asia — refusing to write the ledger")
        return 0

    session = _session(now)
    events: list[dict[str, Any]] = []
    if events_path is not None:
        doc = _load_json(events_path)
        if doc:
            raw = doc.get("events")
            if isinstance(raw, list):
                events = [e for e in raw if isinstance(e, dict)]
            session = str(doc.get("session") or session)

    confirmed: set[str] = set()
    close_board = None
    if close_board_path is not None:
        artifact = _load_json(close_board_path)
        if artifact:
            close_board = artifact.get("close_board") if isinstance(
                artifact.get("close_board"), dict) else artifact
            if isinstance(close_board, dict):
                lanes = close_board.get("lanes") or {}
                if isinstance(lanes, dict):
                    for rows in lanes.values():
                        if not isinstance(rows, list):
                            continue
                        for row in rows:
                            if isinstance(row, dict) and row.get("ticker"):
                                confirmed.add(str(row["ticker"]))
            session = str(artifact.get("session") or session)

    incoming = events_to_rows(events, session=session, confirmed=confirmed or None)
    existing = _read_parquet(out_path)
    merged = merge_rows(existing, incoming)
    try:
        _write_parquet(out_path, merged)
        print(f"reconcile_cn_live: wrote {len(merged)} rows → {out_path}", flush=True)
    except Exception as exc:  # noqa: BLE001
        _warn("reconcile_cn_live", f"ledger write failed: {exc}")

    standouts = _load_json(standouts_path) if standouts_path.exists() else None
    receipt = confirmation_receipt(
        close_board if isinstance(close_board, dict) else None,
        standouts, session=session, built_at=now,
    )
    if receipt is None:
        print("reconcile_cn_live: no confirmation receipt (behind night or missing board)",
              flush=True)
    else:
        print(json.dumps({
            "receipt": receipt["schema"],
            "as_of": receipt["as_of"],
            "n_confirmed": receipt["n_confirmed"],
            "n_adjusted": receipt["n_adjusted"],
            "n_dropped": receipt["n_dropped"],
            "n_added": receipt["detail"]["n_added"],
        }), flush=True)
        receipt_path = out_path.parent / "cn_board_confirmation.json"
        try:
            receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
        except OSError as exc:
            _warn("reconcile_cn_live", f"receipt write failed: {exc}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("--asia", action="store_true",
                        help="asia-close settlement pass (required in v1)")
    parser.add_argument("--pack", type=Path, default=None)
    parser.add_argument("--events", type=Path, default=None)
    parser.add_argument("--close-board", type=Path, default=None)
    parser.add_argument("--standouts", type=Path, default=STANDOUTS_REL)
    parser.add_argument("--out", type=Path, default=LEDGER_REL)
    parser.add_argument("--now", default=None,
                        help="ISO timestamp; default is wall-clock UTC")
    args = parser.parse_args(argv)
    if not args.asia:
        parser.error("v1 is the asia pass; pass --asia")
    now = _utc(datetime.fromisoformat(args.now.replace("Z", "+00:00")) if args.now
               else None)
    try:
        return run_asia(
            pack_path=args.pack, events_path=args.events,
            close_board_path=args.close_board, standouts_path=args.standouts,
            out_path=args.out, now=now,
        )
    except Exception as exc:  # noqa: BLE001 — never red the asia job
        _warn("reconcile_cn_live", f"unhandled {type(exc).__name__}: {exc}")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
