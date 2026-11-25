"""Test dymny logiki GUI niewymagającej wyświetlania okna (worker wątku
roboczego) - patrz app/gui/main_window.py. Nie tworzy żadnego widgetu Tk,
więc działa w środowisku bez X11 (CI, ten kontener)."""

import queue
import threading
from pathlib import Path

import docx
import pytest

from app.gui.main_window import WorkerEvent, anonymize_worker
from app.main import AnonymizeOptions, PasswordRequiredError
from app.pipeline.leak_check import LeakDetectedError


@pytest.fixture
def sample_docx(tmp_path):
    path = tmp_path / "pozew.docx"
    document = docx.Document()
    document.add_paragraph("Powód Jan Kowalski, PESEL 44051401359, tel. 601-234-567.")
    document.save(path)
    return path


def test_anonymize_worker_puts_staged_event_on_success(sample_docx):
    result_queue: "queue.Queue[WorkerEvent]" = queue.Queue()
    cancel_event = threading.Event()

    anonymize_worker(sample_docx, AnonymizeOptions(), result_queue, cancel_event)

    event = result_queue.get_nowait()
    assert event.kind == "staged"
    assert event.path == sample_docx
    assert event.staged is not None
    assert event.staged.entity_count > 0
    assert result_queue.empty()

    # sprzątamy staging utworzony przez proces_to_staging w tym teście
    from app.main import discard_staged

    discard_staged(event.staged)


def test_anonymize_worker_respects_pre_set_cancel(sample_docx):
    result_queue: "queue.Queue[WorkerEvent]" = queue.Queue()
    cancel_event = threading.Event()
    cancel_event.set()

    anonymize_worker(sample_docx, AnonymizeOptions(), result_queue, cancel_event)

    event = result_queue.get_nowait()
    assert event.kind == "cancelled"
    assert event.path == sample_docx
    assert event.staged is None


def test_anonymize_worker_puts_password_required_event(tmp_path, monkeypatch):
    fake_path = tmp_path / "zaszyfrowany.pdf"
    fake_path.write_bytes(b"%PDF-1.4 fake")

    def fake_process_to_staging(path, options):
        raise PasswordRequiredError(f"Plik PDF '{Path(path).name}' jest zaszyfrowany hasłem.")

    monkeypatch.setattr("app.gui.main_window.process_to_staging", fake_process_to_staging)

    result_queue: "queue.Queue[WorkerEvent]" = queue.Queue()
    cancel_event = threading.Event()

    anonymize_worker(fake_path, AnonymizeOptions(), result_queue, cancel_event)

    event = result_queue.get_nowait()
    assert event.kind == "password_required"
    assert "hasłem" in event.message


def test_anonymize_worker_puts_error_event_on_leak_detected(tmp_path, monkeypatch):
    fake_path = tmp_path / "dokument.docx"
    fake_path.write_bytes(b"PK\x03\x04fake")

    def fake_process_to_staging(path, options):
        raise LeakDetectedError(findings=[])

    monkeypatch.setattr("app.gui.main_window.process_to_staging", fake_process_to_staging)

    result_queue: "queue.Queue[WorkerEvent]" = queue.Queue()
    cancel_event = threading.Event()

    anonymize_worker(fake_path, AnonymizeOptions(), result_queue, cancel_event)

    event = result_queue.get_nowait()
    assert event.kind == "error"
    assert "BLOKADA BEZPIECZEŃSTWA" in event.message
