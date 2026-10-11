export interface ToastItem { id: number; text: string }

let seq = 0
export function useToast() {
  const items = useState<ToastItem[]>('fsp-toasts', () => [])
  function show(text: string, ms = 2600) {
    const id = ++seq
    items.value = [...items.value, { id, text }]
    if (import.meta.client) setTimeout(() => { items.value = items.value.filter(t => t.id !== id) }, ms)
  }
  return { items, show }
}
