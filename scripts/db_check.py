#!/usr/bin/env python3
import sqlite3
from pathlib import Path

DB_PATH = Path("/home/rohit_chowdary/Rohit-AI-WorkSpace/marketplace/marketplace.db")


def main() -> None:
    con = sqlite3.connect(DB_PATH)
    try:
        con.execute("PRAGMA foreign_keys = ON;")
        tables = [
            r[0]
            for r in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name;"
            ).fetchall()
        ]
        print("Tables:")
        for t in tables:
            print(f"- {t}")

        print("Row counts:")
        for t in tables:
            cnt = con.execute(f"SELECT COUNT(*) FROM {t};").fetchone()[0]
            print(f"- {t}: {cnt}")
    finally:
        con.close()


if __name__ == "__main__":
    main()
