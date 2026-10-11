import { mkdir } from 'node:fs/promises';
import path from 'node:path';
import * as vscode from 'vscode';
import {
  LARGE_INSERTION_THRESHOLD,
  PASTE_MIN_UNMARKED_CHARS,
  pasteOrigin,
  SNAPSHOT_MAX_FILE_BYTES,
  SNAPSHOT_MAX_FILES,
  SNAPSHOT_MAX_TOTAL_BYTES,
  classifyCommand,
  clipLog,
  computeEditStats,
  isInsideRoot,
  looksBinary,
  parseTestCounts,
  redactCommand,
  sha256Hex,
  testStatus,
  workspaceRelative,
} from './logic.js';
import { EventOutbox, postJson, type TransportResult } from './outbox.js';

interface SavedLink {
  apiUrl: string;
  sessionId: string;
}

const TOKEN_KEY = 'epa.agentToken';
const LINK_KEY = 'epa.link';

function serverOrigin(raw: string): string {
  const trimmed = raw.trim();
  const withScheme = /^https?:\/\//i.test(trimmed) ? trimmed : `http://${trimmed}`;
  try {
    return new URL(withScheme).origin;
  } catch {
    return trimmed.replace(/\/$/, '');
  }
}

function connectFailure(status: number, body: { error?: { message?: string } } | undefined): string {
  if (status === 404) {
    return 'Сервер не нашёл запрос расширения. В адресе укажите только начало ссылки со страницы кандидата, например http://127.0.0.1:8080 — без candidate.html, без /git/ и без /v1. Затем снова выполните «EPA: Подключить практику».';
  }
  return body?.error?.message ?? `Не удалось подключиться (${status}).`;
}

let active: PracticeMonitor | undefined;

export async function activate(context: vscode.ExtensionContext): Promise<void> {
  active = new PracticeMonitor(context);
  context.subscriptions.push(active);
  context.subscriptions.push(
    vscode.commands.registerCommand('epa.connect', () => active?.connect()),
    vscode.commands.registerCommand('epa.disconnect', () => active?.disconnect()),
    vscode.commands.registerCommand('epa.about', () => active?.about()),
    vscode.commands.registerCommand('epa.copy', () => active?.trackClipboard(false)),
    vscode.commands.registerCommand('epa.cut', () => active?.trackClipboard(true)),
    vscode.commands.registerCommand('epa.paste', () => active?.armPaste()),
    vscode.window.registerUriHandler({ handleUri: (uri) => void active?.connectFromUri(uri) }),
  );
  await active.resume();
}

export async function deactivate(): Promise<void> {
  await active?.flush();
}

class PracticeMonitor implements vscode.Disposable {
  private outbox: EventOutbox | null = null;
  private token = '';
  private apiUrl = '';
  private sessionId = '';
  private folder: vscode.WorkspaceFolder | undefined;
  private baselines = new Map<string, string>();
  private pendingEdits = new Map<string, { largest: number; inserted: number; deleted: number; timer: NodeJS.Timeout }>();
  private executions = new Map<unknown, { command: string; started: number; log: string }>();
  private gitHeads = new Map<string, string>();
  private heartbeat: NodeJS.Timeout | null = null;
  private snapshotTimer: NodeJS.Timeout | null = null;
  private dirtySinceSnapshot = false;
  private pasteArmed = false;
  private copiedHashes = new Set<string>();
  private subscriptions: vscode.Disposable[] = [];
  private status: vscode.StatusBarItem;

