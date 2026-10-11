export const REDACTED = '[REDACTED]';

interface Rule {
  name: string;
  pattern: RegExp;
  replace: (match: string, ...groups: string[]) => string;
}

const SECRET_NAME = '[A-Za-z0-9_]*(?:SECRET|TOKEN|PASSWORD|PASSWD|PWD|API_?KEY|ACCESS_?KEY|PRIVATE_?KEY|CREDENTIALS?|AUTH)[A-Za-z0-9_]*';

const RULES: Rule[] = [
  {
    name: 'private_key_block',
    pattern: /-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?(?:-----END [A-Z ]*PRIVATE KEY-----|$)/g,
    replace: () => REDACTED,
  },
  { name: 'aws_access_key', pattern: /\b(?:AKIA|ASIA)[0-9A-Z]{16}\b/g, replace: () => REDACTED },
  { name: 'github_token', pattern: /\b(?:ghp|gho|ghu|ghs|ghr|github_pat)_[A-Za-z0-9_]{20,}\b/g, replace: () => REDACTED },
  { name: 'slack_token', pattern: /\bxox[abprs]-[A-Za-z0-9-]{10,}\b/g, replace: () => REDACTED },
  { name: 'openai_like_key', pattern: /\bsk-[A-Za-z0-9_-]{16,}\b/g, replace: () => REDACTED },
  { name: 'jwt', pattern: /\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b/g, replace: () => REDACTED },
  {
    name: 'bearer',
    pattern: /\b(Bearer|Basic|Token)\s+[A-Za-z0-9._~+/=-]{8,}/gi,
    replace: (_m, scheme) => `${scheme} ${REDACTED}`,
  },
  {
    name: 'url_credentials',
    pattern: /([a-z][a-z0-9+.-]*:\/\/)([^\s/:@]+):([^\s/@]+)@/gi,
    replace: (_m, scheme, user) => `${scheme}${user}:${REDACTED}@`,
  },
  {
    name: 'named_assignment',
    pattern: new RegExp(`\\b(${SECRET_NAME})(\\s*[=:]\\s*)("[^"]*"|'[^']*'|[^\\s"';&|]+)`, 'gi'),
    replace: (_m, name, sep) => `${name}${sep}${REDACTED}`,
  },
  {
    name: 'cli_flag',
    pattern: /(--?(?:password|passwd|token|secret|api-key|apikey|access-key|auth)(?:=|\s+))("[^"]*"|'[^']*'|[^\s"']+)/gi,
    replace: (_m, flag) => `${flag}${REDACTED}`,
  },
];

export interface RedactionResult {
  text: string;
  redactions: number;
  rules: string[];
}

export function redactSecretsDetailed(input: string): RedactionResult {
  let text = input;
  let redactions = 0;
  const rules = new Set<string>();
  for (const rule of RULES) {
    text = text.replace(rule.pattern, (...args: unknown[]) => {
      redactions += 1;
      rules.add(rule.name);
      const match = args[0] as string;
      const groups = args.slice(1, -2) as string[];
      return rule.replace(match, ...groups);
    });
  }
  return { text, redactions, rules: [...rules] };
}

export function redactSecrets(input: string): string {
  return redactSecretsDetailed(input).text;
}

/** Redacts and truncates log output to a byte budget, marking truncation explicitly. */
export function safeLog(input: string, maxBytes: number): { text: string; truncated: boolean; originalBytes: number } {
  const redacted = redactSecrets(input);
  const buf = Buffer.from(redacted, 'utf8');
  if (buf.length <= maxBytes) return { text: redacted, truncated: false, originalBytes: buf.length };
  const marker = `\n...[truncated ${buf.length - maxBytes} bytes]`;
  const head = buf.subarray(0, Math.max(0, maxBytes - Buffer.byteLength(marker))).toString('utf8').replace(/\uFFFD+$/, '');
  return { text: head + marker, truncated: true, originalBytes: buf.length };
}

/** File names whose content must never be sent to AI or shown in logs. */
export function isSecretFile(relPath: string): boolean {
  const base = relPath.split('/').pop() ?? relPath;
  return /^\.env(\..*)?$/i.test(base) || /\.(pem|key|p12|pfx)$/i.test(base) || /^id_(rsa|ed25519|ecdsa)$/.test(base) || base === '.npmrc' || base === '.netrc';
}
