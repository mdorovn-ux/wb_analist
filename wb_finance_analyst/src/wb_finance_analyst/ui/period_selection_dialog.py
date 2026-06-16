from __future__ import annotations

import logging
from datetime import date

from PySide6.QtCore import QObject, QDate, Qt, QThread, Signal, Slot
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QGridLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from wb_finance_analyst.config.defaults import APP_ICON_PATH
from wb_finance_analyst.services.period_selection import PeriodSelection, report_sort_key, selected_reports_from_ids
from wb_finance_analyst.services.token_store import TokenStore
from wb_finance_analyst.services.wb_finance_api import WBFinanceAPI, classify_report_kind, report_id_from_row, report_kind_label

LOGGER = logging.getLogger(__name__)


class ReportListWorker(QObject):
    finished = Signal(object)
    failed = Signal(str)
    status_changed = Signal(str)

    def __init__(self, token: str, date_from: date, date_to: date, period: str) -> None:
        super().__init__()
        self.token = token
        self.date_from = date_from
        self.date_to = date_to
        self.period = period

    @Slot()
    def run(self) -> None:
        try:
            api = WBFinanceAPI(self.token, status_callback=self.status_changed.emit)
            reports = api.get_sales_reports_list(self.date_from, self.date_to, period=self.period)
            self.finished.emit(reports)
        except Exception as exc:
            LOGGER.exception("Failed to load WB report periods")
            self.failed.emit(str(exc))


