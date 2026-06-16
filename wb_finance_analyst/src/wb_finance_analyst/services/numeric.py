from __future__ import annotations

import math
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

import pandas as pd


def to_number(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    try:
        if pd.isna(value):
            return default
    except TypeError:
        pass
    if isinstance(value, (int, float)):
        if math.isnan(value) if isinstance(value, float) else False:
            return default
        return float(value)
    text = str(value).strip()
    if not text:
        return default
    text = text.replace("\u00a0", " ").replace(" ", "")
    text = text.replace(",", ".")
    text = text.replace("−", "-")
    try:
        return float(Decimal(text))
    except (InvalidOperation, ValueError):
        return default


def money(value: Any) -> float:
    return float(Decimal(str(to_number(value))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def numeric_series(series: pd.Series | None) -> pd.Series:
    if series is None:
        return pd.Series(dtype=float)
    return series.map(to_number).astype(float)
