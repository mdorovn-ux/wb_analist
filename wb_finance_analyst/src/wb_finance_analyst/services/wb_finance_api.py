from __future__ import annotations

import json
import logging
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable

import pandas as pd

from wb_finance_analyst.services.load_progress import CancelCallback, LoadingCancelled
from wb_finance_analyst.services.wb_api_client import WBApiClient

FINANCE_BASE_URL = "https://finance-api.wildberries.ru"

LOGGER = logging.getLogger(__name__)


API_COLUMN_MAP = {
    "reportKind": "report_kind",
    "reportType": "report_kind",
    "reportId": "report_id",
    "dateFrom": "report_date_from",
    "dateTo": "report_date_to",
    "createDate": "report_create_date",
    "docTypeName": "document_type",
    "documentType": "document_type",
    "supplierOperName": "payment_reason",
    "paymentReason": "payment_reason",
    "subjectName": "subject",
    "brandName": "brand",
    "vendorCode": "vendor_code",
    "saName": "product",
    "nmName": "product",
    "quantity": "quantity",
    "qty": "quantity",
    "saleQuantity": "quantity",
    "returnQuantity": "quantity",
    "retailPrice": "retail_price",
    "retailAmount": "wb_sale_amount",
    "retailAmountWithDiscRub": "wb_sale_amount",
    "ppvzForPay": "seller_payment",
    "forPay": "seller_payment",
    "deliveryRub": "logistics",
    "deliveryService": "logistics",
    "deliveryServiceSum": "logistics",
    "storageFee": "storage",
    "deduction": "retentions",
    "penalty": "penalties",
    "acceptance": "acceptance",
    "paidStorage": "storage",
    "loyaltyCost": "loyalty_cost",
    "loyaltyPoints": "loyalty_points",
    "delayChange": "transfer_delay_change",
    "transferDelayChange": "transfer_delay_change",
    "rebillLogisticCost": "reimbursement",
    "rebillLogisticCostSum": "reimbursement",
    "kiz": "barcode",
    "barcode": "barcode",
    "srid": "srid",
    "nmId": "nm_id",
    "date": "date",
    "saleDt": "date",
    "rrDt": "date",
    "wbRewardCorrection": "wb_reward_correction",
    "loyaltyCompensation": "loyalty_compensation",
    "loyaltyCompensationSum": "loyalty_compensation",
    "loyaltyDiscountCompensation": "loyalty_compensation",
}

REPORT_KIND_LABELS = {"main": "Основной", "buyouts": "По выкупам", "both": "Оба"}

SUMMARY_ALIASES = {
    "К перечислению по продажам": ["retailAmountSum", "retailAmount", "saleSum", "salesSum"],
    "Возвраты": ["returnAmountSum", "returnsSum", "returnSum"],
    "К перечислению за товар": ["forPaySum", "forPay", "forPayAmount", "ppvzForPaySum"],
    "Логистика": ["deliveryServiceSum", "deliveryService", "deliveryRubSum", "logisticsSum"],
    "Хранение": ["paidStorageSum", "paidStorage", "storageFee", "storageSum"],
    "Удержания/выплаты": ["deductionSum", "deduction", "retentionSum", "retentionsSum"],
    "Штрафы": ["penaltySum", "penalty", "penaltiesSum"],
    "Операции при приемке": ["paidAcceptanceSum", "paidAcceptance", "acceptanceSum"],
    "Лояльность": ["loyaltyCostSum", "loyaltyCost", "loyaltyPointsSum", "loyaltyPoints"],
    "Итого к оплате WB": ["bankPaymentSum", "bankPayment", "paidSum", "totalPay", "toPay"],
}

INTERNAL_COLUMNS = [
    "report_kind",
    "report_id",
    "report_date_from",
    "report_date_to",
    "report_create_date",
    "document_type",
    "payment_reason",
    "product",
    "retail_price",
    "wb_sale_amount",
    "seller_payment",
    "logistics",
    "storage",
    "retentions",
    "penalties",
    "acceptance",
    "loyalty_cost",
    "loyalty_points",
    "transfer_delay_change",
    "wb_reward_correction",
    "loyalty_compensation",
    "reimbursement",
    "date",
    "srid",
    "nm_id",
    "barcode",
    "subject",
    "brand",
    "vendor_code",
    "quantity",
]

