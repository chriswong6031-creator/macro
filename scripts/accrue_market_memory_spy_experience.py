"""Accrue the preregistered private SPY experience ledger.

This is the sole W2C production writer.  It refuses to import the accrual
engine until every runtime contract and tracked input is byte-identical to the
deployed checkout's exact HEAD.  The private owner/store roots are fixed by the
reviewed systemd unit; callers cannot supply a cutoff clock.
"""

from __future__ import annotations

import argparse
import json
import re
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

_COMMIT = re.compile(r"[a-f0-9]{40}(?:[a-f0-9]{24})?\Z")
_TRACKED_RUNTIME_CLOSURE = (
    "app/requirements.txt",
    "scripts/__init__.py",
    "scripts/accrue_market_memory_spy_experience.py",
    "engine/__init__.py",
    "engine/neuralweb/__init__.py",
    "engine/neuralweb/market_memory.py",
    "engine/neuralweb/market_memory_pit.py",
    "engine/neuralweb/market_memory_trusted.py",
    "engine/neuralweb/market_memory_technical_observation.py",
    "engine/neuralweb/market_memory_technical_store.py",
    "engine/neuralweb/market_memory_experience_accrual.py",
    "config/market_memory_canary.v1.json",
    "config/market_memory_technical_price_basis.v1.json",
    "config/market_memory_spy_experience_registration.v1.json",
    "contracts/market_memory/spy_experience_registration.v1.schema.json",
    "contracts/market_memory/spy_experience_opportunity.v1.schema.json",
    "contracts/market_memory/spy_experience_outcome_revision.v1.schema.json",
    "contracts/market_memory/spy_experience_population_receipt.v1.schema.json",
    "lib/__init__.py",
    "lib/nyse_calendar.py",
    "research/licenses/MASSIVE_ENTITLEMENT_RECORD.md",
)


class MarketMemoryExperienceCliError(RuntimeError):
    """The deployed checkout cannot establish an exact W2C writer closure."""


