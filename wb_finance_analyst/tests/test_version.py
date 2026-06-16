from wb_finance_analyst import __version__
from wb_finance_analyst.domain.constants import APP_VERSION as CONSTANTS_APP_VERSION
from wb_finance_analyst.version import APP_VERSION, RELEASE_ARCHIVE_NAME


def test_version_is_defined_once_for_public_imports():
    assert APP_VERSION == "1.1.0-dev"
    assert __version__ == APP_VERSION
    assert CONSTANTS_APP_VERSION == APP_VERSION


def test_release_archive_name_uses_app_version():
    assert RELEASE_ARCHIVE_NAME == f"WB-analyst-v{APP_VERSION}.zip"

