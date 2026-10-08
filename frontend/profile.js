/**
 * Profil & Ziele – profile.js (ES Module)
 *
 * Garmin-Verbindung, Körperprofil, Ziel, berechneter Bedarf und Claude-Nutzung.
 */
import {
  CONFIG, apiGet, apiPost, apiPut, todayISO, fmt, euro, fmtTokens, escapeHtml,
  showToast, setButtonLoading, renderSidebarUsage,
} from './shared.js';

const E = CONFIG.ENDPOINTS;
const $ = (s) => document.querySelector(s);
const state = { profile: null, targets: null, usage: null, garminConnected: false };


// ── Profil & Bedarf ─────────────────────────────────────────────

function fillForm(p) {
  for (const el of $('#profile-form').elements) {
    if (!el.name || p[el.name] === undefined) continue;
    if (el.type === 'checkbox') el.checked = !!p[el.name];
    else el.value = p[el.name];
  }
}

function weightForecast(p, t) {
  const target = Number(p.targetWeightKg), weight = Number(p.weightKg);
  if (!target || target === weight) return '';
  const perWeek = t.goalDelta * 7 / 7700; // ~7.700 kcal pro kg Körpermasse
  if (!perWeek || Math.sign(perWeek) !== Math.sign(target - weight)) {
    return `<div class="error-box">Dein Zielgewicht (${fmt(target, 1)} kg) passt nicht zum Ziel „${escapeHtml(t.goal)}“.</div>`;
  }
  const weeks = Math.ceil(Math.abs((target - weight) / perWeek));
  const when = new Date(Date.now() + weeks * 7 * 864e5).toLocaleDateString('de-DE', { month: 'long', year: 'numeric' });
  return `<p class="small mt-12">Mit ${fmt(Math.abs(perWeek), 2)} kg pro Woche erreichst du ${fmt(target, 1)} kg in etwa
    ${weeks} Wochen (≈ ${when}).</p>`;
}

function renderTargets() {
  const t = state.targets, p = state.profile;
  const source = { garmin: '⌚ gemessen (Garmin)', 'garmin-basis': '⌚ Garmin, Tag läuft noch', schaetzung: 'geschätzt' }[t.source];
  $('#targets-view').innerHTML = `<table class="data-table">
    ${t.steps.map((s) => `<tr><td>${escapeHtml(s.label)}</td><td>${s.kcal >= 0 && s !== t.steps[0] ? '+' : ''}${fmt(s.kcal)} kcal</td></tr>`).join('')}
    <tr><td><b>Tagesziel Energie</b> <span class="source-pill ${t.source === 'schaetzung' ? 'source-pill--estimate' : ''}">${source}</span></td>
      <td><b>${fmt(t.kcal)} kcal</b></td></tr>
    <tr><td>Eiweiß</td><td>${t.protein} g <span class="muted">(${fmt(t.proteinPerKg, 1)} g/kg)</span></td></tr>
    <tr><td>Kohlenhydrate</td><td>${t.carbs} g</td></tr>
    <tr><td>Fett</td><td>${t.fat} g</td></tr>
    <tr><td>Ballaststoffe</td><td>min ${t.fiber} g</td></tr>
    <tr><td>Zucker / ges. Fett / Salz</td><td>max ${t.sugar} / ${t.satfat} / ${t.salt} g</td></tr>
    <tr><td>Budget</td><td>${euro(t.budget)}</td></tr></table>` + weightForecast(p, t);
}

async function loadProfile() {
  [state.profile, state.targets] = await Promise.all([apiGet(E.PROFILE), apiGet(`${E.TARGETS}?date=${todayISO()}`)]);
  fillForm(state.profile);
  renderTargets();
  $('#welcome').classList.toggle('hidden', !!state.profile.onboarded);
}

async function saveProfile(ev) {
  ev.preventDefault();
  const data = { onboarded: true };
  for (const el of ev.target.elements) {
    if (!el.name) continue;
    if (el.type === 'checkbox') data[el.name] = el.checked;
    else if (el.type === 'number' || el.name === 'activity') data[el.name] = el.value === '' ? '' : Number(el.value);
    else data[el.name] = el.value;
  }
  await apiPut(E.PROFILE, data);
  await loadProfile();
  showToast('Profil gespeichert.', 'success');
  loadClaudeStatus();
}


