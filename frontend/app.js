/**
 * ═══════════════════════════════════════════════════════════════
 * AI Athletik- & Ernährungs-Coach – Frontend Application Logic
 *
 * Async fetch functions for all three pipelines:
 *   A) Ernährung (manuelle Eingabe → n8n → SQLite)
 *   B) Garmin Health (Sync → n8n → Python → SQLite)
 *   C) AI Report (n8n → SQLite → Ollama, nur Health/Workout)
 *
 * Hinweis: n8n-Webhook-URLs sind vorkonfiguriert. Solange n8n
 * nicht läuft, zeigt das Frontend saubere Fehlermeldungen.
 * ═══════════════════════════════════════════════════════════════
 */

// ── Configuration ──────────────────────────────────────────────
const CONFIG = {
  // n8n Webhook Base-URL – anpassen sobald n8n konfiguriert ist
  N8N_BASE_URL: 'http://localhost:5678/webhook',

  // Webhook-Pfade (werden an BASE_URL angehängt)
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

  // Timeouts (ms) – Ollama-Calls brauchen länger
  TIMEOUT_DEFAULT: 60_000,
  TIMEOUT_AI:     600_000,

  // Toast Auto-Hide (ms)
  TOAST_DURATION: 4_000,
};


// ── State ──────────────────────────────────────────────────────
const state = {
  todayFoodLog: [],    // Array von food-entry Objekten
  todayMacros: { calories: 0, protein: 0, carbs: 0, fat: 0, fiber: 0 },
  healthData: null,    // daily_health_metrics Objekt
  workouts: [],        // Array von workout Objekten
  isGeneratingReport: false,
};


// ── Utilities ──────────────────────────────────────────────────

/**
 * Heutiges ISO-Datum (YYYY-MM-DD) in lokaler Zeitzone.
 */
function todayISO() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

/**
 * Formatiert ein Datum leserlich (deutsch).
 */
function formatDateDE(isoDate) {
  const d = new Date(isoDate + 'T00:00:00');
  return d.toLocaleDateString('de-DE', {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
    year: 'numeric',
  });
}

/**
 * Generiert eine eindeutige ID für lokale Einträge.
 */
function generateId() {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}


// ── Fetch Wrapper ──────────────────────────────────────────────

/**
 * Führt einen fetch gegen n8n aus mit Timeout und Error-Handling.
 * @param {string}  endpoint  – Pfad (z.B. '/nutrition/add')
 * @param {object}  options   – fetch options (method, body, etc.)
 * @param {number}  timeout   – Timeout in ms
 * @returns {Promise<object>}
 */
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
      // Fallback for webhook responses that are plain text.
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


// ═══════════════════════════════════════════════════════════════
// PIPELINE A: ERNÄHRUNG (Manuelle Eingabe)
// ═══════════════════════════════════════════════════════════════

/**
 * Fügt ein Lebensmittel zum heutigen Log hinzu.
 * POST → n8n → SQLite
 */
