from __future__ import annotations

import pandas as pd
from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt


class DataFrameTableModel(QAbstractTableModel):
    def __init__(self, dataframe: pd.DataFrame | None = None, limit: int = 1000, editable: bool = False) -> None:
        super().__init__()
        self._full = dataframe if dataframe is not None else pd.DataFrame()
        self._limit = limit
        self._editable = editable
        self._df = self._full.head(limit).copy()

    def set_dataframe(self, dataframe: pd.DataFrame | None) -> None:
        self.beginResetModel()
        self._full = dataframe if dataframe is not None else pd.DataFrame()
        self._df = self._full.head(self._limit).copy()
        self.endResetModel()

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._df)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._df.columns)

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole):
        if not index.isValid() or role not in (Qt.DisplayRole, Qt.EditRole, Qt.TextAlignmentRole):
            return None
        if role == Qt.TextAlignmentRole:
            value = self._df.iat[index.row(), index.column()]
            return Qt.AlignRight | Qt.AlignVCenter if isinstance(value, (int, float)) else Qt.AlignLeft | Qt.AlignVCenter
        value = self._df.iat[index.row(), index.column()]
        if pd.isna(value):
            return ""
        if isinstance(value, float):
            return f"{value:,.2f}".replace(",", " ")
        return str(value)

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.DisplayRole):
        if role != Qt.DisplayRole:
            return None
        if orientation == Qt.Horizontal and section < len(self._df.columns):
            return str(self._df.columns[section])
        return str(section + 1)

    def flags(self, index: QModelIndex):
        flags = super().flags(index)
        if self._editable and index.isValid():
            flags |= Qt.ItemIsEditable
        return flags

    def setData(self, index: QModelIndex, value, role: int = Qt.EditRole) -> bool:
        if not self._editable or not index.isValid() or role != Qt.EditRole:
            return False
        row = index.row()
        column = index.column()
        if row >= len(self._df) or column >= len(self._df.columns):
            return False
        column_name = self._df.columns[column]
        parsed = self._parse_value(value, column_name)
        self._df.iat[row, column] = parsed
        if row < len(self._full):
            self._full.iat[row, column] = parsed
        self.dataChanged.emit(index, index, [Qt.DisplayRole, Qt.EditRole])
        return True

    def dataframe(self) -> pd.DataFrame:
        return self._full.copy()

    def _parse_value(self, value, column_name: str):
        text = str(value).replace("\xa0", " ").strip()
        if column_name in {"Себестоимость", "Себестоимость за 1 шт", "Упаковка", "Упаковка за 1 шт"}:
            text = text.replace(" ", "").replace(",", ".")
            try:
                return float(text) if text else 0.0
            except ValueError:
                return 0.0
        return text

    @property
    def note(self) -> str:
        if len(self._full) > self._limit:
            return f"Показаны первые {self._limit} строк из {len(self._full)}"
        return f"Строк: {len(self._full)}"
