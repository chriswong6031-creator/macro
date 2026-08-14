from __future__ import annotations

import ast
import os
import stat
import subprocess
from pathlib import Path

import pytest

from ops.launchd import run_options_sparse_selector_verified as bootstrap


ROOT = Path(__file__).resolve().parents[1]


def _write(path: Path, body: bytes = b"x", *, executable: bool = False) -> Path:
    path.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
    path.write_bytes(body)
    path.chmod(0o755 if executable else 0o644)
    return path


def _marked_target(tmp_path: Path) -> Path:
    target = tmp_path / "disposable"
    target.mkdir(mode=0o700)
    _write(target / bootstrap.DISPOSABLE_MARKER, bootstrap.DISPOSABLE_MARKER_BODY)
    (target / bootstrap.DISPOSABLE_MARKER).chmod(0o600)
    return target


def _source_runtime(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    source = tmp_path / "plane"
    source.mkdir(mode=0o755)
    _write(source / bootstrap.RUNTIME_PYTHON_RELATIVE, b"python", executable=True)
    _write(source / bootstrap.RUNTIME_LIBPYTHON_RELATIVE, b"libpython", executable=True)
    _write(source / bootstrap.RUNTIME_TIMEZONE_RELATIVE / "America/New_York", b"tzif")
    _write(source / bootstrap.RUNTIME_STDLIB_RELATIVE / "os.py", b"stdlib")
    _write(source / bootstrap.RUNTIME_STDLIB_RELATIVE / "lib-dynload" / "_core.so", b"native", executable=True)
    for path in bootstrap.RUNTIME_DEPENDENCY_PATHS:
        if path.suffix == ".py":
            _write(source / path, b"dependency")
        else:
            _write(source / path / "__init__.py", b"dependency")
    monkeypatch.setattr(bootstrap, "EXPECTED_RUNTIME_SOURCE", source)
    return source


def _system_native(_path: Path) -> bootstrap.NativeRecord:
    return bootstrap.NativeRecord(
        install_id=None,
        dependencies=("/usr/lib/libSystem.B.dylib",),
    )


def _mock_safe_proof(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(bootstrap, "attest_target_profile", lambda: None)
    monkeypatch.setattr(bootstrap, "_isolated_import_acceptance", lambda **_kwargs: None)
    monkeypatch.setattr(bootstrap, "_seal_native_signatures", lambda _paths: None)
    monkeypatch.setattr(bootstrap, "_native_dyld_acceptance", lambda **_kwargs: None)


def test_bootstrap_is_stdlib_only_permanently_unarmed_and_never_imports_nbbo() -> None:
    source = Path(bootstrap.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source, feature_version=(3, 9))
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        node.module or ""
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    }
    assert bootstrap.SELECTOR_RUNTIME_ARMED is False
    assert not any(name == "engine" or name.startswith("engine.") for name in imported)
    assert not any("nbbo" in name for name in imported)
    assert "rfc3339_validator" not in bootstrap.RUNTIME_REQUIRED_IMPORTS


def test_ordinary_unarmed_invocation_refuses_before_any_side_effect(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    touched = tmp_path / "must-not-exist"

    def forbidden(*_args: object, **_kwargs: object) -> None:
        touched.mkdir()
        raise AssertionError("ordinary invocation attempted a proof side effect")

    monkeypatch.setattr(bootstrap, "prove_disposable_target", forbidden)
    monkeypatch.setattr(bootstrap, "attest_target_profile", forbidden)
    monkeypatch.setenv("SELECTOR_RUNTIME_ARMED", "1")
    assert bootstrap.main(["--arm", "--target-root", str(touched)]) == 3
    assert not touched.exists()
    assert "code-unarmed" in capsys.readouterr().err


def test_target_profile_is_exact_and_requires_local_theta() -> None:
    bootstrap.attest_target_profile(
        model_probe=lambda: "Mac13,1",
        machine_probe=lambda: "arm64",
        theta_probe=lambda: None,
    )
    with pytest.raises(bootstrap.BootstrapError, match="wrong target host"):
        bootstrap.attest_target_profile(
            model_probe=lambda: "Mac14,14",
            machine_probe=lambda: "arm64",
            theta_probe=lambda: None,
        )
    with pytest.raises(bootstrap.BootstrapError, match="Theta"):
        bootstrap.attest_target_profile(
            model_probe=lambda: "Mac13,1",
            machine_probe=lambda: "arm64",
            theta_probe=lambda: (_ for _ in ()).throw(
                bootstrap.BootstrapError("local Theta is unavailable")
            ),
        )


def test_closure_is_exact_for_current_selector_core() -> None:
    assert bootstrap.EXPECTED_HOST_MODEL == "Mac13,1"
    assert bootstrap.EXPECTED_RUNTIME_SOURCE == Path("/Users/chriswong/miniconda3/envs/plane")
    assert set(path.name for path in bootstrap.RUNTIME_DEPENDENCY_PATHS) == {
        "attr",
        "attrs",
        "dateutil",
        "idna",
        "jsonschema",
        "jsonschema_specifications",
        "numpy",
        "pandas",
        "pyarrow",
        "pytz",
        "referencing",
        "rpds",
        "six.py",
        "typing_extensions.py",
    }
    assert set(bootstrap.RUNTIME_REQUIRED_IMPORTS) == {
        "attr", "attrs", "dateutil", "idna", "jsonschema", "jsonschema_specifications",
        "numpy", "pandas", "pyarrow", "pytz", "referencing", "rpds", "six", "typing_extensions",
    }


def test_provision_disposable_target_seals_exact_closure_and_keeps_python_executable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _source_runtime(tmp_path, monkeypatch)
    target = _marked_target(tmp_path)
    _mock_safe_proof(monkeypatch)
    receipt = bootstrap.prove_disposable_target(
        source_root=source,
        target_root=target,
        repo_root=ROOT,
        native_reader=_system_native,
    )
    runtime = target / bootstrap.RUNTIME_DIRECTORY
    python = runtime / bootstrap.RUNTIME_PYTHON_RELATIVE
    assert receipt["authority"] is False
    assert receipt["training"] is False
    assert receipt["imports"] == list(bootstrap.RUNTIME_REQUIRED_IMPORTS)
    assert stat.S_IMODE(os.lstat(python).st_mode) == 0o555
    assert stat.S_IMODE(os.lstat(runtime / bootstrap.RUNTIME_DEPENDENCY_PATHS[-1]).st_mode) == 0o444
    assert (target / bootstrap.MANIFEST_NAME).is_file()
    bootstrap._attest_sealed_tree(runtime, receipt["files"])


def test_source_python_symlink_is_rejected_without_cross_tree_trust(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _source_runtime(tmp_path, monkeypatch)
    python = source / bootstrap.RUNTIME_PYTHON_RELATIVE
    outside = _write(tmp_path / "outside-python", b"outside", executable=True)
    python.unlink()
    python.symlink_to(outside)
    _mock_safe_proof(monkeypatch)
    with pytest.raises(bootstrap.BootstrapError, match="unsafe"):
        bootstrap.prove_disposable_target(
            source_root=source,
            target_root=_marked_target(tmp_path),
            repo_root=ROOT,
            native_reader=_system_native,
        )


@pytest.mark.parametrize("kind", ["symlink", "hardlink", "mode"])
def test_generic_exact_read_rejects_symlink_hardlink_and_unsafe_mode(
    tmp_path: Path, kind: str
) -> None:
    source = _write(tmp_path / "source", b"source")
    if kind == "symlink":
        source.unlink()
        source.symlink_to(_write(tmp_path / "outside", b"outside"))
    elif kind == "hardlink":
        os.link(source, tmp_path / "second-link")
    else:
        source.chmod(0o666)
    with pytest.raises(bootstrap.BootstrapError, match="unsafe"):
        bootstrap._read_exact(source, label="fixture")


def test_runtime_copy_accepts_conda_hardlink_but_mints_single_link_target(
    tmp_path: Path,
) -> None:
    source = _write(tmp_path / "source", b"package payload", executable=True)
    os.link(source, tmp_path / "conda-package-cache-link")
    destination = tmp_path / "sealed/runtime-file"
    bootstrap._copy_file(source, destination)
    assert destination.read_bytes() == b"package payload"
    assert os.lstat(destination).st_nlink == 1
    assert stat.S_IMODE(os.lstat(destination).st_mode) == 0o700


def test_source_snapshot_rejects_a_torn_file_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _write(tmp_path / "source", b"source")
    real_fstat = bootstrap.os.fstat
    calls = 0

    def torn_fstat(descriptor: int) -> os.stat_result:
        nonlocal calls
        calls += 1
        value = real_fstat(descriptor)
        if calls == 2:
            fields = list(value)
            fields[6] += 1
            return os.stat_result(fields)
        return value

    monkeypatch.setattr(bootstrap.os, "fstat", torn_fstat)
    with pytest.raises(bootstrap.BootstrapError, match="changed"):
        bootstrap._read_exact(source, label="fixture")


@pytest.mark.parametrize("kind", ["symlink", "hardlink", "mode"])
def test_attestation_rejects_post_seal_symlink_hardlink_and_mode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    source = _source_runtime(tmp_path, monkeypatch)
    target = _marked_target(tmp_path)
    _mock_safe_proof(monkeypatch)
    receipt = bootstrap.prove_disposable_target(
        source_root=source, target_root=target, repo_root=ROOT, native_reader=_system_native
    )
    runtime = target / bootstrap.RUNTIME_DIRECTORY
    victim = runtime / bootstrap.RUNTIME_DEPENDENCY_PATHS[-1]
    runtime.chmod(0o755)
    victim.parent.chmod(0o755)
    if kind == "symlink":
        victim.unlink()
        victim.symlink_to(tmp_path / "outside")
    elif kind == "hardlink":
        os.link(victim, tmp_path / "second-link")
    else:
        victim.chmod(0o644)
    with pytest.raises(bootstrap.BootstrapError):
        bootstrap._attest_sealed_tree(runtime, receipt["files"])


def test_native_relocation_handles_bare_self_id_and_rewrites_conda_prefix(tmp_path: Path) -> None:
    runtime = tmp_path / "runtime"
    owner = _write(runtime / "site/libowner.dylib", b"owner", executable=True)
    target = _write(runtime / "lib/libtarget.dylib", b"target", executable=True)
    source_prefix = Path("/Users/chriswong/miniconda3/envs/plane")
    plan = bootstrap._native_relocation_plan(
        runtime,
        {
            owner: bootstrap.NativeRecord(
                "libowner.dylib",
                (str(source_prefix / "lib/libtarget.dylib"),),
                (str(source_prefix / "lib"),),
            ),
            target: bootstrap.NativeRecord("@loader_path/libtarget.dylib", ("/usr/lib/libSystem.B.dylib",)),
        },
        source_prefix=source_prefix,
    )
    assert ("id", "libowner.dylib", "@loader_path/libowner.dylib") in plan[owner]
    assert all(str(source_prefix) not in item[2] for edits in plan.values() for item in edits)
    assert any(item[0] == "change" for item in plan[owner])
    assert any(item[0] == "rpath" for item in plan[owner])


@pytest.mark.parametrize("dependency", ["@loader_path/../../escape.dylib", "libuntrusted.dylib"])
def test_native_relocation_rejects_escape_and_bare_dependency(tmp_path: Path, dependency: str) -> None:
    runtime = tmp_path / "runtime"
    owner = _write(runtime / "lib/libowner.dylib", b"owner", executable=True)
    with pytest.raises(bootstrap.BootstrapError, match="escape|bare"):
        bootstrap._native_relocation_plan(
            runtime,
            {owner: bootstrap.NativeRecord("@loader_path/libowner.dylib", (dependency,))},
        )


@pytest.mark.parametrize(
    "rpath",
    ["/opt/untrusted/lib", "@executable_path/../lib", "@loader_path/../../escape"],
)
def test_native_relocation_rejects_external_or_escaping_rpath(
    tmp_path: Path, rpath: str
) -> None:
    runtime = tmp_path / "runtime"
    owner = _write(runtime / "lib/libowner.dylib", b"owner", executable=True)
    with pytest.raises(bootstrap.BootstrapError, match="rpath|escape"):
        bootstrap._native_relocation_plan(
            runtime,
            {
                owner: bootstrap.NativeRecord(
                    "@loader_path/libowner.dylib", (), (rpath,)
                )
            },
        )


def test_otool_rpath_parser_requires_a_path_for_each_command() -> None:
    output = """Load command 1
          cmd LC_RPATH
      cmdsize 48
         path /mutable/lib (offset 12)
Load command 2
          cmd LC_LOAD_DYLIB
"""
    assert bootstrap._parse_otool_rpaths(output) == ("/mutable/lib",)
    with pytest.raises(bootstrap.BootstrapError, match="has no path"):
        bootstrap._parse_otool_rpaths("cmd LC_RPATH\ncmdsize 16\n")


def test_native_record_does_not_treat_dylib_install_id_as_a_load_edge(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    native = _write(tmp_path / "libowner.dylib", b"native", executable=True)

    def fake_run(argv: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if "-D" in argv:
            output = f"{native}:\n@rpath/libowner.dylib\n"
        elif "-L" in argv:
            output = (
                f"{native}:\n"
                "\t@rpath/libowner.dylib (compatibility version 1.0.0, current version 1.0.0)\n"
                "\t/usr/lib/libSystem.B.dylib (compatibility version 1.0.0, current version 1.0.0)\n"
            )
        else:
            output = "Load command 1\n          cmd LC_RPATH\n         path @loader_path (offset 12)\n"
        return subprocess.CompletedProcess(argv, 0, output, "")

    monkeypatch.setattr(bootstrap.subprocess, "run", fake_run)
    record = bootstrap._native_record(native)
    assert record.install_id == "@rpath/libowner.dylib"
    assert record.dependencies == ("/usr/lib/libSystem.B.dylib",)
    assert record.rpaths == ("@loader_path",)


def test_rpath_resolution_uses_owner_directory_despite_duplicate_basenames(
    tmp_path: Path,
) -> None:
    runtime = tmp_path / "runtime"
    owner = _write(runtime / "pyarrow/_owner.so", b"owner", executable=True)
    chosen = _write(runtime / "pyarrow/lib.so", b"chosen", executable=True)
    collision = _write(runtime / "pandas/lib.so", b"collision", executable=True)
    plan = bootstrap._native_relocation_plan(
        runtime,
        {
            owner: bootstrap.NativeRecord(
                "@loader_path/_owner.so", ("@rpath/lib.so",), ("@loader_path",)
            ),
            chosen: _system_native(chosen),
            collision: _system_native(collision),
        },
        source_prefix=tmp_path / "source",
    )
    assert ("change", "@rpath/lib.so", "@loader_path/lib.so") in plan[owner]


def test_exact_loader_path_rpath_is_already_sealed(tmp_path: Path) -> None:
    runtime = tmp_path / "runtime"
    owner = _write(runtime / "pyarrow/libowner.dylib", b"owner", executable=True)
    plan = bootstrap._native_relocation_plan(
        runtime,
        {
            owner: bootstrap.NativeRecord(
                "@loader_path/libowner.dylib", (), ("@loader_path",)
            )
        },
        source_prefix=tmp_path / "source",
    )
    assert plan[owner] == ()


def test_transitive_prefix_dylib_is_copied_without_scanning_unrelated_libs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _source_runtime(tmp_path, monkeypatch)
    _write(source / "lib/libneeded.dylib", b"needed", executable=True)
    _write(source / "lib/libunrelated.dylib", b"unrelated", executable=True)
    target = _marked_target(tmp_path)
    _mock_safe_proof(monkeypatch)
    relocated = False

    def reader(path: Path) -> bootstrap.NativeRecord:
        if path.name == "libpython3.12.dylib":
            dependency = (
                "@loader_path/libneeded.dylib"
                if relocated
                else str(source / "lib/libneeded.dylib")
            )
            return bootstrap.NativeRecord(None, (dependency,))
        return _system_native(path)

    def apply(_plan: object) -> None:
        nonlocal relocated
        relocated = True

    monkeypatch.setattr(bootstrap, "_apply_native_relocations", apply)

    receipt = bootstrap.prove_disposable_target(
        source_root=source, target_root=target, repo_root=ROOT, native_reader=reader
    )
    assert "lib/libneeded.dylib" in receipt["native_files"]
    assert "lib/libunrelated.dylib" not in receipt["native_files"]


def test_same_directory_conda_native_alias_becomes_regular_single_link_copy(
    tmp_path: Path,
) -> None:
    source = tmp_path / "plane"
    versioned = _write(source / "lib/libz.1.3.2.dylib", b"native", executable=True)
    alias = source / "lib/libz.1.dylib"
    alias.symlink_to(versioned.name)
    runtime = tmp_path / "runtime"
    bootstrap._copy_native_alias(
        alias,
        runtime,
        Path("lib/libz.1.dylib"),
        source_root=source,
    )
    copied = runtime / "lib/libz.1.dylib"
    assert copied.read_bytes() == b"native"
    assert not copied.is_symlink()
    assert os.lstat(copied).st_nlink == 1


def test_native_alias_may_not_escape_or_chain(tmp_path: Path) -> None:
    source = tmp_path / "plane"
    alias = source / "lib/libescape.dylib"
    alias.parent.mkdir(parents=True)
    alias.symlink_to("../outside.dylib")
    with pytest.raises(bootstrap.BootstrapError, match="escapes"):
        bootstrap._copy_native_alias(
            alias,
            tmp_path / "runtime",
            Path("lib/libescape.dylib"),
            source_root=source,
        )


def test_native_signature_seal_signs_then_strictly_verifies_every_object(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = _write(tmp_path / "a.so", b"a", executable=True)
    second = _write(tmp_path / "b.dylib", b"b", executable=True)
    commands: list[list[str]] = []

    def fake_run(argv: list[str], **_kwargs: object) -> subprocess.CompletedProcess[bytes]:
        commands.append(argv)
        return subprocess.CompletedProcess(argv, 0, b"", b"")

    monkeypatch.setattr(bootstrap.subprocess, "run", fake_run)
    bootstrap._seal_native_signatures((second, first))
    assert commands[:2] == [
        [
            "/usr/bin/codesign",
            "--force",
            "--sign",
            "-",
            "--timestamp=none",
            str(first),
        ],
        [
            "/usr/bin/codesign",
            "--force",
            "--sign",
            "-",
            "--timestamp=none",
            str(second),
        ],
    ]
    assert commands[2:] == [
        ["/usr/bin/codesign", "--verify", "--strict", str(first)],
        ["/usr/bin/codesign", "--verify", "--strict", str(second)],
    ]


def test_native_dyld_acceptance_uses_sealed_python_and_every_non_executable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime = tmp_path / "runtime"
    python = _write(
        runtime / bootstrap.RUNTIME_PYTHON_RELATIVE, b"python", executable=True
    )
    first = _write(runtime / "lib/a.dylib", b"a", executable=True)
    second = _write(runtime / "site/b.so", b"b", executable=True)
    observed: dict[str, object] = {}

    def fake_run(argv: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        observed["argv"] = argv
        observed["script"] = argv[-1]
        return subprocess.CompletedProcess(argv, 0, "", "")

    monkeypatch.setattr(bootstrap.subprocess, "run", fake_run)
    bootstrap._native_dyld_acceptance(
        python=python, runtime_root=runtime, natives=(second, python, first)
    )
    assert observed["argv"][:5] == [str(python), "-I", "-S", "-B", "-c"]  # type: ignore[index]
    assert "lib/a.dylib" in observed["script"]  # type: ignore[operator]
    assert "site/b.so" in observed["script"]  # type: ignore[operator]
    assert "bin/python3.12" not in observed["script"]  # type: ignore[operator]
    assert "ctypes.CDLL" in observed["script"]  # type: ignore[operator]


def test_isolated_import_acceptance_uses_isolated_flags_and_current_core(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    observed: dict[str, object] = {}
    runtime = tmp_path / "runtime"
    python = _write(
        runtime / bootstrap.RUNTIME_PYTHON_RELATIVE, b"python", executable=True
    )
    site_packages = runtime / bootstrap.RUNTIME_SITE_PACKAGES_RELATIVE
    site_packages.mkdir(mode=0o755, parents=True)
    _write(runtime / bootstrap.RUNTIME_TIMEZONE_RELATIVE / "America/New_York", b"tzif")

    def fake_run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        observed["argv"] = argv
        observed["script"] = argv[-1]
        return subprocess.CompletedProcess(argv, 0, "", "")

    monkeypatch.setattr(bootstrap.subprocess, "run", fake_run)
    bootstrap._isolated_import_acceptance(
        python=python, repo_root=ROOT, site_packages=site_packages
    )
    assert observed["argv"][1:4] == ["-I", "-S", "-B"]  # type: ignore[index]
    assert "engine import options_sparse_selector" in observed["script"]  # type: ignore[operator]
    for name in bootstrap.RUNTIME_REQUIRED_IMPORTS:
        assert name in observed["script"]  # type: ignore[operator]
    assert "version_info" in observed["script"]  # type: ignore[operator]
    assert "sys.path[:]" in observed["script"]  # type: ignore[operator]
    assert "sys.prefix" in observed["script"]  # type: ignore[operator]
    assert "str(source) not in str(location)" in observed["script"]  # type: ignore[operator]
    assert "zoneinfo.reset_tzpath" in observed["script"]  # type: ignore[operator]
    assert "America/New_York" in observed["script"]  # type: ignore[operator]


@pytest.mark.parametrize("unsafe", ["root-mode", "marker-mode"])
def test_disposable_root_requires_exact_private_modes(
    tmp_path: Path, unsafe: str
) -> None:
    target = _marked_target(tmp_path)
    if unsafe == "root-mode":
        target.chmod(0o755)
        message = "0700"
    else:
        (target / bootstrap.DISPOSABLE_MARKER).chmod(0o644)
        message = "0600"
    with pytest.raises(bootstrap.BootstrapError, match=message):
        bootstrap._attest_disposable_root(target)


def test_disposable_root_rejects_every_non_marker_entry(tmp_path: Path) -> None:
    target = _marked_target(tmp_path)
    _write(target / "unrelated-private-state", b"must not be reused")
    with pytest.raises(bootstrap.BootstrapError, match="unexpected entry"):
        bootstrap._attest_disposable_root(target)


@pytest.mark.parametrize("owner", ["source", "repo"])
def test_disposable_target_cannot_overlap_source_or_repo(
    tmp_path: Path, owner: str
) -> None:
    source = tmp_path / "source"
    repo = tmp_path / "repo"
    source.mkdir()
    repo.mkdir()
    parent = source if owner == "source" else repo
    target = parent / "disposable"
    target.mkdir(mode=0o700)
    _write(target / bootstrap.DISPOSABLE_MARKER, bootstrap.DISPOSABLE_MARKER_BODY)
    (target / bootstrap.DISPOSABLE_MARKER).chmod(0o600)
    with pytest.raises(bootstrap.BootstrapError, match="distinct absolute root"):
        bootstrap.prove_disposable_target(
            source_root=source,
            target_root=target,
            repo_root=repo,
            native_reader=_system_native,
        )


def test_exclusive_receipt_write_retries_partial_os_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    destination = tmp_path / "receipt.json"
    body = b"0123456789"
    real_write = bootstrap.os.write
    calls = 0

    def partial_write(descriptor: int, value: object) -> int:
        nonlocal calls
        calls += 1
        view = memoryview(value)  # type: ignore[arg-type]
        if calls == 1:
            return real_write(descriptor, view[:3])
        return real_write(descriptor, view)

    monkeypatch.setattr(bootstrap.os, "write", partial_write)
    bootstrap._write_exclusive(destination, body)
    assert destination.read_bytes() == body
    assert calls >= 2


def test_fresh_main_scope_fence_preserves_selector_core_and_excludes_producers() -> None:
    required = {
        "engine/options_sparse_selector.py",
        "tests/test_options_sparse_selector_runtime.py",
        "contracts/options/options.sparse_selector_runtime.v1.schema.json",
    }
    for path in required:
        assert (ROOT / path).is_file()
    assert not (ROOT / "scripts/run_options_sparse_selector.py").exists()
    assert not (
        ROOT / "ops/launchd/com.mastermind.optionssparseselector.plist"
    ).exists()
    for path in (
        ROOT / ".github/workflows/daily.yml",
        ROOT / "config/dag.yml",
        ROOT / "config/synapse.yml",
    ):
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        assert "options_sparse_selector" not in text
        assert "options-sparse-selector" not in text
