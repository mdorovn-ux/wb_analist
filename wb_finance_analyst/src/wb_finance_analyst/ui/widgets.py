from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget


class MetricCard(QFrame):
    def __init__(self, title: str, value: str = "0,00") -> None:
        super().__init__()
        self.setObjectName("MetricCard")
        layout = QVBoxLayout(self)
        self.title_label = QLabel(title)
        self.title_label.setObjectName("MetricTitle")
        self.value_label = QLabel(value)
        self.value_label.setObjectName("MetricValue")
        layout.addWidget(self.title_label)
        layout.addWidget(self.value_label)

    def set_value(self, value: float, percent: bool = False) -> None:
        if percent:
            text = f"{value * 100:.2f}%"
        else:
            text = f"{value:,.2f}".replace(",", " ")
        self.value_label.setText(text)


class Toolbar(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(8)
        self.layout.addStretch(1)

    def add_button(self, text: str) -> QPushButton:
        button = QPushButton(text)
        index = max(self.layout.count() - 1, 0)
        self.layout.insertWidget(index, button)
        return button


class DropHint(QFrame):
    def __init__(self, text: str) -> None:
        super().__init__()
        self.setObjectName("DropHint")
        layout = QVBoxLayout(self)
        label = QLabel(text)
        label.setAlignment(Qt.AlignCenter)
        layout.addWidget(label)
