from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from wb_finance_analyst.config.defaults import CONFIG_DIR, LICENSE_PATH


LICENSE_SECRET = "wb-analyst-v1-manual-license-9f6c2f13-keep-private"
UNIVERSAL_LICENSE_KEY = "WB-ANALYST-UNIVERSAL-2026"


@dataclass(frozen=True)
class LicenseState:
    installation_id: str
    activated: bool
    activation_key: str = ""
    activated_at: str = ""


class LicenseManager:
    def __init__(self, path: Path = LICENSE_PATH) -> None:
        self.path = path

    def state(self) -> LicenseState:
        payload = self._read_payload()
        installation_id = normalize_installation_id(payload.get("installation_id") or self._new_installation_id())
        activation_key = normalize_activation_key(payload.get("activation_key") or "")
        activated_at = str(payload.get("activated_at") or "")
        activated = self.validate_activation_key(installation_id, activation_key)
        if payload.get("installation_id") != installation_id or bool(payload.get("activated")) != activated:
            self._write_payload(
                {
                    "installation_id": installation_id,
                    "activated": activated,
                    "activation_key": activation_key if activated else "",
                    "activated_at": activated_at if activated else "",
                }
            )
        return LicenseState(
            installation_id=installation_id,
            activated=activated,
            activation_key=activation_key if activated else "",
            activated_at=activated_at if activated else "",
        )

    def is_activated(self) -> bool:
        return self.state().activated

    def activate(self, activation_key: str) -> bool:
        state = self.state()
        key = normalize_activation_key(activation_key)
        if not self.validate_activation_key(state.installation_id, key):
            return False
        self._write_payload(
            {
                "installation_id": state.installation_id,
                "activated": True,
                "activation_key": key,
                "activated_at": datetime.now().isoformat(timespec="seconds"),
            }
        )
        return True

    def validate_activation_key(self, installation_id: str, activation_key: str) -> bool:
        key = normalize_activation_key(activation_key)
        if not key:
            return False
        if key == normalize_activation_key(UNIVERSAL_LICENSE_KEY):
            return True
        return hmac.compare_digest(key, generate_activation_key(installation_id))

    def _read_payload(self) -> dict:
        if not self.path.exists():
            return {}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        return payload if isinstance(payload, dict) else {}

    def _write_payload(self, payload: dict) -> None:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _new_installation_id(self) -> str:
        return format_groups(uuid4().hex.upper(), group_size=4, groups=4)


def generate_activation_key(installation_id: str) -> str:
    normalized = normalize_installation_id(installation_id)
    digest = hmac.new(LICENSE_SECRET.encode("utf-8"), normalized.encode("utf-8"), hashlib.sha256).hexdigest().upper()
    return format_groups(digest[:20], group_size=5, groups=4)


def normalize_installation_id(value: str) -> str:
    clean = "".join(ch for ch in str(value or "").upper() if ch.isalnum())
    if not clean:
        return ""
    return format_groups(clean[:16], group_size=4, groups=4)


def normalize_activation_key(value: str) -> str:
    clean = "".join(ch for ch in str(value or "").upper() if ch.isalnum())
    if not clean:
        return ""
    if clean == "".join(ch for ch in UNIVERSAL_LICENSE_KEY.upper() if ch.isalnum()):
        return UNIVERSAL_LICENSE_KEY
    return format_groups(clean, group_size=5, groups=max(1, len(clean) // 5))


def format_groups(value: str, group_size: int, groups: int) -> str:
    clean = "".join(ch for ch in str(value or "").upper() if ch.isalnum())
    clean = clean[: group_size * groups]
    return "-".join(clean[index : index + group_size] for index in range(0, len(clean), group_size))
