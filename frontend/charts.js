/**
 * ═══════════════════════════════════════════════════════════════
 * AI Athletik- & Ernährungs-Coach – Charts Module (ES Module)
 * ═══════════════════════════════════════════════════════════════
 *
 * Reusable Chart.js helper functions for the dark theme dashboard.
 * Import via: import { initChartDefaults, createTrendChart, ... } from './charts.js'
 */

import { CONFIG, apiFetch } from './shared.js';

// ── Chart Color Palette ────────────────────────────────────────

export const CHART_COLORS = {
  hrv:      '#2db87a',   // hsl(150, 65%, 55%)
  sleep:    '#9b7ce8',   // hsl(250, 65%, 70%)
  hr:       '#d94f4f',   // hsl(0, 70%, 60%)
  stress:   '#e08a24',   // hsl(30, 80%, 55%)
  steps:    '#2dbf9e',   // hsl(175, 70%, 55%)
  calories: '#e8a317',   // hsl(38, 90%, 55%)
  protein:  '#2dbf9e',   // hsl(175, 70%, 55%)
  carbs:    '#3d9be0',   // hsl(200, 80%, 60%)
  fat:      '#a86dd9',   // hsl(280, 60%, 65%)
};

// ── Theme Constants ────────────────────────────────────────────

const THEME = {
  textSecondary: '#7a7f96',
  textMuted:     '#5a5e72',
  gridColor:     'rgba(255, 255, 255, 0.05)',
  tooltipBg:     'rgba(18, 20, 30, 0.92)',
  tooltipBorder: 'rgba(255, 255, 255, 0.08)',
  fontFamily:    "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
};


// ── Chart.js Global Defaults for Dark Theme ────────────────────

export function initChartDefaults() {
  if (typeof Chart === 'undefined') {
    console.warn('Chart.js not loaded – skipping initChartDefaults()');
    return;
  }

  Chart.defaults.color = THEME.textSecondary;
  Chart.defaults.font.family = THEME.fontFamily;
  Chart.defaults.font.size = 12;
  Chart.defaults.font.weight = 400;

  // Scale defaults
  Chart.defaults.scale.grid = {
    ...Chart.defaults.scale.grid,
    color: THEME.gridColor,
    drawBorder: false,
  };
  Chart.defaults.scale.ticks = {
    ...Chart.defaults.scale.ticks,
    color: THEME.textSecondary,
    padding: 8,
  };
  Chart.defaults.scale.border = {
    ...Chart.defaults.scale.border,
    color: THEME.gridColor,
  };

  // Plugin defaults
  Chart.defaults.plugins.legend.labels.color = THEME.textSecondary;
  Chart.defaults.plugins.legend.labels.usePointStyle = true;
  Chart.defaults.plugins.legend.labels.pointStyleWidth = 10;
  Chart.defaults.plugins.legend.labels.padding = 16;

  Chart.defaults.plugins.tooltip.backgroundColor = THEME.tooltipBg;
  Chart.defaults.plugins.tooltip.titleColor = '#e0e3ef';
  Chart.defaults.plugins.tooltip.bodyColor = '#c0c4d6';
  Chart.defaults.plugins.tooltip.borderColor = THEME.tooltipBorder;
  Chart.defaults.plugins.tooltip.borderWidth = 1;
  Chart.defaults.plugins.tooltip.cornerRadius = 8;
  Chart.defaults.plugins.tooltip.padding = 12;
  Chart.defaults.plugins.tooltip.displayColors = true;
  Chart.defaults.plugins.tooltip.boxPadding = 4;

  // Interaction defaults
  Chart.defaults.interaction.mode = 'index';
  Chart.defaults.interaction.intersect = false;

  // Element defaults
  Chart.defaults.elements.point.radius = 3;
  Chart.defaults.elements.point.hoverRadius = 6;
  Chart.defaults.elements.point.hitRadius = 12;
  Chart.defaults.elements.line.tension = 0.35;
  Chart.defaults.elements.line.borderWidth = 2;
  Chart.defaults.elements.bar.borderRadius = 4;
}


// ── Data Fetching ──────────────────────────────────────────────

/**
 * Fetch daily overview data for charts.
 * @param {number} days - Number of days to fetch (default 14)
 * @returns {Promise<Object>} Chart-ready data from the API
 */
export async function fetchDailyOverview(days = 14) {
  return await apiFetch(CONFIG.ENDPOINTS.DAILY_OVERVIEW + `?days=${days}`, { method: 'GET' });
}


// ── Chart Creators ─────────────────────────────────────────────

