import { createHash } from 'node:crypto';
import { CONSENT_VERSION } from './policies.js';

export interface ConsentNotice {
  version: string;
  title: string;
  collectedEvents: { type: string; description: string }[];
  notCollected: string[];
  purpose: string;
  retention: string;
  visibleTo: string[];
  textHash: string;
}

const collectedEvents = [
  { type: 'session_started / session_ended', description: 'Начало и завершение сессии расширения VS Code в открытой папке задания, причина завершения.' },
  { type: 'file_changed / file_saved / file_created / file_deleted', description: 'Относительный путь файла внутри workspace и объём изменения (без нажатий клавиш).' },
  { type: 'test_started / test_finished', description: 'Запуск тестов в workspace: команда, код выхода, количество passed/failed, длительность.' },
  { type: 'terminal_command', description: 'Команды, запущенные в workspace, после удаления секретов; код выхода и длительность.' },
  { type: 'git_commit', description: 'SHA, сообщение и список изменённых файлов коммита.' },
  { type: 'snapshot_created', description: 'Периодические снимки содержимого репозитория workspace для воспроизведения процесса.' },
  { type: 'large_insertion_signal', description: 'Отметка о крупной единовременной вставке кода. Это сигнал для дополнительной проверки, а не обвинение.' },
  { type: 'code_copied / code_pasted', description: 'Копирование и вставка внутри открытой папки задания: файл, объём и совпало ли вставление с фрагментом, скопированным в этой же папке. Текст буфера обмена других программ не читается.' },
];

const notCollected = [
  'Нажатия клавиш и глобальный ввод',
  'Экран, камера, микрофон',
  'Буфер обмена вне редактора workspace',
  'Файлы, процессы и пути за пределами открытой папки задания',
  'Другие окна VS Code и папки, не входящие в это задание',
  'Секреты в командах (удаляются до сохранения)',
];

export function consentNotice(retentionDays: number): ConsentNotice {
  const base = {
    version: CONSENT_VERSION,
    title: 'Согласие на сбор телеметрии рабочей среды задания',
    collectedEvents,
    notCollected,
    purpose:
      'Восстановить процесс выполнения задания (Development Timeline) для оценки работодателем. Сигналы телеметрии не являются доказательством нарушений.',
    retention: `Данные хранятся ${retentionDays} дней после завершения или истечения задания, затем удаляются или анонимизируются; остаётся минимальная запись аудита.`,
    visibleTo: ['Работодатель организации, создавшей задание', 'Аудитор организации (только чтение)', 'Вы сами'],
  };
  const textHash = createHash('sha256').update(JSON.stringify(base)).digest('hex');
  return { ...base, textHash };
}
