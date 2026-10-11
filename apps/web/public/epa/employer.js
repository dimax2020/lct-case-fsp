const app = () => document.getElementById('app');
let state = {
  practices: [], practice: null, tab: 'overview', files: [], file: null, content: '', me: '', suggestedDescription: '',
  vacancies: [], vacancyError: '', panel: null, createOpen: false,
  flow: { upload: null, processing: false, extract: null, extractTimer: null, reviewPending: false, reviewBaseline: '', advicePending: false, adviceBaseline: '', fillDescriptionId: '', fillBriefId: '', applying: false, aiRefreshing: false, aiPending: { tests: false, process: false }, aiBaseline: { tests: '', process: '' } },
  aiBundle: null,
};
let liveTimer = null;

function stopLive() {
  if (liveTimer) clearInterval(liveTimer);
  liveTimer = null;
}

function vscodeCard(s) {
  if (!s || !s.linked) return '<div class="flash">Кандидат ещё не открывал свою ссылку на расширение.</div>';
  if (s.connected) {
    return `<div class="flash ok">VS Code на связи. Событий: ${esc(s.eventCount)}. Последнее: ${esc(eventLabel(s.lastEventType))} · ${esc(fmt(s.lastEventAt || s.lastSeenAt))}.</div>`;
  }
  if (s.endedAt) return `<div class="flash warn">Сессия VS Code завершена ${esc(fmt(s.endedAt))}. Пробел после этого — отсутствие данных, не обвинение.</div>`;
  return '<div class="flash warn">Ссылка на расширение выдана, сигналов ещё нет. Это отсутствие телеметрии, а не оценка.</div>';
}

async function refreshProject() {
  const el = $('#project-box');
  if (!el || !state.practice) return;
  try {
    const project = await renderRepo($('#repo-browser'), state.practice.id);
    if (!project || !el) return;
    el.innerHTML = `
      <p>Адрес репозитория: <code>${esc(project.remote)}</code></p>
      <p class="muted">Git не спрашивает пароль. Клонировать и отправлять код можно сразу.</p>
      <h3>Что делает кандидат</h3>
      <pre class="howto">git clone ${esc(project.remote)}
cd ${esc((project.remote.split('/').pop() || 'project').replace(/\.git$/, ''))}
# правит файлы
git add .
git commit -m "что сделано"
git push</pre>
      <p class="muted">Закрыть задачу кандидат может только кнопкой на своей странице. Расширение и git push этого не делают.</p>`;
  } catch (e) {
    el.innerHTML = flash(e.message, 'error');
  }
}

async function refreshSuggestions() {
  const el = $('#task-suggestions');
  if (!el || !state.practice) return;
  try {
    const bundle = await api('GET', `/v1/practices/${state.practice.id}/ai`);
    const html = suggestionHtml(bundle.taskSuggestions);
    el.innerHTML = html || '<p class="muted">Модель ещё не предложила тесты. Откройте вкладку «Анализ» и нажмите «Предложить тесты по проекту».</p>';
  } catch (e) {
    el.innerHTML = flash(e.message, 'error');
  }
}

async function askModel(kind) {
  const key = kind === 'task-suggestions' ? 'tests' : 'process';
  const list = key === 'tests' ? (state.aiBundle?.taskSuggestions || []) : (state.aiBundle?.processReviews || []);
  state.flow.aiBaseline[key] = list.length ? list[list.length - 1].id : '';
  state.flow.aiPending[key] = true;
  const el = $('#ai-msg');
  if (el) el.innerHTML = '';
  paintAiLive(state.aiBundle);
  try {
    await api('POST', `/v1/practices/${state.practice.id}/${kind}`, {});
  } catch (e) {
    state.flow.aiPending[key] = false;
    paintAiLive(state.aiBundle);
    if (el) el.innerHTML = flash(e.message, 'error');
  }
}

async function retrySubmission(submissionId) {
  const el = $('#ai-msg');
  try {
    await api('POST', `/v1/submissions/${submissionId}/analysis`);
    if (el) el.innerHTML = flash('Анализ сдачи запущен снова.', 'ok');
    renderDetail();
  } catch (e) {
    if (el) el.innerHTML = flash(e.message, 'error');
  }
}

async function refreshVscode() {
  const el = $('#vscode-status');
  if (!el || !state.practice) return;
  try {
    el.innerHTML = vscodeCard(await api('GET', `/v1/practices/${state.practice.id}/vscode`));
  } catch (e) {
    el.innerHTML = flash(e.message, 'error');
  }
}

function loginView(err) {
  app().innerHTML = `
    <section class="card" id="login">
      <h1>Вход работодателя</h1>
      <p class="lede">Укажите своё имя. Пароль не нужен. То же имя в следующий раз откроет те же практики.</p>
      ${err ? flash(err, 'error') : ''}
      <form id="login-form">
        <label for="name">Ваше имя</label>
        <input id="name" autocomplete="name" required maxlength="80" placeholder="Анна">
        <button class="btn" type="submit">Войти</button>
      </form>
    </section>`;
  listen('login-form', 'submit', async (e) => {
    e.preventDefault();
    try {
      const session = await api('POST', '/v1/auth/login', { name: $('#name').value.trim(), role: 'employer' });
      if (session.role !== 'employer' && session.role !== 'auditor') throw new Error('Это вход кандидата. Откройте страницу кандидата.');
      setToken(session.token, session.role);
      state.me = session.email;
      await loadList();
    } catch (err) {
      setToken('', '');
      loginView(err.message);
    }
  });
}

function who(p) {
  if (p.candidateEmail) return `Выполняет: ${p.candidateEmail}`;
  const count = (p.vacancyIds && p.vacancyIds.length) || (p.vacancyId ? 1 : 0);
  if (count > 1) return `Закреплено за вакансиями: ${count}. Кандидат увидит задание после отклика`;
  if (count === 1) return 'Прикреплено к вакансии. Кандидат увидит задание после отклика';
  return 'Выберите вакансии, чтобы кандидат получил задание после отклика';
}

function takerStatus(status) {
  if (status === 'INVITED') return 'не начато';
  return statusLabel(status);
}

function practiceCard(p) {
  return `
    <section class="card task-card">
      <div class="task-head">
        <div>
          <button type="button" class="linkish open-practice" data-id="${esc(p.id)}">${esc(p.title)}</button>
          <div class="muted">дедлайн ${esc(fmt(p.deadline))}</div>
        </div>
        <button type="button" class="btn danger delete-practice" data-id="${esc(p.id)}">Удалить</button>
      </div>
      <h3>Закрепить за вакансией</h3>
      <p class="muted">Можно выбрать несколько вакансий.</p>
      <div class="pin-list" id="pin-${esc(p.id)}"><p class="muted">Загрузка вакансий…</p></div>
      <div id="pin-msg-${esc(p.id)}"></div>
      <h3>Кто взял тестовое</h3>
      <div class="takers" id="takers-${esc(p.id)}"><p class="muted">Загрузка…</p></div>
    </section>`;
}

