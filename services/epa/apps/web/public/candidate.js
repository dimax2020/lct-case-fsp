const app = () => document.getElementById('app');
let state = {
  practice: null,
  workspaceId: null,
  files: [],
  path: '',
  content: '',
  dirty: false,
  pasted: 0,
  poll: null,
  installHref: '',
  username: '',
  email: '',
  gitRemote: '',
};

function loginView(err) {
  app().innerHTML = `
    <section class="card" id="login">
      <h1>Вход кандидата</h1>
      <p class="lede">Укажите имя, которое вы ввели по ссылке приглашения. Пароль не нужен.</p>
      ${err ? flash(err, 'error') : ''}
      <form id="login-form">
        <label for="name">Ваше имя</label>
        <input id="name" autocomplete="name" required maxlength="80" placeholder="Иван">
        <button class="btn" type="submit">Войти</button>
      </form>
    </section>`;
  listen('login-form', 'submit', async (e) => {
    e.preventDefault();
    try {
      const session = await api('POST', '/v1/auth/login', { name: $('#name').value.trim(), role: 'candidate' });
      if (session.role !== 'candidate') throw new Error('Это вход работодателя.');
      setToken(session.token, 'candidate');
      state.email = session.email;
      const list = await api('GET', '/v1/practices?limit=1');
      if (!list.items[0]) throw new Error('Практик нет');
      location.hash = `practice=${list.items[0].id}`;
      await resume(list.items[0].id);
    } catch (err) {
      setToken('', '');
      loginView(err.message);
    }
  });
}

async function inviteAccount(token, err) {
  let preview;
  try {
    preview = await api('GET', `/v1/invitations/preview?token=${encodeURIComponent(token)}`);
  } catch (e) {
    return loginView(e.status === 410 ? 'Приглашение уже использовано. Войдите тем же именем.' : e.message);
  }
  app().innerHTML = `
    <section class="card">
      <h1>${esc(preview.title)}</h1>
      <p class="lede">Имя увидит работодатель. Логин и пароль вы введёте в расширении VS Code.</p>
      ${err ? flash(err, 'error') : ''}
      <form id="register-form">
        <label for="name">Ваше имя</label>
        <input id="name" autocomplete="name" required maxlength="80" placeholder="Иван">
        <label for="username">Логин для расширения</label>
        <input id="username" autocomplete="username" required minlength="3" maxlength="40" pattern="[A-Za-z0-9._\\-]+" placeholder="ivan">
        <label for="password">Пароль для расширения</label>
        <input id="password" type="password" autocomplete="new-password" required minlength="8">
        <label for="password2">Пароль ещё раз</label>
        <input id="password2" type="password" autocomplete="new-password" required minlength="8">
        <button class="btn" type="submit">Продолжить</button>
      </form>
    </section>`;
  listen('register-form', 'submit', async (e) => {
    e.preventDefault();
    try {
      const password = $('#password').value;
      if (password !== $('#password2').value) return inviteAccount(token, 'Пароли не совпадают');
      const r = await api('POST', '/v1/auth/register', { token, name: $('#name').value.trim(), username: $('#username').value.trim(), password });
      setToken(r.candidateToken, 'candidate');
      state.email = r.email || preview.email;
      state.username = r.username || $('#username').value.trim();
      state.practiceId = r.practiceId;
      location.hash = `practice=${r.practiceId}`;
      consentView(r.consentNotice);
    } catch (err) {
      inviteAccount(token, err.message);
    }
  });
}

function consentView(notice, err) {
  const events = notice.collectedEvents.map((e) => `<li><strong>${esc(e.type)}</strong> — ${esc(e.description)}</li>`).join('');
  const not = notice.notCollected.map((x) => `<li>${esc(x)}</li>`).join('');
  app().innerHTML = `
    <section class="card notice" id="consent">
      <h1>${esc(notice.title)}</h1>
      <p>${esc(notice.purpose)}</p>
      <p class="muted">${esc(notice.retention)}</p>
      <p class="muted">Кто видит данные: ${esc((notice.visibleTo || []).join(', '))}</p>
      <h2>Что собирается</h2>
      <ul>${events}</ul>
      <h2>Что не собирается</h2>
      <ul>${not}</ul>
      ${err ? flash(err, 'error') : ''}
      <form id="consent-form">
        <label class="agree" for="accepted">
          <input type="checkbox" id="accepted" required>
          <span>Я прочитал(а) уведомление и даю согласие на сбор перечисленной телеметрии workspace.</span>
        </label>
        <button class="btn" type="submit">Принять и начать</button>
      </form>
    </section>`;
  listen('consent-form', 'submit', async (e) => {
    e.preventDefault();
    if (!$('#accepted').checked) return;
    try {
      await api('POST', `/v1/practices/${state.practiceId}/consent`, {
        consentVersion: notice.version,
        textHash: notice.textHash,
        accepted: true,
      });
      await startPractice();
    } catch (err) {
      consentView(notice, err.message);
    }
  });
}

