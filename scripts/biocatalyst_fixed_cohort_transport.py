"""Runtime CLI for the privileged B1S2b fixed-cohort collection path.

This executable is the only thing the ``macro-biocatalyst-fixed-cohort`` unit
runs.  One invocation loads ``active.json`` exactly once, binds its exact bytes
and digest into the run receipt, calls the reviewed B1S2a transport library,
writes bounded private run evidence, and appends the canonical ``BC-O1a``
receipt.  If ``BC-O1a`` is unavailable the run fails closed **before** any
collection, because source traffic with no evidence is worse than no traffic.

Membership never reaches this program through an argument.  There is no
``--nct-ids``, ``--cohort``, or ``--allowlist`` option and there never may be:
the only membership authority is ``config/biocatalyst_sources.yml`` plus the
validated, root-owned, digest-qualified manifest that ``active.json`` names.
The environment is scanned first and a run is refused outright if any variable
so much as mentions an NCT identifier.

This CLI is inert on a machine that has not been armed.  The transport gate
(``BIOCATALYST_FIXED_COHORT_TRANSPORT_ENABLED``) defaults to off inside the
transport library itself, and neither the installer nor the updater ever enables
or starts the unit.  Nothing here opens an outcome-family clock; per
``research/BIOCATALYST_OPERATOR_RULING_2026-08-07.md`` a clock opens only through
an activation receipt once collection is proven.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable, Mapping
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from typing import Any

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

from collectors.biocatalyst.clinicaltrials_fixed_cohort import (  # noqa: E402
    DEFAULT_USER_AGENT,
    BoundedFixedCohortHttpTransport,
    ClinicalTrialsFixedCohortTransportRun,
    FixedCohortTransportError,
    FixedCohortTransportLimits,
    build_fixed_cohort_transport_run,
    require_fixed_cohort_user_agent,
)
from engine.biocatalyst.fixed_cohort_runtime import (  # noqa: E402
    RUNTIME_ACTIVE_POINTER_NAME,
    RUNTIME_OPERATIONAL_ROOT,
    RUNTIME_RUN_ROOT,
    RUN_RECEIPT_SOURCE_ID,
    RUN_RECORD_KIND,
    RUN_EVIDENCE_MAX_BYTES,
    RUN_STATE_BY_TRANSPORT_STATE,
    DEFAULT_TRUSTED_GIDS,
    DEFAULT_TRUSTED_UIDS,
    FixedCohortRuntimeError,
    LoadedManifest,
    ROTATION_RECEIPT_RULING_REF,
    assert_environment_carries_no_membership,
    atomic_write_bytes,
    load_active_manifest,
    load_manifest_file,
    require_operational_store_available,
    rotate_active_manifest,
    utc_now,
)
from engine.biocatalyst.operational_store import (  # noqa: E402
    OperationalStore,
    OperationalStoreError,
)
from engine.sector_intelligence.contracts import canonical_json_bytes  # noqa: E402


PROGRAM = "biocatalyst_fixed_cohort_transport"
MODES = ("collect", "rotate", "rollback", "verify")

EXIT_OK = 0
EXIT_PRECONDITION_FAILED = 2
EXIT_RUN_QUARANTINED = 3
EXIT_USAGE = 4
FIXED_COHORT_USER_AGENT_ENV = "BIOCATALYST_FIXED_COHORT_USER_AGENT"

# Nothing in this file may ever accept membership.  The deployment test asserts
# that no parser option matches any of these, so adding one fails CI.
FORBIDDEN_ARGUMENT_TOKENS: tuple[str, ...] = (
    "allowlist",
    "cohort-id",
    "cohort-ids",
    "member",
    "nct",
    "nct-id",
    "nct-ids",
    "query-id",
    "study",
)

_RUN_ID_RE = re.compile(r"^ctgov_fixed_cohort_transport_run_[a-f0-9]{24}$", re.ASCII)
_STARTED_AT_RE = re.compile(
    r"^(?P<year>[0-9]{4})-(?P<month>[0-9]{2})-[0-9]{2}T", re.ASCII
)


class RuntimeCliError(RuntimeError):
    """One bounded CLI failure carrying a distinct, greppable code."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=PROGRAM,
        description=(
            "Run one bounded fixed-cohort transport, or rotate the membership "
            "pointer, using only root-owned immutable manifests."
        ),
        allow_abbrev=False,
    )
    parser.add_argument("--mode", choices=MODES, default="collect")
    parser.add_argument(
        "--manifest",
        required=True,
        help=(
            "absolute path to the active membership pointer "
            f"({RUNTIME_ACTIVE_POINTER_NAME}); membership is never given on the command line"
        ),
    )
    parser.add_argument(
        "--receipt-root",
        required=True,
        help="private receipt root; receipts land under {yyyy}/{mm}/{run_id}.json",
    )
    parser.add_argument(
        "--run-root",
        default=RUNTIME_RUN_ROOT,
        help="private run-evidence root; one bounded directory per run id",
    )
    parser.add_argument(
        "--operational-root",
        default=RUNTIME_OPERATIONAL_ROOT,
        help="provisioned BC-O1a operational store root (the canonical receipt ledger)",
    )
    parser.add_argument(
        "--incoming-manifest",
        default=None,
        help="rotate/rollback only: the root-owned manifest file to make active",
    )
    parser.add_argument(
        "--actor",
        default=None,
        help="rotate/rollback only: the named human authorizing the membership change",
    )
    parser.add_argument(
        "--known-time",
        default=None,
        help="rotate/rollback only: microsecond UTC Z stamp of the authorization",
    )
    parser.add_argument(
        "--user-agent",
        default=None,
        help=(
            "descriptive source contact; defaults to "
            f"{FIXED_COHORT_USER_AGENT_ENV}, then the bounded built-in fallback"
        ),
    )
    return parser