function listView() {
  const items = state.practices.map(practiceCard).join('') || '<p class="muted">Заданий пока нет.</p>';
  app().innerHTML = `
    <h1>Тестовые задания</h1>
    <button class="btn" type="button" id="toggle-create" aria-expanded="${state.createOpen ? 'true' : 'false'}">Создать тестовое задание</button>
    <section class="card" id="create" ${state.createOpen ? '' : 'hidden'}>
      <h2>Новое задание</h2>
      <ol class="steps">
        <li>Назовите проект и загрузите zip. Сразу после загрузки модель определит, что это за проект и что он делает.</li>
        <li>Загрузите ТЗ или сгенерируйте описание и ТЗ. Сохраните текст.</li>
        <li>На карточке задания закрепите его за вакансиями. Ниже видно, кто взял тестовое. «Раскрыть» открывает обзор, ход работы, снимки кода, анализ и отчёт.</li>
      </ol>
      <form id="create-form">
        <label for="title">Название проекта</label>
        <input id="title" required minlength="3" maxlength="200" placeholder="Название задания">
        <label class="btn secondary file-btn"><span>Проект (zip)</span><input id="project-file" type="file" accept=".zip,application/zip"></label>
        <p class="muted" id="create-files">Техническое задание загружается на странице практики.</p>
        <label for="rules">Правила</label>
        <textarea id="rules">Работайте в VS Code с расширением EPA. Телеметрия ограничена открытой папкой задания.</textarea>
        <label for="deadline">Дедлайн</label>
        <input id="deadline" type="datetime-local" required>
        <button class="btn" type="submit">Создать и разобрать</button>
      </form>
      <div id="create-scale"></div>
      <div id="create-msg"></div>
    </section>
    <div id="task-cards">${items}</div>`;
  $('#deadline').value = localFromIso();
  const nameFile = (input, empty) => {
    input.addEventListener('change', () => {
      const span = input.parentElement?.querySelector('span');
      if (span) span.textContent = input.files?.[0]?.name || empty;
    });
  };
  nameFile($('#project-file'), 'Проект (zip)');
  $$('.open-practice').forEach((b) => b.addEventListener('click', () => openPractice(b.dataset.id)));
  $$('.delete-practice').forEach((b) => b.addEventListener('click', () => { void removePractice(b.dataset.id); }));
  listen('toggle-create', 'click', () => {
    state.createOpen = !state.createOpen;
    const card = $('#create');
    const button = $('#toggle-create');
    if (card) card.hidden = !state.createOpen;
    if (button) button.setAttribute('aria-expanded', state.createOpen ? 'true' : 'false');
  });
  listen('create-form', 'submit', onCreate);
  void hydrateTasks();
}

async function loadVacancyCatalog() {
  state.vacancyError = '';
  try {
    const res = await fetch('/api/v1/vacancies', { credentials: 'include' });
    if (!res.ok) throw new Error('не удалось загрузить вакансии');
    const data = await res.json();
    state.vacancies = Array.isArray(data) ? data : [];
  } catch (err) {
    state.vacancies = [];
    state.vacancyError = err.message;
  }
}

function selectedVacancyIds(practice) {
  return practice.vacancyIds?.length ? practice.vacancyIds : (practice.vacancyId ? [practice.vacancyId] : []);
}

function pinChoices(practice) {
  if (state.vacancyError) return `<p class="muted">${esc(state.vacancyError)}</p>`;
  const items = state.vacancies;
  if (!items.length) return '<p class="muted">Сначала создайте вакансию</p>';
  const selected = new Set(selectedVacancyIds(practice));
  const known = new Set(items.map((v) => v.id));
  const extra = selectedVacancyIds(practice).filter((id) => !known.has(id)).map((id) => ({ id, title: 'Вакансия' }));
  return [...items, ...extra].map((v) => `
    <label class="pin-choice">
      <input type="checkbox" class="pin-vacancy" data-id="${esc(practice.id)}" value="${esc(v.id)}" ${selected.has(v.id) ? 'checked' : ''}>
      <span>${esc(v.title)}</span>
    </label>`).join('');
}

function fillPin(p) {
  const box = document.getElementById(`pin-${p.id}`);
  if (!box) return;
  box.innerHTML = pinChoices(p);
}

async function hydrateTasks() {
  await loadVacancyCatalog();
  for (const practice of state.practices) fillPin(practice);
  $$('.pin-vacancy').forEach((input) => input.addEventListener('change', () => { void onPin(input.dataset.id); }));
  await Promise.all(state.practices.map((practice) => fillTakers(practice.id)));
}

async function onPin(practiceId) {
  const vacancyIds = [...document.querySelectorAll(`.pin-vacancy[data-id="${practiceId}"]:checked`)].map((input) => input.value);
  const box = document.getElementById(`pin-msg-${practiceId}`) || $('#vacancy-msg');
  try {
    const updated = await api('PUT', `/v1/practices/${practiceId}/vacancy`, { vacancyIds });
    const row = state.practices.find((item) => item.id === practiceId);
    if (row) {
      row.vacancyIds = updated.vacancyIds || [];
      row.vacancyId = updated.vacancyId;
    }
    if (state.practice?.id === practiceId) {
      state.practice.vacancyIds = updated.vacancyIds || [];
      state.practice.vacancyId = updated.vacancyId;
    }
    if (box) box.innerHTML = flash(vacancyIds.length ? 'Тестовое закреплено за выбранными вакансиями. Кандидат увидит его после отклика.' : 'Закрепление снято.', 'ok');
  } catch (err) {
    if (box) box.innerHTML = flash(err.message, 'error');
  }
}

async function fillTakers(practiceId) {
  const box = document.getElementById(`takers-${practiceId}`);
  if (!box) return;
  try {
    const data = await api('GET', `/v1/practices/${practiceId}/attempts`);
    const items = data.items || [];
    if (!items.length) {
      box.innerHTML = '<p class="muted">Пока никто не взял это задание.</p>';
      return;
    }
    box.innerHTML = items.map((attempt) => `
      <div class="taker">
        <strong>${esc(attempt.candidateEmail || 'Кандидат')}</strong>
        <span class="muted">${esc(takerStatus(attempt.status))}</span>
        ${badge(attempt.status)}
        <button type="button" class="btn secondary expand-attempt" data-id="${esc(attempt.id)}" aria-expanded="false">Раскрыть</button>
        <div class="attempt-panel" id="panel-${esc(attempt.id)}"></div>
      </div>`).join('');
    box.querySelectorAll('.expand-attempt').forEach((button) => button.addEventListener('click', () => { void toggleAttempt(button); }));
  } catch (err) {
    box.innerHTML = `<p class="muted">${esc(err.message)}</p>`;
  }
}

async function toggleAttempt(button) {
  const attemptId = button.dataset.id;
  const panel = document.getElementById(`panel-${attemptId}`);
  if (!panel) return;
  if (state.panel === panel) {
    panel.innerHTML = '';
    state.panel = null;
    button.textContent = 'Раскрыть';
    button.setAttribute('aria-expanded', 'false');
    return;
  }
  if (state.panel) state.panel.innerHTML = '';
  $$('.expand-attempt').forEach((item) => {
    item.textContent = 'Раскрыть';
    item.setAttribute('aria-expanded', 'false');
  });
  button.textContent = 'Свернуть';
  button.setAttribute('aria-expanded', 'true');
  panel.innerHTML = '<p class="muted">Открываем…</p>';
  try {
    state.practice = await api('GET', `/v1/practices/${attemptId}`);
    state.tab = 'overview';
    state.panel = panel;
    await renderDetail();
  } catch (err) {
    state.panel = null;
    button.textContent = 'Раскрыть';
    button.setAttribute('aria-expanded', 'false');
    panel.innerHTML = flash(err.message, 'error');
  }
}

async function onCreate(e) {
  e.preventDefault();
  const msg = $('#create-msg');
  try {
    const zip = $('#project-file').files?.[0];
    const created = await api('POST', '/v1/practices', {
      title: $('#title').value.trim(),
      description: '',
      rules: $('#rules').value,
      deadline: isoFromLocal($('#deadline').value),
    }, { 'idempotency-key': crypto.randomUUID() });
    if (zip) {
      paintCreateScale(0, 'Загрузка архива · 0%');
      const uploaded = await apiRaw('POST', `/v1/practices/${created.id}/project`, zip, 'application/zip', (loaded, total) => {
        const ratio = total ? loaded / total : 0;
        if (ratio >= 1) {
          paintCreateScale(0, 'Читаем архив');
          if (!state.flow.extractTimer) watchExtract(created.id, paintCreateScale);
        } else paintCreateScale(Math.round(ratio * 100), `Загрузка архива · ${Math.round(ratio * 100)}%`);
      });
      stopExtract();
      if (uploaded?.skipped) msg.innerHTML = flash(`Проект создан: ${uploaded.files} файлов. Папки зависимостей не копировались.`, 'ok');
    }
    msg.innerHTML = flash(zip ? 'Проект создан. Разбор уже идёт.' : `Создано: ${created.id}`, 'ok');
    await openPractice(created.id);
  } catch (err) {
    msg.innerHTML = flash(err.message, 'error');
  }
}