async function startPractice() {
  app().innerHTML = `<section class="card"><h1>Готовим workspace</h1><p>Создаётся изолированное окружение. SSH к хостам платформы не выдаётся.</p><div id="wait-msg"></div></section>`;
  await api('POST', `/v1/practices/${state.practiceId}/start`);
  for (let i = 0; i < 60; i++) {
    const p = await api('GET', `/v1/practices/${state.practiceId}`);
    if (p.status === 'IN_PROGRESS' && p.workspace?.lifecycle === 'READY') {
      state.practice = p;
      state.workspaceId = p.workspaceId || p.workspace?.id;
      location.hash = `practice=${p.id}`;
      return connectView();
    }
    if (p.workspace?.lifecycle === 'FAILED') {
      $('#wait-msg').innerHTML = flash(p.workspace.failureReason || 'provisioning failed', 'error');
      return;
    }
    $('#wait-msg').textContent = `статус ${p.status} · workspace ${p.workspace?.lifecycle || '…'}`;
    await sleep(1000);
  }
  $('#wait-msg').innerHTML = flash('Workspace ещё не готов. Обновите страницу.', 'warn');
}

function linkStatusHtml(s) {
  if (!s || !s.linked) return '<p class="muted">Расширение ещё не открывали.</p>';
  if (s.connected) {
    return `<div class="flash ok">Расширение на связи. Событий: ${esc(s.eventCount)}. Последнее: ${esc(eventLabel(s.lastEventType))} · ${esc(fmt(s.lastEventAt || s.lastSeenAt))}. Работодатель видит это во вкладке «Ход работы».</div>`;
  }
  if (s.endedAt) return '<div class="flash warn">Сессия расширения завершена. В VS Code снова выполните «EPA: Подключить практику».</div>';
  return '<div class="flash warn">Логин принят, сигналов ещё нет. Это отсутствие данных, а не оценка.</div>';
}

