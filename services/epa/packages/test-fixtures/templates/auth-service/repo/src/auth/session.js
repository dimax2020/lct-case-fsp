export function createSession(userId, ttlMs, now = Date.now()) {
  return { userId, createdAt: now, expiresAt: now + ttlMs };
}

export function isSessionExpired(session, now = Date.now()) {
  return now > session.expiresAt;
}