function tabBar(active) {
  const tabs = [
    ['overview', 'Обзор'],
    ['timeline', 'Ход работы'],
    ['code', 'Снимки кода'],
    ['ai', 'Анализ'],
    ['report', 'Отчёт'],
  ];
  return `<div class="tabs">${tabs.map(([id, label]) =>
    `<button type="button" data-tab="${id}" class="${id === active ? 'on' : ''}">${label}</button>`).join('')}</div>`;
}

function detailHost() {
  return state.panel || app();
}

function detailShell(inner, extra = '') {
  const p = state.practice;
  const embedded = Boolean(state.panel);
  detailHost().innerHTML = `
    <p><button type="button" class="linkish" id="back">${embedded ? 'Свернуть' : '← к списку'}</button></p>
    <h1>${esc(p.title)} ${badge(p.status)}</h1>
    <p class="muted">${esc(who(p))} · дедлайн ${esc(fmt(p.deadline))}</p>
    ${embedded ? '' : '<p><button type="button" class="btn danger" id="delete-practice">Удалить практику</button></p>'}
    ${tabBar(state.tab)}
    <div id="tab">${inner}</div>
    ${extra}`;
  listen('back', 'click', () => {
    if (embedded) {
      const host = state.panel;
      state.panel = null;
      if (host) host.innerHTML = '';
      const button = document.querySelector(`.expand-attempt[data-id="${p.id}"]`);
      if (button) {
        button.textContent = 'Раскрыть';
        button.setAttribute('aria-expanded', 'false');
      }
      return;
    }
    if (p.sourcePracticeId) {
      void openPractice(p.sourcePracticeId);
      return;
    }
    location.hash = '';
    loadList();
  });
  listen('delete-practice', 'click', () => { void removePractice(p.id); });
  $$('.tabs button').forEach((b) => b.addEventListener('click', () => { state.tab = b.dataset.tab; renderDetail(); }));
}

function materialsHtml() {
  const p = state.practice;
  return `
    <section class="card" id="materials">
      <div id="analysis-status"><p class="muted">Разбор проекта…</p></div>
      <h2>Проект и ТЗ</h2>
      <p class="muted">После загрузки проекта разбор начинается сразу: модель пишет, что это за проект и что он делает.</p>
      <label for="m-title">Название</label>
      <input id="m-title" required minlength="3" maxlength="200" value="${esc(p.title)}">
      <div class="actions">
        <label class="btn secondary file-btn">Загрузить проект (zip)<input id="upload-zip" type="file" accept=".zip,application/zip"></label>
      </div>
      <p class="muted">${p.projectSource === 'upload' ? 'Проект уже загружен. Новый zip заменит файлы.' : 'Zip ещё не загружен.'} Архив — до 4 ГБ. Папки зависимостей (node_modules, .git, .next, venv) в задание не копируются.</p>
      <div class="label-row">
        <label for="m-brief">Техническое задание</label>
        <div class="actions">
          <label class="btn secondary file-btn">Загрузить ТЗ<input id="upload-brief" type="file" accept=".md,.txt,.markdown,text/plain"></label>
          <button class="btn secondary" type="button" id="generate-brief" ${state.flow.fillBriefId ? 'disabled' : ''}>${state.flow.fillBriefId ? 'Генерируем…' : 'Сгенерировать'}</button>
        </div>
      </div>
      <p class="muted">Загрузите файл .md или .txt либо вставьте текст. После сохранения модель сверяет проект с этим ТЗ: что уже сделано и чего не хватает.</p>
      <div id="brief-file">${briefFileHtml(p)}</div>
      <textarea id="m-brief" placeholder="Текст ТЗ">${esc(p.brief || '')}</textarea>
      <div class="label-row">
        <label for="m-description">Описание для кандидата</label>
        <button class="btn" type="button" id="generate-description" ${state.flow.fillDescriptionId ? 'disabled' : ''}>${state.flow.fillDescriptionId ? 'Генерируем…' : 'Сгенерировать'}</button>
      </div>
      <textarea id="m-description" placeholder="Напишите сами или нажмите «Сгенерировать»">${esc(p.description || '')}</textarea>
      <div class="actions">
        <button class="btn secondary" type="button" id="save-materials">Сохранить</button>
      </div>
      <div id="materials-msg"></div>
      <div id="advice-status"></div>
    </section>`;
}

function vacancyHtml() {
  const p = state.practice;
  return `
    <section class="card" id="vacancy-card">
      <h2>Закрепить за вакансией</h2>
      <p class="muted">Можно выбрать несколько вакансий. После отклика кандидат сразу получает это тестовое.</p>
      <div class="pin-list" id="pin-${esc(p.id)}"><p class="muted">Загрузка вакансий…</p></div>
      <div id="vacancy-msg"></div>
      <h2>Кто взял тестовое</h2>
      <div id="attempt-list"><p class="muted">Загрузка…</p></div>
    </section>`;
}

function overviewHtml() {
  const p = state.practice;
  return `
    ${p.sourcePracticeId ? '' : vacancyHtml()}
    ${p.sourcePracticeId ? '' : materialsHtml()}
    <section class="card">
      <p class="muted">${esc(p.rules)}</p>
      <p>Рабочая среда: ${p.workspace ? `${esc(statusLabel(p.workspace.lifecycle))} · драйвер ${esc(p.workspace.driver)}` : 'ещё не создана'}. Кандидат пишет в VS Code и отправляет код командой git push. Доступа по SSH нет.</p>
      <div id="vscode-status"><p class="muted">Проверяем расширение…</p></div>
      <div id="project-box"><p class="muted">Репозиторий…</p></div>
      <div id="task-suggestions"><p class="muted">Модель готовит тесты для кандидата…</p></div>
      <div class="repo" id="repo-browser"><p class="muted">Файлы проекта…</p></div>
      ${p.status === 'SUBMITTED' ? `<button class="btn" id="start-review">Начать проверку</button>` : ''}
      ${p.status === 'REVIEW' ? `
        <div class="actions">
          <button class="btn secondary" id="request-changes">Запросить исправления</button>
          <button class="btn" id="complete">Завершить практику</button>
        </div>` : ''}
      <div id="overview-msg"></div>
    </section>`;
}

function timelineHtml(data) {
  const gaps = (data.interruptions || []).map((g) =>
    `<div class="flash warn">Пробел данных ${esc(g.kind)} (${esc(fmt(g.from))} – ${esc(fmt(g.to))}). Это отсутствие телеметрии, а не обвинение.</div>`).join('');
  const items = (data.items || []).map((e) => `
    <li data-snapshot="${esc(e.refs?.snapshotId || '')}" data-file="${esc(e.refs?.file || '')}">
      <div>
        <div class="type ${esc(e.type)}">${esc(eventLabel(e.type))}${e.client === 'vscode' ? ' · VS Code' : e.client === 'gateway' ? ' · браузер' : ''}</div>
        <div class="muted">${esc(fmt(e.occurredAt))}</div>
      </div>
      <div>${esc(e.summary)}</div>
    </li>`).join('');
  return `${gaps}<ul class="timeline" id="timeline">${items}</ul>
    <p class="muted">Нажмите событие со снимком, чтобы открыть код на этот момент. Крупная вставка — повод посмотреть внимательнее, а не вывод, что кандидат списал.</p>`;
}

function codeHtml() {
  const files = state.files.map((f) =>
    `<button type="button" data-path="${esc(f.path || f)}" class="${(f.path || f) === state.file ? 'on' : ''}">${esc(f.path || f)}</button>`).join('');
  return `
    <div class="row">
      <div>
        <label for="snap">Снимок</label>
        <select id="snap"></select>
      </div>
    </div>
    <div class="ide">
      <div class="tree" id="tree">${files}</div>
      <div class="editor-wrap">
        <div class="editor-bar"><span id="path">${esc(state.file || 'выберите файл')}</span></div>
        <textarea class="editor" id="code" readonly>${esc(state.content)}</textarea>
      </div>
      <pre class="term" id="meta"></pre>
    </div>`;
}

