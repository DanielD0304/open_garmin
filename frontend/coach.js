/**
 * AI Coach Page – coach.js (ES Module)
 */
import { CONFIG, apiFetch, todayISO, setButtonLoading, showToast } from './shared.js';

let isGeneratingReport = false;

async function generateReport() {
  if (isGeneratingReport) return;

  const btn = document.getElementById('generate-report-btn');
  const loading = document.getElementById('report-loading');
  const output = document.getElementById('report-output');

  isGeneratingReport = true;
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
    showToast('Report generiert!', 'success');
  } catch (err) {
    loading.classList.remove('is-active');
    output.textContent = 'Fehler: ' + err.message;
    showToast('Report-Generierung fehlgeschlagen.', 'error');
  } finally {
    isGeneratingReport = false;
    setButtonLoading('generate-report-btn', false);
    btn.disabled = false;
  }
}

function formatReportOutput(text) {
  return text
    .replace(/^### (.+)$/gm, '<h3>$1</h3>')
    .replace(/^## (.+)$/gm, '<h3>$1</h3>')
    .replace(/^# (.+)$/gm, '<h3>$1</h3>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
    .replace(/^- (.+)$/gm, '<li>$1</li>')
    .replace(/(<li>.*<\/li>)/s, '<ul>$1</ul>')
    .replace(/\n\n/g, '<br><br>')
    .replace(/\n/g, '<br>');
}

document.addEventListener('DOMContentLoaded', () => {
  const btn = document.getElementById('generate-report-btn');
  if (btn) {
    btn.addEventListener('click', generateReport);
  }
});