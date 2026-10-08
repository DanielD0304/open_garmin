import os
import sys
import tempfile
from pathlib import Path

# Tests nie gegen die echte Datenbank im Benutzerordner laufen lassen
os.environ["AI_COACH_DATA"] = tempfile.mkdtemp(prefix="ai-coach-test-")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
