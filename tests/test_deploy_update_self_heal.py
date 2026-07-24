"""Regression guards for production deploy reconciliation."""
from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "app" / "deploy" / "update.sh"
SCRIPT = SCRIPT_PATH.read_text(encoding="utf-8")


def test_update_script_has_valid_shell_syntax():
    subprocess.run(["bash", "-n", str(SCRIPT_PATH)], check=True)


def test_repository_noop_does_not_skip_reconciliation():
    assert '[ "$OLD" = "$NEW" ] && exit 0' not in SCRIPT
    assert 'if [ "$OLD" != "$NEW" ]; then' in SCRIPT
    assert SCRIPT.index("# Self-update:") < SCRIPT.index("API_UNIT_UPDATED=0")


def test_caddy_source_is_validated_before_install():
    validate = 'caddy validate --config "$APP_DIR/app/deploy/Caddyfile"'
    install = 'install -m 0644 "$APP_DIR/app/deploy/Caddyfile" /etc/caddy/Caddyfile'
    assert validate in SCRIPT
    assert SCRIPT.index(validate) < SCRIPT.index(install)


def test_changed_systemd_unit_forces_api_restart():
    assert "API_UNIT_UPDATED=1" in SCRIPT
    restart_condition = (
        'if [ "$API_UNIT_UPDATED" -eq 1 ] || echo "$CHANGED" | '
        "grep -qE"
    )
    assert restart_condition in SCRIPT
