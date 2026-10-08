import sqlite3

from db.init_db import init_database


def test_migration_adds_columns_to_old_database_and_keeps_data(tmp_path):
    db = tmp_path / "old.db"
    conn = sqlite3.connect(db)
    conn.execute("""CREATE TABLE nutrition_log (id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT NOT NULL,
        meal_label TEXT, food_name TEXT NOT NULL, amount_g REAL, calories REAL DEFAULT 0, protein_g REAL DEFAULT 0,
        carbs_g REAL DEFAULT 0, fat_g REAL DEFAULT 0, fiber_g REAL DEFAULT 0, created_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
    conn.execute("INSERT INTO nutrition_log (date, food_name, calories) VALUES ('2026-01-01', 'Skyr', 85)")
    conn.commit()
    conn.close()

    init_database(str(db), verbose=False)
    init_database(str(db), verbose=False)  # idempotent

    conn = sqlite3.connect(db)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(nutrition_log)")}
    assert {"price_eur", "sugar_g", "satfat_g", "salt_g", "amount_text", "source", "notes"} <= cols
    assert conn.execute("SELECT food_name, calories FROM nutrition_log").fetchall() == [("Skyr", 85.0)]
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"favorites", "profile", "claude_usage", "daily_health_metrics", "workouts"} <= tables
    assert conn.execute("SELECT total_price_eur FROM daily_summary").fetchone() == (0,)