def _resolved_user_agent(
    configured: object, environ: Mapping[str, str]
) -> str:
    candidate = (
        configured
        if configured is not None
        else environ.get(FIXED_COHORT_USER_AGENT_ENV, DEFAULT_USER_AGENT)
    )
    try:
        return require_fixed_cohort_user_agent(candidate)
    except (ValueError, UnicodeError) as exc:
        raise RuntimeCliError(
            "USER_AGENT_INVALID",
            f"{FIXED_COHORT_USER_AGENT_ENV} or --user-agent is invalid",
        ) from exc


def _require_directory(path: Path, *, code: str, what: str) -> Path:
    if path.is_symlink() or not path.is_dir():
        raise RuntimeCliError(code, f"{what} must be an existing real directory: {path}")
    return path


def _require_active_pointer(raw: str) -> Path:
    pointer = Path(raw)
    if not pointer.is_absolute():
        raise RuntimeCliError(
            "MANIFEST_ARGUMENT_INVALID", "--manifest must be an absolute path"
        )
    if pointer.name != RUNTIME_ACTIVE_POINTER_NAME:
        raise RuntimeCliError(
            "MANIFEST_ARGUMENT_INVALID",
            f"--manifest must name the {RUNTIME_ACTIVE_POINTER_NAME} pointer",
        )
    return pointer


def _receipt_path(receipt_root: Path, run_receipt: Mapping[str, Any]) -> Path:
    run_id = run_receipt.get("run_id")
    started_at = run_receipt.get("started_at")
    if not isinstance(run_id, str) or not _RUN_ID_RE.fullmatch(run_id):
        raise RuntimeCliError("RUN_ID_INVALID", "transport run receipt carries no valid run id")
    match = _STARTED_AT_RE.match(started_at) if isinstance(started_at, str) else None
    if match is None:
        raise RuntimeCliError(
            "RUN_CLOCK_INVALID", "transport run receipt carries no usable start stamp"
        )
    return receipt_root / match.group("year") / match.group("month") / f"{run_id}.json"


def _write_once(path: Path, payload: bytes, *, code: str, what: str) -> None:
    """Write bounded evidence exactly once; identical bytes are a no-op."""

    if path.exists():
        if path.is_symlink() or not path.is_file():
            raise RuntimeCliError(code, f"{what} is occupied by a non-regular file: {path}")
        if path.read_bytes() != payload:
            raise RuntimeCliError(code, f"{what} already exists with different bytes: {path}")
        return
    atomic_write_bytes(path, payload, mode=0o400)


