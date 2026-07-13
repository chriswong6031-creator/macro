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
    """Return set of 'TICKER_YYYY' keys already in case_attempts.jsonl."""
    attempts: set[str] = set()
    path = root / _ATTEMPTS_REL
    if not path.exists():
        return attempts
    try:
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                    ep = row.get("episode")
                    if ep:
                        attempts.add(ep)
                except Exception:
                    continue
    except OSError:
        pass
    return attempts


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


def _build_queue(root: Path) -> list[dict]:
    """Return episodes ranked by |fwd_excess_126d_pp| desc, excluding existing cases and attempts.

    Returns list of dicts: [{ticker, year, excess_col_val}]
    Falls back to an empty list on any error (parquet absent etc.).
    """
    try:
        import pandas as pd  # noqa: PLC0415

        ep_path = root / _EPISODES_REL
        if not ep_path.exists():
            log.warning("codex_case_lane: winner_episodes.parquet absent at %s", ep_path)
            return []

        df = pd.read_parquet(ep_path)
        existing_keys = _existing_case_keys(root)
        attempted_keys = _load_attempted_episodes(root)
        exclude = existing_keys | attempted_keys

        # Build episode key column
        df["_year"] = pd.to_datetime(df["t0"]).dt.year
        df["_key"] = df["ticker"].astype(str) + "_" + df["_year"].astype(str)

        # Filter out already written / attempted
        df = df[~df["_key"].isin(exclude)].copy()

        if df.empty:
            return []

        # Rank by largest absolute forward excess — use best available column
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

        queue = []
        for _, row in df.iterrows():
            try:
                ticker = str(row["ticker"]).strip().upper()
                year = int(row["_year"])
                excess_val = float(row["_sort_val"]) if excess_col else 0.0
                queue.append({"ticker": ticker, "year": year, "excess_val": excess_val, "key": f"{ticker}_{year}"})
            except Exception:
                continue

        return queue

    except Exception as exc:  # noqa: BLE001
        log.warning("codex_case_lane: _build_queue failed (%s)", exc)
        return []


# ---------------------------------------------------------------------------
# Deterministic audit
# ---------------------------------------------------------------------------

_REQUIRED_KEYS = [
    "schema", "ticker", "case_type", "episode_year",
    "run_window", "t0_hypothesis", "thesis_one_liner",
    "mechanism", "stage_map", "catalyst_ladder",
    "hazards", "false_positive_checks", "sources",
]


