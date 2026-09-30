/* PDF Renamer — Frontend */

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

let scanResults = [];
let lastSessionId = null;

// ─── Navigation ──────────────────────────────────────────────
$$('.nav-btn').forEach((btn) => {
  btn.addEventListener('click', () => {
    $$('.nav-btn').forEach((b) => b.classList.remove('active'));
    $$('.panel').forEach((p) => p.classList.remove('active'));
    btn.classList.add('active');
    $(`#panel-${btn.dataset.panel}`).classList.add('active');

    if (btn.dataset.panel === 'history') loadHistory();
    if (btn.dataset.panel === 'settings') loadSettings();
  });
});

// ─── Template selector ──────────────────────────────────────
$('#template-select').addEventListener('change', (e) => {
  const custom = $('#custom-template');
  if (e.target.value === 'custom') {
    custom.classList.remove('hidden');
    custom.focus();
  } else {
    custom.classList.add('hidden');
  }
});

// ─── Scan ────────────────────────────────────────────────────
$('#scan-btn').addEventListener('click', doScan);
$('#dir-input').addEventListener('keydown', (e) => { if (e.key === 'Enter') doScan(); });

async function doScan() {
  const dir = $('#dir-input').value.trim();
  if (!dir) return toast('Enter a directory path', 'error');

  const status = $('#scan-status');
  status.className = 'status-bar loading';
  status.innerHTML = '<span class="spinner"></span> Scanning directory...';
  status.classList.remove('hidden');
  $('#results-section').classList.add('hidden');

  try {
    const tplKey = $('#template-select').value;
    const tplValue = tplKey === 'custom' ? $('#custom-template').value.trim() : tplKey;
    const res = await api('/scan', { directory: dir, template: tplValue });
    if (res.error) throw new Error(res.error);

    scanResults = res.files || [];
    renderResults();
    status.className = 'status-bar success';
    status.textContent = `Found ${res.count} PDF${res.count !== 1 ? 's' : ''}`;
    $('#results-section').classList.remove('hidden');
  } catch (e) {
    status.className = 'status-bar error';
    status.textContent = e.message;
  }
}

// ─── Render results table ────────────────────────────────────
function renderResults() {
  const tbody = $('#results-body');
  tbody.innerHTML = '';
  $('#file-count').textContent = `${scanResults.length} file${scanResults.length !== 1 ? 's' : ''}`;

  scanResults.forEach((file, i) => {
    const tr = document.createElement('tr');
    tr.dataset.index = i;

    const conf = file.confidence || 0;
    const confColor = conf >= 0.8 ? 'var(--success)' : conf >= 0.5 ? 'var(--warning)' : 'var(--danger)';
    const sourceCls = (file.source || 'unknown').replace(/\s/g, '_');

    tr.innerHTML = `
      <td class="col-check"><input type="checkbox" class="row-check" data-i="${i}" checked></td>
      <td class="name-cell" title="${esc(file.original_name)}">${esc(file.original_name)}</td>
      <td><input class="editable-name" data-i="${i}" value="${esc(file.proposed_name)}"></td>
      <td><span class="badge ${sourceCls}">${esc(file.source)}</span></td>
      <td>
        <span class="confidence-bar"><span class="confidence-fill" style="width:${conf * 100}%;background:${confColor}"></span></span>
        ${Math.round(conf * 100)}%
      </td>
      <td><span class="status-icon" data-i="${i}"></span></td>
      <td class="actions-cell">
        <button class="btn-small" onclick="refetch(${i})" title="Re-fetch metadata">Retry</button>
      </td>
    `;
    tbody.appendChild(tr);
  });

  updateExecuteBtn();
}

// ─── Select all ──────────────────────────────────────────────
$('#select-all').addEventListener('change', (e) => {
  $$('.row-check').forEach((cb) => { cb.checked = e.target.checked; });
  updateExecuteBtn();
});
$('#header-check').addEventListener('change', (e) => {
  $$('.row-check').forEach((cb) => { cb.checked = e.target.checked; });
  $('#select-all').checked = e.target.checked;
  updateExecuteBtn();
});

document.addEventListener('change', (e) => {
  if (e.target.classList.contains('row-check')) updateExecuteBtn();
});

function updateExecuteBtn() {
  const checked = $$('.row-check:checked').length;
  $('#execute-btn').disabled = checked === 0;
  $('#execute-btn').textContent = checked ? `Rename Selected (${checked})` : 'Rename Selected';
}

// ─── Execute renames ─────────────────────────────────────────
$('#execute-btn').addEventListener('click', doExecute);

async function doExecute() {
  const files = [];
  $$('.row-check:checked').forEach((cb) => {
    const i = parseInt(cb.dataset.i);
    const nameInput = $(`.editable-name[data-i="${i}"]`);
    const file = scanResults[i];
    files.push({
      original_path: file.original_path,
      new_name: nameInput.value,
      source: file.source,
      metadata: file.metadata,
    });
  });

  if (!files.length) return;

  const status = $('#scan-status');
  status.className = 'status-bar loading';
  status.innerHTML = '<span class="spinner"></span> Renaming files...';

  try {
    const res = await api('/execute', { files });
    if (res.error) throw new Error(res.error);

    lastSessionId = res.session_id;
    $('#undo-last-btn').classList.remove('hidden');

    let ok = 0, fail = 0;
    (res.results || []).forEach((r) => {
      if (r.success) ok++; else fail++;
    });

    // Update status icons in table
    (res.results || []).forEach((r, idx) => {
      // Find matching row
      const rows = $$('.row-check:checked');
      if (rows[idx]) {
        const i = parseInt(rows[idx].dataset.i);
        const icon = $(`.status-icon[data-i="${i}"]`);
        if (icon) icon.textContent = r.success ? 'Done' : 'Err';
      }
    });

    status.className = 'status-bar success';
    status.textContent = `Renamed ${ok} file${ok !== 1 ? 's' : ''}` + (fail ? `, ${fail} failed` : '');
    toast(`Renamed ${ok} file${ok !== 1 ? 's' : ''}`, 'success');
  } catch (e) {
    status.className = 'status-bar error';
    status.textContent = e.message;
    toast(e.message, 'error');
  }
}

