from __future__ import annotations

import re
from collections.abc import Iterable

import pandas as pd

from wb_finance_analyst.config.column_aliases import COLUMN_ALIASES
from wb_finance_analyst.domain.models import ColumnMap


def normalize_header(value: object) -> str:
    text = str(value or "").casefold().strip()
    text = text.replace("ё", "е")
    text = re.sub(r"[^0-9a-zа-я%]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


class ColumnMapper:
    def __init__(self, aliases: dict[str, list[str]] | None = None) -> None:
        self.aliases = aliases or COLUMN_ALIASES

    def map_columns(self, columns: Iterable[object], saved: ColumnMap | None = None) -> ColumnMap:
        available = {normalize_header(col): str(col) for col in columns}
        values: dict[str, str | None] = {}
        saved = saved or ColumnMap()
        for field, aliases in self.aliases.items():
            saved_value = getattr(saved, field, None)
            if saved_value and saved_value in list(map(str, columns)):
                values[field] = saved_value
                continue
            values[field] = self._find_match(aliases, available)
        return ColumnMap(**values)

    def _find_match(self, aliases: list[str], available: dict[str, str]) -> str | None:
        normalized_aliases = [normalize_header(alias) for alias in aliases]
        for alias in normalized_aliases:
            if alias in available:
                return available[alias]
        for alias in normalized_aliases:
            for header, original in available.items():
                if alias and (alias in header or header in alias):
                    return original
        return None

    def mapping_table(self, df: pd.DataFrame, saved: ColumnMap | None = None) -> pd.DataFrame:
        mapped = self.map_columns(df.columns, saved)
        rows = []
        labels = {
            "date_order": "Дата заказа",
            "date_sale": "Дата продажи",
            "doc_type": "Тип документа",
            "payment_reason": "Обоснование",
            "quantity": "Количество",
            "product_name": "Товар",
            "seller_transfer": "К перечислению",
            "logistics": "Логистика",
            "storage": "Хранение",
            "deductions": "Удержания",
            "penalties": "Штрафы",
            "acceptance": "Приемка",
            "loyalty": "Лояльность",
        }
        for field, label in labels.items():
            rows.append({"Поле": label, "Колонка": getattr(mapped, field), "Статус": "OK" if getattr(mapped, field) else "Не найдено"})
        return pd.DataFrame(rows)
