from __future__ import annotations

from pathlib import Path

import pandas as pd

from wb_finance_analyst.config.settings import AppSettings
from wb_finance_analyst.domain.models import LoadedReport
from wb_finance_analyst.services.column_mapper import ColumnMapper
from wb_finance_analyst.services.report_period import detect_period


class ExcelLoader:
    def __init__(self, mapper: ColumnMapper | None = None) -> None:
        self.mapper = mapper or ColumnMapper()

    def load_raw_report(self, path: Path, settings: AppSettings | None = None) -> LoadedReport:
        settings = settings or AppSettings()
        df = pd.read_excel(path, sheet_name=0)
        df = df.dropna(how="all").reset_index(drop=True)
        column_map = self.mapper.map_columns(df.columns, settings.column_map)
        date_columns = [column_map.date_sale] if column_map.date_sale else [column_map.date_order]
        period = detect_period(df, date_columns, path)
        warnings = []
        missing = column_map.missing_required()
        if missing:
            warnings.append("Не найдены обязательные колонки: " + ", ".join(missing))
        return LoadedReport(path=path, dataframe=df, column_map=column_map, period=period, warnings=warnings)

    def load_many_raw_reports(self, paths: list[Path], settings: AppSettings | None = None) -> list[LoadedReport]:
        return [self.load_raw_report(path, settings) for path in paths]
