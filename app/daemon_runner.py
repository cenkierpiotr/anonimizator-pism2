"""Skrypt uruchamiający silnik anonimizacji z wykorzystaniem
bibliotek zbundlowanych w AnonimizatorPism na Windows lub ze środowiska Python.
"""

import os
import sys
from pathlib import Path

# Jeśli działamy w kontekście Windows obok zbudowanej aplikacji, użyj
# bibliotek z jej katalogu _internal (pyinstaller onedir) - szukamy w
# standardowej lokalizacji instalatora oraz względem tego pliku.
_candidates = [
    Path(os.environ.get("LOCALAPPDATA", "")) / "Programy" / "Anonimizator Pism" / "AnonimizatorPism" / "_internal",
    Path(__file__).resolve().parent.parent / "AnonimizatorPism" / "_internal",
    Path(__file__).resolve().parent.parent / "_internal",
]
for bundle_internal in _candidates:
    if bundle_internal.exists():
        sys.path.insert(0, str(bundle_internal / "base_library.zip"))
        sys.path.insert(0, str(bundle_internal))
        break

# Dodaj główny katalog projektu
current_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(current_dir))

from app.server import run_server

if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 4578
    run_server(port)
