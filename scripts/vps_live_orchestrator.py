"""Resource-bounded VPS lanes for ephemeral live dashboard computation.

The VPS owns short-lived ``site/live`` products; the Mac/PC nightly runners own
canonical history, revisions, forward ledgers, calibration, and the full render.
Each lane is independently scheduled and locked so a slow full-universe quote pull
cannot block the one-minute publication/fast-price lane.
"""
from __future__ import annotations

import argparse
import fcntl
import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

log = logging.getLogger("vps_live")
ROOT = Path(__file__).resolve().parent.parent


@dataclass
class TaskResult:
    name: str
    status: str
    elapsed_s: float
    returncode: int | None = None
    published: tuple[str, ...] = ()
    detail: str | None = None


def atomic_write_json(path: Path, payload: dict[str, Any], *, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, separators=(",", ":"), ensure_ascii=False)
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
            os.fchmod(fh.fileno(), mode)
        os.replace(tmp_name, path)
    finally:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass


def _valid_json(path: Path) -> bool:
    try:
        json.loads(path.read_text(encoding="utf-8"))
        return path.stat().st_size > 1
    except (OSError, ValueError, TypeError):
        return False


def atomic_publish(source: Path, target: Path, *, mode: int = 0o644) -> None:
    """Publish a complete artifact without exposing an in-progress write."""
    if source.suffix == ".json" and not _valid_json(source):
        raise ValueError(f"refusing invalid JSON artifact: {source}")
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
    try:
        with source.open("rb") as src, os.fdopen(fd, "wb") as dst:
            shutil.copyfileobj(src, dst)
            dst.flush()
            os.fsync(dst.fileno())
            os.fchmod(dst.fileno(), mode)
        os.replace(tmp_name, target)
    finally:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass


