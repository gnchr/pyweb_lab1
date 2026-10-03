from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import yaml


class StrictLinksTests(unittest.TestCase):
    def test_invalid_links_fail_strict_build(self):
        cases = ('[bad](#missing-anchor)', '[bad](missing/)', '[bad](/missing/)')
        for markdown in cases:
            with self.subTest(markdown=markdown), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                docs = root / 'docs'
                docs.mkdir()
                (docs / 'index.md').write_text('# Fixture\n\n' + markdown, encoding='utf-8')
                config = root / 'mkdocs.yml'
                config.write_text(yaml.safe_dump({
                    'INHERIT': str(Path('mkdocs.yml').resolve()),
                    'docs_dir': str(docs), 'site_dir': str(root / 'site'),
                }), encoding='utf-8')
                result = subprocess.run(
                    [sys.executable, '-m', 'mkdocs', 'build', '--strict', '--config-file', str(config)],
                    capture_output=True, text=True, encoding='utf-8', errors='replace',
                )
                self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn('WARNING', result.stderr)
                self.assertIn('Aborted', result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
