from __future__ import annotations

from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)

from wb_finance_analyst.services.license_manager import LicenseManager


class LicenseDialog(QDialog):
    def __init__(self, manager: LicenseManager, parent=None) -> None:
        super().__init__(parent)
        self.manager = manager
        self.state = manager.state()
        self.setWindowTitle("Активация WB analyst")
        self.setMinimumWidth(560)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        title = QLabel("Активация WB analyst")
        title.setObjectName("PageTitle")
        layout.addWidget(title)
        info = QLabel(
            "Для первого запуска отправьте код компьютера разработчику, получите активационный ключ и вставьте его ниже."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        layout.addWidget(QLabel("Код компьютера"))
        code_row = QHBoxLayout()
        self.installation_id = QLineEdit(self.state.installation_id)
        self.installation_id.setReadOnly(True)
        copy_button = QPushButton("Скопировать")
        copy_button.clicked.connect(self.copy_installation_id)
        code_row.addWidget(self.installation_id, 1)
        code_row.addWidget(copy_button)
        layout.addLayout(code_row)

        layout.addWidget(QLabel("Активационный ключ"))
        self.activation_key = QLineEdit()
        self.activation_key.setPlaceholderText("Введите ключ активации")
        layout.addWidget(self.activation_key)

        note = QTextEdit()
        note.setReadOnly(True)
        note.setFixedHeight(78)
        note.setPlainText(
            "Подсказка: ключ компьютера создается один раз для этой установки. "
            "Если переустановить программу или удалить настройки, код может измениться."
        )
        layout.addWidget(note)

        buttons = QDialogButtonBox()
        activate = buttons.addButton("Активировать", QDialogButtonBox.AcceptRole)
        cancel = buttons.addButton("Выйти", QDialogButtonBox.RejectRole)
        activate.clicked.connect(self.activate)
        cancel.clicked.connect(self.reject)
        layout.addWidget(buttons)

    def copy_installation_id(self) -> None:
        QApplication.clipboard().setText(self.state.installation_id)
        QMessageBox.information(self, "Активация", "Код компьютера скопирован.")

    def activate(self) -> None:
        if self.manager.activate(self.activation_key.text()):
            QMessageBox.information(self, "Активация", "Программа активирована.")
            self.accept()
            return
        QMessageBox.warning(self, "Активация", "Неверный активационный ключ.")
