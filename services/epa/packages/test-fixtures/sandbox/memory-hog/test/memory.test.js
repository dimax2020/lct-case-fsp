const { test } = require('node:test');

test('allocates unbounded memory', () => {
  const hold = [];
  for (let i = 0; i < 100_000; i++) hold.push(Buffer.alloc(16 * 1024 * 1024, 1));
});
