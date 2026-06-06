const state = {
  todayFoodLog: [],
  todayMacros: { calories: 0, protein: 0, carbs: 0, fat: 0, fiber: 0 },
  goals: {
    calories: 2500,
    protein: 150,
    carbs: 250,
    fat: 80
  }
};

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
    console.warn('n8n nicht erreichbar, Eintrag nur lokal gespeichert:', err.message);
    showToast('⚠️ n8n nicht erreichbar – Eintrag nur lokal gespeichert.', 'warning');
  }

  const localEntry = {
    id: generateId(),
    ...payload,
    created_at: new Date().toISOString(),
  };
  state.todayFoodLog.push(localEntry);
  recalcMacros();
  renderFoodLog();
  renderProgressBars();
}

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
  renderProgressBars();
  showToast('🗑️ Eintrag entfernt.', 'info');
}

async function fetchTodayFoodLog() {
  try {
    const data = await apiFetch(CONFIG.ENDPOINTS.GET_FOOD_LOG + '?date=' + todayISO(), {
      method: 'GET',
    });
    state.todayFoodLog = data.entries || [];
    recalcMacros();
    renderFoodLog();
    renderProgressBars();
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
    }),
    { calories: 0, protein: 0, carbs: 0, fat: 0, fiber: 0 }
  );
}

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

function renderProgressBars() {
  updateProgressBar('progress-cal', state.todayMacros.calories, state.goals.calories, 'kcal');
  updateProgressBar('progress-prot', state.todayMacros.protein, state.goals.protein, 'g');
  updateProgressBar('progress-carbs', state.todayMacros.carbs, state.goals.carbs, 'g');
  updateProgressBar('progress-fat', state.todayMacros.fat, state.goals.fat, 'g');
}

function updateProgressBar(idPrefix, current, max, unit) {
  const percentage = Math.min(100, Math.round((current / max) * 100)) || 0;
  const fillEl = document.getElementById(`${idPrefix}-fill`);
  const textEl = document.getElementById(`${idPrefix}-text`);
  
  if (fillEl) fillEl.style.width = `${percentage}%`;
  if (textEl) textEl.textContent = `${Math.round(current)} / ${max} ${unit}`;
}

document.addEventListener('DOMContentLoaded', () => {
  const form = document.getElementById('food-form');
  if (form) {
    form.addEventListener('submit', (e) => {
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

      e.target.reset();
      document.getElementById('food-name').focus();
      showToast('✅ Lebensmittel hinzugefügt!', 'success');
    });
  }

  fetchTodayFoodLog();
});
