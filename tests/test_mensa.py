from pathlib import Path

from db.mensa import detect_mensa, parse_day

PAGE = (Path(__file__).parent / "fixtures" / "mensa_adenauerring.html").read_text(encoding="utf-8")
DAY = "2026-10-08"  # Tag, an dem die Fixture gespeichert wurde


def test_detect_mensa():
    assert detect_mensa("Pizza im Pizzawerk")["slug"] == "mensa_adenauerring"
    assert detect_mensa("Mittag in der Mensa Moltke")["slug"] == "mensa_moltke"
    assert detect_mensa("Gnocchi in der Mensa")["slug"] == "mensa_adenauerring"  # Standard: KIT
    assert detect_mensa("Döner am Kronenplatz") is None


def test_parse_day_has_exact_values_for_students():
    menu = parse_day(PAGE, DAY, "Studierende")
    assert menu.startswith("Linie 1 Gut & Günstig:")
    assert ("Pasta mit Erbsensoße und Speck-Topping [enthält Schweinefleisch] | 3,60 € | 1029 kcal, "
            "Eiweiß 39 g, KH 129 g (Zucker 9 g), Fett 36 g (ges. 15 g), Salz 5 g") in menu
    assert "[pizza]werk" in menu


def test_price_group_changes_price():
    guests = parse_day(PAGE, DAY, "Gäste")
    assert "Pasta mit Erbsensoße und Speck-Topping [enthält Schweinefleisch] | 5,20 €" in guests


def test_unknown_day_returns_none():
    assert parse_day(PAGE, "2020-01-01", "Studierende") is None
