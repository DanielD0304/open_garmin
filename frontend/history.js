/**
 * Historie – history.js (ES Module)
 *
 * Garmin-Gesundheitsdaten + Ernährung (kcal gegen Tagesziel, Eiweiß, Kosten) pro Tag.
 */
import { CONFIG, apiGet, todayISO, shiftDate, formatDateShortDE, fmt, euro, escapeHtml } from './shared.js';

const E = CONFIG.ENDPOINTS;
const $ = (s) => document.querySelector(s);

async function loadNutrition(days) {
  const end = todayISO(), start = shiftDate(end, -(days - 1));
  const [range, targets] = await Promise.all([
    apiGet(`${E.FOOD_RANGE}?start=${start}&end=${end}`),
    apiGet(`/api/targets/range?start=${start}&end=${end}`),
  ]);
  const perDay = {};
  for (const e of range.entries || []) {
    const d = perDay[e.date] ||= { kcal: 0, protein: 0, price: 0, n: 0 };
    d.kcal += e.calories || 0;
    d.protein += e.protein_g || 0;
    d.price += e.price_eur || 0;
    d.n += 1;
  }
  return { perDay, targets: targets.targets || {} };
}

function renderCostStats(perDay) {
  const today = todayISO();
  const inRange = (n) => Object.entries(perDay).filter(([d]) => d > shiftDate(today, -n));
  const total = (rows) => rows.reduce((a, [, v]) => a + v.price, 0);
  const week = inRange(7), month = Object.entries(perDay).filter(([d]) => d.startsWith(today.slice(0, 7)));
  $('#cost-stats').innerHTML = [
    ['Heute', euro(perDay[today]?.price || 0)],
    ['Letzte 7 Tage', euro(total(week))],
    ['Ø pro erfasstem Tag', euro(week.length ? total(week) / week.length : 0)],
    ['Monat bis heute', euro(total(month))],
  ].map(([l, v]) => `<div><div class="stat__label">${l}</div><div class="stat__value">${v}</div></div>`).join('');
}

function renderChart(perDay, targets) {
  const days = Array.from({ length: 14 }, (_, i) => shiftDate(todayISO(), i - 13));
  const goals = days.map((d) => targets[d]?.kcal || 0);
  const avgGoal = goals.reduce((a, b) => a + b, 0) / (goals.filter(Boolean).length || 1);
  const max = Math.max(avgGoal * 1.3, ...days.map((d) => perDay[d]?.kcal || 0), 1);
  $('#kcal-chart').innerHTML = `<div class="kcal-chart__target" style="bottom:${20 + avgGoal / max * 130}px"></div>` +
    days.map((d, i) => {
      const kcal = perDay[d]?.kcal || 0;
      const over = goals[i] && kcal > goals[i] * 1.05;
      return `<div class="kcal-chart__col" title="${d}: ${fmt(kcal)} von ${fmt(goals[i])} kcal">
        <div class="kcal-chart__bar ${over ? 'kcal-chart__bar--over' : ''}" style="height:${kcal / max * 130}px"></div>
        <span>${new Date(d + 'T12:00:00').toLocaleDateString('de-DE', { weekday: 'narrow' })}${d.slice(8)}</span></div>`;
    }).join('');
}

async function loadHistory(days) {
  const tbody = $('#history-tbody');
  $('#history-count-badge').textContent = `Letzte ${days} Tage`;
  tbody.innerHTML = '<tr><td colspan="10" class="muted" style="text-align:center">Daten werden geladen…</td></tr>';

  try {
    const [summary, nutrition] = await Promise.all([apiGet(`${E.GET_SUMMARY}?days=${days}`), loadNutrition(Math.max(days, 31))]);
    renderCostStats(nutrition.perDay);
    renderChart(nutrition.perDay, nutrition.targets);
    renderTable(summary, nutrition, days);
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="10" style="text-align:center;color:var(--danger)">Fehler: ${escapeHtml(err.message)}</td></tr>`;
  }
}

function renderTable(summary, nutrition, days) {
  const byDate = {};
  for (const h of summary.health_daily || []) (byDate[h.date] ||= { workouts: [] }).health = h;
  for (const w of summary.workouts || []) (byDate[w.date] ||= { workouts: [] }).workouts.push(w);
  const oldest = shiftDate(todayISO(), -(days - 1));
  for (const d of Object.keys(nutrition.perDay)) if (d >= oldest) byDate[d] ||= { workouts: [] };

  const dates = Object.keys(byDate).sort((a, b) => b.localeCompare(a));
  if (!dates.length) {
    $('#history-tbody').innerHTML = '<tr><td colspan="10" class="muted" style="text-align:center">Keine Daten in diesem Zeitraum.</td></tr>';
    return;
  }
  $('#history-tbody').innerHTML = dates.map((date) => {
    const day = byDate[date].health || {}, workouts = byDate[date].workouts;
    const food = nutrition.perDay[date], goal = nutrition.targets[date];
    const workoutStr = workouts.length
      ? workouts.map((w) => `<span style="background:var(--bg-card-hover);padding:2px 6px;border-radius:4px;font-size:.8em;margin-right:4px;display:inline-block">${escapeHtml(w.activity_type || 'Workout')}</span>`).join('')
      : '-';
    const kcalOver = food && goal && food.kcal > goal.kcal * 1.05;
    return `<tr>
      <td style="white-space:nowrap;font-weight:500">${formatDateShortDE(date)}</td>
      <td style="color:${day.hrv_avg && day.hrv_avg < 40 ? 'var(--warning)' : 'inherit'}">${day.hrv_avg ?? '-'}</td>
      <td style="color:${day.sleep_score && day.sleep_score < 70 ? 'var(--warning)' : 'inherit'}">${day.sleep_score ?? '-'}</td>
      <td>${day.resting_hr ?? '-'}</td>
      <td style="color:${day.stress_avg && day.stress_avg > 50 ? 'var(--warning)' : 'inherit'}">${day.stress_avg ?? '-'}</td>
      <td>${day.steps != null ? day.steps.toLocaleString('de-DE') : '-'}</td>
      <td>${workoutStr}</td>
      <td class="${kcalOver ? 'over' : ''}" style="white-space:nowrap">${food ? fmt(food.kcal) : '-'} / ${goal ? fmt(goal.kcal) : '-'}</td>
      <td>${food ? fmt(food.protein) + ' g' : '-'}</td>
      <td>${food ? euro(food.price) : '-'}</td>
    </tr>`;
  }).join('');
}

document.addEventListener('DOMContentLoaded', () => {
  $('#btn-load-7').addEventListener('click', () => loadHistory(7));
  $('#btn-load-30').addEventListener('click', () => loadHistory(30));
  $('#btn-load-90').addEventListener('click', () => loadHistory(90));
  loadHistory(30);
});
