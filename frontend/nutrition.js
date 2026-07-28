/**
 * Nutrition Page – nutrition.js (ES Module)
 */
import { CONFIG, apiFetch, todayISO, generateId, showToast, escapeHtml } from './shared.js';
import {
  initChartDefaults, createDoughnutChart,
  destroyChart, CHART_COLORS,
} from './charts.js';

const state = {
  todayFoodLog: [],
  todayMacros: { calories: 0, protein: 0, carbs: 0, fat: 0, fiber: 0 },
  goals: { calories: 2500, protein: 150, carbs: 250, fat: 80 },
  macroChart: null,
  searchTimeout: null,
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
    const result = await apiFetch(CONFIG.ENDPOINTS.ADD_FOOD, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
    // Use server-returned ID if available
    payload.id = result.id || generateId();
  } catch (err) {
    console.warn('Server nicht erreichbar, Eintrag nur lokal gespeichert:', err.message);
    showToast('Server nicht erreichbar – Eintrag nur lokal gespeichert.', 'warning');
    payload.id = generateId();
  }

  const localEntry = { ...payload, created_at: new Date().toISOString() };
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
    console.warn('Server nicht erreichbar, Eintrag nur lokal geloescht:', err.message);
  }

  state.todayFoodLog = state.todayFoodLog.filter(e => e.id !== entryId);
  recalcMacros();
  renderFoodLog();
  renderProgressBars();
  showToast('Eintrag entfernt.', 'info');
}

// Make deleteFoodEntry available for onclick handlers
window.deleteFoodEntry = deleteFoodEntry;

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
  updateMacroChart();
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
      <button class="food-log__delete" onclick="deleteFoodEntry(${entry.id})" title="Löschen">×</button>
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
      showToast('Lebensmittel hinzugefügt!', 'success');
    });
  }
  // Initialize Chart.js defaults & food search
  initChartDefaults();
  initFoodSearch();
  initBarcodeScanner();

  fetchTodayFoodLog();
});


// ── Macro Doughnut Chart ──────────────────────────────────────

function updateMacroChart() {
  const { protein, carbs, fat } = state.todayMacros;

  if (state.macroChart) {
    // Update existing chart data
    state.macroChart.data.datasets[0].data = [protein, carbs, fat];
    state.macroChart.update();
    return;
  }

  state.macroChart = createDoughnutChart(
    'chart-macros',
    ['Protein', 'Kohlenhydrate', 'Fett'],
    [protein, carbs, fat],
    [CHART_COLORS.protein, CHART_COLORS.carbs, CHART_COLORS.fat]
  );
}


// ── OpenFoodFacts Search ────────────────────────────────────

function initFoodSearch() {
  const searchInput = document.getElementById('food-search');
  const resultsContainer = document.getElementById('food-search-results');
  if (!searchInput || !resultsContainer) return;

  searchInput.addEventListener('input', () => {
    clearTimeout(state.searchTimeout);
    const query = searchInput.value.trim();

    if (query.length < 2) {
      resultsContainer.innerHTML = '';
      resultsContainer.classList.remove('is-visible');
      return;
    }

    state.searchTimeout = setTimeout(() => searchFood(query), 300);
  });

  // Close results on outside click
  document.addEventListener('click', (e) => {
    if (!e.target.closest('.food-search-wrapper')) {
      resultsContainer.innerHTML = '';
      resultsContainer.classList.remove('is-visible');
    }
  });
}

async function searchFood(query) {
  const resultsContainer = document.getElementById('food-search-results');

  try {
    const data = await apiFetch(CONFIG.ENDPOINTS.FOOD_SEARCH + `?q=${encodeURIComponent(query)}`, { method: 'GET' });
    const products = data.products || data || [];

    if (!Array.isArray(products) || products.length === 0) {
      resultsContainer.innerHTML = '<div class="food-search-empty">Keine Ergebnisse gefunden.</div>';
      resultsContainer.classList.add('is-visible');
      return;
    }

    resultsContainer.innerHTML = products.slice(0, 8).map(p => {
      const cal = p.calories_100g != null ? Math.round(p.calories_100g) : '?';
      const prot = p.protein_100g != null ? p.protein_100g.toFixed(1) : '?';
      const carb = p.carbs_100g != null ? p.carbs_100g.toFixed(1) : '?';
      const fatV = p.fat_100g != null ? p.fat_100g.toFixed(1) : '?';

      return `
        <div class="food-search-item" 
             data-name="${escapeHtml(p.food_name || p.product_name || '')}"
             data-cal="${p.calories_100g || 0}"
             data-prot="${p.protein_100g || 0}"
             data-carbs="${p.carbs_100g || 0}"
             data-fat="${p.fat_100g || 0}"
             data-fiber="${p.fiber_100g || 0}">
          <div class="food-search-item__name">${escapeHtml(p.food_name || p.product_name || 'Unbekannt')}</div>
          <div class="food-search-item__brand">${escapeHtml(p.brand || p.brands || '')}</div>
          <div class="food-search-item__macros">
            <span>${cal} kcal</span>
            <span>${prot}P</span>
            <span>${carb}C</span>
            <span>${fatV}F</span>
            <span class="food-search-item__per">/ 100g</span>
          </div>
        </div>`;
    }).join('');

    resultsContainer.classList.add('is-visible');

    // Add click handlers to populate form
    resultsContainer.querySelectorAll('.food-search-item').forEach(item => {
      item.addEventListener('click', () => populateFormFromSearch(item));
    });

  } catch (err) {
    console.warn('Lebensmittelsuche fehlgeschlagen:', err.message);
    resultsContainer.innerHTML = '<div class="food-search-empty">Suche fehlgeschlagen. Ist der Server erreichbar?</div>';
    resultsContainer.classList.add('is-visible');
  }
}

