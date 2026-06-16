from __future__ import annotations

import logging

from wb_finance_analyst.domain.constants import APP_NAME, LEGACY_APP_NAME

LOGGER = logging.getLogger(__name__)


class TokenStore:
    FINANCE_KEY = "wb_finance_token"
    PROMOTION_KEY = "wb_promotion_token"

    def __init__(self, service_name: str = APP_NAME) -> None:
        self.service_name = service_name
        self._memory: dict[str, str] = {}
        try:
            import keyring  # type: ignore

            self._keyring = keyring
            self.available = True
        except Exception as exc:
            LOGGER.warning("keyring unavailable: %s", exc)
            self._keyring = None
            self.available = False

    def get_token(self, key: str) -> str:
        if self.available and self._keyring:
            token = self._keyring.get_password(self.service_name, key)
            if token:
                return token
            if self.service_name == APP_NAME:
                legacy_token = self._keyring.get_password(LEGACY_APP_NAME, key)
                if legacy_token:
                    self._keyring.set_password(self.service_name, key, legacy_token)
                    return legacy_token
            return ""
        return self._memory.get(key, "")

    def set_token(self, key: str, token: str) -> None:
        if self.available and self._keyring:
            self._keyring.set_password(self.service_name, key, token)
        else:
            self._memory[key] = token

    def delete_token(self, key: str) -> None:
        if self.available and self._keyring:
            try:
                self._keyring.delete_password(self.service_name, key)
            except Exception:
                pass
        self._memory.pop(key, None)

    def mask(self, token: str) -> str:
        if not token:
            return ""
        return "*" * max(len(token) - 4, 8) + token[-4:]

    def finance_token(self) -> str:
        return self.get_token(self.FINANCE_KEY)

    def promotion_token(self) -> str:
        return self.get_token(self.PROMOTION_KEY)
