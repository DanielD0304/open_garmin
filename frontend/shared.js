/**
 * ═══════════════════════════════════════════════════════════════
 * AI Athletik- & Ernährungs-Coach – Shared Application Logic
 * ═══════════════════════════════════════════════════════════════
 */

// ── Configuration ──────────────────────────────────────────────
const CONFIG = {
  N8N_BASE_URL: 'http://localhost:5678/webhook',
  ENDPOINTS: {
    ADD_FOOD:       '/nutrition/add',
    DELETE_FOOD:    '/nutrition/delete',
    GET_FOOD_LOG:   '/nutrition/today',
    SYNC_GARMIN:    '/garmin/sync',
    SUBMIT_HEALTH:  '/health/manual',
    GET_HEALTH:     '/health/today',
    GET_WORKOUTS:   '/workouts/today',
    GENERATE_REPORT: '/report/generate',
  },
  TIMEOUT_DEFAULT: 60_000,
  TIMEOUT_AI:     600_000,
  TOAST_DURATION: 4_000,
  API_URL: 'http://localhost:8765/run' // Local Python Server Fallback/Direct
};

// ── Shared Utilities ───────────────────────────────────────────

function todayISO() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

function formatDateDE(isoDate) {
  if (!isoDate) return '-';
  const d = new Date(isoDate + 'T00:00:00');
  return d.toLocaleDateString('de-DE', {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
    year: 'numeric',
  });
}

function generateId() {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

async function apiFetch(endpoint, options = {}, timeout = CONFIG.TIMEOUT_DEFAULT) {
  const url = CONFIG.N8N_BASE_URL + endpoint;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeout);

  try {
    const response = await fetch(url, {
      ...options,
      signal: controller.signal,
      headers: {
        'Content-Type': 'application/json',
        ...options.headers,
      },
    });

    clearTimeout(timer);

    const rawText = await response.text().catch(() => '');

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${rawText || 'Unbekannter Fehler'}`);
    }

    if (!rawText) {
      return {};
    }

    try {
      return JSON.parse(rawText);
    } catch {
      return { message: rawText };
    }
  } catch (err) {
    clearTimeout(timer);

    if (err.name === 'AbortError') {
      throw new Error('Zeitüberschreitung – der Server hat nicht rechtzeitig geantwortet.');
    }
    if (err.message.includes('Failed to fetch') || err.message.includes('NetworkError')) {
      throw new Error('Verbindung zu n8n fehlgeschlagen. Läuft n8n auf ' + CONFIG.N8N_BASE_URL + '?');
    }
    throw err;
  }
}

// Direkter lokaler API-Fetch (ohne n8n)
async function localApiFetch(action, params = {}) {
  const response = await fetch(CONFIG.API_URL, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ action, params })
  });
  
  if (!response.ok) {
    throw new Error(`HTTP Error: ${response.status}`);
  }
  
  const result = await response.json();
  if (result.status === 'error') {
    throw new Error(result.message);
  }
  return result.data;
}


// ── UI Helpers ─────────────────────────────────────────────────

function setButtonLoading(btnId, isLoading) {
  const btn = document.getElementById(btnId);
  if (!btn) return;

  if (isLoading) {
    btn.classList.add('btn--loading');
    btn.disabled = true;
  } else {
    btn.classList.remove('btn--loading');
    btn.disabled = false;
  }
}

function showToast(message, type = 'info') {
  const container = document.getElementById('toast-container');
  if (!container) return;
  const toast = document.createElement('div');
  toast.className = `toast toast--${type}`;
  toast.textContent = message;
  container.appendChild(toast);

  setTimeout(() => {
    toast.classList.add('toast--leaving');
    setTimeout(() => toast.remove(), 200);
  }, CONFIG.TOAST_DURATION);
}

function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

// Initialisiere Datum im Header, falls vorhanden
document.addEventListener('DOMContentLoaded', () => {
  const dateEl = document.getElementById('header-date');
  if (dateEl) {
    dateEl.textContent = formatDateDE(todayISO());
  }
});