function populateFormFromSearch(item) {
  const amount = parseFloat(document.getElementById('food-amount').value) || 100;
  const factor = amount / 100;

  document.getElementById('food-name').value = item.dataset.name || '';
  document.getElementById('food-calories').value = Math.round(parseFloat(item.dataset.cal || 0) * factor);
  document.getElementById('food-protein').value = (parseFloat(item.dataset.prot || 0) * factor).toFixed(1);
  document.getElementById('food-carbs').value = (parseFloat(item.dataset.carbs || 0) * factor).toFixed(1);
  document.getElementById('food-fat').value = (parseFloat(item.dataset.fat || 0) * factor).toFixed(1);
  document.getElementById('food-fiber').value = (parseFloat(item.dataset.fiber || 0) * factor).toFixed(1);

  if (!document.getElementById('food-amount').value) {
    document.getElementById('food-amount').value = '100';
  }

  // Close search results
  const resultsContainer = document.getElementById('food-search-results');
  resultsContainer.innerHTML = '';
  resultsContainer.classList.remove('is-visible');
  document.getElementById('food-search').value = '';

  showToast(`"${item.dataset.name}" in Formular übernommen.`, 'info');
}


// ── Barcode Scanner ────────────────────────────────────────

function initBarcodeScanner() {
  const btn = document.getElementById('barcode-scan-btn');
  if (!btn) return;

  btn.addEventListener('click', async () => {
    // Check BarcodeDetector API support
    if (!('BarcodeDetector' in window)) {
      showToast('Barcode-Scanner wird von diesem Browser nicht unterstützt.', 'warning');
      return;
    }

    // Create modal
    const modal = document.createElement('div');
    modal.className = 'barcode-modal';
    modal.innerHTML = `
      <div class="barcode-modal__inner">
        <div class="barcode-modal__header">
          <h3>Barcode scannen</h3>
          <button class="barcode-modal__close" type="button">×</button>
        </div>
        <video class="barcode-modal__video" autoplay playsinline></video>
        <div class="barcode-modal__status">Kamera wird gestartet…</div>
      </div>`;
    document.body.appendChild(modal);

    const video = modal.querySelector('.barcode-modal__video');
    const status = modal.querySelector('.barcode-modal__status');
    const closeBtn = modal.querySelector('.barcode-modal__close');
    let stream = null;
    let scanning = true;

    const cleanup = () => {
      scanning = false;
      if (stream) stream.getTracks().forEach(t => t.stop());
      modal.remove();
    };

    closeBtn.addEventListener('click', cleanup);
    modal.addEventListener('click', (e) => {
      if (e.target === modal) cleanup();
    });

    try {
      stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: 'environment' },
      });
      video.srcObject = stream;
      status.textContent = 'Barcode vor die Kamera halten…';

      const detector = new BarcodeDetector({ formats: ['ean_13', 'ean_8', 'upc_a', 'upc_e'] });

      const scan = async () => {
        if (!scanning) return;
        try {
          const barcodes = await detector.detect(video);
          if (barcodes.length > 0) {
            const code = barcodes[0].rawValue;
            status.textContent = `Barcode erkannt: ${code} – Suche…`;
            cleanup();
            await lookupBarcode(code);
            return;
          }
        } catch (e) { /* ignore detect errors */ }
        if (scanning) requestAnimationFrame(scan);
      };

      video.addEventListener('loadeddata', () => requestAnimationFrame(scan));

    } catch (err) {
      status.textContent = 'Kamerazugriff verweigert.';
      showToast('Kamerazugriff nicht möglich.', 'error');
    }
  });
}

async function lookupBarcode(code) {
  try {
    const data = await apiFetch(CONFIG.ENDPOINTS.FOOD_BARCODE + `?code=${encodeURIComponent(code)}`, { method: 'GET' });
    const p = data.product || data;

    if (p && (p.food_name || p.product_name)) {
      document.getElementById('food-name').value = p.food_name || p.product_name || '';
      document.getElementById('food-calories').value = Math.round(p.calories_100g || 0);
      document.getElementById('food-protein').value = (p.protein_100g || 0).toFixed(1);
      document.getElementById('food-carbs').value = (p.carbs_100g || 0).toFixed(1);
      document.getElementById('food-fat').value = (p.fat_100g || 0).toFixed(1);
      document.getElementById('food-fiber').value = (p.fiber_100g || 0).toFixed(1);
      document.getElementById('food-amount').value = '100';
      showToast(`Produkt gefunden: ${p.food_name || p.product_name}`, 'success');
    } else {
      showToast('Kein Produkt für diesen Barcode gefunden.', 'warning');
    }
  } catch (err) {
    showToast('Barcode-Suche fehlgeschlagen: ' + err.message, 'error');
  }
}
