"""GUI aplikacji "Anonimizator Pism" (CustomTkinter).

Spina istniejący, gotowy backend (`app.main`, `app.pipeline.convert_to_pdf`) -
ten moduł NIE implementuje żadnej logiki anonimizacji/detekcji, wyłącznie
interfejs użytkownika i wątkowanie.

Kluczowe elementy zgodne z planem (patrz plan, sekcje "Wydajność i
responsywność GUI" oraz punkt 7 "Jakość detekcji i warstwa bezpieczeństwa"):

- Kolejka wielu plików jednocześnie, z widocznym statusem każdego.
- Osobny tryb "Konwertuj do PDF", niezależny od anonimizacji.
- Pipeline (`process_to_staging`) uruchamiany w osobnym `threading.Thread`,
  NIGDY w wątku głównym Tk - inaczej okno "nie odpowiada" przy OCR wielu
  stron. Komunikacja worker -> GUI przez `queue.Queue`, odpytywaną przez
  `after()` w wątku głównym (standardowy, bezpieczny wzorzec dla Tk).
- Obowiązkowy ekran podglądu przed zapisem: dopóki użytkownik nie kliknie
  "Zatwierdź i zapisz" (-> `finalize_staged`) albo "Odrzuć"
  (-> `discard_staged`), żaden plik nie ląduje na dysku docelowym.

TODO (świadomie odłożone, patrz zadanie): klasa "podejrzane, nieoznaczone"
(punkt 6 sekcji jakości detekcji w planie) - podświetlanie tokenów z wielkiej
litery nie złapanych przez żadną warstwę detekcji. Backend obecnie nie
udostępnia takiej listy w `StagedAnonymization`, więc GUI też jej nie pokazuje.
"""

from __future__ import annotations

import queue
import threading
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Callable

import customtkinter as ctk
from tkinter import filedialog, messagebox

from app.main import (
    AnonymizeOptions,
    PasswordRequiredError,
    StagedAnonymization,
    discard_staged,
    finalize_staged,
    process_to_staging,
)
from app.pipeline.convert_to_pdf import convert_many_to_pdf
from app.pipeline.format_detect import UnsupportedDocumentError
from app.pipeline.legacy_convert import LibreOfficeNotAvailableError, download_libreoffice
from app.pipeline.leak_check import LeakDetectedError
from app.pipeline.metadata_scrub import neutral_output_filename

ctk.set_appearance_mode("system")
ctk.set_default_color_theme("blue")


class FileStatus(str, Enum):
    OCZEKUJE = "oczekuje"
    PRZETWARZANIE = "przetwarzanie..."
    DO_WERYFIKACJI = "do weryfikacji"
    ZAPISANY = "zapisany"
    BLAD = "błąd"
    POMINIETY = "pominięty"


@dataclass
class QueueItem:
    """Jeden plik w kolejce GUI - stan widoczny w liście, niezależny od
    wątku roboczego (worker operuje na `Path`, nie na tym obiekcie)."""

    path: Path
    status: FileStatus = FileStatus.OCZEKUJE
    staged: StagedAnonymization | None = None
    error: str | None = None
    row_index: int = -1


# ---------------------------------------------------------------------------
# Warstwa non-GUI: worker wątku roboczego, testowalna bez tworzenia okna Tk.
# ---------------------------------------------------------------------------


@dataclass
class WorkerEvent:
    """Zdarzenie wrzucane przez wątek roboczy do kolejki, odbierane przez
    pętlę główną Tk. `kind` rozróżnia typ zdarzenia; pola nieużywane w danym
    typie zostają domyślne."""

    kind: str  # "staged" | "password_required" | "error" | "cancelled"
    path: Path
    staged: StagedAnonymization | None = None
    error: Exception | None = None
    message: str = ""


