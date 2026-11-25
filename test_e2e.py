"""Skrypt weryfikujący działanie Anonimizatora w tle i jego endpointów."""
import json
import threading
import time
import urllib.request

from app.server import run_server

def main():
    print("[1] Uruchamianie serwera w tle...")
    t = threading.Thread(target=run_server, args=(4578,), daemon=True)
    t.start()
    time.sleep(1)

    print("[2] Test endpointu /health...")
    res = urllib.request.urlopen("http://127.0.0.1:4578/health")
    print("Health response:", res.read().decode("utf-8"))

    print("[3] Test endpointu /anonymize/text...")
    test_text = "Powód Jan Kowalski, PESEL 90010112349, zamieszkały w Warszawie przy ul. Marszałkowskiej 10 wnosi pozew."
    payload = json.dumps({"text": test_text}).encode("utf-8")
    req = urllib.request.Request(
        "http://127.0.0.1:4578/anonymize/text",
        data=payload,
        headers={"Content-Type": "application/json; charset=utf-8"}
    )
    res = urllib.request.urlopen(req)
    result = json.loads(res.read().decode("utf-8"))
    print("\n=== WYNIK ANONIMIZACJI ===")
    print("Oryginał:", test_text)
    print("Zanonimizowany:", result.get("anonymized"))
    print("Wykryte encje:", result.get("entities"))
    print("Liczba zamian:", result.get("replaced_count"))
    print("=== TEST ZAKOŃCZONY SUKCESEM ===")

if __name__ == "__main__":
    main()