async function connectView() {
  const p = state.practice;
  if (!state.email || !state.username) {
    try {
      const me = await api('GET', '/v1/me');
      state.email = state.email || me.email;
      state.username = state.username || me.username || '';
    } catch { /* keep empty */ }
  }
  if (!state.gitRemote) {
    try { state.gitRemote = (await api('GET', `/v1/practices/${state.practiceId}/project`)).remote; } catch { /* repo appears after start */ }
  }
  app().innerHTML = `
    <h1>${esc(p.title)} ${badge(p.status)}</h1>
    <section class="card" id="connect">
      <h2>Как выполнять задание</h2>
      <p>Вы вошли как <strong>${esc(state.email || 'кандидат')}</strong>. Git не спрашивает пароль.</p>
      <ol class="steps">
        <li><strong>Поставьте расширение один раз.</strong> Нажмите «Скачать расширение». В VS Code откройте расширения (<code>Cmd+Shift+X</code>), меню «…» → Install from VSIX… и выберите скачанный файл.</li>
        <li><strong>Заберите проект, если папки ещё нет.</strong> В терминале:
          <pre class="howto">git clone ${esc(state.gitRemote || 'АДРЕС')}
cd ${esc(((state.gitRemote || 'project.git').split('/').pop() || 'project').replace(/\.git$/, ''))}</pre>
          Пароль Git не спросит. Откройте появившуюся папку в VS Code: File → Open Folder.
        </li>
        <li><strong>Если проект уже лежит у вас на диске</strong> и это ещё не git-репозиторий, встаньте в эту папку и выполните:
          <pre class="howto">git init
git add .
git commit -m "начальная версия"
git remote add origin ${esc(state.gitRemote || 'АДРЕС')}
git pull origin main --allow-unrelated-histories
git push -u origin HEAD</pre>
          Если <code>git remote add</code> пишет «not a git repository», вы не в папке проекта или пропустили <code>git init</code>.
        </li>
        <li><strong>Подключите расширение.</strong> Папка задания должна быть открыта в VS Code. Нажмите «Подключить VS Code» — адрес сервера подставится сам. Если окно не открылось: <code>Cmd+Shift+P</code> → <code>EPA: Подключить практику</code>. В первое поле вставьте только <code>${esc(location.origin)}</code>, затем логин <strong>${esc(state.username || 'со страницы')}</strong> и пароль, который задали здесь. Не вставляйте адрес этой страницы, ссылку git и не дописывайте <code>/v1</code>.</li>
        <li><strong>Отправьте изменения на сервер:</strong>
          <pre class="howto">git add .
git commit -m "что сделано"
git push</pre>
        </li>
        <li><strong>Закройте задачу на этой странице.</strong> Сначала сделайте <code>git push</code>. Затем нажмите «Закрыть задачу» ниже. Расширение задачу не закрывает.</li>
      </ol>
      <div class="actions">
        <button class="btn" id="close-task" type="button" ${p.status === 'IN_PROGRESS' ? '' : 'disabled'}>Закрыть задачу</button>
        <button class="btn secondary" id="connect-vscode" type="button">Подключить VS Code</button>
        <a class="btn secondary" href="/extension/epa-vscode.vsix">Скачать расширение</a>
        <button class="btn secondary" id="open-ide" type="button">Браузерный редактор</button>
      </div>
      <div id="close-msg">${p.status === 'IN_PROGRESS' ? '' : flash('Задача уже закрыта. Расширение её снова не откроет.', 'ok')}</div>
      <div id="extension-login"></div>
      <div id="vscode-status"><p class="muted">Проверяем связь…</p></div>
    </section>
    <section class="card" id="candidate-tests"><p class="muted">Тесты от модели…</p></section>
    <section class="card" id="candidate-questions"><p class="muted">Вопросы появятся после сдачи решения.</p></section>
    <section class="card">
      <h2>Файлы задания</h2>
      <div class="repo" id="repo-browser"><p class="muted">Загрузка…</p></div>
    </section>`;
  listen('open-ide', 'click', () => { void ide(); });
  listen('connect-vscode', 'click', () => { void installExtension(); });
  listen('close-task', 'click', closeFromPage);
  renderExtensionLogin();
  void renderRepo($('#repo-browser'), state.practiceId).then((project) => {
    if (project?.remote) state.gitRemote = project.remote;
  });
  await refreshLinkStatus();
  void refreshCandidateAi();
  if (state.poll) clearInterval(state.poll);
  state.poll = setInterval(() => { void refreshLinkStatus(); void refreshCandidateAi(); }, 5000);
}

function formatSpent(ms) {
  const sec = Math.max(0, Math.round(Number(ms) / 1000));
  if (sec < 60) return `${sec} с`;
  const min = sec / 60;
  return min < 10 ? `${min.toFixed(1)} мин` : `${Math.round(min)} мин`;
}

function paintQuestions(root, questions, afterAnswer) {
  if (!root) return;
  const open = (questions || []).filter((q) => !q.answer);
  const ids = open.map((q) => q.id).join(',');
  if (root.dataset.ids !== ids) {
    root.dataset.ids = ids;
    root.innerHTML = `<h2>Вопросы по сданному коду</h2>` + (open.map((q) => `
      <form class="answer" data-id="${esc(q.id)}" data-shown="${esc(q.shownAt || '')}">
        <p>${esc(q.text)}</p>
        <p class="muted">${esc(q.evidence?.file)}:${q.evidence?.lineStart}–${q.evidence?.lineEnd}</p>
        <p class="muted">Время ответа: <span data-timer="${esc(q.id)}">0 с</span></p>
        <textarea required placeholder="Ответ своими словами"></textarea>
        <button class="btn" type="submit">Ответить</button>
      </form>`).join('') || '<p class="muted">Вопросы появятся после сдачи: модель задаст их по загруженному коду.</p>');
    root.querySelectorAll('form.answer').forEach((f) => f.addEventListener('submit', async (e) => {
      e.preventDefault();
      f.querySelector('button').disabled = true;
      await api('POST', `/v1/interview/questions/${f.dataset.id}/answers`, { text: f.querySelector('textarea').value });
      root.dataset.ids = '';
      afterAnswer();
    }));
  }
  root.querySelectorAll('form.answer').forEach((f) => {
    const shown = Date.parse(f.dataset.shown);
    const el = f.querySelector('[data-timer]');
    if (el && Number.isFinite(shown)) el.textContent = formatSpent(Date.now() - shown);
  });
}

