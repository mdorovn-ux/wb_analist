from __future__ import annotations

import logging
import time
from datetime import date, timedelta
from pathlib import Path

import requests
from PySide6.QtCore import QObject, QDate, Qt, QSize, QThread, QTimer, Signal, Slot
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QStyle,
    QTableView,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from wb_finance_analyst.config.defaults import EXPORT_DIR
from wb_finance_analyst.config.settings import SettingsStore
from wb_finance_analyst.domain.models import WBFinanceResult
from wb_finance_analyst.services.auto_report_service import AutoReportService
from wb_finance_analyst.services.excel_exporter import ExcelExporter
from wb_finance_analyst.services.load_progress import LoadProgress, LoadingCancelled
from wb_finance_analyst.services.period_selection import PeriodSelection
from wb_finance_analyst.services.token_store import TokenStore
from wb_finance_analyst.ui.period_expenses_dialog import PeriodExpensesDialog
from wb_finance_analyst.ui.period_selection_dialog import PeriodSelectionDialog
from wb_finance_analyst.ui.settings_dialog import SettingsDialog
from wb_finance_analyst.ui.table_model import DataFrameTableModel
from wb_finance_analyst.ui.tax_settings_dialog import TaxSettingsDialog
from wb_finance_analyst.ui.widgets import MetricCard

LOGGER = logging.getLogger(__name__)


class NetworkCheckWorker(QObject):
    finished = Signal(bool, str)

    CHECK_URL = "https://www.cloudflare.com/cdn-cgi/trace"

    @Slot()
    def run(self) -> None:
        try:
            response = requests.get(self.CHECK_URL, timeout=(1, 1.5), proxies={"http": None, "https": None})
            online = response.status_code < 500
            message = "Сеть доступна" if online else f"Сеть недоступна: HTTP {response.status_code}"
            self.finished.emit(online, message)
        except requests.RequestException as exc:
            self.finished.emit(False, f"Сеть недоступна: {exc.__class__.__name__}")


class AutoReportWorker(QObject):
    progress_changed = Signal(int)
    status_changed = Signal(str)
    rows_loaded_changed = Signal(int)
    wait_timer_changed = Signal(int)
    stage_changed = Signal(str)
    finished = Signal(object)
    failed = Signal(str)
    cancelled = Signal()

    def __init__(
        self,
        token_store: TokenStore,
        date_from: date,
        date_to: date,
        report_kind: str,
        settings,
        use_cache: bool,
        load_mode: str,
        resume_checkpoint: bool,
        selected_reports: list[dict] | None = None,
        available_reports: list[dict] | None = None,
        selection_cache_key: str = "",
    ) -> None:
        super().__init__()
        self.token_store = token_store
        self.date_from = date_from
        self.date_to = date_to
        self.report_kind = report_kind
        self.settings = settings
        self.use_cache = use_cache
        self.load_mode = load_mode
        self.resume_checkpoint = resume_checkpoint
        self.selected_reports = selected_reports
        self.available_reports = available_reports
        self.selection_cache_key = selection_cache_key
        self._cancelled = False

    @Slot()
    def run(self) -> None:
        try:
            service = AutoReportService(
                self.token_store,
                status_callback=self.status_changed.emit,
                progress_callback=self._on_progress,
                cancel_callback=self.is_cancelled,
            )
            result = service.build_report(
                self.date_from,
                self.date_to,
                self.report_kind,
                self.settings,
                use_cache=self.use_cache,
                load_mode=self.load_mode,
                resume_checkpoint=self.resume_checkpoint,
                selected_reports=self.selected_reports,
                available_reports=self.available_reports,
                selection_cache_key=self.selection_cache_key,
            )
            if self.is_cancelled():
                self.cancelled.emit()
                return
            self.finished.emit(result)
        except LoadingCancelled:
            self.cancelled.emit()
        except Exception as exc:
            LOGGER.exception("Auto report worker failed")
            self.failed.emit(str(exc))

    def cancel(self) -> None:
        self._cancelled = True

    def is_cancelled(self) -> bool:
        return self._cancelled

    def _on_progress(self, progress: LoadProgress) -> None:
        if progress.stage:
            self.stage_changed.emit(progress.stage)
        if progress.status:
            self.status_changed.emit(progress.status)
        if progress.rows_loaded is not None:
            self.rows_loaded_changed.emit(progress.rows_loaded)
        if progress.progress is not None:
            self.progress_changed.emit(progress.progress)
        if progress.wait_seconds is not None:
            self.wait_timer_changed.emit(progress.wait_seconds)


