"""Lokalny serwer HTTP (daemon) dla wtyczki Chrome, Claude Desktop i Antigravity.
Udostępnia endpointy do anonimizacji tekstu oraz plików dokumentów w locie.
Działa na czystym standardowym module http.server bez dodatkowych zależności.

Bezpieczeństwo (daemon bez uwierzytelniania - świadomy kompromis dla wygody):
- nasłuch WYŁĄCZNIE na 127.0.0.1 (loopback) - niedostępny z sieci,
- limit rozmiaru ciała żądania (ochrona przed OOM/DoS),
- nazwa pliku sanitizowana do samej podstawy + whitelist rozszerzeń
  (ochrona przed path traversal i zapisem poza katalogiem tymczasowym),
- kontrola nagłówka Origin z allowlistą (ochrona przed żądaniami z
  dowolnej strony internetowej; wtyczka i integracje lokalne przechodzą),
- komunikaty błędów bez wewnętrznych ścieżek systemowych.
"""

from __future__ import annotations

import base64
import json
import os
import sys
import tempfile
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

# Ensure project root is always in sys.path
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from app.config import AppConfig
from app.main import AnonymizeOptions, anonymize_file
from app.pipeline.detect_all import detect_in_text
from app.pipeline.identity_cluster import IdentityRegistry

# Port daemona anonimizacji
DEFAULT_PORT = 4578

# Limit ciała żądania (base64 ~4/3 rozmiaru pliku; 64MB body wystarcza na
# dokumenty kilkadziesiąt MB i chroni przed OOM na gigabajtowych payloadach).
MAX_BODY_BYTES = 64 * 1024 * 1024

# Dozwolone rozszerzenia plików wejściowych (te same formaty co GUI).
_ALLOWED_SUFFIXES = {".docx", ".doc", ".odt", ".txt", ".pdf", ".jpg", ".jpeg", ".png", ".tif", ".tiff"}

# Windows: zarezerwowane nazwy urządzeń, których nie można użyć jako nazwy pliku.
_WIN_RESERVED_NAMES = {
    "con", "prn", "aux", "nul",
    *(f"com{i}" for i in range(1, 10)),
    *(f"lpt{i}" for i in range(1, 10)),
}

# Allowlista Originów: strony czatów AI (wtyczka RODO Guard wysyła fetch
# z content scriptu, więc Origin = origin strony, nie chrome-extension://),
# brak Origin (curl/integracje lokalne, np. Claude Desktop). Pozostałe
# originy są odrzucane - dowolna strona w internecie nie może wołać daemona.
_ALLOWED_ORIGIN_PREFIXES = (
    "https://claude.ai",
    "https://chatgpt.com",
    "https://chat.openai.com",
    "https://gemini.google.com",
    "https://aistudio.google.com",
    "https://console.anthropic.com",
    "chrome-extension://",
)


