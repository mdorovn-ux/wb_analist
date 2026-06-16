from pathlib import Path

try:
    from platformdirs import user_config_dir, user_data_dir, user_log_dir
except ImportError:
    import os

    def user_config_dir(appname: str) -> str:
        return str(Path(os.getenv("APPDATA", Path.home() / "AppData" / "Roaming")) / appname)

    def user_data_dir(appname: str) -> str:
        return str(Path(os.getenv("APPDATA", Path.home() / "AppData" / "Roaming")) / appname)

    def user_log_dir(appname: str) -> str:
        return str(Path(os.getenv("APPDATA", Path.home() / "AppData" / "Roaming")) / appname / "logs")

from wb_finance_analyst.domain.constants import APP_NAME, LEGACY_APP_NAME


PACKAGE_DIR = Path(__file__).resolve().parents[1]
APP_ICON_PATH = PACKAGE_DIR / "resources" / "icons" / "app_icon.svg"
CONFIG_DIR = Path(user_config_dir(APP_NAME))
DATA_DIR = Path(user_data_dir(APP_NAME))
LOG_DIR = Path(user_log_dir(APP_NAME))
LEGACY_CONFIG_DIR = Path(user_config_dir(LEGACY_APP_NAME))
LEGACY_DATA_DIR = Path(user_data_dir(LEGACY_APP_NAME))
LEGACY_LOG_DIR = Path(user_log_dir(LEGACY_APP_NAME))
SETTINGS_PATH = CONFIG_DIR / "settings.json"
LICENSE_PATH = CONFIG_DIR / "license.json"
COSTS_PATH = DATA_DIR / "costs.xlsx"
LEGACY_SETTINGS_PATH = LEGACY_CONFIG_DIR / "settings.json"
LEGACY_COSTS_PATH = LEGACY_DATA_DIR / "costs.xlsx"
EXPORT_DIR = DATA_DIR / "reports"
CACHE_DIR = DATA_DIR / "cache" / "api"
