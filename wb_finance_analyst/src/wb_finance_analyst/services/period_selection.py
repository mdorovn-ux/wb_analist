from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from wb_finance_analyst.services.wb_finance_api import classify_report_kind, report_id_from_row, report_kind_label


@dataclass
class PeriodSelection:
    mode: str
    date_from: date
    date_to: date
    report_kind: str = "main"
    period_granularity: str = "weekly"
    selected_reports: list[dict[str, Any]] = field(default_factory=list)
    available_reports: list[dict[str, Any]] = field(default_factory=list)

    @property
    def is_wb_periods(self) -> bool:
        return self.mode == "wb_periods" and bool(self.selected_reports)

    @property
    def effective_date_from(self) -> date:
        bounds = report_bounds(self.selected_reports)
        return bounds[0] if bounds else self.date_from

    @property
    def effective_date_to(self) -> date:
        bounds = report_bounds(self.selected_reports)
        return bounds[1] if bounds else self.date_to

    @property
    def effective_report_kind(self) -> str:
        if not self.selected_reports:
            return self.report_kind
        kinds = {classify_report_kind(report) for report in self.selected_reports}
        if kinds == {"main"}:
            return "main"
        if kinds == {"buyouts"}:
            return "buyouts"
        return "both"

    @property
    def cache_key(self) -> str:
        if not self.selected_reports:
            return ""
        values = []
        for report in sorted(self.selected_reports, key=report_sort_key):
            values.append(str(report_id_from_row(report) or ""))
            values.append(str(report.get("dateFrom", "")))
            values.append(str(report.get("dateTo", "")))
            values.append(classify_report_kind(report))
        return hashlib.sha256("|".join(values).encode("utf-8")).hexdigest()[:16]

    @property
    def label(self) -> str:
        if not self.selected_reports:
            return f"{self.date_from.strftime('%d.%m.%Y')} - {self.date_to.strftime('%d.%m.%Y')} | {report_kind_label(self.report_kind)}"
        groups: dict[tuple[str, str], set[str]] = {}
        for report in self.selected_reports:
            key = (str(report.get("dateFrom", "")), str(report.get("dateTo", "")))
            groups.setdefault(key, set()).add(classify_report_kind(report))
        parts = []
        for (start, end), kinds in sorted(groups.items()):
            if kinds == {"main"}:
                kind_label = "Основной"
            elif kinds == {"buyouts"}:
                kind_label = "По выкупам"
            else:
                kind_label = "Оба"
            parts.append(f"{_display_date(start)} - {_display_date(end)} ({kind_label})")
        if len(parts) <= 2:
            return "; ".join(parts)
        return f"{parts[0]}; ...; {parts[-1]} | выбрано отчётов: {len(self.selected_reports)}"


def report_bounds(reports: list[dict[str, Any]]) -> tuple[date, date] | None:
    starts = [_date_value(report.get("dateFrom")) for report in reports]
    ends = [_date_value(report.get("dateTo")) for report in reports]
    starts = [value for value in starts if value is not None]
    ends = [value for value in ends if value is not None]
    if not starts or not ends:
        return None
    return min(starts), max(ends)


def report_sort_key(report: dict[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(report.get("dateFrom", "")),
        str(report.get("dateTo", "")),
        classify_report_kind(report),
        str(report_id_from_row(report) or ""),
    )


def selected_reports_from_ids(reports: list[dict[str, Any]], selected_ids: set[str]) -> list[dict[str, Any]]:
    return [report for report in reports if str(report_id_from_row(report) or "") in selected_ids]


def _display_date(value: Any) -> str:
    parsed = _date_value(value)
    if parsed:
        return parsed.strftime("%d.%m.%Y")
    return str(value or "")


def _date_value(value: Any) -> date | None:
    if isinstance(value, date):
        return value
    if value in (None, ""):
        return None
    text = str(value).strip()
    if not text:
        return None
    for separator in ("T", " "):
        if separator in text:
            text = text.split(separator, 1)[0]
    try:
        return date.fromisoformat(text)
    except ValueError:
        pass
    try:
        day, month, year = text.split(".")
        return date(int(year), int(month), int(day))
    except Exception:
        return None
