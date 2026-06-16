from __future__ import annotations

import hashlib
import json
import logging
from datetime import date, datetime
from pathlib import Path
from typing import Callable

import pandas as pd

from wb_finance_analyst.config.defaults import CACHE_DIR
from wb_finance_analyst.config.settings import AppSettings
from wb_finance_analyst.domain.models import ColumnMap, LoadedReport, ReportPeriod, WBFinanceResult
from wb_finance_analyst.services.business_expenses import BusinessExpensesCalculator
from wb_finance_analyst.services.load_progress import CancelCallback, LOAD_STAGES, LoadProgress, LoadingCancelled, ProgressCallback
from wb_finance_analyst.services.period_selection import report_bounds
from wb_finance_analyst.services.tax_calculator import TaxCalculator
from wb_finance_analyst.services.token_store import TokenStore
from wb_finance_analyst.services.report_views import ReportViewBuilder
from wb_finance_analyst.services.wb_finance_api import (
    WBFinanceAPI,
    classify_report_kind,
    finance_api_rows_to_dataframe,
    report_id_from_row,
    report_kind_label,
    report_period_for_dates,
    select_reports,
    summary_rows_from_reports,
)
from wb_finance_analyst.services.wb_finance_calculator import WBFinanceCalculator
from wb_finance_analyst.services.wb_promotion_api import WBPromotionAPI


API_COLUMN_MAP = ColumnMap(
    date_sale="date",
    doc_type="document_type",
    payment_reason="payment_reason",
    quantity="quantity",
    supplier_article="vendor_code",
    product_name="product",
    nm_id="nm_id",
    barcode="barcode",
    retail_price="retail_price",
    wb_sold="wb_sale_amount",
    seller_transfer="seller_payment",
    logistics="logistics",
    storage="storage",
    deductions="retentions",
    penalties="penalties",
    acceptance="acceptance",
    loyalty="loyalty_cost",
    loyalty_points="loyalty_points",
    transfer_delay_change="transfer_delay_change",
    wb_reward_correction="wb_reward_correction",
    loyalty_compensation="loyalty_compensation",
)

CACHE_VERSION = "finance-api-v3"
CHECKPOINT_DIR = CACHE_DIR / "checkpoints"
PROMOTION_WARNING = "Не удалось загрузить рекламу WB. Финансовый отчёт сформирован без рекламных расходов."
LOGGER = logging.getLogger(__name__)


