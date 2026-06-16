from __future__ import annotations

from PySide6.QtWidgets import QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout, QVBoxLayout

from wb_finance_analyst.domain.models import TaxSettings


class TaxSettingsDialog(QDialog):
    def __init__(self, settings: TaxSettings, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Настроить налоги")
        self.resize(420, 260)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.mode = QComboBox()
        self.mode.addItem("Не учитывать", "none")
        self.mode.addItem("УСН", "usn")
        self.mode.addItem("НДС", "nds")
        self.mode.addItem("УСН + НДС", "usn_nds")
        self.mode.addItem("Ручная сумма", "manual")
        self._set_combo(self.mode, settings.mode)
        self.usn_rate = self._percent(settings.usn_rate)
        self.nds_rate = self._percent(settings.nds_rate)
        self.usn_base = self._base_combo(settings.usn_base)
        self.nds_base = self._base_combo(settings.nds_base)
        self.manual_amount = QDoubleSpinBox()
        self.manual_amount.setMaximum(1_000_000_000)
        self.manual_amount.setDecimals(2)
        self.manual_amount.setValue(settings.manual_amount)
        form.addRow("Режим налога", self.mode)
        form.addRow("Ставка УСН, %", self.usn_rate)
        form.addRow("База УСН", self.usn_base)
        form.addRow("Ставка НДС, %", self.nds_rate)
        form.addRow("База НДС", self.nds_base)
        form.addRow("Ручная сумма", self.manual_amount)
        layout.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def tax_settings(self) -> TaxSettings:
        return TaxSettings(
            mode=self.mode.currentData(),
            usn_rate=self.usn_rate.value(),
            nds_rate=self.nds_rate.value(),
            usn_base=self.usn_base.currentData(),
            nds_base=self.nds_base.currentData(),
            manual_amount=self.manual_amount.value(),
        )

    def _percent(self, value: float) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(0, 100)
        spin.setDecimals(2)
        spin.setValue(value)
        return spin

    def _base_combo(self, current: str) -> QComboBox:
        combo = QComboBox()
        combo.addItem("Итого к оплате WB", "wb_payable")
        combo.addItem("К перечислению за товар", "goods")
        combo.addItem("Валовая прибыль", "gross_profit")
        self._set_combo(combo, current)
        return combo

    def _set_combo(self, combo: QComboBox, value: str) -> None:
        index = combo.findData(value)
        if index >= 0:
            combo.setCurrentIndex(index)
