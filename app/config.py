from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv("RAB_DATA_DIR") or (BASE_DIR / "data"))
EXPORT_DIR = Path(os.getenv("RAB_EXPORT_DIR") or (DATA_DIR / "exports"))
DB_PATH = Path(os.getenv("RAB_DB_PATH") or (DATA_DIR / "rab.db"))

DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH.parent.mkdir(parents=True, exist_ok=True)
EXPORT_DIR.mkdir(parents=True, exist_ok=True)

APP_TITLE = "RAB Workflow Assistant"
BASIC_AUTH_USERNAME = os.getenv("RAB_BASIC_AUTH_USERNAME")
BASIC_AUTH_PASSWORD = os.getenv("RAB_BASIC_AUTH_PASSWORD")

_DEFAULT_SBM_CANDIDATES = [
    os.getenv("SBM_SOURCE_PATH"),
    DATA_DIR / "sbm-cache.xlsx",
    r"C:\Users\Admin\OneDrive - Kementerian Perindustrian Divisi Agro\MONEV 4.0\2026\LAIN-LAIN\DATA LAMPIRAN PMK 32 2025.xlsx",
]


def resolve_sbm_source() -> Path | None:
    for candidate in _DEFAULT_SBM_CANDIDATES:
        if not candidate:
            continue
        path = Path(candidate)
        if path.exists():
            return path
    return None
