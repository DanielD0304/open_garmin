**Start (Kurz)**

Kurzanleitung zum Starten der Open-Garmin-Umgebung lokal (Windows).

- Voraussetzungen:
  - Docker Desktop installiert und Engine läuft.
  - Python 3.11+ und virtuelles Environment (`venv`) im Projekt (`venv`).
  - PowerShell (für Skripte) oder Bash.

- 1) Python venv aktivieren

  Öffne ein Terminal im Projektordner und aktiviere das venv:

  ```powershell
  Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
  & .\venv\Scripts\Activate.ps1
  ```

- 2) Lokale API-Wrapper starten (nötig für n8n)

  ```powershell
  python .\db\http_server.py
  # läuft standardmäßig auf http://0.0.0.0:8765
  ```

- 3) n8n-Workflows importieren (Docker + Skript)

  ```powershell
  docker compose up -d n8n
  .\scripts\import_n8n_workflows.ps1
  ```

- 4) Ollama (optional, für Modell-Reports)
  - Docker (empfohlen):
    ```powershell
    docker run -d --name ollama -p 11434:11434 -v ollama:/root/.ollama ollama/ollama:latest
    ```
  - Oder portable Variante (kein Admin):
    ```powershell
    winget install --id Ollama.Ollama.Portable -e --accept-package-agreements --accept-source-agreements
    # dann im entpackten Ordner: ollama.exe serve
    ```

- 5) Frontend lokal starten (optional)

  ```powershell
  Set-Location .\frontend
  python -m http.server 8000
  # oder öffne frontend/index.html direkt im Browser
  ```

- Schnelltests / Endpunkte

  - Wrapper health: `http://localhost:8765/healthz`
  - n8n Editor: `http://localhost:5678`
  - Report webhook (Beispiel):
    `http://localhost:5678/webhook/report/generate?date=YYYY-MM-DD`
  - Ollama tags (wenn gestartet): `http://localhost:11434/api/tags`

- Hinweise
  - Wenn n8n Workflows nicht importiert werden, warte auf CLI-Readiness (Skript macht das automatisch).
  - Wenn Ollama nicht läuft, liefert der Wrapper einen Fallback-Report.
  - Firewall/Windows Defender kann Portfreigaben blockieren; erlaube ggf. die Ports 5678, 8765, 11434.

Weitere Details findest du in der Haupt-`README.md`.
