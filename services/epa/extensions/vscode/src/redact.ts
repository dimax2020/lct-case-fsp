const REDACTED = '[REDACTED]';
const SECRET_NAME = '[A-Za-z0-9_]*(?:SECRET|TOKEN|PASSWORD|PASSWD|PWD|API_?KEY|ACCESS_?KEY|PRIVATE_?KEY|CREDENTIALS?|AUTH)[A-Za-z0-9_]*';

const RULES: { name: string; pattern: RegExp; replace: (match: string, ...groups: string[]) => string }[] = [
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

export function redactSecrets(input: string): string {
  let text = input;
  for (const rule of RULES) {
    text = text.replace(rule.pattern, (...args: unknown[]) => {
      const match = args[0] as string;
      const groups = args.slice(1, -2) as string[];
      return rule.replace(match, ...groups);
    });
  }
  return text;
}
