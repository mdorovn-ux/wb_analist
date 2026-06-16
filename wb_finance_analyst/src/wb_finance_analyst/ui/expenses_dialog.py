from __future__ import annotations

from PySide6.QtWidgets import QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout, QLineEdit, QVBoxLayout

from wb_finance_analyst.domain.models import ExternalExpense


class ExpenseDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Внешний расход")
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.name = QLineEdit()
        self.amount = QDoubleSpinBox()
        self.amount.setMaximum(1_000_000_000)
        self.amount.setDecimals(2)
        self.mode = QComboBox()
        self.mode.addItem("Фиксированная сумма", "fixed")
        self.mode.addItem("Процент от продаж", "percent_of_sales")
        self.comment = QLineEdit()
        form.addRow("Название", self.name)
        form.addRow("Сумма / процент", self.amount)
        form.addRow("Режим", self.mode)
        form.addRow("Комментарий", self.comment)
        layout.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def expense(self) -> ExternalExpense:
        return ExternalExpense(name=self.name.text().strip(), amount=self.amount.value(), mode=self.mode.currentData(), comment=self.comment.text())
