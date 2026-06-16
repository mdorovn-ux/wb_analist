from __future__ import annotations

import pandas as pd

from wb_finance_analyst.domain.models import TaxSettings
from wb_finance_analyst.services.numeric import money


class TaxCalculator:
    def calculate(self, settings: TaxSettings, base_amount: float | dict[str, float]) -> tuple[pd.DataFrame, float]:
        bases = base_amount if isinstance(base_amount, dict) else {"wb_payable": base_amount, "goods": base_amount, "gross_profit": base_amount}
        rows = []
        total = 0.0
        mode = settings.mode
        if mode in {"usn", "usn_nds"}:
            base = float(bases.get(settings.usn_base, bases.get("wb_payable", 0.0)))
            amount = money(base * settings.usn_rate / 100)
            total += amount
            comment = "УСН выбран, но ставка не задана" if settings.usn_rate == 0 else ""
            rows.append({"Тип налога": "УСН", "Ставка": settings.usn_rate, "База": base, "Сумма": amount, "Комментарий": comment})
        if mode in {"nds", "usn_nds"}:
            base = float(bases.get(settings.nds_base, bases.get("wb_payable", 0.0)))
            amount = money(base * settings.nds_rate / 100)
            total += amount
            comment = "НДС выбран, но ставка не задана" if settings.nds_rate == 0 else ""
            rows.append({"Тип налога": "НДС", "Ставка": settings.nds_rate, "База": base, "Сумма": amount, "Комментарий": comment})
        if mode == "manual":
            total = money(settings.manual_amount)
            rows.append({"Тип налога": "Ручная сумма", "Ставка": 0.0, "База": float(bases.get("wb_payable", 0.0)), "Сумма": total, "Комментарий": ""})
        if not rows:
            rows.append({"Тип налога": "Не учитывать", "Ставка": 0.0, "База": float(bases.get("wb_payable", 0.0)), "Сумма": 0.0, "Комментарий": ""})
        return pd.DataFrame(rows), money(total)