async function refreshCandidateAi() {
  const tests = $('#candidate-tests');
  const questions = $('#candidate-questions');
  if (!tests && !questions) return;
  try {
    const ai = await api('GET', `/v1/practices/${state.practiceId}/ai`);
    if (tests) {
      const cards = (ai.taskSuggestions || []).flatMap((a) => a.tests || []).map((t) => `
        <div class="comment"><strong>${esc(t.title)}</strong><p>${esc(t.goal)}</p><p class="muted">${esc(t.scenario)}</p></div>`).join('');
      tests.innerHTML = `<h2>Что стоит покрыть тестами</h2>${cards || '<p class="muted">Модель ещё не предложила тесты по проекту работодателя.</p>'}`;
    }
    if (questions) paintQuestions(questions, ai.questions || [], () => { void refreshCandidateAi(); });
  } catch {
    /* the page still works without the model */
  }
}

function renderExtensionLogin() {
  const el = $('#extension-login');
  if (!el) return;
  if (state.username) {
    el.innerHTML = `<p>Адрес сервера: <code>${esc(location.origin)}</code>. Логин: <strong>${esc(state.username)}</strong>. Пароль — тот, который вы задали. Если VS Code пишет «route not found», в адресе остался путь страницы: нужен только адрес выше, без <code>/candidate.html</code> и без <code>/v1</code>.</p>`;
    return;
  }
  el.innerHTML = `
    <p>Для уже начатой практики задайте логин и пароль. Их нужно ввести в расширении.</p>
    <form id="cred-form">
      <label for="username">Логин</label>
      <input id="username" required minlength="3" maxlength="40" pattern="[A-Za-z0-9._\\-]+" placeholder="ivan">
      <label for="password">Пароль</label>
      <input id="password" type="password" required minlength="8">
      <button class="btn" type="submit">Сохранить для расширения</button>
    </form>
    <div id="cred-msg"></div>`;
  listen('cred-form', 'submit', async (e) => {
    e.preventDefault();
    try {
      const saved = await api('POST', '/v1/auth/extension-credentials', { username: $('#username').value.trim(), password: $('#password').value });
      state.username = saved.username;
      renderExtensionLogin();
      const step = document.querySelector('#connect .steps li:nth-child(4)');
      if (step) step.innerHTML = `<strong>Подключите расширение.</strong> Логин <strong>${esc(state.username)}</strong> и ваш пароль. В VS Code: <code>Cmd+Shift+P</code> → <code>EPA: Подключить практику</code>.`;
    } catch (err) {
      const msg = $('#cred-msg');
      if (msg) msg.innerHTML = flash(err.message, 'error');
    }
  });
}

async function installExtension() {
  const status = $('#vscode-status');
  try {
    if (!state.installHref) {
      const r = await api('POST', `/v1/practices/${state.practiceId}/vscode-link`);
      state.installHref = `vscode://epa.epa-vscode/connect?token=${encodeURIComponent(r.token)}&api=${encodeURIComponent(location.origin)}`;
    }
    location.href = state.installHref;
  } catch (e) {
    if (status) status.innerHTML = flash(e.message, 'error');
  }
}

async function refreshLinkStatus() {
  const el = $('#vscode-status');
  if (!el || !state.practiceId) return;
  try {
    el.innerHTML = linkStatusHtml(await api('GET', `/v1/practices/${state.practiceId}/vscode`));
  } catch (e) {
    el.innerHTML = flash(e.message, 'error');
  }
}