class ExcelSaveWorker(QObject):
    finished = Signal(str)
    failed = Signal(str)

    def __init__(self, result: WBFinanceResult, path: Path) -> None:
        super().__init__()
        self.result = result
        self.path = path

    @Slot()
    def run(self) -> None:
        try:
            ExcelExporter().export(self.result, self.path)
            self.finished.emit(str(self.path))
        except PermissionError:
            LOGGER.exception("Excel export failed: file is locked")
            self.failed.emit("Файл занят другой программой.")
        except Exception as exc:
            LOGGER.exception("Excel export failed")
            self.failed.emit(str(exc))


class AutoReportPage(QWidget):
    def __init__(self, settings_store: SettingsStore, parent=None) -> None:
        super().__init__(parent)
        self.settings_store = settings_store
        self.token_store = TokenStore()
        self.service = AutoReportService(self.token_store, status_callback=self._set_status_message)
        self.exporter = ExcelExporter()
        self.result: WBFinanceResult | None = None
        self.status_message = ""
        self.current_stage = "-"
        self.rows_loaded = 0
        self._loading = False
        self._saving = False
        self._load_started_at: float | None = None
        self._worker: AutoReportWorker | None = None
        self._thread: QThread | None = None
        self._network_worker: NetworkCheckWorker | None = None
        self._network_thread: QThread | None = None
        self._save_worker: ExcelSaveWorker | None = None
        self._save_thread: QThread | None = None
        self.elapsed_timer = QTimer(self)
        self.elapsed_timer.timeout.connect(self._update_elapsed_time)
        self.network_timer = QTimer(self)
        self.network_timer.timeout.connect(self._start_network_check)
        self.save_pulse_timer = QTimer(self)
        self.save_pulse_timer.timeout.connect(self._pulse_save_progress)
        self._save_pulse_value = 0
        self._save_pulse_direction = 1
        self.models: dict[str, DataFrameTableModel] = {}
        self.cards: dict[str, MetricCard] = {}
        self.card_value_keys: dict[str, str] = {}
        today = date.today()
        self.period_selection = PeriodSelection(
            mode="manual",
            date_from=today - timedelta(days=7),
            date_to=today,
            report_kind=self.settings_store.load().api.last_report_kind,
        )
        self._build_ui()
        self.network_timer.start(30000)
        QTimer.singleShot(500, self._start_network_check)
        self._refresh_status()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        controls = QGridLayout()
        controls.setHorizontalSpacing(10)
        controls.setVerticalSpacing(8)
        self.period_button = QPushButton("Задать период")
        self._set_button_icon(self.period_button, QStyle.SP_FileDialogContentsView)
        self.period_button.clicked.connect(self.open_period_selection)
        self.period_label = QLabel(self.period_selection.label)
        self.period_label.setWordWrap(False)
        self.period_label.setMinimumWidth(290)
        self.period_label.setMaximumWidth(460)
        self.period_label.setStyleSheet("color: #334155;")
        self.load_mode = QComboBox()
        self.load_mode.addItem("Полный отчёт", "full")
        self.load_mode.addItem("Быстрая сводка", "summary")
        self.ad_source = QComboBox()
        self.ad_source.addItem("Не учитывать", "none")
        self.ad_source.addItem("WB Promotion API", "api")
        self.ad_source.addItem("Ввести вручную", "manual")
        self.ad_source.addItem("Реклама уже в удержаниях", "included")
        self.use_cache_checkbox = QCheckBox("Кэш")
        self.use_cache_checkbox.setChecked(True)

        self.fetch_button = QPushButton("Загрузить отчёт")
        self.fetch_button.setObjectName("PrimaryButton")
        self.fetch_button.setMinimumWidth(150)
        self._set_button_icon(self.fetch_button, QStyle.SP_BrowserReload)
        self.fetch_button.clicked.connect(self.build_report)

        controls.addWidget(self.period_button, 0, 0)
        controls.addWidget(self.period_label, 0, 1)
        controls.addWidget(QLabel("Режим загрузки"), 0, 2)
        controls.addWidget(self.load_mode, 0, 3)
        controls.addWidget(QLabel("Источник рекламы"), 0, 4)
        controls.addWidget(self.ad_source, 0, 5)
        controls.addWidget(self.use_cache_checkbox, 0, 6)
        controls.addWidget(self.fetch_button, 0, 7)
        controls.setColumnMinimumWidth(2, 96)
        controls.setColumnStretch(1, 2)
        controls.setColumnStretch(3, 1)
        controls.setColumnStretch(5, 1)
        controls.setColumnStretch(7, 1)
        layout.addLayout(controls)

        toolbar = QHBoxLayout()
        self.recalculate_button = QPushButton("Обновить расчет")
        self._set_button_icon(self.recalculate_button, QStyle.SP_BrowserReload)
        self.recalculate_button.setEnabled(False)
        self.recalculate_button.clicked.connect(self.recalculate_report)
        self.save_button = QPushButton("Сохранить Excel")
        self._set_button_icon(self.save_button, QStyle.SP_DialogSaveButton)
        self.save_button.setEnabled(False)
        self.save_button.clicked.connect(self.save_excel)
        settings_button = QPushButton("API Wildberries")
        self._set_button_icon(settings_button, QStyle.SP_FileDialogDetailedView)
        settings_button.clicked.connect(self.open_api_settings)
        tax_button = QPushButton("Настроить налоги")
        self._set_button_icon(tax_button, QStyle.SP_FileDialogInfoView)
        tax_button.clicked.connect(self.open_tax_settings)
        expenses_button = QPushButton("Расходы периода")
        self._set_button_icon(expenses_button, QStyle.SP_DriveHDIcon)
        expenses_button.clicked.connect(self.open_period_expenses)
        toolbar.addWidget(self.recalculate_button)
        toolbar.addWidget(self.save_button)
        self.cancel_button = QPushButton("Отмена")
        self._set_button_icon(self.cancel_button, QStyle.SP_DialogCancelButton)
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self.cancel_loading)
        toolbar.addWidget(self.cancel_button)
        toolbar.addWidget(settings_button)
        toolbar.addWidget(tax_button)
        toolbar.addWidget(expenses_button)
        toolbar.addStretch(1)
        layout.addLayout(toolbar)

        cards_layout = QGridLayout()
        card_specs = [
            ("К перечислению за товар", "К перечислению за товар"),
            ("Тип -- Основной", "Основной — Итого к оплате WB"),
            ("Тип -- По выкупам", "По выкупам — Итого к оплате WB"),
            ("Итого к оплате", "Итого к оплате WB"),
            ("Реклама WB", "Реклама WB"),
            ("УСН", "УСН"),
            ("НДС", "НДС"),
            ("Внешние расходы", "Внешние расходы"),
            ("Продано товаров", "Продано товаров"),
            ("Себестоимость", "Себестоимость"),
            ("Чистая прибыль", "Чистая прибыль"),
            ("Маржинальность %", "Маржинальность %"),
        ]
        for index, (title, value_key) in enumerate(card_specs):
            card = MetricCard(title)
            self.cards[title] = card
            self.card_value_keys[title] = value_key
            cards_layout.addWidget(card, index // 4, index % 4)
        layout.addLayout(cards_layout)

        self.tabs = QTabWidget()
        for name in ["Обозначения", "Общая сводка", "Управленческая прибыль", "Продажи", "Возвраты", "Товары", "Прибыль по товарам", "Реклама WB", "Внешние расходы", "Налоги", "Предупреждения", "Настройки отчёта"]:
            table = QTableView()
            table.setAlternatingRowColors(True)
            model = DataFrameTableModel()
            table.setModel(model)
            self.models[name] = model
            self.tabs.addTab(table, name)
        layout.addWidget(self.tabs, 1)

        status_layout = QVBoxLayout()
        status_layout.setSpacing(4)
        status_chips = QHBoxLayout()
        status_chips.setSpacing(6)
        self.status_chips: dict[str, QLabel] = {}
        for key in ["finance", "promotion", "last_load", "stage", "elapsed", "rows", "warnings", "status"]:
            chip = QLabel()
            chip.setObjectName("StatusChip")
            chip.setWordWrap(False)
            self.status_chips[key] = chip
            status_chips.addWidget(chip)
        status_chips.addStretch(1)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.network_indicator = QFrame()
        self.network_indicator.setObjectName("NetworkIndicator")
        self.network_indicator.setFixedSize(12, 12)
        self._set_network_indicator(None, "Проверка сети...")
        status_chips.addWidget(self.network_indicator, alignment=Qt.AlignVCenter)
        status_layout.addLayout(status_chips)
        status_layout.addWidget(self.progress_bar)
        layout.addLayout(status_layout)

    def _set_button_icon(self, button: QPushButton, icon: QStyle.StandardPixmap) -> None:
        button.setIcon(self.style().standardIcon(icon))
        button.setIconSize(QSize(16, 16))

    def _start_network_check(self) -> None:
        if self._network_thread and self._network_thread.isRunning():
            return
        self._set_network_indicator(None, "Проверка сети...")
        self._network_thread = QThread(self)
        self._network_worker = NetworkCheckWorker()
        self._network_worker.moveToThread(self._network_thread)
        self._network_thread.started.connect(self._network_worker.run)
        self._network_worker.finished.connect(self._on_network_checked)
        self._network_worker.finished.connect(self._network_thread.quit)
        self._network_thread.finished.connect(self._network_worker.deleteLater)
        self._network_thread.finished.connect(self._network_thread.deleteLater)
        self._network_thread.finished.connect(self._clear_network_refs)
        self._network_thread.start()

    def _on_network_checked(self, online: bool, message: str) -> None:
        self._set_network_indicator(online, message)

    def _set_network_indicator(self, online: bool | None, tooltip: str) -> None:
        if online is None:
            color = "#94a3b8"
        elif online:
            color = "#16a34a"
        else:
            color = "#dc2626"
        self.network_indicator.setStyleSheet(
            f"QFrame#NetworkIndicator {{ background: {color}; border-radius: 6px; border: 1px solid rgba(15, 23, 42, 0.18); }}"
        )
        self.network_indicator.setToolTip(tooltip)

    def _clear_network_refs(self) -> None:
        self._network_worker = None
        self._network_thread = None

    def _refresh_status(self) -> None:
        finance = "OK" if self.token_store.finance_token() else "не задан"
        promotion = "OK" if self.token_store.promotion_token() else "не задан"
        rows = self.rows_loaded if self._loading else (len(self.result.operations) if self.result else 0)
        warnings = len(self.result.warnings) if self.result else 0
        last_load = self.result.generated_at.strftime("%d.%m.%Y %H:%M:%S") if self.result else "-"
        self._set_chip("finance", f"Finance: {finance}")
        self._set_chip("promotion", f"Promotion: {promotion}")
        self._set_chip("last_load", f"Последняя: {last_load}")
        self._set_chip("stage", f"Этап: {self.current_stage}")
        self._set_chip("elapsed", self.elapsed_label_text())
        self._set_chip("rows", f"Строк: {rows}")
        self._set_chip("warnings", f"Предупр.: {warnings}", warning=warnings > 0)
        self._set_chip("status", f"Статус: {self.status_message or '-'}")

    def _set_chip(self, key: str, text: str, warning: bool = False) -> None:
        chip = self.status_chips.get(key)
        if not chip:
            return
        chip.setText(text)
        chip.setProperty("warning", warning)
        chip.style().unpolish(chip)
        chip.style().polish(chip)

    def _set_status_message(self, message: str) -> None:
        self.status_message = message
        self._refresh_status()
        if not self._loading:
            QApplication.processEvents()

    def build_report(self) -> None:
        if self._loading:
            return
        settings = self._current_settings()
        if not self.token_store.finance_token():
            QMessageBox.warning(self, "Finance API token не задан", "Откройте настройки API Wildberries и сохраните Finance API token.")
            self.open_api_settings()
            return
        selection = self.period_selection
        start = selection.effective_date_from
        end = selection.effective_date_to
        report_kind = selection.effective_report_kind
        load_mode = self.load_mode.currentData()
        use_cache = self.use_cache_checkbox.isChecked()
        cache_key = selection.cache_key
        if not use_cache:
            proceed = QMessageBox.warning(
                self,
                "Загрузка без кэша",
                "Кэш отключен. Загрузка может занять больше времени и повторно обратиться к WB API. Продолжить?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if proceed != QMessageBox.Yes:
                return
        resume_checkpoint = False
        if not use_cache and load_mode == "full" and self.service.has_checkpoint():
            resume_checkpoint = QMessageBox.question(
                self,
                "Незавершённая загрузка",
                "Найдена незавершённая загрузка. Продолжить?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes,
            ) == QMessageBox.Yes
            if not resume_checkpoint:
                self.service.clear_checkpoints()
        self._start_worker(
            start,
            end,
            report_kind,
            settings,
            use_cache,
            load_mode,
            resume_checkpoint,
            selected_reports=selection.selected_reports if selection.is_wb_periods else None,
            available_reports=selection.available_reports if selection.is_wb_periods else None,
            selection_cache_key=cache_key,
        )

    def open_period_selection(self) -> None:
        dialog = PeriodSelectionDialog(self.token_store, self.period_selection, self)
        if dialog.exec():
            self.period_selection = dialog.selection()
            self.period_label.setText(self.period_selection.label)
            self._refresh_status()

    def _ask_cache_choice(self) -> bool:
        box = QMessageBox(self)
        box.setWindowTitle("Кэш автоотчета")
        box.setText("Данные за этот период уже загружены. Использовать кэш или обновить из WB?")
        cache_button = box.addButton("Использовать кэш", QMessageBox.AcceptRole)
        refresh_button = box.addButton("Обновить из WB", QMessageBox.DestructiveRole)
        box.setDefaultButton(cache_button)
        box.exec()
        return box.clickedButton() != refresh_button

    def _start_worker(
        self,
        start: date,
        end: date,
        report_kind: str,
        settings,
        use_cache: bool,
        load_mode: str,
        resume_checkpoint: bool,
        selected_reports: list[dict] | None = None,
        available_reports: list[dict] | None = None,
        selection_cache_key: str = "",
    ) -> None:
        self._loading = True
        self.rows_loaded = 0
        self.current_stage = "Проверка наличия кэша"
        self._load_started_at = time.monotonic()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setValue(0)
        self._set_status_message("WB Finance API: загрузка началась...")
        self._set_loading_buttons(True)
        self.elapsed_timer.start(1000)

        self._thread = QThread(self)
        self._worker = AutoReportWorker(
            self.token_store,
            start,
            end,
            report_kind,
            settings,
            use_cache,
            load_mode,
            resume_checkpoint,
            selected_reports=selected_reports,
            available_reports=available_reports,
            selection_cache_key=selection_cache_key,
        )
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.progress_changed.connect(self._on_progress_changed)
        self._worker.status_changed.connect(self._set_status_message)
        self._worker.rows_loaded_changed.connect(self._on_rows_loaded_changed)
        self._worker.wait_timer_changed.connect(self._on_wait_timer_changed)
        self._worker.stage_changed.connect(self._on_stage_changed)
        self._worker.finished.connect(self._on_worker_finished)
        self._worker.failed.connect(self._on_worker_failed)
        self._worker.cancelled.connect(self._on_worker_cancelled)
        self._worker.finished.connect(self._thread.quit)
        self._worker.failed.connect(self._thread.quit)
        self._worker.cancelled.connect(self._thread.quit)
        self._thread.finished.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.finished.connect(self._clear_worker_refs)
        self._thread.start()

    def cancel_loading(self) -> None:
        if self._worker:
            self._worker.cancel()
            self._set_status_message("Отмена загрузки...")

    def shutdown(self) -> None:
        self.network_timer.stop()
        if self._worker:
            self._worker.cancel()
        if self._thread and self._thread.isRunning():
            self._thread.quit()
            self._thread.wait(3000)
        if self._network_thread and self._network_thread.isRunning():
            self._network_thread.quit()
            if not self._network_thread.wait(2500):
                self._network_thread.terminate()
                self._network_thread.wait(500)
        if self._save_thread and self._save_thread.isRunning():
            self._save_thread.quit()
            self._save_thread.wait(3000)

    def _on_worker_finished(self, result: WBFinanceResult) -> None:
        self.result = result
        self.status_message = "Загрузка завершена"
        self.current_stage = "Готово"
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(100)
        self._finish_loading()
        self._show_result()

    def _on_worker_failed(self, message: str) -> None:
        self.status_message = "Ошибка загрузки"
        self.current_stage = "Ошибка"
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self._finish_loading()
        LOGGER.error("Auto report failed: %s", message)
        QMessageBox.critical(self, "Не удалось получить финансовый отчет", message)

    def _on_worker_cancelled(self) -> None:
        self.status_message = "Загрузка отменена"
        self.current_stage = "Отменено"
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self._finish_loading()
        self._refresh_status()

    def _on_progress_changed(self, value: int) -> None:
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(max(0, min(value, 100)))

    def _on_stage_changed(self, stage: str) -> None:
        self.current_stage = stage
        self._refresh_status()

    def _on_rows_loaded_changed(self, rows: int) -> None:
        self.rows_loaded = rows
        self._refresh_status()

    def _on_wait_timer_changed(self, seconds: int) -> None:
        self.status_message = f"WB Finance API: лимит запросов, ожидание {seconds} секунд..."
        self._refresh_status()

    def _update_elapsed_time(self) -> None:
        self._refresh_status()

    def elapsed_label_text(self) -> str:
        if self._load_started_at is None:
            return "Прошло: 00:00"
        elapsed = int(time.monotonic() - self._load_started_at)
        minutes, seconds = divmod(elapsed, 60)
        hours, minutes = divmod(minutes, 60)
        if hours:
            text = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        else:
            text = f"{minutes:02d}:{seconds:02d}"
        return f"Прошло: {text}"

    def _finish_loading(self) -> None:
        self.elapsed_timer.stop()
        self._update_elapsed_time()
        self._loading = False
        self._set_loading_buttons(False)
        self._refresh_status()

    def _set_loading_buttons(self, loading: bool) -> None:
        busy = loading or self._saving
        self.fetch_button.setEnabled(not busy)
        self.period_button.setEnabled(not busy)
        self.use_cache_checkbox.setEnabled(not busy)
        self.save_button.setEnabled((not busy) and self.result is not None)
        self.recalculate_button.setEnabled((not busy) and self.result is not None and not self.result.operations.empty)
        self.cancel_button.setEnabled(loading)

    def _start_saving(self, path: Path) -> None:
        if not self.result or self._saving:
            return
        self._saving = True
        self._save_pulse_value = 0
        self._save_pulse_direction = 1
        self.current_stage = "Сохранение Excel"
        self._load_started_at = time.monotonic()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self._set_status_message("Сохранение Excel...")
        self._set_loading_buttons(False)
        self.elapsed_timer.start(1000)
        self.save_pulse_timer.start(80)
        QApplication.setOverrideCursor(Qt.WaitCursor)

        self._save_thread = QThread(self)
        self._save_worker = ExcelSaveWorker(self.result, path)
        self._save_worker.moveToThread(self._save_thread)
        self._save_thread.started.connect(self._save_worker.run)
        self._save_worker.finished.connect(self._on_save_finished)
        self._save_worker.failed.connect(self._on_save_failed)
        self._save_worker.finished.connect(self._save_thread.quit)
        self._save_worker.failed.connect(self._save_thread.quit)
        self._save_thread.finished.connect(self._save_worker.deleteLater)
        self._save_thread.finished.connect(self._save_thread.deleteLater)
        self._save_thread.finished.connect(self._clear_save_refs)
        self._save_thread.start()
        QApplication.processEvents()

    def _finish_saving(self, progress_value: int) -> None:
        self.elapsed_timer.stop()
        self.save_pulse_timer.stop()
        self._update_elapsed_time()
        self._saving = False
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(progress_value)
        self._set_loading_buttons(False)
        self._refresh_status()
        if QApplication.overrideCursor() is not None:
            QApplication.restoreOverrideCursor()

    def _pulse_save_progress(self) -> None:
        if not self._saving:
            return
        self._save_pulse_value += self._save_pulse_direction * 4
        if self._save_pulse_value >= 96:
            self._save_pulse_value = 96
            self._save_pulse_direction = -1
        elif self._save_pulse_value <= 4:
            self._save_pulse_value = 4
            self._save_pulse_direction = 1
        self.progress_bar.setValue(self._save_pulse_value)
        self.status_message = "Сохранение Excel..."
        self._refresh_status()

    def _on_save_finished(self, path: str) -> None:
        self.status_message = "Excel сохранен"
        self.current_stage = "Готово"
        self._finish_saving(100)
        QMessageBox.information(self, "Готово", f"Отчет сохранен:\n{path}")

    def _on_save_failed(self, message: str) -> None:
        self.status_message = "Ошибка сохранения Excel"
        self.current_stage = "Ошибка"
        self._finish_saving(0)
        QMessageBox.critical(self, "Не удалось сохранить Excel", message)

    def _clear_save_refs(self) -> None:
        self._save_worker = None
        self._save_thread = None

    def _clear_worker_refs(self) -> None:
        self._worker = None
        self._thread = None

    def recalculate_report(self) -> None:
        if not self.result or self.result.operations.empty:
            QMessageBox.information(self, "Обновить расчет", "Сначала получите данные из WB.")
            return
        settings = self._current_settings()
        start = self.period_selection.effective_date_from
        end = self.period_selection.effective_date_to
        report_kind = self.period_selection.effective_report_kind
        self.fetch_button.setEnabled(False)
        self.recalculate_button.setEnabled(False)
        self._set_status_message("Пересчет отчета без загрузки из WB...")
        try:
            self.result = self.service.recalculate_report(self.result, start, end, report_kind, settings)
            self.status_message = "Расчет обновлен без загрузки из WB"
            self._show_result()
        except Exception as exc:
            LOGGER.exception("Auto report recalculation failed")
            QMessageBox.critical(self, "Не удалось обновить расчет", str(exc))
        finally:
            self.fetch_button.setEnabled(True)
            self.recalculate_button.setEnabled(self.result is not None and not self.result.operations.empty)
            self._refresh_status()

    def _show_result(self) -> None:
        if not self.result:
            return
        tax_mode = self.settings_store.load().api.tax_settings.mode
        for name, model in self.models.items():
            model.set_dataframe(self.result.table_by_name(name))
        for name, card in self.cards.items():
            value_key = self.card_value_keys.get(name, name)
            if name == "УСН" and tax_mode == "manual":
                card.title_label.setText("Ручная сумма")
                value_key = "Ручная сумма"
            elif name == "УСН":
                card.title_label.setText("УСН")
                value_key = "УСН"
            card.set_value(self.result.total(value_key), percent=value_key.endswith("%"))
        self.recalculate_button.setEnabled((not self._saving) and not self.result.operations.empty)
        self.save_button.setEnabled(not self._saving)

    def _current_settings(self):
        settings = self.settings_store.load()
        settings.api.ad_source = self.ad_source.currentData()
        settings.api.last_report_kind = self.period_selection.effective_report_kind
        self.settings_store.save(settings)
        return settings

    def save_excel(self) -> None:
        if not self.result:
            QMessageBox.information(self, "Сохранить Excel", "Сначала получите данные из WB.")
            return
        default = self.exporter.default_path(EXPORT_DIR, self.result)
        path, _ = QFileDialog.getSaveFileName(self, "Сохранить автоотчет", str(default), "Excel (*.xlsx)")
        if path:
            self._start_saving(Path(path))

    def open_api_settings(self) -> None:
        SettingsDialog(self.settings_store.load(), self).exec()
        self._refresh_status()

    def open_tax_settings(self) -> None:
        settings = self.settings_store.load()
        dialog = TaxSettingsDialog(settings.api.tax_settings, self)
        if dialog.exec():
            settings.api.tax_settings = dialog.tax_settings()
            self.settings_store.save(settings)

    def open_period_expenses(self) -> None:
        settings = self.settings_store.load()
        dialog = PeriodExpensesDialog(settings.external_expenses, settings.api.business_expenses_template, self)
        if dialog.exec():
            settings.external_expenses = dialog.expenses()
            settings.api.business_expenses_template = dialog.expenses_template()
            self.settings_store.save(settings)

    def _date(self, qdate: QDate) -> date:
        return date(qdate.year(), qdate.month(), qdate.day())
