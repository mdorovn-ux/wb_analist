# WB analyst Landing

Одностраничный сайт для WB analyst. Сайт показывает возможности программы и дает ссылку на скачивание архива Windows-версии напрямую из GitHub.

## Локальный запуск

```bash
cd landing
npm start
```

После запуска откройте:

```text
http://localhost:3000
```

## Деплой на Railway

1. Загрузите репозиторий на GitHub.
2. Откройте Railway и нажмите `New Project`.
3. Выберите `Deploy from GitHub repo`.
4. Выберите репозиторий `mdorovn-ux/wb_analist`.
5. В настройках сервиса укажите:
   - Root Directory: `landing`
   - Start Command: `npm start`
6. Railway сам задаст переменную `PORT`, сервер ее использует автоматически.
7. После деплоя откройте публичный домен Railway.

Файл программы для скачивания хранится в репозитории здесь:

```text
releases/WB-analyst-v1.0.zip
```

Сайт скачивает архив по ссылке:

```text
https://raw.githubusercontent.com/mdorovn-ux/wb_analist/main/releases/WB-analyst-v1.0.zip
```

Если выходит новая версия, замените zip-файл в `releases`, затем обновите ссылку/текст версии на странице.
