// Malicious fixture: every successful escape prints a LEAK marker. The platform must block all of them.
const { test } = require('node:test');
const fs = require('node:fs');
const net = require('node:net');
const dns = require('node:dns').promises;

const leak = (what) => console.log(`LEAK:${what}`);
const tryConnect = (host, port) =>
  new Promise((resolve) => {
    const s = net.connect({ host, port, timeout: 1500 }, () => {
      s.destroy();
      resolve(true);
    });
    s.on('error', () => resolve(false));
    s.on('timeout', () => {
      s.destroy();
      resolve(false);
    });
  });

test('platform secrets are not in env', () => {
  for (const [k, v] of Object.entries(process.env)) {
    if (/SECRET|TOKEN|PASSWORD|DATABASE_URL|EPA_/i.test(k)) leak(`env:${k}`);
    if (String(v).includes('host-secret-value')) leak('env:value');
  }
});

test('no network egress', async () => {
  if (await tryConnect('1.1.1.1', 80)) leak('net:internet');
  if (await tryConnect('169.254.169.254', 80)) leak('net:metadata');
  if (await tryConnect('host.docker.internal', 8080)) leak('net:host');
  if (await tryConnect('172.17.0.1', 2375)) leak('net:docker-api');
  try {
    await dns.lookup('example.com');
    leak('net:dns');
  } catch {}
});

test('no host filesystem', () => {
  for (const p of ['/var/run/docker.sock', '/run/docker.sock', '/Users', '/home/runner', '/workspace', '/data', '/host', '/proc/1/root/etc/shadow']) {
    try {
      fs.readdirSync(p);
      leak(`fs:${p}`);
    } catch {
      try {
        fs.readFileSync(p);
        leak(`fs:${p}`);
      } catch {}
    }
  }
});

test('submission copy is read-only', () => {
  try {
    fs.writeFileSync('/src/tamper.txt', 'x');
    leak('fs:src-writable');
  } catch {}
});

test('no privileges', () => {
  if (typeof process.getuid === 'function' && process.getuid() === 0) leak('priv:root');
  try {
    fs.writeFileSync('/etc/evil', 'x');
    leak('priv:rootfs-writable');
  } catch {}
});
