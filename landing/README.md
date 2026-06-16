# WB analyst Landing

Одностраничный сайт для WB analyst. Сайт показывает возможности программы и дает ссылку на скачивание архива Windows-версии напрямую из GitHub.

Текущая версия разработки: `1.1.0-dev`.

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

Файл программы для скачивания публикуется в GitHub Releases. Локально архив можно держать здесь перед публикацией:

```text
releases/WB-analyst-v1.0.zip
```

Сайт скачивает архив по ссылке:

```text
https://github.com/mdorovn-ux/wb_analist/releases/download/v1.0/WB-analyst-v1.0.zip
```

## Обновление ссылки скачивания

ZIP-архивы программы публикуются через GitHub Releases. После сборки новой версии прикрепите архив и `latest.json` командой:

Важно: если репозиторий GitHub остается приватным, кнопка скачивания на публичном сайте будет получать `404`. Для внешних пользователей релизные файлы должны быть доступны публично.

```powershell
.\tools\create_github_release.ps1 -Tag "v1.1.0" -ArchivePath "releases/WB-analyst-v1.1.0.zip" -Title "WB analyst v1.1.0"
```

После этого обновите ссылку скачивания и текст версии в `landing/public/index.html`.

Если выходит новая версия, замените zip-файл в `releases`, затем обновите ссылку/текст версии на странице.