def anonymize_worker(
    path: Path,
    options: AnonymizeOptions,
    result_queue: "queue.Queue[WorkerEvent]",
    cancel_event: threading.Event,
) -> None:
    """Uruchamiane w osobnym wątku: woła `process_to_staging` dla JEDNEGO
    pliku i wrzuca wynik/błąd do `result_queue`. Nie dotyka żadnego widgetu
    Tk bezpośrednio - to jest cały sens rozdzielenia przez kolejkę.

    `cancel_event` jest sprawdzany tylko przed startem (backend nie ma haków
    do przerywania w trakcie OCR/detekcji) - jeśli już ustawiony, worker
    kończy natychmiast bez wołania pipeline'u.
    """
    if cancel_event.is_set():
        result_queue.put(WorkerEvent(kind="cancelled", path=path))
        return
    try:
        staged = process_to_staging(path, options)
        if cancel_event.is_set():
            # Użytkownik anulował w międzyczasie - sprzątamy staging od razu,
            # zamiast zostawiać nieużywany katalog tymczasowy.
            discard_staged(staged)
            result_queue.put(WorkerEvent(kind="cancelled", path=path))
            return
        result_queue.put(WorkerEvent(kind="staged", path=path, staged=staged))
    except PasswordRequiredError as exc:
        result_queue.put(WorkerEvent(kind="password_required", path=path, error=exc, message=str(exc)))
    except Exception as exc:  # noqa: BLE001 - kolejka wieloplikowa musi kontynuować mimo błędu 1 pliku
        result_queue.put(
            WorkerEvent(kind="error", path=path, error=exc, message=_format_error(exc))
        )


def _format_error(exc: Exception) -> str:
    """Czytelny komunikat dla użytkownika - NIGDY nie loguje treści dokumentu,
    tylko typ błędu i jego opis (patrz plan, "Higiena plików tymczasowych")."""
    if isinstance(exc, UnsupportedDocumentError):
        return f"Nieobsługiwany lub uszkodzony format pliku: {exc}"
    if isinstance(exc, LibreOfficeNotAvailableError):
        return (
            "Ten plik wymaga dodatkowego komponentu LibreOffice (obsługa .doc/.odt), "
            "który nie jest jeszcze pobrany. Użyj przycisku 'Zainstaluj obsługę .doc'."
        )
    if isinstance(exc, LeakDetectedError):
        return (
            "BLOKADA BEZPIECZEŃSTWA: wykryto dane, które przetrwałyby anonimizację. "
            f"Plik NIE został zapisany. Szczegóły: {exc}"
        )
    return f"{type(exc).__name__}: {exc}"


