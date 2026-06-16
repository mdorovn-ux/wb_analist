# WB analyst

WB analyst - desktop-приложение для селлеров Wildberries. Программа загружает финансовые отчеты WB, сверяет суммы с кабинетом, считает прибыль, рекламу, себестоимость, налоги и сохраняет Excel-отчет.

## Структура репозитория

```text
wb_finance_analyst/   Desktop-приложение на Python/PySide6
landing/              Одностраничный сайт для Railway
releases/             ZIP-архивы готовых Windows-сборок
```

## Версия 1.0

Готовая сборка:

```text
releases/WB-analyst-v1.0.zip
```

Прямая ссылка для сайта:

```text
https://raw.githubusercontent.com/mdorovn-ux/wb_analist/main/releases/WB-analyst-v1.0.zip
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
