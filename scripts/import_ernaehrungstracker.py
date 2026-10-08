"""
Uebernimmt die Daten des frueheren Node-Ernaehrungstrackers in die AI-Coach-Datenbank.

    python scripts/import_ernaehrungstracker.py [Pfad zum data-Ordner]

Standard: %USERPROFILE%\\Documents\\ernaehrungstracker\\data
Mehrfaches Ausfuehren erzeugt keine Duplikate.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db import models  # noqa: E402
from db.init_db import init_database  # noqa: E402

FIELD_MAP = {
    "name": "food_name", "amount": "amount_text", "kcal": "calories", "protein": "protein_g",
    "carbs": "carbs_g", "sugar": "sugar_g", "fat": "fat_g", "satfat": "satfat_g", "fiber": "fiber_g",
    "salt": "salt_g", "price": "price_eur", "source": "source", "notes": "notes",
}


def _load(folder: Path, name: str, default):
    path = folder / f"{name}.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def _map(item: dict) -> dict:
    return {new: item.get(old) for old, new in FIELD_MAP.items()}


def main() -> None:
    folder = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.home() / "Documents" / "ernaehrungstracker" / "data"
    if not folder.is_dir():
        sys.exit(f"Ordner nicht gefunden: {folder}")
    init_database(verbose=False)
    conn = models.get_connection()

    added = 0
    for e in _load(folder, "entries", []):
        created = (e.get("createdAt") or "").replace("T", " ").rstrip("Z")[:19]
        exists = conn.execute(
            "SELECT 1 FROM nutrition_log WHERE date = ? AND food_name = ? AND created_at = ?",
            (e["date"], e.get("name"), created),
        ).fetchone()
        if exists:
            continue
        item = _map(e)
        for key in ("calories", "protein_g", "carbs_g", "fat_g", "fiber_g"):
            item[key] = item[key] or 0
        cols = ["date", "meal_label", "created_at", *item]
        conn.execute(
            f"INSERT INTO nutrition_log ({', '.join(cols)}) VALUES ({', '.join('?' for _ in cols)})",
            (e["date"], e.get("meal") or "snack", created, *item.values()),
        )
        added += 1

    known = {f["food_name"] for f in models.list_favorites()}
    favs = 0
    for f in _load(folder, "favorites", []):
        if f.get("name") not in known:
            models.add_favorite(**_map(f))
            known.add(f.get("name"))
            favs += 1

    profile = _load(folder, "profile", None)
    if profile and not models.get_profile().get("onboarded"):
        models.save_profile(profile)

    usage = _load(folder, "usage", {})
    imported_usage = 0
    have = {r["at"] for r in models.get_claude_usage(limit=10000)["log"]}
    log = list(reversed(usage.get("log") or []))  # aelteste zuerst
    for i, r in enumerate(log):
        at = r["at"][:19]
        if at in have:
            continue
        models.log_claude_usage({
            "at": at, "kind": r.get("kind"), "model": r.get("model"), "input": r.get("input", 0),
            "cacheWrite": r.get("cacheWrite", 0), "cacheRead": r.get("cacheRead", 0), "output": r.get("output", 0),
            "webSearches": r.get("webSearches", 0), "costUsd": r.get("costUsd", 0), "durationMs": r.get("durationMs", 0),
            "rateLimit": usage.get("rateLimit") if i == len(log) - 1 else None,
        })
        imported_usage += 1
    conn.commit()
    print(f"Übernommen: {added} Einträge, {favs} Favoriten, {imported_usage} Claude-Anfragen"
          f"{', Profil' if profile else ''} → {models.DB_PATH}")


if __name__ == "__main__":
    main()
