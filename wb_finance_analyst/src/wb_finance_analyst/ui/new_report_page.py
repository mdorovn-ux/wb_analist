from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableView,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from wb_finance_analyst.config.defaults import EXPORT_DIR
from wb_finance_analyst.config.settings import AppSettings, SettingsStore
from wb_finance_analyst.domain.models import WBFinanceResult
from wb_finance_analyst.services.excel_exporter import ExcelExporter
from wb_finance_analyst.services.excel_loader import ExcelLoader
from wb_finance_analyst.services.wb_finance_calculator import WBFinanceCalculator
from wb_finance_analyst.ui.column_mapping_dialog import ColumnMappingDialog
from wb_finance_analyst.ui.table_model import DataFrameTableModel
from wb_finance_analyst.ui.widgets import DropHint, MetricCard


class NewReportPage(QWidget):
    result_ready = Signal(object)

    def __init__(self, settings_store: SettingsStore, parent=None) -> None:
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.settings_store = settings_store
        self.settings = settings_store.load()
        self.paths: list[Path] = []
        self.result: WBFinanceResult | None = None
        self.calculator = WBFinanceCalculator()
        self.loader = ExcelLoader()
        self.exporter = ExcelExporter()
        self.file_model = DataFrameTableModel()
        self.table_models: dict[str, DataFrameTableModel] = {}
        self.cards: dict[str, MetricCard] = {}
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        header = QHBoxLayout()
        for text, slot in [
            ("Добавить сырой WB-файл", self.add_file),
            ("Добавить несколько файлов", self.add_files),
            ("Очистить", self.clear),
            ("Настройки колонок", self.open_mapping),
            ("Сформировать отчет", self.calculate),
            ("Сохранить Excel", self.save_excel),
            ("Открыть папку результата", self.open_output_dir),
        ]:
            button = QPushButton(text)
            if text == "Сформировать отчет":
                button.setObjectName("PrimaryButton")
            button.clicked.connect(slot)
            header.addWidget(button)
        header.addStretch(1)
        layout.addLayout(header)
        layout.addWidget(DropHint("Перетащите сюда один или несколько Excel-файлов Wildberries"))

        self.files_table = QTableView()
        self.files_table.setAlternatingRowColors(True)
        self.files_table.setModel(self.file_model)
        layout.addWidget(self.files_table, 1)

        cards_layout = QGridLayout()
        names = [
            "К перечислению по продажам",
            "Возвраты",
            "К перечислению за товар",
            "Логистика",
            "Хранение",
            "Итого к оплате WB",
            "Себестоимость",
            "Валовая прибыль",
            "Чистая прибыль",
            "Маржинальность %",
        ]
        for index, name in enumerate(names):
            card = MetricCard(name)
            self.cards[name] = card
            cards_layout.addWidget(card, index // 5, index % 5)
        layout.addLayout(cards_layout)

        self.tabs = QTabWidget()
        for name in ["Обозначения", "Общая сводка", "Продажи", "Возвраты", "Товары", "Прибыль по товарам", "Внешние расходы", "Предупреждения"]:
            table = QTableView()
            table.setAlternatingRowColors(True)
            model = DataFrameTableModel()
            table.setModel(model)
            self.table_models[name] = model
            page = QWidget()
            page_layout = QVBoxLayout(page)
            note = QLabel(model.note)
            note.setObjectName(f"note_{name}")
            page_layout.addWidget(note)
            page_layout.addWidget(table)
            self.tabs.addTab(page, name)
        layout.addWidget(self.tabs, 3)

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:
        paths = [Path(url.toLocalFile()) for url in event.mimeData().urls() if url.toLocalFile().lower().endswith((".xlsx", ".xlsm", ".xls"))]
        self.add_paths(paths)

    def add_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Выберите WB Excel", "", "Excel (*.xlsx *.xlsm *.xls)")
        if path:
            self.add_paths([Path(path)])

    def add_files(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(self, "Выберите WB Excel", "", "Excel (*.xlsx *.xlsm *.xls)")
        self.add_paths([Path(path) for path in paths])

    def add_paths(self, paths: list[Path]) -> None:
        for path in paths:
            if path not in self.paths:
                self.paths.append(path)
        self._refresh_files()

    def clear(self) -> None:
        self.paths.clear()
        self.result = None
        self._refresh_files()
        for model in self.table_models.values():
            model.set_dataframe(None)

    def _refresh_files(self) -> None:
        rows = []
        for path in self.paths:
            rows.append({"Файл": path.name, "Период": "", "Строк": "", "Статус": "Ожидает", "Предупреждения": "", "Путь": str(path)})
        self.file_model.set_dataframe(__import__("pandas").DataFrame(rows))

    def open_mapping(self) -> None:
        if not self.paths:
            QMessageBox.information(self, "Настройки колонок", "Сначала добавьте WB-файл.")
            return
        try:
            loaded = self.loader.load_raw_report(self.paths[0], self.settings)
            dialog = ColumnMappingDialog(list(map(str, loaded.dataframe.columns)), loaded.column_map, self)
            if dialog.exec():
                self.settings.column_map = dialog.column_map()
                self.settings_store.save(self.settings)
        except Exception as exc:
            QMessageBox.warning(self, "Ошибка", f"Не удалось открыть настройки колонок: {exc}")

    def calculate(self) -> None:
        if not self.paths:
            QMessageBox.information(self, "Новый отчет", "Добавьте один или несколько WB-файлов.")
            return
        try:
            self.settings = self.settings_store.load()
            self.result = self.calculator.calculate_from_paths(self.paths, self.settings)
            self._show_result()
            self.result_ready.emit(self.result)
            logging.info("Сформирован отчет по файлам: %s", self.paths)
        except Exception as exc:
            logging.exception("Ошибка расчета")
            QMessageBox.critical(self, "Не удалось сформировать отчет", str(exc))

    def _show_result(self) -> None:
        if not self.result:
            return
        rows = []
        for path in self.paths:
            rows.append({"Файл": path.name, "Период": self.result.period.label, "Строк": len(self.result.operations), "Статус": "Обработан", "Предупреждения": len(self.result.warnings), "Путь": str(path)})
        self.file_model.set_dataframe(__import__("pandas").DataFrame(rows))
        for name, model in self.table_models.items():
            model.set_dataframe(self.result.table_by_name(name))
        for name, card in self.cards.items():
            card.set_value(self.result.total(name), percent=name.endswith("%"))

    def save_excel(self) -> None:
        if not self.result:
            QMessageBox.information(self, "Сохранить Excel", "Сначала сформируйте отчет.")
            return
        default = self.exporter.default_path(EXPORT_DIR, self.result)
        path, _ = QFileDialog.getSaveFileName(self, "Сохранить отчет", str(default), "Excel (*.xlsx)")
        if not path:
            return
        try:
            self.exporter.export(self.result, Path(path))
            QMessageBox.information(self, "Готово", f"Отчет сохранен:\n{path}")
        except PermissionError:
            QMessageBox.critical(self, "Не удалось сохранить Excel", "Файл занят другой программой.")
        except Exception as exc:
            logging.exception("Ошибка экспорта")
            QMessageBox.critical(self, "Не удалось сохранить Excel", str(exc))

    def open_output_dir(self) -> None:
        EXPORT_DIR.mkdir(parents=True, exist_ok=True)
        QFileDialog.getExistingDirectory(self, "Папка результатов", str(EXPORT_DIR))
