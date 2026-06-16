from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QObject, QThread, Qt, Signal, Slot
from PySide6.QtGui import QCloseEvent, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
)

from wb_finance_analyst.config.defaults import APP_ICON_PATH, LOG_DIR
from wb_finance_analyst.services.update_checker import UpdateInfo, check_for_updates
from wb_finance_analyst.version import APP_VERSION, DOWNLOAD_PAGE_URL, LATEST_VERSION_URL, SUPPORT_EMAIL


class UpdateCheckWorker(QObject):
    finished = Signal(object)
    failed = Signal(str)

    @Slot()
    def run(self) -> None:
        try:
            self.finished.emit(check_for_updates())
        except Exception as exc:  # pragma: no cover - covered by UI smoke manually
            self.failed.emit(str(exc))


class AboutDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._update_thread: QThread | None = None
        self._update_worker: UpdateCheckWorker | None = None
        self.setWindowTitle("О программе")
        self.setMinimumWidth(620)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(14)

        header = QFrame()
        header.setObjectName("BrandFrame")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(16, 16, 16, 16)
        header_layout.setSpacing(14)

        logo = QLabel()
        logo.setPixmap(QPixmap(str(APP_ICON_PATH)).scaled(64, 64, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        logo.setFixedSize(64, 64)
        header_layout.addWidget(logo)

        title_box = QVBoxLayout()
        title = QLabel("WB analyst")
        title.setObjectName("PageTitle")
        version = QLabel(f"Версия: {APP_VERSION}")
        version.setObjectName("MutedText")
        title_box.addWidget(title)
        title_box.addWidget(version)
        header_layout.addLayout(title_box, 1)
        layout.addWidget(header)

        description = QTextBrowser()
        description.setOpenExternalLinks(True)
        description.setMinimumHeight(185)
        description.setHtml(
            f"""
            <p><b>WB analyst</b> помогает селлерам Wildberries загружать финансовые отчеты,
            сверять суммы с WB, считать себестоимость, рекламу, налоги, внешние расходы
            и формировать управленческий Excel.</p>
            <p><b>Скачивание и обновления:</b><br>
            <a href="{DOWNLOAD_PAGE_URL}">{DOWNLOAD_PAGE_URL}</a></p>
            <p><b>Безопасность:</b> API-токены хранятся локально на компьютере пользователя
            и не записываются в логи приложения.</p>
            <p><b>Поддержка:</b> <a href="mailto:{SUPPORT_EMAIL}">{SUPPORT_EMAIL}</a></p>
            """
        )
        layout.addWidget(description)

        self.update_status = QLabel(
            f'Проверка обновлений идет через <a href="{LATEST_VERSION_URL}">latest.json</a> и не использует WB API.'
        )
        self.update_status.setObjectName("MutedText")
        self.update_status.setTextFormat(Qt.RichText)
        self.update_status.setOpenExternalLinks(True)
        self.update_status.setWordWrap(True)
        layout.addWidget(self.update_status)

        info = QLabel(f"Файл логов: {LOG_DIR / 'app.log'}")
        info.setObjectName("MutedText")
        info.setWordWrap(True)
        layout.addWidget(info)

        buttons = QDialogButtonBox()
        self.check_update_button = QPushButton("Проверить обновление")
        self.check_update_button.clicked.connect(self.check_update)
        copy_button = QPushButton("Скопировать сведения")
        copy_button.clicked.connect(self.copy_details)
        close_button = buttons.addButton("Закрыть", QDialogButtonBox.RejectRole)
        close_button.clicked.connect(self.reject)
        buttons.addButton(self.check_update_button, QDialogButtonBox.ActionRole)
        buttons.addButton(copy_button, QDialogButtonBox.ActionRole)
        layout.addWidget(buttons)

    def check_update(self) -> None:
        if self._update_thread is not None and self._update_thread.isRunning():
            return

        self.check_update_button.setEnabled(False)
        self.update_status.setText("Проверяю обновление...")

        self._update_thread = QThread(self)
        self._update_worker = UpdateCheckWorker()
        self._update_worker.moveToThread(self._update_thread)

        self._update_thread.started.connect(self._update_worker.run)
        self._update_worker.finished.connect(self._on_update_checked)
        self._update_worker.failed.connect(self._on_update_failed)
        self._update_worker.finished.connect(self._update_thread.quit)
        self._update_worker.failed.connect(self._update_thread.quit)
        self._update_thread.finished.connect(self._update_worker.deleteLater)
        self._update_thread.finished.connect(self._update_thread.deleteLater)
        self._update_thread.finished.connect(self._clear_update_refs)
        self._update_thread.start()

    @Slot(object)
    def _on_update_checked(self, info: UpdateInfo) -> None:
        self.check_update_button.setEnabled(True)
        if info.update_available:
            download_url = info.download_url or DOWNLOAD_PAGE_URL
            notes_url = info.notes_url or DOWNLOAD_PAGE_URL
            self.update_status.setText(
                "Доступна новая версия: "
                f"<b>{info.latest_version}</b>. "
                f'<a href="{download_url}">Скачать</a> | '
                f'<a href="{notes_url}">Описание релиза</a>'
            )
            return

        self.update_status.setText(
            f"Установлена актуальная версия. Текущая: {info.current_version}, последняя: {info.latest_version}."
        )

    @Slot(str)
    def _on_update_failed(self, message: str) -> None:
        self.check_update_button.setEnabled(True)
        self.update_status.setText(f"Не удалось проверить обновление: {message}")

    @Slot()
    def _clear_update_refs(self) -> None:
        self._update_thread = None
        self._update_worker = None

    def copy_details(self) -> None:
        details = "\n".join(
            [
                "WB analyst",
                f"Версия: {APP_VERSION}",
                f"Файл логов: {LOG_DIR / 'app.log'}",
                f"Страница скачивания: {DOWNLOAD_PAGE_URL}",
                f"Проверка обновлений: {LATEST_VERSION_URL}",
                f"Поддержка: {SUPPORT_EMAIL}",
                f"Дата/время: {datetime.now().isoformat(timespec='seconds')}",
            ]
        )
        QApplication.clipboard().setText(details)
        QMessageBox.information(self, "О программе", "Сведения скопированы в буфер обмена.")

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._update_thread is not None and self._update_thread.isRunning():
            self._update_thread.quit()
            if not self._update_thread.wait(2500):
                self._update_thread.terminate()
                self._update_thread.wait(1000)
        super().closeEvent(event)
