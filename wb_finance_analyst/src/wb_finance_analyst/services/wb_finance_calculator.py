from __future__ import annotations

from pathlib import Path

import pandas as pd

from wb_finance_analyst.config.settings import AppSettings
from wb_finance_analyst.domain.constants import SUMMARY_ORDER
from wb_finance_analyst.domain.models import LoadedReport, ReportPeriod, WBFinanceResult
from wb_finance_analyst.services.cost_repository import CostRepository
from wb_finance_analyst.services.excel_loader import ExcelLoader
from wb_finance_analyst.services.external_expenses import ExternalExpensesCalculator
from wb_finance_analyst.services.numeric import money, numeric_series
from wb_finance_analyst.services.product_profit_calculator import ProductProfitCalculator
from wb_finance_analyst.services.report_views import ReportViewBuilder


class WBFinanceCalculator:
    def __init__(
        self,
        loader: ExcelLoader | None = None,
        costs: CostRepository | None = None,
        product_profit: ProductProfitCalculator | None = None,
    ) -> None:
        self.loader = loader or ExcelLoader()
        self.costs = costs or CostRepository()
        self.product_profit = product_profit or ProductProfitCalculator()
        self.expenses_calculator = ExternalExpensesCalculator()
        self.view_builder = ReportViewBuilder()

    def calculate_from_paths(self, paths: list[Path], settings: AppSettings | None = None) -> WBFinanceResult:
        settings = settings or AppSettings()
        loaded = self.loader.load_many_raw_reports(paths, settings)
        return self.calculate_loaded(loaded, settings)

    def calculate_loaded(self, reports: list[LoadedReport], settings: AppSettings | None = None) -> WBFinanceResult:
        settings = settings or AppSettings()
        if not reports:
            return WBFinanceResult(warnings=["Нет данных для расчета"])

        warnings: list[str] = []
        frames = []
        source_files = []
        for report in reports:
            warnings.extend(report.warnings)
            source_files.append(str(report.path))
            df = report.dataframe.copy()
            df["_source_file"] = report.path.name
            frames.append(df)

        df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
        column_map = reports[0].column_map
        period = self._merge_periods([r.period for r in reports])
        operations = self._prepare_operations(df, column_map)
        summary = self._summary(operations, column_map)
        expenses = self.expenses_calculator.build_expenses(settings.external_expenses, summary["К перечислению за товар"])
        external_total = float(expenses["Сумма"].sum()) if not expenses.empty else 0.0
        cost_items = self.costs.load()
        product_profit, product_warnings = self.product_profit.calculate(operations, column_map, cost_items, external_total)
        warnings.extend(product_warnings)

        cost_total = float(product_profit["Себестоимость"].sum()) if not product_profit.empty else 0.0
        packaging_total = float(product_profit["Упаковка"].sum()) if not product_profit.empty else 0.0
        gross_profit = summary["Итого к оплате WB"] - cost_total - packaging_total
        net_profit = gross_profit - external_total
        summary["Себестоимость"] = money(cost_total)
        summary["Упаковка"] = money(packaging_total)
        summary["Реклама WB"] = 0.0
        summary["Внешние расходы"] = money(external_total)
        summary["УСН"] = 0.0
        summary["НДС"] = 0.0
        summary["Валовая прибыль"] = money(gross_profit)
        summary["Чистая прибыль"] = money(net_profit)
        summary["Маржинальность %"] = net_profit / summary["К перечислению за товар"] if summary["К перечислению за товар"] else 0.0

        reconciliation = pd.DataFrame(
            [{"Показатель": key, "Сумма": money(value) if not key.endswith("%") else value} for key, value in summary.items()]
        )
        products = self._products_table(product_profit, column_map)
        result = WBFinanceResult(
            period=period,
            source_files=source_files,
            settings_hash=settings.stable_hash(),
            summary={key: summary.get(key, 0.0) for key in SUMMARY_ORDER},
            reconciliation=reconciliation,
            products=products,
            product_profit=product_profit,
            expenses=expenses,
            management_profit=self._management_profit(summary),
            report_settings=pd.DataFrame([{"Настройка": "Источник данных", "Значение": "Excel"}]),
            operations=operations,
            warnings=warnings,
        )
        self.view_builder.build(result, column_map, cost_items)
        return result

    def _management_profit(self, summary: dict[str, float]) -> pd.DataFrame:
        rows = [
            "Итого к оплате WB",
            "Себестоимость",
            "Упаковка",
            "Реклама WB",
            "Внешние расходы",
            "УСН",
            "НДС",
            "Чистая прибыль",
            "Маржинальность %",
        ]
        return pd.DataFrame([{"Показатель": row, "Сумма": summary.get(row, 0.0)} for row in rows])

    def _prepare_operations(self, df: pd.DataFrame, column_map) -> pd.DataFrame:
        prepared = df.copy()
        for field in ["seller_transfer", "logistics", "storage", "deductions", "penalties", "acceptance", "loyalty", "quantity", "wb_sold"]:
            column = getattr(column_map, field, None)
            if column and column in prepared.columns:
                prepared[column] = numeric_series(prepared[column])
        return prepared

    def _summary(self, df: pd.DataFrame, column_map) -> dict[str, float]:
        reason = df[column_map.payment_reason].fillna("").astype(str).str.casefold() if column_map.payment_reason else pd.Series("", index=df.index)
        transfer = numeric_series(df[column_map.seller_transfer]) if column_map.seller_transfer else pd.Series(0, index=df.index)
        sale_mask = reason.str.fullmatch(r"\s*продажа\s*", na=False)
        return_mask = reason.str.fullmatch(r"\s*возврат\s*", na=False)
        return_compensation_mask = reason.str.contains("добровольная компенсация при возврате", na=False)
        sales = transfer.where(sale_mask, 0.0).sum()
        returns = abs(transfer.where(return_mask, 0.0).sum())
        return_compensation = transfer.where(return_compensation_mask, 0.0).sum()
        goods = sales - returns + return_compensation

        logistics = self._sum(df, column_map.logistics)
        storage = self._sum(df, column_map.storage)
        deductions = self._sum(df, column_map.deductions)
        penalties = self._sum(df, column_map.penalties)
        acceptance = self._sum(df, column_map.acceptance)
        loyalty = self._sum(df, column_map.loyalty)
        payable = goods - logistics - storage - deductions - penalties - acceptance - loyalty
        return {
            "К перечислению по продажам": money(sales),
            "Возвраты": money(returns),
            "К перечислению за товар": money(goods),
            "Логистика": money(logistics),
            "Хранение": money(storage),
            "Удержания/выплаты": money(deductions),
            "Штрафы": money(penalties),
            "Операции при приемке": money(acceptance),
            "Лояльность": money(loyalty),
            "Итого к оплате WB": money(payable),
            "Себестоимость": 0.0,
            "Валовая прибыль": 0.0,
            "Чистая прибыль": 0.0,
            "Маржинальность %": 0.0,
        }

    def _sum(self, df: pd.DataFrame, column: str | None) -> float:
        if not column or column not in df.columns:
            return 0.0
        return float(numeric_series(df[column]).sum())

    def _split_sales_returns(self, df: pd.DataFrame, column_map) -> tuple[pd.DataFrame, pd.DataFrame]:
        if not column_map.payment_reason or column_map.payment_reason not in df.columns:
            return df.head(0), df.head(0)
        reason = df[column_map.payment_reason].fillna("").astype(str).str.casefold()
        sales = df[reason.str.fullmatch(r"\s*продажа\s*", na=False)].copy()
        returns = df[reason.str.fullmatch(r"\s*возврат\s*", na=False)].copy()
        return sales, returns

    def _products_table(self, product_profit: pd.DataFrame, column_map) -> pd.DataFrame:
        if product_profit.empty:
            return product_profit
        cols = ["report_kind", "Тип отчета", column_map.product_name, column_map.supplier_article, column_map.nm_id, "Продано", "Возвращено", "Чистое количество", "К перечислению за товар"]
        cols = [col for col in cols if col and col in product_profit.columns]
        return product_profit[cols].copy()

    def _merge_periods(self, periods: list[ReportPeriod]) -> ReportPeriod:
        starts = [p.start for p in periods if p.start]
        ends = [p.end for p in periods if p.end]
        return ReportPeriod(start=min(starts) if starts else None, end=max(ends) if ends else None)
