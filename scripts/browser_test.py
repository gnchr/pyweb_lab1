"""Проверка поиска Material в браузере, в том числе из подкаталога.

python scripts/browser_test.py --directory site
python scripts/browser_test.py --url https://example.org/pyweb_lab1/
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import sys
from threading import Thread
from urllib.parse import urlsplit

from playwright.sync_api import Error, expect, sync_playwright


@contextmanager
def local_site(directory: Path, prefix: str):
    class Handler(SimpleHTTPRequestHandler):
        def do_GET(self):
            if not self.path.startswith(prefix):
                self.send_error(404)
                return
            self.path = "/" + self.path[len(prefix):]
            super().do_GET()

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(
        ("127.0.0.1", 0), partial(Handler, directory=str(directory.resolve()))
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}{prefix}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def check_browser(url: str, query: str, channel: str | None, blocked_worker: bool = False) -> None:
    origin = urlsplit(url)
    failures: list[str] = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, channel=channel)
        context = browser.new_context()
        page = context.new_page()
        page.on("pageerror", lambda error: failures.append(str(error)))

        def restrict_requests(route):
            target = urlsplit(route.request.url)
            if target.scheme in {"http", "https"} and (
                (target.scheme, target.netloc) != (origin.scheme, origin.netloc)
                or (blocked_worker and "/workers/search." in target.path)
            ):
                route.abort()
            else:
                route.continue_()

        context.route("**/*", restrict_requests)
        try:
            response = page.goto(url, wait_until="networkidle")
            if response is None or response.status != 200:
                raise RuntimeError(f"Страница недоступна: {url}")
            expect(page.locator("h1")).to_contain_text("Публикация результатов исследований")
            search_input = page.locator("[data-md-component='search-query']")
            search_input.click()
            # Material слушает keyup: fill() отправляет только событие input.
            search_input.press_sequentially(query)
            result = page.locator(".md-search-result__link").first
            expect(result).to_be_visible(timeout=15000)
            expect(result).to_contain_text("Публикация результатов исследований")
            href = result.get_attribute("href") or ""
            resolved = urlsplit(page.evaluate("href => new URL(href, location.href).href", href))
            if resolved.netloc != origin.netloc or not resolved.path.startswith(origin.path):
                raise RuntimeError(f"Результат поиска выходит из подкаталога: {href}")
            if failures:
                raise RuntimeError("Ошибки JavaScript: " + "; ".join(failures))
        except AssertionError as error:
            details = "; ".join(failures) or "ошибки JavaScript не зарегистрированы"
            raise RuntimeError(f"{error}\nДополнительная диагностика: {details}") from error
        finally:
            context.close()
            browser.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--directory", type=Path)
    target.add_argument("--url")
    parser.add_argument("--query", default="MkDocs")
    parser.add_argument("--channel", help="Например, msedge для установленного браузера на Windows")
    parser.add_argument("--block-search-worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    try:
        if args.directory:
            if not (args.directory / "index.html").is_file():
                raise RuntimeError("Сначала выполните mkdocs build --strict")
            for prefix in ("/pyweb_lab1/", "/~review/pyweb_lab1/"):
                with local_site(args.directory, prefix) as url:
                    check_browser(url, args.query, args.channel, args.block_search_worker)
                print(f"BROWSER SEARCH PASSED: {prefix} (external resources blocked)")
        else:
            url = args.url.rstrip("/") + "/"
            check_browser(url, args.query, args.channel, args.block_search_worker)
            print("BROWSER SEARCH PASSED (external resources blocked)")
    except (AssertionError, Error, OSError, RuntimeError) as error:
        print(f"BROWSER SEARCH FAILED: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
