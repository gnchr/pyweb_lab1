# HTML и CSS

HTML задаёт структуру и смысл страницы, CSS — её внешний вид. Начните с читаемого документа, затем добавьте оформление.

## Семантическая страница

Сохраните пример как `index.html` и откройте в браузере. Атрибут `lang` задаёт язык документа, а `viewport` помогает корректно отображать страницу на мобильном устройстве.

```html
<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Мой учебный проект</title>
  <link rel="stylesheet" href="styles.css">
</head>
<body>
  <header><p>Веб-мастерская</p></header>
  <main>
    <h1>Мои проекты</h1>
    <section aria-labelledby="projects-title">
      <h2 id="projects-title">Портфолио</h2>
      <div class="projects">
        <article><h3>Справочник</h3><p>Заметки о вебе.</p></article>
        <article><h3>Каталог</h3><p>Подборка учебных ресурсов.</p></article>
      </div>
    </section>
  </main>
  <footer><p>Учебный проект</p></footer>
</body>
</html>
```

Используйте заголовки по смыслу, а не ради размера шрифта. Для действия подходит `button`, для перехода на другой адрес — `a`. Изображениям с содержательной нагрузкой нужен описательный `alt`.

## Адаптивная сетка

Создайте рядом `styles.css`:

```css
* { box-sizing: border-box; }
body {
  margin: 0;
  font-family: system-ui, sans-serif;
  line-height: 1.6;
  color: #18243b;
  background: #f5f7fb;
}
header, main, footer {
  width: min(100% - 2rem, 64rem);
  margin-inline: auto;
}
.projects {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 16rem), 1fr));
  gap: 1rem;
}
article {
  padding: 1.5rem;
  border: 1px solid #d7deea;
  border-radius: 1rem;
  background: white;
}
```

Сетка распределяет карточки по доступной ширине. На узком экране карточки становятся в одну колонку. Проверьте ширины 360, 768 и 1280 пикселей в режиме устройства в браузере.

## Форма с подписью

```html
<form>
  <label for="email">Электронная почта</label>
  <input id="email" name="email" type="email" required>
  <button type="submit">Подписаться</button>
</form>
```

`label` связан с полем через `for` и `id`. `required` и `type="email"` включают проверку в браузере, но сервер всё равно должен проверять полученные данные. Этот пример демонстрирует разметку: для настоящей подписки нужен обработчик на сервере.

!!! question "Попробуйте сами"
    Добавьте третью карточку и ссылку на проект. Убедитесь, что клавиша Tab переводит фокус на ссылку, а страница не прокручивается горизонтально на телефоне.

Подробнее: [HTML](https://developer.mozilla.org/en-US/docs/Web/HTML), [адаптивная вёрстка](https://developer.mozilla.org/en-US/docs/Learn_web_development/Core/CSS_layout/Responsive_Design) и [формы](https://developer.mozilla.org/en-US/docs/Learn_web_development/Extensions/Forms) в MDN.

Далее: [JavaScript и события](javascript.md).
