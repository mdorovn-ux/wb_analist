from __future__ import annotations

import pandas as pd

from wb_finance_analyst.domain.models import ColumnMap, CostItem
from wb_finance_analyst.services.numeric import money, numeric_series


class ProductProfitCalculator:
    def calculate(
        self,
        operations: pd.DataFrame,
        column_map: ColumnMap,
        costs: dict[str, CostItem] | None = None,
        external_expenses_total: float = 0.0,
    ) -> tuple[pd.DataFrame, list[str]]:
        costs = costs or {}
        warnings: list[str] = []
        if operations.empty or not column_map.product_name:
            return pd.DataFrame(), ["Нет данных для расчета прибыли по товарам"]

        df = operations.copy()
        product_col = column_map.product_name
        article_col = column_map.supplier_article
        nm_col = column_map.nm_id
        amount_col = column_map.seller_transfer
        qty_col = column_map.quantity
        doc_col = column_map.doc_type

        df["_amount"] = numeric_series(df[amount_col]) if amount_col else 0.0
        df["_qty"] = numeric_series(df[qty_col]) if qty_col and qty_col in df.columns else 0.0
        doc = df[doc_col].fillna("").astype(str).str.casefold() if doc_col else pd.Series("", index=df.index)
        sale_mask = doc.str.contains("продажа", na=False)
        return_mask = doc.str.contains("возврат", na=False)
        df["_sale_qty"] = df["_qty"].where(sale_mask, 0.0)
        df["_return_qty"] = df["_qty"].abs().where(return_mask, 0.0)
        df["_goods_amount"] = df["_amount"].where(sale_mask, 0.0) - df["_amount"].abs().where(return_mask, 0.0)

        if product_col not in df.columns:
            return pd.DataFrame(), [f"Не найдена колонка товара: {product_col}"]
        group_cols = [product_col]
        if "Тип отчета" in df.columns:
            group_cols.insert(0, "Тип отчета")
        if "report_kind" in df.columns:
            group_cols.insert(0, "report_kind")
        if article_col and article_col in df.columns:
            group_cols.append(article_col)
        if nm_col and nm_col in df.columns:
            group_cols.append(nm_col)

        grouped = (
            df.groupby(group_cols, dropna=False)
            .agg(
                Продано=("_sale_qty", "sum"),
                Возвращено=("_return_qty", "sum"),
                **{"К перечислению за товар": ("_goods_amount", "sum")},
            )
            .reset_index()
        )
        grouped["Чистое количество"] = grouped["Продано"] - grouped["Возвращено"]

        total_transfer = grouped["К перечислению за товар"].clip(lower=0).sum()
        cost_values = []
        packaging_values = []
        allocated_expenses = []
        for _, row in grouped.iterrows():
            product = str(row[product_col] or "")
            item = costs.get(product.casefold())
            if not item:
                item = costs.get(str(row.get(article_col, "")).casefold()) if article_col else None
            if row["Чистое количество"] < 0:
                warnings.append(f"Чистое количество меньше 0 для товара: {product}")
            if not item and row["Чистое количество"] > 0:
                warnings.append(f"Не задана себестоимость для товара: {product}")
            unit_cost = item.cost if item else 0.0
            unit_packaging = item.packaging if item else 0.0
            qty = max(float(row["Чистое количество"]), 0.0)
            cost_values.append(money(unit_cost * qty))
            packaging_values.append(money(unit_packaging * qty))
            share = float(row["К перечислению за товар"]) / total_transfer if total_transfer else 0.0
            allocated_expenses.append(money(max(share, 0.0) * external_expenses_total))

        grouped["Себестоимость"] = cost_values
        grouped["Упаковка"] = packaging_values
        grouped["Внешние расходы"] = allocated_expenses
        grouped["Валовая прибыль"] = grouped["К перечислению за товар"] - grouped["Себестоимость"] - grouped["Упаковка"]
        grouped["Чистая прибыль"] = grouped["Валовая прибыль"] - grouped["Внешние расходы"]
        grouped["Маржинальность %"] = grouped.apply(
            lambda row: row["Чистая прибыль"] / row["К перечислению за товар"] if row["К перечислению за товар"] else 0.0,
            axis=1,
        )
        money_cols = ["К перечислению за товар", "Себестоимость", "Упаковка", "Внешние расходы", "Валовая прибыль", "Чистая прибыль"]
        for col in money_cols:
            grouped[col] = grouped[col].map(money)
        return grouped.sort_values("Чистая прибыль", ascending=False).reset_index(drop=True), warnings
