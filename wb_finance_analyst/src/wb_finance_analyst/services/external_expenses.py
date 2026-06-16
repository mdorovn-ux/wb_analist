from __future__ import annotations

import pandas as pd

from wb_finance_analyst.domain.models import ExternalExpense
from wb_finance_analyst.services.numeric import money


class ExternalExpensesCalculator:
    def build_expenses(self, expenses: list[ExternalExpense], base_sales: float) -> pd.DataFrame:
        rows = []
        for expense in expenses:
            if expense.mode == "percent_of_sales":
                amount = base_sales * expense.amount / 100
            else:
                amount = expense.amount
            rows.append(
                {
                    "Расход": expense.name,
                    "Режим": "Процент от продаж" if expense.mode == "percent_of_sales" else "Фиксированная сумма",
                    "Значение": expense.amount,
                    "Сумма": money(amount),
                    "Комментарий": expense.comment,
                }
            )
        return pd.DataFrame(rows, columns=["Расход", "Режим", "Значение", "Сумма", "Комментарий"])
