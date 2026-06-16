from __future__ import annotations

from pathlib import Path

import pandas as pd
from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QMessageBox, QPushButton, QTableView, QVBoxLayout, QWidget

from wb_finance_analyst.domain.models import CostItem
from wb_finance_analyst.services.cost_repository import CostRepository
from wb_finance_analyst.ui.table_model import DataFrameTableModel


class CostsPage(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.repo = CostRepository()
        self.model = DataFrameTableModel(editable=True)
        self._build_ui()
        self._refresh()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        toolbar = QHBoxLayout()
        for text, slot in [
            ("Импорт себестоимости из Excel", self.import_excel),
            ("Экспорт себестоимости в Excel", self.export_excel),
            ("Сохранить", self.save),
            ("Добавить товар", self.add_item),
            ("Удалить товар", self.delete_item),
        ]:
            button = QPushButton(text)
            button.clicked.connect(slot)
            toolbar.addWidget(button)
        toolbar.addStretch(1)
        layout.addLayout(toolbar)
        self.table = QTableView()
        self.table.setModel(self.model)
        layout.addWidget(self.table)

    def _refresh(self) -> None:
        self.model.set_dataframe(self._items_to_dataframe(list(self.repo.load().values())))

    def import_excel(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Импорт себестоимости", "", "Excel (*.xlsx *.xls)")
        if path:
            items = self.repo.import_from_excel(Path(path))
            self.model.set_dataframe(self._items_to_dataframe(items))

    def export_excel(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Экспорт себестоимости", "costs.xlsx", "Excel (*.xlsx)")
        if path:
            items = self._items_from_table()
            self.repo.save(items)
            self._items_to_dataframe(items).to_excel(path, index=False)

    def save(self) -> None:
        self.repo.save(self._items_from_table())
        QMessageBox.information(self, "Сохранено", "Справочник себестоимости сохранен.")

    def add_item(self) -> None:
        df = self.model.dataframe()
        row = pd.DataFrame([{"Товар": "Новый товар", "Себестоимость за 1 шт": 0.0, "Упаковка за 1 шт": 0.0, "Комментарий": ""}])
        self.model.set_dataframe(pd.concat([df, row], ignore_index=True))
        self.table.selectRow(len(df))
        self.table.edit(self.model.index(len(df), 0))

    def delete_item(self) -> None:
        row = self.table.currentIndex().row()
        df = self.model.dataframe()
        if 0 <= row < len(df):
            self.model.set_dataframe(df.drop(df.index[row]).reset_index(drop=True))

    def _items_to_dataframe(self, items: list[CostItem]) -> pd.DataFrame:
        return pd.DataFrame([item.model_dump() for item in items], columns=["product", "cost", "packaging", "comment"]).rename(
            columns={"product": "Товар", "cost": "Себестоимость за 1 шт", "packaging": "Упаковка за 1 шт", "comment": "Комментарий"}
        )

    def _items_from_table(self) -> list[CostItem]:
        df = self.model.dataframe()
        items: list[CostItem] = []
        for _, row in df.iterrows():
            product = str(row.get("Товар", "")).strip()
            if not product:
                continue
            items.append(
                CostItem(
                    product=product,
                    cost=self._number(row.get("Себестоимость за 1 шт", 0)),
                    packaging=self._number(row.get("Упаковка за 1 шт", 0)),
                    comment=str(row.get("Комментарий", "") or ""),
                )
            )
        return items

    def _number(self, value: object) -> float:
        text = str(value).replace("\xa0", " ").strip().replace(" ", "").replace(",", ".")
        try:
            return float(text) if text else 0.0
        except ValueError:
            return 0.0
