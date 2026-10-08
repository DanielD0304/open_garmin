/**
 * ═══════════════════════════════════════════════════════════════
 * AI Coach – Shared Module (ES Module)
 * ═══════════════════════════════════════════════════════════════
 *
 * Geteilte Konfiguration, API-Zugriff und Hilfsfunktionen.
 * Import via: import { CONFIG, apiFetch, showToast, ... } from './shared.js'
 */

// ── Configuration ──────────────────────────────────────────────

export const CONFIG = {
  ENDPOINTS: {
    ADD_FOOD:        '/api/nutrition/add',
    UPDATE_FOOD:     '/api/nutrition/update',
    DELETE_FOOD:     '/api/nutrition/delete',
    GET_FOOD_LOG:    '/api/nutrition/today',
    FOOD_RANGE:      '/api/nutrition/range',
    FAVORITES:       '/api/favorites',
    PROFILE:         '/api/profile',
    TARGETS:         '/api/targets',
    CLAUDE_STATUS:   '/api/claude/status',
    CLAUDE_LOOKUP:   '/api/claude/lookup',
    CLAUDE_ADVICE:   '/api/claude/advice',
    USAGE:           '/api/usage',
    USAGE_REFRESH:   '/api/usage/refresh',
    SYNC_GARMIN:     '/api/garmin/sync',
    GARMIN_STATUS:   '/api/garmin/status',
    GARMIN_LOGIN:    '/api/garmin/login',
    GARMIN_MFA:      '/api/garmin/mfa',
    GARMIN_LOGOUT:   '/api/garmin/logout',
    GARMIN_PROFILE:  '/api/garmin/import-profile',
    SUBMIT_HEALTH:   '/api/health/manual',
    GET_HEALTH:      '/api/health/today',
    GENERATE_REPORT: '/api/report/generate',
    GET_SUMMARY:     '/api/history/summary',
  },
  TIMEOUT_DEFAULT: 60_000,
  TIMEOUT_AI:     300_000,
  TOAST_DURATION:  4_000,
};

export const MEALS = { breakfast: 'Frühstück', lunch: 'Mittagessen', dinner: 'Abendessen', snack: 'Snacks & Getränke' };


// ── Datum & Formatierung ───────────────────────────────────────

export function isoDate(d) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

export function todayISO() {
  return isoDate(new Date());
}

export function shiftDate(iso, days) {
  const d = new Date(iso + 'T12:00:00');
  d.setDate(d.getDate() + days);
  return isoDate(d);
}

export function formatDateDE(iso) {
  if (!iso) return '-';
  return new Date(iso + 'T00:00:00').toLocaleDateString('de-DE', {
    weekday: 'long', day: 'numeric', month: 'long', year: 'numeric',
  });
}

export function formatDateShortDE(iso) {
  if (!iso) return '-';
  return new Date(iso + 'T00:00:00').toLocaleDateString('de-DE', {
    weekday: 'short', day: '2-digit', month: '2-digit', year: 'numeric',
  });
}

export const fmt = (v, digits = 0) => v == null || isNaN(v) ? '–'
  : Number(v).toLocaleString('de-DE', { maximumFractionDigits: digits, minimumFractionDigits: digits });

export const euro = (v) => v == null || isNaN(v) ? '–'
  : Number(v).toLocaleString('de-DE', { style: 'currency', currency: 'EUR' });

export const fmtTokens = (n) => n >= 10000 ? fmt(n / 1000, 1) + 'k' : fmt(n);

export function generateId() {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

export function guessMeal() {
  const h = new Date().getHours() + new Date().getMinutes() / 60;
  if (h < 10.5) return 'breakfast';
  if (h < 14.5) return 'lunch';
  if (h < 17.5) return 'snack';
  return 'dinner';
}


// ── API ────────────────────────────────────────────────────────

/** Ruft die API auf und entpackt {status, data}. Fehler tragen .code (z.B. garmin_auth_required). */
export async function apiFetch(endpoint, options = {}, timeout = CONFIG.TIMEOUT_DEFAULT) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeout);

  let response, rawText;
  try {
    response = await fetch(endpoint, {
      ...options,
      signal: controller.signal,
      headers: { 'Content-Type': 'application/json', ...options.headers },
    });
    rawText = await response.text().catch(() => '');
  } catch (err) {
    if (err.name === 'AbortError') throw new Error('Zeitüberschreitung – keine Antwort erhalten.');
    throw new Error('Verbindung zum App-Server fehlgeschlagen.');
  } finally {
    clearTimeout(timer);
  }

  let parsed = null;
  try { parsed = rawText ? JSON.parse(rawText) : {}; } catch { /* kein JSON */ }

  if (!response.ok || parsed?.status === 'error') {
    const message = parsed?.message || parsed?.detail || rawText || `HTTP ${response.status}`;
    const error = new Error(typeof message === 'string' ? message : JSON.stringify(message));
    error.code = parsed?.code;
    throw error;
  }
  if (parsed && parsed.status === 'ok' && parsed.data !== undefined) return parsed.data;
  return parsed ?? { message: rawText };
}

