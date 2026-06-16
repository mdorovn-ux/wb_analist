from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
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
from wb_finance_analyst.version import APP_VERSION, DOWNLOAD_PAGE_URL


class AboutDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
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
            <p><b>Поддержка:</b> обратитесь к продавцу или разработчику, который выдал лицензию.</p>
            """
        )
        layout.addWidget(description)

        info = QLabel(f"Файл логов: {LOG_DIR / 'app.log'}")
        info.setObjectName("MutedText")
        info.setWordWrap(True)
        layout.addWidget(info)

        buttons = QDialogButtonBox()
        copy_button = QPushButton("Скопировать сведения")
        copy_button.clicked.connect(self.copy_details)
        close_button = buttons.addButton("Закрыть", QDialogButtonBox.RejectRole)
        close_button.clicked.connect(self.reject)
        buttons.addButton(copy_button, QDialogButtonBox.ActionRole)
        layout.addWidget(buttons)

    def copy_details(self) -> None:
        details = "\n".join(
            [
                "WB analyst",
                f"Версия: {APP_VERSION}",
                f"Файл логов: {LOG_DIR / 'app.log'}",
                f"Страница скачивания: {DOWNLOAD_PAGE_URL}",
                f"Дата/время: {datetime.now().isoformat(timespec='seconds')}",
            ]
        )
        QApplication.clipboard().setText(details)
        QMessageBox.information(self, "О программе", "Сведения скопированы в буфер обмена.")

