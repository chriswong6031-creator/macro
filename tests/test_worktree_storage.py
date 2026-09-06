"""Exercise real temporary Git repos; fake only the diskutil volume probe."""
import concurrent.futures
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('worktree_storage', Path(__file__).resolve().parents[1] / 'scripts/worktree_storage.py')
s = importlib.util.module_from_spec(spec)
spec.loader.exec_module(s)

class StorageTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name).resolve(); self.mount = self.base / 'SSD'; self.mount.mkdir()
        self.policy = dict(version=1, mount_point=str(self.mount), volume_uuid='approved', root=str(self.mount / 'workspaces'), min_free_bytes=0)
        self.info = dict(VolumeUUID='approved', MountPoint=str(self.mount), Internal=False, Writable=True, FilesystemType='apfs')
        probe = patch.object(s, 'volume_info', return_value=self.info); probe.start(); self.addCleanup(probe.stop)
    def git(self, repo, *args):
        return subprocess.check_output(['git', '-C', str(repo), *args], stderr=subprocess.STDOUT, text=True).strip()
    def repository(self):
        r = self.base / 'repo'; r.mkdir(); self.git(r, 'init', '-b', 'main')
        self.git(r, 'config', 'user.name', 'Test'); self.git(r, 'config', 'user.email', 'test@example.invalid')
        for name in ['src/code.py', 'data/heavy.txt', 'config/sparse_worktree.json']:
            p=r/name; p.parent.mkdir(exist_ok=True)
            p.write_text(json.dumps(dict(enabled=True, exclude_dirs=['data'])) if name.endswith('.json') else 'fixture\n')
        self.git(r,'add','.'); self.git(r,'commit','-m','fixture'); return r
    def create(self, r, name='test', session='one'):
        return s.create_worktree(self.policy, r, name, session, base='HEAD', fetch=False)
    def test_valid_root(self):
        root=s.prepare_root(self.policy); self.assertEqual(root,self.mount/'workspaces')
        self.assertEqual(root.stat().st_dev,self.mount.stat().st_dev)
    def test_bad_volume_has_no_directory_effect(self):
        for change in [dict(VolumeUUID='wrong'),dict(Internal=True),dict(Writable=False),dict(MountPoint=str(self.base)),dict(FilesystemType='exfat')]:
            with self.subTest(change=change), patch.object(s,'volume_info',return_value={**self.info,**change}):
                with self.assertRaises(s.StorageError): s.prepare_root(self.policy)
                self.assertFalse(Path(self.policy['root']).exists())
    def test_missing_mount_is_never_recreated(self):
        self.mount.rmdir()
        with self.assertRaises(s.StorageError): s.prepare_root(self.policy)
        self.assertFalse(self.mount.exists())
    def test_low_space_refuses_before_mkdir(self):
        with self.assertRaisesRegex(s.StorageError,'space'): s.prepare_root({**self.policy,'min_free_bytes':2**70})
        self.assertFalse(Path(self.policy['root']).exists())
    def test_symlinks_and_parent_escape_are_rejected(self):
        outside=self.base/'outside'; outside.mkdir(); (self.mount/'link').symlink_to(outside,target_is_directory=True)
        for root in [self.mount/'link'/'work',self.mount/'..'/'escape']:
            with self.subTest(root=root), self.assertRaises(s.StorageError): s.prepare_root({**self.policy,'root':str(root)})
        self.assertEqual(list(outside.iterdir()),[])
    def test_sparse_registered_locked_idempotent(self):
        r=self.repository(); d=self.create(r)
        self.assertTrue((d/'src/code.py').exists()); self.assertFalse((d/'data/heavy.txt').exists())
        self.assertEqual(self.git(d,'status','--porcelain'),'')
        self.assertIn('locked '+s.LOCK_REASON,self.git(r,'worktree','list','--porcelain'))
        self.assertEqual(self.create(r),d); self.assertNotEqual(self.create(r,session='two'),d)
    def test_parallel_same_session_mints_once(self):
        r=self.repository()
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool: result=list(pool.map(lambda _:self.create(r),range(2)))
        self.assertEqual(result[0],result[1]); self.assertEqual(self.git(r,'worktree','list','--porcelain').count('worktree '),2)
    def test_foreign_directory_is_preserved(self):
        r=self.repository(); s.prepare_root(self.policy); d,_=s.destination(self.policy,r,'test','one'); d.mkdir(parents=True)
        (d/'owned.txt').write_text('foreign')
        with self.assertRaisesRegex(s.StorageError,'unreceipted'): self.create(r)
        self.assertEqual((d/'owned.txt').read_text(),'foreign')
        self.assertEqual(self.git(r,'worktree','list','--porcelain').count('worktree '),1)
    def test_dirty_same_session_is_preserved(self):
        r=self.repository(); d=self.create(r); (d/'src/code.py').write_text('unfinished')
        self.assertEqual(self.create(r),d); self.assertEqual((d/'src/code.py').read_text(),'unfinished')
    def test_failed_fetch_has_no_branch_or_worktree_effect(self):
        r=self.repository(); self.git(r,'remote','add','origin',str(self.base/'missing.git')); before=self.git(r,'show-ref')
        with self.assertRaises(s.StorageError): s.create_worktree(self.policy,r,'test','one',base='main',fetch=True)
        self.assertEqual(self.git(r,'show-ref'),before); self.assertEqual(self.git(r,'worktree','list','--porcelain').count('worktree '),1)
    def test_storage_lock_does_not_hide_live_process_from_gc(self):
        from scripts import worktree_gc as gc
        r=self.repository(); d=self.create(r)
        wt=gc.Worktree(path=d, locked=True, lock_reason=s.LOCK_REASON)
        cfg={**gc.DEFAULT_CONFIG, 'min_age_days':0, '_storage_policy':self.policy}
        with patch.object(gc, 'worktree_storage', s, create=True):
            gc.classify(wt,r,cfg,{str(d):['active-test-owner']},{},True,r,0)
        self.assertEqual(wt.verdict,'LIVE_PROC')
    def test_other_git_lock_remains_protected(self):
        from scripts import worktree_gc as gc
        r=self.repository(); d=self.create(r)
        wt=gc.Worktree(path=d,locked=True,lock_reason='operator hold')
        with patch.object(gc,'worktree_storage',s,create=True):
            gc.classify(wt,r,{**gc.DEFAULT_CONFIG,'_storage_policy':self.policy},{},{},True,r,0)
        self.assertEqual(wt.verdict,'LOCKED')
    def test_gc_refuses_unavailable_external_volume_before_pruning(self):
        from scripts import worktree_gc as gc
        r=self.repository(); d=self.create(r)
        with patch.object(gc,'worktree_storage',s,create=True), patch.object(s,'volume_info',return_value={**self.info,'VolumeUUID':'wrong'}):
            result=gc.apply_deletions(r,[],{'_storage_policy':self.policy},[Path(self.policy['root'])])
        self.assertFalse(result['pruned']); self.assertTrue(result['errors'])
        self.assertTrue(d.exists())
    def test_gc_removes_safe_storage_locked_tree_without_force(self):
        from scripts import worktree_gc as gc
        r=self.repository(); d=self.create(r)
        wt=gc.Worktree(path=d,head=self.git(d,'rev-parse','HEAD'),locked=True,lock_reason=s.LOCK_REASON,verdict='SAFE_MERGED')
        with patch.object(gc,'worktree_storage',s,create=True), patch.object(gc,'proc_cwd_map',return_value={}), patch.object(gc,'_ledger_write'):
            result=gc.apply_deletions(r,[wt],{'_storage_policy':self.policy},[Path(self.policy['root'])])
        self.assertEqual(result['errors'],[]); self.assertEqual(result['deleted'],[str(d)]); self.assertFalse(d.exists())
    def test_gc_keeps_work_that_became_dirty_after_report(self):
        from scripts import worktree_gc as gc
        r=self.repository(); d=self.create(r)
        wt=gc.Worktree(path=d,head=self.git(d,'rev-parse','HEAD'),locked=True,lock_reason=s.LOCK_REASON,verdict='SAFE_MERGED')
        (d/'src/code.py').write_text('new unfinished work')
        with patch.object(gc,'worktree_storage',s,create=True), patch.object(gc,'proc_cwd_map',return_value={}), patch.object(gc,'_ledger_write'):
            result=gc.apply_deletions(r,[wt],{'_storage_policy':self.policy},[Path(self.policy['root'])])
        self.assertEqual(result['deleted'],[]); self.assertTrue(result['errors'])
        self.assertIn('locked '+s.LOCK_REASON,self.git(r,'worktree','list','--porcelain'))
        self.assertEqual((d/'src/code.py').read_text(),'new unfinished work')
    def test_native_external_checkout_is_sparsified_and_locked(self):
        r=self.repository(); root=s.prepare_root(self.policy); d=root/'codex'/'native'; d.parent.mkdir()
        self.git(r,'worktree','add','--detach',str(d),'HEAD')
        self.assertTrue((d/'data/heavy.txt').exists())
        self.assertTrue(s.protect_worktree(self.policy,d))
        self.assertFalse((d/'data/heavy.txt').exists())
        self.assertIn('locked '+s.LOCK_REASON,self.git(r,'worktree','list','--porcelain'))
    def test_existing_primary_checkout_is_unchanged_at_startup(self):
        r=self.repository()
        self.assertFalse(s.protect_worktree(self.policy,r))
        self.assertTrue((r/'data/heavy.txt').exists())
    def test_audit_checkout_is_not_a_client_session(self):
        from scripts import worktree_sparse as sparse, worktree_storage as storage
        r=self.repository(); root=s.prepare_root(self.policy); d=root/'audit'/'native'; d.parent.mkdir()
        self.git(r,'worktree','add','--detach',str(d),'HEAD')
        with patch.object(storage,'load_policy',return_value=self.policy), patch.object(storage,'volume_info',return_value=self.info):
            self.assertFalse(sparse.is_session_worktree(d))
        self.assertFalse(s.protect_worktree(self.policy,d))
        self.assertTrue((d/'data/heavy.txt').exists())
    def test_codex_auto_entry_point_protects_external_checkout(self):
        from scripts import worktree_sparse as sparse, worktree_storage as storage
        r=self.repository(); root=s.prepare_root(self.policy); d=root/'codex'/'native'; d.parent.mkdir()
        self.git(r,'worktree','add','--detach',str(d),'HEAD')
        with patch.object(storage,'load_policy',return_value=self.policy), patch.object(storage,'volume_info',return_value=self.info):
            self.assertEqual(sparse.auto_profile(d),0)
        self.assertFalse((d/'data/heavy.txt').exists())
        self.assertIn('locked '+s.LOCK_REASON,self.git(r,'worktree','list','--porcelain'))
    def test_gc_relocks_missing_registration_after_remove_failure_or_exception(self):
        from scripts import worktree_gc as gc
        r=self.repository()
        for raises in (False, True):
            with self.subTest(raises=raises):
                d=self.create(r,session=str(raises))
                wt=gc.Worktree(path=d,head=self.git(d,'rev-parse','HEAD'),locked=True,lock_reason=s.LOCK_REASON,verdict='SAFE_MERGED')
                original=gc._git
                def disappear(repo,*args,**kwargs):
                    if args[:2] == ('worktree','remove'):
                        d.rename(d.with_name(d.name+'-disconnected'))
                        if raises:
                            raise OSError('simulated disconnect')
                        return 1,'','simulated disconnect'
                    return original(repo,*args,**kwargs)
                with patch.object(gc,'worktree_storage',s), patch.object(gc,'proc_cwd_map',return_value={}), patch.object(gc,'_ledger_write'), patch.object(gc,'_git',side_effect=disappear):
                    result=gc.apply_deletions(r,[wt],{'_storage_policy':self.policy},[Path(self.policy['root'])])
                self.assertEqual(result['deleted'],[]); self.assertTrue(result['errors'])
                record=next(w for w in gc.parse_worktree_list(self.git(r,'worktree','list','--porcelain')) if w.path==d)
                self.assertTrue(record.locked); self.assertEqual(record.lock_reason,s.LOCK_REASON)
if __name__=='__main__': unittest.main()
