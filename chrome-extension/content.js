/**
 * Anonimizator Pism & RODO Guard - Content Script
 * Przechwytuje wklejanie tekstu (Paste) oraz przeciąganie plików (Drag & Drop)
 * w oknach czatów AI i wyświetla monit z potwierdzeniem.
 *
 * Zasady bezpieczeństwa danych użytkownika:
 * - oryginalny tekst/plik jest NIGDY niegubiony: przy martwym serwerze,
 *   błędzie sieci/anonimizacji lub odmowie wstawiamy oryginał,
 * - preventDefault na paste wykonuje się SYNCHRONICZNIE (clipboardData
 *   bywa unieważniony po await), dopiero potem lecą żądania async,
 * - wszystkie fetch'e mają twardy timeout 5 s (AbortController) - wtyczka
 *   nigdy nie wisi, gdy daemon padł.
 */

const API_URL = "http://127.0.0.1:4578";
const FETCH_TIMEOUT_MS = 5000;

// Blokada równoległych operacji: ustawiana PRZED pokazaniem modala,
// zdejmowana dopiero PO zakończeniu wstawiania (nie na sztywny timer).
let isAnonymizing = false;

// Flaga pętli drop: syntetyczny DragEvent("drop") dispatchowany przez nas
// samych nie może ponownie wejść w handleDrop (nieskończona rekurencja).
let isDispatchingSyntheticDrop = false;

// Dozwolone formaty plików (zgodne z whitelistą daemona app/server.py).
const ALLOWED_FILE_EXTENSIONS = ["docx", "doc", "odt", "txt", "pdf", "jpg", "jpeg", "png", "tif", "tiff"];
const DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document";

// ---------------------------------------------------------------------------
// Pomocnicze
// ---------------------------------------------------------------------------

function escapeHtml(str) {
  return str
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function formatBytes(bytes) {
  if (bytes >= 1024 * 1024) return (bytes / (1024 * 1024)).toFixed(1) + " MB";
  if (bytes >= 1024) return (bytes / 1024).toFixed(1) + " KB";
  return bytes + " B";
}

/** fetch z twardym timeoutem - zwraca Response albo rzuca po FETCH_TIMEOUT_MS. */
async function fetchWithTimeout(url, options = {}) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), FETCH_TIMEOUT_MS);
  try {
    return await fetch(url, { ...options, signal: controller.signal });
  } finally {
    clearTimeout(timer);
  }
}

function arrayBufferToBase64(buffer) {
  const bytes = new Uint8Array(buffer);
  let binary = "";
  const CHUNK = 32768; // unikaj stack overflow na dużych plikach
  for (let i = 0; i < bytes.length; i += CHUNK) {
    binary += String.fromCharCode.apply(null, bytes.subarray(i, i + CHUNK));
  }
  return btoa(binary);
}

