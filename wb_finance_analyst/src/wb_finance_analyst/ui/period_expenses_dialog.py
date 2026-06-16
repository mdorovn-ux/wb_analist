from __future__ import annotations

from PySide6.QtWidgets import QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout, QPushButton, QVBoxLayout

from wb_finance_analyst.domain.models import ExternalExpense

EXPENSE_FIELDS = [
    ("Логистика до WB", "logistics_to_wb"),
    ("Аренда", "rent"),
    ("Коммуналка", "utilities"),
    ("Бухгалтер", "accountant"),
    ("Менеджер", "manager"),
    ("Зарплаты", "salary"),
    ("Внешняя реклама", "external_ads"),
    ("Прочие расходы", "other"),
]


class PeriodExpensesDialog(QDialog):
    def __init__(self, expenses: list[ExternalExpense], template: dict[str, float] | None = None, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Расходы периода")
        self.resize(460, 420)
        self.template = template or {}
        current = {item.name: item.amount for item in expenses}
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.inputs: dict[str, QDoubleSpinBox] = {}
        for label, key in EXPENSE_FIELDS:
            spin = QDoubleSpinBox()
            spin.setMaximum(1_000_000_000)
            spin.setDecimals(2)
            spin.setValue(float(current.get(label, self.template.get(key, 0.0))))
            self.inputs[label] = spin
            form.addRow(label, spin)
        layout.addLayout(form)
        save_template = QPushButton("Сохранить как шаблон")
        save_template.clicked.connect(self._save_template)
        apply_template = QPushButton("Применить шаблон")
        apply_template.clicked.connect(self._apply_template)
        clear = QPushButton("Очистить")
        clear.clicked.connect(self._clear)
        layout.addWidget(save_template)
        layout.addWidget(apply_template)
        layout.addWidget(clear)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def expenses(self) -> list[ExternalExpense]:
        return [ExternalExpense(name=label, amount=spin.value(), mode="fixed") for label, spin in self.inputs.items() if spin.value() != 0]

    def expenses_template(self) -> dict[str, float]:
        return {key: self.inputs[label].value() for label, key in EXPENSE_FIELDS}

    def _save_template(self) -> None:
        self.template = self.expenses_template()

    def _apply_template(self) -> None:
        for label, key in EXPENSE_FIELDS:
            self.inputs[label].setValue(float(self.template.get(key, 0.0)))

    def _clear(self) -> None:
        for spin in self.inputs.values():
            spin.setValue(0.0)