class AnonymizerApp(ctk.CTk):
    """Główne okno aplikacji."""

    POLL_INTERVAL_MS = 150

    def __init__(self) -> None:
        super().__init__()
        self.title("Anonimizator Pism")
        self.geometry("980x620")
        self.minsize(760, 480)

        self.items: dict[str, QueueItem] = {}  # klucz: str(path)
        self.result_queue: "queue.Queue[WorkerEvent]" = queue.Queue()
        self.cancel_event = threading.Event()
        self.active_thread: threading.Thread | None = None
        self.processing = False
        self.pending_keys: list[str] = []

        self._build_layout()
        self.after(self.POLL_INTERVAL_MS, self._poll_queue)

    # -- layout -------------------------------------------------------

    def _build_layout(self) -> None:
        toolbar = ctk.CTkFrame(self)
        toolbar.pack(side="top", fill="x", padx=10, pady=(10, 5))

        ctk.CTkButton(toolbar, text="Dodaj pliki...", command=self._on_add_files).pack(
            side="left", padx=(0, 8)
        )
        ctk.CTkButton(
            toolbar, text="Anonimizuj zaznaczone", command=self._on_start_anonymize
        ).pack(side="left", padx=8)
        ctk.CTkButton(
            toolbar, text="Konwertuj do PDF", command=self._on_convert_to_pdf
        ).pack(side="left", padx=8)
        ctk.CTkButton(
            toolbar, text="Zainstaluj obsługę .doc", command=self._on_install_libreoffice
        ).pack(side="left", padx=8)
        self.cancel_button = ctk.CTkButton(
            toolbar, text="Anuluj", command=self._on_cancel, state="disabled"
        )
        self.cancel_button.pack(side="left", padx=8)
        ctk.CTkButton(
            toolbar, text="Usuń zaznaczone z listy", command=self._on_remove_selected
        ).pack(side="right")

        self.progress_bar = ctk.CTkProgressBar(self, mode="indeterminate")
        self.progress_bar.pack(side="top", fill="x", padx=10, pady=(0, 5))
        self.progress_bar.set(0)

        self.status_label = ctk.CTkLabel(self, text="Gotowy.", anchor="w")
        self.status_label.pack(side="top", fill="x", padx=12)

        self.list_frame = ctk.CTkScrollableFrame(self, label_text="Kolejka plików")
        self.list_frame.pack(side="top", fill="both", expand=True, padx=10, pady=10)
        self.list_frame.grid_columnconfigure(1, weight=1)

        self.row_widgets: dict[str, dict] = {}

    def _refresh_row(self, key: str) -> None:
        item = self.items[key]
        widgets = self.row_widgets[key]
        widgets["name_label"].configure(text=item.path.name)
        widgets["status_label"].configure(text=item.status.value)
        if item.status == FileStatus.DO_WERYFIKACJI:
            widgets["review_button"].configure(state="normal")
        else:
            widgets["review_button"].configure(state="disabled")

    def _add_row(self, item: QueueItem) -> None:
        key = str(item.path)
        row = len(self.row_widgets)
        item.row_index = row

        check_var = ctk.BooleanVar(value=True)
        checkbox = ctk.CTkCheckBox(self.list_frame, text="", variable=check_var, width=20)
        checkbox.grid(row=row, column=0, padx=(4, 4), pady=3, sticky="w")

        name_label = ctk.CTkLabel(self.list_frame, text=item.path.name, anchor="w")
        name_label.grid(row=row, column=1, padx=4, pady=3, sticky="ew")

        status_label = ctk.CTkLabel(self.list_frame, text=item.status.value, anchor="w", width=140)
        status_label.grid(row=row, column=2, padx=4, pady=3, sticky="w")

        review_button = ctk.CTkButton(
            self.list_frame,
            text="Podgląd / zapisz",
            width=130,
            state="disabled",
            command=lambda k=key: self._open_review(k),
        )
        review_button.grid(row=row, column=3, padx=4, pady=3)

        self.row_widgets[key] = {
            "check_var": check_var,
            "name_label": name_label,
            "status_label": status_label,
            "review_button": review_button,
        }

    # -- akcje toolbar --------------------------------------------------

    def _on_add_files(self) -> None:
        paths = filedialog.askopenfilenames(
            title="Wybierz dokumenty do anonimizacji",
            filetypes=[
                ("Dokumenty", "*.docx *.doc *.odt *.txt *.pdf *.jpg *.jpeg *.png *.tif *.tiff *.bmp"),
                ("Wszystkie pliki", "*.*"),
            ],
        )
        for raw in paths:
            path = Path(raw)
            key = str(path)
            if key in self.items:
                continue
            item = QueueItem(path=path)
            self.items[key] = item
            self._add_row(item)

    def _selected_keys(self) -> list[str]:
        return [
            key
            for key, widgets in self.row_widgets.items()
            if widgets["check_var"].get()
            and self.items[key].status in (FileStatus.OCZEKUJE, FileStatus.BLAD)
        ]

    def _on_remove_selected(self) -> None:
        for key, widgets in list(self.row_widgets.items()):
            if widgets["check_var"].get():
                for w in widgets.values():
                    if hasattr(w, "destroy"):
                        w.destroy()
                del self.row_widgets[key]
                staged = self.items[key].staged
                if staged is not None:
                    discard_staged(staged)
                del self.items[key]
        self._relayout_rows()

    def _relayout_rows(self) -> None:
        for row, (key, widgets) in enumerate(self.row_widgets.items()):
            widgets["check_var"].get()  # no-op, keep var alive
        # CTkScrollableFrame nie ma prostego "compact" API - przy usuwaniu
        # zostawiamy odstępy grid (kosmetyczny drobiazg, nie wpływa na
        # poprawność), pełna rekonstrukcja siatki nie jest tego warta w V1.

    def _on_start_anonymize(self) -> None:
        if self.processing:
            messagebox.showinfo("Anonimizator Pism", "Trwa już przetwarzanie kolejki.")
            return
        keys = self._selected_keys()
        if not keys:
            messagebox.showinfo("Anonimizator Pism", "Zaznacz co najmniej jeden plik oczekujący.")
            return
        self.cancel_event = threading.Event()
        self.pending_keys = keys
        self.processing = True
        self.cancel_button.configure(state="normal")
        self.progress_bar.configure(mode="indeterminate")
        self.progress_bar.start()
        self._process_next()

    def _process_next(self) -> None:
        if not self.pending_keys:
            self.processing = False
            self.cancel_button.configure(state="disabled")
            self.progress_bar.stop()
            self.progress_bar.set(0)
            self.status_label.configure(text="Gotowy.")
            return
        key = self.pending_keys.pop(0)
        item = self.items[key]
        item.status = FileStatus.PRZETWARZANIE
        self._refresh_row(key)
        self.status_label.configure(text=f"Przetwarzanie: {item.path.name}")

        options = AnonymizeOptions()
        self.active_thread = threading.Thread(
            target=anonymize_worker,
            args=(item.path, options, self.result_queue, self.cancel_event),
            daemon=True,
        )
        self.active_thread.start()

    def _on_cancel(self) -> None:
        self.cancel_event.set()
        self.status_label.configure(text="Anulowanie... (bieżący plik dokończy przetwarzanie)")

    def _on_convert_to_pdf(self) -> None:
        keys = [
            key
            for key, widgets in self.row_widgets.items()
            if widgets["check_var"].get()
        ]
        if not keys:
            messagebox.showinfo("Anonimizator Pism", "Zaznacz co najmniej jeden plik do konwersji.")
            return
        output_dir = filedialog.askdirectory(title="Wybierz katalog docelowy dla plików PDF")
        if not output_dir:
            return
        paths = [self.items[key].path for key in keys]
        try:
            results = convert_many_to_pdf(paths, output_dir=output_dir)
        except LibreOfficeNotAvailableError:
            messagebox.showerror(
                "Anonimizator Pism",
                "Konwersja do PDF wymaga komponentu LibreOffice - użyj przycisku "
                "'Zainstaluj obsługę .doc' najpierw.",
            )
            return

        ok = sum(1 for _, out, err in results if err is None)
        failed = [(inp, err) for inp, out, err in results if err is not None]
        message = f"Skonwertowano {ok}/{len(results)} plik(ów) do PDF."
        if failed:
            details = "\n".join(f"- {inp.name}: {_format_error(err)}" for inp, err in failed)
            message += f"\n\nBłędy:\n{details}"
        messagebox.showinfo("Konwersja do PDF", message)

    def _on_install_libreoffice(self) -> None:
        try:
            download_libreoffice()
            messagebox.showinfo(
                "Anonimizator Pism", "Komponent LibreOffice zainstalowany pomyślnie."
            )
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror(
                "Anonimizator Pism", f"Nie udało się zainstalować komponentu: {exc}"
            )

    # -- pętla odpytywania kolejki (uruchamiana przez after() w wątku Tk) --

    def _poll_queue(self) -> None:
        try:
            while True:
                event = self.result_queue.get_nowait()
                self._handle_event(event)
        except queue.Empty:
            pass
        self.after(self.POLL_INTERVAL_MS, self._poll_queue)

    def _handle_event(self, event: WorkerEvent) -> None:
        key = str(event.path)
        item = self.items.get(key)
        if item is None:
            return  # plik usunięty z kolejki w międzyczasie

        if event.kind == "staged":
            item.staged = event.staged
            item.status = FileStatus.DO_WERYFIKACJI
        elif event.kind == "cancelled":
            item.status = FileStatus.POMINIETY
        elif event.kind == "password_required":
            item.status = FileStatus.BLAD
            item.error = "Plik PDF wymaga hasła - podaj je i spróbuj ponownie."
            self._prompt_password_retry(key)
        elif event.kind == "error":
            item.status = FileStatus.BLAD
            item.error = event.message

        self._refresh_row(key)
        if item.status == FileStatus.BLAD and event.kind == "error":
            messagebox.showerror("Błąd przetwarzania", f"{item.path.name}:\n{item.error}")

        self._process_next()

    def _prompt_password_retry(self, key: str) -> None:
        item = self.items[key]
        dialog = ctk.CTkInputDialog(
            text=f"Plik '{item.path.name}' jest zaszyfrowany hasłem. Podaj hasło:",
            title="Hasło wymagane",
        )
        password = dialog.get_input()
        if not password:
            return
        item.status = FileStatus.PRZETWARZANIE
        self._refresh_row(key)
        options = AnonymizeOptions(pdf_password=password)
        thread = threading.Thread(
            target=anonymize_worker,
            args=(item.path, options, self.result_queue, self.cancel_event),
            daemon=True,
        )
        thread.start()

    # -- ekran weryfikacji / podglądu ------------------------------------

    def _open_review(self, key: str) -> None:
        item = self.items[key]
        if item.staged is None:
            return
        ReviewWindow(self, item, on_finished=lambda: self._on_review_finished(key))

    def _on_review_finished(self, key: str) -> None:
        item = self.items.get(key)
        if item is None:
            return
        self._refresh_row(key)


