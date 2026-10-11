const { test } = require('node:test');
const assert = require('node:assert/strict');

test('adds numbers', () => assert.equal(1 + 2, 3));
test('concatenates strings', () => assert.equal('a' + 'b', 'ab'));
test('writes to tmp copy', () => {
  require('node:fs').writeFileSync('scratch.txt', 'ok');
  assert.ok(true);
});
