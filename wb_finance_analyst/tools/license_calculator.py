from __future__ import annotations

import sys
from pathlib import Path
import tkinter as tk
from tkinter import messagebox

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from wb_finance_analyst.services.license_manager import (  # noqa: E402
    UNIVERSAL_LICENSE_KEY,
    generate_activation_key,
    normalize_installation_id,
)


class LicenseCalculator(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("WB analyst license calculator")
        self.geometry("620x270")
        self.resizable(False, False)
        self._build_ui()

    def _build_ui(self) -> None:
        tk.Label(self, text="Код компьютера пользователя").pack(anchor="w", padx=16, pady=(16, 4))
        self.installation_id = tk.Entry(self, font=("Segoe UI", 12))
        self.installation_id.pack(fill="x", padx=16)

        buttons = tk.Frame(self)
        buttons.pack(fill="x", padx=16, pady=10)
        tk.Button(buttons, text="Сгенерировать ключ", command=self.generate).pack(side="left")
        tk.Button(buttons, text="Скопировать ключ", command=self.copy_activation).pack(side="left", padx=8)

        tk.Label(self, text="Активационный ключ").pack(anchor="w", padx=16, pady=(4, 4))
        self.activation_key = tk.Entry(self, font=("Segoe UI", 12))
        self.activation_key.pack(fill="x", padx=16)

        tk.Label(self, text="Универсальный ключ для тестов").pack(anchor="w", padx=16, pady=(14, 4))
        universal_row = tk.Frame(self)
        universal_row.pack(fill="x", padx=16)
        self.universal_key = tk.Entry(universal_row, font=("Segoe UI", 10))
        self.universal_key.insert(0, UNIVERSAL_LICENSE_KEY)
        self.universal_key.config(state="readonly")
        self.universal_key.pack(side="left", fill="x", expand=True)
        tk.Button(universal_row, text="Скопировать", command=self.copy_universal).pack(side="left", padx=(8, 0))

    def generate(self) -> None:
        installation_id = normalize_installation_id(self.installation_id.get())
        if not installation_id:
            messagebox.showwarning("WB analyst", "Введите код компьютера.")
            return
        key = generate_activation_key(installation_id)
        self.activation_key.delete(0, tk.END)
        self.activation_key.insert(0, key)

    def copy_activation(self) -> None:
        key = self.activation_key.get().strip()
        if not key:
            self.generate()
            key = self.activation_key.get().strip()
        if key:
            self.clipboard_clear()
            self.clipboard_append(key)
            messagebox.showinfo("WB analyst", "Активационный ключ скопирован.")

    def copy_universal(self) -> None:
        self.clipboard_clear()
        self.clipboard_append(UNIVERSAL_LICENSE_KEY)
        messagebox.showinfo("WB analyst", "Универсальный ключ скопирован.")


if __name__ == "__main__":
    LicenseCalculator().mainloop()
