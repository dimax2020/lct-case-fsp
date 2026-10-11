const { test } = require('node:test');
const assert = require('node:assert/strict');

test('passes', () => assert.equal(2 * 2, 4));
test('multiplication is broken', () => assert.equal(2 * 2, 5));
