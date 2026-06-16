from __future__ import annotations

from pathlib import Path

import pandas as pd

from wb_finance_analyst.domain.models import ReportPeriod, WBFinanceResult
from wb_finance_analyst.services.numeric import money
from wb_finance_analyst.services.report_views import ReportViewBuilder


class ReportMerger:
    def merge_generated_reports(self, paths: list[Path]) -> WBFinanceResult:
        warnings: list[str] = []
        summaries = []
        products = []
        operations = []
        ads = []
        expenses = []
        periods: list[ReportPeriod] = []
        sources = []
        for path in paths:
            try:
                with pd.ExcelFile(path) as xls:
                    sheet_names = list(xls.sheet_names)
                    sources.append(str(path))
                    if "_DATA_SUMMARY" in sheet_names:
                        summaries.append(pd.read_excel(xls, sheet_name="_DATA_SUMMARY"))
                        products.append(self._read_if_exists(xls, sheet_names, "_DATA_PRODUCTS"))
                        operations.append(self._read_if_exists(xls, sheet_names, "_DATA_OPERATIONS"))
                        ads.append(self._read_if_exists(xls, sheet_names, "_DATA_ADS"))
                        expenses.append(self._read_if_exists(xls, sheet_names, "_DATA_EXPENSES"))
                        meta = self._read_if_exists(xls, sheet_names, "_DATA_META")
                        periods.append(self._period_from_meta(meta))
                    elif "Общая сводка" in sheet_names or "Сверка WB" in sheet_names:
                        warnings.append(f"Файл без технических листов, использованы видимые листы: {path.name}")
                        summary_sheet = "Общая сводка" if "Общая сводка" in sheet_names else "Сверка WB"
                        summaries.append(pd.read_excel(xls, sheet_name=summary_sheet))
                        products.append(self._read_if_exists(xls, sheet_names, "Прибыль по товарам"))
                        ads.append(self._read_if_exists(xls, sheet_names, "Реклама WB"))
                        expenses.append(self._read_if_exists(xls, sheet_names, "Внешние расходы"))
                    else:
                        warnings.append(f"Файл не похож на отчет WB analyst: {path.name}")
            except Exception as exc:
                warnings.append(f"Не удалось прочитать файл {path.name}: {exc}")

        summary = self._merge_summary(summaries)
        product_profit = self._merge_products(products)
        non_empty_operations = [x for x in operations if not x.empty]
        non_empty_ads = [x for x in ads if not x.empty]
        non_empty_expenses = [x for x in expenses if not x.empty]
        operations_df = pd.concat(non_empty_operations, ignore_index=True) if non_empty_operations else pd.DataFrame()
        ads_df = pd.concat(non_empty_ads, ignore_index=True) if non_empty_ads else pd.DataFrame()
        expenses_df = pd.concat(non_empty_expenses, ignore_index=True) if non_empty_expenses else pd.DataFrame()
        period = self._merge_periods(periods)
        reconciliation = pd.DataFrame([{"Показатель": key, "Сумма": value} for key, value in summary.items()])
        result = WBFinanceResult(
            period=period,
            source_files=sources,
            summary=summary,
            reconciliation=reconciliation,
            products=product_profit,
            product_profit=product_profit,
            operations=operations_df,
            ads=ads_df,
            expenses=expenses_df,
            warnings=warnings,
        )
        views = ReportViewBuilder()
        result.products = views.products_table(result.products)
        result.product_profit = views.product_profit_table(result.product_profit)
        result.expenses = views.amount_table(result.expenses, preferred_label_columns=("Расход", "Статья", "Название"), amount_candidates=("Сумма", "amount"))
        result.legend = views.legend_table(result, "both")
        return result

    def _read_if_exists(self, excel_file: pd.ExcelFile, sheets: list[str], sheet: str) -> pd.DataFrame:
        return pd.read_excel(excel_file, sheet_name=sheet) if sheet in sheets else pd.DataFrame()

    def _period_from_meta(self, meta: pd.DataFrame) -> ReportPeriod:
        if meta.empty or "key" not in meta.columns:
            return ReportPeriod()
        values = dict(zip(meta["key"], meta["value"]))
        start = pd.to_datetime(values.get("period_start"), errors="coerce")
        end = pd.to_datetime(values.get("period_end"), errors="coerce")
        return ReportPeriod(
            start=start.date() if not pd.isna(start) else None,
            end=end.date() if not pd.isna(end) else None,
        )

    def _merge_summary(self, frames: list[pd.DataFrame]) -> dict[str, float]:
        merged: dict[str, float] = {}
        for df in frames:
            if df.empty or "Показатель" not in df.columns:
                continue
            value_col = "Сумма" if "Сумма" in df.columns else df.columns[-1]
            for _, row in df.iterrows():
                key = str(row["Показатель"])
                if key in {"Итого к оплате WB", "Чистая прибыль", "Маржинальность %"}:
                    continue
                merged[key] = merged.get(key, 0.0) + float(pd.to_numeric(pd.Series([row[value_col]]), errors="coerce").fillna(0).iloc[0])
        goods = merged.get("К перечислению за товар", merged.get("К перечислению по продажам", 0.0) - merged.get("Возвраты", 0.0))
        payable = goods - merged.get("Логистика", 0.0) - merged.get("Хранение", 0.0) - merged.get("Удержания/выплаты", 0.0) - merged.get("Штрафы", 0.0) - merged.get("Операции при приемке", 0.0) - merged.get("Лояльность", 0.0)
        gross = payable - merged.get("Себестоимость", 0.0) - merged.get("Упаковка", 0.0)
        net = gross - merged.get("Внешние расходы", 0.0) - merged.get("Реклама WB", 0.0) - merged.get("УСН", 0.0) - merged.get("НДС", 0.0)
        merged["К перечислению за товар"] = money(goods)
        merged["Итого к оплате WB"] = money(payable)
        merged["Валовая прибыль"] = money(gross)
        merged["Чистая прибыль"] = money(net)
        merged["Маржинальность %"] = net / goods if goods else 0.0
        return {key: money(value) if not key.endswith("%") else value for key, value in merged.items()}

    def _merge_products(self, frames: list[pd.DataFrame]) -> pd.DataFrame:
        frames = [df for df in frames if not df.empty]
        if not frames:
            return pd.DataFrame()
        df = pd.concat(frames, ignore_index=True)
        product_col = "Название" if "Название" in df.columns else "Товар" if "Товар" in df.columns else df.columns[0]
        numeric_cols = [col for col in df.columns if pd.api.types.is_numeric_dtype(df[col])]
        grouped = df.groupby(product_col, dropna=False)[numeric_cols].sum().reset_index()
        if "К перечислению за товар" in grouped.columns and "Чистая прибыль" in grouped.columns:
            grouped["Маржинальность %"] = grouped.apply(lambda row: row["Чистая прибыль"] / row["К перечислению за товар"] if row["К перечислению за товар"] else 0.0, axis=1)
        return grouped

    def _merge_periods(self, periods: list[ReportPeriod]) -> ReportPeriod:
        starts = [p.start for p in periods if p.start]
        ends = [p.end for p in periods if p.end]
        return ReportPeriod(start=min(starts) if starts else None, end=max(ends) if ends else None)
