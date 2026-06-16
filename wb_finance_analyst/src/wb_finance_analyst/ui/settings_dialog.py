from __future__ import annotations

from datetime import date, timedelta

from PySide6.QtWidgets import QCheckBox, QDialog, QDialogButtonBox, QFormLayout, QLabel, QLineEdit, QMessageBox, QPushButton, QVBoxLayout

from wb_finance_analyst.config.settings import AppSettings, SettingsStore
from wb_finance_analyst.services.token_store import TokenStore
from wb_finance_analyst.services.wb_api_client import WBApiError
from wb_finance_analyst.services.wb_finance_api import WBFinanceAPI
from wb_finance_analyst.services.wb_promotion_api import WBPromotionAPI


class SettingsDialog(QDialog):
    def __init__(self, settings: AppSettings, parent=None) -> None:
        super().__init__(parent)
        self.settings = settings
        self.token_store = TokenStore()
        self.setWindowTitle("Настройки")
        self.resize(620, 420)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("API Wildberries"))
        form = QFormLayout()
        self.finance_token = QLineEdit()
        self.finance_token.setEchoMode(QLineEdit.Password)
        self.finance_token.setPlaceholderText(self.token_store.mask(self.token_store.finance_token()) or "Finance API token")
        self.promotion_token = QLineEdit()
        self.promotion_token.setEchoMode(QLineEdit.Password)
        self.promotion_token.setPlaceholderText(self.token_store.mask(self.token_store.promotion_token()) or "Promotion API token")
        self.use_api = QCheckBox("Использовать API по умолчанию")
        self.use_api.setChecked(settings.api.use_api_by_default)
        self.use_excel_fallback = QCheckBox("Использовать Excel как резерв")
        self.use_excel_fallback.setChecked(settings.api.use_excel_as_fallback)
        form.addRow("Finance API token", self.finance_token)
        form.addRow("Promotion API token", self.promotion_token)
        form.addRow("", self.use_api)
        form.addRow("", self.use_excel_fallback)
        layout.addLayout(form)

        if not self.token_store.available:
            layout.addWidget(QLabel("Предупреждение: keyring недоступен, токены будут храниться только в памяти текущего запуска."))

        check_finance = QPushButton("Проверить Finance API")
        check_finance.clicked.connect(self.check_finance)
        check_promotion = QPushButton("Проверить Promotion API")
        check_promotion.clicked.connect(self.check_promotion)
        save_tokens = QPushButton("Сохранить токены")
        save_tokens.clicked.connect(self.save_tokens)
        delete_tokens = QPushButton("Удалить токены")
        delete_tokens.clicked.connect(self.delete_tokens)
        layout.addWidget(check_finance)
        layout.addWidget(check_promotion)
        layout.addWidget(save_tokens)
        layout.addWidget(delete_tokens)
        layout.addWidget(QLabel("API-токены не записываются в settings.json и не экспортируются в Excel."))
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.save_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def save_tokens(self) -> None:
        if self.finance_token.text().strip():
            self.token_store.set_token(TokenStore.FINANCE_KEY, self.finance_token.text().strip())
            self.finance_token.clear()
        if self.promotion_token.text().strip():
            self.token_store.set_token(TokenStore.PROMOTION_KEY, self.promotion_token.text().strip())
            self.promotion_token.clear()
        QMessageBox.information(self, "Токены", "Токены сохранены.")

    def delete_tokens(self) -> None:
        self.token_store.delete_token(TokenStore.FINANCE_KEY)
        self.token_store.delete_token(TokenStore.PROMOTION_KEY)
        QMessageBox.information(self, "Токены", "Токены удалены.")

    def check_finance(self) -> None:
        token = self.finance_token.text().strip() or self.token_store.finance_token()
        if not token:
            QMessageBox.warning(self, "Finance API", "Finance API token не задан.")
            return
        try:
            today = date.today()
            WBFinanceAPI(token).get_sales_reports_list(today - timedelta(days=7), today)
            QMessageBox.information(self, "Finance API", "OK")
        except WBApiError as exc:
            QMessageBox.warning(self, "Finance API", str(exc))
        except Exception as exc:
            QMessageBox.warning(self, "Finance API", f"Ошибка проверки: {exc}")

    def check_promotion(self) -> None:
        token = self.promotion_token.text().strip() or self.token_store.promotion_token()
        if not token:
            QMessageBox.warning(self, "Promotion API", "Promotion API token не задан.")
            return
        try:
            today = date.today()
            WBPromotionAPI(token).get_ad_expenses(today - timedelta(days=7), today)
            QMessageBox.information(self, "Promotion API", "OK")
        except WBApiError as exc:
            QMessageBox.warning(self, "Promotion API", str(exc))
        except Exception as exc:
            QMessageBox.warning(self, "Promotion API", f"Ошибка проверки: {exc}")

    def save_and_accept(self) -> None:
        self.settings.api.use_api_by_default = self.use_api.isChecked()
        self.settings.api.use_excel_as_fallback = self.use_excel_fallback.isChecked()
        SettingsStore().save(self.settings)
        self.accept()
