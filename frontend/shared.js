/**
 * ═══════════════════════════════════════════════════════════════
 * AI Athletik- & Ernährungs-Coach – Shared Module (ES Module)
 * ═══════════════════════════════════════════════════════════════
 *
 * Alle geteilten Funktionen und Konfiguration.
 * Import via: import { CONFIG, apiFetch, showToast, ... } from './shared.js'
 */

// ── Configuration ──────────────────────────────────────────────

export const CONFIG = {
  // Direkt zum FastAPI-Server (kein n8n-Proxy mehr)
  API_BASE: '/api',
  ENDPOINTS: {
    ADD_FOOD:        '/api/nutrition/add',
    DELETE_FOOD:     '/api/nutrition/delete',
    GET_FOOD_LOG:    '/api/nutrition/today',
    SYNC_GARMIN:     '/api/garmin/sync',
    SUBMIT_HEALTH:   '/api/health/manual',
    GET_HEALTH:      '/api/health/today',
    GENERATE_REPORT: '/api/report/generate',
    GET_SUMMARY:     '/api/history/summary',
  },
  TIMEOUT_DEFAULT: 60_000,
  TIMEOUT_AI:     600_000,
  TOAST_DURATION:  4_000,
};


// ── Shared Utilities ───────────────────────────────────────────

export function todayISO() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

export function formatDateDE(isoDate) {
  if (!isoDate) return '-';
  const d = new Date(isoDate + 'T00:00:00');
  return d.toLocaleDateString('de-DE', {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
    year: 'numeric',
  });
}

export function formatDateShortDE(isoDate) {
  if (!isoDate) return '-';
  const d = new Date(isoDate + 'T00:00:00');
  return d.toLocaleDateString('de-DE', {
    weekday: 'short',
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
  });
}

export function generateId() {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}


// ── API Fetch (direkt zu FastAPI) ──────────────────────────────

export async function apiFetch(endpoint, options = {}, timeout = CONFIG.TIMEOUT_DEFAULT) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeout);

  try {
    const response = await fetch(endpoint, {
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

    if (!rawText) return {};

    try {
      const parsed = JSON.parse(rawText);
      // Unwrap {status, data} envelope if present
      if (parsed.status === 'ok' && parsed.data !== undefined) {
        return parsed.data;
      }
      if (parsed.status === 'error') {
        throw new Error(parsed.message || 'Unbekannter Fehler');
      }
      return parsed;
    } catch (parseErr) {
      if (parseErr.message?.includes('Unbekannter Fehler') || parseErr.message?.includes('fehlgeschlagen')) {
        throw parseErr;
      }
      return { message: rawText };
    }
  } catch (err) {
    clearTimeout(timer);

    if (err.name === 'AbortError') {
      throw new Error('Zeitüberschreitung – der Server hat nicht rechtzeitig geantwortet.');
    }
    if (err.message.includes('Failed to fetch') || err.message.includes('NetworkError')) {
      throw new Error('Verbindung zum Server fehlgeschlagen. Läuft der Server auf Port 8765?');
    }
    throw err;
  }
}


// ── UI Helpers ─────────────────────────────────────────────────

export function setButtonLoading(btnId, isLoading) {
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

export function showToast(message, type = 'info') {
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

export function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}


// ── Init: Datum im Header ──────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
  const dateEl = document.getElementById('header-date');
  if (dateEl) {
    dateEl.textContent = formatDateDE(todayISO());
  }
});
