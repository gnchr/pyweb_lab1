import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from scripts.deploy_helios import Config, deploy


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
            (root / 'index.html').write_text('fixture', encoding='utf-8')
            with patch('scripts.deploy_helios.subprocess.run') as run:
                run.return_value = subprocess.CompletedProcess([], 0, '/home/studs/s123456/public_html\n', '')
                with self.assertRaisesRegex(ValueError, 'unexpected deployment path'):
                    deploy(config, root)
                self.assertEqual(run.call_count, 1)

    def test_remote_validation_failure_never_starts_rsync(self):
        with patch.dict(os.environ, ENV, clear=True):
            config = Config.from_environment()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'index.html').write_text('fixture', encoding='utf-8')
            with patch('scripts.deploy_helios.subprocess.run', side_effect=subprocess.CalledProcessError(1, 'ssh', stderr='Project directory must not be a symbolic link')) as run:
                with self.assertRaises(subprocess.CalledProcessError):
                    deploy(config, root)
                self.assertEqual(run.call_count, 1)

    def test_rsync_uses_validated_physical_target_and_receiver_guard(self):
        canonical = '/export/home/studs/s123456/public_html/pyweb_lab1'
        with patch.dict(os.environ, ENV, clear=True):
            config = Config.from_environment()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'index.html').write_text('fixture', encoding='utf-8')
            with patch('scripts.deploy_helios.subprocess.run') as run:
                run.return_value = subprocess.CompletedProcess([], 0, canonical + '\n', '')
                deploy(config, root)
                args = run.call_args.args[0]
                self.assertEqual(args[0], 'rsync')
                self.assertEqual(args[-1], f's123456@helios.cs.ifmo.ru:{canonical}/')
                receiver = args[args.index('--rsync-path') + 1]
                self.assertIn('test ! -L', receiver)
                self.assertIn('pwd -P', receiver)


if __name__ == '__main__':
    unittest.main()
