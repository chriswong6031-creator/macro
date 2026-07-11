"""build_oracle_ratio_lens.py — off-render builder for Oracle Ratio Lens (RL-R13).

Mirrors build_oracle_timemachine.py structure:
- Loads registry + stores
- Calls engine/oracle/ratio_lens.compute()
- Writes site/oracledata/ratio_lens.json atomically (tempfile + os.replace)
- Appends ledger data/oracle/ratio_lens_ledger.jsonl (COLLECT_LANE=nightly gated,
  keep-first per (date, pair_id, event), atomic rewrite)

Runs in the oracle_offrender job AFTER build_oracle_timemachine (RL-R13).

CRITICAL: This is a parquet-reading one-shot — finish with lib.procutil.hard_exit(0)
to avoid Arrow ThreadPool static-destructor deadlock (#2196, pyarrow-oneshot-shutdown-hang).

Never raises: outer try/except, ::warning:: + exit 0.
"""
from __future__ import annotations

import json
import logging
import os
import sys
import tempfile
import time
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lib import config  # noqa: E402
from lib.procutil import hard_exit  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

def _data_dir() -> Path:
    return config.data_dir()


def _out_dir() -> Path:
    d = ROOT / "site" / "oracledata"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _artifact_path() -> Path:
    return _out_dir() / "ratio_lens.json"


def _ledger_path() -> Path:
    p = _data_dir() / "oracle" / "ratio_lens_ledger.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


# ---------------------------------------------------------------------------
# Ledger helpers
# ---------------------------------------------------------------------------

def _ledger_enabled() -> bool:
    """True only when running in nightly engine lane (RL-R13)."""
    return os.environ.get("COLLECT_LANE", "").lower() == "nightly"


def _load_ledger(p: Path) -> list[dict]:
    if not p.exists():
        return []
    rows: list[dict] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def _write_ledger_atomic(rows: list[dict], p: Path) -> None:
    """Write ledger atomically via tempfile + os.replace."""
    p.parent.mkdir(parents=True, exist_ok=True)
    content = "\n".join(json.dumps(r, default=str) for r in rows)
    if content:
        content += "\n"
    fd, tmp = tempfile.mkstemp(dir=p.parent, prefix=".ratio_lens_ledger_tmp_")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(content)
        os.replace(tmp, p)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _load_prior_states(ledger_rows: list[dict]) -> dict[str, str]:
    """Return {pair_id: last_state} from ledger (for transition detection)."""
    prior: dict[str, str] = {}
    for row in ledger_rows:
        pair_id = row.get("pair_id")
        state = row.get("state")
        if pair_id and state:
            prior[pair_id] = state
    return prior


def _stamp_ledger(
    pair_records: list[dict],
    today_str: str,
    ledger_path: Path,
) -> int:
    """Append pair-state transitions + one_sided-shape events.

    Keep-first per (date, pair_id, event). Atomic rewrite.
    Returns count of new rows appended.
    """
    if not _ledger_enabled():
        log.debug("ratio_lens ledger: skipped (COLLECT_LANE != nightly)")
        return 0

    existing = _load_ledger(ledger_path)
    prior_states = _load_prior_states(existing)

    # Existing (date, pair_id, event) keys for idempotency
    seen: set[tuple[str, str, str]] = set()
    for row in existing:
        key = (row.get("date", ""), row.get("pair_id", ""), row.get("event", ""))
        seen.add(key)

    new_rows: list[dict] = []

    for rec in pair_records:
        if "error" in rec:
            continue
        pair_id = rec.get("id", "")
        state = rec.get("state")
        shape_1w = (rec.get("decomp") or {}).get("shape_1w")

        # State transition event
        if state:
            prior = prior_states.get(pair_id)
            if prior != state:
                event = "state_transition"
                key = (today_str, pair_id, event)
                if key not in seen:
                    new_rows.append({
                        "date": today_str,
                        "pair_id": pair_id,
                        "event": event,
                        "state_from": prior,
                        "state": state,
                        "z252": rec.get("z252"),
                        "z63": rec.get("z63"),
                        "pct_3y": rec.get("pct_3y"),
                        "kind": rec.get("kind"),
                    })
                    seen.add(key)

        # One-sided shape event
        if shape_1w == "one_sided":
            event = "one_sided_shape"
            key = (today_str, pair_id, event)
            if key not in seen:
                new_rows.append({
                    "date": today_str,
                    "pair_id": pair_id,
                    "event": event,
                    "shape_1w": shape_1w,
                    "leg_num_ret_1w": (rec.get("legs") or {}).get("num", {}).get("ret_1w"),
                    "leg_den_ret_1w": (rec.get("legs") or {}).get("den", {}).get("ret_1w"),
                    "state": state,
                    "kind": rec.get("kind"),
                })
                seen.add(key)

    if new_rows:
        all_rows = existing + new_rows
        _write_ledger_atomic(all_rows, ledger_path)
        log.info("[ratio_lens] ledger: %d new rows appended", len(new_rows))

    return len(new_rows)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    t0_total = time.time()
    today_str = date.today().isoformat()

    try:
        # [timing] load inputs
        t0 = time.time()
        data_root = _data_dir()
        log.info("[ratio_lens] data_root: %s", data_root)
        log.info("[timing] inputs loaded in %.1fs", time.time() - t0)

        # [timing] compute
        t0 = time.time()
        from engine.oracle.ratio_lens import compute  # noqa: PLC0415
        payload = compute(data_root=data_root, as_of=today_str)
        log.info("[timing] compute() done in %.1fs", time.time() - t0)

        pair_records = payload.get("pairs", [])
        n_ok = sum(1 for r in pair_records if "error" not in r)
        n_err = len(pair_records) - n_ok
        log.info("[ratio_lens] pairs: %d ok, %d errors", n_ok, n_err)

        # [timing] write artifact
        t0 = time.time()
        out_path = _artifact_path()
        raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        fd, tmp = tempfile.mkstemp(dir=out_path.parent, prefix=".ratio_lens_tmp_")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(raw)
            os.replace(tmp, out_path)
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
        log.info("[timing] artifact written (%d bytes) in %.1fs",
                 len(raw.encode("utf-8")), time.time() - t0)
        log.info("[ratio_lens] artifact: %s", out_path)

        # [timing] ledger
        t0 = time.time()
        n_appended = _stamp_ledger(pair_records, today_str, _ledger_path())
        log.info("[timing] ledger in %.1fs (%d new rows)", time.time() - t0, n_appended)

    except Exception as exc:  # noqa: BLE001
        log.error("[ratio_lens] build failed: %s", exc, exc_info=True)
        print(f"::warning::ratio_lens build failed: {exc}", flush=True)

    log.info("[timing] total wall: %.1fs", time.time() - t0_total)
    # CRITICAL: Arrow ThreadPool static-destructor deadlock fix (#2196)
    hard_exit(0)


if __name__ == "__main__":
    main()
