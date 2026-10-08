/**
 * Ernährung – nutrition.js (ES Module)
 *
 * Tagesbilanz gegen das Ziel aus Körperprofil + Garmin-Aktivität,
 * Nährwertsuche mit Claude (inkl. Rückfragen), Favoriten, Kosten.
 */
import {
  CONFIG, MEALS, apiGet, apiPost, apiPut, apiDelete, todayISO, shiftDate, guessMeal,
  fmt, euro, escapeHtml, showToast, setButtonLoading, usageLine, renderSidebarUsage,
} from './shared.js';

const E = CONFIG.ENDPOINTS;
const NUTRIENTS = [
  { key: 'protein_g', target: 'protein', label: 'Eiweiß', color: 'hsl(175, 70%, 55%)', kind: 'min' },
  { key: 'carbs_g', target: 'carbs', label: 'Kohlenhydrate', color: 'hsl(200, 80%, 60%)', kind: 'target' },
  { key: 'fat_g', target: 'fat', label: 'Fett', color: 'hsl(280, 60%, 65%)', kind: 'target' },
  { key: 'fiber_g', target: 'fiber', label: 'Ballaststoffe', color: 'hsl(150, 65%, 50%)', kind: 'min' },
  { key: 'sugar_g', target: 'sugar', label: 'Zucker', color: 'var(--text-muted)', kind: 'max' },
  { key: 'satfat_g', target: 'satfat', label: 'ges. Fett', color: 'var(--text-muted)', kind: 'max' },
  { key: 'salt_g', target: 'salt', label: 'Salz', color: 'var(--text-muted)', kind: 'max' },
];
const SUM_KEYS = ['calories', 'protein_g', 'carbs_g', 'sugar_g', 'fat_g', 'satfat_g', 'fiber_g', 'salt_g', 'price_eur'];
const ITEM_FIELDS = ['food_name', 'amount_text', 'calories', 'protein_g', 'carbs_g', 'sugar_g', 'fat_g',
  'satfat_g', 'fiber_g', 'salt_g', 'price_eur', 'source', 'notes'];

const state = {
  date: todayISO(),
  entries: [],
  favorites: [],
  targets: null,
  lookupItems: [],
  lookupComment: '',
  pending: null,     // laufende Claude-Suche mit Rückfragen
  lastUsage: null,
};
const $ = (s) => document.querySelector(s);

const sum = (entries) => Object.fromEntries(SUM_KEYS.map((k) => [k, entries.reduce((a, e) => a + (Number(e[k]) || 0), 0)]));
const pick = (obj) => Object.fromEntries(ITEM_FIELDS.map((k) => [k, obj[k] ?? null]));


// ── Laden ───────────────────────────────────────────────────────

async function loadDay() {
  const [log, targets] = await Promise.all([
    apiGet(`${E.GET_FOOD_LOG}?date=${state.date}`),
    apiGet(`${E.TARGETS}?date=${state.date}`),
  ]);
  state.entries = log.entries || [];
  state.targets = targets;
  renderAll();
}

async function loadFavorites() {
  state.favorites = (await apiGet(E.FAVORITES)).favorites || [];
  renderFavorites();
}


// ── Rendering ───────────────────────────────────────────────────

function renderAll() {
  const d = new Date(state.date + 'T12:00:00');
  $('#day-label').textContent = d.toLocaleDateString('de-DE', { weekday: 'long', day: '2-digit', month: '2-digit', year: 'numeric' });
  renderSummary();
  renderEntries();
  renderLookup();
}

