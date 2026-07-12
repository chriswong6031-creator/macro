"""scripts/build_oracle_washout_counterread.py — RC-R11 washout counter-read (Rotation Command W3).

Writes the display artifact site/oracledata/washout_counterread.json (machine feed + the
current chip payload) and appends the append-only, EXPECTED-NULL forward ledger
data/oracle/washout_counterread_ledger.jsonl (one row each time the co-occurrence FIRES —
keep-FIRST per date, atomic write, gated to the nightly lane). Mirrors
scripts/build_oracle_ratio_lens.py exactly.

Registration: research/ORACLE_WASHOUT_COUNTERREAD_REGISTRATION.md (merged before any result
is graded, Constitution §I.3). Display-tier; never ranks/gates/sizes/escalates.

    python -m scripts.build_oracle_washout_counterread
"""
from __future__ import annotations

import json
import logging
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.oracle import washout_counterread as wc  # noqa: E402
from lib import config  # noqa: E402

log = logging.getLogger("build_oracle_washout_counterread")


def _out_dir() -> Path:
    d = config.ROOT / config.load()["storage"]["site_dir"] / "oracledata"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _ledger_path() -> Path:
    p = config.data_dir() / "oracle" / "washout_counterread_ledger.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _ledger_enabled() -> bool:
    """Append only in the nightly engine lane (matches ratio_lens RL-R13)."""
    return os.environ.get("COLLECT_LANE", "").lower() == "nightly"


def _load_ledger(p: Path) -> list[dict]:
    if not p.exists():
        return []
    rows = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def _write_atomic(text: str, p: Path) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=p.parent, prefix=".wc_tmp_")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp, p)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def _stamp_ledger(payload: dict) -> int:
    """Append one FIRING day (keep-first per as_of). Returns rows added (0 or 1)."""
    if not payload.get("show") or not payload.get("as_of"):
        return 0
    p = _ledger_path()
    rows = _load_ledger(p)
    if any(r.get("as_of") == payload["as_of"] for r in rows):
        return 0                                  # keep-first: never overwrite a stamped day
    row = {"as_of": payload["as_of"], "growth_score": payload["growth_score"],
           "growth_band": payload["growth_band"],
           "price_hits": payload.get("price_hits"), "ihm_hits": payload.get("ihm_hits"),
           "note": "expected-null forward accrual — capitulation-zone reading is two-sided"}
    rows.append(row)
    rows.sort(key=lambda r: r.get("as_of") or "")
    _write_atomic("\n".join(json.dumps(r, default=str) for r in rows) + "\n", p)
    return 1


def build() -> dict:
    payload = wc.compute()
    _write_atomic(json.dumps(payload, ensure_ascii=False, indent=1),
                  _out_dir() / "washout_counterread.json")
    added = 0
    if _ledger_enabled():
        added = _stamp_ledger(payload)
    log.info("washout_counterread: show=%s growth=%s price_hits=%s ihm_hits=%s ledger+%d",
             payload.get("show"), payload.get("growth_score"),
             payload.get("price_hits"), payload.get("ihm_hits"), added)
    return {"show": payload.get("show"), "as_of": payload.get("as_of"), "ledger_added": added}


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    try:
        build()
    except Exception as e:  # noqa: BLE001 — additive, never fatal to the nightly
        print(f"::warning::washout_counterread build failed: {e}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
