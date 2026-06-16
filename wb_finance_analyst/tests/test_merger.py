from pathlib import Path

import pandas as pd

from wb_finance_analyst.domain.models import WBFinanceResult
from wb_finance_analyst.services.excel_exporter import ExcelExporter
from wb_finance_analyst.services.report_merger import ReportMerger


def _result(value: float) -> WBFinanceResult:
    summary = {
        "К перечислению по продажам": value,
        "Возвраты": 0,
        "К перечислению за товар": value,
        "Логистика": 10,
        "Хранение": 0,
        "Удержания/выплаты": 0,
        "Штрафы": 0,
        "Операции при приемке": 0,
        "Лояльность": 0,
        "Итого к оплате WB": value - 10,
        "Себестоимость": 20,
        "Валовая прибыль": value - 30,
        "Чистая прибыль": value - 30,
        "Маржинальность %": 0,
    }
    return WBFinanceResult(summary=summary, reconciliation=pd.DataFrame([{"Показатель": k, "Сумма": v} for k, v in summary.items()]))


def test_merger_recalculates_totals(tmp_path: Path):
    exporter = ExcelExporter()
    one = tmp_path / "one.xlsx"
    two = tmp_path / "two.xlsx"
    exporter.export(_result(100), one)
    exporter.export(_result(200), two)
    merged = ReportMerger().merge_generated_reports([one, two])
    assert merged.summary["К перечислению за товар"] == 300
    assert merged.summary["Логистика"] == 20
    assert merged.summary["Себестоимость"] == 40
    assert merged.summary["Итого к оплате WB"] == 280
    assert merged.summary["Чистая прибыль"] == 240
