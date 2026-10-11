<script setup lang="ts">
export interface NavLink { label: string; href?: string; active?: boolean }
const props = withDefaults(defineProps<{
  product?: string; links?: NavLink[]; user?: string; unread?: boolean
  logoDark?: string; logoLight?: string; logoAlt?: string; homeHref?: string
}>(), { links: () => [], logoDark: '/brand/championship-logo-white.svg', logoLight: '/brand/championship-logo-navy.svg', logoAlt: 'Чемпионат России', homeHref: '/' })

const route = useRoute()
const isEmployer = computed(() => route.path.startsWith('/employer'))
const menu = ref<'' | 'bell' | 'user'>('')
const root = ref<HTMLElement>()
const hasUnread = ref(props.unread ?? true)
const { show } = useToast()

const userMenu = computed(() => isEmployer.value
  ? [{ label: 'Профиль компании', to: '/employer/company' }, { label: 'Приглашения', to: '/employer/invites' }]
  : [{ label: 'Мой профиль', to: '/candidate/profile' }, { label: 'Настройки и приватность', to: '/candidate/settings' }])

const anyMatch = computed(() => props.links.some(l => l.href === route.path))
const testCount = ref(0)

async function loadTestCount() {
  if (!props.links.some(l => l.href === '/candidate/process')) {
    testCount.value = 0
    return
  }
  try {
    const applications = await $fetch<unknown>('/api/v1/applications', { query: { role: 'candidate' } })
    const rows = Array.isArray(applications)
      ? applications as { vacancy_id?: string }[]
      : ((applications as { items?: { vacancy_id?: string }[] } | null)?.items ?? [])
    const vacancyIds = [...new Set(rows.map(row => row.vacancy_id).filter((id): id is string => !!id))]
    if (!vacancyIds.length) {
      testCount.value = 0
      return
    }
    const found = await $fetch<{ vacancyIds?: string[] }>('/v1/vacancy-tasks/lookup', { method: 'POST', body: { vacancyIds } })
    testCount.value = found.vacancyIds?.length ?? 0
  } catch {
    testCount.value = 0
  }
}
function isActive(l: NavLink) {
  if (anyMatch.value) return l.href === route.path
  return !!l.active
}
function toggle(m: 'bell' | 'user') {
  menu.value = menu.value === m ? '' : m
  if (m === 'bell') hasUnread.value = false
}
function onDoc(e: MouseEvent) { if (root.value && !root.value.contains(e.target as Node)) menu.value = '' }
onMounted(() => {
  document.addEventListener('click', onDoc)
  void loadTestCount()
})
onBeforeUnmount(() => document.removeEventListener('click', onDoc))
watch(() => route.fullPath, () => { menu.value = '' })
</script>

<template>
  <header ref="root" class="fsp-header">
    <NuxtLink class="fsp-header-brand" :to="homeHref">
      <img class="fsp-only-dark" :src="logoDark" :alt="logoAlt">
      <img class="fsp-only-light" :src="logoLight" :alt="logoAlt">
      <span v-if="product" class="fsp-header-product">{{ product }}</span>
    </NuxtLink>
    <nav class="fsp-header-nav" aria-label="Основная навигация">
      <template v-for="l in links" :key="l.label">
        <NuxtLink v-if="l.href && l.href.startsWith('/')" :to="l.href" :aria-current="isActive(l) ? 'page' : undefined" :aria-label="l.href === '/candidate/process' && testCount ? `${l.label}, тестовых: ${testCount}` : undefined">
          <span class="fsp-nav-label">{{ l.label }}<span v-if="l.href === '/candidate/process' && testCount" class="fsp-nav-count">{{ testCount }}</span></span>
        </NuxtLink>
        <a v-else href="#" @click.prevent="show('Раздел «' + l.label + '» ещё не реализован в рамках MVP')">{{ l.label }}</a>
      </template>
    </nav>
    <div class="fsp-header-actions">
      <slot name="actions">
        <span class="fsp-header-bell fsp-menu-anchor">
          <FspButton variant="ghost" icon="bell" aria-label="Уведомления" :aria-expanded="menu === 'bell'" @click.stop="toggle('bell')" />
          <i v-if="hasUnread" aria-hidden="true" />
          <div v-if="menu === 'bell'" class="fsp-menu fsp-cut" role="menu">
            <div class="fsp-menu-title">Уведомления</div>
            <div class="fsp-menu-item" role="menuitem">Ещё не реализовано в рамках MVP</div>
          </div>
        </span>
        <span v-if="user" class="fsp-menu-anchor">
          <FspButton variant="outline" size="sm" icon="user" :aria-expanded="menu === 'user'" @click.stop="toggle('user')">{{ user }}</FspButton>
          <div v-if="menu === 'user'" class="fsp-menu fsp-cut" role="menu">
            <NuxtLink v-for="m in userMenu" :key="m.to" :to="m.to" class="fsp-menu-item" role="menuitem">{{ m.label }}</NuxtLink>
            <button type="button" class="fsp-menu-item" role="menuitem" disabled style="opacity:.55; cursor:not-allowed; background:transparent; border:0; text-align:left; width:100%; color:inherit; font:inherit;">Смена кабинета ещё не реализована в рамках MVP</button>
            <a href="/auth/keycloak/logout" class="fsp-menu-item" role="menuitem">Выйти</a>
          </div>
        </span>
        <FspButton v-else variant="plate" size="sm" href="/auth">Войти</FspButton>
      </slot>
    </div>
  </header>
</template>

<style>
.fsp-menu-anchor { position: relative; display: inline-flex; }
.fsp-menu { --cut: var(--cut-m); --fill: var(--gray-bright); --edge: var(--line-strong); --bw: 1px; position: absolute; top: calc(100% + 8px); right: 0; z-index: 50; min-width: 300px; padding: 8px 0; display: flex; flex-direction: column; }
.fsp-menu-title { padding: 8px 16px 10px; font-size: 12px; font-weight: 600; letter-spacing: .06em; text-transform: uppercase; color: var(--text-muted); }
.fsp-menu-item { padding: 10px 16px; font: 500 14px/20px var(--font-sans); color: var(--text); text-decoration: none; }
.fsp-menu-item:hover { background: var(--surface-hover); color: var(--text); }
</style>
