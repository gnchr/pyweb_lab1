# Сервер на Python

Создадим небольшой сервер на стандартной библиотеке Python: он отдаёт файлы интерфейса и JSON со списком тем.

## Структура примера

```text
web-demo/
├── server.py
└── public/
    ├── index.html
    ├── styles.css
    └── app.js
```

В `public` разместите примеры из разделов [HTML/CSS](frontend.md) и [JavaScript](javascript.md). В `index.html` добавьте `<p id="topics" aria-live="polite"></p>`.

## Обработчик запроса

Сохраните как `server.py`:

```python
import json
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit


class Handler(SimpleHTTPRequestHandler):
    def do_GET(self):
        path = urlsplit(self.path).path
        if path == '/api/topics':
            body = json.dumps(
                {'topics': ['HTML', 'CSS', 'JavaScript', 'Python']},
                ensure_ascii=False,
            ).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif path.startswith('/api/'):
            self.send_error(404, 'API endpoint not found')
        else:
            super().do_GET()


if __name__ == '__main__':
    public = Path(__file__).resolve().parent / 'public'
    handler = partial(Handler, directory=str(public))
    with ThreadingHTTPServer(('127.0.0.1', 8001), handler) as server:
        print('Откройте http://127.0.0.1:8001/')
        server.serve_forever()
```

`Content-Length` вычисляется по числу байтов UTF-8, а не по длине исходной строки. Неизвестный API-маршрут возвращает 404. Статические файлы обслуживаются только из `public`.

## Запуск и проверка

В каталоге `web-demo` выполните:

```bash
python3 server.py
```

На Windows вместо `python3` можно использовать `python`. Откройте `http://127.0.0.1:8001/`, затем проверьте API:

```bash
curl -i http://127.0.0.1:8001/api/topics
curl -i http://127.0.0.1:8001/api/missing
```

Ожидаемые статусы — 200 и 404 соответственно. Для остановки нажмите Ctrl+C.

!!! warning "Границы учебного примера"
    `http.server` предназначен для локальных экспериментов. Здесь нет авторизации, базы данных и защиты промышленного приложения. Сервер слушает только локальный адрес `127.0.0.1`.

Далее: [практикум](practice.md).
