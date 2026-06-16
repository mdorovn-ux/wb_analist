from __future__ import annotations

import pandas as pd
from PySide6.QtWidgets import QComboBox, QDialog, QDialogButtonBox, QFormLayout, QLabel, QVBoxLayout

from wb_finance_analyst.domain.models import ColumnMap


class ColumnMappingDialog(QDialog):
    FIELDS = [
        ("doc_type", "Тип документа"),
        ("payment_reason", "Обоснование для оплаты"),
        ("date_sale", "Дата продажи"),
        ("quantity", "Количество"),
        ("product_name", "Товар"),
        ("supplier_article", "Артикул"),
        ("nm_id", "Код номенклатуры"),
        ("seller_transfer", "К перечислению продавцу"),
        ("logistics", "Логистика"),
        ("storage", "Хранение"),
        ("deductions", "Удержания"),
        ("penalties", "Штрафы"),
        ("acceptance", "Приемка"),
        ("loyalty", "Лояльность"),
    ]

    def __init__(self, columns: list[str], mapping: ColumnMap, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Настройки колонок")
        self.resize(560, 620)
        self.combos: dict[str, QComboBox] = {}
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Проверьте сопоставление колонок WB-отчета"))
        form = QFormLayout()
        options = [""] + columns
        for field, label in self.FIELDS:
            combo = QComboBox()
            combo.addItems(options)
            current = getattr(mapping, field, None)
            if current in options:
                combo.setCurrentText(current)
            self.combos[field] = combo
            form.addRow(label, combo)
        layout.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def column_map(self) -> ColumnMap:
        return ColumnMap(**{field: combo.currentText() or None for field, combo in self.combos.items()})
