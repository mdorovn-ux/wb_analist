from __future__ import annotations

import logging
import sys
import traceback

from wb_finance_analyst.config.defaults import LOG_DIR


def setup_logging() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=LOG_DIR / "app.log",
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        encoding="utf-8",
    )


def _log_unhandled_exception(exc_type, exc_value, exc_traceback) -> None:
    logging.critical("Unhandled application exception", exc_info=(exc_type, exc_value, exc_traceback))
    sys.__excepthook__(exc_type, exc_value, exc_traceback)


def main() -> int:
    setup_logging()
    sys.excepthook = _log_unhandled_exception
    logging.info("Запуск программы")
    try:
        from PySide6.QtGui import QIcon
        from PySide6.QtWidgets import QApplication

        from wb_finance_analyst.ui.main_window import MainWindow
        from wb_finance_analyst.ui.license_dialog import LicenseDialog
        from wb_finance_analyst.ui.styles import apply_styles
        from wb_finance_analyst.config.defaults import APP_ICON_PATH
        from wb_finance_analyst.services.license_manager import LicenseManager
    except ImportError as exc:
        print("Для запуска интерфейса установите зависимости: pip install -r requirements.txt")
        print(f"Техническая причина: {exc}")
        return 1

    try:
        app = QApplication(sys.argv)
        app.setApplicationName("WB analyst")
        app.setWindowIcon(QIcon(str(APP_ICON_PATH)))
        apply_styles(app)
        license_manager = LicenseManager()
        if not license_manager.is_activated():
            dialog = LicenseDialog(license_manager)
            if not dialog.exec():
                return 0
        window = MainWindow()
        window.show()
        return app.exec()
    except Exception:
        logging.critical("Application startup failed:\n%s", traceback.format_exc())
        raise