class PeriodSelectionDialog(QDialog):
    def __init__(self, token_store: TokenStore, selection: PeriodSelection, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Задать период")
        self.setWindowIcon(QIcon(str(APP_ICON_PATH)))
        self.resize(900, 560)
        self.token_store = token_store
        self._selection = selection
        self._reports: list[dict] = list(selection.available_reports or selection.selected_reports)
        self._thread: QThread | None = None
        self._worker: ReportListWorker | None = None
        self._build_ui(selection)
        self._toggle_mode()
        self._fill_reports(self._reports, selected_reports=selection.selected_reports)

    def selection(self) -> PeriodSelection:
        mode = self.mode.currentData()
        if mode == "wb_periods":
            selected_ids = self._checked_report_ids()
            reports = selected_reports_from_ids(self._reports, selected_ids)
            if not reports:
                mode = "manual"
            return PeriodSelection(
                mode=mode,
                date_from=self._date(self.manual_from.date()),
                date_to=self._date(self.manual_to.date()),
                report_kind=self.manual_report_kind.currentData(),
                period_granularity=self.period_granularity.currentData(),
                selected_reports=reports,
                available_reports=list(self._reports),
            )
        return PeriodSelection(
            mode="manual",
            date_from=self._date(self.manual_from.date()),
            date_to=self._date(self.manual_to.date()),
            report_kind=self.manual_report_kind.currentData(),
            period_granularity=self.period_granularity.currentData(),
        )

    def accept(self) -> None:
        if self.mode.currentData() == "manual" and self.manual_from.date() > self.manual_to.date():
            QMessageBox.warning(self, "Период", "Дата от не может быть больше даты до.")
            return
        if self.mode.currentData() == "wb_periods" and not self._checked_report_ids():
            QMessageBox.warning(self, "WB-периоды", "Выберите хотя бы один WB-отчёт или переключитесь на ручной диапазон.")
            return
        super().accept()

    def closeEvent(self, event) -> None:  # noqa: N802
        self._stop_worker()
        super().closeEvent(event)

    def _build_ui(self, selection: PeriodSelection) -> None:
        layout = QVBoxLayout(self)
        top = QGridLayout()
        top.setHorizontalSpacing(8)
        top.setVerticalSpacing(4)
        self.mode = QComboBox()
        self.mode.addItem("По датам вручную", "manual")
        self.mode.addItem("WB-периоды", "wb_periods")
        self.mode.setCurrentIndex(1 if selection.is_wb_periods else 0)
        self.mode.currentIndexChanged.connect(self._toggle_mode)
        self.manual_controls = QFrame()
        self.manual_controls.setObjectName("ManualPeriodControls")
        manual_layout = QGridLayout(self.manual_controls)
        manual_layout.setContentsMargins(8, 4, 8, 4)
        manual_layout.setHorizontalSpacing(6)
        self.manual_from = QDateEdit(QDate(selection.date_from.year, selection.date_from.month, selection.date_from.day))
        self.manual_from.setCalendarPopup(True)
        self.manual_from.setFixedWidth(118)
        self.manual_to = QDateEdit(QDate(selection.date_to.year, selection.date_to.month, selection.date_to.day))
        self.manual_to.setCalendarPopup(True)
        self.manual_to.setFixedWidth(118)
        self.manual_report_kind = QComboBox()
        self.manual_report_kind.addItem("Основной", "main")
        self.manual_report_kind.addItem("По выкупам", "buyouts")
        self.manual_report_kind.addItem("Оба", "both")
        self.manual_report_kind.setMinimumWidth(140)
        self._set_combo_data(self.manual_report_kind, selection.report_kind)
        manual_layout.addWidget(QLabel("Дата от"), 0, 0)
        manual_layout.addWidget(self.manual_from, 0, 1)
        manual_layout.addWidget(QLabel("до"), 0, 2)
        manual_layout.addWidget(self.manual_to, 0, 3)
        manual_layout.addWidget(QLabel("Тип отчёта"), 0, 4)
        manual_layout.addWidget(self.manual_report_kind, 0, 5)
        top.addWidget(QLabel("Способ выбора периода"), 0, 0)
        top.addWidget(self.mode, 0, 1)
        top.addWidget(self.manual_controls, 0, 2)
        top.setColumnStretch(2, 1)
        layout.addLayout(top)
        self.manual_hint = QLabel("Ручные даты и тип отчёта отключены: в режиме WB-периодов тип и диапазон задаются выбранными строками таблицы.")
        self.manual_hint.setWordWrap(True)
        self.manual_hint.setStyleSheet("color: #64748b; padding: 2px 8px;")
        layout.addWidget(self.manual_hint)

        self.wb_box = QWidget()
        wb_layout = QVBoxLayout(self.wb_box)
        filters = QGridLayout()
        filters.setHorizontalSpacing(8)
        self.lookup_from = QDateEdit(QDate(selection.date_from.year, selection.date_from.month, selection.date_from.day))
        self.lookup_from.setCalendarPopup(True)
        self.lookup_from.setFixedWidth(112)
        self.lookup_to = QDateEdit(QDate(selection.date_to.year, selection.date_to.month, selection.date_to.day))
        self.lookup_to.setCalendarPopup(True)
        self.lookup_to.setFixedWidth(112)
        self.period_granularity = QComboBox()
        self.period_granularity.addItem("Недельно", "weekly")
        self.period_granularity.addItem("По дням", "daily")
        self.period_granularity.setFixedWidth(120)
        self._set_combo_data(self.period_granularity, selection.period_granularity)
        self.load_periods_button = QPushButton("Загрузить WB-периоды")
        self.load_periods_button.setMinimumWidth(210)
        self.load_periods_button.clicked.connect(self.load_wb_periods)
        filters.addWidget(QLabel("С"), 0, 0)
        filters.addWidget(self.lookup_from, 0, 1)
        filters.addWidget(QLabel("по"), 0, 2)
        filters.addWidget(self.lookup_to, 0, 3)
        filters.addWidget(QLabel("Периоды"), 0, 4)
        filters.addWidget(self.period_granularity, 0, 5)
        filters.addWidget(self.load_periods_button, 0, 6)
        filters.setColumnStretch(7, 1)
        wb_layout.addLayout(filters)

        self.report_table = QTableWidget(0, 6)
        self.report_table.setHorizontalHeaderLabels(["", "Период", "Тип", "№ отчёта", "К оплате WB", "Дата формирования"])
        self.report_table.horizontalHeader().setStretchLastSection(True)
        self.report_table.setAlternatingRowColors(True)
        wb_layout.addWidget(self.report_table, 1)
        self.wb_status = QLabel("Загрузите список WB-периодов и выберите нужные отчёты.")
        self.wb_status.setWordWrap(True)
        wb_layout.addWidget(self.wb_status)
        layout.addWidget(self.wb_box, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText("Применить")
        buttons.button(QDialogButtonBox.Cancel).setText("Отмена")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def load_wb_periods(self) -> None:
        if self._thread and self._thread.isRunning():
            return
        token = self.token_store.finance_token()
        if not token:
            QMessageBox.warning(self, "Finance API token не задан", "Сначала сохраните Finance API token в настройках API Wildberries.")
            return
        start = self._date(self.lookup_from.date())
        end = self._date(self.lookup_to.date())
        if start > end:
            QMessageBox.warning(self, "Период", "Дата начала поиска не может быть больше даты окончания.")
            return
        self.load_periods_button.setEnabled(False)
        self.wb_status.setText("WB Finance API: получение списка периодов...")
        self._thread = QThread(self)
        self._worker = ReportListWorker(token, start, end, self.period_granularity.currentData())
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.status_changed.connect(self.wb_status.setText)
        self._worker.finished.connect(self._on_periods_loaded)
        self._worker.failed.connect(self._on_periods_failed)
        self._worker.finished.connect(self._thread.quit)
        self._worker.failed.connect(self._thread.quit)
        self._thread.finished.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.finished.connect(self._clear_worker)
        self._thread.start()

    def _on_periods_loaded(self, reports: object) -> None:
        self._reports = sorted(list(reports or []), key=report_sort_key)
        self._fill_reports(self._reports, selected_reports=[])
        self.load_periods_button.setEnabled(True)
        self.wb_status.setText(f"Загружено WB-отчётов: {len(self._reports)}. Выберите один или несколько периодов.")

    def _on_periods_failed(self, message: str) -> None:
        self.load_periods_button.setEnabled(True)
        self.wb_status.setText("Не удалось загрузить WB-периоды.")
        QMessageBox.critical(self, "Не удалось загрузить WB-периоды", message)

    def _fill_reports(self, reports: list[dict], selected_reports: list[dict] | None = None) -> None:
        selected_ids = {str(report_id_from_row(report) or "") for report in (selected_reports or [])}
        self.report_table.setRowCount(len(reports))
        for row_index, report in enumerate(sorted(reports, key=report_sort_key)):
            report_id = str(report_id_from_row(report) or "")
            check_item = QTableWidgetItem()
            check_item.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            check_item.setCheckState(Qt.Checked if report_id in selected_ids else Qt.Unchecked)
            check_item.setData(Qt.UserRole, report_id)
            self.report_table.setItem(row_index, 0, check_item)
            period = f"{self._display_date(report.get('dateFrom'))} - {self._display_date(report.get('dateTo'))}"
            values = [
                period,
                report_kind_label(classify_report_kind(report)),
                report_id,
                self._number_text(report.get("bankPaymentSum", report.get("bankPayment", ""))),
                self._display_date(report.get("createDate")),
            ]
            for column, value in enumerate(values, start=1):
                item = QTableWidgetItem(value)
                item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                self.report_table.setItem(row_index, column, item)
        self.report_table.resizeColumnsToContents()

    def _checked_report_ids(self) -> set[str]:
        ids: set[str] = set()
        for row in range(self.report_table.rowCount()):
            item = self.report_table.item(row, 0)
            if item and item.checkState() == Qt.Checked:
                value = item.data(Qt.UserRole)
                if value not in (None, ""):
                    ids.add(str(value))
        return ids

    def _toggle_mode(self) -> None:
        is_manual = self.mode.currentData() == "manual"
        self.manual_controls.setEnabled(is_manual)
        self.wb_box.setEnabled(not is_manual)
        self.manual_report_kind.setEnabled(is_manual)
        self.manual_hint.setVisible(not is_manual)
        if is_manual:
            self.manual_controls.setStyleSheet(
                "#ManualPeriodControls { border: 1px solid #d8e2ef; border-radius: 6px; background: #ffffff; }"
            )
        else:
            self.manual_controls.setStyleSheet(
                "#ManualPeriodControls { border: 1px dashed #cbd5e1; border-radius: 6px; background: #eef2f7; }"
                "#ManualPeriodControls QLabel { color: #94a3b8; }"
            )

    def _stop_worker(self) -> None:
        if self._thread and self._thread.isRunning():
            self._thread.quit()
            self._thread.wait(3000)

    def _clear_worker(self) -> None:
        self._worker = None
        self._thread = None

    def _set_combo_data(self, combo: QComboBox, value: str) -> None:
        for index in range(combo.count()):
            if combo.itemData(index) == value:
                combo.setCurrentIndex(index)
                return

    def _date(self, qdate: QDate) -> date:
        return date(qdate.year(), qdate.month(), qdate.day())

    def _display_date(self, value) -> str:
        text = str(value or "")
        if "T" in text:
            text = text.split("T", 1)[0]
        try:
            parsed = date.fromisoformat(text)
            return parsed.strftime("%d.%m.%Y")
        except ValueError:
            return text

    def _number_text(self, value) -> str:
        try:
            return f"{float(value):,.2f}".replace(",", " ")
        except (TypeError, ValueError):
            return str(value or "")