function base64ToBlob(base64, mime) {
  const binary = atob(base64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
  return new Blob([bytes], { type: mime });
}

async function getAutoAnonymizeSetting() {
  return new Promise((resolve) => {
    try {
      chrome.storage.sync.get(["autoAnonymize"], (data) => resolve(!!data.autoAnonymize));
    } catch {
      resolve(false); // storage niedostępny = traktuj jak "zawsze pytaj"
    }
  });
}

async function setAutoAnonymize(value) {
  try {
    await chrome.storage.sync.set({ autoAnonymize: value });
  } catch {
    /* niedostępne - po prostu nie zapamiętamy */
  }
}

// ---------------------------------------------------------------------------
// Toast (nie alert - nie blokuje strony)
// ---------------------------------------------------------------------------

/**
 * showToast(msg, {href, label}) - opcjonalny link do pobrania pliku.
 * Zwraca funkcję przedłużającą życie toastu (np. po zakończeniu anonimizacji).
 */
function showToast(msg, download = null) {
  const old = document.getElementById("anonim-toast");
  if (old) old.remove();

  const toast = document.createElement("div");
  toast.id = "anonim-toast";
  toast.className = "anonim-toast";
  toast.textContent = "🛡️ " + msg;

  if (download && download.href && download.label) {
    const a = document.createElement("a");
    a.href = download.href;
    a.download = download.filename || "";
    a.textContent = download.label;
    a.style.cssText = "color:#7dd3fc;margin-left:10px;text-decoration:underline;cursor:pointer;";
    toast.appendChild(a);
    // Toast z akcją nie znika sam - użytkownik potrzebuje czasu na klik.
    return () => toast.remove();
  }

  const timer = setTimeout(() => toast.remove(), 4000);
  return () => { clearTimeout(timer); toast.remove(); };
}

// ---------------------------------------------------------------------------
// Daemon API
// ---------------------------------------------------------------------------

async function checkServerHealth() {
  try {
    const res = await fetchWithTimeout(`${API_URL}/health`, { method: "GET", cache: "no-store" });
    return res.ok;
  } catch {
    return false;
  }
}

async function requestAnonymizeText(text) {
  const res = await fetchWithTimeout(`${API_URL}/anonymize/text`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

async function requestAnonymizeFile(filename, contentBase64) {
  const res = await fetchWithTimeout(`${API_URL}/anonymize/file`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ filename, content_base64: contentBase64 }),
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

// ---------------------------------------------------------------------------
// Wstawianie treści w pole czatu
// ---------------------------------------------------------------------------

/**
 * Wstawia tekst do zapamiętanego pola. ProseMirror/contenteditable wymaga
 * focusu + execCommand (symulacja klawiatury), textarea/input idzie przez
 * value + Event("input") (React/controlled components tego wymagają).
 */
function insertTextIntoElement(target, text) {
  try {
    if (target && typeof target.focus === "function") target.focus();
    if (target && target.isContentEditable) {
      document.execCommand("insertText", false, text);
    } else if (target && "selectionStart" in target) {
      const start = target.selectionStart ?? target.value.length;
      const end = target.selectionEnd ?? target.value.length;
      target.value = target.value.slice(0, start) + text + target.value.slice(end);
      target.selectionStart = target.selectionEnd = start + text.length;
      target.dispatchEvent(new Event("input", { bubbles: true }));
    } else if (target) {
      document.execCommand("insertText", false, text);
    } else {
      // Pole zniknęło (SPA przerysowała DOM) - ostatnia deska: schowek.
      navigator.clipboard?.writeText(text).catch(() => {});
      showToast("Nie znaleziono pola czatu - tekst skopiowano do schowka.");
    }
  } catch (err) {
    console.warn("[Anonimizator] insertTextIntoElement:", err);
  }
}

/**
 * Próbuje "wrzucić" zanonimizowany plik z powrotem do pola czatu przez
 * syntetyczny DragEvent("drop") (ProseMirror obsługuje drop plików).
 * Zwraca true gdy dispatch poszedł bez wyjątku (nie gwarantuje przyjęcia
 * przez aplikację - to i tak najlepsza dostępna heurystyka).
 */
function dispatchFileDrop(file) {
  try {
    const dt = new DataTransfer();
    dt.items.add(file);
    const target = document.activeElement || document.body;
    target.dispatchEvent(new DragEvent("drop", { bubbles: true, cancelable: true, dataTransfer: dt }));
    return true;
  } catch (err) {
    console.warn("[Anonimizator] dispatchFileDrop:", err);
    return false;
  }
}

/** Fallback: link do pobrania zanonimizowanego pliku. */
function offerDownload(blob, filename) {
  const url = URL.createObjectURL(blob);
  const closeToast = showToast("Zanonimizowano. Pobierz plik:", { href: url, label: filename, filename });
  // revoke po 5 minutach (użytkownik ma czas kliknąć).
  setTimeout(() => URL.revokeObjectURL(url), 5 * 60 * 1000);
  return closeToast;
}

// ---------------------------------------------------------------------------
// Modal potwierdzenia
// ---------------------------------------------------------------------------

/**
 * showConfirmationModal(opts, onConfirm, onCancel)
 * opts: { title, previewText (surowy tekst - escapujemy tutaj!), fileName,
 *         fileSize, charCount }
 * Modal: ESC / klik w tło = anuluj (wstaw oryginał).
 */
function showConfirmationModal(opts, onConfirm, onCancel) {
  const oldModal = document.getElementById("anonim-confirm-modal");
  if (oldModal) oldModal.remove();

  const overlay = document.createElement("div");
  overlay.id = "anonim-confirm-modal";
  overlay.className = "anonim-modal-overlay";

  const previewHtml = opts.previewText
    ? `<code>${escapeHtml(opts.previewText.slice(0, 300))}${opts.previewText.length > 300 ? "..." : ""}</code>`
    : "";
  const fileInfoHtml = opts.fileName
    ? `<div style="font-weight:600;font-size:14px;">${escapeHtml(opts.fileName)} <span style="font-weight:400;color:#64748b;">(${formatBytes(opts.fileSize || 0)})</span></div>`
    : "";
  const charCountHtml = opts.charCount != null
    ? `<div style="font-size:12px;color:#64748b;margin-top:6px;">Liczba znaków: <strong>${opts.charCount}</strong></div>`
    : "";

  overlay.innerHTML = `
    <div class="anonim-modal-card">
      <div class="anonim-modal-header">
        <span class="anonim-modal-icon">🛡️</span>
        <h3>${escapeHtml(opts.title || "Anonimizator Dokumentów & RODO")}</h3>
      </div>
      <div class="anonim-modal-body">
        <p class="anonim-modal-question"><strong>Czy chcesz zanonimizować?</strong></p>
        <p class="anonim-modal-subtext">Anonimizator usunie nazwiska, PESELe, adresy, NIPy i dane wrażliwe.</p>
        ${fileInfoHtml}
        <div class="anonim-modal-preview">${previewHtml}</div>
        ${charCountHtml}
        <label style="display:flex;align-items:center;gap:8px;font-size:13px;color:#475569;margin:12px 0 0 0;cursor:pointer;">
          <input type="checkbox" id="anonim-auto-check" style="accent-color:#0284c7;">
          Zawsze anonimizuj bez pytania (można zmienić w ustawieniach rozszerzenia)
        </label>
        <p class="anonim-modal-subtext" style="margin-top:14px;margin-bottom:0;font-size:11px;">
          🔒 Tekst/plik jest przetwarzany LOKALNIE na tym komputerze (127.0.0.1:4578) - nie opuszcza go.
        </p>
      </div>
      <div class="anonim-modal-actions">
        <button id="anonim-btn-no" class="anonim-btn anonim-btn-secondary">Nie (wstaw oryginalne)</button>
        <button id="anonim-btn-yes" class="anonim-btn anonim-btn-primary">Tak, zanonimizuj</button>
      </div>
    </div>
  `;

  document.body.appendChild(overlay);

  const cleanup = () => {
    overlay.remove();
    document.removeEventListener("keydown", escHandler);
  };
  const escHandler = (e) => {
    if (e.key === "Escape") { cleanup(); onCancel(); }
  };
  document.addEventListener("keydown", escHandler);
  overlay.addEventListener("click", (e) => {
    if (e.target === overlay) { cleanup(); onCancel(); }
  });

  document.getElementById("anonim-btn-yes").addEventListener("click", () => {
    const always = document.getElementById("anonim-auto-check").checked;
    cleanup();
    onConfirm(always);
  });
  document.getElementById("anonim-btn-no").addEventListener("click", () => {
    cleanup();
    onCancel();
  });
}

// ---------------------------------------------------------------------------
// Paste
// ---------------------------------------------------------------------------

async function handlePaste(e) {
  if (isAnonymizing) {
    // Nie gubimy danych przy wklejeniu w trakcie działania - przepuszczaj
    // domyślne zachowanie przeglądarki (zwykłe wklejenie).
    return;
  }

  const clipboardData = e.clipboardData || window.clipboardData;
  if (!clipboardData) return;

  // KRYTYCZNE: odczyt + preventDefault synchronicznie, przed jakimkolwiek
  // await - po yieldzie DataTransfer bywa unieważniony, a preventDefault
  // musisz zdążyć przed domyślnym wklejeniem.
  const pastedText = clipboardData.getData("text");
  if (!pastedText || pastedText.trim().length < 5) return;
  e.preventDefault();
  e.stopPropagation();

  const target = e.target || document.activeElement;
  isAnonymizing = true;

  const release = () => { isAnonymizing = false; };

  // Serwer martwy -> wstaw oryginał (nigdy nie gubimy danych!).
  const serverUp = await checkServerHealth();
  if (!serverUp) {
    console.warn("[Anonimizator] Lokalny serwer (port 4578) jest nieaktywny - wstawiam oryginał.");
    insertTextIntoElement(target, pastedText);
    release();
    return;
  }

  // Zapamiętana decyzja "zawsze anonimizuj" -> bez pytania.
  const autoAnonymize = await getAutoAnonymizeSetting();
  if (autoAnonymize) {
    try {
      const resp = await requestAnonymizeText(pastedText);
      insertTextIntoElement(target, resp.anonymized);
      showToast(`Zanonimizowano automatycznie (${resp.replaced_count} zamian)`);
    } catch (err) {
      console.warn("[Anonimizator] Błąd anonimizacji:", err);
      insertTextIntoElement(target, pastedText);
      showToast("Błąd anonimizacji - wstawiono oryginalny tekst.");
    }
    release();
    return;
  }

  showConfirmationModal(
    { title: "Anonimizacja tekstu", previewText: pastedText, charCount: pastedText.length },
    async (always) => {
      if (always) await setAutoAnonymize(true);
      try {
        const resp = await requestAnonymizeText(pastedText);
        insertTextIntoElement(target, resp.anonymized);
        showToast(`Zanonimizowano pomyślnie (${resp.replaced_count} zamian)`);
      } catch (err) {
        console.warn("[Anonimizator] Błąd anonimizacji:", err);
        insertTextIntoElement(target, pastedText);
        showToast("Błąd anonimizacji - wstawiono oryginalny tekst.");
      } finally {
        release();
      }
    },
    () => {
      insertTextIntoElement(target, pastedText);
      release();
    }
  );
}

// ---------------------------------------------------------------------------
// Drag & Drop plików
// ---------------------------------------------------------------------------

let dropOverlay = null;

function showDropOverlay() {
  if (dropOverlay) return;
  dropOverlay = document.createElement("div");
  dropOverlay.id = "anonim-drop-overlay";
  dropOverlay.style.cssText = `
    position:fixed;top:0;left:0;right:0;bottom:0;
    background:rgba(2,132,199,0.08);border:3px dashed #0284c7;
    display:flex;align-items:center;justify-content:center;
    font:600 22px -apple-system,'Segoe UI',Roboto,sans-serif;color:#0284c7;
    z-index:99999998;pointer-events:none;`;
  dropOverlay.textContent = "🛡️ Upuść plik, aby zanonimizować";
  document.body.appendChild(dropOverlay);
}

function hideDropOverlay() {
  if (dropOverlay) { dropOverlay.remove(); dropOverlay = null; }
}

async function handleDrop(e) {
  // Ignoruj własne syntetyczne dropy (wrzucenie zanonimizowanego pliku).
  if (isDispatchingSyntheticDrop) return;
  if (isAnonymizing) return;

  const dt = e.dataTransfer;
  if (!dt || !Array.from(dt.types || []).includes("Files")) return;

  const file = dt.files && dt.files[0];
  if (!file) return;

  const ext = (file.name.split(".").pop() || "").toLowerCase();
  const mimeOk = file.type.startsWith("text/") || file.type === "application/pdf" || file.type.startsWith("image/");
  if (!ALLOWED_FILE_EXTENSIONS.includes(ext) && !mimeOk) {
    showToast(`Nieobsługiwany format pliku (.${ext || "?"}). Dozwolone: ${ALLOWED_FILE_EXTENSIONS.join(", ")}.`);
    return; // plik nietknięty - nie dispatchujemy dalej
  }

  isAnonymizing = true;
  const release = () => { isAnonymizing = false; };

  try {
    const serverUp = await checkServerHealth();
    if (!serverUp) {
      showToast("Lokalny serwer nieaktywny - plik pozostawiono bez zmian.");
      release();
      return;
    }

    const arrayBuffer = await file.arrayBuffer();
    const base64 = arrayBufferToBase64(arrayBuffer);

    showConfirmationModal(
      { title: "Anonimizacja pliku", fileName: file.name, fileSize: file.size },
      async (always) => {
        if (always) await setAutoAnonymize(true);
        try {
          const resp = await requestAnonymizeFile(file.name, base64);
          const blob = base64ToBlob(resp.content_base64, DOCX_MIME);
          const outName = resp.output_filename || `zanonimizowany_${file.name.replace(/\.[^.]+$/, "")}.docx`;
          const outFile = new File([blob], outName, { type: DOCX_MIME });

          // Najpierw próba wrzucenia do pola czatu (ProseMirror drop)...
          let dispatched = false;
          try {
            isDispatchingSyntheticDrop = true;
            dispatched = dispatchFileDrop(outFile);
          } finally {
            isDispatchingSyntheticDrop = false;
          }
          // ...fallback: link do pobrania (zawsze dostępny - dispatch nie
          // daje gwarancji przyjęcia przez konkretną aplikację czatu).
          offerDownload(blob, outName);
          if (dispatched) {
            showToast(`Zanonimizowano (${resp.entity_count ?? "?"} encji). Spróbowano wstawić do czatu; plik do pobrania w dymku.`);
          }
        } catch (err) {
          console.warn("[Anonimizator] Błąd anonimizacji pliku:", err);
          showToast("Błąd anonimizacji pliku - oryginał pozostał nietknięty.");
        } finally {
          release();
        }
      },
      () => {
        // Odmowa: nic nie robimy z plikiem (użytkownik może upuścić ponownie).
        release();
      }
    );
  } catch (err) {
    console.warn("[Anonimizator] handleDrop:", err);
    release();
  }
}

// ---------------------------------------------------------------------------
// Zdarzenia globalne
// ---------------------------------------------------------------------------

document.addEventListener("paste", handlePaste, true);

document.addEventListener("dragover", (e) => {
  const dt = e.dataTransfer;
  if (dt && Array.from(dt.types || []).includes("Files")) {
    e.preventDefault(); // pozwól na drop (inaczej przeglądarka otwiera plik)
    showDropOverlay();
  }
});

document.addEventListener("dragleave", (e) => {
  if (!e.relatedTarget) hideDropOverlay();
});

document.addEventListener("drop", (e) => {
  hideDropOverlay();
  const dt = e.dataTransfer;
  if (dt && Array.from(dt.types || []).includes("Files") && !isDispatchingSyntheticDrop) {
    e.preventDefault(); // zatrzymaj domyślne otwieranie pliku; my go obsłużymy
    handleDrop(e);
  }
}, true);

console.log("[Anonimizator] Wtyczka aktywna i czuwa nad polem czatu (paste + drag&drop).");