def _deterministic_audit(case_path: Path, ticker: str, year: int) -> list[str]:
    """Run deterministic checks on a case file. Returns list of failure strings (empty = pass).

    Checks:
    - parse_case_file() succeeds (schema + required keys)
    - ticker/year match filename
    - every catalyst_ladder entry has source_url
    - sources non-empty
    - 'validated' (case-insensitive) absent from file text
    """
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

    # catalyst_ladder: every entry must have source_url
    ladder = case.get("catalyst_ladder") or []
    if isinstance(ladder, list):
        for i, entry in enumerate(ladder):
            if isinstance(entry, dict):
                url = entry.get("source_url") or entry.get("url") or ""
                if not url:
                    failures.append(f"catalyst_ladder[{i}] missing source_url")

    # sources non-empty
    sources = case.get("sources") or []
    if not sources:
        failures.append("sources is empty")

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

    audit_prompt = f"""\
You are an independent auditor reviewing a winner autopsy case file for {ticker} ({year}).

{_AUDIT_CHECKLIST}

Review the following case file and return STRICT JSON with this exact shape:
{{"verdict": "PASS" or "FINDINGS", "findings": ["<issue 1>", ...]}}

If the case passes all checks, return: {{"verdict": "PASS", "findings": []}}
If there are issues, return: {{"verdict": "FINDINGS", "findings": ["<detailed issue>", ...]}}

Do NOT return any other text outside the JSON block.

=== CASE FILE CONTENT ===
{case_text[:12000]}
"""
    timeout_s = int(cfg.get("session_timeout_min", 25)) * 60
    model = cfg.get("codex_model", "") or ""
    sandbox = cfg.get("sandbox", "workspace-write")
    network = bool(cfg.get("network", True))

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

    findings_text = "\n".join(f"- {f}" for f in findings)
    fix_prompt = f"""\
You previously generated a winner autopsy case file for {ticker} ({year}).
An audit found the following issues that must be fixed:

{findings_text}

Here is the current case file content:
=== CASE FILE ===
{case_text[:12000]}
=================

Please provide the complete corrected case file. Write ONLY the markdown content
(no preamble), ending with the fenced ```yaml winner_case.v1 block.

Also write the corrected file to: research/winners/cases/{ticker}_{year}.md
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

        # 7. Push the branch
        push_r = subprocess.run(  # noqa: S603
            ["git", "-C", tmpdir, "push", "origin", branch],
            capture_output=True, text=True,
        )
        if push_r.returncode != 0:
            log.warning("codex_case_lane: push failed (%s); skipping PR", push_r.stderr.strip())
            return None

        # 8. Open the PR via gh (run with cwd=tmpdir)
        try:
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

            result = subprocess.run(  # noqa: S603
                gh_cmd,
                cwd=tmpdir,
                capture_output=True,
                text=True,
            )
            # Extract PR URL from output
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

def run_once(root: Path | str | None = None, dry_run: bool = False) -> dict:
    """Run one iteration of the case lane.

    Returns dict: {ok, action, detail, episode, pr_url}.
    NEVER raises.
    """
    try:
        r = _resolve_root(root)
        cfg = _load_cfg(r)

        # 1. Build work queue
        queue = _build_queue(r)
        if not queue:
            log.info("codex_case_lane: no uncased episodes available; nothing to do")
            return {"ok": True, "action": "skip", "detail": "no uncased episodes", "episode": None, "pr_url": None}

        # Take top 1 (cases_per_run = 1 per spec)
        ep = queue[0]
        ticker = ep["ticker"]
        year = ep["year"]
        episode_key = ep["key"]
        case_path = r / _CASES_DIR_REL / f"{ticker}_{year}.md"

        log.info("codex_case_lane: targeting episode %s", episode_key)

        # 2. Fill prompt template
        template = _load_prompt_template(r)
        if not template:
            _append_attempt(r, episode_key, "skipped", None, "prompt template absent")
            return {"ok": False, "action": "skip", "detail": "prompt template absent", "episode": episode_key, "pr_url": None}

        prompt = _fill_prompt(template, ticker, year)

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

        gen_run = run_codex(
            prompt,
            cwd=str(r),
            timeout_s=timeout_s,
            model=model,
            sandbox=sandbox,
            network=network,
        )
        _note_result(gen_run, r)

        if not gen_run.get("ok"):
            err = gen_run.get("error_kind", "error")
            _append_attempt(r, episode_key, "skipped", None, f"gen run failed: {err}")
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
            _append_attempt(r, episode_key, "skipped", None, "case file not created by Codex and not extractable from message")
            return {"ok": False, "action": "error", "detail": "case file not created", "episode": episode_key, "pr_url": None}

        # 5. Deterministic audit
        det_failures = _deterministic_audit(case_path, ticker, year)

        # 6. Codex audit session
        try:
            case_text = case_path.read_text(encoding="utf-8")
        except OSError as exc:
            _append_attempt(r, episode_key, "audit_failed", None, f"could not read case file: {exc}")
            return {"ok": False, "action": "audit_failed", "detail": str(exc), "episode": episode_key, "pr_url": None}

        audit_run = _run_codex_audit(case_text, ticker, year, cfg, r)
        _note_result(audit_run, r)

        verdict, findings = _parse_audit_verdict(audit_run.get("final_message", ""))

        # If FINDINGS -> one fix cycle -> re-audit
        if verdict != "PASS" or det_failures:
            all_issues = det_failures + findings
            if all_issues:
                fix_run = _run_codex_fix(case_text, all_issues, ticker, year, cfg, r)
                _note_result(fix_run, r)

                # Re-read case file (may have been rewritten by fix)
                if case_path.exists():
                    try:
                        case_text = case_path.read_text(encoding="utf-8")
                    except OSError:
                        pass

                # Re-run deterministic audit
                det_failures = _deterministic_audit(case_path, ticker, year)

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

            detail = f"audit_failed: {all_failures[:3]}"
            _append_attempt(r, episode_key, "audit_failed", None, detail)
            return {"ok": False, "action": "audit_failed", "detail": detail, "episode": episode_key, "pr_url": None}

        # 7. Open PR (not in dry_run — already handled above)
        audit_summary = "Deterministic audit: PASS. Codex audit: PASS."
        draft = cfg.get("case_pr_mode", "draft") == "draft"
        pr_url = _open_pr(r, ticker, year, case_path, audit_summary, draft=draft)

        _append_attempt(r, episode_key, "pr_opened", pr_url, f"PR opened: {pr_url}")
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
