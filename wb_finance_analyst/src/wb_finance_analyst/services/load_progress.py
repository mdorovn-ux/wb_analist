from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


LOAD_STAGES = [
    "Проверка наличия кэша",
    "Получение списка финансовых отчётов",
    "Выбор reportId по выбранному типу отчёта",
    "Получение сводки WB",
    "Получение детализации Finance API",
    "Получение рекламы Promotion API",
    "Расчёт отчёта",
    "Формирование таблиц",
    "Готово",
]


class LoadingCancelled(RuntimeError):
    pass


@dataclass(frozen=True)
class LoadProgress:
    stage: str
    status: str = ""
    rows_loaded: int | None = None
    progress: int | None = None
    wait_seconds: int | None = None


ProgressCallback = Callable[[LoadProgress], None]
CancelCallback = Callable[[], bool]
