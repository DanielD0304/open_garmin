const state = {
  healthData: null,
  workouts: [],
};

async function syncGarmin() {
  setButtonLoading('garmin-sync-btn', true);

  try {
    const data = await apiFetch(CONFIG.ENDPOINTS.SYNC_GARMIN, {
      method: 'POST',
      body: JSON.stringify({ date: todayISO() }),
    });

    if (data.status === 'error') {
      showToast('⚠️ Garmin: ' + (data.message || 'Login fehlgeschlagen. Bitte manuell eingeben.'), 'warning');
      showManualHealthForm();
      return;
    }

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

async function syncHistoricalGarmin(days, btnId) {
  setButtonLoading(btnId, true);

  try {
    for (let i = 0; i < days; i++) {
      const d = new Date();
      d.setDate(d.getDate() - i);
      const isoDate = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;

      showToast(`Lade ${isoDate} (${i + 1}/${days})...`, 'info');

      const data = await apiFetch(CONFIG.ENDPOINTS.SYNC_GARMIN, {
        method: 'POST',
        body: JSON.stringify({ date: isoDate }),
      });

      if (data.status === 'error') {
        showToast('⚠️ Abbruch bei ' + isoDate + ': ' + (data.message || 'Fehler'), 'warning');
        break;
      }
    }
    showToast('✅ Daten im Hintergrund gespeichert! Der AI-Report kann sie jetzt nutzen.', 'success');
    fetchTodayHealth(); 
  } catch (err) {
    showToast('❌ Fehler beim Sync: ' + err.message, 'error');
  } finally {
    setButtonLoading(btnId, false);
  }
}

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
    console.warn('n8n nicht erreichbar:', err.message);
    showToast('⚠️ n8n nicht erreichbar – Daten nur lokal angezeigt.', 'warning');
  }

  state.healthData = payload;
  renderHealthMetrics();

  setButtonLoading('manual-health-submit-btn', false);
}

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

function showManualHealthForm() {
  const form = document.getElementById('manual-health-form');
  form.classList.add('is-visible');
}

document.addEventListener('DOMContentLoaded', () => {
  document.getElementById('garmin-sync-btn').addEventListener('click', syncGarmin);

  const btn7d = document.getElementById('garmin-sync-7d-btn');
  if (btn7d) btn7d.addEventListener('click', () => syncHistoricalGarmin(7, 'garmin-sync-7d-btn'));

  const btnAll = document.getElementById('garmin-sync-all-btn');
  if (btnAll) btnAll.addEventListener('click', () => syncHistoricalGarmin(30, 'garmin-sync-all-btn'));

  document.getElementById('health-refresh-btn').addEventListener('click', fetchTodayHealth);

  document.getElementById('manual-health-toggle').addEventListener('click', () => {
    const form = document.getElementById('manual-health-form');
    form.classList.toggle('is-visible');
  });

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

  fetchTodayHealth();
});