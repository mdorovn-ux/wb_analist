from __future__ import annotations

from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QMainWindow, QPushButton, QStackedWidget, QVBoxLayout, QWidget

from wb_finance_analyst.config.defaults import APP_ICON_PATH
from wb_finance_analyst.config.settings import SettingsStore
from wb_finance_analyst.ui.auto_report_page import AutoReportPage
from wb_finance_analyst.ui.costs_page import CostsPage
from wb_finance_analyst.ui.dashboard_page import DashboardPage
from wb_finance_analyst.ui.instruction_page import InstructionPage
from wb_finance_analyst.ui.logs_page import LogsPage
from wb_finance_analyst.ui.merge_reports_page import MergeReportsPage
from wb_finance_analyst.ui.new_report_page import NewReportPage
from wb_finance_analyst.ui.settings_dialog import SettingsDialog
from wb_finance_analyst.version import APP_VERSION


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"WB analyst {APP_VERSION}")
        self.setWindowIcon(QIcon(str(APP_ICON_PATH)))
        self.setMinimumSize(1400, 900)
        self.settings_store = SettingsStore()
        self.nav_buttons: list[QPushButton] = []
        self.nav_button_pages: list[int] = []
        self._pages: list[QWidget | None] = []
        self._visible_page_indexes = {1, 4, 5, 6}
        self._page_factories = [
            lambda: DashboardPage(),
            lambda: AutoReportPage(self.settings_store),
            lambda: NewReportPage(self.settings_store),
            lambda: MergeReportsPage(),
            lambda: CostsPage(),
            lambda: InstructionPage(),
            lambda: LogsPage(),
        ]
        self._build_ui()

    def _build_ui(self) -> None:
        root = QWidget()
        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(250)
        side_layout = QVBoxLayout(sidebar)
        brand_frame = QFrame()
        brand_frame.setObjectName("BrandFrame")
        brand_layout = QHBoxLayout(brand_frame)
        brand_layout.setContentsMargins(12, 14, 12, 14)
        brand_layout.setSpacing(10)
        logo = QLabel()
        logo.setPixmap(QPixmap(str(APP_ICON_PATH)).scaled(52, 52))
        logo.setFixedSize(52, 52)
        brand = QLabel("WB\nAnalyst")
        brand.setObjectName("BrandTitle")
        brand_layout.addWidget(logo)
        brand_layout.addWidget(brand, 1)
        side_layout.addWidget(brand_frame)

        self.stack = QStackedWidget()
        pages = ["Обзор", "Автоотчет", "Новый отчет", "Объединение отчетов", "Себестоимость товаров", "Инструкция", "Логи"]
        support_buttons: list[QPushButton] = []
        for index, title in enumerate(pages):
            button = QPushButton(title)
            button.setObjectName("NavButton")
            button.setCheckable(True)
            button.clicked.connect(lambda checked=False, i=index: self._set_page(i))
            self.nav_buttons.append(button)
            self.nav_button_pages.append(index)
            button.setVisible(index in self._visible_page_indexes)
            if index in {5, 6}:
                support_buttons.append(button)
            else:
                side_layout.addWidget(button)
            placeholder = QWidget()
            self._pages.append(None)
            self.stack.addWidget(placeholder)
        settings_button = QPushButton("Настройки")
        settings_button.setObjectName("NavButton")
        settings_button.clicked.connect(self.open_settings)
        settings_button.setVisible(False)
        side_layout.addWidget(settings_button)
        side_layout.addStretch(1)
        for button in support_buttons:
            side_layout.addWidget(button)
        layout.addWidget(sidebar)
        layout.addWidget(self.stack, 1)
        self.setCentralWidget(root)
        self._set_page(1)

    def _set_page(self, index: int) -> None:
        if self._pages[index] is None:
            page = self._page_factories[index]()
            self._pages[index] = page
            old = self.stack.widget(index)
            self.stack.removeWidget(old)
            old.deleteLater()
            self.stack.insertWidget(index, page)
        self.stack.setCurrentIndex(index)
        for button, page_index in zip(self.nav_buttons, self.nav_button_pages):
            button.setChecked(page_index == index)

    def open_settings(self) -> None:
        SettingsDialog(self.settings_store.load(), self).exec()

    def closeEvent(self, event) -> None:
        for page in self._pages:
            shutdown = getattr(page, "shutdown", None)
            if callable(shutdown):
                shutdown()
        super().closeEvent(event)
