from pathlib import Path
import tempfile
import subprocess
import unittest

from scripts.helios_release import MARKER, ReleaseStore, metadata, shell_executable
from scripts.stamp_release import stamp


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        base = Path(self.temporary.name)
        self.store = ReleaseStore(base / 'public_html/pyweb_lab1', base / 'private')

    def tearDown(self):
        self.temporary.cleanup()

    def stage(self, release, channel='main'):
        path = Path(self.store.prepare(channel, release)['stage'])
        (path / 'index.html').write_text(MARKER, encoding='utf-8')
        stamp(path, release)
        return path

    def publish(self, release, channel='main'):
        self.stage(release, channel)
        return self.store.activate(channel, release)

    def current(self, channel='main'):
        return metadata(self.store.target(channel))['release']

    def test_previous_version_and_rollback(self):
        self.assertFalse(self.publish('v1')['has_previous'])
        self.assertTrue(self.publish('v2')['has_previous'])
        self.assertEqual(self.current(), 'v2')
        result = self.store.rollback('main')
        self.assertEqual(result['release'], 'v1')
        self.assertEqual(self.current(), 'v1')
        self.assertEqual(self.store.rollback('main')['release'], 'v2')

    def test_preview_history_is_independent_and_survives_main_publish_and_rollback(self):
        self.publish('v1')
        self.publish('p1', 'feature-abc')
        self.publish('v2')
        self.publish('p2', 'feature-abc')
        self.store.rollback('main')
        self.assertEqual(self.current(), 'v1')
        self.assertEqual(self.current('feature-abc'), 'p2')
        self.store.rollback('feature-abc')
        self.assertEqual(self.current('feature-abc'), 'p1')
        self.assertEqual(self.current(), 'v1')

    def test_preview_can_be_first_deployment(self):
        self.publish('p1', 'feature-abc')
        self.assertFalse(self.publish('v1')['has_previous'])
        self.assertEqual(self.current('feature-abc'), 'p1')

    def test_partial_upload_does_not_change_publication(self):
        self.publish('v1')
        self.store.prepare('main', 'partial')
        self.assertEqual(self.current(), 'v1')
        with self.assertRaises(ValueError):
            self.store.activate('main', 'partial')
        self.assertEqual(self.current(), 'v1')

    def test_wrong_marker_is_rejected_before_switch(self):
        self.publish('v1')
        stage = self.stage('v2')
        (stage / 'index.html').write_text('broken', encoding='utf-8')
        with self.assertRaises(ValueError):
            self.store.activate('main', 'v2')
        self.assertEqual(self.current(), 'v1')

    def test_wrong_release_id_is_rejected_before_switch(self):
        self.publish('v1')
        path = self.stage('v2')
        stamp(path, 'unexpected')
        with self.assertRaisesRegex(ValueError, 'does not match'):
            self.store.activate('main', 'v2')
        self.assertEqual(self.current(), 'v1')

    def test_reserved_preview_directory_is_rejected(self):
        self.publish('v1')
        (self.stage('v2') / 'previews').mkdir()
        with self.assertRaisesRegex(ValueError, 'reserved'):
            self.store.activate('main', 'v2')
        self.assertEqual(self.current(), 'v1')

    def test_duplicate_staging_is_rejected(self):
        self.stage('v1')
        with self.assertRaises(ValueError):
            self.stage('v1')

    def test_committed_release_id_cannot_be_reused(self):
        self.publish('v1')
        with self.assertRaisesRegex(ValueError, 'already committed'):
            self.store.prepare('main', 'v1')

    def test_corrupt_lock_refuses_to_mutate_public_site(self):
        self.publish('v1')
        (self.store.state / 'lock').write_text('invalid owner\n', encoding='ascii')
        with self.assertRaisesRegex(ValueError, 'Invalid lock owner'):
            self.store.prepare('main', 'v2')
        self.assertEqual(self.current(), 'v1')

    def test_active_lock_does_not_recover_another_operations_journal(self):
        self.publish('v1')
        self.publish('v2')
        owner = subprocess.Popen([shell_executable(), '-c', 'echo $$; read line'], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
        try:
            pid = owner.stdout.readline().strip()
            (self.store.state / 'lock').write_text(pid + ' another-operation\n', encoding='ascii')
            journal = self.store.state / 'transaction'
            journal.mkdir()
            for name, content in {'channel': 'main', 'operation': 'v2', 'had-target': 'true', 'previous': ''}.items():
                (journal / name).write_text(content + '\n', encoding='ascii')
            with self.assertRaisesRegex(ValueError, 'Another release operation'):
                self.store.prepare('main', 'v3')
            self.assertEqual(self.current(), 'v2')
            self.assertTrue((journal / 'channel').is_file())
        finally:
            owner.communicate('stop\n', timeout=5)

    def test_exception_at_each_switch_phase_restores_previous_site(self):
        self.publish('v1')
        for phase in ('old-moved', 'new-moved'):
            release = 'v2-' + phase
            self.stage(release)
            def fail(current):
                if current == phase:
                    raise RuntimeError('injected error')
            self.store.failpoint = fail
            with self.assertRaises(RuntimeError):
                self.store.activate('main', release)
            self.assertEqual(self.current(), 'v1')
            self.assertFalse((self.store.state / 'transaction').exists())
            self.store.failpoint = lambda _: None

    def test_process_interruption_at_each_phase_is_recovered_next_operation(self):
        self.publish('v1')
        for phase in ('old-moved', 'new-moved'):
            release = 'v2-' + phase
            self.stage(release)
            def kill(current):
                if current == phase:
                    raise SystemExit('simulated process kill')
            self.store.failpoint = kill
            with self.assertRaises(SystemExit):
                self.store.activate('main', release)
            self.assertTrue((self.store.state / 'transaction').exists())
            self.store.failpoint = lambda _: None
            self.store.recover()
            self.assertEqual(self.current(), 'v1')
            self.assertFalse((self.store.state / 'transaction').exists())

    def test_automatic_rollback_refuses_to_replace_different_release(self):
        self.publish('v1')
        self.publish('v2')
        with self.assertRaises(ValueError):
            self.store.rollback('main', expected_release='v3')
        self.assertEqual(self.current(), 'v2')

    def test_first_publish_interruption_removes_uncommitted_version(self):
        self.stage('v1')
        def kill(phase):
            if phase == 'new-moved':
                raise SystemExit('kill')
        self.store.failpoint = kill
        with self.assertRaises(SystemExit):
            self.store.activate('main', 'v1')
        with self.assertRaisesRegex(ValueError, 'No published version'):
            self.store.recover()
        self.assertFalse(self.store.root.exists())


if __name__ == '__main__':
    unittest.main()