def quote_snapshot_error(
    path: Path,
    *,
    min_resolved: int,
    min_coverage: float,
) -> str | None:
    """Return a quality error for an empty/severely degraded quote snapshot."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        meta = payload.get("meta") or {}
        quotes = payload.get("quotes") or {}
        requested = int(meta.get("requested") or 0)
        resolved = int(meta.get("resolved") or 0)
        if not isinstance(quotes, dict) or resolved != len(quotes):
            return "quote snapshot resolved count does not match payload"
        if requested <= 0:
            return "quote snapshot requested no symbols"
        coverage = resolved / requested
        if resolved < min_resolved or coverage < min_coverage:
            return (
                f"quote snapshot quality too low: {resolved}/{requested} "
                f"({coverage:.1%})"
            )
        return None
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        return f"quote snapshot quality check failed: {exc}"


class Orchestrator:
    def __init__(
        self,
        *,
        live_dir: Path,
        state_dir: Path,
        data_dir: Path,
        now: datetime | None = None,
        runner=subprocess.run,
    ) -> None:
        self.live_dir = live_dir
        self.public_dir = (
            live_dir.parent
            if live_dir.name == "live" and live_dir.parent.name == "public"
            else live_dir
        )
        self.state_dir = state_dir
        self.data_dir = data_dir
        self.stage_dir = ROOT / "site" / "live"
        self.now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        self.runner = runner
        self.python = Path(sys.executable)
        self.results: list[TaskResult] = []

    def command(
        self,
        name: str,
        args: list[str],
        *,
        outputs: tuple[tuple[Path, Path], ...] = (),
        timeout: int,
        env: dict[str, str] | None = None,
        validator: Callable[[Path], str | None] | None = None,
    ) -> TaskResult:
        started = time.monotonic()
        merged_env = os.environ.copy()
        merged_env.update(env or {})
        # The first output is the task's required product. Remove only that
        # staging file before launch so a builder which exits 0 without writing
        # cannot make an old checkout artifact look like a fresh success. Keep
        # optional sidecars in place because basket/flow builders use their
        # lastgood files as inputs outside active sessions.
        optional_before: dict[Path, tuple[int, int] | None] = {}
        if outputs:
            try:
                outputs[0][0].unlink(missing_ok=True)
            except OSError as exc:
                result = TaskResult(
                    name,
                    "error",
                    round(time.monotonic() - started, 3),
                    detail=f"could not clear required staging output: {exc}"[:800],
                )
                self.results.append(result)
                return result
            for source, _ in outputs[1:]:
                try:
                    stat = source.stat()
                    optional_before[source] = (stat.st_mtime_ns, stat.st_size)
                except OSError:
                    optional_before[source] = None
        try:
            completed = self.runner(
                args,
                cwd=ROOT,
                env=merged_env,
                text=True,
                capture_output=True,
                timeout=timeout,
                check=False,
            )
            published: list[str] = []
            if completed.returncode == 0:
                required_missing = bool(outputs and not outputs[0][0].is_file())
                validation_error = (
                    validator(outputs[0][0])
                    if validator is not None and not required_missing
                    else None
                )
                if required_missing:
                    status = "failed"
                    detail = f"required output was not produced: {outputs[0][0]}"
                elif validation_error:
                    status = "failed"
                    detail = validation_error
                else:
                    for index, (source, target) in enumerate(outputs):
                        if not source.is_file():
                            continue
                        if index > 0 and optional_before.get(source) is not None:
                            stat = source.stat()
                            if (stat.st_mtime_ns, stat.st_size) == optional_before[source]:
                                continue
                        try:
                            label = str(target.relative_to(self.public_dir))
                            mode = 0o644
                        except ValueError:
                            label = target.name
                            mode = 0o600
                        atomic_publish(source, target, mode=mode)
                        published.append(label)
                    status = "ok"
                    detail = (completed.stdout or "").strip()[-500:] or None
            else:
                status = "failed"
                detail = (completed.stderr or completed.stdout or "").strip()[-800:] or None
            result = TaskResult(
                name,
                status,
                round(time.monotonic() - started, 3),
                returncode=completed.returncode,
                published=tuple(published),
                detail=detail,
            )
        except subprocess.TimeoutExpired:
            result = TaskResult(
                name, "timeout", round(time.monotonic() - started, 3), detail=f">{timeout}s"
            )
        except Exception as exc:  # noqa: BLE001 - one task must not darken the lane
            result = TaskResult(
                name,
                "error",
                round(time.monotonic() - started, 3),
                detail=f"{type(exc).__name__}: {exc}"[:800],
            )
        self.results.append(result)
        log.info("%s: %s (%.2fs)", result.name, result.status, result.elapsed_s)
        return result

    def module(
        self,
        name: str,
        module: str,
        module_args: list[str],
        **kwargs: Any,
    ) -> TaskResult:
        return self.command(
            name, [str(self.python), "-m", module, *module_args], **kwargs
        )

    def _publish_pairs(self, names: tuple[str, ...]) -> tuple[tuple[Path, Path], ...]:
        return tuple((self.stage_dir / name, self.live_dir / name) for name in names)

    def fast(self) -> None:
        """One-minute lane: releases first, then small quote/signal leaves."""
        self.module(
            "release_publications",
            "scripts.watch_release_publications",
            [
                "--out",
                str(self.stage_dir / "release_publications.json"),
                "--state-dir",
                str(self.state_dir),
            ],
            outputs=self._publish_pairs(("release_publications.json",)),
            timeout=60,
        )
        self.module(
            "display_quotes",
            "scripts.build_live_quotes",
            ["--display", "--out", str(self.stage_dir / "quotes.json")],
            outputs=self._publish_pairs(("quotes.json",)),
            timeout=45,
            validator=lambda path: quote_snapshot_error(
                path, min_resolved=5, min_coverage=0.20
            ),
        )

        weekday = self.now.weekday() < 5
        hour, minute = self.now.hour, self.now.minute
        if weekday and 11 <= hour <= 22:
            if minute % 2 == 0:
                self.module(
                    "live_overlay",
                    "scripts.build_live_overlay",
                    [],
                    outputs=self._publish_pairs(("overlay.json",)),
                    timeout=70,
                )
            else:
                self.module(
                    "risk_state",
                    "scripts.build_risk_state",
                    [],
                    outputs=self._publish_pairs(
                        ("risk_state.json", "market_drivers.json", "shock_state.json")
                    ),
                    timeout=90,
                )
                self.module(
                    "turn_notifications",
                    "scripts.notify_turn_events",
                    [],
                    timeout=30,
                    env={
                        "MACRO_LIVE_DIR": str(self.live_dir),
                        "MACRO_NOTIFY_STATE_DIR": str(self.state_dir),
                    },
                )

        if weekday and 1 <= hour < 9 and minute % 2 == 0:
            self.module(
                "china_risk_state",
                "scripts.build_china_risk_state",
                [],
                outputs=self._publish_pairs(("china_risk_state.json",)),
                timeout=70,
            )

        if weekday and 13 <= hour <= 21 and minute % 10 == 7:
            heatmap_stage = self.stage_dir / "sp500_heatmap.json"
            self.module(
                "sp500_heatmap",
                "scripts.build_sp500_heatmap",
                ["--out", str(heatmap_stage)],
                outputs=((heatmap_stage, self.live_dir.parent / "marketdata" / heatmap_stage.name),),
                timeout=100,
            )

    def snapshot(self) -> None:
        """Five-minute, network-heavy full snapshot followed by both basket pulses."""
        snapshot_stage = self.stage_dir / "quotes_full.json"
        snapshot_live = self.state_dir / "quotes_full.json"
        quote_result = self.module(
            "full_quotes",
            "scripts.build_live_quotes",
            ["--out", str(snapshot_stage)],
            outputs=((snapshot_stage, snapshot_live),),
            timeout=230,
            validator=lambda path: quote_snapshot_error(
                path, min_resolved=50, min_coverage=0.10
            ),
        )
        if quote_result.status != "ok" or not snapshot_live.exists():
            return
        for market, filename in (
            ("us", "basket_pulse.json"),
            ("hk", "basket_pulse_hk.json"),
        ):
            args = [
                "--market",
                market,
                "--quotes",
                str(snapshot_live),
                "--out",
                str(self.stage_dir / filename),
            ]
            sidecar = filename.replace(".json", "_lastgood.json")
            self.module(
                f"basket_{market}",
                "scripts.build_basket_pulse",
                args,
                outputs=self._publish_pairs((filename, sidecar)),
                timeout=90,
            )

    def bars(self) -> None:
        """Hourly low-priority bar accrual followed by the site-only flow pulse."""
        intraday_dir = self.data_dir / "intraday"
        bars = self.module(
            "intraday_bars",
            "scripts.build_polygon_intraday",
            ["--lookback-days", "5", "--out-dir", str(intraday_dir)],
            timeout=720,
        )
        if bars.status != "ok":
            return
        self.module(
            "intraday_flow",
            "scripts.build_intraday_flow",
            ["--mode", "fastpath"],
            env={"MACRO_INTRADAY_DIR": str(intraday_dir)},
            outputs=self._publish_pairs(("flow_pulse.json", "flow_pulse_lastgood.json")),
            timeout=180,
        )

    def write_status(self, lane: str, started_at: datetime) -> None:
        lane_payload = {
            "schema": "vps_live_lane.v1",
            "lane": lane,
            "started_at": started_at.isoformat(),
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "ok": all(result.status == "ok" for result in self.results),
            "tasks": [asdict(result) for result in self.results],
        }
        atomic_write_json(self.state_dir / f"status-{lane}.json", lane_payload)
        lanes: dict[str, Any] = {}
        for status_path in sorted(self.state_dir.glob("status-*.json")):
            try:
                row = json.loads(status_path.read_text(encoding="utf-8"))
                # Public health is intentionally terse: stderr/stdout detail stays
                # in the root-only state file/journal where a vendor URL or
                # diagnostic can never leak through /live/.
                lanes[str(row.get("lane") or status_path.stem)] = {
                    "lane": row.get("lane"),
                    "started_at": row.get("started_at"),
                    "finished_at": row.get("finished_at"),
                    "ok": row.get("ok"),
                    "tasks": [
                        {
                            key: task.get(key)
                            for key in (
                                "name",
                                "status",
                                "elapsed_s",
                                "returncode",
                                "published",
                            )
                        }
                        for task in (row.get("tasks") or [])
                    ],
                }
            except (OSError, ValueError, TypeError):
                continue
        atomic_write_json(
            self.live_dir / "orchestrator_status.json",
            {
                "schema": "vps_live_orchestrator.v1",
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "lanes": lanes,
            },
            mode=0o644,
        )


def _lock_lane(state_dir: Path, lane: str):
    state_dir.mkdir(parents=True, exist_ok=True)
    lock_file = (state_dir / f"{lane}.lock").open("a+")
    try:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        lock_file.close()
        return None
    return lock_file


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lane", choices=("fast", "snapshot", "bars"), required=True)
    parser.add_argument(
        "--live-dir",
        default=os.environ.get("MACRO_LIVE_DIR", "/var/lib/macro-live/public/live"),
    )
    parser.add_argument(
        "--state-dir",
        default=os.environ.get("MACRO_LIVE_STATE_DIR", "/var/lib/macro-live/state"),
    )
    parser.add_argument(
        "--data-dir",
        default=os.environ.get("MACRO_LIVE_DATA_DIR", "/var/lib/macro-live/data"),
    )
    parser.add_argument("--now", default=None, help="test override: ISO-8601 UTC timestamp")
    args = parser.parse_args()

    live_dir, state_dir, data_dir = map(
        Path, (args.live_dir, args.state_dir, args.data_dir)
    )
    lock_file = _lock_lane(state_dir, args.lane)
    if lock_file is None:
        log.info("%s lane already active; coalescing timer tick", args.lane)
        return 0
    try:
        live_dir.mkdir(parents=True, exist_ok=True)
        data_dir.mkdir(parents=True, exist_ok=True)
        now = datetime.fromisoformat(args.now) if args.now else None
        if now and now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        started_at = datetime.now(timezone.utc)
        orchestrator = Orchestrator(
            live_dir=live_dir, state_dir=state_dir, data_dir=data_dir, now=now
        )
        getattr(orchestrator, args.lane)()
        orchestrator.write_status(args.lane, started_at)
        return 0 if all(result.status == "ok" for result in orchestrator.results) else 1
    finally:
        lock_file.close()


if __name__ == "__main__":
    raise SystemExit(main())
