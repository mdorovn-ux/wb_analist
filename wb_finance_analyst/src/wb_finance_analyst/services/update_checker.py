from __future__ import annotations

import base64
import json
import re
from dataclasses import dataclass
from typing import Any

import requests
from requests import RequestException

from wb_finance_analyst.version import APP_VERSION, LATEST_VERSION_URL

GITHUB_CONTENTS_LATEST_URL = "https://api.github.com/repos/mdorovn-ux/wb_analist/contents/latest.json?ref=main"
UPDATE_CHECK_TIMEOUT = (4, 15)


@dataclass(frozen=True)
class UpdateInfo:
    current_version: str
    latest_version: str
    update_available: bool
    download_url: str
    notes_url: str
    message: str


class UpdateCheckError(RuntimeError):
    pass


def check_for_updates(current_version: str = APP_VERSION, url: str = LATEST_VERSION_URL) -> UpdateInfo:
    payload = _load_latest_payload(url)
    return update_info_from_payload(payload, current_version=current_version)


def _load_latest_payload(url: str) -> dict[str, Any]:
    urls = [url]
    if url == LATEST_VERSION_URL:
        urls.append(GITHUB_CONTENTS_LATEST_URL)

    last_error: Exception | None = None
    for current_url in urls:
        try:
            return _request_latest_payload(current_url)
        except (RequestException, ValueError, KeyError, json.JSONDecodeError) as exc:
            last_error = exc

    raise UpdateCheckError(
        "Не удалось проверить обновление. Проверьте интернет или откройте страницу скачивания вручную."
    ) from last_error


def _request_latest_payload(url: str) -> dict[str, Any]:
    response = requests.get(
        url,
        timeout=UPDATE_CHECK_TIMEOUT,
        headers={
            "Accept": "application/json",
            "User-Agent": "WB-analyst-update-check",
        },
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError("latest.json must contain an object")

    if "version" in payload:
        return payload

    if payload.get("encoding") == "base64" and payload.get("content"):
        content = base64.b64decode(str(payload["content"])).decode("utf-8")
        decoded_payload = json.loads(content)
        if not isinstance(decoded_payload, dict):
            raise ValueError("latest.json must contain an object")
        return decoded_payload

    raise ValueError("latest.json does not contain version")


def update_info_from_payload(payload: dict[str, Any], current_version: str = APP_VERSION) -> UpdateInfo:
    latest_version = str(payload.get("version") or "").strip()
    download_url = str(payload.get("download_url") or "").strip()
    notes_url = str(payload.get("notes_url") or "").strip()
    if not latest_version:
        raise ValueError("latest.json does not contain version")
    update_available = is_version_newer(latest_version, current_version)
    if update_available:
        message = f"Доступна новая версия {latest_version}."
    else:
        message = "Установлена актуальная версия."
    return UpdateInfo(
        current_version=current_version,
        latest_version=latest_version,
        update_available=update_available,
        download_url=download_url,
        notes_url=notes_url,
        message=message,
    )


def is_version_newer(candidate: str, current: str) -> bool:
    return _version_key(candidate) > _version_key(current)


def _version_key(value: str) -> tuple[tuple[int, int, int], int, str]:
    text = str(value or "").strip().lower().lstrip("v")
    match = re.match(r"^(\d+)(?:\.(\d+))?(?:\.(\d+))?(?:[-.]?([a-z]+[0-9a-z.-]*))?$", text)
    if not match:
        return (0, 0, 0), 0, text
    major, minor, patch, suffix = match.groups()
    numbers = (int(major or 0), int(minor or 0), int(patch or 0))
    release_weight = 1 if not suffix else 0
    return numbers, release_weight, suffix or ""
