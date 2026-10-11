import { inflateRawSync } from 'node:zlib';
import { open, mkdir, writeFile } from 'node:fs/promises';
import type { FileHandle } from 'node:fs/promises';
import path from 'node:path';
import { DomainError, isSafeRelativePath } from '@epa/domain';

const MAX_FILES = 100_000;
const MAX_UNCOMPRESSED = 8 * 1024 * 1024 * 1024;
const MAX_FILE = 1024 * 1024 * 1024;
const SKIP_DIRS = new Set(['node_modules', '.git', '.next', '.epa', '__pycache__', '.venv', 'venv', 'bower_components', '.gradle', 'Pods', 'coverage', '.turbo', '.cache', '__MACOSX']);

function crc32(buf: Buffer): number {
  let c = ~0;
  for (let i = 0; i < buf.length; i++) {
    c ^= buf[i];
    for (let k = 0; k < 8; k++) c = (c >>> 1) ^ (0xedb88320 & -(c & 1));
  }
  return ~c >>> 0;
}

/** Builds a stored (uncompressed) zip. Used by tests and small fixtures. */
export function zipStore(files: { name: string; data: Buffer | string }[]): Buffer {
  const locals: Buffer[] = [];
  const centrals: Buffer[] = [];
  let offset = 0;
  for (const file of files) {
    const data = Buffer.isBuffer(file.data) ? file.data : Buffer.from(file.data);
    const name = Buffer.from(file.name);
    const crc = crc32(data);
    const local = Buffer.alloc(30 + name.length);
    local.writeUInt32LE(0x04034b50, 0);
    local.writeUInt16LE(20, 4);
    local.writeUInt16LE(0, 8);
    local.writeUInt32LE(crc, 14);
    local.writeUInt32LE(data.length, 18);
    local.writeUInt32LE(data.length, 22);
    local.writeUInt16LE(name.length, 26);
    name.copy(local, 30);
    locals.push(local, data);
    const central = Buffer.alloc(46 + name.length);
    central.writeUInt32LE(0x02014b50, 0);
    central.writeUInt16LE(20, 4);
    central.writeUInt16LE(20, 6);
    central.writeUInt32LE(crc, 16);
    central.writeUInt32LE(data.length, 20);
    central.writeUInt32LE(data.length, 24);
    central.writeUInt16LE(name.length, 28);
    central.writeUInt32LE(offset, 42);
    name.copy(central, 46);
    centrals.push(central);
    offset += local.length + data.length;
  }
  const centralBuf = Buffer.concat(centrals);
  const end = Buffer.alloc(22);
  end.writeUInt32LE(0x06054b50, 0);
  end.writeUInt16LE(files.length, 8);
  end.writeUInt16LE(files.length, 10);
  end.writeUInt32LE(centralBuf.length, 12);
  end.writeUInt32LE(offset, 16);
  return Buffer.concat([...locals, centralBuf, end]);
}

interface ZipReader {
  size: number;
  readAt(pos: number, len: number): Promise<Buffer>;
}

interface ZipEntry {
  name: string;
  method: number;
  compSize: number;
  localOff: number;
}

function u32(buf: Buffer, pos: number): number {
  return buf.readUInt32LE(pos);
}

function fits(value: bigint): number {
  if (value > BigInt(Number.MAX_SAFE_INTEGER)) throw new DomainError('PAYLOAD_TOO_LARGE', 'архив слишком большой');
  return Number(value);
}

/** Zip64 extra field replaces any size or offset stored as 0xFFFFFFFF. */
function zip64Extra(extra: Buffer, needUncomp: boolean, needComp: boolean, needOff: boolean): { uncomp?: bigint; comp?: bigint; offset?: bigint } {
  let o = 0;
  while (o + 4 <= extra.length) {
    const id = extra.readUInt16LE(o);
    const size = extra.readUInt16LE(o + 2);
    const data = extra.subarray(o + 4, o + 4 + size);
    o += 4 + size;
    if (id !== 1 || data.length < 8) continue;
    let p = 0;
    const read64 = () => {
      if (p + 8 > data.length) throw new DomainError('VALIDATION', 'архив повреждён');
      const v = data.readBigUInt64LE(p);
      p += 8;
      return v;
    };
    return {
      uncomp: needUncomp ? read64() : undefined,
      comp: needComp ? read64() : undefined,
      offset: needOff ? read64() : undefined,
    };
  }
  return {};
}

async function findCentralDirectory(reader: ZipReader): Promise<{ offset: number; count: number }> {
  const tailLen = Math.min(reader.size, 22 + 65536);
  const tail = await reader.readAt(reader.size - tailLen, tailLen);
  let eocd = -1;
  for (let i = tail.length - 22; i >= 0; i--) {
    if (u32(tail, i) === 0x06054b50) {
      eocd = i;
      break;
    }
  }
  if (eocd < 0) throw new DomainError('VALIDATION', 'это не zip-архив');
  const count16 = tail.readUInt16LE(eocd + 10);
  const offset32 = u32(tail, eocd + 16);
  if (count16 !== 0xffff && offset32 !== 0xffffffff) return { count: count16, offset: offset32 };
  const locAt = eocd >= 20 && u32(tail, eocd - 20) === 0x07064b50 ? eocd - 20 : tail.lastIndexOf(Buffer.from([0x50, 0x4b, 0x06, 0x07]));
  if (locAt < 0 || locAt + 20 > tail.length) throw new DomainError('VALIDATION', 'архив повреждён');
  const z64off = fits(tail.readBigUInt64LE(locAt + 8));
  const z64 = await reader.readAt(z64off, 56);
  if (u32(z64, 0) !== 0x06064b50) throw new DomainError('VALIDATION', 'архив повреждён');
  return { count: fits(z64.readBigUInt64LE(32)), offset: fits(z64.readBigUInt64LE(48)) };
}

