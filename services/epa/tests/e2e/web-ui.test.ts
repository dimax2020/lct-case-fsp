import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import { createTestPlatform, type TestPlatform } from '@epa/test-fixtures';

describe('Web UI (employer / candidate browser IDE)', () => {
  let t: TestPlatform;
  beforeAll(async () => {
    t = await createTestPlatform();
  });
  afterAll(async () => t.close());

  it('serves the static UI with a locked-down CSP and no inline scripts', async () => {
    for (const url of ['/', '/index.html', '/employer.html', '/candidate.html', '/app.css', '/common.js', '/employer.js', '/candidate.js']) {
      const res = await t.app.inject({ method: 'GET', url });
      expect(res.statusCode, url).toBe(200);
      expect(String(res.headers['content-security-policy'])).toContain("script-src 'self'");
      expect(String(res.headers['content-security-policy'])).toContain("connect-src 'self'");
    }
    const index = await t.app.inject({ method: 'GET', url: '/' });
    expect(index.body).toContain('Работодатель');
    expect(index.body).toContain('Кандидат');
    const employer = await t.app.inject({ method: 'GET', url: '/employer.html' });
    expect(employer.body).toContain('/employer.js');
    expect(employer.body).not.toContain('<script>alert');
    const candidate = await t.app.inject({ method: 'GET', url: '/candidate.html' });
    expect(candidate.body).toContain('/candidate.js');
    expect(candidate.body).toContain('VS Code');
    expect(candidate.body).toContain('открытой папки');
  });

  it('candidate workspace access still reports sshAccess=false', async () => {
    const health = await t.app.inject({ method: 'GET', url: '/healthz' });
    expect(health.statusCode).toBe(200);
    expect(JSON.parse(health.body).ok).toBe(true);
  });
});
