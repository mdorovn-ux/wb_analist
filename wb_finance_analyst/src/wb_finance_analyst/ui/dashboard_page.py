from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget


class DashboardPage(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        title = QLabel("WB analyst")
        title.setStyleSheet("font-size: 22pt; font-weight: 700;")
        layout.addWidget(title)
        layout.addWidget(QLabel("Выберите раздел слева, чтобы сформировать новый отчет, объединить готовые файлы или настроить себестоимость."))
        layout.addStretch(1)