NUMERIC_COLUMNS = [
    "retail_price",
    "wb_sale_amount",
    "seller_payment",
    "logistics",
    "storage",
    "retentions",
    "penalties",
    "acceptance",
    "loyalty_cost",
    "loyalty_points",
    "transfer_delay_change",
    "wb_reward_correction",
    "loyalty_compensation",
    "reimbursement",
    "quantity",
]


class WBFinanceAPI:
    def __init__(
        self,
        token: str,
        status_callback: Callable[[str], None] | None = None,
        cancel_callback: CancelCallback | None = None,
    ) -> None:
        self.client = WBApiClient(
            token=token,
            base_url=FINANCE_BASE_URL,
            min_interval_seconds=65,
            max_retries=3,
            status_callback=status_callback,
            cancel_callback=cancel_callback,
        )
        self.cancel_callback = cancel_callback

    def get_sales_reports_list(self, date_from: date, date_to: date, period: str | None = None) -> list[dict]:
        report_period = period or report_period_for_dates(date_from, date_to)
        rows: list[dict] = []
        limit = 1000
        offset = 0
        while True:
            payload = {
                "dateFrom": date_from.isoformat(),
                "dateTo": date_to.isoformat(),
                "period": report_period,
                "limit": limit,
                "offset": offset,
            }
            data = self.client.post("/api/finance/v1/sales-reports/list", json=payload)
            batch = _as_list(data)
            if not batch:
                break
            rows.extend(batch)
            if len(batch) < limit:
                break
            offset += limit
        return rows

    def get_sales_report_details_by_report_id(
        self,
        report_id: str | int,
        checkpoint_path: Path | None = None,
        resume_checkpoint: bool = False,
        rows_callback: Callable[[int], None] | None = None,
    ) -> list[dict]:
        rows: list[dict] = []
        rrd_id = 0
        if checkpoint_path and resume_checkpoint and checkpoint_path.exists():
            payload = self._read_checkpoint(checkpoint_path)
            rows = payload.get("rows", [])
            rrd_id = int(payload.get("last_rrd_id") or 0)
            if rows_callback:
                rows_callback(len(rows))
            LOGGER.info(
                "WB Finance checkpoint resume report_id=%s rrdid=%s rows=%s path=%s",
                report_id,
                rrd_id,
                len(rows),
                checkpoint_path,
            )
        while True:
            self._raise_if_cancelled()
            payload = {"limit": 100000, "rrdId": rrd_id}
            data = self.client.post(f"/api/finance/v1/sales-reports/detailed/{report_id}", json=payload)
            batch = _as_list(data)
            if not batch:
                break
            rows.extend(batch)
            if rows_callback:
                rows_callback(len(rows))
            next_rrd = _next_rrd_id(data, batch)
            if not next_rrd or next_rrd == rrd_id:
                break
            rrd_id = next_rrd
            if checkpoint_path:
                self._write_checkpoint(checkpoint_path, report_id, rrd_id, rows)
        if checkpoint_path and checkpoint_path.exists():
            checkpoint_path.unlink(missing_ok=True)
        return rows

    def get_sales_report_details_by_period(self, date_from: date, date_to: date, report_type: str | None = None) -> list[dict]:
        rows: list[dict] = []
        rrd_id: int | None = 0
        while True:
            payload: dict[str, Any] = {"dateFrom": date_from.isoformat(), "dateTo": date_to.isoformat()}
            if report_type:
                payload["reportType"] = report_type
            if rrd_id is not None:
                payload["rrdId"] = rrd_id
            data = self.client.post("/api/finance/v1/sales-reports/detailed", json=payload)
            batch = _as_list(data)
            if not batch:
                break
            rows.extend(batch)
            next_rrd = _next_rrd_id(data, batch)
            if not next_rrd or next_rrd == rrd_id:
                break
            rrd_id = next_rrd
        return rows

    def get_selected_report_details(
        self,
        date_from: date,
        date_to: date,
        report_kind: str,
        checkpoint_dir: Path | None = None,
        resume_checkpoint: bool = False,
        rows_callback: Callable[[int], None] | None = None,
    ) -> tuple[list[dict], list[dict], list[str]]:
        report_period = report_period_for_dates(date_from, date_to)
        reports = self.get_sales_reports_list(date_from, date_to, period=report_period)
        selected = select_reports(reports, report_kind, date_from=date_from, date_to=date_to)
        rows: list[dict] = []
        warnings: list[str] = []
        if report_kind == "main" and any(classify_report_kind(report) == "buyouts" for report in reports):
            warnings.append('Выбран тип отчета "Основной", но в ответе API были данные "По выкупам". Они исключены.')
        if report_kind == "buyouts" and any(classify_report_kind(report) == "main" for report in reports):
            warnings.append('Выбран тип отчета "По выкупам", но в ответе API были данные "Основной". Они исключены.')
        for report in selected:
            kind = classify_report_kind(report)
            report_id = report_id_from_row(report)
            if report_id is None:
                warnings.append(f"У отчета WB не найден reportId: {report}")
                continue
            checkpoint_path = checkpoint_dir / f"finance_{report_id}.json" if checkpoint_dir else None
            details = self.get_sales_report_details_by_report_id(
                report_id,
                checkpoint_path=checkpoint_path,
                resume_checkpoint=resume_checkpoint,
                rows_callback=rows_callback,
            )
            for row in details:
                row["reportKind"] = kind
                row["reportId"] = report_id
                row.setdefault("dateFrom", report.get("dateFrom"))
                row.setdefault("dateTo", report.get("dateTo"))
                row.setdefault("createDate", report.get("createDate"))
            rows.extend(details)
        return selected, rows, warnings

    def _write_checkpoint(self, path: Path, report_id: str | int, rrd_id: int, rows: list[dict]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "report_id": report_id,
            "last_rrd_id": rrd_id,
            "rows_loaded": len(rows),
            "updated_at": datetime.now().isoformat(timespec="seconds"),
            "temp_cache_path": str(path),
            "rows": rows,
        }
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        LOGGER.info("WB Finance rrdid checkpoint report_id=%s rrdid=%s rows=%s path=%s", report_id, rrd_id, len(rows), path)

    def _read_checkpoint(self, path: Path) -> dict:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        rows = payload.get("rows")
        if not isinstance(rows, list):
            payload["rows"] = []
        return payload

    def _raise_if_cancelled(self) -> None:
        if self.cancel_callback and self.cancel_callback():
            raise LoadingCancelled("Загрузка отменена")


