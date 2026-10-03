# JavaScript в браузере

JavaScript позволяет реагировать на действия пользователя и менять документ. DOM представляет HTML как дерево объектов, с которым работает код.

## Счётчик событий

Добавьте в `main` HTML-страницы:

```html
<button id="counter" type="button">Добавить отметку</button>
<p aria-live="polite">Отметок: <span id="count">0</span></p>
<script src="app.js" defer></script>
```

Создайте `app.js` рядом с документом:

```javascript
const button = document.querySelector('#counter');
const output = document.querySelector('#count');
let count = 0;

button.addEventListener('click', () => {
  count += 1;
  output.textContent = String(count);
});
```

`defer` откладывает выполнение внешнего скрипта до разбора HTML. `querySelector` находит элемент, `addEventListener` подписывает обработчик на событие. `textContent` вставляет текст; не подставляйте пользовательские данные в `innerHTML`.

## Получение данных из API

После запуска [Python-сервера](python.md) сохраните этот код в `app.js` и вызовите `loadTopics()`:

```javascript
async function loadTopics() {
  const output = document.querySelector('#topics');
  output.textContent = 'Загрузка…';
  try {
    const response = await fetch('./api/topics');
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    const data = await response.json();
    output.textContent = data.topics.join(', ');
  } catch (error) {
    output.textContent = 'Не удалось загрузить темы. Попробуйте позже.';
    console.error(error);
  }
}

loadTopics();
```

В HTML нужен элемент `<p id="topics" aria-live="polite"></p>`. Открывайте страницу через сервер, а не через `file://`. Относительный URL сохраняет текущий origin; это удобно, когда интерфейс и API размещены на одном сервере.

!!! note "HTTP-ошибка и ошибка сети"
    `fetch` не отклоняет promise только из-за ответа 404 или 500. Проверяйте `response.ok` отдельно; `catch` также обрабатывает сбои сети и ошибки чтения JSON.

## Самопроверка

- Счётчик начинает с нуля и увеличивается ровно на один.
- Кнопка работает с клавиатуры.
- При остановленном сервере появляется понятное сообщение об ошибке.
- В Console нет необработанных ошибок.

Далее: [как устроен HTTP](http.md).
