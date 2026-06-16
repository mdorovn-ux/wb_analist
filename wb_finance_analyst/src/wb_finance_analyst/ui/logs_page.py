from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QDateTime
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QDateTimeEdit,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from wb_finance_analyst.config.defaults import LOG_DIR


class LogsPage(QWidget):
    LOG_TIME_RE = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})")

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.log_path = LOG_DIR / "app.log"
        self._build_ui()
        self.refresh_logs()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        title = QLabel("Логи")
        title.setObjectName("PageTitle")
        subtitle = QLabel(f"Файл логов: {self.log_path}")
        subtitle.setObjectName("MutedText")
        subtitle.setWordWrap(True)
        layout.addWidget(title)
        layout.addWidget(subtitle)

        controls = QHBoxLayout()
        self.date_from = QDateTimeEdit(QDateTime.currentDateTime().addDays(-1))
        self.date_from.setCalendarPopup(True)
        self.date_to = QDateTimeEdit(QDateTime.currentDateTime().addSecs(60))
        self.date_to.setCalendarPopup(True)
        self.copy_button = QPushButton("Скопировать")
        self.copy_button.clicked.connect(self.copy_logs)
        self.save_button = QPushButton("Сохранить")
        self.save_button.clicked.connect(self.save_logs)
        self.clear_button = QPushButton("Очистить логи")
        self.clear_button.clicked.connect(self.clear_logs)
        self.refresh_button = QPushButton("Обновить")
        self.refresh_button.clicked.connect(self.refresh_logs)
        controls.addWidget(QLabel("С"))
        controls.addWidget(self.date_from)
        controls.addWidget(QLabel("до"))
        controls.addWidget(self.date_to)
        controls.addWidget(self.refresh_button)
        controls.addStretch(1)
        controls.addWidget(self.copy_button)
        controls.addWidget(self.save_button)
        controls.addWidget(self.clear_button)
        layout.addLayout(controls)

        self.viewer = QPlainTextEdit()
        self.viewer.setReadOnly(True)
        self.viewer.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.viewer.setObjectName("LogViewer")
        layout.addWidget(self.viewer, 1)

    def refresh_logs(self) -> None:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        if not self.log_path.exists():
            self.viewer.setPlainText("Лог пока пуст. Файл появится после запуска и действий в программе.")
            return
        text = self.log_path.read_text(encoding="utf-8", errors="replace")
        self.viewer.setPlainText(self._filter_text(text))

    def copy_logs(self) -> None:
        QApplication.clipboard().setText(self.viewer.toPlainText())
        QMessageBox.information(self, "Логи", "Логи скопированы в буфер обмена.")

    def save_logs(self) -> None:
        default = Path.home() / "wb_finance_analyst_logs.txt"
        path, _ = QFileDialog.getSaveFileName(self, "Сохранить логи", str(default), "Text (*.txt)")
        if not path:
            return
        Path(path).write_text(self.viewer.toPlainText(), encoding="utf-8")
        QMessageBox.information(self, "Логи", f"Логи сохранены:\n{path}")

    def clear_logs(self) -> None:
        answer = QMessageBox.question(
            self,
            "Очистить логи",
            "Полностью очистить файл логов? Это действие нельзя отменить.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        self.log_path.write_text("", encoding="utf-8")
        self.viewer.setPlainText("")
        QMessageBox.information(self, "Логи", "Логи очищены.")

    def _filter_text(self, text: str) -> str:
        start = self._qdatetime_to_datetime(self.date_from.dateTime())
        end = self._qdatetime_to_datetime(self.date_to.dateTime())
        result: list[str] = []
        current_in_range = True
        for line in text.splitlines():
            parsed = self._line_time(line)
            if parsed is not None:
                current_in_range = start <= parsed <= end
            if current_in_range:
                result.append(line)
        return "\n".join(result)

    def _line_time(self, line: str) -> datetime | None:
        match = self.LOG_TIME_RE.match(line)
        if not match:
            return None
        try:
            return datetime.strptime(match.group(1), "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return None

    def _qdatetime_to_datetime(self, value: QDateTime) -> datetime:
        qdate = value.date()
        qtime = value.time()
        return datetime(qdate.year(), qdate.month(), qdate.day(), qtime.hour(), qtime.minute(), qtime.second())