class ReviewWindow(ctk.CTkToplevel):
    """Obowiązkowy ekran podglądu przed zapisem (patrz plan, punkt 7 sekcji
    "Jakość detekcji i warstwa bezpieczeństwa" - najważniejszy pojedynczy
    element GUI). Dopóki użytkownik nie kliknie "Zatwierdź i zapisz" albo
    "Odrzuć", plik zostaje wyłącznie w katalogu tymczasowym stagingu."""

    def __init__(self, parent: AnonymizerApp, item: QueueItem, on_finished: Callable[[], None]) -> None:
        super().__init__(parent)
        self.parent_app = parent
        self.item = item
        self.on_finished = on_finished
        self.title(f"Podgląd przed zapisem - {item.path.name}")
        self.geometry("820x640")

        staged = item.staged
        assert staged is not None

        header = ctk.CTkLabel(
            self,
            text=f"Wykryto i zanonimizowano {staged.entity_count} encji.",
            font=ctk.CTkFont(size=15, weight="bold"),
        )
        header.pack(side="top", anchor="w", padx=14, pady=(14, 4))

        if staged.warnings:
            warn_frame = ctk.CTkFrame(self)
            warn_frame.pack(side="top", fill="x", padx=14, pady=4)
            ctk.CTkLabel(warn_frame, text="Ostrzeżenia:", font=ctk.CTkFont(weight="bold")).pack(
                anchor="w", padx=8, pady=(6, 0)
            )
            for warning in staged.warnings:
                ctk.CTkLabel(warn_frame, text=f"• {warning}", anchor="w", wraplength=760, justify="left").pack(
                    anchor="w", padx=16, pady=2
                )

        ctk.CTkLabel(self, text="Podgląd zanonimizowanego tekstu:", anchor="w").pack(
            side="top", fill="x", padx=14, pady=(8, 2)
        )
        text_box = ctk.CTkTextbox(self, wrap="word")
        text_box.pack(side="top", fill="both", expand=True, padx=14, pady=(0, 8))
        try:
            preview = staged.preview_text()
        except Exception as exc:  # noqa: BLE001
            preview = f"(nie udało się wczytać podglądu: {exc})"
        text_box.insert("1.0", preview)
        text_box.configure(state="disabled")

        button_row = ctk.CTkFrame(self)
        button_row.pack(side="bottom", fill="x", padx=14, pady=14)

        ctk.CTkButton(
            button_row, text="Odrzuć", fg_color="gray40", command=self._on_reject
        ).pack(side="left")
        ctk.CTkButton(
            button_row, text="Zatwierdź i zapisz...", command=self._on_approve
        ).pack(side="right")

        self.grab_set()  # modalne - decyzja o zapisie musi być świadoma i jednoznaczna

    def _on_reject(self) -> None:
        try:
            discard_staged(self.item.staged)
        finally:
            self.item.staged = None
            self.item.status = FileStatus.POMINIETY
            self.destroy()
            self.on_finished()

    def _on_approve(self) -> None:
        staged = self.item.staged
        assert staged is not None
        output_path = filedialog.asksaveasfilename(
            title="Zapisz zanonimizowany dokument",
            initialfile=neutral_output_filename(),
            defaultextension=".docx",
            filetypes=[("Dokument Word", "*.docx")],
        )
        if not output_path:
            return  # użytkownik anulował dialog zapisu - staging zostaje, okno wciąż otwarte
        try:
            finalize_staged(staged, output_path)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Błąd zapisu", f"Nie udało się zapisać pliku:\n{exc}")
            return
        self.item.staged = None
        self.item.status = FileStatus.ZAPISANY
        messagebox.showinfo("Anonimizator Pism", f"Zapisano: {output_path}")
        self.destroy()
        self.on_finished()


def main() -> None:
    app = AnonymizerApp()
    app.mainloop()


if __name__ == "__main__":
    main()
