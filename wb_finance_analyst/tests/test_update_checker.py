import base64
import json

import pytest
from requests import Timeout

from wb_finance_analyst.services import update_checker
from wb_finance_analyst.services.update_checker import UpdateCheckError, check_for_updates, is_version_newer, update_info_from_payload


def test_version_comparison_understands_release_over_dev():
    assert is_version_newer("1.1.0", "1.1.0-dev")
    assert is_version_newer("1.1.1", "1.1.0")
    assert not is_version_newer("1.0.0", "1.1.0-dev")
    assert not is_version_newer("1.1.0-dev", "1.1.0")


def test_update_info_from_payload_marks_newer_version():
    info = update_info_from_payload(
        {
            "version": "1.2.0",
            "download_url": "https://example.test/app.zip",
            "notes_url": "https://example.test/notes",
        },
        current_version="1.1.0",
    )

    assert info.update_available
    assert info.latest_version == "1.2.0"
    assert info.download_url == "https://example.test/app.zip"


def test_check_for_updates_uses_github_api_fallback_after_raw_timeout(monkeypatch):
    payload = {
        "version": "1.2.0",
        "download_url": "https://example.test/app.zip",
        "notes_url": "https://example.test/notes",
    }
    calls = []

    class Response:
        def __init__(self, data):
            self._data = data

        def raise_for_status(self):
            return None

        def json(self):
            return self._data

    def fake_get(url, **kwargs):
        calls.append((url, kwargs))
        if len(calls) == 1:
            raise Timeout("raw timeout")
        return Response(
            {
                "encoding": "base64",
                "content": base64.b64encode(json.dumps(payload).encode("utf-8")).decode("ascii"),
            }
        )

    monkeypatch.setattr(update_checker.requests, "get", fake_get)

    info = check_for_updates(current_version="1.1.0")

    assert len(calls) == 2
    assert calls[1][0] == update_checker.GITHUB_CONTENTS_LATEST_URL
    assert calls[0][1]["timeout"] == update_checker.UPDATE_CHECK_TIMEOUT
    assert info.update_available
    assert info.latest_version == "1.2.0"


def test_check_for_updates_raises_friendly_error_after_network_failures(monkeypatch):
    def fake_get(url, **kwargs):
        raise Timeout("read timed out")

    monkeypatch.setattr(update_checker.requests, "get", fake_get)

    with pytest.raises(UpdateCheckError, match="Не удалось проверить обновление"):
        check_for_updates(current_version="1.1.0")