function reviewHtml(comments, changes) {
  const list = comments.map((c) => `
    <div class="comment">
      <div class="muted">${esc(c.filePath)}:${c.lineStart}–${c.lineEnd} · ${esc(c.status)} · submission ${esc(c.submissionId)}</div>
      <div>${c.bodyHtml}</div>
      ${c.status === 'OPEN' ? `<button type="button" class="btn secondary resolve" data-id="${esc(c.id)}">Закрыть комментарий</button>` : `<span class="muted">закрыт ${esc(fmt(c.resolvedAt))}</span>`}
    </div>`).join('') || '<p class="muted">Комментариев нет.</p>';
  return `
    <section class="card">
      <h2>Комментарий к строкам текущей отправки</h2>
      <form id="comment-form">
        <label for="c-file">Файл</label>
        <input id="c-file" required value="${esc(state.file || 'src/auth/password.js')}">
        <div class="row">
          <div><label for="c-from">Строка с</label><input id="c-from" type="number" min="1" value="1"></div>
          <div><label for="c-to">по</label><input id="c-to" type="number" min="1" value="1"></div>
        </div>
        <label for="c-body">Текст</label>
        <textarea id="c-body" required></textarea>
        <button class="btn" type="submit">Оставить комментарий</button>
      </form>
      <div id="review-msg"></div>
      ${list}
    </section>
    <section class="card">
      <h2>Изменение требования</h2>
      <form id="req-form">
        <label for="r-text">Текст</label>
        <textarea id="r-text" required></textarea>
        <label for="r-reason">Причина</label>
        <input id="r-reason" required>
        <label for="r-ac">Критерии приёмки (каждый с новой строки)</label>
        <textarea id="r-ac" required></textarea>
        <label for="r-due">Срок</label>
        <input id="r-due" type="datetime-local" required>
        <button class="btn" type="submit">Сохранить изменение условия</button>
      </form>
      ${(changes || []).map((c) => `<p>${esc(c.text)} · baseline ${esc(c.baseline_submission_id)} · revised ${esc(c.revised_submission_id || 'ожидается')}</p>`).join('')}
    </section>`;
}

const AUTHOR_RU = {
  mostly_typed: 'в основном набирал сам',
  mixed: 'часть набрал сам, часть вставил',
  mostly_pasted: 'большая часть кода вставлена, часто не из папки задания',
  insufficient_data: 'правок мало, вывода пока нет',
};

const AI_SIGNAL_RU = {
  no_sign: 'Признаков чужого фрагмента нет: правки похожи на набор в редакторе.',
  possible_external: 'Есть вставки извне папки или крупные куски сразу. Так бывает, когда фрагмент пришёл из нейросети или другого источника. Телеметрия этого не доказывает.',
  insufficient_data: 'Событий мало, про нейросеть сказать нельзя.',
};

function moduleRows(modules) {
  return (modules || []).map((m) => `
    <div class="comment">
      <strong>${esc(m.module)}</strong>
      <p>Активно ${esc(m.activeMinutes)} мин. Набрано ${esc(m.insertedChars)} символов, вставлено ${esc(m.pastedChars)}, вставок извне ${esc(m.externalPastes)}, крупных кусков ${esc(m.largeInsertions)}.</p>
    </div>`).join('');
}

function activityHtml(activity) {
  if (!activity) return '';
  const typed = Math.max(0, (activity.insertedChars || 0) - (activity.pastedChars || 0));
  return `<p>Набрано примерно ${esc(typed)} символов, вставлено ${esc(activity.pastedChars || 0)}, скопировано внутри папки ${esc(activity.copiedChars || 0)}. Вставок извне папки: ${esc(activity.externalPastes || 0)}, из этой папки: ${esc(activity.workspacePastes || 0)}.</p>`;
}

function suggestionHtml(items) {
  const cards = (items || []).map((a) => {
    const tests = (a.output?.tests || a.tests || []).map((t) => `
      <div class="comment">
        <strong>${esc(t.title)}</strong>
        <p>${esc(t.goal)}</p>
        <p class="muted">${esc(t.scenario)}</p>
        <p class="muted">${esc(t.evidence?.file)}:${t.evidence?.lineStart}–${t.evidence?.lineEnd}</p>
      </div>`).join('');
    const summary = a.output?.summary || a.summary;
    return `<section class="card"><h3>Тесты для кандидата · ${esc(a.status)}</h3>${a.error ? flash(a.error, 'warn') : ''}${summary ? `<p>${esc(summary)}</p>` : ''}${tests || '<p class="muted">Модель ещё считает или не нашла, на что сослаться в проекте.</p>'}</section>`;
  }).join('');
  return cards;
}

function aiHtml(bundle) {
  const analyses = (bundle.analyses || []).map((a) => {
    const findings = (a.output?.findings || []).map((f) => `
      <div class="find ${esc(f.severity)}">
        <strong>${esc(f.title)}</strong> · ${esc(f.severity)} · ${esc(f.category)}
        <p>${esc(f.explanation)}</p>
        <p class="muted">основание: ${esc(f.evidence?.file)}:${f.evidence?.lineStart}–${f.evidence?.lineEnd}. ${esc(a.label || 'рекомендация анализа, не решение')}</p>
      </div>`).join('');
    const authorship = a.output?.authorship;
    const who = authorship ? `<p><strong>Ход набора:</strong> ${esc(AUTHOR_RU[authorship.label] || authorship.label)}. ${esc(authorship.summary || '')}</p>${activityHtml(a.output?.activity)}` : activityHtml(a.output?.activity);
    const again = (a.status === 'FAILED' || a.status === 'RETRYING') && a.submissionId
      ? `<button class="btn secondary" type="button" data-retry-analysis="${esc(a.submissionId)}">Повторить анализ</button>`
      : '';
    return `<section class="card"><h2>Анализ сдачи ${esc(a.status)}</h2>${a.error ? flash(modelError(a.error, 'Повторить анализ'), 'warn') : ''}${who}${findings || '<p class="muted">Замечаний нет или анализ ещё не готов.</p>'}${again}</section>`;
  }).join('');
  const process = (bundle.processReviews || []).map((a) => {
    const label = a.output?.label;
    const signal = a.output?.aiSignal;
    return `<section class="card"><h2>Ревью по телеметрии · ${esc(a.status)}</h2>${a.error ? flash(a.error, 'warn') : ''}${label ? `<p><strong>Как писался код:</strong> ${esc(AUTHOR_RU[label] || label)}</p>` : ''}${signal ? `<p><strong>Нейросеть:</strong> ${esc(AI_SIGNAL_RU[signal] || signal)}</p>` : ''}<p>${esc(a.output?.summary || (a.status === 'SUCCEEDED' ? '' : 'Модель читает события папки задания.'))}</p>${moduleRows(a.output?.modules)}${activityHtml(a.output?.activity)}</section>`;
  }).join('');
  const qs = (bundle.questions || []).map((q) => `
    <div class="comment">
      <p>${esc(q.text)}</p>
      <p class="muted">${esc(q.evidence?.file)}:${q.evidence?.lineStart}–${q.evidence?.lineEnd}</p>
      ${q.answer ? `<p>Ответ: ${esc(q.answer.text)}</p><p class="muted">${esc(answerTime(q.answer.durationMs))}${q.answer.evaluation ? ` · оценка ${esc(q.answer.evaluation.score)} — рекомендация, не решение` : ''}</p>` : `<p class="muted">${q.shownAt ? 'кандидат открыл вопрос и отвечает' : 'ожидается ответ'}</p>`}
    </div>`).join('');
  return `
    ${activityHtml(bundle.activity)}
    <div class="actions">
      <button class="btn" type="button" id="suggest-tests">Предложить тесты по проекту</button>
      <button class="btn secondary" type="button" id="review-process">Ревью по телеметрии</button>
    </div>
    <div id="ai-live-tests"></div>
    <div id="ai-live-process"></div>
    <p id="ai-msg"></p>
    ${suggestionHtml(bundle.taskSuggestions)}
    ${process}
    ${analyses || flash('Разбор сдачи ещё не запускался. Он стартует после кнопки «Закрыть задачу» на странице кандидата. Сдача и тесты работают и без модели.', 'warn')}
    <h2>Вопросы по сданному коду</h2>${qs || '<p class="muted">Вопросы появятся после разбора сдачи: модель задаст их по загруженным файлам.</p>'}`;
}

