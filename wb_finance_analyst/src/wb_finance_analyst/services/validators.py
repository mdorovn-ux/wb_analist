from pathlib import Path


def validate_excel_paths(paths: list[Path]) -> list[str]:
    warnings = []
    for path in paths:
        if not path.exists():
            warnings.append(f"Файл не найден: {path}")
        elif path.suffix.lower() not in {".xlsx", ".xlsm", ".xls"}:
            warnings.append(f"Файл не является Excel: {path.name}")
    return warnings