async function ide() {
  if (state.workspaceId) {
    try {
      await refreshFiles();
    } catch {
      /* keep last tree */
    }
  }
  const p = state.practice;
  const tree = state.files.map((f) =>
    `<button type="button" data-path="${esc(f.path)}" class="${f.path === state.path ? 'on' : ''}">${esc(f.path)}</button>`).join('');
  app().innerHTML = `
    <h1>${esc(p.title)} ${badge(p.status)}</h1>
    <p class="muted">Запасной редактор в браузере. SSH нет. Телеметрия только этой папки.</p>
    <div id="banners"></div>
    <div class="actions">
      <button class="btn" id="save" ${p.status === 'IN_PROGRESS' ? '' : 'disabled'}>Сохранить</button>
      <button class="btn secondary" id="tests" ${p.status === 'IN_PROGRESS' ? '' : 'disabled'}>Тесты</button>
      <input id="commit-msg" placeholder="сообщение коммита" ${p.status === 'IN_PROGRESS' ? '' : 'disabled'}>
      <button class="btn secondary" id="commit" ${p.status === 'IN_PROGRESS' ? '' : 'disabled'}>Коммит</button>
      <button class="btn" id="submit" ${p.status === 'IN_PROGRESS' ? '' : 'disabled'}>Закрыть задачу</button>
      <button class="btn secondary" id="reload">Обновить</button>
    </div>
    <div class="row">
      <div>
        <label for="new-path">Новый файл</label>
        <input id="new-path" placeholder="src/auth/new.js">
      </div>
      <div>
        <label for="cmd">Команда из разрешённого списка</label>
        <input id="cmd" placeholder="ls src/auth">
      </div>
    </div>
    <div class="actions">
      <button class="btn secondary" id="create-file">Создать</button>
      <button class="btn secondary" id="run-cmd">Выполнить</button>
    </div>
    <div class="ide">
      <div class="tree" id="tree">${tree}</div>
      <div class="editor-wrap">
        <div class="editor-bar"><span id="cur">${esc(state.path || 'файл не выбран')}</span><span class="muted" id="dirty">${state.dirty ? 'изменено' : ''}</span></div>
        <textarea class="editor" id="editor" ${p.status === 'IN_PROGRESS' ? '' : 'readonly'}>${esc(state.content)}</textarea>
      </div>
      <pre class="term" id="term">Готово. Разрешены node/npm test, ls, cat, git status/log/diff и другие команды из политики workspace.</pre>
    </div>
    <div class="split">
      <section class="card" id="comments-box"><h2>Комментарии проверки</h2></section>
      <section class="card" id="defense-box"><h2>Защита кода</h2></section>
    </div>
    <section class="card" id="req-box"><h2>Изменение требования</h2></section>`;
  $$('#tree button').forEach((b) => b.addEventListener('click', () => openFile(b.dataset.path)));
  const editor = $('#editor');
  editor.addEventListener('input', () => { state.dirty = true; state.content = editor.value; $('#dirty').textContent = 'изменено'; });
  editor.addEventListener('paste', (e) => {
    const t = e.clipboardData?.getData('text') || '';
    state.pasted += t.length;
  });
  listen('save', 'click', saveFile);
  listen('tests', 'click', runTests);
  listen('commit', 'click', commit);
  listen('submit', 'click', submit);
  listen('reload', 'click', () => { void ide(); });
  listen('create-file', 'click', () => {
    const path = $('#new-path').value.trim();
    if (!path) return;
    state.path = path;
    state.content = '';
    state.dirty = true;
    void ide();
  });
  listen('run-cmd', 'click', runCmd);
  loadSidePanels();
  startPoll();
}

function term(text) {
  const el = $('#term');
  if (el) el.textContent = text;
}

async function refreshFiles() {
  const { items } = await api('GET', `/v1/workspaces/${state.workspaceId}/files`);
  state.files = items.filter((f) => f.type === 'file');
}

async function openFile(path) {
  const f = await api('GET', `/v1/workspaces/${state.workspaceId}/file?path=${encodeURIComponent(path)}`);
  state.path = f.path;
  state.content = f.content;
  state.dirty = false;
  state.pasted = 0;
  await ide();
}

async function saveFile() {
  if (!state.path) return;
  try {
    const r = await api('PUT', `/v1/workspaces/${state.workspaceId}/file`, {
      path: state.path,
      content: $('#editor').value,
      editorStats: { pastedChars: state.pasted },
    });
    state.dirty = false;
    state.pasted = 0;
    await refreshFiles();
    const signal = r.largeInsertionSignal;
    await ide();
    term(`Сохранено ${r.path} (${r.bytes} байт)`);
    if (signal) {
      $('#banners').innerHTML = flash(
        `Сигнал крупной вставки в ${signal.file || r.path}. Это повод для дополнительной проверки, а не доказательство нарушения.`,
        'signal',
      );
    }
  } catch (e) {
    term(e.message);
  }
}

async function runTests() {
  term('Запуск тестов в workspace…');
  try {
    const r = await api('POST', `/v1/workspaces/${state.workspaceId}/tests`);
    term(`тесты ${r.status}: успешно ${r.passed}, с ошибкой ${r.failed}\n${r.log || ''}`);
  } catch (e) {
    term(e.message);
  }
}

async function runCmd() {
  const command = $('#cmd').value.trim();
  if (!command) return;
  try {
    const r = await api('POST', `/v1/workspaces/${state.workspaceId}/commands`, { command });
    term(`$ ${command}\nexit ${r.exitCode}\n${r.output || ''}`);
  } catch (e) {
    term(e.message);
  }
}

