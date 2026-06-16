from __future__ import annotations

from datetime import datetime
from typing import Iterable

import pandas as pd

from wb_finance_analyst.domain.constants import SUMMARY_ORDER
from wb_finance_analyst.domain.models import ColumnMap, CostItem, WBFinanceResult
from wb_finance_analyst.services.numeric import money, numeric_series


SUMMARY_VIEW_ORDER = [
    "Продажа WB",
    "Возвраты WB",
    "Продажа WB чистая",
    "К перечислению по продажам",
    "Возвраты к перечислению",
    "К перечислению за товар",
    "Логистика",
    "Хранение",
    "Операции при приёмке",
    "Удержания/выплаты",
    "Штрафы",
    "Лояльность",
    "Реклама WB",
    "Внешние расходы",
    "Себестоимость",
    "Упаковка",
    "УСН",
    "НДС",
    "Итого к оплате WB",
    "Валовая прибыль",
    "Чистая прибыль",
    "Маржинальность %",
]

MANAGEMENT_VIEW_ORDER = [
    "Итого к оплате WB",
    "Себестоимость",
    "Упаковка",
    "Реклама WB",
    "Логистика до WB",
    "Аренда",
    "Коммуналка",
    "Бухгалтер",
    "Менеджер",
    "Зарплаты",
    "Внешняя реклама",
    "Прочие расходы",
    "УСН",
    "НДС",
    "Валовая прибыль",
    "Чистая прибыль",
    "Маржинальность %",
]

SALES_RETURN_COLUMNS = [
    "Товар",
    "Себестоимость/шт",
    "Розничная WB",
    "Количество",
    "WB перечисление",
    "Итого",
    "Средняя на шт",
    "Маржа",
    "Маржа %",
]

TECHNICAL_COLUMNS = {
    "report_kind",
    "report_id",
    "date_from",
    "date_to",
    "create_date",
    "seller_finance_name",
    "report_type",
    "Тип отчета",
    "Тип отчёта",
    "product",
    "nm_id",
    "nmId",
    "nmid",
}

AD_TYPE_LABELS = {
    "4": "Каталог",
    "5": "Карточка товара",
    "6": "Поиск",
    "7": "Рекомендации",
    "8": "Автоматическая кампания",
    "9": "Аукцион",
}

VALUE_LABELS = {
    "api": "Wildberries API",
    "wb_api": "Wildberries API",
    "promotion_api": "Wildberries API",
    "WB API": "Wildberries API",
    "manual": "Вручную",
    "none": "Не используется",
    "included": "Уже учтено в удержаниях WB",
    "usn": "УСН",
    "nds": "НДС",
    "usn_nds": "УСН + НДС",
    "main": "Основной",
    "buyouts": "По выкупам",
    "both": "Оба",
    "wb_payable": "Итого к оплате WB",
    "goods": "К перечислению за товар",
    "gross_profit": "Валовая прибыль",
    True: "да",
    False: "нет",
}


