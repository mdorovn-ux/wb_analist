import pandas as pd
import pytest
from datetime import date

from wb_finance_analyst.config.settings import AppSettings
from wb_finance_analyst.domain.models import ExternalExpense, TaxSettings
from wb_finance_analyst.services.auto_report_service import AutoReportService


def test_auto_report_service_builds_management_profit(monkeypatch):
    service = AutoReportService()

    def fake_finance(date_from, date_to, report_kind, use_cache=True):
        return pd.DataFrame(
            [
                {"document_type": "Продажа", "payment_reason": "Продажа", "product": "A", "seller_payment": 1000, "logistics": 50, "storage": 0, "retentions": 0, "penalties": 0, "acceptance": 0, "loyalty_cost": 0},
                {"document_type": "Возврат", "payment_reason": "Возврат", "product": "A", "seller_payment": 100, "logistics": 0, "storage": 0, "retentions": 0, "penalties": 0, "acceptance": 0, "loyalty_cost": 0},
            ]
        ), pd.DataFrame(), {}, []

    def fake_ads(date_from, date_to, settings):
        return pd.DataFrame([{"Дата": "2026-06-01T23:59:59+03:00", "Кампания": "A", "nmId": 123, "Товар": "", "Расход": 25, "Тип рекламы": 9}]), []

    monkeypatch.setattr(service, "fetch_finance_rows", fake_finance)
    monkeypatch.setattr(service, "fetch_ads", fake_ads)
    settings = AppSettings(external_expenses=[ExternalExpense(name="Аренда", amount=50)])
    settings.api.ad_source = "api"
    settings.api.tax_settings = TaxSettings(mode="usn", usn_rate=6)
    result = service.build_report(__import__("datetime").date(2026, 5, 1), __import__("datetime").date(2026, 5, 2), "main", settings)
    assert result.summary["К перечислению за товар"] == 900
    assert result.summary["Итого к оплате WB"] == 850
    assert result.summary["Реклама WB"] == 25
    assert result.summary["Внешние расходы"] == 50
    assert result.summary["УСН"] == 51
    assert result.summary["Чистая прибыль"] == 724
    assert "nmId" not in result.ads.columns
    assert "Товар" not in result.ads.columns
    assert result.ads.iloc[0]["Дата"] == "2026-06-01 23:59"
    assert result.ads.iloc[0]["Тип рекламы"] == "Аукцион"
    assert result.ads.iloc[-1]["Кампания"] == "Итого"


def test_auto_report_recalculate_uses_existing_wb_data_without_api(monkeypatch):
    service = AutoReportService()

    def fake_finance(date_from, date_to, report_kind, use_cache=True):
        return pd.DataFrame(
            [
                {"document_type": "Продажа", "payment_reason": "Продажа", "product": "A", "retail_price": 1000, "wb_sale_amount": 1000, "seller_payment": 1000, "logistics": 50, "storage": 0, "retentions": 0, "penalties": 0, "acceptance": 0, "loyalty_cost": 0},
            ]
        ), pd.DataFrame(), {}, []

    def fake_ads(date_from, date_to, settings):
        return pd.DataFrame([{"Кампания": "A", "Расход": 25}]), []

    monkeypatch.setattr(service, "fetch_finance_rows", fake_finance)
    monkeypatch.setattr(service, "fetch_ads", fake_ads)
    settings = AppSettings(external_expenses=[ExternalExpense(name="Аренда", amount=50)])
    settings.api.ad_source = "api"
    settings.api.tax_settings = TaxSettings(mode="usn", usn_rate=6)
    result = service.build_report(__import__("datetime").date(2026, 6, 1), __import__("datetime").date(2026, 6, 1), "main", settings)

    monkeypatch.setattr(service, "fetch_finance_rows", lambda *args, **kwargs: pytest.fail("Finance API should not be called"))
    monkeypatch.setattr(service, "fetch_ads", lambda *args, **kwargs: pytest.fail("Promotion API should not be called"))
    new_settings = AppSettings(external_expenses=[ExternalExpense(name="Аренда", amount=100)])
    new_settings.api.ad_source = "api"
    new_settings.api.tax_settings = TaxSettings(mode="usn", usn_rate=10)
    recalculated = service.recalculate_report(result, __import__("datetime").date(2026, 6, 1), __import__("datetime").date(2026, 6, 1), "main", new_settings)

    assert len(recalculated.operations) == len(result.operations)
    assert recalculated.summary["Итого к оплате WB"] == 950
    assert recalculated.summary["Реклама WB"] == 25
    assert recalculated.summary["Внешние расходы"] == 100
    assert recalculated.summary["УСН"] == 95
    assert recalculated.summary["Чистая прибыль"] == 730


def test_single_report_kind_allocates_ads_by_wb_payable(monkeypatch):
    service = AutoReportService()

    summary_df = pd.DataFrame(
        [
            {"report_kind": "buyouts", "Показатель": "Итого к оплате WB", "Сумма": 50},
        ]
    )
    summary_df.attrs["all_summary_rows"] = pd.DataFrame(
        [
            {"report_kind": "main", "Показатель": "Итого к оплате WB", "Сумма": 150},
            {"report_kind": "buyouts", "Показатель": "Итого к оплате WB", "Сумма": 50},
        ]
    )

    def fake_finance(date_from, date_to, report_kind, use_cache=True):
        return pd.DataFrame(
            [
                {"document_type": "Продажа", "payment_reason": "Продажа", "product": "A", "seller_payment": 50, "logistics": 0, "storage": 0, "retentions": 0, "penalties": 0, "acceptance": 0, "loyalty_cost": 0},
            ]
        ), summary_df, {"Итого к оплате WB": 50, "К перечислению за товар": 50}, []

    def fake_ads(date_from, date_to, settings):
        return pd.DataFrame([{"Кампания": "A", "Расход": 100}]), []

    monkeypatch.setattr(service, "fetch_finance_rows", fake_finance)
    monkeypatch.setattr(service, "fetch_ads", fake_ads)
    settings = AppSettings()
    settings.api.ad_source = "api"

    result = service.build_report(__import__("datetime").date(2026, 6, 1), __import__("datetime").date(2026, 6, 7), "buyouts", settings)

    assert result.summary["Реклама WB"] == 25
    assert result.summary["Чистая прибыль"] == 25
    assert any("Реклама WB распределена" in value for value in result.legend["Значение"].astype(str))


def test_auto_report_cache_path_is_scoped_by_api_token():
    class TokenStoreA:
        def finance_token(self):
            return "finance-token-a"

        def promotion_token(self):
            return "promotion-token-a"

    class TokenStoreB:
        def finance_token(self):
            return "finance-token-b"

        def promotion_token(self):
            return "promotion-token-b"

    service_a = AutoReportService(token_store=TokenStoreA())
    service_b = AutoReportService(token_store=TokenStoreB())

    path_a = service_a._cache_path("finance_api", date(2026, 6, 1), date(2026, 6, 1), "main")
    path_b = service_b._cache_path("finance_api", date(2026, 6, 1), date(2026, 6, 1), "main")
    ads_a = service_a._cache_path("promotion_api", date(2026, 6, 1), date(2026, 6, 1), "ads")
    ads_b = service_b._cache_path("promotion_api", date(2026, 6, 1), date(2026, 6, 1), "ads")

    assert path_a != path_b
    assert ads_a != ads_b