async function commit() {
  const message = ($('#commit-msg')?.value || '').trim();
  if (!message) {
    term('Нужно сообщение коммита.');
    return;
  }
  try {
    const r = await api('POST', `/v1/workspaces/${state.workspaceId}/commits`, { message });
    term(`commit ${r.sha}\n${(r.changedFiles || []).join('\n')}`);
  } catch (e) {
    term(e.message);
  }
}

async function submitSolution() {
  return api('POST', `/v1/practices/${state.practiceId}/submissions`, undefined, { 'idempotency-key': crypto.randomUUID() });
}

async function closeFromPage() {
  const msg = $('#close-msg');
  try {
    if (msg) msg.innerHTML = flash('Закрываем задачу…', '');
    const r = await submitSolution();
    state.practice = await api('GET', `/v1/practices/${state.practiceId}`);
    await connectView();
    const done = $('#close-msg');
    if (done) done.innerHTML = flash(`Задача закрыта, версия ${r.submission.version}. Проверка идёт.`, 'ok');
  } catch (e) {
    if (msg) msg.innerHTML = flash(e.message, 'error');
  }
}

async function submit() {
  try {
    const r = await submitSolution();
    term(`Задача закрыта, версия ${r.submission.version}. Проверка в отдельном sandbox: ${r.testRunId}`);
    state.practice = await api('GET', `/v1/practices/${state.practiceId}`);
    await ide();
  } catch (e) {
    term(e.message);
  }
}

async function loadSidePanels() {
  const id = state.practiceId;
  try {
    const comments = await api('GET', `/v1/practices/${id}/comments`);
    $('#comments-box').innerHTML = `<h2>Review</h2>` + ((comments.items || []).map((c) => `
      <div class="comment">
        <div class="muted">${esc(c.filePath)}:${c.lineStart}–${c.lineEnd} · ${esc(c.status)}</div>
        <div>${c.bodyHtml}</div>
      </div>`).join('') || '<p class="muted">Замечаний пока нет.</p>');
  } catch {
    /* not in a status that exposes comments */
  }
  try {
    const ai = await api('GET', `/v1/practices/${id}/ai`);
    paintQuestions($('#defense-box'), ai.questions || [], () => { void loadSidePanels(); });
  } catch { /* ignore */ }
  try {
    const ch = await api('GET', `/v1/practices/${id}/requirement-changes`);
    const pending = (ch.items || []).filter((c) => !c.revised_submission_id);
    $('#req-box').innerHTML = `<h2>Изменение требования</h2>` + (pending.length
      ? pending.map((c) => `<p>${esc(c.text)}</p><p class="muted">критерии: ${esc((c.acceptance_criteria || []).join('; '))} · до ${esc(fmt(c.due_at))}</p>`).join('')
      : '<p class="muted">Новых требований нет.</p>');
  } catch { /* ignore */ }
}

function startPoll() {
  if (state.poll) clearInterval(state.poll);
  state.poll = setInterval(async () => {
    try {
      const p = await api('GET', `/v1/practices/${state.practiceId}`);
      if (p.status !== state.practice.status) {
        state.practice = p;
        await ide();
      }
    } catch {
      /* keep last view */
    }
  }, 8000);
}

async function resume(practiceId) {
  state.practiceId = practiceId;
  const p = await api('GET', `/v1/practices/${practiceId}`);
  state.practice = p;
  if (p.status === 'INVITED') {
    const notice = await api('GET', `/v1/practices/${practiceId}/consent-notice`);
    return consentView(notice);
  }
  if (p.status === 'STARTED' || (p.workspace && p.workspace.lifecycle !== 'READY' && p.workspace.lifecycle !== 'DESTROYED')) {
    return startPractice();
  }
  state.workspaceId = p.workspaceId || p.workspace?.id;
  if (!state.workspaceId) throw new Error('workspace ещё не создан');
  return connectView();
}

bindLogout();
(async function boot() {
  const h = hashParams();
  try {
    if (h.invite) return inviteAccount(h.invite);
    if (h.practice && getToken()) return resume(h.practice);
    if (getToken()) {
      const list = await api('GET', '/v1/practices?limit=1');
      if (list.items[0]) return resume(list.items[0].id);
    }
    loginView();
  } catch (e) {
    if (e.status === 401) {
      setToken('', '');
      loginView('Нужно войти снова');
    } else loginView(e.message);
  }
})();