function reportHtml(r) {
  if (!r) return flash('Отчёт появится после черновика оценки.', 'warn');
  const a = r.assessment;
  const dims = (a?.dimensions || []).map((d) => `
    <div class="score">
      <div class="muted">${esc(d.dimension)}${d.aiDerived ? ' · из анализа, не факт' : ''}</div>
      <div class="n">${d.score == null ? '—' : esc(d.score)}</div>
      <div class="bar"><span class="p${Math.max(0, Math.min(100, Math.round((d.score || 0) / 10) * 10))}"></span></div>
      <p>${esc(d.rationale)}</p>
    </div>`).join('');
  return `
    <section class="card">
      <h2>${esc(a?.label || 'Нет оценки')}</h2>
      <p>Итог: <strong>${a?.overall ?? '—'}</strong> · рубрика ${esc(r.rubricVersion)} · ${esc(a?.aggregation?.formula || '')}</p>
      <p class="muted">Итог — рекомендация, пока вы его не утвердите.</p>
      <div class="score-grid">${dims}</div>
      <div class="actions">
        <button class="btn" id="draft">Сформировать черновик</button>
        ${a && a.status === 'DRAFT' ? `<button class="btn secondary" id="approve">Утвердить</button>` : ''}
      </div>
      <h3>Сигналы</h3>
      <p class="muted">${esc(r.telemetrySignals?.note)}</p>
      ${(r.telemetrySignals?.largeInsertions || []).map((s) => `<div class="flash signal">${esc(s.file)} · ${esc(s.insertedChars)} символов ≥ ${esc(s.threshold)}</div>`).join('')}
    </section>`;
}

async function renderDetail() {
  stopLive();
  const p = state.practice;
  if (state.tab === 'review') state.tab = 'overview';
  if (state.tab === 'overview') {
    detailShell(overviewHtml());
    if (!p.sourcePracticeId) {
      void loadVacancySelect();
      void loadAttempts(p.id);
    }
    listen('upload-zip', 'change', onUploadZip);
    listen('upload-brief', 'change', onUploadBrief);
    listen('save-materials', 'click', saveMaterials);
    listen('generate-description', 'click', generateDescription);
    listen('generate-brief', 'click', generateBrief);
    void refreshVscode();
    void refreshProject();
    void refreshSuggestions();
    void refreshMaterials();
    let ticks = 0;
    liveTimer = setInterval(() => {
      ticks += 1;
      void refreshMaterials();
      if (ticks % 4 === 0) void refreshVscode();
    }, 1000);
    listen('start-review', 'click', async () => { await api('POST', `/v1/practices/${p.id}/review`); await openPractice(p.id); });
    listen('request-changes', 'click', async () => { await api('POST', `/v1/practices/${p.id}/request-changes`); await openPractice(p.id); });
    listen('complete', 'click', async () => { await api('POST', `/v1/practices/${p.id}/complete`); await openPractice(p.id); });
    return;
  }
  if (state.tab === 'timeline') {
    const tl = await api('GET', `/v1/practices/${p.id}/timeline?limit=200`);
    detailShell(timelineHtml(tl));
    const bindTimeline = () => $$('#timeline li').forEach((li) => li.addEventListener('click', () => {
      if (li.dataset.snapshot) {
        state.tab = 'code';
        state.snapshotId = li.dataset.snapshot;
        state.file = li.dataset.file || state.file;
        renderDetail();
      }
    }));
    bindTimeline();
    liveTimer = setInterval(async () => {
      if (state.tab !== 'timeline' || !state.practice) return;
      try {
        const next = await api('GET', `/v1/practices/${state.practice.id}/timeline?limit=200`);
        const tab = $('#tab');
        if (!tab) return;
        tab.innerHTML = timelineHtml(next);
        bindTimeline();
      } catch {
        /* keep the last timeline */
      }
    }, 4000);
    return;
  }
  if (state.tab === 'code') {
    const snaps = await api('GET', `/v1/practices/${p.id}/snapshots`);
    const subs = await api('GET', `/v1/practices/${p.id}/submissions`);
    if (!state.snapshotId) state.snapshotId = subs.items[subs.items.length - 1]?.snapshotId || snaps.items[snaps.items.length - 1]?.id;
    if (state.snapshotId) {
      const tree = await api('GET', `/v1/snapshots/${state.snapshotId}/tree`);
      state.files = tree.files || [];
      if (state.file) {
        try {
          const f = await api('GET', `/v1/snapshots/${state.snapshotId}/file?path=${encodeURIComponent(state.file)}`);
          state.content = f.content;
        } catch {
          state.content = '';
        }
      }
    }
    detailShell(codeHtml());
    const sel = $('#snap');
    for (const s of snaps.items) {
      const o = document.createElement('option');
      o.value = s.id;
      o.textContent = `${s.kind} ${s.reason} ${s.id.slice(0, 12)}`;
      if (s.id === state.snapshotId) o.selected = true;
      sel.appendChild(o);
    }
    sel.addEventListener('change', () => { state.snapshotId = sel.value; renderDetail(); });
    $$('#tree button').forEach((b) => b.addEventListener('click', () => { state.file = b.dataset.path; renderDetail(); }));
    return;
  }
  if (state.tab === 'ai') {
    const bundle = await api('GET', `/v1/practices/${p.id}/ai`);
    detailShell(aiHtml(bundle));
    listen('suggest-tests', 'click', () => askModel('task-suggestions'));
    listen('review-process', 'click', () => askModel('process-review'));
    $$('[data-retry-analysis]').forEach((b) => b.addEventListener('click', () => { void retrySubmission(b.dataset.retryAnalysis); }));
    state.aiBundle = bundle;
    paintAiLive(bundle);
    liveTimer = setInterval(() => { void refreshAiLive(); }, 1000);
    return;
  }
  if (state.tab === 'report') {
    let report = null;
    try { report = await api('GET', `/v1/practices/${p.id}/report`); } catch (e) { report = { error: e.message }; }
    detailShell(reportHtml(report.error ? null : report) + (report.error ? flash(report.error, 'warn') : ''));
    listen('draft', 'click', async () => { await api('POST', `/v1/practices/${p.id}/assessments`); renderDetail(); });
    listen('approve', 'click', async () => {
      const r = await api('GET', `/v1/practices/${p.id}/report`);
      if (r.assessment?.id) await api('POST', `/v1/assessments/${r.assessment.id}/approve`);
      renderDetail();
    });
  }
}

function materialsMessage(text, kind) {
  const msg = $('#materials-msg');
  if (msg) msg.innerHTML = flash(text, kind);
}

function scaleMarkup(title, pct, label, kind) {
  const width = Math.max(0, Math.min(100, Math.round(pct)));
  return `<div class="scale"><div class="scale-head"><strong>${esc(title)}</strong><span class="muted">${esc(label)}</span></div><div class="bar ${kind || ''}"><span style="width:${width}%"></span></div></div>`;
}

function paintCreateScale(pct, label) {
  const el = $('#create-scale');
  if (el) el.innerHTML = scaleMarkup('Загрузка и обработка', pct, label, 'busy');
}

function markReviewPending() {
  const reviews = state.aiBundle?.materialsReviews || [];
  state.flow.reviewBaseline = reviews.length ? reviews[reviews.length - 1].id : '';
  state.flow.reviewPending = true;
}

function markAdvicePending() {
  const items = state.aiBundle?.improvements || [];
  state.flow.adviceBaseline = items.length ? items[items.length - 1].id : '';
  state.flow.advicePending = true;
}

function stopExtract() {
  if (state.flow.extractTimer) clearInterval(state.flow.extractTimer);
  state.flow.extractTimer = null;
}

function watchExtract(practiceId, onUpdate) {
  stopExtract();
  const pull = async () => {
    try {
      const data = await api('GET', `/v1/practices/${practiceId}/setup-progress`);
      state.flow.extract = data.extract;
      if (data.extract?.total) {
        const pct = Math.round((100 * data.extract.done) / data.extract.total);
        onUpdate?.(pct, `Записываем файлы · ${data.extract.done} из ${data.extract.total}`);
      }
      paintMaterials();
    } catch {
      /* the upload request reports the failure */
    }
  };
  void pull();
  state.flow.extractTimer = setInterval(() => { void pull(); }, 400);
}

