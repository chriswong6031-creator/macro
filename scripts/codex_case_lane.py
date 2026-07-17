"""scripts/codex_case_lane.py — Winner-case research lane (CRX-R1/R5/R6).

Public API:
    run_once(root=None, dry_run=False) -> dict

Picks the next unwritten winner episode, runs Codex to generate the case
file, applies deterministic + Codex audit, then opens a draft PR.

Budget checks are the LOOP's job; this script does NOT call can_run().
Every run_codex() result is passed to budget.note_result() (guarded).

Exit 0 always (never-raise public interface).
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths (relative to repo root)
# ---------------------------------------------------------------------------

_CASES_DIR_REL = Path("research/winners/cases")
_EPISODES_REL = Path("data/research/winner_episodes.parquet")
_ATTEMPTS_REL = Path("data/codex_lane/case_attempts.jsonl")
_REJECTED_DIR_REL = Path("data/codex_lane/rejected_cases")
_PROMPT_REL = Path("research/winners/CODEX_WINNER_CASE_PROMPT.md")


# ---------------------------------------------------------------------------
# Root resolution
# ---------------------------------------------------------------------------

def _resolve_root(root: Path | str | None) -> Path:
    if root is not None:
        return Path(root)
    return Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# Config helper (guarded import)
# ---------------------------------------------------------------------------

def _load_cfg(root: Path) -> dict:
    try:
        from engine.codex_lane.budget import load_cfg  # noqa: PLC0415
        return load_cfg(root)
    except Exception as exc:  # noqa: BLE001
        log.warning("codex_case_lane: could not load cfg (%s); using defaults", exc)
        return {
            "budget_pct": 85,
            "max_sessions_per_window": 10,
            "session_timeout_min": 25,
            "cases_per_run": 1,
            "case_pr_mode": "draft",
            "codex_model": "",
            "sandbox": "workspace-write",
            "network": True,
        }


# ---------------------------------------------------------------------------
# note_result (guarded)
# ---------------------------------------------------------------------------

def _note_result(run: dict, root: Path) -> None:
    try:
        from engine.codex_lane.budget import note_result  # noqa: PLC0415
        note_result({**run, "lane": "cases"}, root=root)
    except Exception as exc:  # noqa: BLE001
        log.warning("codex_case_lane: note_result failed (%s)", exc)


# ---------------------------------------------------------------------------
# Load the prompt template
# ---------------------------------------------------------------------------

def _load_prompt_template(root: Path) -> str:
    try:
        path = root / _PROMPT_REL
        text = path.read_text(encoding="utf-8")
        # The template says "paste everything below the line".
        # Split on the FIRST full-line horizontal rule (^---+\s*$) so that
        # '---' embedded in YAML blocks or tables cannot truncate the prompt.
        m = re.search(r"^---+\s*$", text, re.MULTILINE)
        if m:
            return text[m.end():].strip()
        return text.strip()
    except Exception as exc:  # noqa: BLE001
        log.warning("codex_case_lane: could not load prompt template (%s)", exc)
        return ""


def _fill_prompt(template: str, ticker: str, year: int) -> str:
    text = template.replace("{{TICKER}}", ticker)
    text = text.replace("{{EPISODE_YEAR}}", str(year))
    return text


# ---------------------------------------------------------------------------
# Attempt ledger helpers
# ---------------------------------------------------------------------------

def _load_attempted_episodes(root: Path) -> set[str]:
    """Return set of 'TICKER_YYYY' keys that should be EXCLUDED from the queue.

    FIX 1 — retryable transient failures:
    Exclusion applies only when an episode has:
      (a) at least one row with status in {"pr_opened", "audit_failed", "generated"}, OR
      (b) >= 3 rows of any status (bounded retry to avoid poison-pill episodes).
    Episodes with only 'skipped' rows below the 3-attempt bound are NOT excluded,
    so transient failures (e.g. codex not installed, timeout) are retryable.
    """
    _TERMINAL_STATUSES = {"pr_opened", "audit_failed", "generated", "pr_exists_closed"}
    # episode -> list of statuses
    ep_rows: dict[str, list[str]] = {}
    path = root / _ATTEMPTS_REL
    if not path.exists():
        return set()
    try:
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                    ep = row.get("episode")
                    status = row.get("status", "")
                    if ep:
                        ep_rows.setdefault(ep, []).append(status)
                except Exception:
                    continue
    except OSError:
        pass

    excluded: set[str] = set()
    for ep, statuses in ep_rows.items():
        # Exclude if any terminal status is present
        if any(s in _TERMINAL_STATUSES for s in statuses):
            excluded.add(ep)
        # Exclude if 3+ attempts of any kind (poison-pill cap)
        elif len(statuses) >= 3:
            excluded.add(ep)
    return excluded


def _append_attempt(root: Path, episode: str, status: str, pr_url: str | None, detail: str) -> None:
    """Append a row to data/codex_lane/case_attempts.jsonl. NEVER raises."""
    try:
        path = root / _ATTEMPTS_REL
        path.parent.mkdir(parents=True, exist_ok=True)
        row = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "episode": episode,
            "status": status,
            "pr_url": pr_url,
            "detail": detail,
        }
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, default=str) + "\n")
    except Exception as exc:  # noqa: BLE001
        log.warning("codex_case_lane: _append_attempt failed (%s)", exc)


# ---------------------------------------------------------------------------
# Episode queue builder
# ---------------------------------------------------------------------------

def _existing_case_keys(root: Path) -> set[str]:
    """Return set of 'TICKER_YYYY' for existing case files."""
    cases_dir = root / _CASES_DIR_REL
    keys: set[str] = set()
    if not cases_dir.exists():
        return keys
    for f in cases_dir.glob("*.md"):
        # e.g. NVDA_2023.md -> NVDA_2023
        keys.add(f.stem)
    return keys


def _ls_remote_case_keys(root: Path) -> set[str]:
    """FIX 4 — Return set of 'TICKER_YYYY' keys for branches already on origin.

    Runs: git ls-remote --heads origin "codex/case-*"
    Parses ref names like refs/heads/codex/case-nvda-2023 -> NVDA_2023.
    Guarded: any failure -> empty set, log warning, NEVER raise.
    """
    keys: set[str] = set()
    try:
        result = subprocess.run(  # noqa: S603
            ["git", "ls-remote", "--heads", "origin", "codex/case-*"],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if result.returncode != 0:
            log.warning("codex_case_lane: ls-remote failed (rc=%d): %s", result.returncode, result.stderr.strip()[:200])
            return keys
        # Each line: <sha>\trefs/heads/codex/case-<ticker>-<year>
        for line in result.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            parts = line.split("\t", 1)
            if len(parts) < 2:
                continue
            ref = parts[1].strip()
            # refs/heads/codex/case-nvda-2023
            prefix = "refs/heads/codex/case-"
            if not ref.startswith(prefix):
                continue
            tail = ref[len(prefix):]  # e.g. "nvda-2023"
            # Last segment is the year (4 digits), everything before is the ticker
            dash_parts = tail.rsplit("-", 1)
            if len(dash_parts) == 2 and dash_parts[1].isdigit() and len(dash_parts[1]) == 4:
                ticker_part = dash_parts[0].upper()
                year_part = dash_parts[1]
                keys.add(f"{ticker_part}_{year_part}")
    except Exception as exc:  # noqa: BLE001
        log.warning("codex_case_lane: _ls_remote_case_keys failed (%s); dedup skipped", exc)
    return keys


def _build_queue(root: Path, track: str = "winner") -> list[dict]:
    """Return episodes ranked per track, excluding existing cases, attempts, and remote branches.

    FIX 10 — two tracks:
      winner: keep outcome_label in {"durable_winner","clean_hold"}, require non-null
              fwd_excess_252d_pp, sort DESC by fwd_excess_252d_pp.
      failed: keep outcome_label in {"failed","blow_off"}, sort DESC by excess_42d_pp
              (biggest run-ups that failed to sustain).

    In both tracks:
      - Exclude tickers matching r'(-USD$)|(_F$)|(^\\^)' (crypto, futures, indices).
      - Exclude rows with outcome_label == "unmatured" (always).
      - Exclude existing cases, attempts-ledger exclusions, remote branches.

    If the needed columns are absent (old parquet), fall back to pre-pass-1 behavior
    (rank by absolute fwd_excess_126d_pp) and log a warning.

    Returns list of dicts: [{ticker, year, excess_val, key, row, outcome_label}]
    """
    import re as _re  # noqa: PLC0415

    # FIX 5 — columns to carry in "row" for episode context injection
    _EPISODE_COLS = ["t0", "sector", "benchmark", "excess_21d_pp", "excess_42d_pp",
                     "dollar_vol_z21", "dv_5_60_ratio", "new_high_63d"]
    _TICKER_EXCLUDE_RE = _re.compile(r"(?:-USD$)|(?:_F$)|(?:^\^)")

    try:
        import pandas as pd  # noqa: PLC0415

        ep_path = root / _EPISODES_REL
        if not ep_path.exists():
            log.warning("codex_case_lane: winner_episodes.parquet absent at %s", ep_path)
            return []

        df = pd.read_parquet(ep_path)
        existing_keys = _existing_case_keys(root)
        attempted_keys = _load_attempted_episodes(root)
        # FIX 4 — also exclude episodes whose branch already exists on remote
        remote_keys = _ls_remote_case_keys(root)
        exclude = existing_keys | attempted_keys | remote_keys

        # Build episode key column
        df["_year"] = pd.to_datetime(df["t0"]).dt.year
        df["_key"] = df["ticker"].astype(str) + "_" + df["_year"].astype(str)

        # Filter out already written / attempted
        df = df[~df["_key"].isin(exclude)].copy()

        if df.empty:
            return []

        # FIX 10 — check for new columns
        _has_outcome_label = "outcome_label" in df.columns
        _has_fwd_252 = "fwd_excess_252d_pp" in df.columns
        _has_excess_42 = "excess_42d_pp" in df.columns

        if not _has_outcome_label:
            log.warning("codex_case_lane: outcome_label column absent (old parquet) — falling back to legacy sort")

        # Always exclude unmatured and non-equity tickers
        if _has_outcome_label:
            df = df[df["outcome_label"] != "unmatured"].copy()
        # Exclude crypto pairs, futures, indices
        df = df[~df["ticker"].astype(str).str.contains(_TICKER_EXCLUDE_RE)].copy()

        if df.empty:
            return []

        if _has_outcome_label:
            # FIX 10 — track-based filtering and sort
            if track == "failed":
                df = df[df["outcome_label"].isin({"failed", "blow_off"})].copy()
                if _has_excess_42:
                    df = df.sort_values("excess_42d_pp", ascending=False, na_position="last")
                    sort_col = "excess_42d_pp"
                else:
                    df["_sort_val"] = 0.0
                    sort_col = None
            else:
                # winner track (default)
                df = df[df["outcome_label"].isin({"durable_winner", "clean_hold"})].copy()
                if _has_fwd_252:
                    df = df[df["fwd_excess_252d_pp"].notna()].copy()
                    df = df.sort_values("fwd_excess_252d_pp", ascending=False, na_position="last")
                    sort_col = "fwd_excess_252d_pp"
                else:
                    # fallback within winner track: use 126d
                    excess_col = None
                    for col in ["fwd_excess_126d_pp", "fwd_excess_63d_pp", "fwd_excess_21d_pp"]:
                        if col in df.columns:
                            excess_col = col
                            break
                    if excess_col:
                        df["_sort_val"] = df[excess_col].abs()
                        df = df.sort_values("_sort_val", ascending=False, na_position="last")
                    sort_col = None
        else:
            # Legacy fallback (no outcome_label column)
            excess_col = None
            for col in ["fwd_excess_126d_pp", "fwd_excess_63d_pp", "fwd_excess_21d_pp"]:
                if col in df.columns:
                    excess_col = col
                    break
            if excess_col is not None:
                df["_sort_val"] = df[excess_col].abs()
            else:
                df["_sort_val"] = 0.0
            df = df.sort_values("_sort_val", ascending=False, na_position="last")
            sort_col = None

        if df.empty:
            return []

        queue = []
        for _, row_ser in df.iterrows():
            try:
                ticker = str(row_ser["ticker"]).strip().upper()
                year = int(row_ser["_year"])

                # Determine excess_val for display
                try:
                    if _has_outcome_label and track == "failed" and _has_excess_42:
                        excess_val = float(row_ser["excess_42d_pp"]) if not _is_nan(row_ser["excess_42d_pp"]) else 0.0
                    elif _has_outcome_label and _has_fwd_252:
                        excess_val = float(row_ser["fwd_excess_252d_pp"]) if not _is_nan(row_ser["fwd_excess_252d_pp"]) else 0.0
                    elif "_sort_val" in row_ser.index:
                        excess_val = float(row_ser["_sort_val"])
                    else:
                        excess_val = 0.0
                except Exception:
                    excess_val = 0.0

                outcome_label = str(row_ser.get("outcome_label", "")) if _has_outcome_label else ""

                # FIX 5 — carry episode context fields
                ep_row: dict = {}
                for col in _EPISODE_COLS:
                    if col in row_ser.index:
                        val = row_ser[col]
                        try:
                            # Convert pandas/numpy types to plain Python for JSON safety
                            import numpy as _np  # noqa: PLC0415
                            if isinstance(val, (_np.integer,)):
                                val = int(val)
                            elif isinstance(val, (_np.floating,)):
                                val = None if (hasattr(val, "__class__") and str(val) in ("nan", "inf", "-inf")) else float(val)
                            elif hasattr(val, "item"):
                                val = val.item()
                            elif hasattr(val, "isoformat"):
                                val = val.isoformat()
                            import math
                            if isinstance(val, float) and not math.isfinite(val):
                                val = None
                        except Exception:
                            val = str(val)
                        ep_row[col] = val
                # FIX 10 — add outcome_label to row context
                ep_row["outcome_label"] = outcome_label
                queue.append({
                    "ticker": ticker,
                    "year": year,
                    "excess_val": excess_val,
                    "key": f"{ticker}_{year}",
                    "row": ep_row,
                    "outcome_label": outcome_label,
                })
            except Exception:
                continue

        return queue

    except Exception as exc:  # noqa: BLE001
        log.warning("codex_case_lane: _build_queue failed (%s)", exc)
        return []


def _is_nan(val: object) -> bool:
    """Return True if val is a float NaN (never raises)."""
    try:
        import math
        return isinstance(val, float) and not math.isfinite(val)
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Deterministic audit
# ---------------------------------------------------------------------------

_REQUIRED_KEYS = [
    "schema", "ticker", "case_type", "episode_year",
    "run_window", "t0_hypothesis", "thesis_one_liner",
    "mechanism", "stage_map", "catalyst_ladder",
    "hazards", "false_positive_checks", "sources",
]


def _deterministic_audit(case_path: Path, ticker: str, year: int, expect_failed: bool = False) -> list[str]:
    """Run deterministic checks on a case file. Returns list of failure strings (empty = pass).

    FIX 11 — extended checks:
    - parse_case_file() succeeds (schema + required keys)
    - ticker/year match filename
    - every catalyst_ladder entry (dict) has non-empty headline (accept 'title' fallback),
      non-empty type, and date whose first 10 chars parse as ISO date.
    - t0_hypothesis parses as ISO date.
    - run_window: accept dict {start,end} or 2-element list; both parse as ISO dates;
      t0_hypothesis must lie within [start, end] inclusive; start year within [year-1, year+1].
    - sources list length >= 2.
    - catalyst_ladder non-empty.
    - case_type track match: expect_failed=True requires case_type=='failed_breakaway';
      expect_failed=False requires case_type != 'failed_breakaway'.
    - Each catalyst_ladder type validated against ALLOWED_CATALYST_TYPES if importable.
    - source_url present on each ladder entry (original check).
    - 'validated' (case-insensitive) absent from file text.
    """
    from datetime import datetime as _dt  # noqa: PLC0415
    failures: list[str] = []
    try:
        from engine.winner_autopsy import parse_case_file  # noqa: PLC0415
    except ImportError:
        failures.append("parse_case_file not importable")
        return failures

    # Parse gate
    try:
        case = parse_case_file(str(case_path))
    except ValueError as exc:
        failures.append(f"parse_case_file failed: {exc}")
        return failures

    # Ticker match
    case_ticker = str(case.get("ticker", "")).strip().upper()
    if case_ticker != ticker.strip().upper():
        failures.append(f"ticker mismatch: file has '{case_ticker}', expected '{ticker}'")

    # Year match
    try:
        case_year = int(case.get("episode_year", 0))
        if case_year != year:
            failures.append(f"episode_year mismatch: file has {case_year}, expected {year}")
    except (TypeError, ValueError):
        failures.append(f"episode_year not parseable: {case.get('episode_year')!r}")

    # FIX 11 — catalyst_ladder non-empty
    ladder = case.get("catalyst_ladder") or []
    if not ladder:
        failures.append("catalyst_ladder is empty")

    # FIX 11 — optionally load allowed catalyst types
    _allowed_catalyst_types: set[str] | None = None
    try:
        import engine.winner_autopsy as _wa  # noqa: PLC0415
        for _attr in dir(_wa):
            if "CATALYST" in _attr.upper() and "TYPE" in _attr.upper():
                _candidate = getattr(_wa, _attr, None)
                if isinstance(_candidate, (set, list, frozenset, tuple)):
                    _allowed_catalyst_types = set(_candidate)
                    break
    except Exception:
        pass

    # FIX 11 — catalyst_ladder entry checks + original source_url
    if isinstance(ladder, list):
        for i, entry in enumerate(ladder):
            if not isinstance(entry, dict):
                continue
            # headline (accept 'title' as fallback)
            headline = entry.get("headline") or entry.get("title") or ""
            if not str(headline).strip():
                failures.append(f"catalyst_ladder[{i}] missing headline/title")
            # type
            ctype = entry.get("type") or ""
            if not str(ctype).strip():
                failures.append(f"catalyst_ladder[{i}] missing type")
            elif _allowed_catalyst_types is not None:
                if str(ctype) not in _allowed_catalyst_types:
                    failures.append(f"catalyst_ladder[{i}] type '{ctype}' not in allowed catalyst types")
            # date: first 10 chars must parse as ISO date
            cdate = entry.get("date") or ""
            try:
                if not str(cdate).strip():
                    failures.append(f"catalyst_ladder[{i}] missing date")
                else:
                    _dt.strptime(str(cdate)[:10], "%Y-%m-%d")
            except (ValueError, TypeError):
                failures.append(f"catalyst_ladder[{i}] date '{cdate}' does not parse as ISO date")
            # source_url (original check, kept)
            url = entry.get("source_url") or entry.get("url") or ""
            if not url:
                failures.append(f"catalyst_ladder[{i}] missing source_url")

    # FIX 11 — t0_hypothesis parses as ISO date
    t0_hyp = case.get("t0_hypothesis") or ""
    t0_dt: "_dt | None" = None
    try:
        if not str(t0_hyp).strip():
            failures.append("t0_hypothesis is empty")
        else:
            t0_dt = _dt.strptime(str(t0_hyp)[:10], "%Y-%m-%d")
    except (ValueError, TypeError):
        failures.append(f"t0_hypothesis '{t0_hyp}' does not parse as ISO date")

    # FIX 11 — run_window: accept dict {start,end} or 2-element list
    rw = case.get("run_window")
    rw_start_dt: "_dt | None" = None
    rw_end_dt: "_dt | None" = None
    if rw is not None:
        try:
            if isinstance(rw, dict):
                rw_start_str = str(rw.get("start", "")).strip()
                rw_end_str = str(rw.get("end", "")).strip()
            elif isinstance(rw, (list, tuple)) and len(rw) >= 2:
                rw_start_str = str(rw[0]).strip()
                rw_end_str = str(rw[1]).strip()
            elif isinstance(rw, str):
                # Accept "YYYY-MM-DD / YYYY-MM-DD" or "YYYY-MM-DD YYYY-MM-DD"
                rw_parts = [p.strip() for p in rw.replace("/", " ").split() if p.strip()]
                rw_start_str = rw_parts[0] if len(rw_parts) >= 1 else ""
                rw_end_str = rw_parts[-1] if len(rw_parts) >= 2 else ""
            else:
                rw_start_str = str(rw).strip()
                rw_end_str = rw_start_str

            if rw_start_str:
                try:
                    rw_start_dt = _dt.strptime(rw_start_str[:10], "%Y-%m-%d")
                except (ValueError, TypeError):
                    failures.append(f"run_window start '{rw_start_str}' does not parse as ISO date")
            if rw_end_str:
                try:
                    rw_end_dt = _dt.strptime(rw_end_str[:10], "%Y-%m-%d")
                except (ValueError, TypeError):
                    failures.append(f"run_window end '{rw_end_str}' does not parse as ISO date")

            # t0_hypothesis must lie within [start, end]
            if rw_start_dt and rw_end_dt and t0_dt:
                if not (rw_start_dt <= t0_dt <= rw_end_dt):
                    failures.append(
                        f"t0_hypothesis {t0_hyp} outside run_window [{rw_start_str}, {rw_end_str}]"
                    )
            # start year within [year-1, year+1]
            if rw_start_dt:
                if not (year - 1 <= rw_start_dt.year <= year + 1):
                    failures.append(
                        f"run_window start year {rw_start_dt.year} outside [{year-1}, {year+1}] for episode_year {year}"
                    )
        except Exception as exc:
            failures.append(f"run_window parse error: {exc}")

    # FIX 11 — sources length >= 2
    sources = case.get("sources") or []
    if len(sources) < 2:
        failures.append(f"sources list has {len(sources)} entries (need >= 2)")

    # FIX 11 — case_type track match
    case_type = case.get("case_type") or ""
    if expect_failed:
        if case_type != "failed_breakaway":
            failures.append(
                f"case_type mismatch: expected 'failed_breakaway' (expect_failed=True), got '{case_type}'"
            )
    else:
        if case_type == "failed_breakaway":
            failures.append(
                "case_type is 'failed_breakaway' but expect_failed=False (this is a winner track case)"
            )

    # Banned word: 'validated' (case-insensitive, word-boundary matched).
    # The token is EXEMPT when:
    #   (a) it is the word 'unvalidated', 'invalidated', or 'non-validated'
    #       (the match is preceded directly by 'un'/'in'/'non-' at a word boundary), OR
    #   (b) a negator token (not|no|never|non) appears immediately before 'validated'
    #       within the same sentence fragment (scanning back up to 60 chars, word boundary).
    # This mirrors check_validated_claims.py's _is_negated() semantics.
    _NEG_BEFORE = re.compile(
        r"\b(not|no|never|non)\b[\w\s,''\-/×&()]{0,55}$",
        re.IGNORECASE,
    )
    _GLUED_NEG = re.compile(r"(?:un|in|non-?)$", re.IGNORECASE)

    def _validated_is_negated(text_before: str) -> bool:
        """Return True if the 'validated' token is negated/hedged."""
        if _GLUED_NEG.search(text_before):
            return True
        tail = text_before[-60:]
        if _NEG_BEFORE.search(tail):
            return True
        return False

    try:
        text = case_path.read_text(encoding="utf-8")
        for m in re.finditer(r"\bvalidated\b", text, re.IGNORECASE):
            text_before = text[:m.start()]
            if not _validated_is_negated(text_before):
                failures.append("contains banned word 'validated' (CI-enforced)")
                break
    except OSError:
        failures.append("could not read case file for banned-word check")

    return failures


# ---------------------------------------------------------------------------
# Codex audit pass
# ---------------------------------------------------------------------------

_AUDIT_CHECKLIST = """\
Audit checklist for a winner_case.v1 file:
1. CONTRACT: fenced ```yaml block parses, schema=winner_case.v1, all required keys present.
2. TAPE: run_window dates plausible; t0_hypothesis is a valid ISO date.
3. EVIDENCE: every catalyst_ladder entry has a source_url and a publication date (not event date).
4. SECTIONS: all ten numbered sections present in the markdown.
5. LANGUAGE: no 'validated' claims; no composite scores; no buy/sell language.
6. NULL_HONESTY: missing data is stated explicitly, not omitted or filled with inference.
7. SOURCES: sources list non-empty; every external claim has a URL.
8. CATALYST_TYPES: each catalyst_ladder type is from the allowed enum.
9. OWNERSHIP: any ownership/insider section is labeled context_only: true.
10. FALSE_POSITIVES: meme_squeeze, one_day_binary, sector_beta, options_mirage keys all present.
"""


def _run_codex_audit(case_text: str, ticker: str, year: int, cfg: dict, root: Path) -> dict:
    """Run a second Codex session to audit the case file. Returns run dict."""
    try:
        from engine.codex_lane.runner import run_codex  # noqa: PLC0415
    except ImportError:
        return {"ok": False, "final_message": "", "error_kind": "not_installed", "events_count": 0, "token_usage": None, "rate_limits": None, "raw_tail": "runner not importable"}

    case_path_hint = f"research/winners/cases/{ticker}_{year}.md"
    audit_prompt = f"""\
You are an independent auditor reviewing a winner autopsy case file for {ticker} ({year}).

{_AUDIT_CHECKLIST}

Review the following case file and return STRICT JSON with this exact shape:
{{"verdict": "PASS" or "FINDINGS", "findings": ["<issue 1>", ...]}}

If the case passes all checks, return: {{"verdict": "PASS", "findings": []}}
If there are issues, return: {{"verdict": "FINDINGS", "findings": ["<detailed issue>", ...]}}

Do NOT return any other text outside the JSON block.

Full file on disk (read-only): {case_path_hint}
(If the inlined copy below appears truncated, read the full file from that path.)

=== CASE FILE CONTENT ===
{case_text[:60000]}
"""
    timeout_s = int(cfg.get("session_timeout_min", 25)) * 60
    model = cfg.get("codex_model", "") or ""
    # FIX 3 — audit session is read-only (must not modify the workspace)
    sandbox = "read-only"
    network = False

    return run_codex(
        audit_prompt,
        cwd=str(root),
        timeout_s=timeout_s,
        model=model,
        sandbox=sandbox,
        network=network,
    )


def _parse_audit_verdict(final_message: str) -> tuple[str, list[str]]:
    """Parse the audit JSON from the Codex final message. Returns (verdict, findings)."""
    if not final_message:
        return "FINDINGS", ["audit returned empty response"]

    # Find JSON object in the message
    text = final_message.strip()
    # Try to find first { ... } block
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end <= start:
        return "FINDINGS", [f"audit response not parseable as JSON: {text[:200]}"]

    try:
        obj = json.loads(text[start:end + 1])
        verdict = str(obj.get("verdict", "FINDINGS")).upper()
        findings = [str(f) for f in (obj.get("findings") or [])]
        return verdict, findings
    except json.JSONDecodeError:
        return "FINDINGS", [f"audit JSON parse failed: {text[:200]}"]


# ---------------------------------------------------------------------------
# Fix session
# ---------------------------------------------------------------------------

def _run_codex_fix(case_text: str, findings: list[str], ticker: str, year: int, cfg: dict, root: Path) -> dict:
    """Run a Codex fix session given audit findings. Returns run dict."""
    try:
        from engine.codex_lane.runner import run_codex  # noqa: PLC0415
    except ImportError:
        return {"ok": False, "final_message": "", "error_kind": "not_installed", "events_count": 0, "token_usage": None, "rate_limits": None, "raw_tail": "runner not importable"}

    case_path_hint = f"research/winners/cases/{ticker}_{year}.md"
    findings_text = "\n".join(f"- {f}" for f in findings)
    fix_prompt = f"""\
You previously generated a winner autopsy case file for {ticker} ({year}).
An audit found the following issues that must be fixed:

{findings_text}

Here is the current case file content:
=== CASE FILE ===
{case_text[:60000]}
=================

Full file on disk: {case_path_hint}
(If the inlined copy above appears truncated, read the full file from that path first.)

Please provide the complete corrected case file. Write ONLY the markdown content
(no preamble), ending with the fenced ```yaml winner_case.v1 block.

