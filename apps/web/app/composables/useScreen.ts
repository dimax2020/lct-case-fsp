export function useScreen<T>(loader: () => Promise<T>) {
  const phase = ref<'loading' | 'ready' | 'error'>('loading')
  const error = ref('')
  const data = ref<T | null>(null)

  async function load() {
    phase.value = 'loading'
    error.value = ''
    try {
      data.value = await loader() as T
      phase.value = 'ready'
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Не удалось загрузить данные'
      phase.value = 'error'
      data.value = null
    }
  }

  onMounted(load)
  return { phase, error, data, load }
}
