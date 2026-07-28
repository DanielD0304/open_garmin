"""
Initialisiert die SQLite-Datenbank fuer den AI Athletik- & Ernaehrungs-Coach.

Das Schema liegt in migrations.py und ist ueber PRAGMA user_version versioniert.
Dieses Skript wendet alle ausstehenden Migrationen an und baut die Views neu.

Idempotent: Kann beliebig oft ausgefuehrt werden. Auf einer bestehenden DB
werden nur die noch fehlenden Migrationen angewendet.
"""

import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.migrations import LATEST_VERSION, ensure_views, get_version, run_migrations  # noqa: E402

DB_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(DB_DIR, "coach.db")


def init_database(db_path: str = DB_PATH, verbose: bool = True) -> int:
    """Wendet Migrationen an und erstellt die Views. Gibt die Schema-Version zurueck."""
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA foreign_keys=ON")
        before = get_version(conn)
        after = run_migrations(conn, verbose=verbose)
        ensure_views(conn)
    finally:
        conn.close()

    if verbose:
        print(f"[OK] Datenbank initialisiert: {db_path}")
        if before == after:
            print(f"     Schema bereits aktuell (Version {after})")
        else:
            print(f"     Schema-Version {before} -> {after}")
        print("     Tabellen: nutrition_log, daily_health_metrics, workouts, raw_garmin_payloads")
        print("     Views:    daily_summary")

    return after


if __name__ == "__main__":
    version = init_database()
    if version != LATEST_VERSION:
        print(f"[WARN] Erwartet Version {LATEST_VERSION}, ist {version}", file=sys.stderr)
        sys.exit(1)