function analysisView(latest) {
  const flow = state.flow;
  if (flow.upload != null) {
    const pct = Math.round(flow.upload * 100);
    return { pct, label: `Загрузка архива · ${pct}%`, kind: 'busy', summary: '' };
  }
  if (flow.processing) {
    const extract = flow.extract;
    if (extract?.total) {
      const pct = Math.round((100 * extract.done) / extract.total);
      return { pct, label: `Записываем файлы · ${extract.done} из ${extract.total}`, kind: 'busy', summary: '' };
    }
    return { pct: 0, label: 'Читаем архив', kind: 'busy', summary: '' };
  }
  if (flow.reviewPending && (!latest || latest.id === flow.reviewBaseline)) {
    return { pct: 0, label: 'Разбор в очереди', kind: 'busy', summary: '' };
  }
  flow.reviewPending = false;
  if (!latest) return { pct: 0, label: 'Загрузите проект — разбор начнётся сразу', kind: '', summary: '' };
  if (latest.status === 'QUEUED') return { pct: 0, label: 'Разбор в очереди', kind: 'busy', summary: '' };
  if (latest.status === 'RUNNING' || latest.status === 'RETRYING') {
    const pct = Math.max(0, Math.min(99, Number(latest.progress) || 0));
    const withBrief = Boolean(state.practice?.brief?.trim());
    const writing = withBrief ? 'Модель сверяет проект с ТЗ' : 'Модель пишет, что это за проект';
    return { pct, label: pct >= 80 ? 'Собираем текст разбора' : pct >= 40 ? writing : 'Читаем исходники и ТЗ', kind: 'busy', summary: '' };
  }
  if (latest.status === 'SUCCEEDED') {
    const withBrief = Boolean(state.practice?.brief?.trim());
    return { pct: 100, label: withBrief ? 'Проект сверен с ТЗ' : 'Проект разобран', kind: '', summary: latest.output?.summary || '' };
  }
  return { pct: 100, label: 'Разбор остановился', kind: 'bad', summary: modelError(latest.error) };
}

function modelError(text, retry = 'Повторить разбор') {
  if (!text) return `Модель не ответила. Нажмите «${retry}».`;
  if (/timeout|aborted|не успела/i.test(text)) return `Модель не успела закончить ответ. Нажмите «${retry}».`;
  if (/not valid JSON|invalid_output|violates schema/i.test(text)) return `Ответ модели оборвался и не собрался в текст. Нажмите «${retry}».`;
  if (/fetch failed|unavailable|ECONNREFUSED|ECONNRESET|HeadersTimeout|связаться с Ollama/i.test(text)) return `Не удалось связаться с моделью. Нажмите «${retry}».`;
  return text;
}

function answerTime(ms) {
  const n = Number(ms);
  if (!Number.isFinite(n) || n < 0) return '';
  const sec = Math.round(n / 1000);
  if (sec < 60) return `отвечал ${Math.max(sec, 1)} с`;
  const min = sec / 60;
  return `отвечал ${min < 10 ? min.toFixed(1) : Math.round(min)} мин`;
}

function analysisCard(view) {
  return `<div class="analysis ${esc(view.kind)}">
    <div class="analysis-num">${esc(view.pct)}<small>%</small></div>
    <div class="meter ${esc(view.kind)}"><span style="width:${esc(view.pct)}%"></span></div>
    <p class="analysis-label">${esc(view.label)}</p>
    ${view.summary ? `<p class="analysis-summary">${esc(view.summary)}</p>` : ''}
    ${view.kind === 'bad' && view.retry !== false ? '<button type="button" class="btn secondary" id="retry-review">Повторить разбор</button>' : ''}
  </div>`;
}

function adviceMeter(advice) {
  const flow = state.flow;
  if (flow.advicePending && (!advice || advice.id === flow.adviceBaseline)) return { pct: 0, label: 'Рекомендации в очереди', kind: 'busy' };
  flow.advicePending = false;
  if (!advice) return { pct: 0, label: 'Появятся по кнопке «Сгенерировать» у ТЗ', kind: '' };
  if (advice.status === 'QUEUED') return { pct: 0, label: 'Рекомендации в очереди', kind: 'busy' };
  if (advice.status === 'RUNNING' || advice.status === 'RETRYING') {
    const pct = Math.max(0, Math.min(99, Number(advice.progress) || 0));
    return { pct, label: 'Модель пишет рекомендации', kind: 'busy' };
  }
  if (advice.status === 'SUCCEEDED') return { pct: 100, label: 'Рекомендации готовы', kind: '' };
  return { pct: 100, label: 'Рекомендации не получены', kind: 'bad' };
}

function materialsParts(bundle) {
  const reviews = bundle?.materialsReviews || [];
  const latest = reviews[reviews.length - 1];
  const improvements = bundle?.improvements || [];
  const advice = improvements[improvements.length - 1];
  const review = analysisView(latest);
  const rec = adviceMeter(advice);
  const items = (advice?.output?.items || []).map((item) => `<div class="comment"><strong>${esc(item.title)}</strong><p>${esc(item.text)}</p></div>`).join('');
  const adviceHtml = !advice
    ? ''
    : `<section class="card"><h3>Рекомендации</h3>${advice.error ? flash(advice.error, 'warn') : ''}<p>${esc(advice.output?.summary || (advice.status === 'SUCCEEDED' ? '' : 'Модель готовит рекомендации.'))}</p>${items}</section>`;
  return {
    view: review,
    adviceHtml: scaleMarkup('Рекомендации', rec.pct, rec.label, rec.kind) + adviceHtml,
  };
}

const AI_LIVE = {
  tests: {
    host: 'ai-live-tests',
    queued: 'Тесты в очереди',
    early: 'Читаем проект',
    mid: 'Модель предлагает тесты',
    late: 'Собираем текст тестов',
    failed: 'Тесты не собрались',
  },
  process: {
    host: 'ai-live-process',
    queued: 'Ревью в очереди',
    early: 'Читаем телеметрию',
    mid: 'Модель пишет ревью',
    late: 'Собираем текст ревью',
    failed: 'Ревью не собралось',
  },
};

function latestAi(list) {
  return list && list.length ? list[list.length - 1] : null;
}

function aiPhase(list) {
  const item = latestAi(list);
  if (!item) return '';
  const moving = item.status === 'QUEUED' || item.status === 'RUNNING' || item.status === 'RETRYING';
  return moving ? `${item.id}:busy` : `${item.id}:${item.status}`;
}

function liveJobView(item, key) {
  const copy = AI_LIVE[key];
  const pending = state.flow.aiPending[key] && (!item || item.id === state.flow.aiBaseline[key]);
  if (pending) return { pct: 0, label: copy.queued, kind: 'busy', summary: '', retry: false };
  if (!item || item.status === 'SUCCEEDED') return null;
  if (item.status === 'QUEUED') return { pct: 0, label: copy.queued, kind: 'busy', summary: '', retry: false };
  if (item.status === 'RUNNING' || item.status === 'RETRYING') {
    const pct = Math.max(0, Math.min(99, Number(item.progress) || 0));
    const label = pct >= 80 ? copy.late : pct >= 40 ? copy.mid : copy.early;
    return { pct, label, kind: 'busy', summary: '', retry: false };
  }
  return { pct: 100, label: copy.failed, kind: 'bad', summary: modelError(item.error, 'Повторить'), retry: false };
}

function settleAiPending(bundle) {
  const tests = latestAi(bundle?.taskSuggestions);
  const process = latestAi(bundle?.processReviews);
  if (state.flow.aiPending.tests && tests && tests.id !== state.flow.aiBaseline.tests) state.flow.aiPending.tests = false;
  if (state.flow.aiPending.process && process && process.id !== state.flow.aiBaseline.process) state.flow.aiPending.process = false;
}

function paintAiLive(bundle) {
  settleAiPending(bundle);
  for (const key of ['tests', 'process']) {
    const el = document.getElementById(AI_LIVE[key].host);
    if (!el) continue;
    const item = latestAi(key === 'tests' ? bundle?.taskSuggestions : bundle?.processReviews);
    const view = liveJobView(item, key);
    if (!view) {
      if (el.innerHTML) {
        el.innerHTML = '';
        delete el.dataset.sig;
      }
      continue;
    }
    paintAnalysis(el, view);
  }
}

