# WB analyst

WB analyst - desktop-приложение для селлеров Wildberries. Программа загружает финансовые отчеты WB, сверяет суммы с кабинетом, считает прибыль, рекламу, себестоимость, налоги и сохраняет Excel-отчет.

## Структура репозитория

```text
wb_finance_analyst/   Desktop-приложение на Python/PySide6
landing/              Одностраничный сайт для Railway
releases/             ZIP-архивы готовых Windows-сборок
docs/                 Продуктовые планы и дорожная карта
```

## План развития

Дорожная карта продукта после v1.0:

```text
docs/PRODUCT_ROADMAP.md
```

## Текущая версия разработки

```text
1.1.0-dev
```

## Версия 1.0

Готовая сборка:

```text
releases/WB-analyst-v1.0.zip
```

Прямая ссылка для сайта:

```text
https://github.com/mdorovn-ux/wb_analist/releases/download/v1.0/WB-analyst-v1.0.zip
```

## GitHub Release

Готовые ZIP-сборки публикуются через GitHub Releases, а не через raw-файлы в репозитории.
Для публикации релиза нужен авторизованный GitHub CLI:

```powershell
gh auth login
.\tools\create_github_release.ps1
```

Скрипт для v1.0 прикрепляет к релизу:

```text
releases/WB-analyst-v1.0.zip
latest.json
```

Для будущей версии можно передать другой тег и архив:

```powershell
.\tools\create_github_release.ps1 -Tag "v1.1.0" -ArchivePath "releases/WB-analyst-v1.1.0.zip" -Title "WB analyst v1.1.0"
```

## Локальный запуск приложения

```bash
cd wb_finance_analyst
pip install -r requirements.txt
python main.py
```

## Проверка приложения

```bash
cd wb_finance_analyst
python -m compileall .
python -m pytest
```

## Локальный запуск сайта

```bash
cd landing
npm start
```

Открыть:

```text
http://localhost:3000
```

## Railway

1. Railway -> `New Project`.
2. `Deploy from GitHub repo`.
3. Репозиторий: `mdorovn-ux/wb_analist`.
4. Root Directory: `landing`.
5. Start Command: `npm start`.

Сайт скачивает программу напрямую из GitHub, поэтому сам Railway-сервис остается легким.
