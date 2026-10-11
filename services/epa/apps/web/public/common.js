const TOKEN_KEY = 'epa.token';
const ROLE_KEY = 'epa.role';

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

function esc(s) {
  return String(s ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function getToken() {
  return sessionStorage.getItem(TOKEN_KEY) || '';
}
function setToken(token, role) {
  if (token) sessionStorage.setItem(TOKEN_KEY, token);
  else sessionStorage.removeItem(TOKEN_KEY);
  if (role) sessionStorage.setItem(ROLE_KEY, role);
  else sessionStorage.removeItem(ROLE_KEY);
}

function hashParams() {
  const out = {};
  const h = location.hash.replace(/^#/, '');
  for (const part of h.split('&')) {
    if (!part) continue;
    const i = part.indexOf('=');
    if (i < 0) out[part] = '';
    else out[decodeURIComponent(part.slice(0, i))] = decodeURIComponent(part.slice(i + 1));
  }
  return out;
}

function fmt(ts) {
  if (!ts) return '—';
  const d = new Date(ts);
  return Number.isNaN(d.getTime()) ? String(ts) : d.toLocaleString();
}

function isoFromLocal(value) {
  const d = value ? new Date(value) : new Date(Date.now() + 3 * 86400000);
  return d.toISOString();
}

function localFromIso(iso, plusDays = 3) {
  const d = iso ? new Date(iso) : new Date(Date.now() + plusDays * 86400000);
  const pad = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

async function api(method, path, body, extra = {}) {
  const headers = { ...extra };
  const token = getToken();
  if (token) headers.authorization = `Bearer ${token}`;
  if (body !== undefined) headers['content-type'] = 'application/json';
  const res = await fetch(path, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) });
  const text = await res.text();
  let data = text;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = text;
  }
  if (!res.ok) {
    const err = new Error(data?.error?.message || res.statusText || 'request failed');
    err.status = res.status;
    err.code = data?.error?.code;
    err.body = data;
    throw err;
  }
  return data;
}

function flash(msg, kind = '') {
  return `<div class="flash ${kind}" role="status">${esc(msg)}</div>`;
}

const STATUS_RU = {
  INVITED: 'приглашение',
  STARTED: 'запуск',
  IN_PROGRESS: 'идёт',
  SUBMITTED: 'сдано',
  REVIEW: 'проверка',
  COMPLETED: 'завершено',
  EXPIRED: 'срок вышел',
  FAILED: 'ошибка',
  READY: 'готово',
  PROVISIONING: 'готовится',
  DESTROYED: 'удалено',
  TEARING_DOWN: 'удаляется',
};

const EVENT_RU = {
  session_started: 'Сессия началась',
  session_ended: 'Сессия завершена',
  file_changed: 'Правка файла',
  file_saved: 'Файл сохранён',
  file_created: 'Файл создан',
  file_deleted: 'Файл удалён',
  test_started: 'Тесты запущены',
  test_finished: 'Тесты закончились',
  terminal_command: 'Команда',
  git_commit: 'Коммит',
  snapshot_created: 'Снимок',
  large_insertion_signal: 'Крупная вставка',
  code_copied: 'Копирование',
  code_pasted: 'Вставка',
  submit_created: 'Решение сдано',
  review_requested: 'Нужны исправления',
  requirement_changed: 'Условие изменено',
};

function statusLabel(status) {
  return STATUS_RU[status] || status || '—';
}

function eventLabel(type) {
  return EVENT_RU[type] || type || 'сигнал';
}

function badge(status) {
  return `<span class="badge ${esc(status)}">${esc(statusLabel(status))}</span>`;
}

async function apiRaw(method, path, body, contentType, onUpload) {
  if (typeof onUpload === 'function') return apiRawUpload(method, path, body, contentType, onUpload);
  const headers = { 'content-type': contentType };
  const token = getToken();
  if (token) headers.authorization = `Bearer ${token}`;
  const res = await fetch(path, { method, headers, body });
  const text = await res.text();
  let data = text;
  try { data = text ? JSON.parse(text) : null; } catch { data = text; }
  if (!res.ok) {
    const err = new Error(data?.error?.message || res.statusText || 'request failed');
    err.status = res.status;
    throw err;
  }
  return data;
}

function apiRawUpload(method, path, body, contentType, onUpload) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open(method, path);
    xhr.setRequestHeader('content-type', contentType);
    const token = getToken();
    if (token) xhr.setRequestHeader('authorization', `Bearer ${token}`);
    xhr.upload.onprogress = (ev) => {
      if (ev.lengthComputable) onUpload(ev.loaded, ev.total);
    };
    xhr.onload = () => {
      const text = xhr.responseText;
      let data = text;
      try { data = text ? JSON.parse(text) : null; } catch { data = text; }
      if (xhr.status < 200 || xhr.status >= 300) {
        const err = new Error(data?.error?.message || xhr.statusText || 'request failed');
        err.status = xhr.status;
        reject(err);
        return;
      }
      resolve(data);
    };
    xhr.onerror = () => reject(new Error('не удалось загрузить файл'));
    xhr.send(body);
  });
}