async function refreshAiLive() {
  if (state.tab !== 'ai' || !state.practice || state.flow.aiRefreshing) return;
  try {
    const bundle = await api('GET', `/v1/practices/${state.practice.id}/ai`);
    if (aiPhase(state.aiBundle?.taskSuggestions) !== aiPhase(bundle.taskSuggestions) || aiPhase(state.aiBundle?.processReviews) !== aiPhase(bundle.processReviews) || aiPhase(state.aiBundle?.analyses) !== aiPhase(bundle.analyses)) {
      state.aiBundle = bundle;
      state.flow.aiRefreshing = true;
      try {
        await renderDetail();
      } finally {
        state.flow.aiRefreshing = false;
      }
      return;
    }
    state.aiBundle = bundle;
    paintAiLive(bundle);
  } catch (e) {
    const el = $('#ai-msg');
    if (el) el.innerHTML = flash(e.message, 'error');
  }
}

function paintAnalysis(el, view) {
  const sig = JSON.stringify([view.pct, view.kind, view.label, view.summary]);
  if (el.dataset.sig === sig) return;
  const card = el.querySelector('.analysis');
  const summary = card?.querySelector('.analysis-summary');
  if (!card || Boolean(summary) !== Boolean(view.summary) || view.kind === 'bad') {
    el.innerHTML = analysisCard(view);
    el.dataset.sig = sig;
    const retry = el.querySelector('#retry-review');
    if (retry) retry.addEventListener('click', () => { void retryReview(); });
    return;
  }
  card.className = view.kind ? `analysis ${view.kind}` : 'analysis';
  const num = card.querySelector('.analysis-num');
  if (num) num.innerHTML = `${view.pct}<small>%</small>`;
  const meter = card.querySelector('.meter');
  if (meter) {
    meter.className = view.kind ? `meter ${view.kind}` : 'meter';
    const bar = meter.querySelector('span');
    if (bar) bar.style.width = `${view.pct}%`;
  }
  const label = card.querySelector('.analysis-label');
  if (label) label.textContent = view.label;
  if (summary) summary.textContent = view.summary;
  el.dataset.sig = sig;
}

function briefFileHtml(p) {
  if (!p?.briefFilename) return '';
  return `<div class="file-chip"><span class="muted">Загруженный файл</span><strong>${esc(p.briefFilename)}</strong></div>`;
}

function recommendationBlock(advice) {
  const items = (advice?.output?.items || []).map((item) => `- ${item.title}. ${item.text}`).join('\n');
  const summary = advice?.output?.summary ? `${advice.output.summary}\n\n` : '';
  return `## Что доделать и улучшить\n\n${summary}${items}`.trim();
}

function mergeBrief(current, block) {
  const marker = '## Что доделать и улучшить';
  const at = current.indexOf(marker);
  const base = (at >= 0 ? current.slice(0, at) : current).trim();
  return base ? `${base}\n\n${block}` : block;
}

function syncGenerateButtons() {
  const description = $('#generate-description');
  const brief = $('#generate-brief');
  if (description) {
    description.disabled = !!state.flow.fillDescriptionId;
    description.textContent = state.flow.fillDescriptionId ? 'Генерируем…' : 'Сгенерировать';
  }
  if (brief) {
    brief.disabled = !!state.flow.fillBriefId;
    brief.textContent = state.flow.fillBriefId ? 'Генерируем…' : 'Сгенерировать';
  }
}

function paintMaterials() {
  const analysis = $('#analysis-status');
  const advice = $('#advice-status');
  if ((!analysis && !advice) || state.tab !== 'overview') return;
  const parts = materialsParts(state.aiBundle);
  if (analysis) paintAnalysis(analysis, parts.view);
  if (advice && advice.dataset.paint !== parts.adviceHtml) {
    advice.innerHTML = parts.adviceHtml;
    advice.dataset.paint = parts.adviceHtml;
  }
  syncGenerateButtons();
}

async function refreshMaterials() {
  const analysis = $('#analysis-status');
  if (!analysis || !state.practice || state.tab !== 'overview') return;
  try {
    state.aiBundle = await api('GET', `/v1/practices/${state.practice.id}/ai`);
    const reviews = state.aiBundle.materialsReviews || [];
    const latest = reviews[reviews.length - 1];
    if (latest?.status === 'SUCCEEDED' && latest.output?.description) state.suggestedDescription = latest.output.description;
    paintMaterials();
    await applyPendingGeneration();
  } catch (e) {
    analysis.innerHTML = flash(e.message, 'error');
  }
}

async function retryReview() {
  try {
    markReviewPending();
    paintMaterials();
    await api('POST', `/v1/practices/${state.practice.id}/materials-review`, {});
    materialsMessage('Разбор запущен снова.', 'ok');
    void refreshMaterials();
  } catch (err) {
    state.flow.reviewPending = false;
    paintMaterials();
    materialsMessage(err.message, 'error');
  }
}

async function saveMaterials() {
  try {
    const title = $('#m-title').value.trim();
    const description = $('#m-description').value;
    const brief = $('#m-brief').value;
    materialsMessage('Сохраняем…', '');
    state.practice = await api('POST', `/v1/practices/${state.practice.id}/materials`, { title, description });
    if (brief.trim() && brief !== (state.practice.brief || '')) {
      markReviewPending();
      await api('POST', `/v1/practices/${state.practice.id}/brief`, { text: brief });
      state.practice = await api('GET', `/v1/practices/${state.practice.id}`);
      materialsMessage('Сохранено. Модель снова разбирает ТЗ.', 'ok');
      paintMaterials();
    } else materialsMessage('Сохранено.', 'ok');
    const titleEl = document.querySelector('#app h1');
    if (titleEl) titleEl.innerHTML = `${esc(state.practice.title)} ${badge(state.practice.status)}`;
    void refreshProject();
    void refreshMaterials();
  } catch (err) {
    materialsMessage(err.message, 'error');
  }
}

async function applyGeneratedDescription(text) {
  const field = $('#m-description');
  if (field) field.value = text;
  state.suggestedDescription = text;
  state.practice = await api('POST', `/v1/practices/${state.practice.id}/materials`, { description: text });
  materialsMessage('Описание для кандидата сгенерировано. Его можно поправить и сохранить.', 'ok');
}

async function applyGeneratedBrief(advice) {
  const block = recommendationBlock(advice);
  const field = $('#m-brief');
  const current = field?.value ?? state.practice.brief ?? '';
  const next = mergeBrief(current, block);
  if (field) field.value = next;
  await api('POST', `/v1/practices/${state.practice.id}/brief`, { text: next, review: false });
  state.practice = { ...state.practice, brief: next };
  materialsMessage('В ТЗ добавлено, что доделать и улучшить. Текст можно поправить и сохранить.', 'ok');
}

async function applyPendingGeneration() {
  if (state.flow.applying) return;
  const reviews = state.aiBundle?.materialsReviews || [];
  const improvements = state.aiBundle?.improvements || [];
  const review = state.flow.fillDescriptionId ? reviews.find((item) => item.id === state.flow.fillDescriptionId) : null;
  const advice = state.flow.fillBriefId ? improvements.find((item) => item.id === state.flow.fillBriefId) : null;
  if (review?.status === 'FAILED') {
    state.flow.fillDescriptionId = '';
    syncGenerateButtons();
    materialsMessage(review.error || 'Не удалось сгенерировать описание', 'error');
  }
  if (advice?.status === 'FAILED') {
    state.flow.fillBriefId = '';
    syncGenerateButtons();
    materialsMessage(advice.error || 'Не удалось дополнить ТЗ', 'error');
  }
  const description = review?.status === 'SUCCEEDED' ? review.output?.description : '';
  const briefReady = advice?.status === 'SUCCEEDED' && (advice.output?.items || []).length;
  if (!description && !briefReady) return;
  state.flow.applying = true;
  try {
    if (description) {
      state.flow.fillDescriptionId = '';
      await applyGeneratedDescription(description);
    }
    if (briefReady) {
      state.flow.fillBriefId = '';
      await applyGeneratedBrief(advice);
    }
  } catch (err) {
    materialsMessage(err.message, 'error');
  } finally {
    state.flow.applying = false;
    syncGenerateButtons();
  }
}

