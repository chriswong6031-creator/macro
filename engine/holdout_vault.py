"""Holdout Vault — the irreversible, content-hashed out-of-sample data gate (P3).

The sealed final window is the ONE test set a candidate signal may touch only under audit.
Three governance properties the suite's anti-overfit doctrine needs (research/SELF_IMPROVING_AI_SUITE.md):

  1. SEAL — the window's content is hashed at seal time; re-sealing the same id with DIFFERENT
     content is a tamper error. You cannot quietly change the holdout after the fact.
  2. IRREVERSIBLE PEEK LOG — every read is appended to a tamper-evident HASH CHAIN (each record
     carries the hash of the prior one). The number of peeks IS the multiple-testing budget
     spent on the holdout: it can only grow, so "just re-run it" is counted, never free.
  3. RETIREMENT — a hypothesis that has been read (or has failed) can be permanently retired;
     a retired hypothesis can NEVER be peeked again. No restart-the-clock.

Unlike the display-only desks, a vault breach must be LOUD: the write paths raise
``VaultError`` rather than degrading silently. Pure stdlib; append-only JSONL.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

_SEALS = ("data", "vault", "seals.json")
_PEEKLOG = ("data", "vault", "peek_log.jsonl")
_GENESIS = "0" * 64


class VaultError(RuntimeError):
    """A holdout-governance violation (tamper, double-seal mismatch, retired-id peek)."""


def _sha(obj) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, default=str, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class HoldoutVault:
    def __init__(self, root: str | Path | None = None, *, seals=_SEALS, peeklog=_PEEKLOG) -> None:
        base = Path(root) if root is not None else Path(".")
        self.seals_path = base.joinpath(*seals)
        self.peeklog_path = base.joinpath(*peeklog)
        self._seals: dict[str, str] = {}          # window_id -> content hash
        self._head = _GENESIS                      # hash-chain head
        self._records: list[dict] = []
        self._retired: dict[str, str] = {}         # hypothesis_id -> reason
        self._peeks: dict[str, int] = {}           # window_id -> peek count
        self._load()

    # -- load / persist ---------------------------------------------------- #
    def _load(self) -> None:
        try:
            self._seals = json.loads(self.seals_path.read_text())
        except Exception:  # noqa: BLE001
            self._seals = {}
        if not self.peeklog_path.exists():
            return
        for line in self.peeklog_path.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except Exception:  # noqa: BLE001
                continue
            self._records.append(rec)
            self._head = rec.get("record_hash", self._head)
            if rec.get("kind") == "retire":
                self._retired[rec["hypothesis_id"]] = rec.get("reason", "")
            elif rec.get("kind") == "peek":
                self._peeks[rec["window_id"]] = self._peeks.get(rec["window_id"], 0) + 1

    def _write_seals(self) -> None:
        self.seals_path.parent.mkdir(parents=True, exist_ok=True)
        self.seals_path.write_text(json.dumps(self._seals, indent=2, sort_keys=True))

    def _append(self, rec: dict) -> dict:
        rec = {**rec, "ts": _now(), "prev_hash": self._head}
        rec["record_hash"] = _sha({k: rec[k] for k in rec if k != "record_hash"})
        self.peeklog_path.parent.mkdir(parents=True, exist_ok=True)
        with self.peeklog_path.open("a") as fh:
            fh.write(json.dumps(rec, default=str) + "\n")
        self._records.append(rec)
        self._head = rec["record_hash"]
        return rec

    # -- governance API ---------------------------------------------------- #
    def seal(self, window_id: str, content) -> str:
        """Seal a holdout window by content hash. Idempotent for identical content; a re-seal
        with DIFFERENT content raises VaultError (you can't silently swap the holdout)."""
        h = _sha(content)
        prev = self._seals.get(window_id)
        if prev is not None and prev != h:
            raise VaultError(f"window {window_id!r} re-sealed with different content "
                             f"(was {prev[:12]}…, now {h[:12]}…) — holdout tamper")
        self._seals[window_id] = h
        self._write_seals()
        return h

    def is_sealed(self, window_id: str) -> bool:
        return window_id in self._seals

    def is_retired(self, hypothesis_id: str) -> bool:
        return hypothesis_id in self._retired

    def peek_count(self, window_id: str | None = None) -> int:
        """Total peeks (the multiple-testing budget spent on the holdout)."""
        if window_id is None:
            return sum(self._peeks.values())
        return self._peeks.get(window_id, 0)

    def peek(self, hypothesis_id: str, *, window_id: str, result, commit: str | None = None) -> dict:
        """Record an irreversible, chained read of the sealed window for one hypothesis.
        Raises if the window isn't sealed or the hypothesis is retired. Returns the record
        (incl. the running peek count — every peek counts into the family's effective-N)."""
        if window_id not in self._seals:
            raise VaultError(f"window {window_id!r} is not sealed — cannot peek the holdout")
        if hypothesis_id in self._retired:
            raise VaultError(f"hypothesis {hypothesis_id!r} is retired "
                             f"({self._retired[hypothesis_id]}) — no re-peeking the holdout")
        rec = self._append({"kind": "peek", "hypothesis_id": hypothesis_id, "window_id": window_id,
                            "window_hash": self._seals[window_id], "result": result, "commit": commit})
        self._peeks[window_id] = self._peeks.get(window_id, 0) + 1
        return {**rec, "peek_n": self._peeks[window_id]}

    def retire(self, hypothesis_id: str, reason: str = "") -> dict:
        """Permanently retire a hypothesis id (e.g. it failed the holdout). Irreversible."""
        self._retired[hypothesis_id] = reason
        return self._append({"kind": "retire", "hypothesis_id": hypothesis_id, "reason": reason})

    def verify_chain(self) -> bool:
        """Re-walk the peek log and verify the tamper-evident hash chain end to end."""
        head = _GENESIS
        for rec in self._records:
            if rec.get("prev_hash") != head:
                return False
            expect = _sha({k: rec[k] for k in rec if k != "record_hash"})
            if rec.get("record_hash") != expect:
                return False
            head = rec["record_hash"]
        return True


__all__ = ["HoldoutVault", "VaultError"]
