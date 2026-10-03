# pyweb_lab1

Каркас лабораторной работы о генераторах статических сайтов на Python.
Содержимое сайта пока представлено заглушкой; инфраструктура локальной сборки,
проверок и развёртывания уже подготовлена.

## Локальный запуск

Требуется Python 3.12.

```powershell
python -m pip install virtualenv==21.14.5
python -m virtualenv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --requirement requirements.txt
mkdocs serve
```

Если политика PowerShell запрещает активацию, команды можно запускать напрямую:

```powershell
.\.venv\Scripts\python.exe -m pip install --requirement requirements.txt
.\.venv\Scripts\python.exe -m mkdocs serve
```

Строгая сборка и локальная проверка:

```powershell
.\.venv\Scripts\python.exe -m mkdocs build --strict
.\.venv\Scripts\python.exe scripts\smoke_test.py --directory site
```

Битые якоря, ссылки на отсутствующие каталоги и абсолютные внутренние пути
являются предупреждениями и останавливают строгую сборку.

Для регрессионных тестов и функциональной проверки поиска:

```powershell
.\.venv\Scripts\python.exe -m pip install --requirement requirements-dev.txt
.\.venv\Scripts\python.exe -m playwright install chromium
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe scripts\browser_test.py --directory site
```

Если на Windows уже установлен Microsoft Edge, вместо загрузки Chromium можно
запустить `browser_test.py --directory site --channel msedge`.
Тест открывает сайт из двух подкаталогов, ищет `MkDocs`, проверяет результат
и блокирует загрузку внешних ресурсов. Эти проверки также выполняются в CI.

## GitHub Pages

Workflow `.github/workflows/pages.yml` собирает сайт и публикует artifact через
официальную связку `actions/upload-pages-artifact` и `actions/deploy-pages`.

Перед первым деплоем в настройках репозитория нужно выбрать:

`Settings → Pages → Build and deployment → Source → GitHub Actions`.

Ожидаемый адрес проекта:

`https://gnchr.github.io/pyweb_lab1/`

Базовый URL сборки берётся из `actions/configure-pages`, включая пользовательский
домен, если он настроен. После деплоя выполняется HTTP smoke-тест публичного URL:
контрольная строка, локальные CSS/JS, worker поиска и поисковый индекс.

## Helios

При деплое автоматически создаётся папка `~/public_html/pyweb_lab1`.
В неё копируется **содержимое** локального каталога `site/`:

```text
~/public_html/
└── pyweb_lab1/
    ├── index.html
    ├── assets/
    ├── search/
    └── sitemap.xml
```

Дополнительная папка `site` на сервере не создаётся. Остальные лабораторные
работы в `public_html` не участвуют в синхронизации.

Workflow `.github/workflows/helios.yml` можно запустить вручную. Автоматический
запуск после push в `main` включается переменной репозитория
`HELIOS_ENABLED=true`.

### Где заполнить настройки

В файлах проекта ничего подставлять не требуется: workflow получает настройки
из GitHub. Открой репозиторий → **Settings → Secrets and variables → Actions**.
Ниже замени `sXXXXXX` на свою учётную запись Helios, например `s123456`.

Во вкладке **Variables** нажми **New repository variable** для каждого значения:

| Name | Value |
| --- | --- |
| `HELIOS_ENABLED` | `true` — автоматический деплой после push в `main`; `false` — только ручной запуск |
| `HELIOS_HOST` | `helios.cs.ifmo.ru` |
| `HELIOS_PORT` | `2222` |
| `HELIOS_DEPLOY_PATH` | `/home/studs/sXXXXXX/public_html/pyweb_lab1` |
| `HELIOS_SITE_URL` | `https://se.ifmo.ru/~sXXXXXX/pyweb_lab1/` |

В `HELIOS_DEPLOY_PATH` нужен абсолютный путь, а не строка с `~`.
Допускается также `/export/home/studs/sXXXXXX/public_html/pyweb_lab1`.
Проверь домашний каталог своей учётной записи командой `pwd -P` после входа
на сервер. В `HELIOS_SITE_URL` обязателен завершающий `/`.