class AnonymizerHandler(BaseHTTPRequestHandler):
    def _origin_allowed(self) -> bool:
        """Zwraca True gdy żądanie pochodzi z dozwolonego kontekstu.

        Brak nagłówka Origin = klient non-browser (curl, integracje lokalne)
        - dozwolony. Obecny Origin musi pasować do allowlisty prefixów
        (konta czatów AI + rozszerzenia przeglądarki)."""
        origin = self.headers.get("Origin")
        if not origin:
            return True
        return origin.startswith(_ALLOWED_ORIGIN_PREFIXES)

    def _send_cors_headers(self) -> None:
        origin = self.headers.get("Origin")
        if origin and origin.startswith(_ALLOWED_ORIGIN_PREFIXES):
            # Echo znanego Originu zamiast wildcard - przeglądarka dopuści
            # tylko ten jeden origin, a inna strona nie dostanie nagłówka.
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        else:
            self.send_header("Access-Control-Allow-Origin", "null")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def do_OPTIONS(self) -> None:
        self.send_response(HTTPStatus.NO_CONTENT)
        self._send_cors_headers()
        self.end_headers()

    def _reject_request(self, status: HTTPStatus, message: str) -> None:
        self._send_json(status, {"error": message})

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            resp = {"status": "ok", "service": "AnonimizatorDokumentow-API", "version": "1.0.0"}
            self._send_json(HTTPStatus.OK, resp)
            return

        self.send_response(HTTPStatus.NOT_FOUND)
        self.end_headers()

    def do_POST(self) -> None:
        if not self._origin_allowed():
            self._reject_request(HTTPStatus.FORBIDDEN, "Niedozwolony origin żądania.")
            return

        parsed = urlparse(self.path)

        if parsed.path == "/anonymize/text":
            self._handle_anonymize_text()
        elif parsed.path == "/anonymize/file":
            self._handle_anonymize_file()
        else:
            self.send_response(HTTPStatus.NOT_FOUND)
            self._send_cors_headers()
            self.end_headers()

    def _read_body(self) -> bytes | None:
        """Czyta ciało żądania z limitem rozmiaru. Zwraca None i odsyła 413
        gdy klient przekroczył limit (żądanie odrzucone przed parsowaniem)."""
        try:
            content_length = int(self.headers.get("Content-Length", 0))
        except ValueError:
            self._reject_request(HTTPStatus.BAD_REQUEST, "Niepoprawny nagłówek Content-Length.")
            return None
        if content_length <= 0:
            self._reject_request(HTTPStatus.BAD_REQUEST, "Puste żądanie.")
            return None
        if content_length > MAX_BODY_BYTES:
            self._reject_request(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "Żądanie zbyt duże.")
            return None
        return self.rfile.read(content_length)

    def _handle_anonymize_text(self) -> None:
        try:
            body = self._read_body()
            if body is None:
                return

            data = json.loads(body.decode("utf-8"))
            raw_text = data.get("text", "")

            if not raw_text.strip():
                self._send_json(HTTPStatus.OK, {"anonymized": raw_text, "replaced_count": 0, "entities": []})
                return

            # Wykonaj anonimizację tekstu
            registry = IdentityRegistry()
            replacements = detect_in_text(raw_text, registry)

            # Podmień od tyłu według pozycji startowych
            result = raw_text
            for rep in sorted(replacements, key=lambda s: s.start, reverse=True):
                result = result[:rep.start] + rep.label + result[rep.end:]

            self._send_json(HTTPStatus.OK, {
                "anonymized": result,
                "replaced_count": len(replacements),
                "entities": [{"label": r.label, "category": r.category, "score": r.score} for r in replacements]
            })
        except Exception as exc:
            self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": f"Błąd anonimizacji tekstu: {exc}"})

    @staticmethod
    def _sanitize_filename(raw_name: object) -> str | None:
        """Zwraca bezpieczną nazwę pliku (sama baza, dozwolone rozszerzenie,
        nie zaczyna się od kropki, nie jest nazwą zarezerwowaną na Windows),
        albo None gdy nazwa nie przechodzi walidacji."""
        if not isinstance(raw_name, str):
            return None
        # Sama baza - odcina całą ścieżkę (traversal ../../, \\, absolutne).
        safe = Path(raw_name.replace("\\", "/")).name
        if not safe or safe.startswith("."):
            return None
        if Path(safe).stem.lower() in _WIN_RESERVED_NAMES:
            return None
        if Path(safe).suffix.lower() not in _ALLOWED_SUFFIXES:
            return None
        return safe

    def _handle_anonymize_file(self) -> None:
        """Anonimizuje plik przekazany w formacie base64 JSON."""
        tmp_dir = None
        try:
            body = self._read_body()
            if body is None:
                return

            data = json.loads(body.decode("utf-8"))
            filename = self._sanitize_filename(data.get("filename", ""))
            if filename is None:
                self._reject_request(
                    HTTPStatus.BAD_REQUEST,
                    "Niepoprawna nazwa pliku (dozwolone rozszerzenia: " + ", ".join(sorted(_ALLOWED_SUFFIXES)) + ").",
                )
                return
            file_b64 = data.get("content_base64", "")
            file_bytes = base64.b64decode(file_b64, validate=False)

            with tempfile.TemporaryDirectory() as tmp_dir:
                tmp_in = Path(tmp_dir) / filename
                tmp_out = Path(tmp_dir) / f"zanonimizowany_{filename}"
                # Wyjście pipeline'u to zawsze .docx (patrz app/main.py).
                if tmp_out.suffix.lower() != ".docx":
                    tmp_out = tmp_out.with_suffix(".docx")

                tmp_in.write_bytes(file_bytes)
                res = anonymize_file(tmp_in, tmp_out)

                out_bytes = tmp_out.read_bytes()
                out_b64 = base64.b64encode(out_bytes).decode("utf-8")

                self._send_json(HTTPStatus.OK, {
                    "output_filename": tmp_out.name,
                    "content_base64": out_b64,
                    "entity_count": res.entity_count,
                    "warnings": res.warnings
                })
        except Exception as exc:
            # Bez ścieżek systemowych w odpowiedzi - tylko klasa błędu.
            self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": f"Błąd anonimizacji pliku: {type(exc).__name__}"})

    def _send_json(self, status: HTTPStatus, data: dict) -> None:
        encoded = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self._send_cors_headers()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, format: str, *args) -> None:  # noqa: A002 - nazwa parametru z klasy bazowej
        """Cichsze logi: bez pełnych URL-i, tylko metoda + ścieżka + status."""
        print(f"[daemon] {self.command} {self.path} -> {args[0] if args else ''}")


def run_server(port: int = DEFAULT_PORT) -> None:
    server_address = ("127.0.0.1", port)
    httpd = ThreadingHTTPServer(server_address, AnonymizerHandler)
    print(f"[*] Anonimizator Server działa na http://127.0.0.1:{port}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Anonimizator Local HTTP Server")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Port to listen on")
    parser.add_argument("pos_port", nargs="?", type=int, default=None, help="Positional port")
    args = parser.parse_args()
    port = args.pos_port if args.pos_port is not None else args.port
    run_server(port)