class AutoReportService:
    def __init__(
        self,
        token_store: TokenStore | None = None,
        status_callback: Callable[[str], None] | None = None,
        progress_callback: ProgressCallback | None = None,
        cancel_callback: CancelCallback | None = None,
    ) -> None:
        self.token_store = token_store or TokenStore()
        self.status_callback = status_callback
        self.progress_callback = progress_callback
        self.cancel_callback = cancel_callback
        self.finance_calculator = WBFinanceCalculator()
        self.business_expenses = BusinessExpensesCalculator()
        self.tax_calculator = TaxCalculator()
        self.view_builder = ReportViewBuilder()

    def fetch_finance_rows(
        self,
        date_from: date,
        date_to: date,
        report_kind: str = "main",
        use_cache: bool = True,
        resume_checkpoint: bool = False,
        selected_reports: list[dict] | None = None,
        available_reports: list[dict] | None = None,
        cache_key: str = "",
    ) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, float], list[str]]:
        warnings: list[str] = []
        cache_kind = self._cache_kind(report_kind, cache_key)
        cache_path = self._cache_path("finance_api", date_from, date_to, cache_kind)
        self._stage("Проверка наличия кэша", "Проверка локального кэша WB Finance API...")
        if use_cache and cache_path.exists():
            LOGGER.info("WB Finance cache hit source=finance_api date_from=%s date_to=%s report_kind=%s", date_from, date_to, cache_kind)
            warnings.append("Данные взяты из кэша")
            payload = json.loads(cache_path.read_text(encoding="utf-8"))
            if isinstance(payload, list):
                details = pd.DataFrame(payload)
                summary_df = pd.DataFrame()
                summary = {}
            else:
                details = pd.DataFrame(payload.get("details", []))
                summary_df = pd.DataFrame(payload.get("summary_rows", []))
                all_summary_df = pd.DataFrame(payload.get("all_summary_rows", []))
                if not all_summary_df.empty:
                    summary_df.attrs["all_summary_rows"] = all_summary_df
                if payload.get("detail_date_from"):
                    summary_df.attrs["detail_date_from"] = payload.get("detail_date_from")
                if payload.get("detail_date_to"):
                    summary_df.attrs["detail_date_to"] = payload.get("detail_date_to")
                summary = {key: float(value) for key, value in payload.get("summary", {}).items()}
            self._progress(rows_loaded=len(details))
            return details, summary_df, summary, warnings
        token = self.token_store.finance_token()
        if not token:
            return pd.DataFrame(), pd.DataFrame(), {}, ["Finance API token не задан"]
        LOGGER.info("WB Finance load start date_from=%s date_to=%s report_kind=%s", date_from, date_to, report_kind)
        api = WBFinanceAPI(token, status_callback=self._notify, cancel_callback=self._is_cancelled)
        if selected_reports is None:
            self._stage("Получение списка финансовых отчётов", "WB Finance API: получение списка финансовых отчётов...")
            reports = api.get_sales_reports_list(date_from, date_to, period=report_period_for_dates(date_from, date_to))
        else:
            self._stage("Получение списка финансовых отчётов", "Используются выбранные WB-периоды...")
            reports = list(available_reports or selected_reports)
        self._stage("Выбор reportId по выбранному типу отчёта", "Выбор reportId по выбранному типу отчёта...")
        if selected_reports is None:
            all_reports = select_reports(reports, "both", date_from=date_from, date_to=date_to)
            selected = select_reports(reports, report_kind, date_from=date_from, date_to=date_to)
        else:
            selected = list(selected_reports)
            selected_periods = {(report.get("dateFrom"), report.get("dateTo")) for report in selected}
            same_period_reports = [report for report in reports if (report.get("dateFrom"), report.get("dateTo")) in selected_periods]
            all_reports = select_reports(same_period_reports, "both")
        all_summary_df, _ = summary_rows_from_reports(all_reports)
        warnings.extend(self._report_kind_warnings(reports, report_kind))
        if not selected:
            warnings.append("В списке WB не найден отчёт выбранного типа за указанный период")
        self._stage("Получение сводки WB", "Формирование сводки WB из sales-reports/list...")
        summary_df, summary = summary_rows_from_reports(selected)
        if not all_summary_df.empty:
            summary_df.attrs["all_summary_rows"] = all_summary_df
        detail_bounds = report_bounds(selected)
        if detail_bounds:
            summary_df.attrs["detail_date_from"] = detail_bounds[0].isoformat()
            summary_df.attrs["detail_date_to"] = detail_bounds[1].isoformat()
            if detail_bounds != (date_from, date_to):
                warnings.append(
                    "Фактический период детализации WB отличается от выбранного: "
                    f"{detail_bounds[0].strftime('%d.%m.%Y')} - {detail_bounds[1].strftime('%d.%m.%Y')}."
                )
        rows: list[dict] = []
        self._stage("Получение детализации Finance API", "WB Finance API: получение детализации отчёта...")
        CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
        for report in selected:
            self._raise_if_cancelled()
            kind = classify_report_kind(report)
            report_id = report_id_from_row(report)
            if report_id is None:
                warnings.append(f"У отчёта WB не найден reportId: {report}")
                continue
            details = api.get_sales_report_details_by_report_id(
                report_id,
                checkpoint_path=self._checkpoint_path(report_id),
                resume_checkpoint=resume_checkpoint,
                rows_callback=lambda count: self._progress(rows_loaded=len(rows) + count),
            )
            for row in details:
                row["reportKind"] = kind
                row["reportId"] = report_id
                row.setdefault("dateFrom", report.get("dateFrom"))
                row.setdefault("dateTo", report.get("dateTo"))
                row.setdefault("createDate", report.get("createDate"))
            rows.extend(details)
            self._progress(rows_loaded=len(rows))
        df = finance_api_rows_to_dataframe(rows)
        if not df.empty:
            df["report_kind"] = df["report_kind"].replace("", report_kind if report_kind != "both" else "main")
            df["Тип отчета"] = df["report_kind"].map(report_kind_label)
        self._write_finance_cache(cache_path, df, summary_df, summary, selected)
        LOGGER.info("WB Finance rows loaded rows=%s date_from=%s date_to=%s report_kind=%s", len(df), date_from, date_to, report_kind)
        return df, summary_df, summary, warnings

    def fetch_ads(self, date_from: date, date_to: date, settings: AppSettings) -> tuple[pd.DataFrame, list[str]]:
        mode = settings.api.ad_source
        if mode == "none":
            return pd.DataFrame(columns=["Дата", "Кампания", "ID кампании", "nmId", "Товар", "Расход", "Источник оплаты", "Тип рекламы"]), []
        if mode == "manual":
            return pd.DataFrame([{"Дата": "", "Кампания": "Ручной ввод", "ID кампании": "", "nmId": "", "Товар": "", "Расход": settings.api.manual_ad_expense, "Источник оплаты": "Ручной ввод", "Тип рекламы": ""}]), []
        if mode == "included":
            return pd.DataFrame(), ["Реклама считается уже учтенной в удержаниях WB"]
        token = self.token_store.promotion_token()
        if not token:
            return pd.DataFrame(), ["Promotion API token не задан"]
        cache_path = self._cache_path("promotion_api", date_from, date_to, "ads")
        if cache_path.exists():
            return pd.read_json(cache_path, orient="records"), ["Данные рекламы взяты из кэша"]
        ads = WBPromotionAPI(token).get_ad_expenses(date_from, date_to)
        self._write_table_cache(cache_path, ads)
        return ads, []

    def build_report(
        self,
        date_from: date,
        date_to: date,
        report_kind: str,
        settings: AppSettings,
        use_cache: bool = True,
        load_mode: str = "full",
        resume_checkpoint: bool = False,
        selected_reports: list[dict] | None = None,
        available_reports: list[dict] | None = None,
        selection_cache_key: str = "",
    ) -> WBFinanceResult:
        LOGGER.info("Auto report load start date_from=%s date_to=%s report_kind=%s load_mode=%s", date_from, date_to, report_kind, load_mode)
        if load_mode == "summary":
            return self._build_summary_only_report(
                date_from,
                date_to,
                report_kind,
                settings,
                use_cache=use_cache,
                selected_reports=selected_reports,
                available_reports=available_reports,
                cache_key=selection_cache_key,
            )
        if resume_checkpoint:
            if selected_reports is None and not selection_cache_key:
                finance_df, summary_df, official_summary, warnings = self.fetch_finance_rows(date_from, date_to, report_kind, use_cache=use_cache, resume_checkpoint=True)
            else:
                finance_df, summary_df, official_summary, warnings = self.fetch_finance_rows(
                    date_from,
                    date_to,
                    report_kind,
                    use_cache=use_cache,
                    resume_checkpoint=True,
                    selected_reports=selected_reports,
                    available_reports=available_reports,
                    cache_key=selection_cache_key,
                )
        else:
            if selected_reports is None and not selection_cache_key:
                finance_df, summary_df, official_summary, warnings = self.fetch_finance_rows(date_from, date_to, report_kind, use_cache=use_cache)
            else:
                finance_df, summary_df, official_summary, warnings = self.fetch_finance_rows(
                    date_from,
                    date_to,
                    report_kind,
                    use_cache=use_cache,
                    selected_reports=selected_reports,
                    available_reports=available_reports,
                    cache_key=selection_cache_key,
                )
        if finance_df.empty and not official_summary:
            return WBFinanceResult(period=ReportPeriod(start=date_from, end=date_to), warnings=warnings or ["Не удалось получить финансовый отчет"])
        result = self._build_from_finance_data(
            finance_df=finance_df,
            summary_df=summary_df,
            official_summary=official_summary,
            warnings=warnings,
            date_from=date_from,
            date_to=date_to,
            report_kind=report_kind,
            settings=settings,
            use_cache=use_cache,
            ads_override=None,
            ad_warnings_override=None,
        )
        self._stage("Готово", "Загрузка завершена")
        LOGGER.info("Auto report load finished rows=%s warnings=%s", len(result.operations), len(result.warnings))
        return result

    def recalculate_report(self, previous: WBFinanceResult, date_from: date, date_to: date, report_kind: str, settings: AppSettings) -> WBFinanceResult:
        if previous.operations.empty:
            return WBFinanceResult(period=ReportPeriod(start=date_from, end=date_to), warnings=["Нет загруженных данных WB для пересчета"])
        summary_df = previous.reconciliation_by_kind.copy() if not previous.reconciliation_by_kind.empty else pd.DataFrame()
        official_summary = self._summary_from_rows(summary_df)
        ads, ad_warnings = self._ads_from_existing(previous.ads, settings)
        warnings = ["Расчет обновлен без повторной загрузки из WB"]
        return self._build_from_finance_data(
            finance_df=previous.operations.copy(),
            summary_df=summary_df,
            official_summary=official_summary,
            warnings=warnings,
            date_from=date_from,
            date_to=date_to,
            report_kind=report_kind,
            settings=settings,
            use_cache=True,
            ads_override=ads,
            ad_warnings_override=ad_warnings,
        )

    def _build_from_finance_data(
        self,
        finance_df: pd.DataFrame,
        summary_df: pd.DataFrame,
        official_summary: dict[str, float],
        warnings: list[str],
        date_from: date,
        date_to: date,
        report_kind: str,
        settings: AppSettings,
        use_cache: bool,
        ads_override: pd.DataFrame | None,
        ad_warnings_override: list[str] | None,
    ) -> WBFinanceResult:
        self._stage("Расчёт отчёта", "Расчёт финансового отчёта...")
        loaded = LoadedReport(path=Path("WB Finance API"), dataframe=finance_df, column_map=API_COLUMN_MAP, period=ReportPeriod(start=date_from, end=date_to), warnings=warnings)
        result = self.finance_calculator.calculate_loaded([loaded], settings)
        result.source_files = ["WB API"]
        if not summary_df.empty and official_summary:
            detail_logistics = result.summary.get("Логистика", 0.0)
            if abs(detail_logistics - official_summary.get("Логистика", 0.0)) > 1:
                result.warnings.append("Логистика по детализации отличается от сводки WB. Для сверки используется сводка WB.")
            result.summary.update(official_summary)
            for kind, label in [("main", "Основной"), ("buyouts", "По выкупам")]:
                rows = summary_df[(summary_df.get("report_kind") == kind) & (summary_df.get("Показатель") == "Итого к оплате WB")]
                if not rows.empty:
                    result.summary[f"{label} — Итого к оплате WB"] = float(rows.iloc[0]["Сумма"])
            result.reconciliation = summary_df.copy()
            result.reconciliation_by_kind = summary_df.copy()
            calculated = (
                official_summary.get("К перечислению за товар", 0.0)
                - official_summary.get("Логистика", 0.0)
                - official_summary.get("Хранение", 0.0)
                - official_summary.get("Удержания/выплаты", 0.0)
                - official_summary.get("Штрафы", 0.0)
                - official_summary.get("Операции при приемке", 0.0)
                - official_summary.get("Лояльность", 0.0)
            )
            if abs(calculated - official_summary.get("Итого к оплате WB", 0.0)) > 1:
                result.warnings.append(f"Расчет не сошелся со сводкой WB. Разница: {round(calculated - official_summary.get('Итого к оплате WB', 0.0), 2)}")
        if ads_override is None:
            self._stage("Получение рекламы Promotion API", "Получение рекламы WB Promotion API...")
            try:
                if self._finance_loaded_from_cache(warnings) and settings.api.ad_source == "api" and not self._cache_path("promotion_api", date_from, date_to, "ads").exists():
                    ads, ad_warnings = pd.DataFrame(), ["Данные WB взяты из кэша; рекламы WB в кэше нет, Promotion API не запрашивался."]
                else:
                    ads, ad_warnings = self.fetch_ads(date_from, date_to, settings)
            except Exception:
                LOGGER.exception("WB Promotion API failed")
                ads, ad_warnings = pd.DataFrame(), [PROMOTION_WARNING]
        else:
            ads, ad_warnings = ads_override, ad_warnings_override or []
        result.ads = ads
        self._add_kind_columns(result.ads, report_kind)
        result.warnings.extend(ad_warnings)
        ads_total_raw = float(ads["Расход"].sum()) if not ads.empty and "Расход" in ads.columns and settings.api.ad_source in {"api", "manual"} else 0.0
        ads_total, ad_allocation_note = self._allocated_ads_total(ads_total_raw, summary_df, report_kind)
        if ad_allocation_note:
            result.warnings.append(ad_allocation_note)
        expenses, expenses_total = self.business_expenses.calculate(settings.external_expenses, result.total("К перечислению за товар"))
        if settings.external_expenses == []:
            result.warnings.append("Внешние расходы не заданы.")
        result.expenses = expenses
        self._add_kind_columns(result.expenses, report_kind)
        tax_base_values = {
            "wb_payable": result.total("Итого к оплате WB"),
            "goods": result.total("К перечислению за товар"),
            "gross_profit": result.total("Итого к оплате WB") - result.total("Себестоимость") - result.summary.get("Упаковка", 0.0),
        }
        taxes, tax_total = self.tax_calculator.calculate(settings.api.tax_settings, tax_base_values)
        result.taxes = taxes
        self._add_kind_columns(result.taxes, report_kind)
        if settings.api.tax_settings.mode in {"usn", "usn_nds"} and settings.api.tax_settings.usn_rate == 0:
            result.warnings.append("УСН выбран, но ставка не задана.")
        if settings.api.tax_settings.mode in {"nds", "usn_nds"} and settings.api.tax_settings.nds_rate == 0:
            result.warnings.append("НДС выбран, но ставка не задана.")
        cost = result.total("Себестоимость")
        packaging = result.summary.get("Упаковка", 0.0)
        gross = result.total("Итого к оплате WB") - cost - packaging
        net = gross - ads_total - expenses_total - tax_total
        result.summary["Реклама WB"] = ads_total
        result.summary["Внешние расходы"] = expenses_total
        result.summary["УСН"] = float(taxes.loc[taxes["Тип налога"].eq("УСН"), "Сумма"].sum()) if not taxes.empty else 0.0
        result.summary["НДС"] = float(taxes.loc[taxes["Тип налога"].eq("НДС"), "Сумма"].sum()) if not taxes.empty else 0.0
        result.summary["Ручная сумма"] = tax_total if settings.api.tax_settings.mode == "manual" else 0.0
        result.summary["Валовая прибыль"] = gross
        result.summary["Чистая прибыль"] = net
        result.summary["Продано товаров"] = self._sold_goods_count(result.operations)
        base = result.total("К перечислению за товар")
        result.summary["Маржинальность %"] = net / base if base else 0.0
        result.management_profit = self._management_profit(result, ads_total, expenses_total, tax_total)
        self._add_kind_columns(result.management_profit, report_kind)
        result.report_settings = self._report_settings(date_from, date_to, report_kind, settings, expenses_total, use_cache, "Полный отчёт", ad_allocation_note, summary_df=summary_df)
        if summary_df.empty:
            result.reconciliation = pd.DataFrame([{"Показатель": key, "Сумма": value} for key, value in result.summary.items()])
        self._stage("Формирование таблиц", "Формирование таблиц отчёта...")
        self.view_builder.build(result, API_COLUMN_MAP, self.finance_calculator.costs.load(), report_kind)
        return result

    def _build_summary_only_report(
        self,
        date_from: date,
        date_to: date,
        report_kind: str,
        settings: AppSettings,
        use_cache: bool,
        selected_reports: list[dict] | None = None,
        available_reports: list[dict] | None = None,
        cache_key: str = "",
    ) -> WBFinanceResult:
        warnings: list[str] = []
        cache_path = self._cache_path("finance_api", date_from, date_to, self._cache_kind(f"{report_kind}:summary", cache_key))
        self._stage("Проверка наличия кэша", "Проверка локального кэша быстрой сводки...")
        if use_cache and cache_path.exists():
            LOGGER.info("WB Finance cache hit source=finance_api_summary date_from=%s date_to=%s report_kind=%s", date_from, date_to, report_kind)
            payload = json.loads(cache_path.read_text(encoding="utf-8"))
            summary_df = pd.DataFrame(payload.get("summary_rows", []))
            if payload.get("detail_date_from"):
                summary_df.attrs["detail_date_from"] = payload.get("detail_date_from")
            if payload.get("detail_date_to"):
                summary_df.attrs["detail_date_to"] = payload.get("detail_date_to")
            official_summary = {key: float(value) for key, value in payload.get("summary", {}).items()}
            warnings.append("Данные взяты из кэша")
        else:
            token = self.token_store.finance_token()
            if not token:
                return WBFinanceResult(period=ReportPeriod(start=date_from, end=date_to), warnings=["Finance API token не задан"])
            api = WBFinanceAPI(token, status_callback=self._notify, cancel_callback=self._is_cancelled)
            if selected_reports is None:
                self._stage("Получение списка финансовых отчётов", "WB Finance API: получение списка финансовых отчётов...")
                reports = api.get_sales_reports_list(date_from, date_to, period=report_period_for_dates(date_from, date_to))
            else:
                self._stage("Получение списка финансовых отчётов", "Используются выбранные WB-периоды...")
                reports = list(available_reports or selected_reports)
            self._stage("Выбор reportId по выбранному типу отчёта", "Выбор reportId по выбранному типу отчёта...")
            selected = select_reports(reports, report_kind, date_from=date_from, date_to=date_to) if selected_reports is None else list(selected_reports)
            warnings.extend(self._report_kind_warnings(reports, report_kind))
            self._stage("Получение сводки WB", "Формирование быстрой сводки WB из sales-reports/list...")
            summary_df, official_summary = summary_rows_from_reports(selected)
            detail_bounds = report_bounds(selected)
            if detail_bounds:
                summary_df.attrs["detail_date_from"] = detail_bounds[0].isoformat()
                summary_df.attrs["detail_date_to"] = detail_bounds[1].isoformat()
            self._write_finance_cache(cache_path, pd.DataFrame(), summary_df, official_summary, selected)
        result = WBFinanceResult(period=ReportPeriod(start=date_from, end=date_to), source_files=["WB API"], warnings=warnings)
        result.summary.update(official_summary)
        for kind, label in [("main", "Основной"), ("buyouts", "По выкупам")]:
            rows = summary_df[(summary_df.get("report_kind") == kind) & (summary_df.get("Показатель") == "Итого к оплате WB")] if not summary_df.empty else pd.DataFrame()
            if not rows.empty:
                result.summary[f"{label} — Итого к оплате WB"] = float(rows.iloc[0]["Сумма"])
        result.reconciliation = summary_df.copy()
        result.reconciliation_by_kind = summary_df.copy()
        self._stage("Расчёт отчёта", "Расчёт быстрой сводки...")
        expenses, expenses_total = self.business_expenses.calculate(settings.external_expenses, result.total("К перечислению за товар"))
        result.expenses = expenses
        self._add_kind_columns(result.expenses, report_kind)
        tax_base_values = {
            "wb_payable": result.total("Итого к оплате WB"),
            "goods": result.total("К перечислению за товар"),
            "gross_profit": result.total("Итого к оплате WB"),
        }
        taxes, tax_total = self.tax_calculator.calculate(settings.api.tax_settings, tax_base_values)
        result.taxes = taxes
        self._add_kind_columns(result.taxes, report_kind)
        result.summary["Реклама WB"] = 0.0
        result.summary["Внешние расходы"] = expenses_total
        result.summary["УСН"] = float(taxes.loc[taxes["Тип налога"].eq("УСН"), "Сумма"].sum()) if not taxes.empty else 0.0
        result.summary["НДС"] = float(taxes.loc[taxes["Тип налога"].eq("НДС"), "Сумма"].sum()) if not taxes.empty else 0.0
        result.summary["Ручная сумма"] = tax_total if settings.api.tax_settings.mode == "manual" else 0.0
        gross = result.total("Итого к оплате WB")
        net = gross - expenses_total - tax_total
        result.summary["Валовая прибыль"] = gross
        result.summary["Чистая прибыль"] = net
        result.summary["Продано товаров"] = 0.0
        base = result.total("К перечислению за товар")
        result.summary["Маржинальность %"] = net / base if base else 0.0
        result.management_profit = self._management_profit(result, 0.0, expenses_total, tax_total)
        self._add_kind_columns(result.management_profit, report_kind)
        result.report_settings = self._report_settings(date_from, date_to, report_kind, settings, expenses_total, use_cache, "Быстрая сводка", summary_df=summary_df)
        self._stage("Формирование таблиц", "Формирование таблиц быстрой сводки...")
        self.view_builder.build(result, API_COLUMN_MAP, self.finance_calculator.costs.load(), report_kind)
        self._stage("Готово", "Быстрая сводка готова")
        LOGGER.info("Auto report summary load finished warnings=%s", len(result.warnings))
        return result

    def _summary_from_rows(self, summary_df: pd.DataFrame) -> dict[str, float]:
        if summary_df.empty or "Показатель" not in summary_df.columns or "Сумма" not in summary_df.columns:
            return {}
        rows = summary_df
        if "report_kind" in rows.columns and (rows["report_kind"] == "total").any():
            rows = rows[rows["report_kind"] == "total"]
        totals: dict[str, float] = {}
        for _, row in rows.iterrows():
            key = str(row["Показатель"])
            value = float(pd.to_numeric(pd.Series([row["Сумма"]]), errors="coerce").fillna(0).iloc[0])
            totals[key] = totals.get(key, 0.0) + value
        return {key: round(value, 2) for key, value in totals.items()}

    def _ads_from_existing(self, ads: pd.DataFrame, settings: AppSettings) -> tuple[pd.DataFrame, list[str]]:
        mode = settings.api.ad_source
        if mode == "none":
            return pd.DataFrame(columns=["Дата", "Кампания", "ID кампании", "nmId", "Товар", "Расход", "Источник оплаты", "Тип рекламы"]), []
        if mode == "manual":
            return pd.DataFrame([{"Дата": "", "Кампания": "Ручной ввод", "ID кампании": "", "nmId": "", "Товар": "", "Расход": settings.api.manual_ad_expense, "Источник оплаты": "Ручной ввод", "Тип рекламы": ""}]), []
        if mode == "included":
            return pd.DataFrame(), ["Реклама считается уже учтенной в удержаниях WB"]
        return self._without_total_row(ads), ["Реклама WB использована из уже загруженного отчета"]

    def _without_total_row(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return df.copy()
        mask = pd.Series(False, index=df.index)
        for column in df.columns:
            mask = mask | df[column].fillna("").astype(str).str.strip().eq("Итого")
        return df.loc[~mask].copy()

    def _sold_goods_count(self, operations: pd.DataFrame) -> float:
        if operations.empty or "document_type" not in operations.columns or "quantity" not in operations.columns:
            return 0.0
        doc = operations["document_type"].fillna("").astype(str).str.casefold()
        qty = pd.to_numeric(operations["quantity"], errors="coerce").fillna(0.0)
        return float(qty.where(doc.str.contains("продажа", na=False), 0.0).sum())

    def _allocated_ads_total(self, ads_total: float, summary_df: pd.DataFrame, report_kind: str) -> tuple[float, str]:
        if report_kind == "both" or ads_total == 0:
            return ads_total, ""
        if report_kind not in {"main", "buyouts"}:
            return ads_total, ""

        rows = summary_df.attrs.get("all_summary_rows")
        all_summary_df = rows if isinstance(rows, pd.DataFrame) and not rows.empty else summary_df
        payable_by_kind = self._wb_payable_by_kind(all_summary_df)
        selected_payable = max(payable_by_kind.get(report_kind, 0.0), 0.0)
        total_payable = sum(max(value, 0.0) for value in payable_by_kind.values())
        if selected_payable <= 0 or total_payable <= 0:
            return ads_total, "Реклама WB не распределена по типам отчёта: нет полной сводки по «Итого к оплате WB»."

        ratio = selected_payable / total_payable
        allocated = round(ads_total * ratio, 2)
        label = report_kind_label(report_kind)
        note = (
            f"Реклама WB распределена для типа «{label}» пропорционально «Итого к оплате WB»: "
            f"{allocated:.2f} из {ads_total:.2f}."
        )
        return allocated, note

    def _wb_payable_by_kind(self, summary_df: pd.DataFrame) -> dict[str, float]:
        if summary_df.empty or "report_kind" not in summary_df.columns or "Показатель" not in summary_df.columns or "Сумма" not in summary_df.columns:
            return {}
        rows = summary_df[
            summary_df["report_kind"].isin(["main", "buyouts"])
            & summary_df["Показатель"].astype(str).eq("Итого к оплате WB")
        ]
        totals: dict[str, float] = {}
        for _, row in rows.iterrows():
            kind = str(row["report_kind"])
            value = float(pd.to_numeric(pd.Series([row["Сумма"]]), errors="coerce").fillna(0.0).iloc[0])
            totals[kind] = totals.get(kind, 0.0) + value
        return totals

    def _management_profit(self, result: WBFinanceResult, ads_total: float, expenses_total: float, tax_total: float) -> pd.DataFrame:
        rows = [
            ("Итого к оплате WB", result.total("Итого к оплате WB")),
            ("Себестоимость", result.total("Себестоимость")),
            ("Упаковка", result.summary.get("Упаковка", 0.0)),
            ("WB реклама", ads_total),
            ("Внешние расходы", expenses_total),
            ("Налоги", tax_total),
            ("Чистая прибыль", result.total("Чистая прибыль")),
            ("Маржинальность %", result.total("Маржинальность %")),
        ]
        return pd.DataFrame([{"Показатель": name, "Сумма": value} for name, value in rows])

    def _report_settings(
        self,
        date_from: date,
        date_to: date,
        report_kind: str,
        settings: AppSettings,
        expenses_total: float,
        use_cache: bool,
        load_mode: str,
        ad_allocation_note: str = "",
        summary_df: pd.DataFrame | None = None,
    ) -> pd.DataFrame:
        detail_from = summary_df.attrs.get("detail_date_from") if summary_df is not None else ""
        detail_to = summary_df.attrs.get("detail_date_to") if summary_df is not None else ""
        rows = [
                {"Настройка": "Период", "Значение": f"{date_from.isoformat()} - {date_to.isoformat()}"},
                {"Настройка": "Фактический период детализации WB", "Значение": f"{detail_from} - {detail_to}" if detail_from and detail_to else f"{date_from.isoformat()} - {date_to.isoformat()}"},
                {"Настройка": "Выбранный тип отчета", "Значение": report_kind},
                {"Настройка": "Режим загрузки", "Значение": load_mode},
                {"Настройка": "Источник данных", "Значение": "WB API"},
                {"Настройка": "Источник рекламы", "Значение": settings.api.ad_source},
                {"Настройка": "Режим налога", "Значение": settings.api.tax_settings.mode},
                {"Настройка": "Ставка УСН", "Значение": settings.api.tax_settings.usn_rate},
                {"Настройка": "База УСН", "Значение": settings.api.tax_settings.usn_base},
                {"Настройка": "Ставка НДС", "Значение": settings.api.tax_settings.nds_rate},
                {"Настройка": "База НДС", "Значение": settings.api.tax_settings.nds_base},
                {"Настройка": "Внешние расходы", "Значение": expenses_total},
                {"Настройка": "Использован ли кэш", "Значение": use_cache},
                {"Настройка": "Сформировано", "Значение": datetime.now().isoformat(timespec="seconds")},
        ]
        if ad_allocation_note:
            rows.append({"Настройка": "Учет рекламы WB", "Значение": ad_allocation_note})
        return pd.DataFrame(rows)

    def _add_kind_columns(self, df: pd.DataFrame, report_kind: str) -> None:
        if df.empty:
            return
        if "report_kind" not in df.columns:
            df.insert(0, "report_kind", "total" if report_kind == "both" else report_kind)
        if "Тип отчета" not in df.columns:
            label = "Итого общий" if report_kind == "both" else report_kind_label(report_kind)
            df.insert(1, "Тип отчета", label)

    def _cache_path(self, source: str, date_from: date, date_to: date, kind: str) -> Path:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        scope = self._cache_scope(source)
        key = hashlib.sha256(f"{CACHE_VERSION}:{scope}:{source}:{date_from}:{date_to}:{kind}".encode("utf-8")).hexdigest()[:16]
        return CACHE_DIR / f"{key}.json"

    def _cache_scope(self, source: str) -> str:
        if source == "promotion_api":
            token = self.token_store.promotion_token()
        else:
            token = self.token_store.finance_token()
        if not token:
            return "no-token"
        return hashlib.sha256(token.encode("utf-8")).hexdigest()[:12]

    def _cache_kind(self, report_kind: str, cache_key: str = "") -> str:
        return f"{report_kind}:reports:{cache_key}" if cache_key else report_kind

    def has_finance_cache(self, date_from: date, date_to: date, report_kind: str, cache_key: str = "") -> bool:
        return self._cache_path("finance_api", date_from, date_to, self._cache_kind(report_kind, cache_key)).exists()

    def has_summary_cache(self, date_from: date, date_to: date, report_kind: str, cache_key: str = "") -> bool:
        return self._cache_path("finance_api", date_from, date_to, self._cache_kind(f"{report_kind}:summary", cache_key)).exists()

    def has_checkpoint(self) -> bool:
        return CHECKPOINT_DIR.exists() and any(CHECKPOINT_DIR.glob("finance_*.json"))

    def clear_checkpoints(self) -> None:
        if not CHECKPOINT_DIR.exists():
            return
        for path in CHECKPOINT_DIR.glob("finance_*.json"):
            path.unlink(missing_ok=True)

    def _checkpoint_path(self, report_id: str | int) -> Path:
        safe_report_id = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in str(report_id))
        return CHECKPOINT_DIR / f"finance_{safe_report_id}.json"

    def _write_table_cache(self, path: Path, df: pd.DataFrame) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(df.to_json(orient="records", force_ascii=False), encoding="utf-8")

    def _write_finance_cache(self, path: Path, df: pd.DataFrame, summary_df: pd.DataFrame, summary: dict[str, float], reports: list[dict] | None = None) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "source": "finance_api",
            "seller_account": self._seller_account_from_reports(reports or []),
            "details": json.loads(df.to_json(orient="records", force_ascii=False)),
            "summary_rows": json.loads(summary_df.to_json(orient="records", force_ascii=False)),
            "all_summary_rows": json.loads(
                summary_df.attrs.get("all_summary_rows", pd.DataFrame()).to_json(orient="records", force_ascii=False)
            ),
            "summary": summary,
            "detail_date_from": summary_df.attrs.get("detail_date_from", ""),
            "detail_date_to": summary_df.attrs.get("detail_date_to", ""),
        }
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    def _notify(self, message: str) -> None:
        if self.status_callback:
            self.status_callback(message)
        self._progress(status=message, wait_seconds=self._wait_seconds_from_message(message))

    def _stage(self, stage: str, status: str = "") -> None:
        self._raise_if_cancelled()
        progress = self._stage_progress(stage)
        LOGGER.info("WB load stage=%s status=%s", stage, status)
        if self.status_callback and status:
            self.status_callback(status)
        self._progress(stage=stage, status=status, progress=progress)

    def _progress(
        self,
        stage: str | None = None,
        status: str = "",
        rows_loaded: int | None = None,
        progress: int | None = None,
        wait_seconds: int | None = None,
    ) -> None:
        if self.progress_callback:
            self.progress_callback(
                LoadProgress(
                    stage=stage or "",
                    status=status,
                    rows_loaded=rows_loaded,
                    progress=progress,
                    wait_seconds=wait_seconds,
                )
            )

    def _stage_progress(self, stage: str) -> int:
        if stage not in LOAD_STAGES:
            return 0
        if len(LOAD_STAGES) == 1:
            return 100
        return int(LOAD_STAGES.index(stage) / (len(LOAD_STAGES) - 1) * 100)

    def _is_cancelled(self) -> bool:
        return bool(self.cancel_callback and self.cancel_callback())

    def _raise_if_cancelled(self) -> None:
        if self._is_cancelled():
            raise LoadingCancelled("Загрузка отменена")

    def _report_kind_warnings(self, reports: list[dict], report_kind: str) -> list[str]:
        warnings: list[str] = []
        if report_kind == "main" and any(classify_report_kind(report) == "buyouts" for report in reports):
            warnings.append('Выбран тип отчета "Основной", но в ответе API были данные "По выкупам". Они исключены.')
        if report_kind == "buyouts" and any(classify_report_kind(report) == "main" for report in reports):
            warnings.append('Выбран тип отчета "По выкупам", но в ответе API были данные "Основной". Они исключены.')
        return warnings

    def _seller_account_from_reports(self, reports: list[dict]) -> str:
        for report in reports:
            for key in ("sellerFinanceName", "sellerName", "supplierName", "legalEntity", "inn"):
                value = report.get(key)
                if value not in (None, ""):
                    return str(value)
        return ""

    def _finance_loaded_from_cache(self, warnings: list[str]) -> bool:
        return any("кэша" in warning.casefold() for warning in warnings)

    def _wait_seconds_from_message(self, message: str) -> int | None:
        marker = "ожидание "
        if marker not in message:
            return None
        tail = message.split(marker, 1)[1]
        number = tail.split(" ", 1)[0]
        try:
            return int(number)
        except ValueError:
            return None
