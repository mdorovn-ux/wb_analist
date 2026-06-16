from enum import StrEnum


class FileStatus(StrEnum):
    WAITING = "Ожидает"
    LOADED = "Загружен"
    PROCESSED = "Обработан"
    ERROR = "Ошибка"


class ExpenseMode(StrEnum):
    FIXED = "fixed"
    PERCENT_OF_SALES = "percent_of_sales"
