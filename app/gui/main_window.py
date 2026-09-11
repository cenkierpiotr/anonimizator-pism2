"""GUI aplikacji "Anonimizator Dokumentów" (CustomTkinter).

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
from tkinterdnd2 import DND_FILES, TkinterDnD

from app.gui import theme
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
from app.pipeline.temp_hygiene import cleanup_stale_staging_dirs

ctk.set_appearance_mode("light")
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
        self.title("Anonimizator Dokumentów")
        self.geometry("980x620")
        self.minsize(760, 480)

        self.items: dict[str, QueueItem] = {}  # klucz: str(path)
        self.result_queue: "queue.Queue[WorkerEvent]" = queue.Queue()
        self.cancel_event = threading.Event()
        self.active_thread: threading.Thread | None = None
        self.processing = False
        self.pending_keys: list[str] = []

        self._build_layout()
        self._setup_drag_and_drop()
        self.after(self.POLL_INTERVAL_MS, self._poll_queue)

    # -- przeciągnij i upuść --------------------------------------------

    def _setup_drag_and_drop(self) -> None:
        """Rejestruje listę plików jako cel drop - przeciągnięcie pliku/ów
        z eksploratora systemowego dodaje je do kolejki dokładnie tak samo
        jak przycisk "Dodaj pliki...". `TkinterDnD._require` ładuje
        natywną bibliotekę tkdnd do interpretera Tcl tego okna raz na start;
        samo `drop_target_register`/`dnd_bind` jest dostępne na KAŻDYM
        widgecie Tk (w tym CTk) od chwili zaimportowania `tkinterdnd2`, bo
        biblioteka podmienia je na poziomie `tkinter.BaseWidget` - nie trzeba
        żadnej specjalnej klasy okna głównego."""
        try:
            TkinterDnD._require(self)
        except RuntimeError as exc:
            # Brak natywnej biblioteki tkdnd dla tej platformy - funkcja
            # przeciągnij-i-upuść nie będzie dostępna, ale reszta aplikacji
            # (w tym przycisk "Dodaj pliki...") działa normalnie dalej.
            self.status_label.configure(
                text=f"Uwaga: przeciągnij i upuść niedostępne na tym systemie ({exc})."
            )
            return
        self.list_frame.drop_target_register(DND_FILES)
        self.list_frame.dnd_bind("<<Drop>>", self._on_drop)

    def _on_drop(self, event) -> None:
        raw_paths = self.list_frame.tk.splitlist(event.data)
        self._add_paths(Path(p) for p in raw_paths)

    # -- layout -------------------------------------------------------

    def _build_layout(self) -> None:
        self.configure(fg_color=theme.NEUTRAL_LIGHT)

        header = ctk.CTkFrame(self, fg_color="white", corner_radius=0, height=64)
        header.pack(side="top", fill="x")
        header.pack_propagate(False)

        logo = ctk.CTkLabel(
            header,
            text="AD",
            width=36,
            height=36,
            corner_radius=10,
            fg_color=theme.PRIMARY,
            text_color="white",
            font=ctk.CTkFont(family=theme.FONT_HEADLINE, size=14, weight="bold"),
        )
        logo.pack(side="left", padx=(18, 10), pady=14)

        title_box = ctk.CTkFrame(header, fg_color="transparent")
        title_box.pack(side="left", pady=10)
        ctk.CTkLabel(
            title_box,
            text="Anonimizator Dokumentów",
            anchor="w",
            text_color="#1F2A2A",
            font=ctk.CTkFont(family=theme.FONT_HEADLINE, size=16, weight="bold"),
        ).pack(anchor="w")
        ctk.CTkLabel(
            title_box,
            text="Bezpieczne usuwanie danych osobowych z dokumentów",
            anchor="w",
            text_color=theme.TEXT_MUTED,
            font=ctk.CTkFont(family=theme.FONT_BODY, size=11),
        ).pack(anchor="w")

        body = ctk.CTkFrame(self, fg_color=theme.NEUTRAL_LIGHT, corner_radius=0)
        body.pack(side="top", fill="both", expand=True)

        toolbar = ctk.CTkFrame(body, fg_color="transparent")
        toolbar.pack(side="top", fill="x", padx=16, pady=(14, 6))

        ctk.CTkButton(
            toolbar,
            text="Dodaj pliki...",
            command=self._on_add_files,
            corner_radius=theme.CORNER_RADIUS,
            fg_color=theme.PRIMARY,
            hover_color=theme.PRIMARY_DARK,
            font=ctk.CTkFont(family=theme.FONT_BODY, size=12, weight="bold"),
        ).pack(side="left", padx=(0, 8))
        ctk.CTkButton(
            toolbar,
            text="Anonimizuj zaznaczone",
            command=self._on_start_anonymize,
            corner_radius=theme.CORNER_RADIUS,
            fg_color=theme.PRIMARY,
            hover_color=theme.PRIMARY_DARK,
            font=ctk.CTkFont(family=theme.FONT_BODY, size=12, weight="bold"),
        ).pack(side="left", padx=8)

        self._secondary_button(
            toolbar, "Konwertuj do PDF", self._on_convert_to_pdf
        ).pack(side="left", padx=8)
        self._secondary_button(
            toolbar, "Zainstaluj obsługę .doc", self._on_install_libreoffice
        ).pack(side="left", padx=8)
        self.cancel_button = self._secondary_button(toolbar, "Anuluj", self._on_cancel)
        self.cancel_button.configure(state="disabled")
        self.cancel_button.pack(side="left", padx=8)
        self._secondary_button(
            toolbar, "Usuń zaznaczone z listy", self._on_remove_selected, danger=True
        ).pack(side="right")

        self.progress_bar = ctk.CTkProgressBar(
            body, mode="indeterminate", corner_radius=4, progress_color=theme.PRIMARY
        )
        self.progress_bar.pack(side="top", fill="x", padx=16, pady=(4, 4))
        self.progress_bar.set(0)

        self.status_label = ctk.CTkLabel(
            body,
            text="Gotowy.",
            anchor="w",
            text_color=theme.TEXT_MUTED,
            font=ctk.CTkFont(family=theme.FONT_BODY, size=11),
        )
        self.status_label.pack(side="top", fill="x", padx=18)

        ctk.CTkLabel(
            body,
            text="Kolejka plików",
            anchor="w",
            text_color="#1F2A2A",
            font=ctk.CTkFont(family=theme.FONT_HEADLINE, size=13, weight="bold"),
        ).pack(side="top", fill="x", padx=18, pady=(14, 4))

        self.list_frame = ctk.CTkScrollableFrame(
            body, fg_color=theme.NEUTRAL_LIGHT, label_text=""
        )
        self.list_frame.pack(side="top", fill="both", expand=True, padx=14, pady=(0, 14))
        self.list_frame.grid_columnconfigure(0, weight=1)

        self.empty_state_label = ctk.CTkLabel(
            self.list_frame,
            text="Brak plików w kolejce - użyj \"Dodaj pliki...\" albo przeciągnij je tutaj.",
            text_color=theme.TEXT_MUTED,
            font=ctk.CTkFont(family=theme.FONT_BODY, size=12),
        )
        self.empty_state_label.grid(row=0, column=0, pady=40)

        self.row_widgets: dict[str, dict] = {}

    def _secondary_button(
        self, parent, text: str, command, *, danger: bool = False
    ) -> ctk.CTkButton:
        return ctk.CTkButton(
            parent,
            text=text,
            command=command,
            corner_radius=theme.CORNER_RADIUS,
            fg_color="transparent",
            border_width=1,
            border_color=theme.DANGER if danger else theme.NEUTRAL_BORDER,
            text_color=theme.DANGER if danger else "#1F2A2A",
            hover_color=theme.DANGER_LIGHT if danger else theme.NEUTRAL_LIGHT,
            font=ctk.CTkFont(family=theme.FONT_BODY, size=12),
        )

    def _refresh_row(self, key: str) -> None:
        item = self.items[key]
        widgets = self.row_widgets[key]
        widgets["name_label"].configure(text=item.path.name)
        bg, fg, label = theme.status_badge_style(item.status.value)
        widgets["status_badge"].configure(text=label, fg_color=bg, text_color=fg)
        if item.status == FileStatus.DO_WERYFIKACJI:
            widgets["review_button"].configure(
                state="normal", fg_color=theme.PRIMARY, hover_color=theme.PRIMARY_DARK
            )
        else:
            widgets["review_button"].configure(
                state="disabled", fg_color=theme.NEUTRAL_BORDER, hover_color=theme.NEUTRAL_BORDER
            )

    def _add_row(self, item: QueueItem) -> None:
        key = str(item.path)
        row = len(self.row_widgets)
        item.row_index = row
        self.empty_state_label.grid_forget()

        card = ctk.CTkFrame(
            self.list_frame,
            fg_color="white",
            corner_radius=theme.CARD_CORNER_RADIUS,
            border_width=1,
            border_color=theme.NEUTRAL_BORDER,
        )
        card.grid(row=row, column=0, sticky="ew", padx=2, pady=4)
        card.grid_columnconfigure(2, weight=1)

        check_var = ctk.BooleanVar(value=True)
        checkbox = ctk.CTkCheckBox(
            card, text="", variable=check_var, width=20, fg_color=theme.PRIMARY, hover_color=theme.PRIMARY_DARK
        )
        checkbox.grid(row=0, column=0, padx=(12, 8), pady=12, sticky="w")

        type_color, type_label = theme.file_type_style(item.path.suffix)
        type_chip = ctk.CTkLabel(
            card,
            text=type_label,
            width=48,
            corner_radius=6,
            fg_color=type_color,
            text_color="white",
            font=ctk.CTkFont(family=theme.FONT_BODY, size=10, weight="bold"),
        )
        type_chip.grid(row=0, column=1, padx=(0, 10), pady=12)

        name_label = ctk.CTkLabel(
            card,
            text=item.path.name,
            anchor="w",
            text_color="#1F2A2A",
            font=ctk.CTkFont(family=theme.FONT_BODY, size=12),
        )
        name_label.grid(row=0, column=2, padx=4, pady=12, sticky="ew")

        bg, fg, label = theme.status_badge_style(item.status.value)
        status_badge = ctk.CTkLabel(
            card,
            text=label,
            corner_radius=999,
            fg_color=bg,
            text_color=fg,
            width=120,
            font=ctk.CTkFont(family=theme.FONT_BODY, size=11, weight="bold"),
        )
        status_badge.grid(row=0, column=3, padx=8, pady=12)

        review_button = ctk.CTkButton(
            card,
            text="Podgląd / zapisz",
            width=130,
            state="disabled",
            command=lambda k=key: self._open_review(k),
            corner_radius=theme.CORNER_RADIUS,
            fg_color=theme.NEUTRAL_BORDER,
            hover_color=theme.NEUTRAL_BORDER,
            text_color_disabled=theme.TEXT_MUTED,
            font=ctk.CTkFont(family=theme.FONT_BODY, size=11, weight="bold"),
        )
        review_button.grid(row=0, column=4, padx=(4, 12), pady=12)

        self.row_widgets[key] = {
            "card": card,
            "check_var": check_var,
            "name_label": name_label,
            "status_badge": status_badge,
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
        self._add_paths(Path(raw) for raw in paths)

    def _add_paths(self, paths) -> None:
        """Dodaje pliki do kolejki - współdzielone przez przycisk "Dodaj
        pliki..." i przeciągnij-i-upuść, żeby oba miały identyczne
        zachowanie (pomijanie duplikatów/katalogów)."""
        skipped_dirs = 0
        for path in paths:
            if path.is_dir():
                skipped_dirs += 1
                continue
            key = str(path)
            if key in self.items:
                continue
            item = QueueItem(path=path)
            self.items[key] = item
            self._add_row(item)
        if skipped_dirs:
            messagebox.showinfo(
                "Anonimizator Dokumentów",
                f"Pominięto {skipped_dirs} katalog(ów) - przeciągnij same pliki.",
            )

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
                widgets["card"].destroy()  # niszczy też wszystkie widgety-dzieci karty
                del self.row_widgets[key]
                staged = self.items[key].staged
                if staged is not None:
                    discard_staged(staged)
                del self.items[key]
        if not self.row_widgets:
            self.empty_state_label.grid(row=0, column=0, pady=40)
        self._relayout_rows()

    def _relayout_rows(self) -> None:
        for row, (key, widgets) in enumerate(self.row_widgets.items()):
            widgets["check_var"].get()  # no-op, keep var alive
        # CTkScrollableFrame nie ma prostego "compact" API - przy usuwaniu
        # zostawiamy odstępy grid (kosmetyczny drobiazg, nie wpływa na
        # poprawność), pełna rekonstrukcja siatki nie jest tego warta w V1.

    def _on_start_anonymize(self) -> None:
        if self.processing:
            messagebox.showinfo("Anonimizator Dokumentów", "Trwa już przetwarzanie kolejki.")
            return
        keys = self._selected_keys()
        if not keys:
            messagebox.showinfo("Anonimizator Dokumentów", "Zaznacz co najmniej jeden plik oczekujący.")
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
            messagebox.showinfo("Anonimizator Dokumentów", "Zaznacz co najmniej jeden plik do konwersji.")
            return
        output_dir = filedialog.askdirectory(title="Wybierz katalog docelowy dla plików PDF")
        if not output_dir:
            return
        paths = [self.items[key].path for key in keys]
        results = convert_many_to_pdf(paths, output_dir=output_dir)

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
                "Anonimizator Dokumentów", "Komponent LibreOffice zainstalowany pomyślnie."
            )
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror(
                "Anonimizator Dokumentów", f"Nie udało się zainstalować komponentu: {exc}"
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

        if staged.potentially_missed:
            missed_frame = ctk.CTkFrame(self)
            missed_frame.pack(side="top", fill="x", padx=14, pady=4)
            ctk.CTkLabel(
                missed_frame,
                text=(
                    "Potencjalnie pominięte (sprawdź ręcznie - nie zostały "
                    "automatycznie zanonimizowane):"
                ),
                font=ctk.CTkFont(weight="bold"),
                anchor="w",
                wraplength=760,
                justify="left",
            ).pack(anchor="w", padx=8, pady=(6, 0))
            for snippet in staged.potentially_missed[:20]:
                ctk.CTkLabel(
                    missed_frame, text=f"• ...{snippet}...", anchor="w", wraplength=760, justify="left"
                ).pack(anchor="w", padx=16, pady=2)

        if staged.uncertain_detections:
            uncertain_frame = ctk.CTkFrame(self)
            uncertain_frame.pack(side="top", fill="x", padx=14, pady=4)
            ctk.CTkLabel(
                uncertain_frame,
                text=(
                    "Niepewne trafienia (rozpoznane tylko po korekcie typowych "
                    "pomyłek OCR - sprawdź ręcznie w oryginale):"
                ),
                font=ctk.CTkFont(weight="bold"),
                anchor="w",
                wraplength=760,
                justify="left",
            ).pack(anchor="w", padx=8, pady=(6, 0))
            for note in staged.uncertain_detections[:20]:
                ctk.CTkLabel(
                    uncertain_frame, text=f"• {note}", anchor="w", wraplength=760, justify="left"
                ).pack(anchor="w", padx=16, pady=2)

        self.leak_ack_var: ctk.BooleanVar | None = None
        if staged.leak_findings:
            leak_frame = ctk.CTkFrame(self, fg_color="#7a1f1f")
            leak_frame.pack(side="top", fill="x", padx=14, pady=4)
            ctk.CTkLabel(
                leak_frame,
                text=(
                    "OSTRZEŻENIE: ponowne skanowanie zapisanego pliku wykryło dane, "
                    "które mogły przetrwać anonimizację:"
                ),
                font=ctk.CTkFont(weight="bold"),
                text_color="white",
                anchor="w",
                wraplength=760,
                justify="left",
            ).pack(anchor="w", padx=8, pady=(6, 0))
            for finding in staged.leak_findings:
                ctk.CTkLabel(
                    leak_frame,
                    text=f"• {finding.detector_name} x{finding.count} w {finding.part_name}",
                    text_color="white",
                    anchor="w",
                    wraplength=760,
                    justify="left",
                ).pack(anchor="w", padx=16, pady=2)
            self.leak_ack_var = ctk.BooleanVar(value=False)
            ctk.CTkCheckBox(
                leak_frame,
                text="Rozumiem ryzyko i chcę mimo to zapisać ten plik.",
                variable=self.leak_ack_var,
                text_color="white",
            ).pack(anchor="w", padx=8, pady=(4, 8))

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
            button_row,
            text="Odrzuć",
            fg_color="transparent",
            border_width=1,
            border_color=theme.NEUTRAL_BORDER,
            text_color="#1F2A2A",
            hover_color=theme.NEUTRAL_LIGHT,
            corner_radius=theme.CORNER_RADIUS,
            command=self._on_reject,
        ).pack(side="left")
        ctk.CTkButton(
            button_row,
            text="Zatwierdź i zapisz...",
            fg_color=theme.PRIMARY,
            hover_color=theme.PRIMARY_DARK,
            corner_radius=theme.CORNER_RADIUS,
            command=self._on_approve,
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
        if staged.leak_findings and (self.leak_ack_var is None or not self.leak_ack_var.get()):
            messagebox.showwarning(
                "Anonimizator Dokumentów",
                "Zaznacz checkbox 'Rozumiem ryzyko...' powyżej, żeby zapisać plik mimo ostrzeżenia.",
            )
            return
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
        messagebox.showinfo("Anonimizator Dokumentów", f"Zapisano: {output_path}")
        self.destroy()
        self.on_finished()


def main() -> None:
    cleanup_stale_staging_dirs()
    app = AnonymizerApp()
    app.mainloop()


if __name__ == "__main__":
    main()
