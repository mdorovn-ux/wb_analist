from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from wb_finance_analyst.config.defaults import CONFIG_DIR, LEGACY_SETTINGS_PATH, SETTINGS_PATH
from wb_finance_analyst.domain.models import APISettings, ColumnMap, ExternalExpense


class AppSettings(BaseModel):
    column_map: ColumnMap = Field(default_factory=ColumnMap)
    external_expenses: list[ExternalExpense] = Field(default_factory=list)
    api: APISettings = Field(default_factory=APISettings)
    last_output_dir: str = ""
    advertisement_mode: str = "none"

    def stable_hash(self) -> str:
        payload = self.model_dump_json(exclude={"last_output_dir"})
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


class SettingsStore:
    def __init__(self, path: Path = SETTINGS_PATH) -> None:
        self.path = path

    def load(self) -> AppSettings:
        path = self.path
        if not path.exists() and self.path == SETTINGS_PATH and LEGACY_SETTINGS_PATH.exists():
            path = LEGACY_SETTINGS_PATH
        if not path.exists():
            return AppSettings()
        try:
            return AppSettings.model_validate_json(path.read_text(encoding="utf-8"))
        except Exception:
            return AppSettings()

    def save(self, settings: AppSettings) -> None:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        data = json.dumps(settings.model_dump(), ensure_ascii=False, indent=2)
        self.path.write_text(data, encoding="utf-8")
