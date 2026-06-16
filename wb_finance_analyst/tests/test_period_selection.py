from datetime import date

import pandas as pd
import pytest
from PySide6.QtWidgets import QApplication

from wb_finance_analyst.config.settings import AppSettings
from wb_finance_analyst.services.auto_report_service import AutoReportService
from wb_finance_analyst.services.period_selection import PeriodSelection, report_bounds
from wb_finance_analyst.ui.period_selection_dialog import PeriodSelectionDialog


class FakeTokenStore:
    def finance_token(self) -> str:
        return "finance-token"

    def promotion_token(self) -> str:
        return ""


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    return app


def test_period_selection_calculates_effective_wb_period_and_kind():
    reports = [
        {"reportId": 11, "reportType": 1, "dateFrom": "2026-05-04", "dateTo": "2026-05-10"},
        {"reportId": 12, "reportType": 2, "dateFrom": "2026-05-11", "dateTo": "2026-05-17"},
    ]

    selection = PeriodSelection(
        mode="wb_periods",
        date_from=date(2026, 5, 8),
        date_to=date(2026, 5, 13),
        report_kind="main",
        selected_reports=reports,
        available_reports=reports,
    )

    assert selection.is_wb_periods
    assert selection.effective_date_from == date(2026, 5, 4)
    assert selection.effective_date_to == date(2026, 5, 17)
    assert selection.effective_report_kind == "both"
    assert selection.cache_key
    assert "04.05.2026 - 10.05.2026" in selection.label


def test_report_bounds_returns_min_and_max_report_dates():
    assert report_bounds(
        [
            {"dateFrom": "2026-05-11", "dateTo": "2026-05-17"},
            {"dateFrom": "2026-05-04", "dateTo": "2026-05-10"},
        ]
    ) == (date(2026, 5, 4), date(2026, 5, 17))


def test_period_selection_dialog_returns_checked_wb_reports(qapp):
    reports = [
        {"reportId": 11, "reportType": 1, "dateFrom": "2026-05-04", "dateTo": "2026-05-10"},
        {"reportId": 12, "reportType": 2, "dateFrom": "2026-05-04", "dateTo": "2026-05-10"},
    ]
    dialog = PeriodSelectionDialog(
        FakeTokenStore(),
        PeriodSelection(
            mode="wb_periods",
            date_from=date(2026, 5, 4),
            date_to=date(2026, 5, 10),
            selected_reports=[reports[0]],
            available_reports=reports,
        ),
    )

    assert not dialog.manual_report_kind.isEnabled()
    selection = dialog.selection()

    assert selection.is_wb_periods
    assert selection.effective_report_kind == "main"
    assert [report["reportId"] for report in selection.selected_reports] == [11]


def test_service_uses_selected_wb_reports_without_fetching_report_list(monkeypatch):
    service = AutoReportService(token_store=FakeTokenStore())
    selected_reports = [
        {
            "reportId": 101,
            "reportType": 1,
            "dateFrom": "2026-05-04",
            "dateTo": "2026-05-10",
            "forPaySum": 1000,
            "deliveryServiceSum": 100,
            "bankPaymentSum": 900,
        },
        {
            "reportId": 102,
            "reportType": 2,
            "dateFrom": "2026-05-11",
            "dateTo": "2026-05-17",
            "forPaySum": 500,
            "deliveryServiceSum": 50,
            "bankPaymentSum": 450,
        },
    ]

    monkeypatch.setattr(
        "wb_finance_analyst.services.wb_finance_api.WBFinanceAPI.get_sales_reports_list",
        lambda *args, **kwargs: pytest.fail("sales-reports/list should not be called for already selected WB periods"),
    )

    def fake_details(self, report_id, checkpoint_path=None, resume_checkpoint=False, rows_callback=None):
        if rows_callback:
            rows_callback(1)
        return [
            {
                "reportKind": 1 if report_id == 101 else 2,
                "docTypeName": "Продажа",
                "supplierOperName": "Продажа",
                "saName": f"Товар {report_id}",
                "quantity": 1,
                "retailAmount": 1000 if report_id == 101 else 500,
                "ppvzForPay": 1000 if report_id == 101 else 500,
                "deliveryRub": 100 if report_id == 101 else 50,
            }
        ]

    monkeypatch.setattr(
        "wb_finance_analyst.services.wb_finance_api.WBFinanceAPI.get_sales_report_details_by_report_id",
        fake_details,
    )

    result = service.build_report(
        date(2026, 5, 4),
        date(2026, 5, 17),
        "both",
        AppSettings(),
        use_cache=False,
        selected_reports=selected_reports,
        available_reports=selected_reports,
        selection_cache_key="test-selection",
    )

    assert len(result.operations) == 2
    assert result.summary["К перечислению за товар"] == 1500
    assert result.summary["Итого к оплате WB"] == 1350
    settings = dict(zip(result.report_settings["Настройка"], result.report_settings["Значение"]))
    assert settings["Фактический период детализации WB"] == "2026-05-04 - 2026-05-17"


def test_selected_wb_period_ad_allocation_uses_same_period_available_reports(monkeypatch):
    service = AutoReportService(token_store=FakeTokenStore())
    selected_reports = [
        {
            "reportId": 201,
            "reportType": 1,
            "dateFrom": "2026-05-04",
            "dateTo": "2026-05-10",
            "forPaySum": 100,
            "bankPaymentSum": 100,
        }
    ]
    available_reports = selected_reports + [
        {
            "reportId": 202,
            "reportType": 2,
            "dateFrom": "2026-05-04",
            "dateTo": "2026-05-10",
            "forPaySum": 100,
            "bankPaymentSum": 100,
        },
        {
            "reportId": 203,
            "reportType": 2,
            "dateFrom": "2026-05-11",
            "dateTo": "2026-05-17",
            "forPaySum": 800,
            "bankPaymentSum": 800,
        },
    ]

    monkeypatch.setattr(
        "wb_finance_analyst.services.wb_finance_api.WBFinanceAPI.get_sales_report_details_by_report_id",
        lambda *args, **kwargs: [{"reportKind": 1, "docTypeName": "Продажа", "supplierOperName": "Продажа", "saName": "Товар", "quantity": 1, "ppvzForPay": 100}],
    )
    monkeypatch.setattr(service, "fetch_ads", lambda *args, **kwargs: (pd.DataFrame([{"Кампания": "A", "Расход": 100}]), []))

    settings = AppSettings()
    settings.api.ad_source = "api"
    result = service.build_report(
        date(2026, 5, 4),
        date(2026, 5, 10),
        "main",
        settings,
        use_cache=False,
        selected_reports=selected_reports,
        available_reports=available_reports,
        selection_cache_key="same-period-allocation",
    )

    assert result.summary["Реклама WB"] == 50