// ── Garmin ──────────────────────────────────────────────────────

async function loadGarminStatus() {
  const { connected } = await apiGet(E.GARMIN_STATUS);
  state.garminConnected = connected;
  $('#garmin-badge').textContent = connected ? 'verbunden' : 'nicht verbunden';
  $('#garmin-connected').classList.toggle('hidden', !connected);
  $('#garmin-disconnected').classList.toggle('hidden', connected);
}

function openGarminDialog() {
  const form = $('#garmin-form');
  form.reset();
  $('#garmin-step-login').classList.remove('hidden');
  $('#garmin-step-mfa').classList.add('hidden');
  $('#garmin-error').classList.add('hidden');
  $('#garmin-dialog').showModal();
  form.elements.email.focus();
}

async function submitGarmin() {
  const form = $('#garmin-form'), btn = $('#garmin-submit'), err = $('#garmin-error');
  const mfaStep = !$('#garmin-step-mfa').classList.contains('hidden');
  err.classList.add('hidden');
  setButtonLoading(btn, true);
  try {
    let res;
    if (mfaStep) {
      res = await apiPost(E.GARMIN_MFA, { code: form.elements.code.value });
    } else {
      res = await apiPost(E.GARMIN_LOGIN, { email: form.elements.email.value, password: form.elements.password.value });
      form.elements.password.value = '';
    }
    if (res.mfa) {
      $('#garmin-step-login').classList.add('hidden');
      $('#garmin-step-mfa').classList.remove('hidden');
      form.elements.code.focus();
      return;
    }
    $('#garmin-dialog').close();
    showToast('Mit Garmin verbunden. Die letzten Tage werden synchronisiert.', 'success');
    await loadGarminStatus();
    await importFromGarmin();
  } catch (e) {
    err.textContent = e.message;
    err.classList.remove('hidden');
  } finally {
    setButtonLoading(btn, false);
  }
}

async function importFromGarmin() {
  const btn = $('#garmin-import-btn');
  setButtonLoading(btn, true);
  try {
    const res = await apiPost(E.GARMIN_PROFILE, {});
    const g = res.fromGarmin || {};
    const parts = [g.sex && (g.sex === 'm' ? 'männlich' : 'weiblich'), g.age && `${g.age} Jahre`,
      g.heightCm && `${g.heightCm} cm`, g.weightKg && `${fmt(g.weightKg, 1)} kg`, g.bodyFat && `${fmt(g.bodyFat, 1)} % KF`].filter(Boolean);
    showToast(parts.length ? `Aus Garmin übernommen: ${parts.join(', ')}` : 'Garmin hat keine Körperdaten geliefert.',
      parts.length ? 'success' : 'warning');
    await loadProfile();
  } catch (e) {
    showToast(e.message, 'error');
    if (e.code === 'garmin_auth_required') loadGarminStatus();
  } finally {
    setButtonLoading(btn, false);
  }
}


// ── Claude ──────────────────────────────────────────────────────

async function loadClaudeStatus() {
  const s = await apiGet(E.CLAUDE_STATUS);
  $('#claude-cli-status').textContent = s.found ? `Claude CLI: ${s.path}`
    : 'Claude CLI nicht gefunden. Installieren: irm https://claude.ai/install.ps1 | iex, danach „claude“ starten und /login.';
}

function resetText(ts) {
  if (!ts) return '';
  const d = new Date(ts * 1000);
  const sameDay = d.toDateString() === new Date().toDateString();
  return 'setzt zurück ' + (sameDay ? 'um ' : 'am ' + d.toLocaleDateString('de-DE', { weekday: 'short', day: '2-digit', month: '2-digit' }) + ', ') +
    d.toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' }) + ' Uhr';
}

