import type { Ref } from 'vue'
import { apiFetch, asList } from '~/utils/raw'

export interface NotificationItem {
  id: string
  text: string
  to: string
  at: string | null
}

type InvitationRow = {
  id: string
  status: string
  title: string
  created_at: string
  company_name?: string | null
  candidate_display_name?: string | null
}

const SEEN_KEY = 'fsp-seen-notifications'

function readSeen(): string[] {
  try {
    const raw = localStorage.getItem(SEEN_KEY)
    const parsed = raw ? JSON.parse(raw) as unknown : []
    return Array.isArray(parsed) ? parsed.filter((x): x is string => typeof x === 'string') : []
  } catch {
    return []
  }
}

function writeSeen(ids: string[]) {
  try {
    localStorage.setItem(SEEN_KEY, JSON.stringify(ids.slice(-300)))
  } catch {
    // Без хранилища уведомления просто снова считаются новыми.
  }
}

/**
 * Уведомления собираются из приглашений: кандидату — новые предложения,
 * работодателю — ответы. Прочитанные id хранятся в браузере.
 */
export function useNotifications(role: Readonly<Ref<'candidate' | 'employer'>>) {
  const items = ref<NotificationItem[]>([])
  const seen = ref<string[]>([])
  const loaded = ref(false)

  async function load() {
    seen.value = readSeen()
    const out: NotificationItem[] = []
    try {
      const invites = asList<InvitationRow>(await apiFetch<unknown>('/api/v1/invitations', { query: { role: role.value } }))
      for (const inv of invites) {
        if (role.value === 'candidate' && inv.status === 'sent') {
          out.push({ id: `inv-${inv.id}-sent`, text: `Новое приглашение: ${inv.title}${inv.company_name ? ` · ${inv.company_name}` : ''}`, to: '/candidate/invites', at: inv.created_at })
        }
        if (role.value === 'employer' && (inv.status === 'accepted' || inv.status === 'declined')) {
          const who = inv.candidate_display_name || 'Кандидат'
          out.push({
            id: `inv-${inv.id}-${inv.status}`,
            text: inv.status === 'accepted' ? `${who} принял(а) приглашение «${inv.title}»` : `${who} отклонил(а) приглашение «${inv.title}»`,
            to: inv.status === 'accepted' ? `/employer/chat?invitation=${inv.id}` : '/employer/invites',
            at: inv.created_at,
          })
        }
      }
    } catch {
      // Уведомления не критичны: молча показываем то, что удалось собрать.
    }
    items.value = out.sort((a, b) => String(b.at ?? '').localeCompare(String(a.at ?? ''))).slice(0, 12)
    loaded.value = true
  }

  const unread = computed(() => items.value.filter(item => !seen.value.includes(item.id)).length)

  function markAllSeen() {
    const next = Array.from(new Set([...seen.value, ...items.value.map(item => item.id)]))
    seen.value = next
    writeSeen(next)
  }

  return { items, unread, loaded, load, markAllSeen, isSeen: (id: string) => seen.value.includes(id) }
}
