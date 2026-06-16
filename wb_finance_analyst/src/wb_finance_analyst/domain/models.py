from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field


class ReportPeriod(BaseModel):
    start: date | None = None
    end: date | None = None

    @property
    def label(self) -> str:
        if self.start and self.end:
            if self.start == self.end:
                return self.start.strftime("%d.%m.%Y")
            return f"{self.start.strftime('%d.%m.%Y')} - {self.end.strftime('%d.%m.%Y')}"
        return "Период не определен"


class CostItem(BaseModel):
    product: str
    cost: float = 0.0
    packaging: float = 0.0
    comment: str = ""


class ExternalExpense(BaseModel):
    name: str
    amount: float = 0.0
    mode: str = "fixed"
    comment: str = ""


class TaxSettings(BaseModel):
    mode: str = "none"
    usn_rate: float = 0.0
    nds_rate: float = 0.0
    usn_base: str = "wb_payable"
    nds_base: str = "wb_payable"
    manual_amount: float = 0.0


class APISettings(BaseModel):
    use_api_by_default: bool = True
    use_excel_as_fallback: bool = True
    ad_source: str = "none"
    tax_settings: TaxSettings = Field(default_factory=TaxSettings)
    manual_ad_expense: float = 0.0
    expense_allocation: str = "none"
    last_report_kind: str = "main"
    business_expenses_template: dict[str, float] = Field(default_factory=dict)


class ColumnMap(BaseModel):
    date_order: str | None = None
    date_sale: str | None = None
    doc_type: str | None = None
    payment_reason: str | None = None
    quantity: str | None = None
    product_name: str | None = None
    supplier_article: str | None = None
    nm_id: str | None = None
    barcode: str | None = None
    retail_price: str | None = None
    wb_sold: str | None = None
    seller_transfer: str | None = None
    logistics: str | None = None
    storage: str | None = None
    deductions: str | None = None
    penalties: str | None = None
    acceptance: str | None = None
    loyalty: str | None = None
    loyalty_points: str | None = None
    transfer_delay_change: str | None = None
    wb_reward_correction: str | None = None
    loyalty_compensation: str | None = None

    def missing_required(self) -> list[str]:
        required = {
            "doc_type": "Тип документа",
            "payment_reason": "Обоснование для оплаты",
            "seller_transfer": "К перечислению продавцу",
            "logistics": "Логистика",
            "product_name": "Товар",
        }
        return [label for field, label in required.items() if not getattr(self, field)]


class LoadedReport(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    path: Path
    dataframe: pd.DataFrame
    column_map: ColumnMap
    period: ReportPeriod
    warnings: list[str] = Field(default_factory=list)


class WBFinanceResult(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    report_id: str = Field(default_factory=lambda: str(uuid4()))
    period: ReportPeriod = Field(default_factory=ReportPeriod)
    generated_at: datetime = Field(default_factory=datetime.now)
    source_files: list[str] = Field(default_factory=list)
    settings_hash: str = ""
    summary: dict[str, float] = Field(default_factory=dict)
    reconciliation: pd.DataFrame = Field(default_factory=pd.DataFrame)
    reconciliation_by_kind: pd.DataFrame = Field(default_factory=pd.DataFrame)
    sales: pd.DataFrame = Field(default_factory=pd.DataFrame)
    returns: pd.DataFrame = Field(default_factory=pd.DataFrame)
    products: pd.DataFrame = Field(default_factory=pd.DataFrame)
    product_profit: pd.DataFrame = Field(default_factory=pd.DataFrame)
    expenses: pd.DataFrame = Field(default_factory=pd.DataFrame)
    ads: pd.DataFrame = Field(default_factory=pd.DataFrame)
    taxes: pd.DataFrame = Field(default_factory=pd.DataFrame)
    management_profit: pd.DataFrame = Field(default_factory=pd.DataFrame)
    legend: pd.DataFrame = Field(default_factory=pd.DataFrame)
    report_settings: pd.DataFrame = Field(default_factory=pd.DataFrame)
    operations: pd.DataFrame = Field(default_factory=pd.DataFrame)
    warnings: list[str] = Field(default_factory=list)

    def table_by_name(self, name: str) -> pd.DataFrame:
        return {
            "Обозначения": self.legend,
            "Общая сводка": self.reconciliation,
            "Продажи": self.sales,
            "Возвраты": self.returns,
            "Товары": self.products,
            "Прибыль по товарам": self.product_profit,
            "Глобальные расходы": self.expenses,
            "Внешние расходы": self.expenses,
            "Реклама WB": self.ads,
            "Налоги": self.taxes,
            "Управленческая прибыль": self.management_profit,
            "Настройки отчёта": self.report_settings,
            "Предупреждения": pd.DataFrame({"Предупреждение": self.warnings}),
        }.get(name, pd.DataFrame())

    def total(self, name: str) -> float:
        return float(self.summary.get(name, 0.0) or 0.0)


def empty_result(message: str = "") -> WBFinanceResult:
    result = WBFinanceResult()
    if message:
        result.warnings.append(message)
    return result