function renderSummary() {
  const t = state.targets;
  if (!t) return;
  const s = sum(state.entries);
  const ratio = t.kcal ? s.calories / t.kcal : 0;
  const r = 52, c = 2 * Math.PI * r;
  const over = ratio > 1.05;
  $('#energy-ring').innerHTML = `
    <defs><linearGradient id="ring-grad" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="hsl(175, 75%, 48%)"/><stop offset="1" stop-color="hsl(200, 85%, 55%)"/></linearGradient></defs>
    <circle cx="60" cy="60" r="${r}" fill="none" stroke="var(--bg-input)" stroke-width="10"/>
    <circle cx="60" cy="60" r="${r}" fill="none" stroke="${over ? 'var(--danger)' : 'url(#ring-grad)'}" stroke-width="10"
      stroke-linecap="${ratio > 0 ? 'round' : 'butt'}" stroke-dasharray="${c * Math.min(ratio, 1)} ${c}" transform="rotate(-90 60 60)"/>
    <text x="60" y="56" text-anchor="middle" font-size="21" font-weight="700">${fmt(s.calories)}</text>
    <text x="60" y="73" text-anchor="middle" font-size="10" fill="var(--text-secondary)">von ${fmt(t.kcal)} kcal</text>
    <text x="60" y="88" text-anchor="middle" font-size="10" fill="var(--text-muted)">${s.calories <= t.kcal
      ? 'noch ' + fmt(t.kcal - s.calories) : fmt(s.calories - t.kcal) + ' drüber'}</text>`;

  $('#nutrient-bars').innerHTML = NUTRIENTS.map((n) => {
    const goal = t[n.target], val = s[n.key];
    const pct = goal ? Math.min(val / goal, 1) * 100 : 0;
    const bad = n.kind === 'max' ? val > goal : n.kind === 'target' ? val > goal * 1.15 : false;
    const prefix = n.kind === 'max' ? 'max ' : n.kind === 'min' ? 'min ' : '';
    return `<div class="nutrient-bar"><span>${n.label}</span>
      <div class="nutrient-bar__track"><div class="nutrient-bar__fill" style="width:${pct}%;background:${bad ? 'var(--danger)' : n.color}"></div></div>
      <span class="nutrient-bar__value ${bad ? 'over' : ''}">${fmt(val)} / ${prefix}${goal} g</span></div>`;
  }).join('') + (t.budget ? `
    <div class="nutrient-bar"><span><b>Bezahlt</b></span>
      <div class="nutrient-bar__track"><div class="nutrient-bar__fill" style="width:${Math.min(s.price_eur / t.budget, 1) * 100}%;
        background:${s.price_eur > t.budget ? 'var(--danger)' : 'var(--warning)'}"></div></div>
      <span class="nutrient-bar__value ${s.price_eur > t.budget ? 'over' : ''}">${euro(s.price_eur)} / ${euro(t.budget)}</span></div>` : '');

  $('#day-cost').textContent = euro(s.price_eur);

  const sourceText = {
    garmin: '<span class="source-pill">⌚ Garmin gemessen</span>',
    'garmin-basis': '<span class="source-pill">⌚ Garmin, Tag läuft noch</span>',
    schaetzung: '<span class="source-pill source-pill--estimate">geschätzt, keine Garmin-Daten</span>',
  }[t.source] || '';
  $('#derivation').innerHTML = `<b>Tagesziel ${fmt(t.kcal)} kcal</b>${sourceText}<br>` +
    t.steps.map((st, i) => `${i ? (st.kcal < 0 ? ' − ' : ' + ') : ''}${escapeHtml(st.label)} ${fmt(Math.abs(st.kcal))}`).join('') +
    ` · Eiweiß ${t.protein} g (${fmt(t.proteinPerKg, 1)} g/kg) · KH ${t.carbs} g · Fett ${t.fat} g` +
    (t.source === 'garmin-basis' ? '<br><span class="muted">Training und Bewegung, die Garmin heute noch misst, erhöhen das Ziel automatisch.</span>' : '');
}

