/**
 * History Page – history.js (ES Module)
 * 
 * FIX: Benutzt jetzt shared.js statt eigener Duplikate.
 */
import { CONFIG, apiFetch, todayISO, formatDateShortDE } from './shared.js';

async function loadHistory(days) {
  const tbody = document.getElementById('history-tbody');
  const badge = document.getElementById('history-count-badge');
  
  tbody.innerHTML = '<tr><td colspan="7" style="text-align: center; color: var(--text-muted);">Daten werden geladen...</td></tr>';
  badge.textContent = `Letzte ${days} Tage`;

  try {
    const data = await apiFetch(CONFIG.ENDPOINTS.GET_SUMMARY + '?days=' + days, {
      method: 'GET',
    });

    const healthData = data.health_daily || [];
    const workoutsData = data.workouts || [];
    
    renderTable(healthData, workoutsData);

  } catch (err) {
    console.error('Fehler beim Laden der Historie:', err);
    tbody.innerHTML = `<tr><td colspan="7" style="text-align: center; color: var(--danger);">Fehler: ${err.message}<br>Läuft der Server auf Port 8765?</td></tr>`;
  }
}

function renderTable(healthData, workoutsData) {
  const tbody = document.getElementById('history-tbody');
  
  if (healthData.length === 0 && workoutsData.length === 0) {
    tbody.innerHTML = '<tr><td colspan="7" style="text-align: center; color: var(--text-muted);">Keine Daten in diesem Zeitraum gefunden.</td></tr>';
    return;
  }

  // Combined map by date
  const datesMap = {};
  
  healthData.forEach(h => {
    datesMap[h.date] = { health: h, workouts: [] };
  });

  workoutsData.forEach(w => {
    if (!datesMap[w.date]) {
      datesMap[w.date] = { health: {}, workouts: [] };
    }
    datesMap[w.date].workouts.push(w);
  });

  const sortedDates = Object.keys(datesMap).sort((a, b) => b.localeCompare(a));

  const rows = sortedDates.map(date => {
    const data = datesMap[date];
    const day = data.health;
    const wList = data.workouts;

    const workoutStr = wList.length > 0 
      ? wList.map(w => `<span style="background: var(--bg-card-hover); padding: 2px 6px; border-radius: 4px; font-size: 0.8em; margin-right: 4px; display: inline-block; margin-bottom: 2px;">${w.activity_type || 'Workout'}</span>`).join('') 
      : '-';

    return `
      <tr>
        <td style="white-space: nowrap; font-weight: 500;">${formatDateShortDE(date)}</td>
        <td style="color: ${day.hrv_avg && day.hrv_avg < 40 ? 'var(--warning)' : 'inherit'}">${day.hrv_avg != null ? day.hrv_avg : '-'}</td>
        <td style="color: ${day.sleep_score && day.sleep_score < 70 ? 'var(--warning)' : 'inherit'}">${day.sleep_score != null ? day.sleep_score : '-'}</td>
        <td>${day.resting_hr != null ? day.resting_hr : '-'}</td>
        <td style="color: ${day.stress_avg && day.stress_avg > 50 ? 'var(--warning)' : 'inherit'}">${day.stress_avg != null ? day.stress_avg : '-'}</td>
        <td>${day.steps != null ? day.steps.toLocaleString('de-DE') : '-'}</td>
        <td>${workoutStr}</td>
      </tr>
    `;
  });

  tbody.innerHTML = rows.join('');
}

document.addEventListener('DOMContentLoaded', () => {
  document.getElementById('btn-load-7').addEventListener('click', () => loadHistory(7));
  document.getElementById('btn-load-30').addEventListener('click', () => loadHistory(30));
  document.getElementById('btn-load-90').addEventListener('click', () => loadHistory(90));

  // Initial load
  loadHistory(30);
});