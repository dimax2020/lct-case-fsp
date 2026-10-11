const { test } = require('node:test');

test('never finishes', () => {
  // eslint-disable-next-line no-constant-condition
  while (true) {}
});
