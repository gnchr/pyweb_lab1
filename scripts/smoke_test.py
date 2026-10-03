"""Минимальная проверка собранного или опубликованного сайта.

Скрипт использует только стандартную библиотеку Python, поэтому подходит как
для локального запуска, так и для GitHub Actions.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import unquote, urljoin, urlsplit
from urllib.request import Request, urlopen


MARKER = "PYWEB_LAB1_DEPLOYMENT_OK"
FORBIDDEN_CDN_HOSTS = {
    "cdn.jsdelivr.net",
    "cdnjs.cloudflare.com",
    "fonts.googleapis.com",
    "fonts.gstatic.com",
    "unpkg.com",
}


class AssetParser(HTMLParser):
    """Собирает исполняемые и стилевые ресурсы из HTML."""

    def __init__(self) -> None:
        super().__init__()
        self.assets: list[str] = []
        self.config: dict = {}
        self._in_config = False
        self._config_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "script" and attributes.get("id") == "__config":
            self._in_config = True
        if tag == "script" and attributes.get("src"):
            self.assets.append(attributes["src"] or "")
        if tag == "link" and "stylesheet" in (attributes.get("rel") or "").split():
            self.assets.append(attributes.get("href") or "")

    def handle_data(self, data: str) -> None:
        if self._in_config:
            self._config_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "script" and self._in_config:
            self.config = json.loads("".join(self._config_text))
            self._in_config = False


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def parse_assets(html: str) -> list[str]:
    parser = AssetParser()
    parser.feed(html)
    worker = parser.config.get("search")
    require(isinstance(worker, str) and bool(worker), "Не найден worker поиска в конфигурации Material")
    return list(dict.fromkeys([*parser.assets, worker]))


def check_no_external_cdn(assets: list[str]) -> None:
    for asset in assets:
        host = (urlsplit(asset).hostname or "").lower()
        require(host not in FORBIDDEN_CDN_HOSTS, f"Обнаружена зависимость от CDN: {asset}")


def check_directory(directory: Path) -> None:
    index_path = directory / "index.html"
    search_path = directory / "search" / "search_index.json"
    require(index_path.is_file(), f"Не найден файл {index_path}")
    require(search_path.is_file(), f"Не найден поисковый индекс {search_path}")

    html = index_path.read_text(encoding="utf-8")
    require(MARKER in html, "В index.html отсутствует контрольная строка")

    assets = parse_assets(html)
    require(assets, "В index.html не найдены CSS/JavaScript-ресурсы")
    check_no_external_cdn(assets)

    for asset in assets:
        parsed = urlsplit(asset)
        require(not parsed.scheme and not parsed.netloc, f"Ресурс не является локальным: {asset}")
        require(not parsed.path.startswith("/"), f"Абсолютный путь ломает подкаталог: {asset}")
        asset_path = index_path.parent / unquote(parsed.path)
        require(asset_path.is_file(), f"Не найден локальный ресурс {asset_path}")

    search_data = json.loads(search_path.read_text(encoding="utf-8"))
    require(bool(search_data.get("docs")), "Поисковый индекс не содержит документов")


def fetch(url: str, attempts: int = 6, *, expected_marker: str | None = None) -> str:
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            request = Request(url, headers={"User-Agent": "pyweb-lab1-smoke-test/1.0"})
            with urlopen(request, timeout=20) as response:
                require(response.status == 200, f"{url} вернул HTTP {response.status}")
                content = response.read().decode("utf-8")
                if expected_marker is not None:
                    require(expected_marker in content, f"{url}: отсутствует контрольная строка")
                return content
        except (HTTPError, URLError, TimeoutError, RuntimeError) as error:
            last_error = error
            if attempt < attempts:
                time.sleep(5)
    raise RuntimeError(f"Не удалось получить {url}: {last_error}")


def check_url(base_url: str) -> None:
    base_url = base_url.rstrip("/") + "/"
    parsed_base = urlsplit(base_url)
    require(parsed_base.scheme in {"http", "https"} and bool(parsed_base.netloc), "Нужен HTTP(S) URL сайта")
    html = fetch(base_url, expected_marker=MARKER)

    assets = parse_assets(html)
    require(assets, "На опубликованной странице не найдены CSS/JavaScript-ресурсы")
    check_no_external_cdn(assets)
    for asset in assets:
        parsed_asset = urlsplit(asset)
        require(not parsed_asset.scheme and not parsed_asset.netloc, f"Ресурс не является локальным: {asset}")
        require(not parsed_asset.path.startswith("/"), f"Абсолютный путь ломает подкаталог: {asset}")
        asset_url = urljoin(base_url, asset)
        require(urlsplit(asset_url).path.startswith(parsed_base.path), f"Ресурс выходит из подкаталога: {asset}")
        fetch(asset_url, attempts=3)

    search_text = fetch(urljoin(base_url, "search/search_index.json"))
    search_data = json.loads(search_text)
    require(bool(search_data.get("docs")), "Опубликованный поисковый индекс пуст")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--directory", type=Path, help="Каталог результата MkDocs")
    target.add_argument("--url", help="Публичный базовый URL сайта")
    args = parser.parse_args()

    try:
        if args.directory:
            check_directory(args.directory.resolve())
        else:
            check_url(args.url)
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as error:
        print(f"SMOKE TEST FAILED: {error}", file=sys.stderr)
        return 1

    print("SMOKE TEST PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

