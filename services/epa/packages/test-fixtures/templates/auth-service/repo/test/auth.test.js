import { test } from 'node:test';
import assert from 'node:assert/strict';
import { hashPassword, verifyPassword } from '../src/auth/password.js';
import { createSession, isSessionExpired } from '../src/auth/session.js';

test('accepts the correct password', () => {
  assert.equal(verifyPassword('s3cret', hashPassword('s3cret')), true);
});

test('rejects a wrong password', () => {
  assert.equal(verifyPassword('wrong', hashPassword('s3cret')), false);
});

test('session is active before expiry', () => {
  const s = createSession('u1', 1000, 0);
  assert.equal(isSessionExpired(s, 999), false);
});

test('session expires exactly at expiresAt', () => {
  const s = createSession('u1', 1000, 0);
  assert.equal(isSessionExpired(s, 1000), true);
});
