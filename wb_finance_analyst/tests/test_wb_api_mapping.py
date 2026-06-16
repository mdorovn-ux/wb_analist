from datetime import date

from wb_finance_analyst.services.wb_finance_api import (
    WBFinanceAPI,
    finance_api_rows_to_dataframe,
    report_id_from_row,
    report_period_for_dates,
    select_reports,
    summary_rows_from_reports,
)


def test_finance_api_rows_to_dataframe_maps_camel_case_fields():
    df = finance_api_rows_to_dataframe(
        [
            {
                "reportKind": "main",
                "docTypeName": "Продажа",
                "supplierOperName": "Продажа",
                "saName": "Товар A",
                "retailAmount": 1200,
                "ppvzForPay": 900,
                "deliveryRub": 50,
                "storageFee": 3,
                "nmId": 123,
            }
        ]
    )
    assert df.loc[0, "report_kind"] == "main"
    assert df.loc[0, "payment_reason"] == "Продажа"
    assert df.loc[0, "product"] == "Товар A"
    assert df.loc[0, "seller_payment"] == 900
    assert df.loc[0, "logistics"] == 50
    assert "loyalty_points" in df.columns


def test_select_reports_filters_report_kind_and_summary_uses_list_values():
    reports = [
        {"reportId": 1, "reportType": 1, "dateFrom": "2026-06-01", "dateTo": "2026-06-01", "forPaySum": 145073.87, "deliveryServiceSum": 25405.36, "paidStorageSum": 541.73, "deductionSum": 18530, "penaltySum": 120, "bankPaymentSum": 100476.78},
        {"reportId": 2, "reportType": 2, "dateFrom": "2026-06-01", "dateTo": "2026-06-01", "forPaySum": 10, "bankPaymentSum": 10},
    ]
    selected = select_reports(reports, "main", date(2026, 6, 1), date(2026, 6, 1))
    assert [row["reportId"] for row in selected] == [1]
    summary_df, summary = summary_rows_from_reports(selected)
    assert summary["К перечислению за товар"] == 145073.87
    assert summary["Логистика"] == 25405.36
    assert summary["Итого к оплате WB"] == 100476.78
    assert set(summary_df["report_kind"]) == {"main"}
    assert set(summary_df["report_id"]) == {1}


def test_report_details_by_id_sends_required_body_and_paginates(monkeypatch):
    calls = []

    def fake_post(self, path, json=None):
        calls.append((path, json))
        if json["rrdId"] == 0:
            return [{"rrdId": 10, "supplierOperName": "Продажа"}]
        return []

    monkeypatch.setattr("wb_finance_analyst.services.wb_api_client.WBApiClient.post", fake_post)
    rows = WBFinanceAPI("token").get_sales_report_details_by_report_id(123)
    assert rows == [{"rrdId": 10, "supplierOperName": "Продажа"}]
    assert calls == [
        ("/api/finance/v1/sales-reports/detailed/123", {"limit": 100000, "rrdId": 0}),
        ("/api/finance/v1/sales-reports/detailed/123", {"limit": 100000, "rrdId": 10}),
    ]


def test_sales_reports_list_uses_daily_period_and_paginates(monkeypatch):
    calls = []

    def fake_post(self, path, json=None):
        calls.append((path, json))
        if json["offset"] == 0:
            return [{"reportId": index, "reportType": 1} for index in range(1000)]
        return [{"reportId": 1001, "reportType": 1}]

    monkeypatch.setattr("wb_finance_analyst.services.wb_api_client.WBApiClient.post", fake_post)
    rows = WBFinanceAPI("token").get_sales_reports_list(date(2026, 6, 1), date(2026, 6, 1))
    assert len(rows) == 1001
    assert calls[0][1]["period"] == "daily"
    assert calls[0][1]["limit"] == 1000
    assert calls[1][1]["offset"] == 1000


def test_report_period_for_dates_uses_weekly_for_ranges():
    assert report_period_for_dates(date(2026, 6, 1), date(2026, 6, 1)) == "daily"
    assert report_period_for_dates(date(2026, 5, 4), date(2026, 5, 10)) == "weekly"


def test_report_id_from_row_does_not_use_uuid_id_as_report_id():
    assert report_id_from_row({"id": "3a93be88-fa5a-492c-ae4e-36ef74531dd7"}) is None
    assert report_id_from_row({"id": "12345"}) == "12345"
    assert report_id_from_row({"reportId": 12345, "id": "uuid"}) == 12345
