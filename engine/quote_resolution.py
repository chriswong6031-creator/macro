"""Neutral, read-only quote waterfall shared by Brain and typed consumers.

The precedence and output vocabulary are the existing Brain contract.  This
module adds only batching: each provider surface is contacted/read at most once
for the unresolved symbols in a call.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
from typing import Iterable
import urllib.parse
import urllib.request


def safe_symbol(symbol: str) -> str:
    """Preserve Brain's established artifact-symbol canonicalization."""
    raw = str(symbol or "").strip().upper()
    prefixed = re.fullmatch(r"(SSE|SHSE|SZSE|HKEX|TSX|TSXV):([A-Z0-9.\-]+)", raw)
    if prefixed:
        exchange, ticker = prefixed.groups()
        suffix = {
            "SSE": "SS",
            "SHSE": "SS",
            "SZSE": "SZ",
            "HKEX": "HK",
            "TSX": "TO",
            "TSXV": "V",
        }[exchange]
        raw = f"{ticker}.{suffix}"
    clean = re.sub(r"[^A-Z0-9.\-]", "", raw)
    clean = re.sub(r"\.{2,}", ".", clean).strip(".")
    if clean.endswith(".SH"):
        clean = clean[:-3] + ".SS"
    if clean.endswith(".HK"):
        stem = clean[:-3]
        if stem.isdigit():
            clean = f"{stem.zfill(4)}.HK"
    return clean[:24]


def _unique_symbols(symbols: Iterable[str]) -> tuple[str, ...]:
    ordered: list[str] = []
    seen: set[str] = set()
    for raw in symbols:
        symbol = safe_symbol(raw)
        if symbol and symbol not in seen:
            ordered.append(symbol)
            seen.add(symbol)
    return tuple(ordered)