function renderEntries() {
  if (!state.entries.length) {
    $('#entry-list').innerHTML = `<div class="food-log__empty"><span class="food-log__empty-icon">📋</span>Noch nichts eingetragen.</div>`;
    return;
  }
  $('#entry-list').innerHTML = Object.entries(MEALS).map(([key, label]) => {
    const items = state.entries.filter((e) => (e.meal_label || 'snack') === key);
    if (!items.length) return '';
    const s = sum(items);
    return `<div class="meal-group"><div class="meal-group__title">${label} · ${fmt(s.calories)} kcal · ${euro(s.price_eur)}</div>` +
      items.map((e) => `
      <div class="entry-row">
        <div>
          <div class="food-log__food-name">${escapeHtml(e.food_name)}
            ${e.amount_text ? `<span class="muted small">· ${escapeHtml(e.amount_text)}</span>` : ''}</div>
          <div class="food-log__food-meta">P ${fmt(e.protein_g)} g · KH ${fmt(e.carbs_g)} g · F ${fmt(e.fat_g)} g ·
            Bst ${fmt(e.fiber_g)} g · Salz ${fmt(e.salt_g, 1)} g
            ${/^https?:/.test(e.source || '') ? ` · <a href="${escapeHtml(e.source)}">Quelle</a>` : ''}</div>
        </div>
        <div class="entry-row__kcal">${fmt(e.calories)} kcal<br><span class="muted small">${euro(e.price_eur)}</span></div>
        <div class="row" style="gap:0">
          <button class="icon-btn" title="Als Favorit speichern" data-fav-entry="${e.id}">☆</button>
          <button class="icon-btn" title="Bearbeiten" data-edit-entry="${e.id}">✎</button>
          <button class="icon-btn icon-btn--danger" title="Löschen" data-del-entry="${e.id}">✕</button>
        </div>
      </div>`).join('') + '</div>';
  }).join('');
}

function renderFavorites() {
  $('#fav-chips').innerHTML = state.favorites.length
    ? state.favorites.map((f) => `<button class="chip" data-quick="${f.id}" title="${escapeHtml(f.amount_text || '')}">${escapeHtml(f.food_name)}<small>${fmt(f.calories)} kcal${f.price_eur != null ? ' · ' + euro(f.price_eur) : ''}</small></button>`).join('')
    : '<span class="small muted">Noch keine Favoriten. Speichere Einträge mit ☆ oder lege sie unter „Favoriten verwalten“ an.</span>';
  $('#fav-table').innerHTML = `<tr><th>Name</th><th>Menge</th><th>kcal</th><th>Eiweiß</th><th>KH</th><th>Fett</th><th>Preis</th><th></th></tr>` +
    (state.favorites.map((f) => `<tr><td>${escapeHtml(f.food_name)}</td><td>${escapeHtml(f.amount_text || '')}</td>
      <td>${fmt(f.calories)}</td><td>${fmt(f.protein_g)} g</td><td>${fmt(f.carbs_g)} g</td><td>${fmt(f.fat_g)} g</td><td>${euro(f.price_eur)}</td>
      <td style="white-space:nowrap"><button class="icon-btn" data-edit-fav="${f.id}">✎</button>
        <button class="icon-btn icon-btn--danger" data-del-fav="${f.id}">✕</button></td></tr>`).join('') ||
      '<tr><td colspan="8" class="muted">Noch keine Favoriten.</td></tr>');
}

