import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.smoke_test import MARKER, check_directory, check_url, fetch


HTML = f'''<html><head>
<link rel="stylesheet" href="assets/main.css">
<script src="assets/main.js"></script>
<script id="__config" type="application/json">{{"search":"assets/workers/search.js"}}</script>
</head><body><!-- {MARKER} --></body></html>'''


class SmokeTests(unittest.TestCase):
    def test_missing_search_worker_fails_directory_check(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'assets/workers').mkdir(parents=True)
            (root / 'search').mkdir()
            (root / 'index.html').write_text(HTML, encoding='utf-8')
            (root / 'assets/main.css').write_text('body {}', encoding='utf-8')
            (root / 'assets/main.js').write_text('// fixture', encoding='utf-8')
            (root / 'search/search_index.json').write_text(json.dumps({'docs': [{}]}), encoding='utf-8')
            with self.assertRaisesRegex(RuntimeError, 'search.js'):
                check_directory(root)
            (root / 'assets/workers/search.js').write_text('// worker fixture', encoding='utf-8')
            check_directory(root)

    def test_missing_search_worker_fails_http_check(self):
        calls = []

        def response(url, **kwargs):
            calls.append(url)
            if url.endswith('search.js'):
                raise RuntimeError('HTTP 404: search worker')
            return HTML if url.endswith('/pyweb_lab1/') else '{}'

        with patch('scripts.smoke_test.fetch', side_effect=response):
            with self.assertRaisesRegex(RuntimeError, '404'):
                check_url('https://example.org/~s123456/pyweb_lab1/')
        self.assertIn('https://example.org/~s123456/pyweb_lab1/assets/workers/search.js', calls)

    def test_resources_cannot_escape_public_subdirectory(self):
        html = HTML.replace('assets/main.css', '../main.css')
        with patch('scripts.smoke_test.fetch', return_value=html):
            with self.assertRaisesRegex(RuntimeError, 'подкаталога'):
                check_url('https://example.org/~s123456/pyweb_lab1/')

    def test_marker_is_retried_while_old_page_is_served(self):
        with patch('scripts.smoke_test.urlopen') as request, patch('scripts.smoke_test.time.sleep'):
            response = request.return_value.__enter__.return_value
            response.status = 200
            response.read.side_effect = [b'old page', HTML.encode('utf-8')]
            self.assertEqual(fetch('https://example.org/', expected_marker=MARKER), HTML)
            self.assertEqual(request.call_count, 2)


if __name__ == '__main__':
    unittest.main()