  constructor(private readonly context: vscode.ExtensionContext) {
    this.status = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 100);
    this.status.command = 'epa.connect';
    this.setStatus('EPA: не подключено', 'Откройте папку задания и перейдите по своей ссылке со страницы кандидата. Подробности: «EPA: Что собирается и чего нет».');
    this.status.show();
  }

  private setStatus(text: string, tooltip: string): void {
    this.status.text = text;
    this.status.tooltip = tooltip;
  }

  private practiceFolder(): vscode.WorkspaceFolder | undefined {
    return vscode.workspace.workspaceFolders?.[0];
  }

  async resume(): Promise<void> {
    const link = this.context.globalState.get<SavedLink>(LINK_KEY);
    const token = await this.context.secrets.get(TOKEN_KEY);
    if (!link || !token) return;
    const folder = this.practiceFolder();
    if (!folder) {
      this.setStatus('EPA: откройте папку', 'Откройте папку задания и выполните «EPA: Подключить практику» ещё раз');
      return;
    }
    await this.start(link.apiUrl, token, link.sessionId, folder, false);
  }

  async connect(): Promise<void> {
    const folder = this.practiceFolder();
    if (!folder) {
      void vscode.window.showErrorMessage('Откройте папку задания в VS Code. Расширение смотрит только её.');
      return;
    }
    const configured = vscode.workspace.getConfiguration('epa').get<string>('apiUrl') || 'http://127.0.0.1:8080';
    const apiUrl = await vscode.window.showInputBox({
      title: 'EPA',
      prompt: 'Адрес сервера со страницы кандидата. Только начало, например http://127.0.0.1:8080',
      placeHolder: 'http://127.0.0.1:8080',
      value: serverOrigin(configured),
      ignoreFocusOut: true,
    });
    if (!apiUrl) return;
    const username = await vscode.window.showInputBox({
      title: 'EPA',
      prompt: 'Логин, который вы задали на странице кандидата',
      ignoreFocusOut: true,
      value: this.context.globalState.get<string>('epa.username') ?? '',
    });
    if (!username) return;
    const password = await vscode.window.showInputBox({
      title: 'EPA',
      prompt: 'Пароль, который вы задали на странице кандидата',
      password: true,
      ignoreFocusOut: true,
    });
    if (!password) return;
    const base = serverOrigin(apiUrl);
    let login: { status: number; body: any };
    try {
      const res = await fetch(`${base}/v1/agent/login`, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ username: username.trim(), password }),
        signal: AbortSignal.timeout(15_000),
      });
      login = { status: res.status, body: await res.json().catch(() => ({})) };
    } catch (e) {
      void vscode.window.showErrorMessage(e instanceof Error ? e.message : String(e));
      return;
    }
    if (login.status === 401) {
      void vscode.window.showErrorMessage('Неверный логин или пароль.');
      return;
    }
    if (login.status !== 200 || typeof login.body?.token !== 'string') {
      void vscode.window.showErrorMessage(connectFailure(login.status, login.body));
      return;
    }
    await this.context.globalState.update('epa.username', username.trim());
    await this.pair(base, login.body.token, folder);
  }

  async connectFromUri(uri: vscode.Uri): Promise<void> {
    const q = new URLSearchParams(uri.query);
    const token = q.get('token')?.trim();
    const apiUrl = q.get('api') ? serverOrigin(q.get('api')!) : '';
    if (!token || !apiUrl) return;
    const folder = this.practiceFolder();
    if (!folder) {
      void vscode.window.showErrorMessage('Сначала откройте папку задания, затем снова перейдите по ссылке EPA.');
      return;
    }
    const ok = await vscode.window.showWarningMessage(
      `Подключить практику и отправлять ход работы только из папки «${folder.name}»? Клавиши, экран и другие папки не собираются.`,
      { modal: true },
      'Подключить',
    );
    if (ok !== 'Подключить') return;
    await this.pair(apiUrl, token, folder);
  }

  private async pair(apiUrl: string, token: string, folder: vscode.WorkspaceFolder): Promise<void> {
    let beat: { status: number; body: any };
    try {
      beat = await postJson(`${apiUrl}/v1/agent/heartbeat`, token, {});
    } catch (e) {
      void vscode.window.showErrorMessage(e instanceof Error ? e.message : String(e));
      return;
    }
    if (beat.status === 401) {
      void vscode.window.showErrorMessage('Код недействителен. На странице кандидата выдайте новый.');
      return;
    }
    if (beat.status !== 200) {
      void vscode.window.showErrorMessage(connectFailure(beat.status, beat.body));
      return;
    }
    const sessionId = String(beat.body.sessionId ?? '');
    if (!sessionId) {
      void vscode.window.showErrorMessage('API не вернул сессию.');
      return;
    }
    await this.context.secrets.store(TOKEN_KEY, token);
    await this.context.globalState.update(LINK_KEY, { apiUrl, sessionId } satisfies SavedLink);
    await vscode.workspace.getConfiguration('epa').update('apiUrl', apiUrl, vscode.ConfigurationTarget.Global);
    await this.start(apiUrl, token, sessionId, folder, true);
    void vscode.window.showInformationMessage(`EPA записывает ход работы папки «${folder.name}». Закрыть задачу можно только кнопкой на странице кандидата.`);
  }

  private async start(apiUrl: string, token: string, sessionId: string, folder: vscode.WorkspaceFolder, announce: boolean): Promise<void> {
    this.stopWatching();
    this.apiUrl = apiUrl;
    this.token = token;
    this.sessionId = sessionId;
    this.folder = folder;
    const dir = path.join(this.context.globalStorageUri.fsPath, 'outbox');
    await mkdir(dir, { recursive: true });
    this.outbox = await EventOutbox.open(dir, sessionId, (batch) => this.sendBatch(batch));
    this.watch();
    this.heartbeat = setInterval(() => void this.beat(), 15_000);
    this.snapshotTimer = setInterval(() => void this.uploadSnapshot('interval'), 120_000);
    this.setStatus('$(record) EPA', `Папка ${folder.name} · сессия ${sessionId}`);
    if (announce) await this.outbox.record('session_started', { client: 'vscode', reason: 'extension_connected' });
    await this.beat();
  }

  private async sendBatch(batch: { sessionId: string; events: unknown[] }): Promise<TransportResult> {
    const res = await postJson(`${this.apiUrl}/v1/agent/events:batch`, this.token, batch);
    if (res.status === 401) {
      this.setStatus('$(error) EPA', 'Код отозван. Выдайте новый на странице кандидата.');
      throw new Error('код отозван');
    }
    if (res.status === 200 || (res.status === 409 && res.body?.gap)) return res.body as TransportResult;
    if (res.status >= 500 || res.status === 429) throw new Error(`сервер недоступен (${res.status})`);
    throw new Error(res.body?.error?.message ?? `отклонено (${res.status})`);
  }

  private async beat(): Promise<void> {
    if (!this.token) return;
    const res = await postJson(`${this.apiUrl}/v1/agent/heartbeat`, this.token, {}).catch(() => null);
    if (!res) {
      this.setStatus('$(sync) EPA', this.outbox?.lastError ?? 'нет сети, события в буфере');
      return;
    }
    if (res.status === 401 || res.status === 409) {
      this.setStatus('$(error) EPA', 'Сессия неактивна. Подключитесь новым кодом.');
      return;
    }
    const pending = this.outbox?.pendingCount ?? 0;
    this.setStatus(pending ? `$(sync) EPA ${pending}` : '$(record) EPA', this.outbox?.lastError ?? `Папка ${this.folder?.name ?? ''}`);
  }

  private watch(): void {
    const folder = this.folder;
    if (!folder) return;
    for (const doc of vscode.workspace.textDocuments) this.remember(doc);
    this.subscriptions.push(
      vscode.workspace.onDidOpenTextDocument((doc) => this.remember(doc)),
      vscode.workspace.onDidChangeTextDocument((e) => this.onChange(e)),
      vscode.workspace.onDidSaveTextDocument((doc) => void this.onSave(doc)),
      vscode.workspace.onDidCreateFiles((e) => void this.onCreate(e)),
      vscode.workspace.onDidDeleteFiles((e) => void this.onDelete(e)),
      vscode.window.onDidStartTerminalShellExecution((e) => this.onShellStart(e)),
      vscode.window.onDidEndTerminalShellExecution((e) => void this.onShellEnd(e)),
    );
    void this.watchGit(folder);
  }

  private rel(uri: vscode.Uri): string | null {
    if (!this.folder || uri.scheme !== 'file') return null;
    return workspaceRelative(this.folder.uri.fsPath, uri.fsPath);
  }

  private remember(doc: vscode.TextDocument): void {
    const rel = this.rel(doc.uri);
    if (!rel || this.baselines.has(rel)) return;
    this.baselines.set(rel, doc.getText());
  }

  private onChange(e: vscode.TextDocumentChangeEvent): void {
    if (e.contentChanges.length === 0) return;
    const rel = this.rel(e.document.uri);
    if (!rel) return;
    let inserted = 0;
    let deleted = 0;
    let largest = 0;
    const pasted: string[] = [];
    const undo = e.reason === vscode.TextDocumentChangeReason.Undo || e.reason === vscode.TextDocumentChangeReason.Redo;
    for (const change of e.contentChanges) {
      inserted += change.text.length;
      deleted += change.rangeLength;
      largest = Math.max(largest, change.text.length);
      if (change.text && (this.pasteArmed || (!undo && change.text.length >= PASTE_MIN_UNMARKED_CHARS))) pasted.push(change.text);
    }
    if (this.pasteArmed) this.pasteArmed = false;
    for (const text of pasted) void this.notePaste(rel, text);
    const prev = this.pendingEdits.get(rel);
    if (prev) clearTimeout(prev.timer);
    const timer = setTimeout(() => void this.flushEdit(rel, e.document), 1200);
    this.pendingEdits.set(rel, {
      largest: Math.max(prev?.largest ?? 0, largest),
      inserted: (prev?.inserted ?? 0) + inserted,
      deleted: (prev?.deleted ?? 0) + deleted,
      timer,
    });
  }

  private async flushEdit(rel: string, doc: vscode.TextDocument): Promise<void> {
    const slot = this.pendingEdits.get(rel);
    this.pendingEdits.delete(rel);
    const after = doc.getText();
    const known = this.baselines.has(rel);
    const before = known ? this.baselines.get(rel)! : '';
    this.baselines.set(rel, after);
    const stats = known
      ? computeEditStats(before, after)
      : {
          insertedChars: slot?.inserted ?? 0,
          deletedChars: slot?.deleted ?? 0,
          insertedLines: 0,
          deletedLines: 0,
        };
    if (stats.insertedChars === 0 && stats.deletedChars === 0) return;
    await this.outbox?.record('file_changed', { path: rel, ...stats, bytesAfter: Buffer.byteLength(after) });
    this.dirtySinceSnapshot = true;
    if ((slot?.largest ?? 0) >= LARGE_INSERTION_THRESHOLD) {
      await this.outbox?.record('large_insertion_signal', {
        file: rel,
        insertedChars: slot!.largest,
        threshold: LARGE_INSERTION_THRESHOLD,
        relatedSequence: null,
        interpretation: 'signal_for_additional_review_not_a_verdict',
      });
    }
  }

  async trackClipboard(cut: boolean): Promise<void> {
    const editor = vscode.window.activeTextEditor;
    const rel = editor ? this.rel(editor.document.uri) : null;
    const text = editor && rel && !editor.selection.isEmpty ? editor.document.getText(editor.selection) : '';
    await vscode.commands.executeCommand(cut ? 'editor.action.clipboardCutAction' : 'editor.action.clipboardCopyAction');
    if (!rel || !text || !this.outbox) return;
    const snippetHash = sha256Hex(text);
    this.copiedHashes.add(snippetHash);
    await this.outbox.record('code_copied', { file: rel, chars: text.length, lines: text.split('\n').length, snippetHash });
  }

  async armPaste(): Promise<void> {
    this.pasteArmed = true;
    try {
      await vscode.commands.executeCommand('editor.action.clipboardPasteAction');
    } finally {
      setTimeout(() => {
        this.pasteArmed = false;
      }, 400);
    }
  }

  private async notePaste(rel: string, text: string): Promise<void> {
    if (!this.outbox || !text) return;
    const snippetHash = sha256Hex(text);
    await this.outbox.record('code_pasted', {
      file: rel,
      chars: text.length,
      lines: text.split('\n').length,
      snippetHash,
      origin: pasteOrigin(snippetHash, this.copiedHashes),
      interpretation: 'signal_for_additional_review_not_a_verdict',
    });
  }

  private async onSave(doc: vscode.TextDocument): Promise<void> {
    const rel = this.rel(doc.uri);
    if (!rel) return;
    const pending = this.pendingEdits.get(rel);
    if (pending) {
      clearTimeout(pending.timer);
      await this.flushEdit(rel, doc);
    }
    const text = doc.getText();
    this.baselines.set(rel, text);
    await this.outbox?.record('file_saved', { path: rel, contentHash: sha256Hex(text), bytes: Buffer.byteLength(text) });
    this.dirtySinceSnapshot = true;
    if (Buffer.byteLength(text) >= 400) void this.uploadSnapshot('significant_save');
  }

  private async onCreate(e: vscode.FileCreateEvent): Promise<void> {
    for (const uri of e.files) {
      const rel = this.rel(uri);
      if (rel) await this.outbox?.record('file_created', { path: rel });
    }
  }

  private async onDelete(e: vscode.FileDeleteEvent): Promise<void> {
    for (const uri of e.files) {
      const rel = this.rel(uri);
      if (!rel) continue;
      this.baselines.delete(rel);
      await this.outbox?.record('file_deleted', { path: rel });
    }
  }

  private onShellStart(e: vscode.TerminalShellExecutionStartEvent): void {
    if (!this.folder || !e.execution.cwd || !isInsideRoot(this.folder.uri.fsPath, e.execution.cwd.fsPath)) return;
    const command = e.execution.commandLine.value;
    const slot = { command, started: Date.now(), log: '' };
    this.executions.set(e.execution, slot);
    void (async () => {
      try {
        for await (const chunk of e.execution.read()) {
          if (slot.log.length >= 20_000) break;
          slot.log += chunk;
        }
      } catch {
        /* stream closed */
      }
    })();
  }

  private async onShellEnd(e: vscode.TerminalShellExecutionEndEvent): Promise<void> {
    const slot = this.executions.get(e.execution);
    this.executions.delete(e.execution);
    if (!slot || !this.folder) return;
    const command = redactCommand(slot.command);
    const durationMs = Math.max(0, Date.now() - slot.started);
    const exitCode = e.exitCode ?? null;
    if (classifyCommand(slot.command) === 'test') {
      const counts = parseTestCounts(slot.log);
      const status = testStatus(exitCode);
      await this.outbox?.record('test_started', { runId: `local-${slot.started}`, command });
      await this.outbox?.record('test_finished', {
        runId: `local-${slot.started}`,
        command,
        status,
        exitCode,
        passed: counts?.passed ?? 0,
        failed: counts?.failed ?? 0,
        durationMs,
        safeLog: clipLog(slot.log || `exit ${exitCode ?? 'unknown'}`),
      });
      return;
    }
    await this.outbox?.record('terminal_command', { command, exitCode, durationMs, timedOut: false });
  }

  private async watchGit(folder: vscode.WorkspaceFolder): Promise<void> {
    const ext = vscode.extensions.getExtension<any>('vscode.git');
    if (!ext) return;
    const api = ext.isActive ? ext.exports.getAPI(1) : (await ext.activate()).getAPI(1);
    const bind = (repo: any) => {
      if (!isInsideRoot(folder.uri.fsPath, repo.rootUri.fsPath)) return;
      const key = repo.rootUri.toString();
      this.gitHeads.set(key, repo.state.HEAD?.commit ?? '');
      this.subscriptions.push(repo.state.onDidChange(() => void this.onGit(repo, key)));
    };
    for (const repo of api.repositories) bind(repo);
    this.subscriptions.push(api.onDidOpenRepository(bind));
  }

  private async onGit(repo: any, key: string): Promise<void> {
    const hash = repo.state.HEAD?.commit as string | undefined;
    const prev = this.gitHeads.get(key) ?? '';
    if (!hash || hash === prev || !/^[a-f0-9]{40}$/.test(hash)) return;
    this.gitHeads.set(key, hash);
    let files: string[] = [];
    try {
      const changes = await repo.diffBetween(prev || `${hash}~1`, hash);
      files = (changes as { uri: vscode.Uri }[])
        .map((c) => this.rel(c.uri))
        .filter((p): p is string => !!p)
        .slice(0, 2000);
    } catch {
      files = [];
    }
    const commit = await repo.getCommit(hash);
    const author = `${commit.authorName ?? ''} ${commit.authorEmail ? `<${commit.authorEmail}>` : ''}`.trim().slice(0, 200);
    await this.outbox?.record('git_commit', {
      sha: hash,
      message: String(commit.message ?? '').slice(0, 2000),
      author: author || 'unknown',
      changedFiles: files,
    });
    void this.uploadSnapshot('git_commit');
  }

  async uploadSnapshot(reason: 'interval' | 'significant_save' | 'pre_submit' | 'git_commit' | 'manual'): Promise<{ snapshotId: string; manifestHash: string; kind: string; baseSnapshotId: string | null; reused: boolean } | null> {
    if (!this.folder || !this.token) return null;
    if (reason === 'interval' && !this.dirtySinceSnapshot) return null;
    const uris = await vscode.workspace.findFiles(
      new vscode.RelativePattern(this.folder, '**/*'),
      '{**/node_modules/**,**/.git/**,**/dist/**,**/out/**,**/.epa/**,**/coverage/**,**/.next/**}',
    );
    const files: { path: string; contentBase64: string }[] = [];
    let total = 0;
    for (const uri of uris) {
      if (files.length >= SNAPSHOT_MAX_FILES) break;
      const rel = this.rel(uri);
      if (!rel) continue;
      let bytes: Uint8Array;
      try {
        bytes = await vscode.workspace.fs.readFile(uri);
      } catch {
        continue;
      }
      if (bytes.byteLength > SNAPSHOT_MAX_FILE_BYTES || looksBinary(bytes)) continue;
      if (total + bytes.byteLength > SNAPSHOT_MAX_TOTAL_BYTES) break;
      total += bytes.byteLength;
      files.push({ path: rel, contentBase64: Buffer.from(bytes).toString('base64') });
    }
    if (files.length === 0) return null;
    const res = await postJson(`${this.apiUrl}/v1/agent/snapshots`, this.token, { files, reason });
    if (res.status !== 201) {
      this.setStatus('$(warning) EPA', res.body?.error?.message ?? 'snapshot не принят');
      return null;
    }
    this.dirtySinceSnapshot = false;
    if (!res.body.reused) {
      await this.outbox?.record('snapshot_created', {
        snapshotId: res.body.snapshotId,
        baseSnapshotId: res.body.baseSnapshotId ?? null,
        manifestHash: res.body.manifestHash,
        kind: res.body.kind,
        reason: reason === 'pre_submit' ? 'pre_submit' : reason === 'git_commit' ? 'git_commit' : reason === 'significant_save' ? 'significant_save' : 'interval',
      });
    }
    return res.body;
  }

  about(): void {
    const panel = vscode.window.createWebviewPanel('epa.about', 'EPA — что собирается', vscode.ViewColumn.Active, { enableScripts: false });
    panel.webview.html = `<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8">
<style>
  body { font: 15px/1.55 -apple-system, "Segoe UI", sans-serif; color: #1c1914; background: #f7f3ea; margin: 0; padding: 28px 32px 48px; }
  h1 { font-size: 24px; margin: 0 0 8px; }
  h2 { font-size: 16px; margin: 22px 0 8px; }
  p, li { max-width: 68ch; }
  .card { background: #fffdf8; border: 1px solid #ddd4c4; padding: 14px 16px; margin: 10px 0; }
  code { font-family: ui-monospace, Menlo, monospace; font-size: 13px; }
</style>
</head>
<body>
  <h1>EPA записывает ход работы</h1>
  <p>Расширение смотрит только папку, которую вы открыли для задания, и отправляет события работодателю. Это не слежка за компьютером.</p>
  <div class="card">
    <h2>Что сохраняется</h2>
    <ul>
      <li>Начало и конец сессии в этой папке.</li>
      <li>Какие файлы созданы, изменены, сохранены или удалены, и насколько они изменились. Нажатия клавиш не пишутся.</li>
      <li>Команды в терминале этой папки, без паролей и ключей.</li>
      <li>Запуски тестов: команда, сколько прошло и сколько упало.</li>
      <li>Коммиты: сообщение, список файлов, короткий идентификатор.</li>
      <li>Снимки содержимого папки, чтобы можно было посмотреть код на момент события.</li>
      <li>Отметка о крупной вставке кода. Это повод посмотреть внимательнее, а не вывод, что решение списано.</li>
      <li>Каждое копирование и каждая вставка в этой папке: файл, объём и совпал ли фрагмент с тем, что копировали здесь же. Буфер обмена других программ не читается.</li>
    </ul>
  </div>
  <div class="card">
    <h2>Что не сохраняется</h2>
    <ul>
      <li>Клавиши, экран, камера и микрофон.</li>
      <li>Буфер обмена вне редактора этой папки.</li>
      <li>Другие папки, окна и проекты.</li>
      <li>Секреты в командах: они вырезаются до отправки.</li>
    </ul>
  </div>
  <h2>Как подключиться</h2>
  <ol>
    <li>Скачайте расширение на странице кандидата и установите через Install from VSIX…</li>
    <li>Откройте папку задания.</li>
    <li>На странице кандидата нажмите «Подключить VS Code» и подтвердите «Подключить».</li>
    <li>Если окно не открылось: команда «EPA: Подключить практику». Адрес — только начало ссылки, например <code>http://127.0.0.1:8080</code>, без адреса страницы и без <code>/v1</code>. Дальше логин и пароль с той же страницы.</li>
  </ol>
  <h2>Как сдать задание</h2>
  <p>Сначала отправьте код на сервер из папки задания:</p>
  <p><code>git add .<br>git commit -m "что сделано"<br>git push</code></p>
  <p>Закройте задачу кнопкой «Закрыть задачу» на странице кандидата. Расширение задачу не закрывает, и обычный push тоже.</p>
</body>
</html>`;
  }

  async disconnect(): Promise<void> {
    if (this.outbox) {
      await this.outbox.record('session_ended', { reason: 'user_closed' });
      await this.outbox.flush();
    }
    this.stopWatching();
    this.outbox?.close();
    this.outbox = null;
    this.token = '';
    await this.context.secrets.delete(TOKEN_KEY);
    await this.context.globalState.update(LINK_KEY, undefined);
    this.setStatus('EPA: не подключено', 'Запись остановлена');
  }

  async flush(): Promise<void> {
    await this.outbox?.flush();
  }

  private stopWatching(): void {
    for (const timer of this.pendingEdits.values()) clearTimeout(timer.timer);
    this.pendingEdits.clear();
    this.executions.clear();
    if (this.heartbeat) clearInterval(this.heartbeat);
    if (this.snapshotTimer) clearInterval(this.snapshotTimer);
    this.heartbeat = null;
    this.snapshotTimer = null;
    for (const sub of this.subscriptions) sub.dispose();
    this.subscriptions = [];
  }

  dispose(): void {
    this.stopWatching();
    this.outbox?.close();
    this.status.dispose();
  }
}