/** File list and file view of the practice repository, for the employer and the candidate. */
async function renderRepo(el, practiceId) {
  if (!el) return null;
  let project;
  try {
    project = await api('GET', `/v1/practices/${practiceId}/project`);
  } catch (e) {
    el.innerHTML = `<p class="muted">${esc(e.message)}</p>`;
    return null;
  }
  let files = [];
  let fileError = '';
  try {
    files = (await api('GET', `/v1/practices/${practiceId}/files`)).items || [];
  } catch (e) {
    fileError = e.message;
  }
  const source = project.source === 'upload' ? 'Загружен работодателем' : 'Шаблон задания';
  const commits = (project.commits || []).slice(0, 8).map((c) =>
    `<li><code>${esc(String(c.sha).slice(0, 7))}</code> ${esc(c.message)} <span class="muted">${esc(c.author)}</span></li>`).join('');

  const paintList = () => {
    const shown = files.slice(0, 500);
    const rows = shown.map((f) =>
      `<li><button type="button" data-path="${esc(f.path)}">${esc(f.path)}</button><span class="muted">${esc(f.size)} б</span></li>`).join('');
    const more = files.length > shown.length ? `<li class="muted">Показаны первые ${shown.length} из ${files.length} файлов.</li>` : '';
    el.innerHTML = `
      <div class="repo-head">
        <strong>${esc(source)}</strong>
        <span class="muted">ветка main · коммитов ${esc((project.commits || []).length)}</span>
      </div>
      ${project.brief || project.briefFilename ? `<div class="repo-brief"><h3>Техническое задание</h3>${project.briefFilename ? `<div class="file-chip"><span class="muted">Загруженный файл</span><strong>${esc(project.briefFilename)}</strong></div>` : ''}${project.brief ? `<pre class="blob">${esc(project.brief)}</pre>` : ''}</div>` : ''}
      ${fileError ? `<p class="muted">${esc(fileError)}</p>` : `<ul class="repo-files">${rows || '<li class="muted">Файлов нет</li>'}${more}</ul>`}
      ${commits ? `<h3 class="repo-commits-title">Коммиты</h3><ul class="repo-commits">${commits}</ul>` : ''}`;
    el.querySelectorAll('.repo-files button').forEach((b) => b.addEventListener('click', () => { void paintFile(b.dataset.path); }));
  };

  const paintFile = async (filePath) => {
    el.innerHTML = `<div class="repo-head"><button type="button" class="linkish" id="repo-back">← к списку файлов</button><span>${esc(filePath)}</span></div><pre class="blob" id="repo-blob">Загрузка…</pre>`;
    $('#repo-back', el)?.addEventListener('click', paintList);
    try {
      const file = await api('GET', `/v1/practices/${practiceId}/file?path=${encodeURIComponent(filePath)}`);
      const blob = $('#repo-blob', el);
      if (blob) blob.textContent = file.binary ? `Файл бинарный, ${file.size} байт. В браузере он не показывается.` : file.content;
    } catch (e) {
      const blob = $('#repo-blob', el);
      if (blob) blob.textContent = e.message;
    }
  };

  paintList();
  return project;
}

function bindLogout() {
  $('#logout')?.addEventListener('click', () => {
    setToken('', '');
    location.href = '/';
  });
}

function listen(id, ev, fn) {
  const el = typeof id === 'string' ? document.getElementById(id) : id;
  el?.addEventListener(ev, fn);
}

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}
