/**
 * Dashboard – app.js (ES Module)
 */
import { CONFIG, apiFetch, apiGet, todayISO, escapeHtml, fmt, euro } from './shared.js';

const state = {
  todayFoodLog: [],
  todayMacros: { calories: 0, protein: 0, carbs: 0, fat: 0, fiber: 0, price: 0 },
  targets: null,
  healthData: null,
  workouts: [],
};

async function fetchTodayFoodLog() {
  try {
    const data = await apiFetch(CONFIG.ENDPOINTS.GET_FOOD_LOG + '?date=' + todayISO(), { method: 'GET' });
    state.todayFoodLog = data.entries || [];
    state.targets = await apiGet(CONFIG.ENDPOINTS.TARGETS + '?date=' + todayISO()).catch(() => null);
    recalcMacros();
    renderMacroBar();
  } catch (err) {
    console.warn('Konnte Food-Log nicht laden:', err.message);
  }
}

function recalcMacros() {
  state.todayMacros = state.todayFoodLog.reduce(
    (acc, e) => ({
      calories: acc.calories + (e.calories || 0),
      protein: acc.protein + (e.protein_g || 0),
      carbs: acc.carbs + (e.carbs_g || 0),
      fat: acc.fat + (e.fat_g || 0),
      fiber: acc.fiber + (e.fiber_g || 0),
      price: acc.price + (e.price_eur || 0),
    }),
    { calories: 0, protein: 0, carbs: 0, fat: 0, fiber: 0, price: 0 }
  );
}

function renderMacroBar() {
  const calEl = document.getElementById('macro-cal');
  if (calEl) calEl.textContent = Math.round(state.todayMacros.calories);
  
  const protEl = document.getElementById('macro-prot');
  if (protEl) protEl.textContent = state.todayMacros.protein.toFixed(1) + 'g';
  
  const carbsEl = document.getElementById('macro-carbs');
  if (carbsEl) carbsEl.textContent = state.todayMacros.carbs.toFixed(1) + 'g';
  
  const fatEl = document.getElementById('macro-fat');
  if (fatEl) fatEl.textContent = state.todayMacros.fat.toFixed(1) + 'g';

  const costEl = document.getElementById('macro-cost');
  if (costEl) costEl.textContent = euro(state.todayMacros.price);

  // Ziele aus Koerperprofil + Garmin-Aktivitaet
  const t = state.targets;
  if (t) {
    const label = (id, text) => { const el = document.getElementById(id); if (el) el.textContent = text; };
    label('macro-cal-label', `von ${fmt(t.kcal)} kcal`);
    label('macro-prot-label', `Protein / ${t.protein} g`);
    label('macro-carbs-label', `Carbs / ${t.carbs} g`);
    label('macro-fat-label', `Fett / ${t.fat} g`);
  }
}

async function fetchTodayHealth() {
  try {
    const data = await apiFetch(CONFIG.ENDPOINTS.GET_HEALTH + '?date=' + todayISO(), { method: 'GET' });
    state.healthData = data.health || null;
    state.workouts = data.workouts || [];
    renderHealthMetrics();
    renderWorkoutList();
  } catch (err) {
    console.warn('Konnte Health-Daten nicht laden:', err.message);
  }
}

function renderHealthMetrics() {
  const h = state.healthData;
  const badge = document.getElementById('health-source-badge');
  
  if (!badge) return;

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

function renderWorkoutList() {
  const container = document.getElementById('workout-list');
  const badge = document.getElementById('workout-count-badge');
  
  if (!container || !badge) return;

  badge.textContent = state.workouts.length;

  if (state.workouts.length === 0) {
    container.innerHTML = '<div class="workout-list__empty">Noch keine Workouts synchronisiert.</div>';
    return;
  }

  const activityIcons = {
    running: '🏃', cycling: '🚴', strength: '🏋️',
    swimming: '🏊', hiking: '🥾', yoga: '🧘', default: '💪',
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

document.addEventListener('DOMContentLoaded', () => {
  fetchTodayFoodLog();
  fetchTodayHealth();
});
