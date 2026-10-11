export function useCabinetUser(fallback = '') {
  const { data } = useFetch('/api/bff/session', {
    key: 'fsp-bff-session',
    default: () => ({ authenticated: false as boolean, name: null as string | null }),
    credentials: 'include',
  })
  return computed(() => data.value?.name || fallback)
}
