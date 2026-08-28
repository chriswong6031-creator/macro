"""Sentry wiring contract (app/observability.py).

The point of every test here is the same one: observability must never be the
reason the serving tier fails to boot. The API calls ``init_sentry`` before the
FastAPI object exists, so an exception, a hang, or a NaN handed to the SDK is
an unbootable /api — not a missing breadcrumb.
"""
from __future__ import annotations

import builtins
import logging
import importlib
import sys

import pytest


@pytest.fixture()
def obs(monkeypatch):
    """A freshly imported module so the ``_INITIALIZED`` latch starts down."""
    for var in (
        "SENTRY_DSN", "SENTRY_ENVIRONMENT", "SENTRY_RELEASE",
        "SENTRY_TRACES_SAMPLE_RATE", "SENTRY_PROFILE_SESSION_SAMPLE_RATE",
        "SENTRY_SEND_DEFAULT_PII", "SENTRY_ENABLE_LOGS",
    ):
        monkeypatch.delenv(var, raising=False)
    sys.modules.pop("app.observability", None)
    module = importlib.import_module("app.observability")
    yield module
    sys.modules.pop("app.observability", None)


class _FakeSDK:
    def __init__(self, raises=None):
        self.calls: list[dict] = []
        self._raises = raises
        self.tags: dict[str, str] = {}

    def init(self, **kwargs):
        self.calls.append(kwargs)
        if self._raises is not None and len(self.calls) == 1:
            raise self._raises

    def set_tag(self, key, value):
        self.tags[key] = value


def _install(monkeypatch, sdk):
    monkeypatch.setitem(sys.modules, "sentry_sdk", sdk)


def test_no_dsn_is_a_noop(obs, monkeypatch):
    """The default local/dev state: no DSN, no init, no exception."""
    _install(monkeypatch, _FakeSDK())
    assert obs.init_sentry("macro-api") is False
    assert obs.sentry_armed() is False
    assert sys.modules["sentry_sdk"].calls == []


def test_missing_sdk_does_not_raise(obs, monkeypatch):
    """A venv whose pip step has not landed yet must still boot the API."""
    monkeypatch.setenv("SENTRY_DSN", "https://k@o1.ingest.us.sentry.io/2")
    monkeypatch.delitem(sys.modules, "sentry_sdk", raising=False)

    real_import = builtins.__import__

    def _no_sentry(name, *args, **kwargs):
        if name == "sentry_sdk":
            raise ImportError("No module named 'sentry_sdk'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _no_sentry)
    assert obs.init_sentry("macro-api") is False
    assert obs.sentry_armed() is False


def test_init_failure_does_not_raise(obs, monkeypatch):
    """A malformed DSN makes sentry_sdk.init raise. That must not reach uvicorn."""
    monkeypatch.setenv("SENTRY_DSN", "not-a-dsn")
    _install(monkeypatch, _FakeSDK(raises=ValueError("Unsupported scheme")))
    assert obs.init_sentry("macro-api") is False
    assert obs.sentry_armed() is False


def test_arms_with_conservative_defaults(obs, monkeypatch):
    """Errors at 100%; traces sampled; profiling OFF unless the operator asks."""
    monkeypatch.setenv("SENTRY_DSN", "https://k@o1.ingest.us.sentry.io/2")
    monkeypatch.setenv("SENTRY_RELEASE", "deadbeef")
    sdk = _FakeSDK()
    _install(monkeypatch, sdk)

    assert obs.init_sentry("macro-api") is True
    assert obs.sentry_armed() is True

    (opts,) = sdk.calls
    assert opts["dsn"] == "https://k@o1.ingest.us.sentry.io/2"
    assert opts["environment"] == "production"
    assert opts["release"] == "deadbeef"
    assert opts["send_default_pii"] is True
    assert opts["enable_logs"] is True
    # The quickstart's 1.0/1.0 would trace every /api/flow/* poll on a 1-2 vCPU
    # droplet. Errors are unsampled regardless of these two.
    assert opts["traces_sample_rate"] == 0.1
    assert opts["profile_session_sample_rate"] == 0.0
    assert sdk.tags == {"component": "macro-api"}


def test_second_call_is_latched(obs, monkeypatch):
    """uvicorn reload / a lane that double-arms must not re-init the SDK."""
    monkeypatch.setenv("SENTRY_DSN", "https://k@o1.ingest.us.sentry.io/2")
    sdk = _FakeSDK()
    _install(monkeypatch, sdk)
    assert obs.init_sentry("macro-api") is True
    assert obs.init_sentry("macro-api") is False
    assert len(sdk.calls) == 1


def test_typeerror_retries_without_newer_kwargs(obs, monkeypatch):
    """An older wheel that rejects `enable_logs` still gets errors reporting."""
    monkeypatch.setenv("SENTRY_DSN", "https://k@o1.ingest.us.sentry.io/2")
    sdk = _FakeSDK(raises=TypeError("unexpected keyword argument 'enable_logs'"))
    _install(monkeypatch, sdk)

    assert obs.init_sentry("macro-api") is True
    assert len(sdk.calls) == 2
    retry = sdk.calls[1]
    assert "enable_logs" not in retry
    assert "profile_session_sample_rate" not in retry
    assert retry["dsn"] == "https://k@o1.ingest.us.sentry.io/2"


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("1.0", 1.0),
        ("0", 0.0),
        ("2.5", 1.0),      # clamped up-side
        ("-1", 0.0),       # clamped down-side
        ("", 0.1),         # empty -> default
        ("banana", 0.1),   # unparseable -> default
        ("nan", 0.1),      # NaN fails every comparison; a naive range guard
                           # would fail OPEN and hand NaN to the SDK
        ("inf", 1.0),      # finite clamp still applies
    ],
)
def test_sample_rate_parsing(obs, monkeypatch, raw, expected):
    monkeypatch.setenv("SENTRY_TRACES_SAMPLE_RATE", raw)
    assert obs._rate("SENTRY_TRACES_SAMPLE_RATE", 0.1) == expected