def _close_transport(
    transport: object, *, primary: BaseException | None
) -> BaseException | None:
    """Close an injected transport without ever masking the primary error.

    When something is already propagating, a cleanup failure is strictly less
    informative and is dropped.  When nothing is propagating, the failure is
    *returned* rather than raised, so the caller can finish persisting evidence
    it already holds before reporting it.  A close failure must not cost a run
    its receipt.
    """

    closer = getattr(transport, "close", None)
    if closer is None:
        session = getattr(transport, "session", None)
        closer = getattr(session, "close", None)
    if closer is None:
        return None
    try:
        closer()
    except BaseException as exc:  # noqa: BLE001 - cleanup must not shadow the cause
        if primary is None:
            return exc
    return None


def _default_transport_factory(
    *, user_agent: str, environ: Mapping[str, str]
) -> BoundedFixedCohortHttpTransport:
    # Constructing this refuses outright unless the reviewed activation gate is
    # explicitly on, so an unarmed host cannot reach the network from here.
    return BoundedFixedCohortHttpTransport(
        user_agent=user_agent,
        limits=FixedCohortTransportLimits(),
        environ=environ,
    )


def _run_evidence_payloads(
    *, manifest: LoadedManifest, run_receipt: Mapping[str, Any]
) -> tuple[bytes, bytes]:
    run_bytes = canonical_json_bytes(run_receipt) + b"\n"
    binding = {
        "active_manifest_path": str(manifest.path),
        "active_manifest_sha256": manifest.content_sha256,
        "cohort_id": manifest.cohort_id,
        "membership_authority": "fixed_cohort_only",
        "ruling_ref": ROTATION_RECEIPT_RULING_REF,
    }
    return run_bytes, canonical_json_bytes(binding) + b"\n"


def _operational_payload(
    *, run_receipt: Mapping[str, Any], evidence_sha256: str
) -> dict[str, Any]:
    """Project the transport receipt onto BC-O1a's closed ``source_run_receipt`` shape.

    BC-O1a fixes this payload exactly; the richer NCT-level reconciliation stays
    in the private run evidence, which ``evidence_sha256`` binds by content.
    """

    state = RUN_STATE_BY_TRANSPORT_STATE.get(run_receipt["run_state"])
    if state is None:
        raise RuntimeCliError(
            "RUN_STATE_UNMAPPED",
            f"transport run_state {run_receipt['run_state']!r} has no BC-O1a equivalent",
        )
    return {
        "source_id": RUN_RECEIPT_SOURCE_ID,
        "run_id": run_receipt["run_id"],
        "started_at": run_receipt["started_at"],
        "finished_at": run_receipt["finished_at"],
        "run_state": state,
        "evidence_sha256": evidence_sha256,
    }


