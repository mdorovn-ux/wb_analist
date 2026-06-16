from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, ClassVar

import requests

from wb_finance_analyst.services.load_progress import LoadingCancelled

LOGGER = logging.getLogger(__name__)


class WBApiError(RuntimeError):
    pass


@dataclass
class WBApiClient:
    token: str
    base_url: str
    timeout: float | tuple[float, float] = (10, 120)
    max_retries: int = 3
    min_interval_seconds: float = 0.0
    status_callback: Callable[[str], None] | None = None
    cancel_callback: Callable[[], bool] | None = None

    _state_lock: ClassVar[threading.Lock] = threading.Lock()
    _last_request_at_by_base_url: ClassVar[dict[str, float]] = {}

    def get(self, path: str, params: dict | None = None) -> dict | list:
        return self._request("GET", path, params=params)

    def post(self, path: str, json: dict | None = None) -> dict | list:
        return self._request("POST", path, json=json)

    def _request(self, method: str, path: str, **kwargs: Any) -> dict | list:
        if not self.token:
            raise WBApiError("API token не задан")
        url = self.base_url.rstrip("/") + "/" + path.lstrip("/")
        headers = {
            "Authorization": self.token,
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Connection": "close",
        }
        endpoint = f"{method} /{path.lstrip('/')}"
        skip_preflight_wait = False
        for attempt in range(1, self.max_retries + 2):
            if skip_preflight_wait:
                skip_preflight_wait = False
            else:
                self._wait_for_rate_limit(endpoint)
            try:
                response = requests.request(method, url, headers=headers, timeout=self.timeout, **kwargs)
            except requests.RequestException as exc:
                self._mark_request_finished()
                if self._retry_network_error(endpoint, attempt, exc):
                    skip_preflight_wait = True
                    continue
            self._mark_request_finished()
            LOGGER.info("WB API request endpoint=%s status=%s attempt=%s", endpoint, response.status_code, attempt)
            if response.status_code == 429 and attempt <= self.max_retries:
                delay = self._retry_delay(response)
                LOGGER.warning(
                    "WB API rate limit endpoint=%s status=%s retry_seconds=%s attempt=%s",
                    endpoint,
                    response.status_code,
                    delay,
                    attempt,
                )
                retry_text = f"Повтор {attempt + 1}/{self.max_retries + 1}"
                self._sleep_with_status(
                    delay,
                    lambda seconds, text=retry_text: (
                        f"WB Finance API: лимит запросов, ожидание {seconds} секунд... {text}"
                    ),
                )
                skip_preflight_wait = True
                continue
            if response.status_code in {500, 502, 503, 504} and attempt <= self.max_retries:
                delay = self._server_retry_delay(response)
                LOGGER.warning(
                    "WB API temporary server error endpoint=%s status=%s retry_seconds=%s attempt=%s",
                    endpoint,
                    response.status_code,
                    delay,
                    attempt,
                )
                retry_text = f"Повтор {attempt + 1}/{self.max_retries + 1}"
                self._sleep_with_status(
                    delay,
                    lambda seconds, text=retry_text: (
                        f"WB API: временный сбой, ожидание {seconds} секунд... {text}"
                    ),
                )
                skip_preflight_wait = True
                continue
            try:
                response_text = response.text
            except requests.RequestException as exc:
                if self._retry_network_error(endpoint, attempt, exc):
                    skip_preflight_wait = True
                    continue
            if response.status_code >= 400:
                raise WBApiError(self._message(response.status_code, response_text[:300]))
            if not response_text:
                return {}
            try:
                return response.json()
            except requests.RequestException as exc:
                if self._retry_network_error(endpoint, attempt, exc):
                    skip_preflight_wait = True
                    continue
            except ValueError as exc:
                raise WBApiError("WB API вернул некорректный JSON") from exc
        raise WBApiError("WB API вернул 429, лимит запросов")

    def _wait_for_rate_limit(self, endpoint: str) -> None:
        if self.min_interval_seconds <= 0:
            return
        while True:
            self._raise_if_cancelled()
            with self._state_lock:
                last = self._last_request_at_by_base_url.get(self.base_url, 0.0)
                wait_for = self.min_interval_seconds - (time.monotonic() - last)
            if wait_for <= 0:
                return
            seconds = int(wait_for) + 1
            LOGGER.info("WB API rate wait endpoint=%s retry_seconds=%s attempt=preflight", endpoint, seconds)
            self._notify(f"WB Finance API: лимит запросов, ожидание {seconds} секунд...")
            self._sleep_with_cancel(min(wait_for, 1.0))

    def _mark_request_finished(self) -> None:
        if self.min_interval_seconds <= 0:
            return
        with self._state_lock:
            self._last_request_at_by_base_url[self.base_url] = time.monotonic()

    def _retry_delay(self, response: requests.Response) -> int:
        raw = response.headers.get("X-Ratelimit-Retry")
        if raw:
            try:
                return max(int(float(raw)) + 2, 1)
            except ValueError:
                pass
        return 65

    def _network_retry_delay(self) -> int:
        return 5

    def _server_retry_delay(self, response: requests.Response) -> int:
        raw = response.headers.get("Retry-After")
        if raw:
            try:
                return max(int(float(raw)) + 2, 1)
            except ValueError:
                pass
        if self.min_interval_seconds > 0:
            return max(int(self.min_interval_seconds), 1)
        return 10

    def _retry_network_error(self, endpoint: str, attempt: int, exc: requests.RequestException) -> bool:
        if attempt <= self.max_retries:
            delay = self._network_retry_delay()
            LOGGER.warning(
                "WB API network error endpoint=%s status=network_error retry_seconds=%s attempt=%s error=%s",
                endpoint,
                delay,
                attempt,
                exc.__class__.__name__,
            )
            retry_text = f"Повтор {attempt + 1}/{self.max_retries + 1}"
            self._sleep_with_status(
                delay,
                lambda seconds, text=retry_text: (
                    f"WB Finance API: ошибка соединения, ожидание {seconds} секунд... {text}"
                ),
            )
            return True
        LOGGER.error(
            "WB API network error endpoint=%s status=network_error retry_seconds=0 attempt=%s error=%s",
            endpoint,
            attempt,
            exc.__class__.__name__,
        )
        raise WBApiError(f"WB API: ошибка соединения после повторов. {exc}") from exc

    def _notify(self, message: str) -> None:
        if self.status_callback:
            self.status_callback(message)

    def _sleep_with_cancel(self, seconds: float) -> None:
        if not self.cancel_callback:
            time.sleep(seconds)
            return
        deadline = time.monotonic() + seconds
        while True:
            self._raise_if_cancelled()
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return
            time.sleep(min(remaining, 1.0))

    def _sleep_with_status(self, seconds: float, message_factory: Callable[[int], str]) -> None:
        if not self.cancel_callback:
            self._notify(message_factory(max(int(seconds), 1)))
            time.sleep(seconds)
            return
        deadline = time.monotonic() + seconds
        last_notified: int | None = None
        while True:
            self._raise_if_cancelled()
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return
            display_seconds = max(int(remaining) + 1, 1)
            if display_seconds != last_notified:
                self._notify(message_factory(display_seconds))
                last_notified = display_seconds
            time.sleep(min(remaining, 1.0))

    def _raise_if_cancelled(self) -> None:
        if self.cancel_callback and self.cancel_callback():
            raise LoadingCancelled("Загрузка отменена")

    def _message(self, status_code: int, body: str) -> str:
        messages = {
            400: "WB API: запрос отклонён. Возможно, изменился формат запроса или параметры периода",
            401: "WB API: токен неверный, истёк или не подходит для этого метода",
            403: "WB API: нет прав на метод. Проверьте права токена в кабинете WB",
            404: "WB API: метод не найден. Возможно, WB изменил адрес метода",
            429: "WB API: превышен лимит запросов",
            500: "WB API: внутренняя ошибка сервера",
            502: "WB API: временный сбой шлюза WB",
            503: "WB API: сервис временно недоступен",
            504: "WB API: сервис WB не ответил вовремя",
        }
        base = messages.get(status_code, f"WB API вернул HTTP {status_code}")
        return f"{base}. {body}" if body else base
