from __future__ import annotations

import re
from datetime import date
from pathlib import Path

import pandas as pd

from wb_finance_analyst.domain.models import ReportPeriod


def detect_period(df: pd.DataFrame, date_columns: list[str | None], path: Path | None = None) -> ReportPeriod:
    dates: list[pd.Timestamp] = []
    for column in date_columns:
        if not column or column not in df.columns:
            continue
        parsed = pd.to_datetime(df[column], errors="coerce")
        dates.extend([x for x in parsed.dropna().tolist()])
    if dates:
        data_period = ReportPeriod(start=min(dates).date(), end=max(dates).date())
        filename_period = _from_filename(path.name) if path else ReportPeriod()
        if (
            filename_period.start
            and filename_period.end
            and data_period.start
            and data_period.end
            and data_period.start <= filename_period.start <= data_period.end
            and data_period.start <= filename_period.end <= data_period.end
        ):
            return filename_period
        return data_period
    if path:
        return _from_filename(path.name)
    return ReportPeriod()


def _from_filename(name: str) -> ReportPeriod:
    range_match = re.search(r"(\d{2})\.(\d{2})\s*[-_]\s*(\d{2})\.(\d{2})(?:\.(\d{4}))?", name)
    if range_match:
        d1, m1, d2, m2, year = range_match.groups()
        y = int(year or date.today().year)
        return ReportPeriod(start=date(y, int(m1), int(d1)), end=date(y, int(m2), int(d2)))
    one = re.search(r"(\d{2})\.(\d{2})(?:\.(\d{4}))?", name)
    if one:
        d, m, year = one.groups()
        y = int(year or date.today().year)
        dt = date(y, int(m), int(d))
        return ReportPeriod(start=dt, end=dt)
    compact = re.search(r"20\d{6}", name)
    if compact:
        text = compact.group(0)
        dt = date(int(text[:4]), int(text[4:6]), int(text[6:8]))
        return ReportPeriod(start=dt, end=dt)
    return ReportPeriod()
