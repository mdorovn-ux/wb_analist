from __future__ import annotations

from pathlib import Path


def apply_styles(app) -> None:
    path = Path(__file__).resolve().parent.parent / "resources" / "app.qss"
    if path.exists():
        app.setStyleSheet(path.read_text(encoding="utf-8"))