def _collect(
    args: argparse.Namespace,
    *,
    environ: Mapping[str, str],
    transport_factory: Callable[..., Any],
    store: OperationalStore,
    trusted_uids,
    trusted_gids,
    repo_root: Path | str | None,
    now_fn: Callable[[], datetime],
    stream,
) -> int:
    pointer = _require_active_pointer(args.manifest)
    receipt_root = _require_directory(
        Path(args.receipt_root), code="RECEIPT_ROOT_UNAVAILABLE", what="the receipt root"
    )
    run_root = _require_directory(
        Path(args.run_root), code="RUN_ROOT_UNAVAILABLE", what="the run root"
    )

    # Fail closed before collection: no evidence store, no source traffic.
    require_operational_store_available(store)

    manifest = load_active_manifest(
        pointer.parent,
        trusted_uids=trusted_uids,
        trusted_gids=trusted_gids,
        repo_root=repo_root,
    )

    transport = transport_factory(user_agent=args.user_agent, environ=environ)
    primary: BaseException | None = None
    close_error: BaseException | None = None
    try:
        run = ClinicalTrialsFixedCohortTransportRun(
            cohort=manifest.document,
            transport=transport,
            limits=FixedCohortTransportLimits(),
            user_agent=args.user_agent,
            now_fn=now_fn,
            repo_root=repo_root,
        )
        result = run.run()
    except BaseException as exc:
        primary = exc
        raise
    finally:
        close_error = _close_transport(transport, primary=primary)

    run_receipt = build_fixed_cohort_transport_run(result, repo_root=repo_root)
    run_id = run_receipt["run_id"]
    run_directory = run_root / run_id
    if run_directory.exists() and not run_directory.is_dir():
        raise RuntimeCliError(
            "DUPLICATE_RUN_ID", f"run evidence path is not a directory: {run_directory}"
        )
    receipt_path = _receipt_path(receipt_root, run_receipt)
    run_bytes, binding_bytes = _run_evidence_payloads(
        manifest=manifest, run_receipt=run_receipt
    )
    if len(run_bytes) + len(binding_bytes) > RUN_EVIDENCE_MAX_BYTES:
        raise RuntimeCliError(
            "RUN_EVIDENCE_TOO_LARGE", "private run evidence exceeds its bounded size"
        )
    _write_once(
        run_directory / "run.json",
        run_bytes,
        code="DUPLICATE_RUN_ID",
        what="run evidence",
    )
    _write_once(
        run_directory / "active_manifest.json",
        binding_bytes,
        code="DUPLICATE_RUN_ID",
        what="run manifest binding",
    )
    _write_once(
        receipt_path, run_bytes, code="DUPLICATE_RUN_ID", what="the private receipt"
    )

    try:
        store.append(
            RUN_RECORD_KIND,
            _operational_payload(
                run_receipt=run_receipt,
                evidence_sha256=hashlib.sha256(run_bytes + binding_bytes).hexdigest(),
            ),
            idempotency_key=f"fixed_cohort_run.{run_id}",
            # Stamp the record with the run's own known time rather than the
            # process wall clock, so replaying an identical run is a true no-op
            # instead of a same-key/different-bytes conflict.
            recorded_at=run_receipt["finished_at"],
        )
    except (OperationalStoreError, OSError) as exc:
        raise RuntimeCliError(
            "OPERATIONAL_RECEIPT_REFUSED",
            f"BC-O1a refused the run receipt: {getattr(exc, 'code', exc)}",
        ) from exc

    if close_error is not None:
        # Reported only now: the evidence and the receipt are already durable,
        # so a failed close costs visibility, never the record of the run.
        raise RuntimeCliError(
            "TRANSPORT_CLOSE_FAILED", f"transport could not be closed: {close_error}"
        )

    print(
        json.dumps(
            {
                "mode": "collect",
                "run_id": run_id,
                "run_state": run_receipt["run_state"],
                "cohort_id": manifest.cohort_id,
                "active_manifest_sha256": manifest.content_sha256,
                "receipt_path": str(receipt_path),
            },
            sort_keys=True,
        ),
        file=stream,
        flush=True,
    )
    return EXIT_OK if run_receipt["run_state"] == "complete" else EXIT_RUN_QUARANTINED


def _rotate(
    args: argparse.Namespace,
    *,
    store: OperationalStore,
    trusted_uids,
    trusted_gids,
    repo_root: Path | str | None,
    stream,
) -> int:
    pointer = _require_active_pointer(args.manifest)
    if not args.incoming_manifest:
        raise RuntimeCliError(
            "ROTATION_ARGUMENT_MISSING", "--incoming-manifest is required to rotate"
        )
    if not args.actor or not args.known_time:
        raise RuntimeCliError(
            "ROTATION_ARGUMENT_MISSING",
            "--actor and --known-time are required: a membership change is always attributed",
        )
    incoming_path = Path(args.incoming_manifest)
    if not incoming_path.is_absolute():
        raise RuntimeCliError(
            "ROTATION_ARGUMENT_INVALID", "--incoming-manifest must be an absolute path"
        )
    rotation_kind = "rollback" if args.mode == "rollback" else "rotation"
    candidate = load_manifest_file(
        incoming_path,
        trusted_uids=trusted_uids,
        trusted_gids=trusted_gids,
        repo_root=repo_root,
        require_digest_qualified_name=(rotation_kind == "rollback"),
    )
    receipt = rotate_active_manifest(
        config_root=pointer.parent,
        receipt_root=_require_directory(
            Path(args.receipt_root),
            code="RECEIPT_ROOT_UNAVAILABLE",
            what="the receipt root",
        ),
        document=candidate.document,
        actor=args.actor,
        known_time=args.known_time,
        store=store,
        rotation_kind=rotation_kind,
        trusted_uids=trusted_uids,
        trusted_gids=trusted_gids,
        repo_root=repo_root,
    )
    print(
        json.dumps(
            {
                "mode": rotation_kind,
                "previous_cohort_id": receipt["previous_cohort_id"],
                "next_cohort_id": receipt["next_cohort_id"],
                "next_manifest_sha256": receipt["next_manifest_sha256"],
                "actor": receipt["actor"],
                "known_time": receipt["known_time"],
            },
            sort_keys=True,
        ),
        file=stream,
        flush=True,
    )
    return EXIT_OK


