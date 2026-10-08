"""
Liest die Speiseplaene des Studierendenwerks Karlsruhe (sw-ka.de) direkt aus.

Claude bekommt so exakte Naehrwerte und Preise, statt die Webseite nur
zusammengefasst zu lesen (dabei gehen Gerichte verloren oder werden erfunden).
"""

from __future__ import annotations

import html
import re
import time
from urllib import request as urllib_request

MENSEN = [
    {"keys": ["adenauer", "kit-mensa", "kit mensa", "pizzawerk", "koeriwerk", "kœriwerk", "schnitzelbar"],
     "slug": "mensa_adenauerring", "name": "Mensa am Adenauerring"},
    {"keys": ["moltke"], "slug": "mensa_moltke", "name": "Mensa Moltkestraße"},
    {"keys": ["erzberger"], "slug": "mensa_erzberger", "name": "Mensa Erzbergerstraße"},
    {"keys": ["gottesaue"], "slug": "mensa_gottesaue", "name": "Mensa Schloss Gottesaue"},
    {"keys": ["tiefenbronner"], "slug": "mensa_tiefenbronner", "name": "Mensa Tiefenbronner Straße"},
    {"keys": ["holzgarten"], "slug": "mensa_holzgarten", "name": "Mensa Holzgartenstraße"},
]
PRICE_INDEX = {"Studierende": 1, "Gäste": 2, "Bedienstete": 3, "Schüler": 4}
CACHE_SECONDS = 30 * 60
_cache: dict[str, tuple[float, str]] = {}


def detect_mensa(text: str) -> dict | None:
    """Welche Mensa ist gemeint? Nur 'Mensa' ohne Ort → Adenauerring (KIT)."""
    t = text.lower()
    for mensa in MENSEN:
        if any(k in t for k in mensa["keys"]):
            return mensa
    return MENSEN[0] if re.search(r"mensa|\bkit\b", t) else None


def _clean(fragment: str) -> str:
    text = re.sub(r"<[^>]+>", " ", fragment)
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def _num(chunk: str, css_class: str) -> str:
    m = re.search(rf'class="{css_class}"><div>[^<]*</div><div>([\d.,]+)', chunk)
    return m.group(1) if m else "?"


def parse_day(page: str, date: str, price_group: str) -> str | None:
    nav = re.search(rf'canteen_day_nav_(\d+)" rel="{re.escape(date)}"', page)
    if not nav:
        return None
    start = page.find(f'id="canteen_day_{nav.group(1)}"')
    if start < 0:
        return None
    nxt = page.find('id="canteen_day_', start + 20)
    day = page[start:nxt if nxt >= 0 else None]
    price_idx = PRICE_INDEX.get(price_group, 1)

    lines = []
    for line_chunk in day.split('<tr class="mensatype_rows">')[1:]:
        m = re.search(r'class="mensatype"[^>]*><div>([\s\S]*?)</div>', line_chunk)
        line_name = _clean(m.group(1)) if m else "Linie"
        pieces = line_chunk.split('class="first menu-title"')
        meals = []
        for i in range(1, len(pieces)):
            piece = pieces[i]
            name_m = re.search(r"<b>([\s\S]*?)</b>", piece)
            name = _clean(name_m.group(1)) if name_m else ""
            if not name:
                continue
            prev = pieces[i - 1]
            icons = re.findall(r'class="mealicon_\d" title="([^"]+)"', prev[prev.rfind("mtd-icon"):])
            price_m = re.search(rf'price_{price_idx}">([\d,]+)', piece)
            kcal_m = re.search(r"([\d.,]+) kcal", piece)
            if kcal_m:
                facts = (
                    f"{kcal_m.group(1)} kcal, Eiweiß {_num(piece, 'proteine')} g, "
                    f"KH {_num(piece, 'kohlenhydrate')} g (Zucker {_num(piece, 'zucker')} g), "
                    f"Fett {_num(piece, 'fett')} g (ges. {_num(piece, 'gesaettigt')} g), "
                    f"Salz {_num(piece, 'salz')} g"
                )
            else:
                facts = "keine Nährwerte angegeben"
            icon_text = f" [{', '.join(html.unescape(i) for i in icons)}]" if icons else ""
            price = f"{price_m.group(1)} €" if price_m else "Preis ?"
            meals.append(f"  - {name}{icon_text} | {price} | {facts}")
        if meals:
            lines.append(f"{line_name}:\n" + "\n".join(meals))
    return "\n".join(lines) if lines else None


def get_menu(text: str, date: str, price_group: str) -> dict | None:
    """Speiseplan als kompakter Text, falls der Nutzer eine Mensa erwaehnt. Sonst None."""
    mensa = detect_mensa(text)
    if not mensa:
        return None
    url = f"https://www.sw-ka.de/de/hochschulgastronomie/speiseplan/{mensa['slug']}/"
    try:
        cached = _cache.get(url)
        if cached and time.time() - cached[0] < CACHE_SECONDS:
            page = cached[1]
        else:
            req = urllib_request.Request(url, headers={"User-Agent": "open_garmin-ernaehrung/1.0"})
            with urllib_request.urlopen(req, timeout=15) as resp:
                page = resp.read().decode("utf-8", errors="replace")
            _cache[url] = (time.time(), page)
        menu = parse_day(page, date, price_group)
    except Exception:
        return None  # Dann sucht Claude selbst im Web
    return {"name": mensa["name"], "url": url, "menu": menu} if menu else None