function renderLookup() {
  const out = $('#claude-out');
  const usage = state.lastUsage ? `<div class="usage-line">${usageLine(state.lastUsage)}</div>` : '';
  const comment = state.lookupComment ? `<p class="small muted mt-12">${escapeHtml(state.lookupComment)}</p>` : '';

  if (state.pending?.questions?.length) {
    out.innerHTML = comment + state.pending.questions.map((q, qi) => `
      <div class="question-box">
        <p>${escapeHtml(q.question)}</p>
        <div class="chips">${q.options.map((o, oi) => `<button class="chip" data-opt="${qi}|${oi}">${escapeHtml(o)}</button>`).join('')}</div>
        <input class="form-input" id="answer-${qi}" placeholder="${q.options.length ? 'oder eigene Antwort…' : 'Deine Antwort…'}">
      </div>`).join('') + `
      <div class="row mt-12">
        <button class="btn btn--primary btn--sm" data-answer>Antworten &amp; weitersuchen</button>
        <button class="btn btn--secondary btn--sm" data-skip-questions>Einfach schätzen</button>
        <button class="btn btn--secondary btn--sm" data-cancel-lookup>Abbrechen</button>
      </div>` + usage;
    return;
  }
  if (!state.lookupItems.length) { out.innerHTML = usage; return; }
  out.innerHTML = comment + state.lookupItems.map((it, i) => `
    <div class="result-card">
      <div class="row" style="justify-content:space-between">
        <b>${escapeHtml(it.food_name)}</b>
        ${it.confidence ? `<span class="confidence confidence--${escapeHtml(it.confidence)}">${escapeHtml(it.confidence)}</span>` : ''}
      </div>
      <div class="small muted">${escapeHtml(it.amount_text)}</div>
      <div class="result-card__nutr"><b>${fmt(it.calories)} kcal</b><span>P ${fmt(it.protein_g)} g</span>
        <span>KH ${fmt(it.carbs_g)} g (Zucker ${fmt(it.sugar_g)})</span><span>F ${fmt(it.fat_g)} g (ges. ${fmt(it.satfat_g)})</span>
        <span>Bst ${fmt(it.fiber_g)} g</span><span>Salz ${fmt(it.salt_g, 1)} g</span><b>${euro(it.price_eur)}</b></div>
      ${it.notes ? `<div class="small muted">${escapeHtml(it.notes)}</div>` : ''}
      ${/^https?:/.test(it.source || '') ? `<div class="small"><a href="${escapeHtml(it.source)}">Quelle</a></div>`
        : it.source ? `<div class="small muted">Quelle: ${escapeHtml(it.source)}</div>` : ''}
      <div class="row mt-12">
        <button class="btn btn--primary btn--sm" data-take="${i}">Eintragen</button>
        <button class="btn btn--secondary btn--sm" data-take-edit="${i}">Anpassen…</button>
        <button class="btn btn--secondary btn--sm" data-take-fav="${i}">☆ Eintragen + Favorit</button>
      </div>
    </div>`).join('') +
    (state.lookupItems.length > 1 ? `<div class="row mt-12"><button class="btn btn--primary btn--sm" data-take-all>Alle eintragen</button></div>` : '') +
    usage;
}


// ── Dialog ──────────────────────────────────────────────────────

function openItemDialog({ title, item = {}, entryMode = true }) {
  const dlg = $('#item-dialog'), form = $('#item-form');
  $('#item-dialog-title').textContent = title;
  form.reset();
  for (const el of form.elements) {
    if (!el.name || el.type === 'checkbox') continue;
    el.value = item[el.name] ?? '';
  }
  if (entryMode && !item.meal_label) form.elements.meal_label.value = $('#quick-meal').value;
  form.querySelectorAll('[data-entry-only]').forEach((el) => el.classList.toggle('hidden', !entryMode));
  dlg.returnValue = '';
  dlg.showModal();
  return new Promise((resolve) => {
    dlg.addEventListener('close', () => {
      if (dlg.returnValue !== 'ok') return resolve(null);
      const data = {};
      for (const el of form.elements) {
        if (!el.name) continue;
        if (el.type === 'checkbox') data[el.name] = el.checked;
        else if (el.type === 'number') data[el.name] = el.value === '' ? null : Number(el.value);
        else data[el.name] = el.value;
      }
      resolve(data);
    }, { once: true });
  });
}


// ── Aktionen ────────────────────────────────────────────────────

async function addEntries(items, meal, alsoFavorite = false) {
  for (const item of items) {
    await apiPost(E.ADD_FOOD, {
      ...pick(item), date: state.date, meal_label: item.meal_label || meal,
      calories: item.calories || 0, protein_g: item.protein_g || 0, carbs_g: item.carbs_g || 0,
      fat_g: item.fat_g || 0, fiber_g: item.fiber_g || 0,
    });
    if (alsoFavorite) await apiPost(E.FAVORITES, pick(item));
  }
  if (alsoFavorite) await loadFavorites();
  await loadDay();
}

