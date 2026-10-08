"""
AI Coach – Desktop-App.

Startet das FastAPI-Backend im Hintergrund (nur 127.0.0.1, freier Port) und
zeigt die Oberflaeche in einem eigenen Programmfenster (pywebview / Edge WebView2).
Beim Schliessen des Fensters wird auch der Server beendet.

    python app.py
"""

from __future__ import annotations

import ctypes
import logging
import os
import socket
import sys
import threading
import time
import webbrowser
from logging.handlers import RotatingFileHandler

from db.paths import DATA_DIR, LOG_DIR, resource_dir

APP_TITLE = "AI Coach"


def setup_logging() -> logging.Logger:
    # In der .exe ohne Konsole gibt es kein stdout/stderr – alles ins Logfile
    log_file = LOG_DIR / "app.log"
    if sys.stdout is None or sys.stderr is None:
        stream = open(log_file, "a", encoding="utf-8", buffering=1)  # noqa: SIM115
        sys.stdout = sys.stdout or stream
        sys.stderr = sys.stderr or stream
    handler = RotatingFileHandler(log_file, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)
    return logging.getLogger("ai_coach")


def message_box(text: str, title: str = APP_TITLE) -> None:
    if sys.platform == "win32":
        ctypes.windll.user32.MessageBoxW(None, text, title, 0x10)
    else:
        print(f"{title}: {text}", file=sys.stderr)


def acquire_single_instance():
    """Verhindert, dass die App zweimal laeuft (zwei Server auf derselben Datenbank)."""
    lock_path = DATA_DIR / "app.lock"
    handle = open(lock_path, "a+")  # noqa: SIM115 – bleibt bis zum Prozessende offen
    try:
        if sys.platform == "win32":
            import msvcrt
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return None
    return handle


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def windows_taskbar_identity() -> None:
    """Eigene Taskleisten-Gruppe statt 'Python' (wichtig beim Start ueber pythonw.exe)."""
    if sys.platform == "win32":
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("AICoach.Desktop")


def set_window_icon(window, log: logging.Logger) -> None:
    """Fenster-Icon setzen (WinForms). In der .exe kommt das Icon bereits aus der Datei."""
    icon_path = resource_dir() / "packaging" / "ai_coach.ico"
    if sys.platform != "win32" or getattr(sys, "frozen", False) or not icon_path.exists():
        return
    try:
        import clr  # pythonnet, kommt mit pywebview
        clr.AddReference("System.Drawing")
        from System import Action
        from System.Drawing import Icon

        form = window.native
        form.Invoke(Action(lambda: setattr(form, "Icon", Icon(str(icon_path)))))
    except Exception as e:  # rein kosmetisch
        log.info("Fenster-Icon nicht gesetzt: %s", e)


class JsApi:
    """Funktionen, die das Frontend ueber window.pywebview.api aufrufen kann."""

    def open_external(self, url: str) -> None:
        if url.startswith(("http://", "https://")):
            webbrowser.open(url)


def main() -> int:
    log = setup_logging()
    lock = acquire_single_instance()
    if lock is None:
        message_box("AI Coach läuft bereits.")
        return 1

    import uvicorn
    import webview

    from db import models
    from db.server import app

    port = free_port()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_config=None, log_level="info"))
    thread = threading.Thread(target=server.run, name="api-server", daemon=True)
    thread.start()

    deadline = time.time() + 20
    while not server.started:
        if not thread.is_alive() or time.time() > deadline:
            log.error("Server konnte nicht gestartet werden")
            message_box("Der App-Server konnte nicht gestartet werden. Details: " + str(LOG_DIR / "app.log"))
            return 1
        time.sleep(0.05)
    log.info("Server läuft auf Port %s", port)

    windows_taskbar_identity()
    start_page = "index.html" if models.get_profile().get("onboarded") else "profile.html"
    window = webview.create_window(
        APP_TITLE, f"http://127.0.0.1:{port}/{start_page}", js_api=JsApi(),
        width=1320, height=880, min_size=(1040, 640), background_color="#0c0f16",
    )
    window.events.shown += lambda: set_window_icon(window, log)
    webview.start(private_mode=False, storage_path=str(DATA_DIR / "webview"))

    log.info("Fenster geschlossen, beende Server")
    server.should_exit = True
    thread.join(timeout=5)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:  # letzte Rettung: Fehler sichtbar machen statt still abzustuerzen
        logging.getLogger("ai_coach").exception("Unerwarteter Fehler")
        message_box(f"Unerwarteter Fehler: {e}\n\nDetails: {LOG_DIR / 'app.log'}")
        sys.exit(1)