def _git(
    repository_root: Path,
    *arguments: str,
    text: bool = False,
) -> subprocess.CompletedProcess[Any]:
    try:
        return subprocess.run(
            ["git", "-C", str(repository_root), *arguments],
            check=True,
            capture_output=True,
            text=text,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise MarketMemoryExperienceCliError(
            "cannot authenticate the deployed W2C checkout"
        ) from exc


def _verified_repository_commit(repository_root: Path) -> str:
    """Return HEAD only when the complete W2C closure matches its tree bytes."""

    root = repository_root.expanduser().resolve()
    top_level = _git(root, "rev-parse", "--show-toplevel", text=True).stdout.strip()
    try:
        resolved_top_level = Path(top_level).resolve(strict=True)
    except OSError as exc:
        raise MarketMemoryExperienceCliError(
            "deployed W2C repository root is not a real directory"
        ) from exc
    if resolved_top_level != root:
        raise MarketMemoryExperienceCliError(
            "deployed W2C repository root is not the checkout top level"
        )
    commit = _git(root, "rev-parse", "--verify", "HEAD^{commit}", text=True).stdout.strip()
    if not _COMMIT.fullmatch(commit):
        raise MarketMemoryExperienceCliError(
            "deployed W2C repository commit is malformed"
        )

    for relative in _TRACKED_RUNTIME_CLOSURE:
        candidate = root / relative
        try:
            resolved_candidate = candidate.resolve(strict=True)
            metadata = candidate.lstat()
        except OSError as exc:
            raise MarketMemoryExperienceCliError(
                f"tracked W2C input cannot be read: {relative}"
            ) from exc
        if (
            resolved_candidate != candidate
            or not stat.S_ISREG(metadata.st_mode)
            or candidate.is_symlink()
        ):
            raise MarketMemoryExperienceCliError(
                f"tracked W2C input is not a regular file: {relative}"
            )
        try:
            body = candidate.read_bytes()
        except OSError as exc:
            raise MarketMemoryExperienceCliError(
                f"tracked W2C input cannot be read: {relative}"
            ) from exc
        expected = _git(root, "cat-file", "blob", f"{commit}:{relative}").stdout
        if body != expected:
            raise MarketMemoryExperienceCliError(
                f"tracked W2C input differs from deployed HEAD: {relative}"
            )
    return commit


def accrue_registered_spy_experience(
    repository_root: str | Path,
    *,
    experience_root: str | Path,
    trusted_root: str | Path,
    technical_root: str | Path,
) -> dict[str, Any]:
    """Authenticate the checkout, then invoke the one reviewed writer API."""

    repository = Path(repository_root).expanduser().resolve()
    commit = _verified_repository_commit(repository)
    from engine.neuralweb import market_memory_experience_accrual as experience

    result = experience.accrue_spy_experience(
        repository,
        experience_root=Path(experience_root).expanduser(),
        trusted_root=Path(trusted_root).expanduser(),
        technical_root=Path(technical_root).expanduser(),
        writer_commit=commit,
    )
    return {
        "schema": "market_memory.spy_experience_accrual_run.v1",
        "deployed_commit": commit,
        "registration_id": result.registration_id,
        "opportunity_ids": list(result.opportunity_ids),
        "outcome_revision_ids": list(result.outcome_revision_ids),
        "population_receipt_id": result.population_receipt_id,
    }


def verify_registered_spy_experience_installation(
    repository_root: str | Path,
    *,
    experience_root: str | Path,
) -> dict[str, Any]:
    """Read-only authentication of the immutable preactivation receipt."""

    repository = Path(repository_root).expanduser().resolve()
    commit = _verified_repository_commit(repository)
    from engine.neuralweb import market_memory_experience_accrual as experience

    installation = experience.verify_experience_installation(
        repository,
        experience_root=Path(experience_root).expanduser(),
        expected_writer_commit=None,
    )
    return {
        "schema": "market_memory.spy_experience_installation_attestation.v1",
        "deployed_commit": commit,
        "installation": installation,
    }


def verify_registered_spy_experience_terminal(
    repository_root: str | Path,
    *,
    experience_root: str | Path,
) -> dict[str, Any] | None:
    """Read-only authentication of the terminal marker and complete ledger."""

    repository = Path(repository_root).expanduser().resolve()
    commit = _verified_repository_commit(repository)
    from engine.neuralweb import market_memory_experience_accrual as experience

    marker = experience.verify_terminal_ledger(
        repository,
        experience_root=Path(experience_root).expanduser(),
        expected_writer_commit=None,
    )
    if marker is None:
        return None
    return {
        "schema": "market_memory.spy_experience_terminal_attestation.v1",
        "deployed_commit": commit,
        "terminal": marker,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Accrue the private preregistered SPY experience census"
    )
    parser.add_argument("--repository-root", type=Path, default=_ROOT)
    parser.add_argument("--experience-root", type=Path, required=True)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--verify-installation",
        action="store_true",
        help="authenticate the preactivation receipt without reading owners or writing",
    )
    mode.add_argument(
        "--verify-terminal",
        action="store_true",
        help="authenticate the terminal marker and full ledger without writing",
    )
    parser.add_argument("--trusted-root", type=Path)
    parser.add_argument("--technical-root", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        if args.verify_installation:
            result = verify_registered_spy_experience_installation(
                args.repository_root,
                experience_root=args.experience_root,
            )
        elif args.verify_terminal:
            result = verify_registered_spy_experience_terminal(
                args.repository_root,
                experience_root=args.experience_root,
            )
            if result is None:
                return 3
        else:
            if args.trusted_root is None or args.technical_root is None:
                parser.error("accrual requires --trusted-root and --technical-root")
            result = accrue_registered_spy_experience(
                args.repository_root,
                experience_root=args.experience_root,
                trusted_root=args.trusted_root,
                technical_root=args.technical_root,
            )
    except Exception as exc:
        print(f"W2C command failed: {exc}", file=sys.stderr)
        return 2
    print(
        json.dumps(
            result,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
