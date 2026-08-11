"""Publish committed display-only GEX state files to the public R2 plane.

The producer of ``site/options_structure/gex_state`` is the nightly GEX board.
This module is only its projection lane: it never recomputes levels, changes
dealer-sign assumptions, or grants signal/ranking authority.

The M1 scheduler runs this module from a clean, fast-forward-only standalone
clone.  Publication fails closed unless the index is internally complete and
SPY/QQQ/NVDA describe the expected settled NYSE session.  A durable local state
file plus authenticated reads of every object avoids rewriting the full prefix
every cycle. A deterministic public content-hash manifest makes the complete
projection auditable; the former mixed-vintage writer is retired separately.

Env: R2_ENDPOINT, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_BUCKET.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import logging
import os
import re
import sys
import tempfile
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Callable, Iterable

from lib.gex_state_index import build_index
from lib.nyse_calendar import expected_last_session

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("gex_state_mirror")

PREFIX = "options_structure/gex_state"
PUBLIC_BASE = "https://pub-f7ffb4441c5f4ad983ca56ec7c651c61.r2.dev"
STATE_SCHEMA = "options_structure.gex_state/v1"
INDEX_SCHEMA = "options_structure.gex_state_index/v1"
DEFAULT_REQUIRED_ROOTS = ("SPY", "QQQ", "NVDA")
ROOT_RE = re.compile(r"^[A-Z0-9][A-Z0-9.-]*$")
AUTHORITY_TIER = "display"
PASSPORT_BASIS = "assumption"
PASSPORT_VERDICT = "display-only"
LEVEL_AUTHORITY = "display-only-until-gate"
CONTENT_MANIFEST_NAME = "_content_manifest.json"
CONTENT_MANIFEST_SCHEMA = "options_structure.gex_state_content_manifest/v1"


@dataclass(frozen=True)
class MirrorBundle:
    """Validated byte-exact publication bundle."""

    source_dir: Path
    objects: tuple[tuple[str, bytes], ...]
    roots: tuple[str, ...]
    required_roots: tuple[str, ...]
    expected_session: date | None
    manifest_sha256: str

    def body(self, name: str) -> bytes:
        for candidate, body in self.objects:
            if candidate == name:
                return body
        raise KeyError(name)


def _parse_asof(value: object, *, label: str) -> date:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label}: missing canonical asof")
    stamp = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        return datetime.fromisoformat(stamp).date()
    except ValueError as exc:
        raise ValueError(f"{label}: invalid asof {value!r}") from exc


def _manifest_sha256(objects: Iterable[tuple[str, bytes]]) -> str:
    digest = hashlib.sha256()
    for name, body in objects:
        digest.update(name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(hashlib.sha256(body).digest())
    return digest.hexdigest()


def content_manifest_bytes(bundle: MirrorBundle, *, source_commit: str) -> bytes:
    """Build the deterministic public content-hash receipt for every object."""

    payload = {
        "schema": CONTENT_MANIFEST_SCHEMA,
        "source_manifest_sha256": bundle.manifest_sha256,
        "source_commit": source_commit,
        "source_object_count": len(bundle.objects),
        "n_roots": len(bundle.roots),
        "expected_session": (
            bundle.expected_session.isoformat() if bundle.expected_session else None
        ),
        "required_roots": list(bundle.required_roots),
        "authority": {
            "tier": AUTHORITY_TIER,
            "dealer_sign_basis": PASSPORT_BASIS,
            "may_rank": False,
            "may_score": False,
            "may_trade": False,
        },
        "objects": {
            name: hashlib.sha256(body).hexdigest() for name, body in bundle.objects
        },
    }
    return (
        json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def load_bundle(
    source_dir: Path,
    *,
    required_roots: Iterable[str] = DEFAULT_REQUIRED_ROOTS,
    expected_session: date | None = None,
) -> MirrorBundle:
    """Load and validate the complete committed projection set.

    Every per-root file retains the repository's display-only/assumption
    passport.  Only required liquid anchors are required to match the expected
    settled session; sparse single names may honestly retain their last usable
    chain date.
    """

    source_dir = Path(source_dir)
    if not source_dir.is_dir():
        raise ValueError(f"gex_state source dir absent: {source_dir}")

    required = tuple(
        dict.fromkeys(str(root).strip().upper() for root in required_roots)
    )
    if not required or any(not ROOT_RE.fullmatch(root) for root in required):
        raise ValueError("required roots must be canonical uppercase option roots")

    objects: list[tuple[str, bytes]] = []
    roots: dict[str, dict] = {}
    index_payload: dict | None = None
    today = datetime.now(timezone.utc).date()

    for path in sorted(source_dir.glob("*.json"), key=lambda item: item.name):
        body = path.read_bytes()
        try:
            payload = json.loads(body)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ValueError(f"{path.name}: invalid JSON") from exc
        if not isinstance(payload, dict):
            raise ValueError(f"{path.name}: payload must be an object")
        objects.append((path.name, body))

        if path.name == "_index.json":
            index_payload = payload
            continue
        if path.name.startswith("_"):
            raise ValueError(f"{path.name}: unexpected private JSON artifact")

        root = payload.get("root")
        if not isinstance(root, str) or not ROOT_RE.fullmatch(root):
            raise ValueError(f"{path.name}: invalid root")
        if path.name != f"{root}.json":
            raise ValueError(f"{path.name}: filename/root mismatch ({root})")
        if root in roots:
            raise ValueError(f"{path.name}: duplicate root {root}")
        if payload.get("schema") != STATE_SCHEMA:
            raise ValueError(f"{path.name}: wrong schema")
        if payload.get("authority_tier") != AUTHORITY_TIER:
            raise ValueError(f"{path.name}: authority tier is not display")
        passport = payload.get("regime_passport")
        if not isinstance(passport, dict):
            raise ValueError(f"{path.name}: missing regime passport")
        if passport.get("basis") != PASSPORT_BASIS:
            raise ValueError(f"{path.name}: dealer-sign basis is not assumption")
        if passport.get("verdict") != PASSPORT_VERDICT:
            raise ValueError(f"{path.name}: regime passport is not display-only")
        reliability = payload.get("reliability")
        if (
            not isinstance(reliability, dict)
            or reliability.get("levels") != LEVEL_AUTHORITY
        ):
            raise ValueError(f"{path.name}: level authority is not display-only")
        asof = _parse_asof(payload.get("asof"), label=path.name)
        if asof > today:
            raise ValueError(f"{path.name}: future asof {asof.isoformat()}")
        roots[root] = payload

    if not roots:
        raise ValueError("gex_state source set is empty")
    if index_payload is None:
        raise ValueError("gex_state _index.json is required")
    if index_payload.get("schema") != INDEX_SCHEMA:
        raise ValueError("_index.json: wrong schema")
    index_rows = index_payload.get("rows")
    if not isinstance(index_rows, dict) or set(index_rows) != set(roots):
        raise ValueError("_index.json: rows do not exactly cover per-root files")
    if index_payload.get("n_roots") != len(roots):
        raise ValueError("_index.json: n_roots does not match rows")
    rebuilt_index = build_index(source_dir)
    if rebuilt_index != index_payload:
        raise ValueError(
            "_index.json: payload differs from deterministic per-root reconstruction"
        )

    missing = sorted(set(required) - set(roots))
    if missing:
        raise ValueError(f"required roots absent: {', '.join(missing)}")
    if expected_session is not None:
        index_date = _parse_asof(index_payload.get("asof"), label="_index.json")
        if index_date != expected_session:
            raise ValueError(
                "_index.json: expected settled session "
                f"{expected_session.isoformat()}, got {index_date.isoformat()}"
            )
        stale = [
            root
            for root in required
            if _parse_asof(roots[root].get("asof"), label=f"{root}.json")
            != expected_session
        ]
        if stale:
            raise ValueError(
                "required roots are not on expected settled session "
                f"{expected_session.isoformat()}: {', '.join(stale)}"
            )

    frozen_objects = tuple(objects)
    return MirrorBundle(
        source_dir=source_dir,
        objects=frozen_objects,
        roots=tuple(sorted(roots)),
        required_roots=required,
        expected_session=expected_session,
        manifest_sha256=_manifest_sha256(frozen_objects),
    )


def _http_get(url: str, *, timeout: float = 15.0) -> bytes:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "mastermind-gex-mirror/1"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
        return response.read()


def public_anchors_match(
    bundle: MirrorBundle,
    public_base: str,
    *,
    fetch: Callable[[str], bytes] | None = None,
) -> bool:
    """Return whether public required roots and the coverage index are exact."""

    fetcher = fetch or _http_get
    names = [f"{root}.json" for root in bundle.required_roots] + ["_index.json"]
    # A unique query prevents an earlier probe of the same manifest from
    # masking a later stale overwrite in an intermediary cache.
    cache_key = f"{bundle.manifest_sha256[:16]}-{time.time_ns()}"
    for name in names:
        url = f"{public_base.rstrip('/')}/{PREFIX}/{name}?v={cache_key}"
        try:
            if fetcher(url) != bundle.body(name):
                return False
        except (OSError, urllib.error.URLError, urllib.error.HTTPError):
            return False
    return True


def public_content_manifest_matches(
    body: bytes,
    public_base: str,
    *,
    fetch: Callable[[str], bytes] | None = None,
) -> bool:
    """Verify the public every-object hash manifest byte-for-byte."""

    fetcher = fetch or _http_get
    cache_key = f"{hashlib.sha256(body).hexdigest()[:16]}-{time.time_ns()}"
    url = (
        f"{public_base.rstrip('/')}/{PREFIX}/{CONTENT_MANIFEST_NAME}"
        f"?v={cache_key}"
    )
    try:
        return fetcher(url) == body
    except (OSError, urllib.error.URLError, urllib.error.HTTPError):
        return False


def _read_state(path: Path | None) -> dict:
    if path is None or not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_state(path: Path | None, payload: dict) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, sort_keys=True, separators=(",", ":"))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    finally:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass


def _r2_client():
    endpoint = os.environ.get("R2_ENDPOINT")
    access_key = os.environ.get("R2_ACCESS_KEY_ID")
    secret_key = os.environ.get("R2_SECRET_ACCESS_KEY")
    bucket = os.environ.get("R2_BUCKET")
    if not all((endpoint, access_key, secret_key, bucket)):
        raise RuntimeError("R2_ENDPOINT/access key/secret/bucket are required")
    try:
        import boto3  # type: ignore
        from botocore.config import Config  # type: ignore
    except ImportError as exc:
        raise RuntimeError("boto3 is required for GEX state publication") from exc
    config_kwargs = dict(
        region_name="auto",
        signature_version="s3v4",
        retries={"max_attempts": 4, "mode": "standard"},
    )
    try:
        config = Config(
            **config_kwargs,
            request_checksum_calculation="when_required",
            response_checksum_validation="when_required",
        )
    except TypeError:  # Older botocore does not expose checksum policy knobs.
        config = Config(**config_kwargs)
    client = boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        config=config,
    )
    return client, str(bucket)


def _remote_keys(client, bucket: str) -> set[str]:
    prefix = f"{PREFIX}/"
    keys: set[str] = set()
    token: str | None = None
    while True:
        kwargs = {"Bucket": bucket, "Prefix": prefix}
        if token is not None:
            kwargs["ContinuationToken"] = token
        page = client.list_objects_v2(**kwargs)
        for row in page.get("Contents", []):
            key = row.get("Key")
            if isinstance(key, str):
                keys.add(key)
        if not page.get("IsTruncated"):
            return keys
        token = page.get("NextContinuationToken")
        if not isinstance(token, str) or not token:
            raise RuntimeError("R2 listing truncated without continuation token")


def _expected_keys(bundle: MirrorBundle) -> set[str]:
    keys = {f"{PREFIX}/{name}" for name, _ in bundle.objects}
    keys.add(f"{PREFIX}/{CONTENT_MANIFEST_NAME}")
    return keys


def _delete_remote_keys(client, bucket: str, keys: Iterable[str]) -> None:
    """Delete objects outside the exact source projection in bounded batches."""

    ordered = sorted(set(keys))
    for offset in range(0, len(ordered), 1000):
        batch = ordered[offset : offset + 1000]
        response = client.delete_objects(
            Bucket=bucket,
            Delete={"Objects": [{"Key": key} for key in batch], "Quiet": True},
        )
        errors = response.get("Errors", [])
        if errors:
            sample = ", ".join(str(row.get("Key", "?")) for row in errors[:8])
            raise RuntimeError(
                f"R2 projection cleanup failed for {len(errors)} object(s): {sample}"
            )


def r2_object_mismatches(
    bundle: MirrorBundle,
    client,
    bucket: str,
    *,
    content_manifest: bytes,
) -> tuple[str, ...]:
    """Return every source/manifest object whose direct R2 bytes differ."""

    expected = list(bundle.objects) + [(CONTENT_MANIFEST_NAME, content_manifest)]

    def mismatch(item: tuple[str, bytes]) -> str | None:
        name, expected_body = item
        try:
            body = client.get_object(
                Bucket=bucket,
                Key=f"{PREFIX}/{name}",
            )["Body"].read()
        except Exception:  # noqa: BLE001 - any missing/unreadable object is a mismatch.
            return name
        return name if body != expected_body else None

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(mismatch, expected))
    return tuple(name for name in results if name is not None)


@contextmanager
def exclusive_lock(path: Path | None):
    """Hold one non-blocking cross-process lock for the complete projection."""

    if path is None:
        yield
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
    acquired = False
    try:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            acquired = True
        except BlockingIOError as exc:
            raise RuntimeError(f"GEX state publisher lock is already held: {path}") from exc
        yield
    finally:
        if acquired:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def publish_bundle(
    bundle: MirrorBundle,
    *,
    public_base: str = PUBLIC_BASE,
    state_file: Path | None = None,
    source_commit: str = "unknown",
    force: bool = False,
) -> dict:
    """Publish the bundle, then verify direct R2 and public exact bytes."""

    content_manifest = content_manifest_bytes(bundle, source_commit=source_commit)
    content_manifest_sha256 = hashlib.sha256(content_manifest).hexdigest()
    prior = _read_state(state_file)
    client = None
    bucket = None
    if (
        not force
        and prior.get("manifest_sha256") == bundle.manifest_sha256
        and prior.get("content_manifest_sha256") == content_manifest_sha256
    ):
        client, bucket = _r2_client()
    direct_mismatches: tuple[str, ...] = ()
    exact_remote_keys = False
    if client is not None and bucket is not None:
        exact_remote_keys = _remote_keys(client, bucket) == _expected_keys(bundle)
        direct_mismatches = r2_object_mismatches(
            bundle,
            client,
            bucket,
            content_manifest=content_manifest,
        )
    if (
        client is not None
        and bucket is not None
        and exact_remote_keys
        and not direct_mismatches
        and public_anchors_match(bundle, public_base)
        and public_content_manifest_matches(content_manifest, public_base)
    ):
        receipt = {
            "status": "unchanged",
            "manifest_sha256": bundle.manifest_sha256,
            "content_manifest_sha256": content_manifest_sha256,
            "source_commit": source_commit,
            "n_roots": len(bundle.roots),
            "source_object_count": len(bundle.objects),
            "published_object_count": len(bundle.objects) + 1,
            "direct_verified_count": len(bundle.objects) + 1,
            "expected_session": (
                bundle.expected_session.isoformat() if bundle.expected_session else None
            ),
            "required_roots": list(bundle.required_roots),
            "public_verified": True,
        }
        return receipt

    if client is None or bucket is None:
        client, bucket = _r2_client()
    metadata = {
        "source-manifest": bundle.manifest_sha256,
        "source-commit": source_commit[:64],
        "authority-tier": AUTHORITY_TIER,
    }

    index_object: tuple[str, bytes] | None = None
    root_objects: list[tuple[str, bytes]] = []
    for item in bundle.objects:
        if item[0] == "_index.json":
            index_object = item
        else:
            root_objects.append(item)
    if index_object is None:  # load_bundle already guarantees this.
        raise RuntimeError("validated bundle lost _index.json")

    def upload(item: tuple[str, bytes]) -> None:
        name, body = item
        client.put_object(
            Bucket=bucket,
            Key=f"{PREFIX}/{name}",
            Body=body,
            ContentType="application/json",
            Metadata=metadata,
        )

    # Four workers keeps this independent of ThetaData request budgets while
    # reducing a 600-object projection from minutes to a short bounded pass.
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(upload, root_objects))
    upload(index_object)  # coverage marker publishes last
    upload((CONTENT_MANIFEST_NAME, content_manifest))  # every-object receipt is final

    expected_keys = _expected_keys(bundle)
    remote_keys = _remote_keys(client, bucket)
    missing_keys = sorted(expected_keys - remote_keys)
    if missing_keys:
        raise RuntimeError(f"R2 publication missing {len(missing_keys)} source objects")
    unexpected_keys = sorted(remote_keys - expected_keys)
    if unexpected_keys:
        _delete_remote_keys(client, bucket, unexpected_keys)
        remote_keys = _remote_keys(client, bucket)
    if remote_keys != expected_keys:
        missing = len(expected_keys - remote_keys)
        unexpected = len(remote_keys - expected_keys)
        raise RuntimeError(
            "R2 projection key set is not exact after publication "
            f"(missing={missing}, unexpected={unexpected})"
        )

    direct_mismatches = r2_object_mismatches(
        bundle,
        client,
        bucket,
        content_manifest=content_manifest,
    )
    if direct_mismatches:
        sample = ", ".join(direct_mismatches[:8])
        raise RuntimeError(
            f"R2 direct verification mismatched {len(direct_mismatches)} object(s): {sample}"
        )

    public_verified = False
    for attempt in range(1, 7):
        if (
            public_anchors_match(bundle, public_base)
            and public_content_manifest_matches(content_manifest, public_base)
        ):
            public_verified = True
            break
        if attempt < 6:
            time.sleep(1.0)
    if not public_verified:
        raise RuntimeError("public R2 anchor/index verification did not converge")

    receipt = {
        "status": "published",
        "published_at": datetime.now(timezone.utc).isoformat(),
        "manifest_sha256": bundle.manifest_sha256,
        "content_manifest_sha256": content_manifest_sha256,
        "source_commit": source_commit,
        "n_roots": len(bundle.roots),
        "source_object_count": len(bundle.objects),
        "published_object_count": len(bundle.objects) + 1,
        "direct_verified_count": len(bundle.objects) + 1,
        "expected_session": (
            bundle.expected_session.isoformat() if bundle.expected_session else None
        ),
        "required_roots": list(bundle.required_roots),
        "public_verified": True,
    }
    _write_state(state_file, receipt)
    return receipt


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    repo = Path(__file__).resolve().parents[1]
    parser.add_argument(
        "--source-dir",
        type=Path,
        default=repo / "site" / "options_structure" / "gex_state",
    )
    parser.add_argument("--state-file", type=Path)
    parser.add_argument("--lock-file", type=Path)
    parser.add_argument("--public-base", default=PUBLIC_BASE)
    parser.add_argument("--required-root", action="append", dest="required_roots")
    parser.add_argument(
        "--require-expected-session",
        action="store_true",
        help="require the index and liquid anchors to match expected_last_session()",
    )
    parser.add_argument("--force", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    required_roots = args.required_roots or list(DEFAULT_REQUIRED_ROOTS)
    expected = expected_last_session() if args.require_expected_session else None
    source_commit = os.environ.get("GEX_STATE_SOURCE_COMMIT", "unknown")
    try:
        with exclusive_lock(args.lock_file):
            bundle = load_bundle(
                args.source_dir,
                required_roots=required_roots,
                expected_session=expected,
            )
            receipt = publish_bundle(
                bundle,
                public_base=args.public_base,
                state_file=args.state_file,
                source_commit=source_commit,
                force=args.force,
            )
    except Exception as exc:  # noqa: BLE001 - scheduler must fail closed on every defect.
        log.error("gex_state mirror failed: %s", exc)
        return 1
    print(json.dumps(receipt, sort_keys=True, separators=(",", ":")), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
