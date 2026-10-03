import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from scripts.deploy_helios import Config, branch_channel, deploy, parse_remote_output, remote_action
from scripts.stamp_release import stamp
from scripts.helios_release import MARKER


ENV = {
    'HELIOS_HOST': 'helios.cs.ifmo.ru',
    'HELIOS_PORT': '2222',
    'HELIOS_USER': 's123456',
    'HELIOS_DEPLOY_PATH': '/home/studs/s123456/public_html/pyweb_lab1',
    'HELIOS_SITE_URL': 'https://se.ifmo.ru/~s123456/pyweb_lab1/',
    'HELIOS_SSH_KEY': 'test key, not a credential',
    'HELIOS_KNOWN_HOSTS': 'test host key, not a credential',
}


class HeliosTests(unittest.TestCase):
    def test_ssh_sends_only_shell_sources_and_never_runs_remote_python(self):
        with patch.dict(os.environ, ENV, clear=True):
            config = Config.from_environment()
        reply = 'release=test-release\nmarker=PYWEB_LAB1_RELEASE:test-release\nhas_previous=true\n'
        with patch('scripts.deploy_helios.subprocess.run', return_value=subprocess.CompletedProcess([], 0, reply, '')) as run:
            result = remote_action(config, 'activate', 'main', 'test-release')
            args = run.call_args.args[0]
            source = run.call_args.kwargs['input']
            self.assertTrue(args[-1].startswith('sh -s -- activate '))
            self.assertNotIn('python3', args[-1])
            self.assertNotIn('import ', source)
            self.assertIn('switch_release()', source)
            self.assertTrue(result['has_previous'])

    def test_remote_protocol_rejects_banner_duplicate_and_invalid_boolean(self):
        for output in ('login banner\nrelease=v1\n', 'release=v1\nrelease=v2\n', 'has_previous=maybe\n', ''):
            with self.subTest(output=output), self.assertRaises(ValueError):
                parse_remote_output(output)

    def test_remote_protocol_converts_false_to_boolean(self):
        self.assertIs(parse_remote_output('has_previous=false\n')['has_previous'], False)

    def fixture(self, root):
        (root / 'index.html').write_text(MARKER, encoding='utf-8')
        stamp(root, 'test-release')

    def test_branch_channels_are_safe_stable_and_distinct(self):
        self.assertEqual(branch_channel('main'), 'main')
        self.assertEqual(branch_channel('master', 'master'), 'main')
        values = [branch_channel(b) for b in ('feature/a', 'feature-a', 'Feature/A', 'фича', 'a' * 200)]
        self.assertEqual(len(set(values)), len(values))
        for value in values:
            self.assertRegex(value, r'^[a-z0-9-]{1,53}$')
        self.assertEqual(branch_channel('feature/a'), branch_channel('feature/a'))
    def test_accepts_only_account_project_directories(self):
        for path in ('/home/studs/s123456/public_html/pyweb_lab1', '/export/home/studs/s123456/public_html/pyweb_lab1/'):
            with self.subTest(path=path), patch.dict(os.environ, ENV | {'HELIOS_DEPLOY_PATH': path}, clear=True):
                self.assertEqual(Config.from_environment().path, path.rstrip('/'))

    def test_rejects_broad_foreign_traversal_and_shell_paths(self):
        paths = (
            '/', '/home/studs/s123456', '/home/studs/s123456/public_html',
            '/home/studs/s999999/public_html/pyweb_lab1',
            '/home/studs/s123456/public_html/pyweb_lab1/..',
            '/home/studs/s123456/public_html/other',
            '/home/studs/s123456/public_html/pyweb_lab1; echo unsafe',
        )
        for path in paths:
            with self.subTest(path=path), patch.dict(os.environ, ENV | {'HELIOS_DEPLOY_PATH': path}, clear=True):
                with self.assertRaisesRegex(ValueError, 'HELIOS_DEPLOY_PATH'):
                    Config.from_environment()

    def test_rejects_invalid_connection_parameters(self):
        values = {'HELIOS_HOST': '-oProxyCommand=unsafe', 'HELIOS_USER': 'root', 'HELIOS_PORT': '65536', 'HELIOS_SITE_URL': 'https://se.ifmo.ru/'}
        for field, value in values.items():
            with self.subTest(field=field), patch.dict(os.environ, ENV | {field: value}, clear=True):
                with self.assertRaises(ValueError):
                    Config.from_environment()

    def test_unexpected_physical_path_never_starts_rsync(self):
        with patch.dict(os.environ, ENV, clear=True):
            config = Config.from_environment()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.fixture(root)
            with patch('scripts.deploy_helios.remote_action', return_value={'stage': '/home/studs/s123456/public_html'}), patch('scripts.deploy_helios.subprocess.run') as run:
                with self.assertRaisesRegex(ValueError, 'Unexpected remote staging path'):
                    deploy(config, root, release='test-release')
                run.assert_not_called()

    def test_remote_validation_failure_never_starts_rsync(self):
        with patch.dict(os.environ, ENV, clear=True):
            config = Config.from_environment()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.fixture(root)
            with patch('scripts.deploy_helios.subprocess.run', side_effect=subprocess.CalledProcessError(1, 'ssh', stderr='Project directory must not be a symbolic link')) as run:
                with self.assertRaises(subprocess.CalledProcessError):
                    deploy(config, root, release='test-release')
                self.assertEqual(run.call_count, 1)

    def test_rsync_uses_validated_physical_target_and_receiver_guard(self):
        canonical = '/export/home/studs/s123456/.pyweb_lab1-deploy/staging/test-release'
        with patch.dict(os.environ, ENV, clear=True):
            config = Config.from_environment()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.fixture(root)
            with patch('scripts.deploy_helios.remote_action', side_effect=[{'stage': canonical}, {'release': 'test-release', 'marker': MARKER}]) as remote, patch('scripts.deploy_helios.subprocess.run') as run:
                deploy(config, root, release='test-release')
                args = run.call_args.args[0]
                self.assertEqual(args[0], 'rsync')
                self.assertEqual(args[-1], f's123456@helios.cs.ifmo.ru:{canonical}/')
                receiver = args[args.index('--rsync-path') + 1]
                self.assertIn('test ! -L', receiver)
                self.assertIn('pwd -P', receiver)
                self.assertNotIn('--delete', args)
                self.assertEqual(remote.call_args.args[1], 'activate')

    def test_interrupted_rsync_never_activates_release(self):
        with patch.dict(os.environ, ENV, clear=True):
            config = Config.from_environment()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.fixture(root)
            stage = '/home/studs/s123456/.pyweb_lab1-deploy/staging/test-release'
            with patch('scripts.deploy_helios.remote_action', return_value={'stage': stage}) as remote, patch('scripts.deploy_helios.subprocess.run', side_effect=subprocess.CalledProcessError(23, 'rsync')):
                with self.assertRaises(subprocess.CalledProcessError):
                    deploy(config, root, release='test-release')
                self.assertEqual(remote.call_count, 1)
                self.assertEqual(remote.call_args.args[1], 'prepare')


if __name__ == '__main__':
    unittest.main()
