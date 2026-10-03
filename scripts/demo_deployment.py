"""Локальная демонстрация того же хранилища релизов, что используется на Helios.

Не подключается к SSH и не измеряет производительность реального хостинга.
"""

import argparse
from datetime import datetime, timezone
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import shutil
import tempfile
import threading
import time
from urllib.error import HTTPError
from urllib.request import urlopen

from helios_release import ReleaseStore, metadata
from smoke_test import check_directory, check_url
from stamp_release import stamp


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def demonstrate(source):
    check_directory(source)
    events = []
    with tempfile.TemporaryDirectory(prefix='pyweb-release-demo-') as temporary:
        base = Path(temporary)
        store = ReleaseStore(base / 'public_html/pyweb_lab1', base / 'private')
        store.root.parent.mkdir(parents=True)
        server = ThreadingHTTPServer(('127.0.0.1', 0), partial(QuietHandler, directory=str(store.root.parent)))
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        url = f'http://127.0.0.1:{server.server_port}/pyweb_lab1/'

        def stage(release, channel='main'):
            path = Path(store.prepare(channel, release)['stage'])
            shutil.copytree(source, path, dirs_exist_ok=True)
            stamp(path, release, channel)
            return path

        def health(channel='main'):
            info = metadata(store.target(channel))
            target_url = url if channel == 'main' else url + 'previews/' + channel + '/'
            check_url(target_url, info['marker'])
            return info['release']

        def event(name, started, **details):
            events.append({'step': name, 'outcome': 'passed', 'seconds': round(time.perf_counter() - started, 6), **details})

        try:
            for release in ('demo-v1', 'demo-v2'):
                started = time.perf_counter()
                stage(release)
                store.activate('main', release)
                assert health() == release
                event('publish-' + release, started, http_status=200, release=release)
                if release == 'demo-v1':
                    stage('preview-v1', 'feature-demo')
                    store.activate('feature-demo', 'preview-v1')

            started = time.perf_counter()
            assert health('feature-demo') == 'preview-v1'
            store.rollback('main', expected_release='demo-v2')
            assert health() == 'demo-v1'
            assert health('feature-demo') == 'preview-v1'
            event('rollback-v2-to-v1', started, http_status=200, release='demo-v1', preview_preserved=True)

            started = time.perf_counter()
            bad = stage('broken-v3')
            for path in (bad / 'assets' / 'javascripts').glob('bundle*.js'):
                path.unlink()  # Only an explicitly identified fixture inside this temporary release.
            store.activate('main', 'broken-v3')
            try:
                health()
            except RuntimeError as error:
                failure = str(error)
            else:
                raise AssertionError('Broken release unexpectedly passed healthcheck')
            store.rollback('main', expected_release='broken-v3')
            assert health() == 'demo-v1'
            event('failed-healthcheck-and-rollback', started, expected_failure=failure, restored_release='demo-v1')

            started = time.perf_counter()
            partial_stage = Path(store.prepare('main', 'partial-upload')['stage'])
            shutil.copyfile(source / 'index.html', partial_stage / 'index.html')
            assert health() == 'demo-v1'
            event('interrupted-upload-keeps-public-site', started, release='demo-v1', http_status=200)

            for phase in ('old-moved', 'new-moved'):
                started = time.perf_counter()
                release = 'interrupted-' + phase
                stage(release)
                def kill(current):
                    if current == phase:
                        raise SystemExit('Injected process interruption')
                store.failpoint = kill
                try:
                    store.activate('main', release)
                except SystemExit:
                    pass
                else:
                    raise AssertionError('Interruption was not injected')
                assert (store.state / 'transaction').is_dir()
                if phase == 'old-moved':
                    try:
                        with urlopen(url, timeout=5) as response:
                            interrupted_status = response.status
                    except HTTPError as error:
                        interrupted_status = error.code
                    assert interrupted_status == 404
                else:
                    interrupted_status = 200
                    assert health() == release
                store.failpoint = lambda _: None
                store.recover()
                assert health() == 'demo-v1'
                event('recover-after-' + phase, started, interrupted_http_status=interrupted_status, recovered_http_status=200, release='demo-v1')
        finally:
            server.shutdown()
            server.server_close()
            worker.join(timeout=5)
    return {'scope': 'local filesystem + HTTP; not live Helios or GitHub Pages', 'date_utc': datetime.now(timezone.utc).isoformat(), 'events': events}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--site-dir', type=Path, default=Path('site'))
    parser.add_argument('--report', type=Path, default=Path('_build/rollback-demo.json'))
    args = parser.parse_args()
    result = demonstrate(args.site_dir.resolve())
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
