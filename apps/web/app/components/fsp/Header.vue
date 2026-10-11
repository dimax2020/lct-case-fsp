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

const notes = computed(() => isEmployer.value
  ? [
      { text: 'Алексей Кузнецов принял приглашение', to: '/employer/chat' },
      { text: 'Мария С. просмотрела приглашение', to: '/employer/invites' },
      { text: 'В подборке «Backend · Middle» 12 новых кандидатов', to: '/employer/pool' }
    ]
  : [
      { text: 'Код Сибири пригласил вас на Backend (Go)', to: '/candidate/invites' },
      { text: 'Новое задание от работодателя — +баллы к рейтингу', to: '/candidate/grade' },
      { text: 'Вы поднялись на 3 место в категории', to: '/candidate/grade' }
    ])
const userMenu = computed(() => isEmployer.value
  ? [{ label: 'Профиль компании', to: '/employer/company' }, { label: 'Приглашения', to: '/employer/invites' }]
  : [{ label: 'Мой профиль', to: '/candidate/profile' }, { label: 'Настройки и приватность', to: '/candidate/settings' }])

const anyMatch = computed(() => props.links.some(l => l.href === route.path))
function isActive(l: NavLink) {
  if (anyMatch.value) return l.href === route.path
  return !!l.active
}
function toggle(m: 'bell' | 'user') {
  menu.value = menu.value === m ? '' : m
  if (m === 'bell') hasUnread.value = false
}
function previewRole(role: 'candidate' | 'employer') {
  if (import.meta.client) sessionStorage.setItem('fsp-mock-role', role)
}
function onDoc(e: MouseEvent) { if (root.value && !root.value.contains(e.target as Node)) menu.value = '' }
onMounted(() => document.addEventListener('click', onDoc))
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
        <NuxtLink v-if="l.href && l.href.startsWith('/')" :to="l.href" :aria-current="isActive(l) ? 'page' : undefined">{{ l.label }}</NuxtLink>
        <a v-else href="#" @click.prevent="show('Раздел «' + l.label + '» появится в следующей версии')">{{ l.label }}</a>
      </template>
    </nav>
    <div class="fsp-header-actions">
      <slot name="actions">
        <span class="fsp-header-bell fsp-menu-anchor">
          <FspButton variant="ghost" icon="bell" aria-label="Уведомления" :aria-expanded="menu === 'bell'" @click.stop="toggle('bell')" />
          <i v-if="hasUnread" aria-hidden="true" />
          <div v-if="menu === 'bell'" class="fsp-menu fsp-cut" role="menu">
            <div class="fsp-menu-title">Уведомления</div>
            <NuxtLink v-for="n in notes" :key="n.text" :to="n.to" class="fsp-menu-item" role="menuitem">{{ n.text }}</NuxtLink>
          </div>
        </span>
        <span v-if="user" class="fsp-menu-anchor">
          <FspButton variant="outline" size="sm" icon="user" :aria-expanded="menu === 'user'" @click.stop="toggle('user')">{{ user }}</FspButton>
          <div v-if="menu === 'user'" class="fsp-menu fsp-cut" role="menu">
            <NuxtLink v-for="m in userMenu" :key="m.to" :to="m.to" class="fsp-menu-item" role="menuitem">{{ m.label }}</NuxtLink>
            <NuxtLink :to="isEmployer ? '/candidate/profile' : '/employer/need'" class="fsp-menu-item" role="menuitem" @click="previewRole(isEmployer ? 'candidate' : 'employer')">{{ isEmployer ? 'Перейти в кабинет кандидата' : 'Перейти в кабинет компании' }}</NuxtLink>
            <NuxtLink to="/" class="fsp-menu-item" role="menuitem">Выйти</NuxtLink>
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