def _verify(
    args: argparse.Namespace,
    *,
    store: OperationalStore,
    trusted_uids,
    trusted_gids,
    repo_root: Path | str | None,
    stream,
) -> int:
    pointer = _require_active_pointer(args.manifest)
    manifest = load_active_manifest(
        pointer.parent,
        trusted_uids=trusted_uids,
        trusted_gids=trusted_gids,
        repo_root=repo_root,
    )
    require_operational_store_available(store)
    print(
        json.dumps(
            {
                "mode": "verify",
                "cohort_id": manifest.cohort_id,
                "active_manifest_sha256": manifest.content_sha256,
                "member_count": len(manifest.nct_ids),
                "operational_store_available": True,
            },
            sort_keys=True,
        ),
        file=stream,
        flush=True,
    )
    return EXIT_OK


def main(
    argv: list[str] | None = None,
    *,
    environ: Mapping[str, str] | None = None,
    transport_factory: Callable[..., Any] | None = None,
    store_factory: Callable[[Path], OperationalStore] | None = None,
    trusted_uids=DEFAULT_TRUSTED_UIDS,
    trusted_gids=DEFAULT_TRUSTED_GIDS,
    repo_root: Path | str | None = None,
    now_fn: Callable[[], datetime] = utc_now,
    stream=None,
    error_stream=None,
) -> int:
    """Run one bounded invocation and return its exit code.

    Every seam a test needs -- environment, transport, receipt store, trusted
    owner, clock, streams -- is a keyword argument here rather than a production
    command-line flag, so no test performs real network or filesystem-root I/O
    and no operator can widen the runtime's trust from the command line.
    """

    out = sys.stdout if stream is None else stream
    err = sys.stderr if error_stream is None else error_stream
    values = os.environ if environ is None else environ
    parser = build_parser()
    try:
        args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    except SystemExit:
        return EXIT_USAGE

    try:
        assert_environment_carries_no_membership(values)
        if args.mode == "collect":
            args.user_agent = _resolved_user_agent(args.user_agent, values)
        store = (
            OperationalStore(Path(args.operational_root), repo_root=repo_root)
            if store_factory is None
            else store_factory(Path(args.operational_root))
        )
        if args.mode == "collect":
            return _collect(
                args,
                environ=values,
                transport_factory=(
                    _default_transport_factory
                    if transport_factory is None
                    else transport_factory
                ),
                store=store,
                trusted_uids=trusted_uids,
                trusted_gids=trusted_gids,
                repo_root=repo_root,
                now_fn=now_fn,
                stream=out,
            )
        if args.mode in ("rotate", "rollback"):
            return _rotate(
                args,
                store=store,
                trusted_uids=trusted_uids,
                trusted_gids=trusted_gids,
                repo_root=repo_root,
                stream=out,
            )
        return _verify(
            args,
            store=store,
            trusted_uids=trusted_uids,
            trusted_gids=trusted_gids,
            repo_root=repo_root,
            stream=out,
        )
    except (RuntimeCliError, FixedCohortRuntimeError, FixedCohortTransportError) as exc:
        print(
            json.dumps({"error_code": exc.code, "message": str(exc)}, sort_keys=True),
            file=err,
            flush=True,
        )
        return EXIT_PRECONDITION_FAILED
    except OperationalStoreError as exc:
        print(
            json.dumps({"error_code": exc.code, "message": str(exc)}, sort_keys=True),
            file=err,
            flush=True,
        )
        return EXIT_PRECONDITION_FAILED


if __name__ == "__main__":  # pragma: no cover - process entry point
    raise SystemExit(main())