def finance_api_rows_to_dataframe(rows: list[dict]) -> pd.DataFrame:
    normalized_rows = []
    for row in rows:
        normalized = {column: "" for column in INTERNAL_COLUMNS}
        for source, target in API_COLUMN_MAP.items():
            if source in row:
                normalized[target] = row.get(source)
        normalized["report_kind"] = normalize_report_kind(normalized.get("report_kind"))
        if not normalized["payment_reason"]:
            normalized["payment_reason"] = normalized["document_type"]
        normalized_rows.append(normalized)
    df = pd.DataFrame(normalized_rows, columns=INTERNAL_COLUMNS)
    for column in NUMERIC_COLUMNS:
        df[column] = pd.to_numeric(df[column], errors="coerce").fillna(0.0)
    return df


def select_reports(
    reports: list[dict],
    selected_report_kind: str,
    date_from: date | None = None,
    date_to: date | None = None,
) -> list[dict]:
    if selected_report_kind not in {"main", "buyouts", "both"}:
        raise ValueError("selected_report_kind must be one of: main, buyouts, both")
    allowed = {"main", "buyouts"} if selected_report_kind == "both" else {selected_report_kind}
    selected = [report for report in reports if classify_report_kind(report) in allowed]
    if date_from and date_to:
        exact = [report for report in selected if report_matches_period(report, date_from, date_to)]
        if exact:
            return exact
    return selected


def report_id_from_row(row: dict) -> str | int | None:
    for key in ("reportId", "realizationReportId", "realizationreport_id", "report_id"):
        if row.get(key) not in (None, ""):
            return row[key]
    value = row.get("id")
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return value
    return None


def classify_report_kind(row: dict) -> str:
    for key in ("reportKind", "reportType"):
        kind = normalize_report_kind(row.get(key))
        if kind in {"main", "buyouts"}:
            return kind
    parts = []
    for key in ("reportKind", "reportType", "type", "name", "reportName", "subject"):
        if row.get(key) is not None:
            parts.append(str(row[key]).casefold())
    text = " ".join(parts)
    if "buyout" in text or "выкуп" in text:
        return "buyouts"
    if "main" in text or "основ" in text:
        return "main"
    return "main"