async function addFoodEntry(entry) {
  const payload = {
    date: todayISO(),
    meal_label: entry.mealLabel,
    food_name: entry.foodName,
    amount_g: entry.amountG || null,
    calories: entry.calories || 0,
    protein_g: entry.protein || 0,
    carbs_g: entry.carbs || 0,
    fat_g: entry.fat || 0,
    fiber_g: entry.fiber || 0,
  };

  try {
    await apiFetch(CONFIG.ENDPOINTS.ADD_FOOD, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  } catch (err) {
    // Wenn n8n nicht läuft: lokal in State speichern + Warnung anzeigen
    console.warn('n8n nicht erreichbar, Eintrag nur lokal gespeichert:', err.message);
    showToast('⚠️ n8n nicht erreichbar – Eintrag nur lokal gespeichert.', 'warning');
  }

  // Immer lokal in State aktualisieren (für sofortiges UI-Feedback)
  const localEntry = {
    id: generateId(),
    ...payload,
    created_at: new Date().toISOString(),
  };
  state.todayFoodLog.push(localEntry);
  recalcMacros();
  renderFoodLog();
  renderMacroBar();
}

/**
 * Löscht einen Eintrag aus dem heutigen Food-Log.
 */
async function deleteFoodEntry(entryId) {
  try {
    await apiFetch(CONFIG.ENDPOINTS.DELETE_FOOD, {
      method: 'POST',
      body: JSON.stringify({ id: entryId, date: todayISO() }),
    });
  } catch (err) {
    console.warn('n8n nicht erreichbar, Eintrag nur lokal gelöscht:', err.message);
  }

  state.todayFoodLog = state.todayFoodLog.filter(e => e.id !== entryId);
  recalcMacros();
  renderFoodLog();
  renderMacroBar();
  showToast('🗑️ Eintrag entfernt.', 'info');
}

/**
 * Lädt das heutige Food-Log vom Server.
 */
async function fetchTodayFoodLog() {
  try {
    const data = await apiFetch(CONFIG.ENDPOINTS.GET_FOOD_LOG + '?date=' + todayISO(), {
      method: 'GET',
    });
    state.todayFoodLog = data.entries || [];
    recalcMacros();
    renderFoodLog();
    renderMacroBar();
  } catch (err) {
    console.warn('Konnte Food-Log nicht laden:', err.message);
  }
}

/**
 * Berechnet die Makro-Summen aus dem lokalen State neu.
 */
function recalcMacros() {
  state.todayMacros = state.todayFoodLog.reduce(
    (acc, e) => ({
      calories: acc.calories + (e.calories || 0),
      protein: acc.protein + (e.protein_g || 0),
      carbs: acc.carbs + (e.carbs_g || 0),
      fat: acc.fat + (e.fat_g || 0),
      fiber: acc.fiber + (e.fiber_g || 0),
    }),
    { calories: 0, protein: 0, carbs: 0, fat: 0, fiber: 0 }
  );
}


// ═══════════════════════════════════════════════════════════════
// PIPELINE B: GARMIN HEALTH
// ═══════════════════════════════════════════════════════════════

/**
 * Triggert Garmin-Sync via n8n → Python-Skript.
 * Bei Fehler (z.B. 2FA nötig) wird das Fallback-Formular angezeigt.
 */
async function syncGarmin() {
  setButtonLoading('garmin-sync-btn', true);

  try {
    const data = await apiFetch(CONFIG.ENDPOINTS.SYNC_GARMIN, {
      method: 'POST',
      body: JSON.stringify({ date: todayISO() }),
    });

    if (data.status === 'error') {
      // Garmin-Login fehlgeschlagen (z.B. 2FA/Captcha)
      showToast('⚠️ Garmin: ' + (data.message || 'Login fehlgeschlagen. Bitte manuell eingeben.'), 'warning');
      showManualHealthForm();
      return;
    }

    // Erfolg: Health-Daten + Workouts aktualisieren
    state.healthData = data.health || null;
    state.workouts = data.workouts || [];
    renderHealthMetrics();
    renderWorkoutList();
    showToast('✅ Garmin-Daten synchronisiert!', 'success');
  } catch (err) {
    showToast('❌ ' + err.message, 'error');
    showManualHealthForm();
  } finally {
    setButtonLoading('garmin-sync-btn', false);
  }
}

/**
 * Speichert manuell eingegebene Health-Daten.
 * POST → n8n → SQLite
 */
async function submitManualHealth(data) {
  setButtonLoading('manual-health-submit-btn', true);

  const payload = {
    date: todayISO(),
    hrv_avg: data.hrv || null,
    sleep_score: data.sleepScore || null,
    sleep_hours: data.sleepHours || null,
    resting_hr: data.restingHr || null,
    stress_avg: data.stress || null,
    steps: data.steps || null,
    source: 'manual',
  };

  try {
    await apiFetch(CONFIG.ENDPOINTS.SUBMIT_HEALTH, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
    showToast('✅ Gesundheitsdaten gespeichert!', 'success');
  } catch (err) {
    // Wenn n8n nicht läuft: trotzdem lokal anzeigen
    console.warn('n8n nicht erreichbar:', err.message);
    showToast('⚠️ n8n nicht erreichbar – Daten nur lokal angezeigt.', 'warning');
  }

  // Lokal in State übernehmen
  state.healthData = payload;
  renderHealthMetrics();

  setButtonLoading('manual-health-submit-btn', false);
}

/**
 * Lädt die heutigen Health-Daten vom Server.
 */
async function fetchTodayHealth() {
  try {
    const data = await apiFetch(CONFIG.ENDPOINTS.GET_HEALTH + '?date=' + todayISO(), {
      method: 'GET',
    });
    state.healthData = data.health || null;
    state.workouts = data.workouts || [];
    renderHealthMetrics();
    renderWorkoutList();
  } catch (err) {
    console.warn('Konnte Health-Daten nicht laden:', err.message);
  }
}


// ═══════════════════════════════════════════════════════════════
// PIPELINE C: AI COACHING REPORT (nur Health + Workouts)
// ═══════════════════════════════════════════════════════════════

/**
 * Generiert den AI Coaching Report.
 * GET → n8n → SQLite (letzte 7 Tage Health+Workouts) → Ollama → Report
 * HINWEIS: Ernährungsdaten werden NICHT an das LLM gesendet.
 */
async function generateReport() {
  if (state.isGeneratingReport) return;

  const btn = document.getElementById('generate-report-btn');
  const loading = document.getElementById('report-loading');
  const output = document.getElementById('report-output');

  state.isGeneratingReport = true;
  setButtonLoading('generate-report-btn', true);
  btn.disabled = true;
  output.textContent = '';
  loading.classList.add('is-active');

  try {
    const data = await apiFetch(
      CONFIG.ENDPOINTS.GENERATE_REPORT + '?date=' + todayISO(),
      { method: 'GET' },
      CONFIG.TIMEOUT_AI
    );

    loading.classList.remove('is-active');
    output.innerHTML = formatReportOutput(data.report || data.message || 'Kein Report erhalten.');
    showToast('✅ Report generiert!', 'success');
  } catch (err) {
    loading.classList.remove('is-active');
    output.textContent = '❌ Fehler: ' + err.message;
    showToast('❌ Report-Generierung fehlgeschlagen.', 'error');
  } finally {
    state.isGeneratingReport = false;
    setButtonLoading('generate-report-btn', false);
    btn.disabled = false;
  }
}

/**
 * Formatiert den Report-Text für die HTML-Ausgabe.
 * Unterstützt einfaches Markdown (Headings, Bold, Listen).
 */
function formatReportOutput(text) {
  return text
    // Headers
    .replace(/^### (.+)$/gm, '<h3>$1</h3>')
    .replace(/^## (.+)$/gm, '<h3>$1</h3>')
    .replace(/^# (.+)$/gm, '<h3>$1</h3>')
    // Bold
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    // Italic
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
    // Lists
    .replace(/^- (.+)$/gm, '<li>$1</li>')
    .replace(/(<li>.*<\/li>)/s, '<ul>$1</ul>')
    // Line breaks
    .replace(/\n\n/g, '<br><br>')
    .replace(/\n/g, '<br>');
}


// ═══════════════════════════════════════════════════════════════
// UI RENDERING
// ═══════════════════════════════════════════════════════════════

/**
 * Rendert das heutige Food-Log in der Sidebar.
 */
function renderFoodLog() {
  const container = document.getElementById('food-log');
  const countBadge = document.getElementById('nutrition-meal-count');

  countBadge.textContent = `${state.todayFoodLog.length} Einträge`;

  if (state.todayFoodLog.length === 0) {
    container.innerHTML = `
      <div class="food-log__empty">
        <span class="food-log__empty-icon">📋</span>
        Noch keine Einträge heute – füge deine erste Mahlzeit hinzu.
      </div>`;
    return;
  }

  const mealEmojis = { breakfast: '🌅', lunch: '☀️', dinner: '🌙', snack: '🍎' };

  container.innerHTML = state.todayFoodLog.map(entry => `
    <div class="food-log__item" data-id="${entry.id}">
      <div>
        <div class="food-log__food-name">${mealEmojis[entry.meal_label] || '🍽️'} ${escapeHtml(entry.food_name)}</div>
        <div class="food-log__food-meta">${entry.amount_g ? entry.amount_g + 'g' : ''} ${entry.meal_label || ''}</div>
      </div>
      <div class="food-log__macros">
        <span>${Math.round(entry.calories || 0)} kcal</span>
        <span>${(entry.protein_g || 0).toFixed(1)}P</span>
        <span>${(entry.carbs_g || 0).toFixed(1)}C</span>
        <span>${(entry.fat_g || 0).toFixed(1)}F</span>
      </div>
      <button class="food-log__delete" onclick="deleteFoodEntry('${entry.id}')" title="Löschen">×</button>
    </div>
  `).join('');
}

/**
 * Aktualisiert die Makro-Übersichtsleiste.
 */
function renderMacroBar() {
  document.getElementById('macro-cal').textContent = Math.round(state.todayMacros.calories);
  document.getElementById('macro-prot').textContent = state.todayMacros.protein.toFixed(1) + 'g';
  document.getElementById('macro-carbs').textContent = state.todayMacros.carbs.toFixed(1) + 'g';
  document.getElementById('macro-fat').textContent = state.todayMacros.fat.toFixed(1) + 'g';
}

/**
 * Rendert die Health-Metriken in den Tile-Kacheln.
 */
function renderHealthMetrics() {
  const h = state.healthData;
  const badge = document.getElementById('health-source-badge');

  if (!h) {
    badge.textContent = 'Keine Daten';
    return;
  }

  badge.textContent = h.source === 'garmin' ? '⌚ Garmin' : '✍️ Manuell';

  document.getElementById('metric-hrv').textContent = h.hrv_avg != null ? h.hrv_avg : '–';
  document.getElementById('metric-sleep').textContent = h.sleep_score != null ? h.sleep_score : '–';
  document.getElementById('metric-hr').textContent = h.resting_hr != null ? h.resting_hr : '–';
  document.getElementById('metric-battery').textContent =
    h.body_battery_high != null ? `${h.body_battery_low || 0}–${h.body_battery_high}` : '–';
  document.getElementById('metric-stress').textContent = h.stress_avg != null ? h.stress_avg : '–';
  document.getElementById('metric-steps').textContent =
    h.steps != null ? h.steps.toLocaleString('de-DE') : '–';
}

/**
 * Rendert die heutigen Workouts.
 */
function renderWorkoutList() {
  const container = document.getElementById('workout-list');
  const badge = document.getElementById('workout-count-badge');

  badge.textContent = state.workouts.length;

  if (state.workouts.length === 0) {
    container.innerHTML = '<div class="workout-list__empty">Noch keine Workouts synchronisiert.</div>';
    return;
  }

  const activityIcons = {
    running: '🏃',
    cycling: '🚴',
    strength: '🏋️',
    swimming: '🏊',
    hiking: '🥾',
    yoga: '🧘',
    default: '💪',
  };

  container.innerHTML = state.workouts.map(w => {
    const icon = activityIcons[(w.activity_type || '').toLowerCase()] || activityIcons.default;
    const dur = w.duration_min ? `${Math.round(w.duration_min)} min` : '';
    const dist = w.distance_km ? `${w.distance_km.toFixed(1)} km` : '';
    const hr = w.avg_hr ? `❤️ ${w.avg_hr} bpm` : '';
    const details = [dur, dist, hr].filter(Boolean).join(' · ');

    return `
      <div class="workout-item">
        <div class="workout-item__icon">${icon}</div>
        <div class="workout-item__info">
          <div class="workout-item__type">${escapeHtml(w.activity_type || 'Workout')}</div>
          <div class="workout-item__details">${details}</div>
        </div>
        ${w.training_load ? `<div class="workout-item__load">Load: ${w.training_load}</div>` : ''}
      </div>`;
  }).join('');
}


// ═══════════════════════════════════════════════════════════════
// UI HELPERS
// ═══════════════════════════════════════════════════════════════

/**
 * Setzt einen Button in den Loading-Zustand (Spinner + deaktiviert).
 */
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

/**
 * Zeigt das manuelle Health-Eingabeformular an.
 */
function showManualHealthForm() {
  const form = document.getElementById('manual-health-form');
  form.classList.add('is-visible');
}

/**
 * Zeigt eine Toast-Benachrichtigung an.
 * @param {string} message  – Nachricht
 * @param {'success'|'error'|'info'|'warning'} type
 */
function showToast(message, type = 'info') {
  const container = document.getElementById('toast-container');
  const toast = document.createElement('div');
  toast.className = `toast toast--${type}`;
  toast.textContent = message;
  container.appendChild(toast);

  setTimeout(() => {
    toast.classList.add('toast--leaving');
    setTimeout(() => toast.remove(), 200);
  }, CONFIG.TOAST_DURATION);
}

/**
 * Escapes HTML für sichere Textausgabe.
 */
function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}


// ═══════════════════════════════════════════════════════════════
// EVENT LISTENERS
// ═══════════════════════════════════════════════════════════════

document.addEventListener('DOMContentLoaded', () => {

  // ── Datum im Header ────────────────────────────────────────
  document.getElementById('header-date').textContent = formatDateDE(todayISO());

  // ── Food-Formular ──────────────────────────────────────────
  document.getElementById('food-form').addEventListener('submit', (e) => {
    e.preventDefault();

    const foodName = document.getElementById('food-name').value.trim();
    if (!foodName) return;

    addFoodEntry({
      foodName,
      mealLabel: document.getElementById('meal-label').value,
      amountG: parseFloat(document.getElementById('food-amount').value) || null,
      calories: parseFloat(document.getElementById('food-calories').value) || 0,
      protein: parseFloat(document.getElementById('food-protein').value) || 0,
      carbs: parseFloat(document.getElementById('food-carbs').value) || 0,
      fat: parseFloat(document.getElementById('food-fat').value) || 0,
      fiber: parseFloat(document.getElementById('food-fiber').value) || 0,
    });

    // Formular zurücksetzen, Fokus auf Food-Name
    e.target.reset();
    document.getElementById('food-name').focus();
    showToast('✅ Lebensmittel hinzugefügt!', 'success');
  });

  // ── Garmin Sync ────────────────────────────────────────────
  document.getElementById('garmin-sync-btn').addEventListener('click', syncGarmin);

  // ── Health Refresh ─────────────────────────────────────────
  document.getElementById('health-refresh-btn').addEventListener('click', fetchTodayHealth);

  // ── Manuelle Health-Eingabe Toggle ─────────────────────────
  document.getElementById('manual-health-toggle').addEventListener('click', () => {
    const form = document.getElementById('manual-health-form');
    form.classList.toggle('is-visible');
  });

  // ── Manuelle Health-Eingabe Submit ─────────────────────────
  document.getElementById('manual-health-form').addEventListener('submit', (e) => {
    e.preventDefault();

    submitManualHealth({
      hrv: parseFloat(document.getElementById('manual-hrv').value) || null,
      sleepScore: parseInt(document.getElementById('manual-sleep-score').value) || null,
      sleepHours: parseFloat(document.getElementById('manual-sleep-hours').value) || null,
      restingHr: parseInt(document.getElementById('manual-resting-hr').value) || null,
      stress: parseInt(document.getElementById('manual-stress').value) || null,
      steps: parseInt(document.getElementById('manual-steps').value) || null,
    });
  });

  // ── AI Report generieren ───────────────────────────────────
  document.getElementById('generate-report-btn').addEventListener('click', generateReport);

  // ── Initial Data Load ──────────────────────────────────────
  // Versuche Daten vom Server zu laden (scheitert leise wenn n8n nicht läuft)
  fetchTodayFoodLog();
  fetchTodayHealth();
});