function scaled(item, factor) {
  if (factor === 1) return { ...item };
  const out = { ...item, amount_text: `${fmt(factor, 2)} × ${item.amount_text || 'Portion'}` };
  for (const k of SUM_KEYS) if (item[k] != null) out[k] = Math.round(item[k] * factor * 100) / 100;
  return out;
}

async function runLookup() {
  const btn = $('#claude-btn'), p = state.pending;
  setButtonLoading(btn, true);
  $('#claude-out').innerHTML = `<p class="small muted mt-12"><span class="inline-spinner"></span>${p.answers.length
    ? 'Suche mit deinen Antworten weiter…' : 'Suche Nährwerte und Preis…'}</p>`;
  try {
    const res = await apiPost(E.CLAUDE_LOOKUP,
      { text: p.text, date: p.date, meal: MEALS[p.meal], answers: p.answers, research: p.research }, CONFIG.TIMEOUT_AI);
    state.lookupComment = res.comment;
    state.lastUsage = res.usage;
    renderSidebarUsage(res.usage);
    if (res.status === 'question') {
      p.questions = res.questions;
      p.research = [p.research, res.research].filter(Boolean).join('\n');
    } else {
      state.pending = null;
      state.lookupItems = res.items;
      $('#claude-text').value = '';
    }
    renderLookup();
    if (res.status === 'ok' && !res.items.length) {
      $('#claude-out').insertAdjacentHTML('afterbegin', '<div class="error-box">Claude hat nichts gefunden.</div>');
    }
  } catch (err) {
    state.pending = null;
    $('#claude-out').innerHTML = `<div class="error-box">${escapeHtml(err.message)}</div>`;
  } finally {
    setButtonLoading(btn, false);
  }
}

async function askAdvice() {
  const btn = $('#advice-btn');
  setButtonLoading(btn, true);
  $('#advice-out').innerHTML = '<p class="small muted"><span class="inline-spinner"></span>Claude schaut sich deinen Tag an…</p>';
  try {
    const res = await apiPost(E.CLAUDE_ADVICE, { date: state.date }, CONFIG.TIMEOUT_AI);
    renderSidebarUsage(res.usage);
    $('#advice-out').innerHTML = `<div class="advice-box">${escapeHtml(res.text)}</div><div class="usage-line">${usageLine(res.usage)}</div>`;
  } catch (err) {
    $('#advice-out').innerHTML = `<div class="error-box">${escapeHtml(err.message)}</div>`;
  } finally {
    setButtonLoading(btn, false);
  }
}