def normalize_report_kind(value: Any) -> str:
    if value in (None, ""):
        return ""
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    if isinstance(value, int):
        return {1: "main", 2: "buyouts"}.get(value, str(value))
    text = str(value).strip().casefold()
    if text in {"1", "1.0", "main", "основной"}:
        return "main"
    if text in {"2", "2.0", "buyouts", "buyout", "по выкупам"} or "выкуп" in text:
        return "buyouts"
    if "основ" in text:
        return "main"
    return str(value)


def report_kind_label(kind: str) -> str:
    return REPORT_KIND_LABELS.get(kind, kind)


def report_period_for_dates(date_from: date, date_to: date) -> str:
    return "daily" if date_from == date_to else "weekly"


def report_matches_period(report: dict, date_from: date, date_to: date) -> bool:
    report_from = _date_value(report.get("dateFrom"))
    report_to = _date_value(report.get("dateTo"))
    if not report_from or not report_to:
        return False
    return report_from == date_from and report_to == date_to


def summary_rows_from_reports(reports: list[dict]) -> tuple[pd.DataFrame, dict[str, float]]:
    per_kind: list[dict] = []
    totals: dict[str, float] = {}
    for report in reports:
        kind = classify_report_kind(report)
        label = report_kind_label(kind)
        values = {name: _first_number(report, aliases) for name, aliases in SUMMARY_ALIASES.items()}
        if not values["Итого к оплате WB"]:
            values["Итого к оплате WB"] = (
                values["К перечислению за товар"]
                - values["Логистика"]
                - values["Хранение"]
                - values["Удержания/выплаты"]
                - values["Штрафы"]
                - values["Операции при приемке"]
                - values["Лояльность"]
            )
        for name, value in values.items():
            totals[name] = totals.get(name, 0.0) + value
            per_kind.append(
                {
                    "report_kind": kind,
                    "report_id": report_id_from_row(report),
                    "date_from": report.get("dateFrom", ""),
                    "date_to": report.get("dateTo", ""),
                    "create_date": report.get("createDate", ""),
                    "seller_finance_name": report.get("sellerFinanceName", ""),
                    "report_type": report.get("reportType", report.get("reportKind", "")),
                    "Тип отчета": label,
                    "Показатель": name,
                    "Сумма": round(value, 2),
                    "Знак": "+" if name in {"К перечислению по продажам", "К перечислению за товар", "Итого к оплате WB"} else "-",
                    "Источник": "sales-reports/list",
                    "Комментарий": "",
                }
            )
    if len({row["report_kind"] for row in per_kind}) > 1:
        for name, value in totals.items():
            per_kind.append(
                {
                    "report_kind": "total",
                    "report_id": "",
                    "date_from": "",
                    "date_to": "",
                    "create_date": "",
                    "seller_finance_name": "",
                    "report_type": "",
                    "Тип отчета": "Итого общий",
                    "Показатель": name,
                    "Сумма": round(value, 2),
                    "Знак": "",
                    "Источник": "sales-reports/list",
                    "Комментарий": "Сумма по выбранным типам отчета",
                }
            )
    return pd.DataFrame(per_kind), {key: round(value, 2) for key, value in totals.items()}


def _first_number(row: dict, aliases: list[str]) -> float:
    lowered = {str(key).casefold(): value for key, value in row.items()}
    for alias in aliases:
        value = row.get(alias)
        if value is None:
            value = lowered.get(alias.casefold())
        if value not in (None, ""):
            return float(pd.to_numeric(pd.Series([value]), errors="coerce").fillna(0).iloc[0])
    return 0.0


def _date_value(value: Any) -> date | None:
    if isinstance(value, date):
        return value
    if value in (None, ""):
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _as_list(data: dict | list) -> list[dict]:
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    for key in ("data", "reports", "rows", "items"):
        value = data.get(key)
        if isinstance(value, list):
            return [row for row in value if isinstance(row, dict)]
    return []


def _next_rrd_id(data: dict | list, batch: list[dict]) -> int | None:
    if isinstance(data, dict):
        for key in ("nextRrdId", "rrdId", "next"):
            value = data.get(key)
            if isinstance(value, int):
                return value
    last = batch[-1]
    for key in ("rrdId", "rrd_id"):
        value = last.get(key)
        if isinstance(value, int):
            return value
    return None
