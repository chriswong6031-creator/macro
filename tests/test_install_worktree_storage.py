"""Host installation preserves unrelated app settings and existing hooks."""
import json
from pathlib import Path
from unittest.mock import patch

from scripts import install_worktree_storage as installer


def test_staged_install_preserves_settings_and_records_reversible_fields(tmp_path):
    home = tmp_path / 'home'
    profile = home / 'Library/Application Support/Claude-3/claude_desktop_config.json'
    cli = home / '.claude/settings.json'
    codex = home / '.codex/hooks.json'
    old_hook = {'hooks': [{'type': 'command', 'command': 'existing-hook'}]}
    for path, content in (
        (profile, {'preferences': {'unrelated': 'keep'}, 'accountField': 'keep'}),
        (cli, {'theme': 'dark', 'hooks': {'WorktreeCreate': [old_hook]}}),
        (codex, {'description': 'keep', 'hooks': {'SessionStart': [old_hook]}}),
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(content))
    mount = tmp_path / 'SSD'; mount.mkdir()
    policy_path = home / '.config/mastermind/worktree-storage.json'
    info = dict(VolumeUUID='approved', MountPoint=str(mount), Internal=False, Writable=True, FilesystemType='apfs')
    with patch.object(Path, 'home', return_value=home), patch.object(installer.storage, 'POLICY_PATH', policy_path), patch.object(installer.storage, 'volume_info', return_value=info), patch('sys.argv', ['install', '--apply', '--without-create-hook', '--mount', str(mount), '--volume-uuid', 'approved', '--min-free-gib', '0']):
        installer.main()
    native = json.loads(profile.read_text())
    assert native['accountField'] == 'keep'
    assert native['preferences'] == {'unrelated': 'keep', 'chillingSlothLocation': {'customPath': str(mount / 'agent-workspaces/claude')}}
    claude = json.loads(cli.read_text())
    assert claude['theme'] == 'dark'
    assert claude['hooks']['WorktreeCreate'] == [old_hook]
    assert len(claude['hooks']['SessionStart']) == 1
    codex_config = json.loads(codex.read_text())
    assert codex_config['description'] == 'keep'
    assert codex_config['hooks']['SessionStart'][0] == old_hook
    assert len(codex_config['hooks']['SessionStart']) == 2
    receipt = json.loads(next((mount / 'agent-workspaces/backups').glob('*/receipt.json')).read_text())
    assert receipt['status'] == 'APPLIED'
    assert receipt['creation_hook'] == 'DEFERRED'
    assert not receipt['helper_previously_present']
    assert not receipt['policy_previously_present']
    assert receipt['changes'][0]['before'] == {'present': False, 'value': None}


def test_concurrent_settings_change_is_not_overwritten(tmp_path):
    path = tmp_path / 'config.json'; path.write_bytes(b'new writer')
    try:
        installer.write_if_unchanged(path, b'old value', b'our change')
    except RuntimeError as exc:
        assert 'concurrent settings update' in str(exc)
    else:
        raise AssertionError('concurrent update accepted')
    assert path.read_bytes() == b'new writer'