Во вкладке **Secrets** нажми **New repository secret** для каждого значения:

| Name | Secret |
| --- | --- |
| `HELIOS_USER` | `sXXXXXX` |
| `HELIOS_SSH_KEY` | Полное содержимое файла закрытого SSH-ключа, включая строки `BEGIN` и `END`; ключ должен быть без парольной фразы |
| `HELIOS_KNOWN_HOSTS` | Запись проверенного ключа сервера для `[helios.cs.ifmo.ru]:2222` из `known_hosts` |

Все перечисленные значения задаются на уровне **repository**. Это особенно
важно для `HELIOS_ENABLED`: условие запуска вычисляется до загрузки настроек
deployment environment. Workflow использует environment с именем `helios`;
его можно заранее создать через **Settings → Environments → New environment**.

### Как подготовить SSH-ключ

На Windows в PowerShell создай отдельный ключ для CI:

```powershell
New-Item -ItemType Directory -Force -Path "$env:USERPROFILE\.ssh" | Out-Null
ssh-keygen -t ed25519 -f "$env:USERPROFILE\.ssh\helios_pyweb_lab1" -C "github-actions-pyweb-lab1"
```

На запросы парольной фразы нажми Enter: пайплайн использует ключ без неё.
Получатся два файла:

- `helios_pyweb_lab1.pub` — публичный ключ, который добавляется на Helios;
- `helios_pyweb_lab1` — закрытый ключ, содержимое которого сохраняется в
  `HELIOS_SSH_KEY` на GitHub.

Войди на Helios обычным способом:

```powershell
ssh -p 2222 sXXXXXX@helios.cs.ifmo.ru
```

При первом подключении проверь fingerprint ключа сервера по доверенному
источнику ИТМО и подтверди его. На сервере добавь полную строку из `.pub`
в файл `~/.ssh/authorized_keys`, сохранив уже существующие ключи. Каталог
`~/.ssh` должен иметь права `700`, файл `authorized_keys` — `600`.
На сервере также проверь `command -v rsync` — команда должна вывести путь
к установленному `rsync`.

После настройки проверь вход новым ключом из PowerShell:

```powershell
ssh -i "$env:USERPROFILE\.ssh\helios_pyweb_lab1" -o BatchMode=yes -p 2222 sXXXXXX@helios.cs.ifmo.ru
```

Если вход проходит без запроса пароля, ключ готов для CI.
После выхода получи сохранённую, уже проверенную запись сервера:

```powershell
ssh-keygen -F "[helios.cs.ifmo.ru]:2222" -f "$env:USERPROFILE\.ssh\known_hosts"
```

Скопируй строки ключей из результата в `HELIOS_KNOWN_HOSTS`.
Закрытый ключ хранится в GitHub Secrets, а не в файлах репозитория.

### Как запустить деплой

Отправь файлы проекта в ветку `main`, заполни настройки и открой
**Actions → Deploy to Helios → Run workflow → Branch: main → Run workflow**.
Ручной запуск работает и при `HELIOS_ENABLED=false`.
После успешного запуска сайт доступен по значению `HELIOS_SITE_URL`.
При `HELIOS_ENABLED=true` следующие push в `main` обновят его автоматически.

Перед синхронизацией `deploy_helios.py` проверяет параметры подключения и точный
каталог назначения. На сервере проверяются текущий пользователь, физический
путь домашнего каталога и отсутствие символьных ссылок у `public_html` и
`pyweb_lab1`. Синхронизация с `rsync --delete` начинается только после этих
проверок и выполняется по подтверждённому физическому пути. Проверка путей
повторяется в команде принимающего `rsync`. Каталоги получают права `755`,
файлы — `644`.

На Helios должны быть доступны POSIX `sh` и `rsync`; установленный Python на
сервере не требуется. Первый реальный деплой необходим для проверки SSH-доступа,
ключа сервера, наличия `rsync` и HTTP-доступности сайта.

## Лицензии

- программный код и workflow: [MIT](LICENSE);
- авторское содержимое сайта: [CC BY 4.0](LICENSE-CONTENT.md).