Also write the corrected file to: {case_path_hint}
"""
    timeout_s = int(cfg.get("session_timeout_min", 25)) * 60
    model = cfg.get("codex_model", "") or ""
    sandbox = cfg.get("sandbox", "workspace-write")
    network = bool(cfg.get("network", True))

    return run_codex(
        fix_prompt,
        cwd=str(root),
        timeout_s=timeout_s,
        model=model,
        sandbox=sandbox,
        network=network,
    )


# ---------------------------------------------------------------------------
# Fallback: extract case content from final_message
# ---------------------------------------------------------------------------

def _extract_case_from_message(message: str) -> str | None:
    """Try to extract a winner_case.v1 block from a Codex final message.

    The brief says: if the file doesn't exist but final_message contains a
    winner_case.v1 block, write final_message verbatim to the case path.
    """
    if "winner_case.v1" in message:
        return message
    return None


# ---------------------------------------------------------------------------
# Git / PR helpers
# ---------------------------------------------------------------------------

def _git_run(args: list[str], root: Path, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(  # noqa: S603
        ["git"] + args,
        cwd=str(root),
        capture_output=True,
        text=True,
        check=check,
    )


def _open_pr(root: Path, ticker: str, year: int, case_path: Path, audit_summary: str, draft: bool) -> str | None:
    """Create branch + commit + push + gh pr create via a throwaway git worktree.

    Uses a temporary worktree so the CALLER's HEAD is NEVER touched.
    Every step is error-tolerated; on failure the case file is NOT lost (already written).
    NEVER touches main or the caller's checkout.
    """
    branch = f"codex/case-{ticker.lower()}-{year}"
    pr_url: str | None = None
    tmpdir: str | None = None

    try:
        tmpdir = tempfile.mkdtemp(prefix="codex-case-pr-")

        # 1. Fetch latest origin/main so worktree starts from it
        subprocess.run(  # noqa: S603
            ["git", "-C", str(root), "fetch", "origin", "main"],
            capture_output=True, text=True, check=False,
        )

        # 2. Add a detached worktree at origin/main
        wt_add = subprocess.run(  # noqa: S603
            ["git", "-C", str(root), "worktree", "add", "--detach", tmpdir, "origin/main"],
            capture_output=True, text=True,
        )
        if wt_add.returncode != 0:
            log.warning("codex_case_lane: worktree add failed (%s); skipping PR", wt_add.stderr.strip())
            return None

        # 3. Create branch inside the throwaway worktree
        br = subprocess.run(  # noqa: S603
            ["git", "-C", tmpdir, "checkout", "-b", branch],
            capture_output=True, text=True,
        )
        if br.returncode != 0:
            log.warning("codex_case_lane: checkout -b failed (%s); skipping PR", br.stderr.strip())
            return None

        # 4. Copy the case file into the worktree at the same relative path
        try:
            case_rel = case_path.relative_to(root)
        except ValueError:
            log.warning("codex_case_lane: case_path not relative to root; skipping PR")
            return None
        dest = Path(tmpdir) / case_rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(case_path), str(dest))

        # 5. Stage ONLY the case file
        add_r = subprocess.run(  # noqa: S603
            ["git", "-C", tmpdir, "add", str(case_rel)],
            capture_output=True, text=True,
        )
        if add_r.returncode != 0:
            log.warning("codex_case_lane: git add failed (%s); skipping PR", add_r.stderr.strip())
            return None

        # 6. Commit with fixed bot identity
        msg = f"feat(case): add winner autopsy {ticker} {year}\n\nGenerated and audited by codex_case_lane."
        commit_r = subprocess.run(  # noqa: S603
            [
                "git", "-C", tmpdir,
                "-c", "user.name=dashboard-bot",
                "-c", "user.email=actions@users.noreply.github.com",
                "commit", "-m", msg,
            ],
            capture_output=True, text=True,
        )
        if commit_r.returncode != 0:
            log.warning("codex_case_lane: commit failed (%s); skipping PR", commit_r.stderr.strip())
            return None

        # 7. Push the branch — FIX 5(a): retry with --force-with-lease on first failure
        push_r = subprocess.run(  # noqa: S603
            ["git", "-C", tmpdir, "push", "origin", branch],
            capture_output=True, text=True,
        )
        if push_r.returncode != 0:
            log.warning("codex_case_lane: push failed (%s); retrying with --force-with-lease", push_r.stderr.strip())
            push_r2 = subprocess.run(  # noqa: S603
                ["git", "-C", tmpdir, "push", "--force-with-lease", "origin", branch],
                capture_output=True, text=True,
            )
            if push_r2.returncode != 0:
                log.warning("codex_case_lane: force-with-lease push also failed (%s); checking for existing PR", push_r2.stderr.strip())
                # FIX 5(a): even if push fails, check if PR already exists
                try:
                    reuse_r = subprocess.run(  # noqa: S603
                        ["gh", "pr", "list", "--head", branch, "--state", "open", "--json", "url", "--jq", ".[0].url"],
                        cwd=str(root),
                        capture_output=True, text=True, timeout=30,
                    )
                    existing_url = reuse_r.stdout.strip()
                    if existing_url and existing_url.startswith("https://"):
                        log.info("codex_case_lane: reusing existing PR %s", existing_url)
                        return existing_url
                except Exception as exc:  # noqa: BLE001
                    log.warning("codex_case_lane: PR reuse check failed (%s)", exc)
                return None

        # 8. Open the PR via gh (run with cwd=tmpdir)
        try:
            # FIX A(c): check for an existing open PR before creating (using token fallback env)
            _gh_env_base = dict(os.environ)
            _gh_fallback = os.environ.get("GH_TOKEN_FALLBACK", "")
            try:
                reuse_r = subprocess.run(  # noqa: S603
                    ["gh", "pr", "list", "--head", branch, "--state", "open", "--json", "url", "--jq", ".[0].url"],
                    cwd=str(root),
                    capture_output=True, text=True, timeout=30,
                    env=_gh_env_base,
                )
                existing_url = reuse_r.stdout.strip()
                if existing_url and existing_url.startswith("https://"):
                    log.info("codex_case_lane: PR already exists at %s; skipping create", existing_url)
                    pr_url = existing_url
                    return pr_url  # skip push+create
                # Also try with fallback token if present
                if reuse_r.returncode != 0 and _gh_fallback and _gh_fallback != _gh_env_base.get("GH_TOKEN", ""):
                    reuse_r2 = subprocess.run(  # noqa: S603
                        ["gh", "pr", "list", "--head", branch, "--state", "open", "--json", "url", "--jq", ".[0].url"],
                        cwd=str(root),
                        capture_output=True, text=True, timeout=30,
                        env={**_gh_env_base, "GH_TOKEN": _gh_fallback},
                    )
                    existing_url2 = reuse_r2.stdout.strip()
                    if existing_url2 and existing_url2.startswith("https://"):
                        log.info("codex_case_lane: PR already exists at %s (found via fallback token); skipping create", existing_url2)
                        pr_url = existing_url2
                        return pr_url
            except Exception as exc:  # noqa: BLE001
                log.warning("codex_case_lane: PR existence check failed (%s); proceeding with create", exc)

            body = (
                f"## Winner autopsy: {ticker} {year}\n\n"
                f"Generated by `codex_case_lane`. Audit summary:\n\n"
                f"{audit_summary}\n\n"
                f"**Merge authority: operator / babysitter only (CRX-R6).**"
            )
            gh_cmd = [
                "gh", "pr", "create",
                "--title", f"feat(case): winner autopsy {ticker} {year}",
                "--body", body,
                "--head", branch,
                "--base", "main",
            ]
            if draft:
                gh_cmd.append("--draft")

            # FIX A(a): attempt 1 — primary token
            result = subprocess.run(  # noqa: S603
                gh_cmd,
                cwd=tmpdir,
                capture_output=True,
                text=True,
                env=_gh_env_base,
            )
            if result.returncode != 0:
                log.warning(
                    "codex_case_lane: gh pr create failed rc=%d: %s",
                    result.returncode,
                    (result.stderr + result.stdout)[-500:],
                )
                # FIX A(b): attempt 2 — fallback token if present and different
                if _gh_fallback and _gh_fallback != _gh_env_base.get("GH_TOKEN", ""):
                    log.info("codex_case_lane: retrying gh pr create with GH_TOKEN_FALLBACK")
                    result2 = subprocess.run(  # noqa: S603
                        gh_cmd,
                        cwd=tmpdir,
                        capture_output=True,
                        text=True,
                        env={**_gh_env_base, "GH_TOKEN": _gh_fallback},
                    )
                    if result2.returncode == 0:
                        log.info("codex_case_lane: gh pr create succeeded on fallback token attempt")
                        result = result2
                    else:
                        log.warning(
                            "codex_case_lane: gh pr create fallback attempt also failed rc=%d: %s",
                            result2.returncode,
                            (result2.stderr + result2.stdout)[-500:],
                        )
            # Extract PR URL from whichever attempt succeeded
            for line in (result.stdout + result.stderr).splitlines():
                line = line.strip()
                if line.startswith("https://github.com") and "/pull/" in line:
                    pr_url = line
                    break
            if not pr_url and result.returncode == 0:
                pr_url = result.stdout.strip()
        except Exception as exc:  # noqa: BLE001
            log.warning("codex_case_lane: gh pr create failed (%s)", exc)

    except Exception as exc:  # noqa: BLE001
        log.warning("codex_case_lane: _open_pr unexpected error (%s); case file is safe", exc)

    finally:
        # Always clean up the throwaway worktree
        if tmpdir is not None:
            try:
                subprocess.run(  # noqa: S603
                    ["git", "-C", str(root), "worktree", "remove", "--force", tmpdir],
                    capture_output=True, text=True, check=False,
                )
            except Exception:  # noqa: BLE001
                pass
            try:
                shutil.rmtree(tmpdir, ignore_errors=True)
            except Exception:  # noqa: BLE001
                pass
            try:
                subprocess.run(  # noqa: S603
                    ["git", "-C", str(root), "worktree", "prune"],
                    capture_output=True, text=True, check=False,
                )
            except Exception:  # noqa: BLE001
                pass

    return pr_url


# ---------------------------------------------------------------------------
# Main run_once
# ---------------------------------------------------------------------------

def _gh_pr_list_head(branch: str, root: Path, fallback_token: str | None = None) -> str | None:
    """Run `gh pr list --head <branch> --state all` and return the first URL or None.

    Tries primary GH_TOKEN first; if fallback_token is set and differs, retries with it.
    NEVER raises.
    """
    url, _state = _gh_pr_list_head_with_state(branch, root, fallback_token=fallback_token)
    return url


def _gh_pr_list_head_with_state(branch: str, root: Path, fallback_token: str | None = None) -> tuple[str | None, str | None]:
    """Run `gh pr list --head <branch> --state all` and return (url, state) of the first PR, or (None, None).

    state is one of "OPEN", "MERGED", "CLOSED" (GitHub GraphQL enum values) or None if no PR.
    Tries primary GH_TOKEN first; if fallback_token is set and differs, retries with it.
    NEVER raises.
    """
    cmd = ["gh", "pr", "list", "--head", branch, "--state", "all", "--json", "url,state"]
    _env_base = dict(os.environ)
    for attempt_env in ([_env_base] + ([{**_env_base, "GH_TOKEN": fallback_token}] if fallback_token and fallback_token != _env_base.get("GH_TOKEN", "") else [])):
        try:
            r = subprocess.run(  # noqa: S603
                cmd, cwd=str(root), capture_output=True, text=True, timeout=30, env=attempt_env,
            )
            raw = r.stdout.strip()
            if raw:
                try:
                    items = json.loads(raw)
                    if items:
                        first = items[0]
                        url = first.get("url", "")
                        state = first.get("state", "")
                        if url and url.startswith("https://"):
                            return url, state or None
                except Exception:  # noqa: BLE001
                    # jq-style plain URL fallback (old gh versions)
                    if raw.startswith("https://"):
                        return raw, None
        except Exception as exc:  # noqa: BLE001
            log.warning("codex_case_lane: _gh_pr_list_head_with_state failed (%s)", exc)
    return None, None


def _pr_recovery_sweep(root: Path, cfg: dict) -> None:
    """FIX B — Recovery sweep: for each remote codex/case-* branch with no pr_opened row,
    attempt gh pr create (capped at 3 branches per run). NEVER raises.

    Three sub-cases for each stranded branch:
    (a) gh pr list finds an existing PR (open/merged/closed) but ledger lacks a pr_opened-with-url row
        → append a backfill row (detail "ledger backfill from existing PR"), no create call.
    (b) gh pr list finds nothing → attempt gh pr create, append pr_opened on success.
    (c) Any failure → log and continue.
    """
    try:
        _fallback = os.environ.get("GH_TOKEN_FALLBACK", "") or None

        # Load ledger: track pr_opened-with-url episodes, pr_exists_closed episodes,
        # and total row counts per episode (for the cross-run bound).
        _pr_opened_with_url: set[str] = set()
        _pr_exists_closed: set[str] = set()
        _ep_row_counts: dict[str, int] = {}
        path = root / _ATTEMPTS_REL
        if path.exists():
            try:
                with path.open(encoding="utf-8") as fh:
                    for line in fh:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            row = json.loads(line)
                            ep = row.get("episode")
                            if not ep:
                                continue
                            _ep_row_counts[ep] = _ep_row_counts.get(ep, 0) + 1
                            status = row.get("status", "")
                            if status == "pr_opened" and row.get("pr_url"):
                                _pr_opened_with_url.add(ep)
                            if status == "pr_exists_closed":
                                _pr_exists_closed.add(ep)
                        except Exception:
                            continue
            except OSError:
                pass

        # List remote codex/case-* branches
        ls_r = subprocess.run(  # noqa: S603
            ["git", "ls-remote", "--heads", "origin", "codex/case-*"],
            cwd=str(root), capture_output=True, text=True, timeout=30, check=False,
        )
        if ls_r.returncode != 0:
            log.warning("codex_case_lane: recovery sweep ls-remote failed (rc=%d)", ls_r.returncode)
            return

        branches: list[str] = []
        for line in ls_r.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            parts = line.split("\t", 1)
            if len(parts) < 2:
                continue
            ref = parts[1].strip()
            prefix = "refs/heads/"
            if ref.startswith(prefix):
                branches.append(ref[len(prefix):])

        draft = cfg.get("case_pr_mode", "draft") == "draft"
        sweep_count = 0

        for branch in branches:
            if sweep_count >= 3:
                break

            # Derive episode key from branch name: codex/case-nvda-2023 -> NVDA_2023
            branch_tail = branch
            if branch_tail.startswith("codex/case-"):
                branch_tail = branch_tail[len("codex/case-"):]
            dash_parts = branch_tail.rsplit("-", 1)
            if len(dash_parts) != 2 or not dash_parts[1].isdigit() or len(dash_parts[1]) != 4:
                continue
            ticker_raw = dash_parts[0].upper()
            year_raw = int(dash_parts[1])
            episode_key = f"{ticker_raw}_{year_raw}"

            # Skip if already have a good pr_opened row or operator-rejected (pr_exists_closed)
            if episode_key in _pr_opened_with_url or episode_key in _pr_exists_closed:
                continue

            # Finding 3: skip if episode has >= 3 ledger rows (cross-run bound)
            if _ep_row_counts.get(episode_key, 0) >= 3:
                log.info("codex_case_lane: recovery sweep: episode %s has >= 3 ledger rows; skipping", episode_key)
                continue

            sweep_count += 1

            # Check if a PR already exists for this branch (with state, for Finding 4)
            existing_url, pr_state = _gh_pr_list_head_with_state(branch, root, fallback_token=_fallback)

            if existing_url:
                # Finding 4: differentiate CLOSED (operator-rejected) from OPEN/MERGED
                if pr_state and pr_state.upper() == "CLOSED":
                    log.info(
                        "codex_case_lane: recovery sweep: PR for %s is CLOSED (operator-rejected) at %s; "
                        "marking terminal", branch, existing_url,
                    )
                    _append_attempt(
                        root, episode_key, "pr_exists_closed", None,
                        f"operator-rejected PR at {existing_url}",
                    )
                    _pr_exists_closed.add(episode_key)
                else:
                    # OPEN or MERGED — backfill the ledger
                    state_note = f" (state={pr_state})" if pr_state else ""
                    log.info(
                        "codex_case_lane: recovery sweep: PR exists for %s at %s%s; backfilling ledger",
                        branch, existing_url, state_note,
                    )
                    _append_attempt(
                        root, episode_key, "pr_opened", existing_url,
                        f"ledger backfill from existing PR{state_note}",
                    )
                    _pr_opened_with_url.add(episode_key)
                continue

            # No existing PR — try to create one
            log.info("codex_case_lane: recovery sweep: no PR found for %s; attempting gh pr create", branch)
            gh_cmd = [
                "gh", "pr", "create",
                "--title", f"feat(case): winner autopsy {ticker_raw} {year_raw}",
                "--body", f"## Winner autopsy: {ticker_raw} {year_raw}\n\nRecovered by PR sweep in `codex_case_lane` (branch was pushed but PR was not opened).\n\n**Merge authority: operator / babysitter only (CRX-R6).**",
                "--head", branch,
                "--base", "main",
            ]
            if draft:
                gh_cmd.append("--draft")

            _env_base = dict(os.environ)
            _envs = [_env_base]
            if _fallback and _fallback != _env_base.get("GH_TOKEN", ""):
                _envs.append({**_env_base, "GH_TOKEN": _fallback})

            created_url: str | None = None
            create_failed = False
            for attempt_env in _envs:
                try:
                    cr = subprocess.run(  # noqa: S603
                        gh_cmd, cwd=str(root), capture_output=True, text=True, timeout=60, env=attempt_env,
                    )
                    if cr.returncode == 0:
                        url_candidate = ""
                        for out_line in (cr.stdout + cr.stderr).splitlines():
                            out_line = out_line.strip()
                            if out_line.startswith("https://github.com") and "/pull/" in out_line:
                                url_candidate = out_line
                                break
                        if not url_candidate and cr.returncode == 0:
                            url_candidate = cr.stdout.strip()
                        if url_candidate and url_candidate.startswith("https://"):
                            created_url = url_candidate
                            log.info("codex_case_lane: recovery sweep: created PR %s for %s", created_url, branch)
                            break
                    else:
                        create_failed = True
                        log.warning("codex_case_lane: recovery sweep: gh pr create failed rc=%d for %s: %s",
                                    cr.returncode, branch, (cr.stderr + cr.stdout)[-300:])
                except Exception as exc:  # noqa: BLE001
                    create_failed = True
                    log.warning("codex_case_lane: recovery sweep: gh pr create exception for %s: %s", branch, exc)

            if created_url:
                _append_attempt(root, episode_key, "pr_opened", created_url, "recovered by PR sweep")
                _pr_opened_with_url.add(episode_key)
            elif create_failed:
                # Finding 3: record failure so cross-run bound accrues
                _append_attempt(
                    root, episode_key, "pr_create_failed", None,
                    "recovery sweep create failed",
                )
                _ep_row_counts[episode_key] = _ep_row_counts.get(episode_key, 0) + 1

    except Exception as exc:  # noqa: BLE001
        log.warning("codex_case_lane: _pr_recovery_sweep unexpected error (%s); continuing", exc)


def _count_pr_opened(root: Path) -> int:
    """Count case_attempts.jsonl rows with status='pr_opened'. NEVER raises."""
    try:
        path = root / _ATTEMPTS_REL
        if not path.exists():
            return 0
        count = 0
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                    if row.get("status") == "pr_opened":
                        count += 1
                except Exception:
                    continue
        return count
    except Exception:
        return 0


def run_once(root: Path | str | None = None, dry_run: bool = False) -> dict:
    """Run one iteration of the case lane.

    FIX 10 — failed-track cadence:
    Count pr_opened rows; if count % 4 == 3 use track="failed", else "winner".
    If chosen track's queue is empty, fall back to other track.

    FIX 12 — prior-case context line appended after EPISODE CONTEXT block.

    FIX 13 — worktree_guard wraps GENERATION and FIX codex sessions.

    Returns dict: {ok, action, detail, episode, pr_url}.
    NEVER raises.
    """
    # FIX 13 — guarded import of worktree_guard
    _wg_snapshot = None
    _wg_restore = None
    _wg_protect: list[str] = []
    try:
        from engine.codex_lane.worktree_guard import snapshot as _snap, restore as _rest, DEFAULT_PROTECT  # noqa: PLC0415
        _wg_snapshot = _snap
        _wg_restore = _rest
        _wg_protect = list(DEFAULT_PROTECT)
    except Exception as exc:  # noqa: BLE001
        log.info("codex_case_lane: worktree_guard not importable (%s); proceeding without guard", exc)

    try:
        r = _resolve_root(root)
        cfg = _load_cfg(r)

        # FIX B — PR recovery sweep (before queue build; skip in dry_run)
        if not dry_run:
            _pr_recovery_sweep(r, cfg)

        # FIX 10 — track cadence
        pr_opened_count = _count_pr_opened(r)
        use_failed = (pr_opened_count % 4) == 3

        primary_track = "failed" if use_failed else "winner"
        fallback_track = "winner" if use_failed else "failed"

        queue = _build_queue(r, track=primary_track)
        active_track = primary_track
        if not queue:
            log.info("codex_case_lane: queue empty for track=%s; trying fallback track=%s", primary_track, fallback_track)
            queue = _build_queue(r, track=fallback_track)
            active_track = fallback_track

        if not queue:
            log.info("codex_case_lane: no uncased episodes available; nothing to do")
            return {"ok": True, "action": "skip", "detail": "no uncased episodes", "episode": None, "pr_url": None}

        # Take top 1 (cases_per_run = 1 per spec)
        ep = queue[0]
        ticker = ep["ticker"]
        year = ep["year"]
        episode_key = ep["key"]
        case_path = r / _CASES_DIR_REL / f"{ticker}_{year}.md"
        expect_failed = (active_track == "failed")

        log.info("codex_case_lane: targeting episode %s (track=%s)", episode_key, active_track)

        # 2. Fill prompt template
        template = _load_prompt_template(r)
        if not template:
            _append_attempt(r, episode_key, "skipped", None, "prompt template absent")
            return {"ok": False, "action": "skip", "detail": "prompt template absent", "episode": episode_key, "pr_url": None}

        prompt = _fill_prompt(template, ticker, year)

        # FIX 5(b) — episode context injection
        try:
            ep_row = ep.get("row", {})
            ctx_lines = ["", "EPISODE CONTEXT (from data/research/winner_episodes.parquet — real computed stats; use them)"]
            _float_cols = {"excess_21d_pp", "excess_42d_pp", "dollar_vol_z21", "dv_5_60_ratio"}
            for fld in ["t0", "sector", "benchmark", "excess_21d_pp", "excess_42d_pp",
                        "dollar_vol_z21", "dv_5_60_ratio", "new_high_63d"]:
                if fld in ep_row and ep_row[fld] is not None:
                    val = ep_row[fld]
                    if fld in _float_cols and isinstance(val, float):
                        ctx_lines.append(f"  {fld}: {val:.2f}")
                    else:
                        ctx_lines.append(f"  {fld}: {val}")
            prompt += "\n".join(ctx_lines)
        except Exception:  # noqa: BLE001
            pass

        # FIX 12 — prior-case context line
        try:
            existing_keys_sorted = sorted(_existing_case_keys(r))
            _cap = 60
            if existing_keys_sorted:
                displayed = existing_keys_sorted[:_cap]
                overflow = len(existing_keys_sorted) - len(displayed)
                keys_str = ", ".join(displayed)
                if overflow > 0:
                    keys_str += f" (+{overflow} more)"
                prompt += f"\n\nAlready-cased episodes (context only — the queue already excludes them): {keys_str}"
        except Exception:  # noqa: BLE001
            pass

        # FIX 5(b) — price-store availability note (guarded)
        try:
            price_store = r / "data" / "massive_stock_day"
            store_note_lines: list[str] = [""]
            if not price_store.exists() or len(list(price_store.iterdir())) < 100:
                store_note_lines.append("NOTE: data/massive_stock_day is unavailable or thin in this checkout.")
                codex_ps = os.environ.get("CODEX_PRICE_STORE", "")
                if codex_ps and Path(codex_ps).exists():
                    store_note_lines.append(f"A full price store is readable at: {Path(codex_ps).resolve()} (absolute path, read-only).")
                else:
                    store_note_lines.append("Rely on the EPISODE CONTEXT stats above, data/yahoo/ benchmarks, and state coverage gaps honestly.")
            prompt += "\n".join(store_note_lines)
        except Exception:  # noqa: BLE001
            pass

        # FIX 10 — inject failed-track instruction at end of prompt
        if expect_failed:
            prompt += (
                "\n\nIMPORTANT: This is a FAILED breakaway case (`case_type: failed_breakaway`). "
                "The run did NOT sustain — the study's purpose is why it failed (what distinguished it "
                "from durable winners). State this after the first paragraph as the format contract requires."
            )

        # 3. Run Codex to generate the case (dry_run: skip the actual call)
        if dry_run:
            log.info("codex_case_lane: dry_run=True; skipping Codex generation call")
            _append_attempt(r, episode_key, "skipped", None, "dry_run")
            return {"ok": True, "action": "dry_run", "detail": "dry_run: no Codex call", "episode": episode_key, "pr_url": None}

        try:
            from engine.codex_lane.runner import run_codex  # noqa: PLC0415
        except ImportError:
            _append_attempt(r, episode_key, "skipped", None, "runner not importable")
            return {"ok": False, "action": "error", "detail": "runner not importable", "episode": episode_key, "pr_url": None}

        timeout_s = int(cfg.get("session_timeout_min", 25)) * 60
        model = cfg.get("codex_model", "") or ""
        sandbox = cfg.get("sandbox", "workspace-write")
        network = bool(cfg.get("network", True))

        # FIX 13 — snapshot before generation run
        _allowed_case_path = f"research/winners/cases/{ticker}_{year}.md"
        _guard_handle: dict = {}
        _wt_violations_detail = ""
        _wt_fix_violations_detail = ""  # surfaced in audit_failed detail (Finding 5)
        if _wg_snapshot is not None:
            try:
                _guard_handle = _wg_snapshot(r, _wg_protect)
            except Exception as exc:  # noqa: BLE001
                log.warning("codex_case_lane: worktree_guard.snapshot failed (%s)", exc)

        gen_run = run_codex(
            prompt,
            cwd=str(r),
            timeout_s=timeout_s,
            model=model,
            sandbox=sandbox,
            network=network,
        )

        # FIX 13 — restore after generation run
        if _wg_restore is not None and _guard_handle:
            try:
                violations = _wg_restore(r, _guard_handle, allowed={_allowed_case_path})
                if violations:
                    log.warning("codex_case_lane: worktree_guard violations (gen): %s", violations)
                    _wt_violations_detail = f"; worktree_violations={len(violations)}"
            except Exception as exc:  # noqa: BLE001
                log.warning("codex_case_lane: worktree_guard.restore failed (%s)", exc)
            _guard_handle = {}

        _note_result(gen_run, r)

        if not gen_run.get("ok"):
            err = gen_run.get("error_kind", "error")
            # FIX C — log raw_tail so failure diagnostics are visible in the runner log
            _raw_tail_gen = (gen_run.get("raw_tail") or "")[-500:]
            log.warning("codex_case_lane: gen run failed error_kind=%s raw_tail=%r", err, _raw_tail_gen)
            _append_attempt(r, episode_key, "skipped", None, f"gen run failed: {err}{_wt_violations_detail}")
            return {"ok": False, "action": "error", "detail": f"gen run failed: {err}", "episode": episode_key, "pr_url": None}

        # 4. If case file not written by Codex, try to extract from final_message
        if not case_path.exists():
            extracted = _extract_case_from_message(gen_run.get("final_message", ""))
            if extracted:
                try:
                    case_path.parent.mkdir(parents=True, exist_ok=True)
                    case_path.write_text(extracted, encoding="utf-8")
                    log.info("codex_case_lane: wrote case file from final_message: %s", case_path)
                except Exception as exc:  # noqa: BLE001
                    log.warning("codex_case_lane: could not write case from final_message (%s)", exc)

        if not case_path.exists():
            _append_attempt(r, episode_key, "skipped", None, f"case file not created by Codex and not extractable from message{_wt_violations_detail}")
            return {"ok": False, "action": "error", "detail": "case file not created", "episode": episode_key, "pr_url": None}

        # 5. Deterministic audit (FIX 11: pass expect_failed)
        det_failures = _deterministic_audit(case_path, ticker, year, expect_failed=expect_failed)

        # 6. Codex audit session
        try:
            case_text = case_path.read_text(encoding="utf-8")
        except OSError as exc:
            _append_attempt(r, episode_key, "audit_failed", None, f"could not read case file: {exc}")
            return {"ok": False, "action": "audit_failed", "detail": str(exc), "episode": episode_key, "pr_url": None}

        audit_run = _run_codex_audit(case_text, ticker, year, cfg, r)
        _note_result(audit_run, r)
        # FIX C — log raw_tail on audit failures
        if not audit_run.get("ok"):
            _raw_tail_audit = (audit_run.get("raw_tail") or "")[-500:]
            log.warning("codex_case_lane: audit run failed error_kind=%s raw_tail=%r", audit_run.get("error_kind", "error"), _raw_tail_audit)

        verdict, findings = _parse_audit_verdict(audit_run.get("final_message", ""))

        # If FINDINGS -> one fix cycle -> re-audit
        if verdict != "PASS" or det_failures:
            all_issues = det_failures + findings
            if all_issues:
                # FIX 13 — snapshot before fix run
                _guard_handle_fix: dict = {}
                _wt_fix_violations_detail = ""
                if _wg_snapshot is not None:
                    try:
                        _guard_handle_fix = _wg_snapshot(r, _wg_protect)
                    except Exception as exc:  # noqa: BLE001
                        log.warning("codex_case_lane: worktree_guard.snapshot (fix) failed (%s)", exc)

                fix_run = _run_codex_fix(case_text, all_issues, ticker, year, cfg, r)

                # FIX 13 — restore after fix run
                if _wg_restore is not None and _guard_handle_fix:
                    try:
                        fix_violations = _wg_restore(r, _guard_handle_fix, allowed={_allowed_case_path})
                        if fix_violations:
                            log.warning("codex_case_lane: worktree_guard violations (fix): %s", fix_violations)
                            _wt_fix_violations_detail = f"; worktree_violations={len(fix_violations)}"
                    except Exception as exc:  # noqa: BLE001
                        log.warning("codex_case_lane: worktree_guard.restore (fix) failed (%s)", exc)

                _note_result(fix_run, r)
                # FIX C — log raw_tail on fix run failures
                if not fix_run.get("ok"):
                    _raw_tail_fix = (fix_run.get("raw_tail") or "")[-500:]
                    log.warning("codex_case_lane: fix run failed error_kind=%s raw_tail=%r", fix_run.get("error_kind", "error"), _raw_tail_fix)

                # Re-read case file (may have been rewritten by fix)
                if case_path.exists():
                    try:
                        case_text = case_path.read_text(encoding="utf-8")
                    except OSError:
                        pass

                # Re-run deterministic audit (FIX 11: pass expect_failed)
                det_failures = _deterministic_audit(case_path, ticker, year, expect_failed=expect_failed)

                # Re-run Codex audit
                audit_run2 = _run_codex_audit(case_text, ticker, year, cfg, r)
                _note_result(audit_run2, r)
                verdict, findings = _parse_audit_verdict(audit_run2.get("final_message", ""))

        # Check final state
        all_failures = det_failures + (findings if verdict != "PASS" else [])
        if all_failures:
            # Park the file under rejected_cases
            rejected_dir = r / _REJECTED_DIR_REL
            try:
                rejected_dir.mkdir(parents=True, exist_ok=True)
                rejected_path = rejected_dir / case_path.name
                if case_path.exists():
                    rejected_path.write_text(case_path.read_text(encoding="utf-8"), encoding="utf-8")
                    case_path.unlink()
            except Exception as exc:  # noqa: BLE001
                log.warning("codex_case_lane: could not park rejected case (%s)", exc)

            detail = f"audit_failed: {all_failures[:3]}{_wt_fix_violations_detail}"
            _append_attempt(r, episode_key, "audit_failed", None, detail)
            return {"ok": False, "action": "audit_failed", "detail": detail, "episode": episode_key, "pr_url": None}

        # 7. Open PR (not in dry_run — already handled above)
        audit_summary = "Deterministic audit: PASS. Codex audit: PASS."
        draft = cfg.get("case_pr_mode", "draft") == "draft"
        pr_url = _open_pr(r, ticker, year, case_path, audit_summary, draft=draft)

        # FIX B(a): distinguish pr_create_failed (retryable) from pr_opened (terminal)
        if pr_url is None:
            detail_fail = f"gh pr create returned no URL for branch codex/case-{ticker.lower()}-{year}{_wt_violations_detail}"
            log.warning("codex_case_lane: %s", detail_fail)
            _append_attempt(r, episode_key, "pr_create_failed", None, detail_fail)
            return {
                "ok": False,
                "action": "pr_create_failed",
                "detail": detail_fail,
                "episode": episode_key,
                "pr_url": None,
            }

        _append_attempt(r, episode_key, "pr_opened", pr_url, f"PR opened: {pr_url}{_wt_violations_detail}")
        return {
            "ok": True,
            "action": "pr_opened",
            "detail": f"case {episode_key} passed audit; PR={pr_url}",
            "episode": episode_key,
            "pr_url": pr_url,
        }

    except Exception as exc:  # noqa: BLE001
        log.exception("codex_case_lane: unexpected error in run_once: %s", exc)
        return {"ok": False, "action": "error", "detail": str(exc), "episode": None, "pr_url": None}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", type=Path, default=None, help="Repo root")
    ap.add_argument("--dry-run", action="store_true", default=False)
    args = ap.parse_args(argv)

    result = run_once(root=args.root, dry_run=args.dry_run)
    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(_main())