function renderUsage() {
  const { rateLimit, updatedAt, log = [] } = state.usage;
  const w = rateLimit?.unifiedWindows;
  const pct = (u) => Math.round((u || 0) * 100);
  const limit = (label, win) => !win ? '' : `<div class="limit">
    <div class="row" style="justify-content:space-between"><b>${label}</b>
      <span><b>${pct(win.utilization)} % verbraucht</b> · noch ${100 - pct(win.utilization)} % frei</span></div>
    <div class="limit__track"><div class="limit__fill ${win.utilization > 0.8 ? 'limit__fill--high' : ''}" style="width:${pct(win.utilization)}%"></div></div>
    <div class="small muted">${resetText(win.resetsAt)}</div></div>`;
  $('#limit-view').innerHTML = w
    ? limit('5-Stunden-Fenster', w.five_hour) + limit('Wochenlimit', w.seven_day) +
      (rateLimit.status !== 'allowed' ? `<div class="error-box">Status: ${escapeHtml(rateLimit.status)}. Claude ist gerade limitiert.</div>` : '') +
      `<div class="small muted mt-12">Stand: ${new Date(updatedAt).toLocaleString('de-DE')}</div>`
    : '<p class="muted">Noch kein Stand bekannt. Klicke auf „Aktualisieren“ oder mach eine Claude-Suche.</p>';

  const today = todayISO();
  const todays = log.filter((r) => r.at.startsWith(today));
  const lookups = log.filter((r) => r.kind === 'lookup');
  const total = (arr) => arr.reduce((a, r) => a + r.total, 0);
  $('#usage-stats').innerHTML = [
    ['Anfragen heute', todays.length],
    ['Tokens heute', fmtTokens(total(todays))],
    ['Ø pro Suche', fmtTokens(lookups.length ? total(lookups) / lookups.length : 0)],
    ['Tokens gesamt', fmtTokens(total(log))],
  ].map(([l, v]) => `<div><div class="stat__label">${l}</div><div class="stat__value">${v}</div></div>`).join('');

  const KIND = { lookup: 'Suche', advice: 'Tagestipp', report: 'Coach-Report', 'limit-check': 'Limit-Abfrage' };
  $('#usage-table').innerHTML = `<tr><th>Zeit</th><th>Art</th><th>Modell</th><th>Rein</th><th>Raus</th><th>Gesamt</th><th>Websuchen</th><th>Dauer</th><th>API-Wert</th></tr>` +
    (log.slice(0, 40).map((r) => `<tr>
      <td>${new Date(r.at).toLocaleString('de-DE', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })}</td>
      <td>${KIND[r.kind] || escapeHtml(r.kind)}</td><td>${escapeHtml(String(r.model).replace(/^claude-/, '').replace(/-\d{8}$/, ''))}</td>
      <td>${fmtTokens(r.input + r.cacheRead + r.cacheWrite)}</td><td>${fmtTokens(r.output)}</td><td><b>${fmtTokens(r.total)}</b></td>
      <td>${r.webSearches || ''}</td><td>${fmt(r.durationMs / 1000)} s</td><td>${r.costUsd ? '$' + fmt(r.costUsd, 3) : '–'}</td></tr>`).join('') ||
    '<tr><td colspan="9" class="muted">Noch keine Anfragen.</td></tr>');
}

async function loadUsage() {
  state.usage = await apiGet(E.USAGE);
  renderUsage();
  renderSidebarUsage(state.usage);
}


// ── Init ────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', async () => {
  $('#profile-form').addEventListener('submit', (ev) => saveProfile(ev).catch((e) => showToast(e.message, 'error')));
  $('#garmin-login-btn').onclick = openGarminDialog;
  $('#garmin-submit').onclick = submitGarmin;
  $('#garmin-form').addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); submitGarmin(); } });
  $('#garmin-import-btn').onclick = importFromGarmin;
  $('#garmin-logout-btn').onclick = async () => {
    if (!confirm('Verbindung zu Garmin trennen? Die gespeicherten Daten bleiben erhalten.')) return;
    await apiPost(E.GARMIN_LOGOUT, {});
    loadGarminStatus();
  };
  $('#usage-refresh-btn').onclick = async () => {
    const btn = $('#usage-refresh-btn');
    setButtonLoading(btn, true);
    try { await apiPost(E.USAGE_REFRESH, {}, CONFIG.TIMEOUT_AI); await loadUsage(); }
    catch (e) { showToast(e.message, 'error'); }
    finally { setButtonLoading(btn, false); }
  };

  try {
    await Promise.all([loadProfile(), loadGarminStatus(), loadUsage(), loadClaudeStatus()]);
  } catch (e) {
    showToast('Fehler beim Laden: ' + e.message, 'error');
  }
  if (location.hash === '#claude') $('#claude').scrollIntoView();
});
