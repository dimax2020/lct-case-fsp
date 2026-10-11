export function safeNext(value: unknown): string {
  if (typeof value !== 'string') return '/'
  if (!value.startsWith('/') || value.startsWith('//') || value.includes('\\') || value.includes('\n') || value.includes('\r')) {
    return '/'
  }
  if (value.length > 512) return '/'
  return value
}

export function afterRole(role: 'candidate' | 'employer', next: string): string {
  if (next.startsWith('/candidate') || next.startsWith('/employer')) return next
  // Повторный вход: в рабочий кабинет своей роли.
  if (next === '/cabinet') return role === 'employer' ? '/employer/need' : '/candidate/profile'
  // Новый кандидат сразу попадает в обязательный путь: опрос по отрасли и специализации, затем тест.
  return role === 'employer' ? '/employer/company' : '/candidate/onboarding'
}

function esc(value: string): string {
  return value.replace(/[&<>"']/g, (char) => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;'
  }[char] ?? char))
}

export function rolePickerHtml(next: string, error = ''): string {
  const candidateHref = `/auth/role?pick=candidate&next=${encodeURIComponent(next)}`
  const employerHref = `/auth/role?pick=employer&next=${encodeURIComponent(next)}`
  const errorBlock = error ? `<p role="alert" style="color:#ff8d8d;">${esc(error)}</p>` : ''
  return `<!doctype html>
<html lang="ru" data-theme="dark">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Выбор роли — Карьера ФСП</title>
  <link rel="icon" href="/brand/fsp-star-dark.svg">
  <style>
    body { margin: 0; min-height: 100vh; background: #1b1c21; color: #ededed; font-family: Inter, system-ui, sans-serif; }
    main { max-width: 720px; margin: 0 auto; padding: 64px 24px; }
    img { height: 36px; }
    h1 { font-size: 40px; line-height: 1.1; margin: 28px 0 12px; }
    p { color: #9b9c9e; font-size: 16px; line-height: 1.5; }
    form { display: grid; gap: 12px; margin-top: 28px; }
    form a { text-align: left; background: #1b1c21; color: #ededed; border: 1px solid #9b9c9e; padding: 20px; font: inherit; cursor: pointer; text-decoration: none; }
    form a strong { display: block; font-size: 16px; }
    form a span { display: block; margin-top: 4px; color: #9b9c9e; font-size: 14px; }
    form a:hover { border-color: #402fff; }
    a { color: #ededed; }
  </style>
</head>
<body>
  <main>
    <a href="/"><img src="/brand/championship-logo-white.svg" alt="Чемпионат России — на главную"></a>
    <h1>Кто вы?</h1>
    <p>Аккаунт создан. Роль выбирается один раз и попадает в токен Keycloak. Демо-пользователи уже имеют роль и эту страницу не видят.</p>
    <p><a href="/">На главную</a> · <a href="/auth/keycloak/logout">Выйти</a></p>
    ${errorBlock}
    <form>
      <a href="${esc(candidateHref)}"><strong>Я кандидат</strong><span>Пройду тест на грейд и буду получать приглашения</span></a>
      <a href="${esc(employerHref)}"><strong>Я работодатель</strong><span>Ищу специалистов и отправляю приглашения</span></a>
    </form>
  </main>
</body>
</html>`
}

export function forbiddenHtml(): string {
  return `<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <title>Недостаточно прав — Карьера ФСП</title>
  <style>
    body { margin: 0; min-height: 100vh; background: #1b1c21; color: #ededed; font-family: Inter, system-ui, sans-serif; }
    main { max-width: 640px; margin: 0 auto; padding: 64px 24px; }
    a { color: #ededed; }
  </style>
</head>
<body>
  <main>
    <h1>Недостаточно прав</h1>
    <p>Этот кабинет доступен другой роли.</p>
    <p><a href="/">На главную</a> · <a href="/auth/logout">Выйти</a></p>
  </main>
</body>
</html>`
}