class ReportViewBuilder:
    def build(self, result: WBFinanceResult, column_map: ColumnMap, costs: dict[str, CostItem], report_kind: str = "main") -> None:
        result.reconciliation = self.summary_table(result, column_map)
        result.management_profit = self.management_profit_table(result)
        sales, sales_warnings = self.operations_table(
            result.operations,
            column_map,
            costs,
            document_name="Продажа",
            report_kind=report_kind,
        )
        returns, return_warnings = self.operations_table(
            result.operations,
            column_map,
            costs,
            document_name="Возврат",
            report_kind=report_kind,
        )
        result.sales = sales
        result.returns = returns
        result.products = self.products_table(result.products if not result.products.empty else result.product_profit)
        result.product_profit = self.product_profit_table(result.product_profit)
        result.ads = self.ads_table(result.ads)
        result.expenses = self.amount_table(result.expenses, preferred_label_columns=("Расход", "Статья", "Название"), amount_candidates=("Сумма", "amount"))
        result.taxes = self.amount_table(result.taxes, preferred_label_columns=("Тип налога",), amount_candidates=("Сумма", "amount"))
        result.report_settings = self.settings_table(result.report_settings)
        result.legend = self.legend_table(result, report_kind)
        self._extend_unique(result.warnings, sales_warnings + return_warnings)

    def summary_table(self, result: WBFinanceResult, column_map: ColumnMap) -> pd.DataFrame:
        values = {name: result.total(name) for name in SUMMARY_ORDER}
        values["Возвраты к перечислению"] = result.total("Возвраты")
        values["Продажа WB"] = self._sum_by_doc(result.operations, column_map, "Продажа")
        values["Возвраты WB"] = self._sum_by_doc(result.operations, column_map, "Возврат")
        values["Продажа WB чистая"] = values["Продажа WB"] - values["Возвраты WB"]
        values["Операции при приёмке"] = result.total("Операции при приемке") or result.total("Операции при приёмке")
        rows = [{"Показатель": name, "Сумма": self._value(values.get(name, 0.0), name)} for name in SUMMARY_VIEW_ORDER]
        return pd.DataFrame(rows, columns=["Показатель", "Сумма"])

    def management_profit_table(self, result: WBFinanceResult) -> pd.DataFrame:
        values = {name: result.total(name) for name in MANAGEMENT_VIEW_ORDER}
        expenses = result.expenses if result.expenses is not None else pd.DataFrame()
        if not expenses.empty:
            for source_col in ("Расход", "Показатель", "Статья", "Название"):
                if source_col in expenses.columns:
                    name_col = source_col
                    break
            else:
                name_col = ""
            amount_col = "Сумма" if "Сумма" in expenses.columns else ""
            if name_col and amount_col:
                grouped = expenses.groupby(expenses[name_col].fillna("").astype(str), dropna=False)[amount_col].sum()
                for name in ["Логистика до WB", "Аренда", "Коммуналка", "Бухгалтер", "Менеджер", "Зарплаты", "Внешняя реклама", "Прочие расходы"]:
                    values[name] = float(grouped.get(name, 0.0))
        rows = [{"Показатель": name, "Сумма": self._value(values.get(name, 0.0), name)} for name in MANAGEMENT_VIEW_ORDER]
        return pd.DataFrame(rows, columns=["Показатель", "Сумма"])

    def products_table(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return df
        table = df.copy()
        product_col = self._product_column(table)
        if not product_col:
            return self._drop_technical_columns(table)
        table = self._rename_product_column(table, product_col)
        grouped = self._group_by_product(table)
        return self._drop_technical_columns(grouped)

    def product_profit_table(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return df
        table = self._without_total_rows(df.copy())
        product_col = self._product_column(table)
        if product_col:
            table = self._rename_product_column(table, product_col)
            table = self._group_by_product(table)
        table = self._drop_technical_columns(table)
        return self._append_product_profit_total(table)

    def ads_table(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return self._append_amount_total(self._drop_technical_columns(df), ("Расход",))
        table = self._drop_technical_columns(self._without_total_rows(df.copy()))
        if "Дата" in table.columns:
            table["Дата"] = table["Дата"].map(self._format_datetime_minute)
        if "Тип рекламы" in table.columns:
            table["Тип рекламы"] = table["Тип рекламы"].map(self._ad_type_label)
        if "Товар" in table.columns and table["Товар"].fillna("").astype(str).str.strip().eq("").all():
            table = table.drop(columns=["Товар"])
        return self._append_amount_total(table, ("Расход",), ("Кампания", "Дата"))

    def amount_table(self, df: pd.DataFrame, preferred_label_columns: tuple[str, ...], amount_candidates: tuple[str, ...]) -> pd.DataFrame:
        table = self._drop_technical_columns(self._without_total_rows(df.copy())) if not df.empty else df.copy()
        return self._append_amount_total(table, amount_candidates, preferred_label_columns)

    def settings_table(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return df
        table = df.copy()
        if "Настройка" in table.columns and "Значение" in table.columns:
            table["Значение"] = table.apply(lambda row: self._humanize_setting_value(row["Настройка"], row["Значение"]), axis=1)
        return table

    def legend_table(self, result: WBFinanceResult, report_kind: str) -> pd.DataFrame:
        settings = self._settings_dict(result.report_settings)
        source = settings.get("Источник данных") or ("Wildberries API" if "WB API" in result.source_files else "Excel")
        rows = [
            {"Раздел": "Период отчёта", "Значение": result.period.label},
            {"Раздел": "Тип отчёта", "Значение": VALUE_LABELS.get(report_kind, report_kind)},
            {"Раздел": "Источник данных", "Значение": self._humanize_setting_value("Источник данных", source)},
            {"Раздел": "Дата формирования", "Значение": result.generated_at.strftime("%Y-%m-%d %H:%M:%S")},
            {"Раздел": "Как читать отчёт", "Значение": "1. Сначала откройте лист «Общая сводка» — там показана сверка с Wildberries: продажи, возвраты, удержания, логистика и итог к оплате."},
            {"Раздел": "Как читать отчёт", "Значение": "2. Лист «Управленческая прибыль» показывает прибыль с учётом себестоимости, рекламы, налогов и внешних расходов."},
            {"Раздел": "Как читать отчёт", "Значение": "3. Лист «Продажи» показывает сгруппированные продажи по товарам и розничной цене WB."},
            {"Раздел": "Как читать отчёт", "Значение": "4. Лист «Возвраты» показывает сгруппированные возвраты."},
            {"Раздел": "Как читать отчёт", "Значение": "5. Лист «Товары» показывает общую товарную аналитику."},
            {"Раздел": "Как читать отчёт", "Значение": "6. Лист «Прибыль по товарам» показывает прибыльность по каждому товару."},
            {"Раздел": "Как читать отчёт", "Значение": "7. Лист «Реклама WB» показывает рекламные расходы, если подключён WB Promotion API."},
            {"Раздел": "Как читать отчёт", "Значение": "8. Лист «Внешние расходы» показывает расходы, введённые пользователем вручную."},
            {"Раздел": "Как читать отчёт", "Значение": "9. Лист «Налоги» показывает рассчитанные налоги по выбранным настройкам."},
            {"Раздел": "Как читать отчёт", "Значение": "10. Лист «Предупреждения» показывает проблемы и замечания, которые нужно проверить."},
        ]
        ad_allocation_note = settings.get("Учет рекламы WB")
        if ad_allocation_note:
            rows.append({"Раздел": "Реклама WB", "Значение": ad_allocation_note})
        return pd.DataFrame(rows, columns=["Раздел", "Значение"])

    def operations_table(
        self,
        operations: pd.DataFrame,
        column_map: ColumnMap,
        costs: dict[str, CostItem],
        document_name: str,
        report_kind: str = "main",
    ) -> tuple[pd.DataFrame, list[str]]:
        warnings: list[str] = []
        if operations.empty:
            return pd.DataFrame(columns=SALES_RETURN_COLUMNS), [f"Нет {self._plural(document_name)} за выбранный период"]

        required = [
            (column_map.doc_type, "Не найдено поле типа документа"),
            (column_map.seller_transfer, "Не найдено поле WB перечисления / forPay"),
        ]
        for column, message in required:
            if not column or column not in operations.columns:
                warnings.append(message)
                return pd.DataFrame(columns=SALES_RETURN_COLUMNS), warnings
        product_col = self._first_existing(operations, [column_map.supplier_article, column_map.product_name, "vendor_code", "product"])
        retail_col = self._first_existing(operations, [column_map.retail_price, "retail_price"])
        if not product_col:
            warnings.append("Не найдено поле товара / vendorCode / Артикул поставщика")
            return pd.DataFrame(columns=SALES_RETURN_COLUMNS), warnings
        if not retail_col:
            warnings.append("Не найдено поле розничной цены")
            return pd.DataFrame(columns=SALES_RETURN_COLUMNS), warnings

        doc = operations[column_map.doc_type].fillna("").astype(str).str.strip().str.casefold()
        filtered = operations[doc.str.contains(document_name.casefold(), na=False)].copy()
        if filtered.empty:
            warnings.append(f"Нет {self._plural(document_name)} за выбранный период")
            return pd.DataFrame(columns=SALES_RETURN_COLUMNS), warnings

        filtered["_view_product"] = filtered[product_col].fillna("").astype(str).str.strip()
        filtered["_retail_price"] = numeric_series(filtered[retail_col])
        filtered["_seller_payment"] = numeric_series(filtered[column_map.seller_transfer])
        qty_col = self._first_existing(filtered, [column_map.quantity, "quantity"])
        wb_col = self._first_existing(filtered, [column_map.wb_sold, "wb_sale_amount"])
        filtered["_qty"] = numeric_series(filtered[qty_col]).abs() if qty_col else 1.0
        filtered["_wb_amount"] = numeric_series(filtered[wb_col]).abs() if wb_col else 0.0
        filtered = filtered[(filtered["_qty"] != 0) | (filtered["_seller_payment"] != 0) | (filtered["_wb_amount"] != 0)].copy()
        if filtered.empty:
            warnings.append(f"Нет {self._plural(document_name)} за выбранный период")
            return pd.DataFrame(columns=SALES_RETURN_COLUMNS), warnings
        group_cols = ["_view_product", "_retail_price"]
        include_kind = report_kind == "both" and "Тип отчета" in filtered.columns
        if include_kind:
            group_cols.insert(0, "Тип отчета")

        rows = []
        for keys, group in filtered.groupby(group_cols, dropna=False, sort=True):
            if not isinstance(keys, tuple):
                keys = (keys,)
            type_label = keys[0] if include_kind else None
            product = keys[1 if include_kind else 0]
            retail_price = keys[2 if include_kind else 1]
            quantity = int(group["_qty"].sum())
            seller_payment = money(group["_seller_payment"].sum())
            unit_cost = self._unit_cost(costs, product)
            if unit_cost == 0 and str(product).strip():
                warnings.append(f"Не задана себестоимость для товара: {product}")
            margin = money(seller_payment - unit_cost * quantity)
            row = {
                "Товар": product,
                "Себестоимость/шт": money(unit_cost),
                "Розничная WB": money(retail_price),
                "Количество": quantity,
                "WB перечисление": seller_payment,
                "Итого": seller_payment,
                "Средняя на шт": money(seller_payment / quantity) if quantity else 0.0,
                "Маржа": margin,
                "Маржа %": margin / seller_payment if seller_payment else 0.0,
            }
            if include_kind:
                row = {"Тип отчёта": type_label, **row}
            rows.append(row)

        df = pd.DataFrame(rows)
        if df.empty:
            return pd.DataFrame(columns=SALES_RETURN_COLUMNS), warnings
        sort_cols = ["Тип отчёта", "Товар", "Розничная WB"] if include_kind else ["Товар", "Розничная WB"]
        df = df.sort_values(sort_cols).reset_index(drop=True)
        df = self._append_total_row(df, include_kind)
        columns = (["Тип отчёта"] if include_kind else []) + SALES_RETURN_COLUMNS
        return df[columns], list(dict.fromkeys(warnings))

    def _append_total_row(self, df: pd.DataFrame, include_kind: bool) -> pd.DataFrame:
        quantity = float(df["Количество"].sum()) if "Количество" in df.columns else 0.0
        total = float(df["Итого"].sum()) if "Итого" in df.columns else 0.0
        margin = float(df["Маржа"].sum()) if "Маржа" in df.columns else 0.0
        row = {
            "Товар": "Итого",
            "Себестоимость/шт": "",
            "Розничная WB": "",
            "Количество": quantity,
            "WB перечисление": money(df["WB перечисление"].sum()),
            "Итого": money(total),
            "Средняя на шт": money(total / quantity) if quantity else 0.0,
            "Маржа": money(margin),
            "Маржа %": margin / total if total else 0.0,
        }
        if include_kind:
            row = {"Тип отчёта": "", **row}
        return pd.concat([df, pd.DataFrame([row])], ignore_index=True)

    def _append_product_profit_total(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty or "Товар" not in df.columns:
            return df
        total_columns = [
            "Продано",
            "Возвращено",
            "К перечислению за товар",
            "Чистое количество",
            "Себестоимость",
            "Упаковка",
            "Внешние расходы",
            "Валовая прибыль",
            "Чистая прибыль",
        ]
        row = {column: "" for column in df.columns}
        row["Товар"] = "Итого"
        for column in total_columns:
            if column in df.columns:
                row[column] = money(numeric_series(df[column]).sum())
        margin_col = "Маржинальность %"
        if margin_col in df.columns:
            goods = float(row.get("К перечислению за товар") or 0.0)
            profit = float(row.get("Чистая прибыль") or 0.0)
            row[margin_col] = profit / goods if goods else 0.0
        return pd.concat([df, pd.DataFrame([row])], ignore_index=True)

    def _append_amount_total(
        self,
        df: pd.DataFrame,
        amount_candidates: tuple[str, ...],
        label_candidates: tuple[str, ...] = (),
    ) -> pd.DataFrame:
        if df.empty:
            return df
        amount_col = self._first_existing(df, amount_candidates)
        if not amount_col:
            return df
        if len(df.columns) == 1 and df.columns[0] == amount_col:
            df = df.copy()
            df.insert(0, "Показатель", "")
        row = {column: "" for column in df.columns}
        label_col = self._first_existing(df, label_candidates) or df.columns[0]
        row[label_col] = "Итого"
        row[amount_col] = money(numeric_series(df[amount_col]).sum())
        return pd.concat([df, pd.DataFrame([row])], ignore_index=True)

    def _group_by_product(self, df: pd.DataFrame) -> pd.DataFrame:
        if "Товар" not in df.columns:
            return df
        df = self._without_total_rows(df)
        df = self._without_empty_zero_products(df)
        numeric_cols = [column for column in df.columns if column != "Товар" and pd.api.types.is_numeric_dtype(pd.to_numeric(df[column], errors="coerce"))]
        other_cols = [column for column in df.columns if column not in set(numeric_cols) | {"Товар"}]
        grouped = df.copy()
        for column in numeric_cols:
            grouped[column] = numeric_series(grouped[column])
        agg = {column: "sum" for column in numeric_cols}
        for column in other_cols:
            agg[column] = "first"
        result = grouped.groupby("Товар", dropna=False, as_index=False).agg(agg)
        if "Маржинальность %" in result.columns and "Чистая прибыль" in result.columns and "К перечислению за товар" in result.columns:
            result["Маржинальность %"] = result.apply(
                lambda row: row["Чистая прибыль"] / row["К перечислению за товар"] if row["К перечислению за товар"] else 0.0,
                axis=1,
            )
        return result

    def _without_empty_zero_products(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty or "Товар" not in df.columns:
            return df
        numeric_cols = [column for column in df.columns if column != "Товар" and pd.api.types.is_numeric_dtype(pd.to_numeric(df[column], errors="coerce"))]
        if not numeric_cols:
            return df
        product_empty = df["Товар"].fillna("").astype(str).str.strip().eq("")
        numeric_zero = pd.DataFrame({column: numeric_series(df[column]) for column in numeric_cols}).sum(axis=1).eq(0)
        return df.loc[~(product_empty & numeric_zero)].copy()

    def _without_total_rows(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return df
        mask = pd.Series(False, index=df.index)
        for column in df.columns:
            mask = mask | df[column].fillna("").astype(str).str.strip().eq("Итого")
        return df.loc[~mask].copy()

    def _drop_technical_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return df
        return df.drop(columns=[column for column in df.columns if column in TECHNICAL_COLUMNS], errors="ignore")

    def _product_column(self, df: pd.DataFrame) -> str:
        return self._first_existing(df, ["vendor_code", "Товар", "Артикул поставщика", "Название", "product"])

    def _rename_product_column(self, df: pd.DataFrame, product_col: str) -> pd.DataFrame:
        table = df.copy()
        if product_col != "Товар":
            if "Товар" in table.columns:
                table = table.drop(columns=["Товар"])
            table = table.rename(columns={product_col: "Товар"})
        return table

    def _sum_by_doc(self, operations: pd.DataFrame, column_map: ColumnMap, document_name: str) -> float:
        doc_col = column_map.doc_type
        amount_col = column_map.wb_sold
        if operations.empty or not doc_col or not amount_col or doc_col not in operations.columns or amount_col not in operations.columns:
            return 0.0
        doc = operations[doc_col].fillna("").astype(str).str.strip().str.casefold()
        return money(numeric_series(operations[amount_col]).where(doc.str.contains(document_name.casefold(), na=False), 0.0).sum())

    def _unit_cost(self, costs: dict[str, CostItem], product: object) -> float:
        item = costs.get(str(product or "").strip().casefold())
        return float(item.cost) if item else 0.0

    def _first_existing(self, df: pd.DataFrame, candidates: Iterable[str | None]) -> str:
        for column in candidates:
            if column and column in df.columns:
                return column
        return ""

    def _value(self, value: float, name: str) -> float:
        return float(value or 0.0) if name.endswith("%") else money(value)

    def _format_datetime_minute(self, value: object) -> str:
        if value in (None, ""):
            return ""
        parsed = pd.to_datetime(value, errors="coerce")
        if pd.isna(parsed):
            text = str(value).replace("T", " ")
            return text[:16]
        try:
            return parsed.strftime("%Y-%m-%d %H:%M")
        except ValueError:
            return str(value)

    def _ad_type_label(self, value: object) -> object:
        if value in (None, ""):
            return value
        text = str(value).strip()
        if text.endswith(".0"):
            text = text[:-2]
        return AD_TYPE_LABELS.get(text, value)

    def _settings_dict(self, df: pd.DataFrame) -> dict[str, object]:
        if df.empty or "Настройка" not in df.columns or "Значение" not in df.columns:
            return {}
        return dict(zip(df["Настройка"], df["Значение"]))

    def _humanize_setting_value(self, setting: object, value: object) -> object:
        if isinstance(value, bool):
            return VALUE_LABELS[value]
        if value in (None, ""):
            return value
        if isinstance(value, str):
            text = value.strip()
            lowered = text.casefold()
            if lowered in {"true", "false"}:
                return "да" if lowered == "true" else "нет"
            if text in VALUE_LABELS:
                return VALUE_LABELS[text]
            if lowered in VALUE_LABELS:
                return VALUE_LABELS[lowered]
            if "T" in text:
                parsed = pd.to_datetime(text, errors="coerce")
                if not pd.isna(parsed):
                    return parsed.strftime("%Y-%m-%d %H:%M:%S")
            return text
        return value

    def _plural(self, document_name: str) -> str:
        return "продаж" if document_name == "Продажа" else "возвратов"

    def _extend_unique(self, target: list[str], values: Iterable[str]) -> None:
        seen = set(target)
        for value in values:
            if value and value not in seen:
                target.append(value)
                seen.add(value)