@pytest.mark.parametrize(
    "raw,expected",
    [("1", True), ("0", False), ("true", True), ("no", False),
     ("", True), ("garbage", False)],
)
def test_flag_parsing(obs, monkeypatch, raw, expected):
    monkeypatch.setenv("SENTRY_SEND_DEFAULT_PII", raw)
    assert obs._flag("SENTRY_SEND_DEFAULT_PII", True) is expected


def test_armed_banner_reaches_stdout_not_just_the_logger(obs, monkeypatch, capsys):
    """The runbook's verification step greps the journal. Pin the mechanism.

    FOUND LIVE 2026-08-20 right after #6115 deployed: the arm line was a
    `log.info` and never reached `journalctl -u macro-api`, because uvicorn
    configures only its own three loggers and leaves root at WARNING. The
    documented verification could not work. Asserting via capsys (NOT caplog)
    is the whole point — caplog would pass on the broken version.
    """
    monkeypatch.setenv("SENTRY_DSN", "https://k@o1.ingest.us.sentry.io/2")
    monkeypatch.setenv("SENTRY_RELEASE", "deadbeef")
    _install(monkeypatch, _FakeSDK())

    assert obs.init_sentry("macro-api") is True
    out = capsys.readouterr().out
    assert "Sentry armed for macro-api" in out
    # The operator reads these three off the banner to confirm the box is on
    # the settings they think it is.
    assert "env=production" in out
    assert "release=deadbeef" in out
    assert "traces=0.1" in out


def test_disabled_banner_also_reaches_stdout(obs, capsys):
    """"Why is Sentry dark?" must be answerable from the journal alone."""
    assert obs.init_sentry("macro-api") is False
    assert "SENTRY_DSN unset" in capsys.readouterr().out


def test_banner_survives_a_root_logger_pinned_at_warning(obs, monkeypatch, capsys):
    """Reproduce uvicorn's actual config: root at WARNING, INFO suppressed."""
    root = logging.getLogger()
    prev = root.level
    root.setLevel(logging.WARNING)
    try:
        monkeypatch.setenv("SENTRY_DSN", "https://k@o1.ingest.us.sentry.io/2")
        _install(monkeypatch, _FakeSDK())
        assert obs.init_sentry("macro-api") is True
        assert logging.getLogger("macro.observability").getEffectiveLevel() == logging.WARNING
        assert "Sentry armed for macro-api" in capsys.readouterr().out
    finally:
        root.setLevel(prev)


def test_pii_and_logs_can_be_switched_off(obs, monkeypatch):
    """The operator's kill switches for header/IP capture and log forwarding."""
    monkeypatch.setenv("SENTRY_DSN", "https://k@o1.ingest.us.sentry.io/2")
    monkeypatch.setenv("SENTRY_SEND_DEFAULT_PII", "0")
    monkeypatch.setenv("SENTRY_ENABLE_LOGS", "0")
    monkeypatch.setenv("SENTRY_ENVIRONMENT", "staging")
    sdk = _FakeSDK()
    _install(monkeypatch, sdk)

    assert obs.init_sentry("macro-api") is True
    (opts,) = sdk.calls
    assert opts["send_default_pii"] is False
    assert opts["enable_logs"] is False
    assert opts["environment"] == "staging"
