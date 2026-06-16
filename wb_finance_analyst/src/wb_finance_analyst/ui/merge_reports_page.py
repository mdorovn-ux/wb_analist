from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QMessageBox, QPushButton, QTableView, QTabWidget, QVBoxLayout, QWidget

from wb_finance_analyst.config.defaults import EXPORT_DIR
from wb_finance_analyst.domain.models import WBFinanceResult
from wb_finance_analyst.services.excel_exporter import ExcelExporter
from wb_finance_analyst.services.report_merger import ReportMerger
from wb_finance_analyst.ui.table_model import DataFrameTableModel


class MergeReportsPage(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.paths: list[Path] = []
        self.result: WBFinanceResult | None = None
        self.merger = ReportMerger()
        self.exporter = ExcelExporter()
        self.files_model = DataFrameTableModel()
        self.models: dict[str, DataFrameTableModel] = {}
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        toolbar = QHBoxLayout()
        for text, slot in [
            ("Добавить отчеты", self.add_reports),
            ("Удалить выбранный", self.remove_selected),
            ("Очистить", self.clear),
            ("Объединить", self.merge),
            ("Сохранить объединенный Excel", self.save_excel),
        ]:
            button = QPushButton(text)
            if text == "Объединить":
                button.setObjectName("PrimaryButton")
            button.clicked.connect(slot)
            toolbar.addWidget(button)
        toolbar.addStretch(1)
        layout.addLayout(toolbar)
        self.files = QTableView()
        self.files.setModel(self.files_model)
        layout.addWidget(self.files, 1)
        self.tabs = QTabWidget()
        for name in ["Обозначения", "Общая сводка", "Товары", "Прибыль по товарам", "Внешние расходы", "Предупреждения"]:
            model = DataFrameTableModel()
            table = QTableView()
            table.setModel(model)
            self.models[name] = model
            self.tabs.addTab(table, name)
        layout.addWidget(self.tabs, 3)

    def add_reports(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(self, "Выберите сформированные отчеты", "", "Excel (*.xlsx)")
        for path in paths:
            p = Path(path)
            if p not in self.paths:
                self.paths.append(p)
        self._refresh_files()

    def remove_selected(self) -> None:
        row = self.files.currentIndex().row()
        if 0 <= row < len(self.paths):
            self.paths.pop(row)
            self._refresh_files()

    def clear(self) -> None:
        self.paths.clear()
        self.result = None
        self._refresh_files()

    def _refresh_files(self) -> None:
        import pandas as pd

        self.files_model.set_dataframe(pd.DataFrame([{"Файл": p.name, "Период": "", "Итого к оплате WB": "", "Чистая прибыль": "", "Статус": "Ожидает", "Путь": str(p)} for p in self.paths]))

    def merge(self) -> None:
        if not self.paths:
            QMessageBox.information(self, "Объединение", "Добавьте сформированные отчеты.")
            return
        self.result = self.merger.merge_generated_reports(self.paths)
        for name, model in self.models.items():
            model.set_dataframe(self.result.table_by_name(name))

    def save_excel(self) -> None:
        if not self.result:
            QMessageBox.information(self, "Сохранить Excel", "Сначала объедините отчеты.")
            return
        default = self.exporter.default_path(EXPORT_DIR, self.result)
        path, _ = QFileDialog.getSaveFileName(self, "Сохранить объединенный отчет", str(default), "Excel (*.xlsx)")
        if path:
            self.exporter.export(self.result, Path(path))
            QMessageBox.information(self, "Готово", f"Отчет сохранен:\n{path}")