async function handleClick(ev) {
  const b = ev.target.closest('button');
  if (!b) return;
  const d = b.dataset;

  if (d.quick) {
    const fav = state.favorites.find((f) => String(f.id) === d.quick);
    await addEntries([scaled(pick(fav), Number($('#quick-factor').value) || 1)], $('#quick-meal').value);
    showToast(`${fav.food_name} eingetragen.`, 'success');
  } else if (d.opt) {
    const [qi, oi] = d.opt.split('|').map(Number);
    b.parentElement.querySelectorAll('.chip').forEach((c) => c.classList.toggle('is-selected', c === b));
    $('#answer-' + qi).value = state.pending.questions[qi].options[oi];
  } else if (d.answer !== undefined || d.skipQuestions !== undefined) {
    state.pending.answers.push(...state.pending.questions.map((q, qi) => ({
      question: q.question, answer: d.answer !== undefined ? $('#answer-' + qi).value.trim() : '',
    })));
    state.pending.questions = [];
    await runLookup();
  } else if (d.cancelLookup !== undefined) {
    state.pending = null;
    state.lookupComment = '';
    renderLookup();
  } else if (d.take !== undefined || d.takeFav !== undefined) {
    const i = Number(d.take ?? d.takeFav);
    const [item] = state.lookupItems.splice(i, 1);
    await addEntries([item], $('#claude-meal').value, d.takeFav !== undefined);
    showToast('Eingetragen.', 'success');
  } else if (d.takeEdit !== undefined) {
    const i = Number(d.takeEdit);
    const data = await openItemDialog({ title: 'Eintrag anpassen', item: { ...state.lookupItems[i], meal_label: $('#claude-meal').value } });
    if (data) {
      state.lookupItems.splice(i, 1);
      await addEntries([data], data.meal_label, data.asFavorite);
    }
  } else if (d.takeAll !== undefined) {
    const items = state.lookupItems;
    state.lookupItems = [];
    await addEntries(items, $('#claude-meal').value);
  } else if (d.delEntry) {
    await apiPost(E.DELETE_FOOD, { id: Number(d.delEntry) });
    await loadDay();
  } else if (d.editEntry) {
    const entry = state.entries.find((e) => String(e.id) === d.editEntry);
    const data = await openItemDialog({ title: 'Eintrag bearbeiten', item: entry });
    if (data) {
      const { asFavorite, ...fields } = data;
      await apiPost(E.UPDATE_FOOD, { id: entry.id, ...fields });
      if (asFavorite) { await apiPost(E.FAVORITES, pick(fields)); await loadFavorites(); }
      await loadDay();
    }
  } else if (d.favEntry) {
    const entry = state.entries.find((e) => String(e.id) === d.favEntry);
    await apiPost(E.FAVORITES, pick(entry));
    b.textContent = '★';
    await loadFavorites();
    showToast('Als Favorit gespeichert.', 'success');
  } else if (d.editFav) {
    const fav = state.favorites.find((f) => String(f.id) === d.editFav);
    const data = await openItemDialog({ title: 'Favorit bearbeiten', item: fav, entryMode: false });
    if (data) { await apiPut(`${E.FAVORITES}/${fav.id}`, pick(data)); await loadFavorites(); }
  } else if (d.delFav) {
    if (!confirm('Favorit löschen?')) return;
    await apiDelete(`${E.FAVORITES}/${d.delFav}`);
    await loadFavorites();
  }
}


// ── Init ────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', async () => {
  for (const sel of ['#claude-meal', '#quick-meal', '#item-form [name=meal_label]']) {
    $(sel).innerHTML = Object.entries(MEALS).map(([k, v]) => `<option value="${k}">${v}</option>`).join('');
  }
  $('#claude-meal').value = $('#quick-meal').value = guessMeal();

  document.addEventListener('click', (ev) => handleClick(ev).catch((err) => showToast(err.message, 'error')));
  $('#prev-day').onclick = () => { state.date = shiftDate(state.date, -1); loadDay(); };
  $('#next-day').onclick = () => { state.date = shiftDate(state.date, 1); loadDay(); };
  $('#today-btn').onclick = () => { state.date = todayISO(); loadDay(); };
  $('#manage-favs-btn').onclick = () => {
    $('#fav-section').classList.toggle('hidden');
    $('#fav-section').scrollIntoView({ behavior: 'smooth' });
  };
  $('#manual-btn').onclick = async () => {
    const data = await openItemDialog({ title: 'Manuell eintragen' });
    if (data) await addEntries([data], data.meal_label, data.asFavorite).catch((err) => showToast(err.message, 'error'));
  };
  $('#new-fav-btn').onclick = async () => {
    const data = await openItemDialog({ title: 'Neuer Favorit', entryMode: false });
    if (data) { await apiPost(E.FAVORITES, pick(data)); await loadFavorites(); }
  };
  $('#claude-btn').onclick = () => {
    const text = $('#claude-text').value.trim();
    if (!text) return $('#claude-text').focus();
    state.pending = { text, date: state.date, meal: $('#claude-meal').value, answers: [], questions: [], research: '' };
    state.lookupItems = [];
    runLookup();
  };
  $('#claude-text').addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) $('#claude-btn').click();
  });
  $('#advice-btn').onclick = askAdvice;

  try {
    await Promise.all([loadDay(), loadFavorites()]);
  } catch (err) {
    showToast('Fehler beim Laden: ' + err.message, 'error');
  }
});