export const apiGet = (endpoint, timeout) => apiFetch(endpoint, { method: 'GET' }, timeout);
export const apiPost = (endpoint, body, timeout) =>
  apiFetch(endpoint, { method: 'POST', body: JSON.stringify(body ?? {}) }, timeout);
export const apiPut = (endpoint, body) => apiFetch(endpoint, { method: 'PUT', body: JSON.stringify(body ?? {}) });
export const apiDelete = (endpoint) => apiFetch(endpoint, { method: 'DELETE' });


// ── UI Helpers ─────────────────────────────────────────────────

export function setButtonLoading(btnId, isLoading) {
  const btn = typeof btnId === 'string' ? document.getElementById(btnId) : btnId;
  if (!btn) return;
  btn.classList.toggle('btn--loading', isLoading);
  btn.disabled = isLoading;
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
  return String(text ?? '').replace(/[&<>"']/g, (c) =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

/** Kurze Zeile "Diese Anfrage: 7.012 Tokens … Limit jetzt: 5 h 40 %". */
export function usageLine(usage) {
  const r = usage?.request;
  if (!r) return '';
  const w = usage.rateLimit?.unifiedWindows;
  const pct = (u) => Math.round((u || 0) * 100);
  return `Diese Anfrage: <b>${fmtTokens(r.total)} Tokens</b> (${fmtTokens(r.input + r.cacheRead + r.cacheWrite)} rein, ${fmtTokens(r.output)} raus)` +
    (r.webSearches ? `, ${r.webSearches} Websuche${r.webSearches > 1 ? 'n' : ''}` : '') +
    ` · ${fmt(r.durationMs / 1000)} s` +
    (w ? ` · Limit jetzt: 5 h ${pct(w.five_hour?.utilization)} %, Woche ${pct(w.seven_day?.utilization)} %` : '');
}


// ── Sidebar: Claude-Limit ──────────────────────────────────────

export function renderSidebarUsage(usage) {
  const sidebar = document.querySelector('.sidebar');
  if (!sidebar) return;
  let box = document.getElementById('sidebar-usage');
  if (!box) {
    box = document.createElement('a');
    box.id = 'sidebar-usage';
    box.className = 'sidebar-usage';
    box.href = 'profile.html#claude';
    box.title = 'Claude-Nutzungslimit deines Abos';
    sidebar.appendChild(box);
  }
  const w = usage?.rateLimit?.unifiedWindows;
  if (!w) {
    box.innerHTML = '<div class="sidebar-usage__title">Claude-Limit</div><div>noch kein Stand</div>';
    return;
  }
  const row = (label, u) => {
    const pct = Math.round((u || 0) * 100);
    return `<div class="sidebar-usage__row"><span>${label}</span>
      <span class="sidebar-usage__track"><span class="sidebar-usage__fill ${pct > 80 ? 'sidebar-usage__fill--high' : ''}"
        style="display:block;width:${pct}%"></span></span><span>${pct} %</span></div>`;
  };
  box.innerHTML = '<div class="sidebar-usage__title">Claude-Limit</div>' +
    row('5 h', w.five_hour?.utilization) + row('Woche', w.seven_day?.utilization);
}

export async function refreshSidebarUsage() {
  try {
    renderSidebarUsage(await apiGet(CONFIG.ENDPOINTS.USAGE));
  } catch { /* Server noch nicht bereit */ }
}


// ── Externe Links im Systembrowser öffnen (Desktop-Fenster) ────

document.addEventListener('click', (ev) => {
  const link = ev.target.closest('a[href^="http"]');
  if (!link) return;
  if (window.pywebview?.api?.open_external) {
    ev.preventDefault();
    window.pywebview.api.open_external(link.href);
  } else {
    link.target = '_blank';
    link.rel = 'noopener';
  }
});


// ── Init ───────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
  const dateEl = document.getElementById('header-date');
  if (dateEl) dateEl.textContent = formatDateDE(todayISO());
  refreshSidebarUsage();
});