async function readCentralDirectory(reader: ZipReader): Promise<{ kept: ZipEntry[]; skipped: number }> {
  const { count, offset } = await findCentralDirectory(reader);
  const kept: ZipEntry[] = [];
  let skipped = 0;
  let cursor = offset;
  for (let n = 0; n < count; n++) {
    const head = await reader.readAt(cursor, 46);
    if (u32(head, 0) !== 0x02014b50) throw new DomainError('VALIDATION', 'архив повреждён');
    const method = head.readUInt16LE(10);
    let compSize = u32(head, 20);
    let uncompSize = u32(head, 24);
    const nameLen = head.readUInt16LE(28);
    const extraLen = head.readUInt16LE(30);
    const commentLen = head.readUInt16LE(32);
    let localOff = u32(head, 42);
    const rest = await reader.readAt(cursor + 46, nameLen + extraLen);
    const name = rest.subarray(0, nameLen).toString('utf8');
    const extra = rest.subarray(nameLen, nameLen + extraLen);
    if (uncompSize === 0xffffffff || compSize === 0xffffffff || localOff === 0xffffffff) {
      const z64 = zip64Extra(extra, uncompSize === 0xffffffff, compSize === 0xffffffff, localOff === 0xffffffff);
      if (z64.comp !== undefined) compSize = fits(z64.comp);
      if (z64.offset !== undefined) localOff = fits(z64.offset);
      if (z64.uncomp !== undefined) uncompSize = fits(z64.uncomp);
    }
    cursor += 46 + nameLen + extraLen + commentLen;
    if (!name || name.endsWith('/') || name.split('/').includes('.DS_Store')) continue;
    const rel = name.replace(/\\/g, '/').replace(/^\/+/, '');
    if (rel.split('/').some((part) => SKIP_DIRS.has(part))) {
      skipped += 1;
      continue;
    }
    if (!isSafeRelativePath(rel)) throw new DomainError('VALIDATION', `недопустимый путь в архиве: ${name}`);
    if (uncompSize > MAX_FILE || compSize > MAX_FILE) throw new DomainError('PAYLOAD_TOO_LARGE', `файл слишком большой: ${rel}`);
    kept.push({ name: rel, method, compSize, localOff });
    if (kept.length > MAX_FILES) throw new DomainError('PAYLOAD_TOO_LARGE', 'в архиве слишком много файлов');
  }
  return { kept, skipped };
}

/**
 * Extracts a zip into `dest`. Rejects paths that leave the directory.
 * A single top-level folder is unwrapped, so `project/src/a.js` becomes `src/a.js`.
 * Dependency directories are skipped so a large project stays the source tree.
 */
export async function unzipSafe(source: Buffer | string, dest: string, onFile?: (done: number, total: number) => void): Promise<{ files: number; skipped: number }> {
  const file = typeof source === 'string' ? await open(source, 'r') : null;
  const reader: ZipReader = file
    ? {
        size: (await file.stat()).size,
        async readAt(pos, len) {
          const buf = Buffer.alloc(len);
          const { bytesRead } = await file.read(buf, 0, len, pos);
          if (bytesRead !== len) throw new DomainError('VALIDATION', 'архив повреждён');
          return buf;
        },
      }
    : {
        size: source.length,
        async readAt(pos, len) {
          if (pos < 0 || len < 0 || pos + len > source.length) throw new DomainError('VALIDATION', 'архив повреждён');
          return source.subarray(pos, pos + len);
        },
      };
  try {
    if (reader.size < 22) throw new DomainError('VALIDATION', 'архив пустой');
    const { kept, skipped } = await readCentralDirectory(reader);
    if (kept.length === 0) throw new DomainError('VALIDATION', 'в архиве нет файлов проекта. Папки зависимостей не копируются.');
    const roots = new Set(kept.map((f) => f.name.split('/')[0]));
    const nested = kept.every((f) => f.name.includes('/')) && roots.size === 1;
    const prefix = nested ? `${[...roots][0]}/` : '';
    let total = 0;
    let written = 0;
    onFile?.(0, kept.length);
    for (const entry of kept) {
      const local = await reader.readAt(entry.localOff, 30);
      if (u32(local, 0) !== 0x04034b50) throw new DomainError('VALIDATION', 'архив повреждён');
      const dataOff = entry.localOff + 30 + local.readUInt16LE(26) + local.readUInt16LE(28);
      const compressed = await reader.readAt(dataOff, entry.compSize);
      let data: Buffer;
      if (entry.method === 0) data = Buffer.from(compressed);
      else if (entry.method === 8) {
        try {
          data = inflateRawSync(compressed, { maxOutputLength: Math.min(MAX_FILE, MAX_UNCOMPRESSED - total) });
        } catch (e) {
          if (e instanceof RangeError) throw new DomainError('PAYLOAD_TOO_LARGE', 'распакованный проект слишком большой');
          throw e;
        }
      } else throw new DomainError('VALIDATION', 'архив использует неподдерживаемое сжатие');
      total += data.length;
      if (total > MAX_UNCOMPRESSED) throw new DomainError('PAYLOAD_TOO_LARGE', 'распакованный проект слишком большой');
      const rel = prefix ? entry.name.slice(prefix.length) : entry.name;
      if (!rel || !isSafeRelativePath(rel)) continue;
      const target = path.join(dest, rel);
      await mkdir(path.dirname(target), { recursive: true });
      await writeFile(target, data);
      written += 1;
      onFile?.(written, kept.length);
    }
    return { files: written, skipped };
  } finally {
    await file?.close();
  }
}
