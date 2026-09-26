"""Testy warstwy GLiNER (`app/pipeline/gliner_layer.py`).

Pakiet `gliner` NIE jest zainstalowany w środowisku testowym (opcjonalna
zależność, patrz requirements.txt) - te testy sprawdzają wyłącznie kontrakt
niezależny od realnego modelu: obsługę brakującego pliku/pakietu przez
`GlinerUnavailableError`, oraz konwersję predykcji na `GlinerCandidate` przy
użyciu prostego fake modelu (bez importu `gliner`)."""

import pytest

from app.pipeline import gliner_layer
from app.pipeline.gliner_layer import GlinerCandidate, GlinerUnavailableError, find_gliner_candidates


def test_load_model_missing_file_raises_clear_error(tmp_path):
    missing_path = tmp_path / "nie_istnieje" / "model.onnx"

    with pytest.raises(GlinerUnavailableError, match="nie istnieje"):
        gliner_layer.load_model(str(missing_path))


def test_load_model_missing_package_raises_clear_error(tmp_path, monkeypatch):
    """Gdy plik modelu istnieje, ale pakiet `gliner` nie jest zainstalowany -
    czytelny błąd, nie goły ModuleNotFoundError."""
    model_file = tmp_path / "model_quantized.onnx"
    model_file.write_bytes(b"nie prawdziwy model, tylko test pliku")
    gliner_layer.load_model.cache_clear()

    with pytest.raises(GlinerUnavailableError, match="nie jest zainstalowany"):
        gliner_layer.load_model(str(model_file))


class _FakeGlinerModel:
    """Symuluje interfejs `GLiNER.predict_entities` bez importu prawdziwego
    pakietu - wystarczające do przetestowania konwersji wyników przez
    `find_gliner_candidates`, niezależnie od tego, czy `gliner` jest
    zainstalowany w środowisku, w którym odpalane są testy."""

    def __init__(self, predictions):
        self._predictions = predictions

    def predict_entities(self, text, labels, threshold=0.5):
        return self._predictions


def test_find_gliner_candidates_converts_predictions():
    text = "Umowę zawarto pomiędzy Janem Kowalskim a Fundacją Alfa."
    start = text.index("Janem Kowalskim")
    end = start + len("Janem Kowalskim")
    model = _FakeGlinerModel(
        [{"start": start, "end": end, "text": "Janem Kowalskim", "label": "legal_role_person", "score": 0.87}]
    )

    candidates = find_gliner_candidates(text, model)

    assert candidates == [
        GlinerCandidate(start=start, end=end, text="Janem Kowalskim", label="legal_role_person", score=0.87)
    ]


def test_find_gliner_candidates_empty_text_returns_empty_list():
    model = _FakeGlinerModel([{"start": 0, "end": 1, "text": "x", "label": "y", "score": 1.0}])

    assert find_gliner_candidates("   ", model) == []


def test_find_gliner_candidates_wraps_prediction_errors():
    class _BrokenModel:
        def predict_entities(self, text, labels, threshold=0.5):
            raise RuntimeError("silnik ONNX się wywalił")

    with pytest.raises(GlinerUnavailableError, match="Błąd predykcji"):
        find_gliner_candidates("jakiś tekst", _BrokenModel())
