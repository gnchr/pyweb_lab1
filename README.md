# pyweb_lab1

Учебный сайт «Веб-программирование» на MkDocs Material: HTML/CSS, JavaScript,
HTTP, сервер на Python и практикум. Есть поиск, светлая и тёмная темы,
адаптивная навигация и формула в MathML без зависимости от CDN.

Материалы находятся в `docs/`, локальные стили — в `docs/stylesheets/extra.css`.

На macOS/Linux для локального запуска:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
mkdocs serve
mkdocs build --strict
python scripts/smoke_test.py --directory site
```

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
Тест открывает сайт из подкаталогов Pages, Helios и preview, ищет `MkDocs`, проверяет результат
и блокирует загрузку внешних ресурсов. Дополнительно проверяются отображение
формулы MathML и отсутствие горизонтальной прокрутки при ширине 360 пикселей.
Эти проверки также выполняются в CI.

Для установленного Google Chrome используйте `--channel chrome`.
Если Playwright сообщает, что исполняемый файл Chromium отсутствует, выберите
установленный браузер через `--channel` или установите Chromium командой выше.

## GitHub Pages

Workflow `.github/workflows/pages.yml` собирает сайт и публикует artifact через
официальную связку `actions/upload-pages-artifact` и `actions/deploy-pages`.
Автоматически вызывается из `production.yml` после merge PR в main и успешного
push-CI merge-коммита. Ручной запуск сначала выполняет полный CI текущего main.

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
деплой вызывают `preview.yml` и `production.yml` только **после успешного
полного push-CI** для того же SHA.
Для него нужна переменная репозитория `HELIOS_ENABLED=true`.

### CI, обязательные проверки PR и ссылка на preview

`ci.yml` запускается на push в любую ветку (и вручную), но не дублирует запуск
на `pull_request`. Проверки push отображаются в PR для того же commit.
Полный набор проверок вынесен в reusable `ci-build.yml`: регрессионные тесты,
строгая сборка, smoke-тест, демонстрация отката и браузерный тест.
Сам push запускает только `CI / build`, без деплоев.

| Событие | Что выполняется |
| --- | --- |
| Push в любую ветку | Только полный CI |
| Открытие/повторное открытие PR рабочей ветки | `preview.yml`: ожидание push-CI head SHA → Helios preview → healthcheck → комментарий с URL |
| Новый push в открытый PR | CI по push; preview обновляется по `pull_request: synchronize` после успешного CI нового SHA |
| Merge PR в main | CI merge-коммита по push; `production.yml` ждёт его и параллельно вызывает Helios main и GitHub Pages |
| Закрытие PR без merge | Без деплоя |
| Прямой push в main без merge PR | Только CI, без автоматической публикации |

`ci-gate.yml` проверяет через GitHub API результат `ci.yml` для **точного SHA и
ветки**, а также успешный job `CI / build`. Если CI ещё выполняется либо ещё
не появился в API, ожидание продолжается до 30 минут. Failed, cancelled,
skipped, отсутствие проверки и timeout не разрешают деплой. Проверки не
дублируются в PR. При merge проверяется новый SHA в main, а не старый head PR.

Деплой привязан к **тому же SHA**, который проверял CI. Если за время проверки
ветка продвинулась, устаревший запуск откажется от публикации. При ручном запуске
Helios сначала фиксируется SHA целевой ветки и выполняется тот же CI; это
относится также к операциям rollback/recover. Ручной GitHub Pages также
выполняет полный CI до публикации.

После успешного healthcheck в открытом PR появляется комментарий бота
**«Preview на Helios»** со ссылкой на сайт, ID релиза и запуск Actions.
Следующая публикация обновляет комментарий. Ссылка также записывается в
Actions Summary и URL environment `helios`. Если CI прошёл до открытия PR,
preview публикуется сразу после проверки его результата, без повторного CI.
Для PR из чужих forks автоматическая публикация с SSH-секретами
не поддерживается; такие изменения сначала нужно перенести в доверенную ветку.

На GitHub для `main` включена защита: требуется актуальная база ветки,
успешные **`CI / build`** и **`Deploy to Helios / deploy`** от GitHub Actions,
правила действуют и для администратора. Проверить можно в
**Settings → Branches → Branch protection rules → main**.
Конфигурация сохранена в `.github/branch-protection.json` как эталон; сам файл
не включает защиту — ограничения применяются в настройках GitHub.

При неуспешном CI деплой не начинается; при неуспешном деплое/healthcheck
merge блокируется. Обязательный итоговый job `Deploy to Helios / deploy`
успешен только при успешных CI-gate и публикации: skipped/cancelled/timeout
не дают ложного разрешения на merge. `HELIOS_ENABLED=false` приводит к failed обязательной
проверке автоматического деплоя, а не к skipped/успешному статусу. После
публикации изменений workflows нужно дождаться обеих новых проверок; старые
проверки с именами `build`/`deploy` не удовлетворяют новой защите.

### Где заполнить настройки

В файлах проекта ничего подставлять не требуется: workflow получает настройки
из GitHub. Открой репозиторий → **Settings → Secrets and variables → Actions**.
Ниже замени `sXXXXXX` на свою учётную запись Helios, например `s123456`.

Во вкладке **Variables** нажми **New repository variable** для каждого значения:

| Name | Value |
| --- | --- |
| `HELIOS_ENABLED` | `true` — автоматический деплой после успешного CI; `false` — только ручной запуск, обязательная автоматическая проверка PR завершится ошибкой |
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

Все перечисленные значения задаются на уровне **repository** и доступны
как автоматическому, так и ручному запуску. Workflow использует environment с именем `helios`;
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
На сервере проверь `command -v rsync` и `command -v sh`.
**Python на Helios не нужен и не устанавливается.** Сборка, управление SSH
и HTTP healthcheck выполняются Python на GitHub runner. На сервер по SSH
передаются только shell-скрипты: POSIX `sh` и стандартные Unix-команды
(`cp`, `mv`, `ln`, `find`, `df`, `awk`, `grep` и др.) управляют версиями
и восстановлением. MkDocs и другие интерпретаторы на Helios не требуются.
`public_html` и приватное хранилище должны находиться на одной файловой системе.
Для отдельного ключа CI рекомендуется префикс `restrict` перед строкой
публичного ключа в `authorized_keys` (если сервер поддерживает эту опцию):
он запрещает PTY и forwarding, сохраняя возможность SSH-команд и rsync.

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
**Actions → Deploy to Helios → Run workflow → Branch: main → action: deploy → Run workflow**.
Ручной запуск работает и при `HELIOS_ENABLED=false`.
После успешного запуска сайт доступен по значению `HELIOS_SITE_URL`.
При `HELIOS_ENABLED=true` открытие/обновление PR публикует preview, а merge PR
в main обновляет основной сайт — в обоих случаях после успешного push-CI.
Для ручного запуска можно указать `target_branch`;
пустое значение означает ветку, выбранную в Run workflow.

Перед синхронизацией `deploy_helios.py` проверяет параметры подключения и точный
каталог назначения. На сервере проверяются текущий пользователь, физический
путь домашнего каталога и отсутствие символьных ссылок. `rsync` передаёт сайт
в новый приватный каталог `~/.pyweb_lab1-deploy/staging/<release>/`, а не поверх
работающего сайта. Проверка пути повторяется принимающей командой rsync;
каталоги статики получают права `755`, файлы — `644`, хранилище — `700`.
После успешной передачи каталог активируется в `~/public_html/pyweb_lab1`.
Старый каталог сохраняется в приватном `backups`, не доступном через HTTP.

Первый реальный деплой необходим для проверки SSH-доступа, ключа сервера,
наличия `rsync`, POSIX shell и HTTP-доступности сайта. Если environment `helios`
ограничен только веткой main, разреши нужные доверенные ветки для preview.
Публикации из чужих fork/PR не запускаются; не выдавай секреты недоверенным
авторам веток и не размещай приватные данные в публичных preview.

### Preview и healthcheck

Основная ветка (default branch репозитория) публикуется в корень проекта.
Каждая другая ветка получает `previews/<slug>-<sha256-12>/`: хеш предотвращает
совпадения имён вроде `feature/a` и `feature-a`. URL указан в шаге Configure
deployment or preview; этот URL используется и в `site_url` MkDocs.
Обновление и откат основной версии сохраняют текущие preview. Сборка не
должна содержать каталог `previews`: он зарезервирован для деплоя веток.

После выкладки проверяются HTTP **200**, общая контрольная строка и уникальная
`PYWEB_LAB1_RELEASE:<release>`, CSS/JS, worker и непустой индекс поиска.
Поэтому ответ 200 от старой версии не считается успешным деплоем.
При ошибке проверка возвращает exit code 1, и job остаётся красным.
Если предыдущая версия есть, пайплайн пытается автоматически восстановить
её и проверяет восстановленный сайт. При первом деплое откатывать нечего.

### Ручной откат и восстановление

В **Actions → Deploy to Helios → Run workflow** выбери ветку с актуальными
workflow/скриптами, `action: rollback` и `target_branch: main` (либо имя preview-
ветки). Сайт не пересобирается: активируется сохранённая предыдущая версия,
затем выполняется публичный healthcheck. Повторный rollback меняет версии
местами. Для отката preview его ветка должна ещё существовать в GitHub.

Если процесс прервался во время переключения каталогов, выбери `action: recover`
с той же целевой веткой. Журнал восстанавливается также автоматически перед
следующей операцией. Между двумя переименованиями возможен короткий HTTP 404;
если процесс остановлен в этот момент, 404 сохраняется до recover/нового запуска.
Это **не** обещание атомарной выкладки без простоя. Подробности — в отчёте.

Все выкладки Helios сериализуются общей очередью GitHub Actions и файловой
блокировкой на сервере. Не запускай параллельно внешние скрипты управления
этим же сайтом. Старые backup и незавершённые staging остаются в приватном
хранилище; автоматическая очистка намеренно отсутствует. Контролируй квоту
диска; не удаляй backup, на который ссылается `history/<channel>.previous`,
или файлы при незавершённом `transaction/`. Идентификатор текущего релиза
читается из `.release-id` в опубликованном каталоге, JSON парсится только на runner.
Файловая блокировка использует атомарный hard link с PID; блокировка погибшего
процесса снимается следующим запуском. Если PID уже занят другим процессом,
owner повреждён или остался каталог `lock-recovery`, скрипт безопасно откажется
от выкладки: сначала проверь процессы и файлы блокировки вручную, не удаляя
блокировку работающей операции.

### Демонстрация и отчёт

```powershell
.\.venv\Scripts\python.exe -m mkdocs build --strict
.\.venv\Scripts\python.exe scripts\demo_deployment.py --report _build\rollback-demo.json
```

Для локальных тестов/демонстрации также нужен POSIX shell: на Windows подходит
установленный Git for Windows, в CI используется `/bin/sh` Ubuntu.
Демонстрация исполняет тот же shell-менеджер релизов и настоящий локальный HTTP,
но не подключается к Helios. Проверяются откат v2 → v1, сохранность preview,
неуспешный healthcheck и прерывания загрузки/переключения. Она также запускается
в CI; JSON доступен в artifact `local-rollback-demo`.

На реальных выкладках оба хостинга сохраняют измерения в Actions Summary и
artifact `helios-measurements-*` / `pages-measurements-*`.
Методика сравнения и протокол проверки: [отчёт](reports/deployment-report.md),
сохранённая локальная демонстрация: [JSON](reports/rollback-demo.json).

## Лицензии

- программный код и workflow: [MIT](LICENSE);
- авторское содержимое сайта: [CC BY 4.0](LICENSE-CONTENT.md).