// ─── Undo last session ──────────────────────────────────────
$('#undo-last-btn').addEventListener('click', async () => {
  if (!lastSessionId) return;
  try {
    const res = await api('/undo', { session_id: lastSessionId });
    const undone = Array.isArray(res) ? res.filter((r) => r.success).length : 0;
    toast(`Undid ${undone} rename${undone !== 1 ? 's' : ''}`, 'success');
    lastSessionId = null;
    $('#undo-last-btn').classList.add('hidden');
  } catch (e) {
    toast(e.message, 'error');
  }
});

// ─── Re-fetch metadata ─────────────────────────────────────
async function refetch(i) {
  const file = scanResults[i];
  toast('Re-fetching metadata...', 'info');
  try {
    const res = await api('/scan', { directory: file.original_path.substring(0, file.original_path.lastIndexOf('/') || file.original_path.lastIndexOf('\\')) });
    if (res.files) {
      const match = res.files.find((f) => f.original_path === file.original_path);
      if (match) {
        scanResults[i] = match;
        const input = $(`.editable-name[data-i="${i}"]`);
        if (input) input.value = match.proposed_name;
        toast('Metadata updated', 'success');
        return;
      }
    }
    toast('Could not re-fetch', 'error');
  } catch (e) {
    toast(e.message, 'error');
  }
}

// ─── History ─────────────────────────────────────────────────
$('#refresh-history').addEventListener('click', loadHistory);

async function loadHistory() {
  try {
    const entries = await api('/history', null, 'GET');
    const tbody = $('#history-body');
    tbody.innerHTML = '';
    if (!entries.length) {
      tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;color:var(--text-dim);padding:32px">No rename history yet</td></tr>';
      return;
    }
    entries.forEach((entry, i) => {
      const tr = document.createElement('tr');
      if (entry.undone) tr.classList.add('undone-row');
      const ts = new Date(entry.timestamp).toLocaleString();
      const origName = entry.original_path.split(/[/\\]/).pop();
      const newName = entry.new_path.split(/[/\\]/).pop();
      tr.innerHTML = `
        <td>${i}</td>
        <td class="name-cell" title="${esc(entry.original_path)}">${esc(origName)}</td>
        <td class="name-cell" title="${esc(entry.new_path)}">${esc(newName)}</td>
        <td><span class="badge ${(entry.metadata_source || '').replace(/\s/g, '_')}">${esc(entry.metadata_source)}</span></td>
        <td style="white-space:nowrap">${ts}</td>
        <td>${entry.undone ? 'Undone' : 'Active'}</td>
        <td>${entry.undone ? '' : `<button class="btn-small" onclick="undoSingle(${i})">Undo</button>`}</td>
      `;
      tbody.appendChild(tr);
    });
  } catch (e) {
    toast(e.message, 'error');
  }
}

async function undoSingle(index) {
  try {
    const res = await api('/undo', { index });
    if (res.error) throw new Error(res.error);
    toast('Rename undone', 'success');
    loadHistory();
  } catch (e) {
    toast(e.message, 'error');
  }
}

// ─── Settings ────────────────────────────────────────────────
async function loadSettings() {
  try {
    const s = await api('/settings', null, 'GET');
    $('#zotero-api-key').value = s.zotero_api_key || '';
    $('#zotero-library-id').value = s.zotero_library_id || '';
    $('#zotero-library-type').value = s.zotero_library_type || 'user';
    $('#settings-template').value = s.template || 'standard';
    $('#settings-custom-template').value = s.custom_template || '';
  } catch (_) { /* ignore */ }
}

$('#settings-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const msg = $('#settings-status');
  try {
    await api('/settings', {
      zotero_api_key: $('#zotero-api-key').value.trim(),
      zotero_library_id: $('#zotero-library-id').value.trim(),
      zotero_library_type: $('#zotero-library-type').value,
      template: $('#settings-template').value,
      custom_template: $('#settings-custom-template').value.trim(),
    });
    msg.textContent = 'Saved';
    msg.className = 'status-msg ok';
    setTimeout(() => { msg.textContent = ''; }, 2000);
  } catch (err) {
    msg.textContent = err.message;
    msg.className = 'status-msg err';
  }
});

// ─── API helper ──────────────────────────────────────────────
async function api(path, body, method = 'POST') {
  const opts = { method, headers: { 'Content-Type': 'application/json' } };
  if (body && method !== 'GET') opts.body = JSON.stringify(body);
  const res = await fetch(path, opts);
  const data = await res.json();
  if (!res.ok && data.error) throw new Error(data.error);
  return data;
}

// ─── Toast ───────────────────────────────────────────────────
function toast(msg, type = 'info') {
  const el = document.createElement('div');
  el.className = `toast ${type}`;
  el.textContent = msg;
  $('#toast-container').appendChild(el);
  setTimeout(() => el.remove(), 4000);
}

// ─── Escape HTML ─────────────────────────────────────────────
function esc(s) {
  if (!s) return '';
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}

// ─── Init ────────────────────────────────────────────────────
loadSettings();