async function generateDescription() {
  try {
    const latest = (state.aiBundle?.materialsReviews || []).at(-1);
    const current = $('#m-description')?.value || '';
    if (latest?.status === 'SUCCEEDED' && latest.output?.description && current.trim() !== latest.output.description.trim()) {
      await applyGeneratedDescription(latest.output.description);
      return;
    }
    if (latest && ['QUEUED', 'RUNNING', 'RETRYING'].includes(latest.status)) {
      state.flow.fillDescriptionId = latest.id;
      syncGenerateButtons();
      materialsMessage('Описание появится в поле, когда разбор закончится.', 'ok');
      return;
    }
    markReviewPending();
    paintMaterials();
    const queued = await api('POST', `/v1/practices/${state.practice.id}/materials-review`, {});
    state.flow.fillDescriptionId = queued.analysisId;
    syncGenerateButtons();
    materialsMessage('Модель составляет описание для кандидата.', 'ok');
    void refreshMaterials();
  } catch (err) {
    state.flow.fillDescriptionId = '';
    syncGenerateButtons();
    materialsMessage(err.message, 'error');
  }
}

async function generateBrief() {
  try {
    const latest = (state.aiBundle?.improvements || []).at(-1);
    const current = $('#m-brief')?.value || '';
    const block = latest?.status === 'SUCCEEDED' ? recommendationBlock(latest) : '';
    if (block && !current.includes(block)) {
      await applyGeneratedBrief(latest);
      return;
    }
    if (latest && ['QUEUED', 'RUNNING', 'RETRYING'].includes(latest.status)) {
      state.flow.fillBriefId = latest.id;
      syncGenerateButtons();
      materialsMessage('Рекомендации появятся в ТЗ, когда модель закончит.', 'ok');
      return;
    }
    markAdvicePending();
    paintMaterials();
    const queued = await api('POST', `/v1/practices/${state.practice.id}/improvements`, {});
    state.flow.fillBriefId = queued.analysisId;
    syncGenerateButtons();
    materialsMessage('Модель дописывает в ТЗ, что доделать и улучшить.', 'ok');
    void refreshMaterials();
  } catch (err) {
    state.flow.fillBriefId = '';
    state.flow.advicePending = false;
    paintMaterials();
    materialsMessage(err.message, 'error');
  }
}

async function onUploadZip(e) {
  const file = e.target.files?.[0];
  if (!file) return;
  try {
    materialsMessage('Загружаем проект…', '');
    state.flow.upload = 0;
    state.flow.processing = false;
    state.flow.extract = null;
    paintMaterials();
    const uploaded = await apiRaw('POST', `/v1/practices/${state.practice.id}/project`, file, 'application/zip', (loaded, total) => {
      const ratio = total ? loaded / total : 0;
      if (ratio >= 1) {
        state.flow.upload = null;
        state.flow.processing = true;
        if (!state.flow.extractTimer) watchExtract(state.practice.id);
      } else state.flow.upload = ratio;
      paintMaterials();
    });
    stopExtract();
    state.flow.upload = null;
    state.flow.processing = false;
    state.flow.extract = null;
    markReviewPending();
    state.practice = await api('GET', `/v1/practices/${state.practice.id}`);
    materialsMessage(uploaded?.skipped ? `Проект загружен: ${uploaded.files} файлов. Папки зависимостей не копировались. Разбор уже идёт.` : 'Проект загружен. Разбор уже идёт.', 'ok');
    void refreshProject();
    void refreshMaterials();
  } catch (err) {
    stopExtract();
    state.flow.upload = null;
    state.flow.processing = false;
    state.flow.extract = null;
    state.flow.reviewPending = false;
    paintMaterials();
    materialsMessage(err.message, 'error');
  }
  e.target.value = '';
}

async function onUploadBrief(e) {
  const file = e.target.files?.[0];
  if (!file) return;
  try {
    const text = await file.text();
    if ($('#m-brief')) $('#m-brief').value = text;
    markReviewPending();
    paintMaterials();
    await api('POST', `/v1/practices/${state.practice.id}/brief`, { text, name: file.name });
    state.practice = await api('GET', `/v1/practices/${state.practice.id}`);
    const slot = $('#brief-file');
    if (slot) slot.innerHTML = briefFileHtml(state.practice);
    materialsMessage('ТЗ сохранено. DeepSeek разбирает его вместе с проектом.', 'ok');
    void refreshProject();
    void refreshMaterials();
  } catch (err) {
    state.flow.reviewPending = false;
    paintMaterials();
    materialsMessage(err.message, 'error');
  }
  e.target.value = '';
}

async function loadVacancySelect() {
  const practice = state.practice;
  if (!practice || !document.getElementById(`pin-${practice.id}`)) return;
  await loadVacancyCatalog();
  fillPin(practice);
  $$(`#pin-${practice.id} .pin-vacancy`).forEach((input) => input.addEventListener('change', () => { void onPin(practice.id); }));
}

async function loadAttempts(id) {
  const box = $('#attempt-list');
  if (!box) return;
  try {
    const data = await api('GET', `/v1/practices/${id}/attempts`);
    const items = data.items || [];
    if (!items.length) {
      box.innerHTML = '<p class="muted">Пока никто не откликнулся.</p>';
      return;
    }
    box.innerHTML = `<ul class="list">${items.map((a) => `
      <li>
        <div>
          <button type="button" class="linkish open-attempt" data-id="${esc(a.id)}">${esc(a.candidateEmail || 'Кандидат')}</button>
          <div class="muted">${esc(takerStatus(a.status))}</div>
        </div>
        ${badge(a.status)}
      </li>`).join('')}</ul>`;
    $$('.open-attempt').forEach((b) => b.addEventListener('click', () => { void openPractice(b.dataset.id); }));
  } catch (err) {
    box.innerHTML = `<p class="muted">${esc(err.message)}</p>`;
  }
}

async function onComment(e) {
  e.preventDefault();
  try {
    if (!state.latestSubmission) throw new Error('нет submission');
    await api('POST', `/v1/submissions/${state.latestSubmission.id}/comments`, {
      filePath: $('#c-file').value.trim(),
      lineStart: Number($('#c-from').value),
      lineEnd: Number($('#c-to').value),
      body: $('#c-body').value,
    });
    renderDetail();
  } catch (err) {
    $('#review-msg').innerHTML = flash(err.message, 'error');
  }
}

async function onRequirement(e) {
  e.preventDefault();
  try {
    await api('POST', `/v1/practices/${state.practice.id}/requirement-changes`, {
      text: $('#r-text').value.trim(),
      reason: $('#r-reason').value.trim(),
      acceptanceCriteria: $('#r-ac').value.split('\n').map((s) => s.trim()).filter(Boolean),
      dueAt: isoFromLocal($('#r-due').value),
    });
    await openPractice(state.practice.id);
  } catch (err) {
    $('#review-msg').innerHTML = flash(err.message, 'error');
  }
}

async function removePractice(id) {
  const practice = state.practices.find((p) => p.id === id) || state.practice;
  const title = practice?.title || 'эту практику';
  if (!confirm(`Удалить «${title}»? Файлы, приглашение и ход работы исчезнут.`)) return;
  try {
    await api('DELETE', `/v1/practices/${id}`);
    if (state.practice?.id === id) state.practice = null;
    await loadList();
  } catch (err) {
    alert(err.message);
  }
}

async function loadList() {
  stopLive();
  state.panel = null;
  try { state.me = (await api('GET', '/v1/me')).email; } catch { state.me = ''; }
  const page = await api('GET', '/v1/practices?limit=50');
  state.practices = page.items;
  location.hash = '';
  listView();
}

async function openPractice(id) {
  state.panel = null;
  state.practice = await api('GET', `/v1/practices/${id}`);
  location.hash = `practice=${id}`;
  await renderDetail();
}

bindLogout();
(async function boot() {
  const { practice } = hashParams();
  if (!getToken()) return loginView();
  try {
    if (practice) {
      state.tab = 'overview';
      await openPractice(practice);
    } else await loadList();
  } catch (e) {
    if (e.status === 401) loginView('Сессия недействительна');
    else loginView(e.message);
  }
})();
