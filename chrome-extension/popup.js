/**
 * Anonimizator Pism & RODO Guard - popup
 * MV3 zakazuje inline <script> na extension pages - cały kod musi być tutaj.
 */

const API_URL = "http://127.0.0.1:4578";
const FETCH_TIMEOUT_MS = 5000;

const statusText = document.getElementById("status-text");
const statusBox = document.getElementById("status-box");
const recheckBtn = document.getElementById("recheck");
const autoAnonChk = document.getElementById("auto-anon");
const verEl = document.getElementById("ver");

async function checkHealth() {
  statusText.textContent = "Sprawdzanie serwera...";
  statusBox.classList.remove("err");
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), FETCH_TIMEOUT_MS);
  try {
    const res = await fetch(`${API_URL}/health`, { signal: controller.signal, cache: "no-store" });
    clearTimeout(timer);
    if (res.ok) {
      statusText.textContent = "Silnik offline aktywny (127.0.0.1:4578)";
    } else {
      throw new Error(`HTTP ${res.status}`);
    }
  } catch {
    clearTimeout(timer);
    statusBox.classList.add("err");
    statusText.textContent = "Silnik niedostępny (uruchom aplikację)";
  }
}

async function loadSettings() {
  try {
    const data = await chrome.storage.sync.get(["autoAnonymize"]);
    autoAnonChk.checked = !!data.autoAnonymize;
  } catch {
    /* storage niedostępny */
  }
}

autoAnonChk.addEventListener("change", async () => {
  try {
    await chrome.storage.sync.set({ autoAnonymize: autoAnonChk.checked });
  } catch {
    /* niedostępny */
  }
});

recheckBtn.addEventListener("click", checkHealth);

try {
  const manifest = chrome.runtime.getManifest();
  verEl.textContent = `Wersja ${manifest.version}`;
} catch {
  verEl.textContent = "";
}

loadSettings();
checkHealth();