/**
 * Create a line chart for health metric trends.
 * @param {string} canvasId - The canvas element ID
 * @param {string[]} labels - X-axis labels (dates)
 * @param {Object[]} datasets - Chart.js dataset objects
 * @param {Object} options - Additional Chart.js options to merge
 * @returns {Chart} The Chart.js instance
 */
export function createTrendChart(canvasId, labels, datasets, options = {}) {
  const canvas = document.getElementById(canvasId);
  if (!canvas) {
    console.warn(`Canvas #${canvasId} not found`);
    return null;
  }

  const ctx = canvas.getContext('2d');

  const defaultOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: {
        position: 'top',
        align: 'end',
      },
    },
    scales: {
      x: {
        grid: { display: false },
        ticks: { maxRotation: 0, autoSkipPadding: 12 },
      },
      y: {
        beginAtZero: false,
        ticks: { padding: 8 },
      },
    },
  };

  // Deep merge options
  const mergedOptions = deepMerge(defaultOptions, options);

  return new Chart(ctx, {
    type: 'line',
    data: { labels, datasets },
    options: mergedOptions,
  });
}


/**
 * Create a doughnut chart for macro distribution.
 * @param {string} canvasId - The canvas element ID
 * @param {string[]} labels - Macro labels
 * @param {number[]} data - Macro values
 * @param {string[]} colors - Color array for each segment
 * @returns {Chart} The Chart.js instance
 */
export function createDoughnutChart(canvasId, labels, data, colors) {
  const canvas = document.getElementById(canvasId);
  if (!canvas) {
    console.warn(`Canvas #${canvasId} not found`);
    return null;
  }

  const ctx = canvas.getContext('2d');

  return new Chart(ctx, {
    type: 'doughnut',
    data: {
      labels,
      datasets: [{
        data,
        backgroundColor: colors,
        borderColor: 'transparent',
        borderWidth: 0,
        hoverOffset: 6,
        spacing: 2,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      cutout: '68%',
      plugins: {
        legend: {
          position: 'bottom',
          labels: {
            padding: 16,
            usePointStyle: true,
            pointStyleWidth: 10,
          },
        },
        tooltip: {
          callbacks: {
            label: (ctx) => {
              const total = ctx.dataset.data.reduce((a, b) => a + b, 0);
              const pct = total > 0 ? ((ctx.parsed / total) * 100).toFixed(1) : 0;
              return ` ${ctx.label}: ${ctx.parsed.toFixed(1)}g (${pct}%)`;
            },
          },
        },
      },
    },
  });
}


/**
 * Create a bar chart.
 * @param {string} canvasId - The canvas element ID
 * @param {string[]} labels - X-axis labels
 * @param {Object[]} datasets - Chart.js dataset objects
 * @param {Object} options - Additional Chart.js options to merge
 * @returns {Chart} The Chart.js instance
 */
export function createBarChart(canvasId, labels, datasets, options = {}) {
  const canvas = document.getElementById(canvasId);
  if (!canvas) {
    console.warn(`Canvas #${canvasId} not found`);
    return null;
  }

  const ctx = canvas.getContext('2d');

  const defaultOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: {
        position: 'top',
        align: 'end',
      },
    },
    scales: {
      x: {
        grid: { display: false },
        ticks: { maxRotation: 0, autoSkipPadding: 12 },
      },
      y: {
        beginAtZero: true,
        ticks: { padding: 8 },
      },
    },
  };

  const mergedOptions = deepMerge(defaultOptions, options);

  return new Chart(ctx, {
    type: 'bar',
    data: { labels, datasets },
    options: mergedOptions,
  });
}


// ── Utility: Destroy Chart ─────────────────────────────────────

/**
 * Safely destroy a Chart.js instance before re-creating.
 * @param {Chart|null} chartInstance - The chart to destroy
 */
export function destroyChart(chartInstance) {
  if (chartInstance && typeof chartInstance.destroy === 'function') {
    chartInstance.destroy();
  }
}


// ── Internal Helpers ───────────────────────────────────────────

/**
 * Deep merge two objects (simple recursive).
 */
function deepMerge(target, source) {
  const result = { ...target };
  for (const key of Object.keys(source)) {
    if (
      source[key] &&
      typeof source[key] === 'object' &&
      !Array.isArray(source[key]) &&
      target[key] &&
      typeof target[key] === 'object' &&
      !Array.isArray(target[key])
    ) {
      result[key] = deepMerge(target[key], source[key]);
    } else {
      result[key] = source[key];
    }
  }
  return result;
}
