import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
import zipfile

spec = importlib.util.spec_from_file_location('build_release', Path(__file__).resolve().parents[1] / 'tools/build_release.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.files = {'image/character/a.png': b'A', 'image/ar/a.png': b'AR',
                      **{f'index/{name}.json': b'{}' for name in ('ui', 'characters', 'ar')}}

    def test_full_and_delta_have_consistent_inventory_and_independent_archive_hashes(self):
        target = dict(self.files)
        del target['image/character/a.png']
        target['image/character/renamed.png'] = b'A'
        target['index/ui.json'] = b'{"new":1}'
        release = builder.build(self.root, 'B', target, 'A', self.files)
        for package in release['packages']:
            archive = self.root / package['name']
            self.assertEqual(builder.sha(archive.read_bytes()), package['sha256'])
            self.assertEqual(archive.stat().st_size, package['size'])
            with zipfile.ZipFile(archive) as z:
                manifest = json.loads(z.read(builder.MANIFEST))
                self.assertEqual(manifest, package['manifest'])
                self.assertEqual(set(z.namelist()), set(manifest['changed']) | {builder.MANIFEST})
                self.assertEqual(manifest['files'], builder.inventory(target))
        delta = release['packages'][1]['manifest']
        self.assertEqual(delta['baseContentId'], builder.content_id(builder.inventory(self.files)))
        self.assertEqual(delta['deleted'], ['image/character/a.png'])
        self.assertEqual(set(delta['changed']), {'image/character/renamed.png', 'index/ui.json'})

    def test_deletion_only_and_noop_deltas_are_valid_archives(self):
        before = dict(self.files, **{'image/character/old.png': b'old'})
        release = builder.build(self.root, 'B', self.files, 'A', before)
        self.assertEqual(release['packages'][1]['manifest']['changed'], [])
        self.assertEqual(release['packages'][1]['manifest']['deleted'], ['image/character/old.png'])
        release = builder.build(self.root, 'C', self.files, 'B', self.files)
        self.assertEqual(release['packages'][1]['manifest']['changed'], [])
        self.assertEqual(release['packages'][1]['manifest']['deleted'], [])

    def test_first_release_and_same_tag_republish(self):
        first = builder.build(self.root, 'A', self.files)
        self.assertEqual(len(first['packages']), 1)
        self.assertEqual((self.root / 'mah_res-full-A.zip').read_bytes(), (self.root / 'mah_res-hotfix-A.zip').read_bytes())
        second = builder.build(self.root, 'A', dict(self.files, **{'index/ui.json': b'[]'}))
        self.assertNotEqual(first['contentId'], second['contentId'])

    def test_bad_paths_and_incomplete_target_fail(self):
        for name in ['image/../outside', 'image/a\tb.png', 'image/./a.png', 'image/a\\b.png']:
            with self.assertRaises(ValueError):
                builder.build(self.root, 'A', dict(self.files, **{name: b'x'}))
        with self.assertRaises(KeyError):
            builder.build(self.root, 'A', {'image/ar/a.png': b'AR'})

    def test_git_source_is_pinned_and_ignores_dirty_worktree(self):
        def git(*args):
            return subprocess.check_output(['git', '-C', str(self.root), *args], stderr=subprocess.STDOUT)
        git('init')
        for name, data in self.files.items():
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        git('add', '.')
        git('-c', 'user.name=Test', '-c', 'user.email=test@example.invalid', 'commit', '-m', 'fixture')
        (self.root / 'image/character/a.png').write_bytes(b'dirty')
        self.assertEqual(builder.git_files(self.root, 'HEAD'), self.files)
        with self.assertRaises(subprocess.CalledProcessError):
            builder.git_files(self.root, 'missing-ref')


if __name__ == '__main__':
    unittest.main()
