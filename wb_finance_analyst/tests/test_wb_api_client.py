import pytest
import requests

from wb_finance_analyst.services.wb_api_client import WBApiClient, WBApiError


class FakeResponse:
    def __init__(self, status_code, text="", headers=None):
        self.status_code = status_code
        self.text = text
        self.headers = headers or {}

    def json(self):
        return {"ok": True}


def test_wb_api_client_retries_429_with_retry_header(monkeypatch):
    calls = []
    sleeps = []

    def fake_request(method, url, headers, timeout, **kwargs):
        calls.append((method, url))
        if len(calls) == 1:
            return FakeResponse(429, "too many requests", {"X-Ratelimit-Retry": "3"})
        return FakeResponse(200, "{}")

    monkeypatch.setattr("wb_finance_analyst.services.wb_api_client.requests.request", fake_request)
    monkeypatch.setattr("wb_finance_analyst.services.wb_api_client.time.sleep", lambda seconds: sleeps.append(seconds))
    client = WBApiClient(token="secret", base_url="https://finance-api.wildberries.ru", max_retries=3)
    result = client.get("/test")
    assert result == {"ok": True}
    assert len(calls) == 2
    assert sleeps == [5]


def test_wb_api_client_does_not_double_wait_after_429(monkeypatch):
    WBApiClient._last_request_at_by_base_url.clear()
    calls = []
    sleeps = []

    def fake_request(method, url, headers, timeout, **kwargs):
        calls.append((method, url))
        if len(calls) == 1:
            return FakeResponse(429, "too many requests", {"X-Ratelimit-Retry": "3"})
        return FakeResponse(200, "{}")

    monkeypatch.setattr("wb_finance_analyst.services.wb_api_client.requests.request", fake_request)
    monkeypatch.setattr("wb_finance_analyst.services.wb_api_client.time.sleep", lambda seconds: sleeps.append(seconds))
    client = WBApiClient(
        token="secret",
        base_url="https://finance-api.wildberries.ru",
        max_retries=3,
        min_interval_seconds=65,
    )
    result = client.get("/test")
    assert result == {"ok": True}
    assert len(calls) == 2
    assert sleeps == [5]


def test_wb_api_client_retries_temporary_server_errors(monkeypatch):
    calls = []
    sleeps = []

    def fake_request(method, url, headers, timeout, **kwargs):
        calls.append((method, url))
        if len(calls) == 1:
            return FakeResponse(503, "service unavailable", {"Retry-After": "2"})
        return FakeResponse(200, "{}")

    monkeypatch.setattr("wb_finance_analyst.services.wb_api_client.requests.request", fake_request)
    monkeypatch.setattr("wb_finance_analyst.services.wb_api_client.time.sleep", lambda seconds: sleeps.append(seconds))
    client = WBApiClient(token="secret", base_url="https://finance-api.wildberries.ru", max_retries=3)
    result = client.get("/test")

    assert result == {"ok": True}
    assert len(calls) == 2
    assert sleeps == [4]


def test_wb_api_client_does_not_retry_auth_errors(monkeypatch):
    calls = []

    def fake_request(method, url, headers, timeout, **kwargs):
        calls.append((method, url))
        return FakeResponse(403, "forbidden")

    monkeypatch.setattr("wb_finance_analyst.services.wb_api_client.requests.request", fake_request)
    client = WBApiClient(token="secret", base_url="https://finance-api.wildberries.ru", max_retries=3)

    with pytest.raises(WBApiError, match="нет прав"):
        client.get("/test")
    assert len(calls) == 1


def test_wb_api_client_retries_network_errors_with_short_delay(monkeypatch):
    WBApiClient._last_request_at_by_base_url.clear()
    calls = []
    sleeps = []

    def fake_request(method, url, headers, timeout, **kwargs):
        calls.append((method, url))
        if len(calls) == 1:
            raise requests.ConnectTimeout("offline")
        return FakeResponse(200, "{}")

    monkeypatch.setattr("wb_finance_analyst.services.wb_api_client.requests.request", fake_request)
    monkeypatch.setattr("wb_finance_analyst.services.wb_api_client.time.sleep", lambda seconds: sleeps.append(seconds))
    client = WBApiClient(token="secret", base_url="https://finance-api.wildberries.ru", max_retries=3, min_interval_seconds=65)
    result = client.get("/test")

    assert result == {"ok": True}
    assert len(calls) == 2
    assert sleeps == [5]
