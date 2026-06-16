from __future__ import annotations

from pathlib import Path

import pandas as pd

from wb_finance_analyst.config.defaults import COSTS_PATH, LEGACY_COSTS_PATH
from wb_finance_analyst.domain.models import CostItem
from wb_finance_analyst.services.numeric import to_number


class CostRepository:
    def __init__(self, path: Path = COSTS_PATH) -> None:
        self.path = path

    def load(self) -> dict[str, CostItem]:
        path = self.path
        if not path.exists() and self.path == COSTS_PATH and LEGACY_COSTS_PATH.exists():
            path = LEGACY_COSTS_PATH
        if not path.exists():
            return {}
        df = pd.read_excel(path)
        result: dict[str, CostItem] = {}
        for _, row in df.iterrows():
            product = str(row.get("Товар", "")).strip()
            if not product:
                continue
            result[product.casefold()] = CostItem(
                product=product,
                cost=to_number(row.get("Себестоимость", row.get("Себестоимость за 1 шт", 0))),
                packaging=to_number(row.get("Упаковка", row.get("Упаковка за 1 шт", 0))),
                comment=str(row.get("Комментарий", "") or ""),
            )
        return result

    def save(self, items: list[CostItem]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        df = pd.DataFrame([item.model_dump() for item in items])
        df = df.rename(columns={"product": "Товар", "cost": "Себестоимость", "packaging": "Упаковка", "comment": "Комментарий"})
        df.to_excel(self.path, index=False)

    def import_from_excel(self, path: Path) -> list[CostItem]:
        df = pd.read_excel(path)
        items = []
        for _, row in df.iterrows():
            product = str(row.get("Товар", "")).strip()
            if product:
                items.append(
                    CostItem(
                        product=product,
                        cost=to_number(row.get("Себестоимость", 0)),
                        packaging=to_number(row.get("Упаковка", 0)),
                        comment=str(row.get("Комментарий", "") or ""),
                    )
                )
        self.save(items)
        return items
