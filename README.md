# WB analyst

WB analyst - desktop-приложение для селлеров Wildberries. Программа загружает финансовые отчеты WB, сверяет суммы с кабинетом, считает прибыль, рекламу, себестоимость, налоги, внешние расходы и сохраняет Excel-отчет.

Текущая стабильная версия: `1.1.1`.

Стабильный релиз: `v1.1.1`.

## Структура

```text
wb_finance_analyst/   Desktop-приложение на Python/PySide6
landing/              Одностраничный сайт для Railway
releases/             Локальная папка для ZIP-сборок перед публикацией
docs/                 Roadmap и рабочие планы версий
tools/                Скрипты публикации релизов
```

## Скачать

Стабильная сборка опубликована в GitHub Releases:

```text
https://github.com/mdorovn-ux/wb_analist/releases/download/v1.1.1/WB-analyst-v1.1.1.zip
```

Релизные ZIP-архивы публикуются в GitHub Releases и доступны по публичной ссылке.

## Локальный запуск приложения

```bash
cd wb_finance_analyst
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

## Проверка приложения

```bash
cd wb_finance_analyst
python -m compileall .
python -m pytest
```

## Сборка exe

```bash
cd wb_finance_analyst
python -m PyInstaller --noconfirm --clean --windowed --paths src --name "WB analyst v1.1.1" --add-data "src\wb_finance_analyst\resources;wb_finance_analyst\resources" main.py
```

После сборки проверьте запуск exe из `dist/`, затем упакуйте папку приложения в ZIP.

## Ручная активация

При первом запуске программа показывает код компьютера. Для генерации ключа используйте локальный калькулятор:

```bash
cd wb_finance_analyst
python tools/license_calculator.py
```

Универсальный тестовый ключ есть внутри калькулятора и предназначен для внутренних проверок.

## GitHub Releases

Готовые ZIP-сборки публикуются через GitHub Releases, а не через raw-файлы в репозитории. Для публикации нужен авторизованный GitHub CLI:

```powershell
gh auth login
.\tools\create_github_release.ps1
```

Для будущей версии:

```powershell
.\tools\create_github_release.ps1 -Tag "v1.2.0" -ArchivePath "releases/WB-analyst-v1.2.0.zip" -Title "WB analyst v1.2.0"
```

Скрипт прикрепляет к релизу ZIP-архив и `latest.json`. После публикации обновите `latest.json`, landing и README под новую стабильную версию.

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
3. Repository: `mdorovn-ux/wb_analist`.
4. Root Directory: `landing`.
5. Start Command: `npm start`.

Railway сам задает переменную `PORT`; сервер лендинга использует ее автоматически.

## Документы

```text
docs/PRODUCT_ROADMAP.md  План развития продукта
docs/in_job.md           Рабочий план текущей версии
landing/README.md        Деплой и обслуживание лендинга
wb_finance_analyst/README.md  Запуск, сборка и пользовательский сценарий приложения
```

## Ветки

`main` - текущая разработка.

`prod` - проверенный стабильный релиз. Обновлять только после финальной проверки версии.
