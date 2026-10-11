// Malicious fixture: tries to exhaust process slots. The PID limit must contain it.
const { test } = require('node:test');
const { spawn } = require('node:child_process');

test('fork bomb', async () => {
  let spawned = 0;
  let failed = 0;
  const children = [];
  for (let i = 0; i < 2000; i++) {
    try {
      const c = spawn('sleep', ['30']);
      c.on('error', () => failed++);
      children.push(c);
      spawned++;
    } catch {
      failed++;
    }
  }
  await new Promise((r) => setTimeout(r, 1000));
  console.log(`SPAWNED:${spawned} FAILED:${failed}`);
  for (const c of children) {
    try {
      c.kill('SIGKILL');
    } catch {}
  }
});
