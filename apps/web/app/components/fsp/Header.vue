<script setup lang="ts">
export interface NavLink { label: string; href?: string; active?: boolean }
const props = withDefaults(defineProps<{
  product?: string; links?: NavLink[]; user?: string
  logoDark?: string; logoLight?: string; logoAlt?: string; homeHref?: string
}>(), { links: () => [], logoDark: '/brand/fsp-star-dark.svg', logoLight: '/brand/fsp-star-light.svg', logoAlt: 'ФСП — на главную', homeHref: '/' })

const route = useRoute()
const isEmployer = computed(() => route.path.startsWith('/employer'))
const role = computed<'candidate' | 'employer'>(() => (isEmployer.value ? 'employer' : 'candidate'))
const menu = ref<'' | 'bell' | 'user'>('')
const root = ref<HTMLElement>()
const brand = ref<{ $el: HTMLElement }>()
const nav = ref<HTMLElement>()
const actions = ref<HTMLElement>()
const stacked = ref(false)
let observer: ResizeObserver | undefined

// Ширина самих ссылок не зависит от раскладки, поэтому шапка не мигает между режимами.
function measure() {
  const header = root.value
  if (!header || !nav.value || !actions.value) return
  const links = Array.from(nav.value.children) as HTMLElement[]
  const navGap = parseFloat(getComputedStyle(nav.value).columnGap) || 0
  const need = links.reduce((sum, el) => sum + el.offsetWidth, 0) + navGap * Math.max(0, links.length - 1)
  const style = getComputedStyle(header)
  const gap = parseFloat(style.columnGap) || 0
  const pad = parseFloat(style.paddingLeft) + parseFloat(style.paddingRight)
  const free = header.clientWidth - pad - (brand.value?.$el.offsetWidth ?? 0) - actions.value.offsetWidth - gap * 2
  stacked.value = need > free
}
const { theme, toggle: toggleTheme } = useTheme()
const notes = useNotifications(role)

const userMenu = computed(() => isEmployer.value
  ? [{ label: 'Профиль компании', to: '/employer/company' }, { label: 'Приглашения', to: '/employer/invites' }, { label: 'Переписка', to: '/employer/chat' }]
  : [{ label: 'Мой профиль', to: '/candidate/profile' }, { label: 'Редактировать профиль', to: '/candidate/profile/edit' }, { label: 'Тесты и грейд', to: '/candidate/grade' }, { label: 'Настройки и приватность', to: '/candidate/settings' }])

function isActive(l: NavLink) {
  if (!l.href) return !!l.active
  if (route.path === l.href) return true
  if (l.href !== '/' && route.path.startsWith(`${l.href}/`)) return true
  return props.links.every(x => x.href !== route.path) && !!l.active
}
function toggle(m: 'bell' | 'user') {
  menu.value = menu.value === m ? '' : m
  if (m === 'bell' && menu.value === 'bell') notes.markAllSeen()
}
function onDoc(e: MouseEvent) { if (root.value && !root.value.contains(e.target as Node)) menu.value = '' }
function onKey(e: KeyboardEvent) { if (e.key === 'Escape') menu.value = '' }
onMounted(() => {
  document.addEventListener('click', onDoc)
  document.addEventListener('keydown', onKey)
  if (props.user) void notes.load()
  measure()
  observer = new ResizeObserver(measure)
  if (root.value) observer.observe(root.value)
  if (actions.value) observer.observe(actions.value)
})
onBeforeUnmount(() => {
  document.removeEventListener('click', onDoc)
  document.removeEventListener('keydown', onKey)
  observer?.disconnect()
})
watch(() => route.fullPath, () => { menu.value = '' })
watch(() => [props.links.length, props.user], () => nextTick(measure))
</script>

<template>
  <header ref="root" :class="['fsp-header', stacked && 'fsp-header-stacked']">
    <NuxtLink ref="brand" class="fsp-header-brand" :to="homeHref">
      <img class="fsp-only-dark" :src="logoDark" :alt="logoAlt">
      <img class="fsp-only-light" :src="logoLight" :alt="logoAlt">
      <span v-if="product" class="fsp-header-product">{{ product }}</span>
    </NuxtLink>
    <nav ref="nav" class="fsp-header-nav" aria-label="Основная навигация">
      <NuxtLink v-for="l in links" :key="l.label" :to="l.href || '/'" :aria-current="isActive(l) ? 'page' : undefined">{{ l.label }}</NuxtLink>
    </nav>
    <div ref="actions" class="fsp-header-actions">
      <slot name="actions">
        <FspButton variant="ghost" :icon="theme === 'light' ? 'moon' : 'sun'" :aria-label="theme === 'light' ? 'Тёмная тема' : 'Светлая тема'" @click="toggleTheme" />
        <span v-if="user" class="fsp-header-bell fsp-menu-anchor">
          <FspButton variant="ghost" icon="bell" :aria-label="notes.unread.value ? `Уведомления: ${notes.unread.value} новых` : 'Уведомления'" :aria-expanded="menu === 'bell'" @click.stop="toggle('bell')" />
          <i v-if="notes.unread.value" aria-hidden="true" />
          <div v-if="menu === 'bell'" class="fsp-menu fsp-cut" role="menu">
            <div class="fsp-menu-title">Уведомления</div>
            <div v-if="!notes.loaded.value" class="fsp-menu-item u-muted">Загружаем…</div>
            <div v-else-if="!notes.items.value.length" class="fsp-menu-item u-muted">Новых событий нет</div>
            <NuxtLink v-for="n in notes.items.value" :key="n.id" :to="n.to" class="fsp-menu-item" role="menuitem">
              {{ n.text }}<span v-if="n.at" class="fsp-menu-when">{{ whenLabel(n.at) }}</span>
            </NuxtLink>
          </div>
        </span>
        <span v-if="user" class="fsp-menu-anchor">
          <FspButton variant="outline" size="sm" icon="user" :aria-expanded="menu === 'user'" @click.stop="toggle('user')"><span class="fsp-user-name">{{ user }}</span></FspButton>
          <div v-if="menu === 'user'" class="fsp-menu fsp-cut" role="menu">
            <NuxtLink v-for="m in userMenu" :key="m.to" :to="m.to" class="fsp-menu-item" role="menuitem">{{ m.label }}</NuxtLink>
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
.fsp-menu { --cut: var(--cut-m); --fill: var(--gray-bright); --edge: var(--line-strong); --bw: 1px; position: absolute; top: calc(100% + 8px); right: 0; z-index: 50; min-width: 300px; max-width: 380px; padding: 8px 0; display: flex; flex-direction: column; }
[data-theme="light"] .fsp-menu { --fill: #ffffff; }
.fsp-menu-title { padding: 8px 16px 10px; font-size: 12px; font-weight: 600; letter-spacing: .06em; text-transform: uppercase; color: var(--text-muted); }
.fsp-menu-item { padding: 10px 16px; font: 500 14px/20px var(--font-sans); color: var(--text); text-decoration: none; display: block; }
.fsp-menu-item:hover { background: var(--surface-hover); color: var(--text); }
.fsp-menu-when { display: block; font-size: 12px; color: var(--text-muted); margin-top: 2px; }
@media (max-width: 640px) { .fsp-user-name { display: none; } }
</style>
