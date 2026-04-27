from __future__ import annotations

import argparse
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from app.config import DB_PATH
from app.database import bootstrap_schema, db_cursor
from app.services.rab import bootstrap_application_data


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed database RAB workflow assistant.")
    parser.add_argument("--reset", action="store_true", help="Hapus database lama sebelum membuat seed baru.")
    args = parser.parse_args()

    if args.reset and DB_PATH.exists():
        DB_PATH.unlink()

    bootstrap_schema()
    with db_cursor() as connection:
        meta = bootstrap_application_data(connection)
        print(f"Seed selesai. Referensi biaya: {meta['cost_meta']}")


if __name__ == "__main__":
    main()
