from __future__ import annotations

import pandas as pd

from wb_finance_analyst.domain.models import ExternalExpense
from wb_finance_analyst.services.external_expenses import ExternalExpensesCalculator


DEFAULT_EXPENSE_NAMES = [
    "Логистика до WB",
    "Аренда",
    "Коммуналка",
    "Бухгалтер",
    "Менеджер",
    "Зарплаты",
    "Внешняя реклама",
    "Прочие расходы",
]


class BusinessExpensesCalculator:
    def calculate(self, expenses: list[ExternalExpense], base_sales: float) -> tuple[pd.DataFrame, float]:
        df = ExternalExpensesCalculator().build_expenses(expenses, base_sales)
        if df.empty:
            df = pd.DataFrame([{"Расход": name, "Режим": "Фиксированная сумма", "Значение": 0.0, "Сумма": 0.0, "Комментарий": ""} for name in DEFAULT_EXPENSE_NAMES])
        return df, float(df["Сумма"].sum()) if "Сумма" in df.columns else 0.0
