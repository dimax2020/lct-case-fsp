/** Тема интерфейса. Хранится в cookie, поэтому сервер сразу отдаёт страницу в нужной теме, без вспышки. */
export function useTheme() {
  const theme = useCookie<'dark' | 'light'>('fsp-theme', {
    default: () => 'dark',
    maxAge: 60 * 60 * 24 * 365,
    sameSite: 'lax',
  })
  function toggle() {
    theme.value = theme.value === 'light' ? 'dark' : 'light'
  }
  return { theme, toggle }
}
