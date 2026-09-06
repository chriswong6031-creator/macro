"""The installed GC wrapper must carry the storage dependency from one commit."""
from pathlib import Path
from subprocess import CompletedProcess

from scripts import worktree_gc_launchd as launcher


def test_launchd_extracts_coherent_bundle_before_running(monkeypatch):
    source = 'a' * 40
    reads = []
    def git(*args):
        if args == ('rev-parse', '--verify', 'origin/main^{commit}'):
            return CompletedProcess(args, 0, source.encode(), b'')
        if args[0] == 'show':
            reads.append(args[1])
            return CompletedProcess(args, 0, b'fixture bytes', b'')
        return CompletedProcess(args, 0, b'.git', b'')
    def run(command, **kwargs):
        folder = Path(command[1]).parent
        assert (folder/'worktree_storage.py').read_bytes() == b'fixture bytes'
        assert (folder/'config.json').read_bytes() == b'fixture bytes'
        assert len(reads) == 3 and all(ref.startswith(source+':') for ref in reads)
        return CompletedProcess(command, 0)
    monkeypatch.setattr(launcher, '_git', git)
    monkeypatch.setattr(launcher.subprocess, 'run', run)
    assert launcher.main() == 0


def test_missing_storage_dependency_refuses_before_deletion(monkeypatch):
    def git(*args):
        if args[0] == 'show' and args[1].endswith(':scripts/worktree_storage.py'):
            return CompletedProcess(args, 1, b'', b'missing')
        return CompletedProcess(args, 0, b'a'*40, b'')
    monkeypatch.setattr(launcher, '_git', git)
    monkeypatch.setattr(launcher.subprocess, 'run', lambda *a, **k: (_ for _ in ()).throw(AssertionError('must not run GC')))
    assert launcher.main() == 1