def resolve_quotes(
    symbols: Iterable[str],
    terminal_data_dir: Path,
    terminal_hub_url: str,
    root: Path,
) -> dict[str, dict]:
    """Resolve a symbol batch through the frozen hub→full→manifest→site ladder."""
    requested = _unique_symbols(symbols)
    results: dict[str, dict] = {}
    unresolved = set(requested)
    if not requested:
        return results

    # 1. Existing quote-hub batch endpoint.
    try:
        csv = ",".join(requested)
        url = f"{terminal_hub_url.rstrip('/')}/quotes?syms={urllib.parse.quote(csv)}"
        req = urllib.request.Request(url, headers={"User-Agent": "brain-gateway/1.0"})
        with urllib.request.urlopen(req, timeout=3) as resp:
            payload = json.loads(resp.read())
        if not isinstance(payload, dict) or payload.get("error"):
            raise ValueError("hub miss")
        for symbol in requested:
            try:
                row = payload.get(symbol)
                if not isinstance(row, dict) or row.get("last") is None:
                    continue
                if row.get("market") == "us" and not row.get("regularSessionDate"):
                    continue
                ts_s = row.get("ts")
                as_of = None
                if (
                    isinstance(ts_s, (int, float))
                    and not isinstance(ts_s, bool)
                    and ts_s > 0
                ):
                    as_of = datetime.fromtimestamp(
                        ts_s, tz=timezone.utc
                    ).isoformat(timespec="seconds")
                out = {
                    "symbol": symbol,
                    "price": row.get("last"),
                    "prev_close": row.get("prevClose"),
                    "change_pct": row.get("chg"),
                    "as_of": as_of
                    or datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    "live": row.get("live"),
                    "source": "terminal_hub",
                }
                basis = str(row.get("basis") or "")
                basis_delay = re.search(r"(\d+)", basis)
                if basis.upper().startswith("DELAYED") and basis_delay:
                    out["delayed_min"] = int(basis_delay.group(1))
                results[symbol] = {
                    key: value for key, value in out.items() if value is not None
                }
                unresolved.discard(symbol)
            except Exception:  # noqa: BLE001 - one malformed row is a per-symbol miss
                continue
    except Exception:  # noqa: BLE001
        pass

    # 2. Root-side full-universe snapshot, loaded once.
    full_env = os.environ.get("MACRO_QUOTES_FULL_PATH")
    quotes_full_path = (
        Path(full_env)
        if full_env
        else Path(os.environ.get("MACRO_LIVE_STATE_DIR", "/var/lib/macro-live/state"))
        / "quotes_full.json"
    )
    try:
        if unresolved and quotes_full_path.exists():
            snap = json.loads(quotes_full_path.read_text(encoding="utf-8"))
            rows = snap.get("quotes") or {}
            for symbol in requested:
                if symbol not in unresolved:
                    continue
                try:
                    row = rows.get(symbol) or {}
                    if row.get("price") is None:
                        continue
                    as_of = None
                    ts_ms = row.get("ts")
                    if (
                        isinstance(ts_ms, (int, float))
                        and not isinstance(ts_ms, bool)
                        and ts_ms > 0
                    ):
                        as_of = datetime.fromtimestamp(
                            ts_ms / 1000, tz=timezone.utc
                        ).isoformat(timespec="seconds")
                    out = {
                        "symbol": symbol,
                        "price": row.get("price"),
                        "prev_close": row.get("prevClose"),
                        "change_pct": row.get("changePct"),
                        "as_of": as_of or snap.get("asof"),
                        "source": "live_plane_full",
                    }
                    delayed_min = (snap.get("meta") or {}).get("delayed_min")
                    if delayed_min:
                        out["delayed_min"] = delayed_min
                    results[symbol] = {
                        key: value for key, value in out.items() if value is not None
                    }
                    unresolved.discard(symbol)
                except Exception:  # noqa: BLE001 - isolate malformed owner rows
                    continue
    except Exception:  # noqa: BLE001
        pass

    # 3. Terminal manifest fallback, loaded once.
    manifest_path = terminal_data_dir / "manifest.json"
    try:
        if unresolved and manifest_path.exists():
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            rows = manifest.get("symbols") or {}
            for symbol in requested:
                if symbol not in unresolved:
                    continue
                row = rows.get(symbol) or {}
                if not row:
                    continue
                results[symbol] = {
                    "symbol": symbol,
                    "price": row.get("price"),
                    "verdict": row.get("verdict"),
                    "wr": row.get("wr"),
                    "as_of": manifest.get("as_of"),
                    "source": "manifest",
                }
                unresolved.discard(symbol)
    except Exception:  # noqa: BLE001
        pass

    # 4. Display-set site fallback, loaded once.
    quotes_path = root / "site" / "live" / "quotes.json"
    try:
        if unresolved and quotes_path.exists():
            quotes = json.loads(quotes_path.read_text(encoding="utf-8"))
            rows = quotes.get("quotes") or quotes.get("symbols") or {}
            for symbol in requested:
                if symbol not in unresolved:
                    continue
                row = rows.get(symbol) or {}
                if not row:
                    continue
                row_ts = row.get("ts")
                as_of = None
                if isinstance(row_ts, (int, float)) and row_ts > 0:
                    try:
                        as_of = datetime.fromtimestamp(
                            float(row_ts) / 1000.0, tz=timezone.utc
                        ).isoformat(timespec="seconds")
                    except (OverflowError, OSError, ValueError):
                        as_of = None
                results[symbol] = {
                    "symbol": symbol,
                    "price": row.get("price") or row.get("last"),
                    "change_pct": row.get("changePct"),
                    "prev_close": row.get("prevClose"),
                    "as_of": as_of or quotes.get("asof") or quotes.get("as_of"),
                    "source": "site_quotes",
                }
                unresolved.discard(symbol)
    except Exception:  # noqa: BLE001
        pass

    for symbol in requested:
        if symbol in unresolved:
            results[symbol] = {
                "symbol": symbol,
                "available": False,
                "note": "quote not available from any source",
            }
    return results


def resolve_quote(
    symbol: str,
    terminal_data_dir: Path,
    terminal_hub_url: str,
    root: Path,
) -> dict:
    """Single-symbol compatibility facade used by the Brain tool."""
    clean = safe_symbol(symbol)
    if not clean:
        return {"error": "symbol required"}
    return resolve_quotes((clean,), terminal_data_dir, terminal_hub_url, root)[clean]
