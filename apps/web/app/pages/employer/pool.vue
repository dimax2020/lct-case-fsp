<script setup lang="ts">
useHead({ title: 'Подборка кандидатов — Карьера ФСП' })

const links = [
  { label: 'Подборка', href: '/employer/need' },
  { label: 'Банк кандидатов', href: '/employer/pool' },
  { label: 'Приглашения', href: '/employer/invites' },
  { label: 'Вакансии', href: '#' },
  { label: 'Компания', href: '/employer/company' }
]

interface Cand {
  id: number; name: string; full: string; meta: string; cat: string; match: number; score: number
  badge?: { disc: string; text: string }; why: string[]; status: 'none' | 'viewed' | 'sent'
  kafka: boolean; fintech: boolean; active: boolean; remote: boolean; city: string; stack: string[]; saved: boolean; inPool: boolean
}
const cands = ref<Cand[]>([
  { id: 1, name: 'Алексей К.', full: 'Алексей Кузнецов', meta: 'Backend · Middle · опыт 4 года · Новосибирск', cat: 'bm', match: 94, score: 82,
    badge: { disc: 'algo', text: 'ФСП · 2 место ЧР-2025' }, status: 'none', kafka: true, fintech: true, active: true, remote: true, city: 'Новосибирск', stack: ['go', 'postgresql', 'kafka'], saved: true, inPool: true,
    why: ['Тест Middle: 82/100, место 12 из 340 в категории', 'Стек совпадает 4 из 4: Go 88, PostgreSQL 81, Kafka, конкурентность 76', 'Призёр Чемпионата России по алгоритмическому программированию'] },
  { id: 2, name: 'Мария С.', full: 'Мария Соколова', meta: 'Backend · Middle · опыт 3 года · Казань', cat: 'bm', match: 89, score: 79,
    badge: { disc: 'infosec', text: 'ФСП · финал Кубка-2024' }, status: 'viewed', kafka: false, fintech: true, active: true, remote: true, city: 'Казань', stack: ['go', 'postgresql'], saved: false, inPool: true,
    why: ['Тест Middle: 79/100 · свежее задание по антифроду 5 дней назад', 'Стек 3 из 4: нет подтверждённого Kafka', 'Финалист Кубка России по инфобезопасности — плюс для антифрода'] },
  { id: 3, name: 'Игорь Л.', full: 'Игорь Лебедев', meta: 'Backend · Middle · опыт 5 лет · Москва', cat: 'bm', match: 86, score: 90,
    status: 'none', kafka: true, fintech: true, active: false, remote: true, city: 'Москва', stack: ['go', 'postgresql', 'kafka', 'grpc'], saved: false, inPool: true,
    why: ['Лучший тест в категории: 90/100 — компенсирует отсутствие соревнований', 'Стек 4 из 4, 3 года в платёжных системах'] },
  { id: 4, name: 'Екатерина В.', full: 'Екатерина Волкова', meta: 'Backend · Middle · опыт 2 года · Новосибирск', cat: 'bm', match: 72, score: 71,
    badge: { disc: 'product', text: 'ФСП · полуфинал ЧР-2025' }, status: 'none', kafka: false, fintech: false, active: true, remote: false, city: 'Новосибирск', stack: ['go', 'redis'], saved: false, inPool: false,
    why: ['Тест Middle: 71/100', 'Стек 2 из 4: Go, Redis', 'Хакатон ФСП по продуктовому программированию'] },
  { id: 5, name: 'Олег Н.', full: 'Олег Николаев', meta: 'Backend · Senior · опыт 8 лет · Екатеринбург', cat: 'bs', match: 91, score: 88,
    badge: { disc: 'algo', text: 'ФСП · КМС' }, status: 'sent', kafka: true, fintech: true, active: true, remote: true, city: 'Екатеринбург', stack: ['go', 'postgresql', 'kafka'], saved: true, inPool: true,
    why: ['Тест Senior: 88/100', 'Вёл антифрод в банке 3 года', 'Ожидания выше вилки на 15%'] },
  { id: 6, name: 'Дина Р.', full: 'Дина Рахимова', meta: 'Fullstack · Middle · опыт 4 года · Уфа', cat: 'fm', match: 78, score: 80,
    status: 'none', kafka: false, fintech: true, active: true, remote: true, city: 'Уфа', stack: ['go', 'vue', 'postgresql'], saved: false, inPool: true,
    why: ['Тест Fullstack Middle: 80/100', 'Go на бэкенде, 40% стека совпадает', 'Финтех 2 года'] }
])

const cats = [
  { id: 'bm', title: 'Backend · Middle', sub: '340 кандидатов · совпадение 94%' },
  { id: 'bs', title: 'Backend · Senior', sub: '118 кандидатов · выше вилки' },
  { id: 'fm', title: 'Fullstack · Middle', sub: '205 кандидатов · смежная' }
]
const cat = ref('bm')
const tab = ref('pool')
const { show } = useToast()

// фильтры сайдбара
const onlyFsp = ref(false)
const discs = reactive({ algo: false, product: false, infosec: false })
const minScore = ref<string | number>('70')
const stackQ = ref('')
const remote = ref(true)
const nsk = ref(false)
const fresh = ref(false)

// подсказки топ-3
const hints = reactive([
  { id: 'kafka', title: 'Kafka — только подтверждённая тестом', to: 9, note: 'Среднее соответствие вырастет с 89% до 95%', on: false },
  { id: 'fintech', title: 'Опыт в финтехе от 1 года', to: 11, note: 'В описании команды — платёжный процессинг', on: false },
  { id: 'active', title: 'Активен в последние 14 дней', to: 13, note: 'Такие кандидаты принимают приглашения в 2 раза чаще', on: false }
])
function toggleHint(h: typeof hints[number]) {
  h.on = !h.on
  show(h.on ? `Уточнение «${h.title}» применено` : 'Уточнение снято, подборка восстановлена')
}

const list = computed(() => cands.value.filter((c) => {
  if (tab.value === 'saved' && !c.saved) return false
  if (tab.value === 'pool' && (!c.inPool || c.cat !== cat.value)) return false
  if (onlyFsp.value && !c.badge) return false
  const picked = Object.entries(discs).filter(([, on]) => on).map(([k]) => k)
  if (picked.length && (!c.badge || !picked.includes(c.badge.disc))) return false
  if (Number(minScore.value) && c.score < Number(minScore.value)) return false
  const q = stackQ.value.toLowerCase().split(/[,\s]+/).filter(Boolean)
  if (q.length && !q.every(t => c.stack.some(s => s.includes(t)))) return false
  if (remote.value && !nsk.value && !c.remote) return false
  if (nsk.value && !remote.value && c.city !== 'Новосибирск') return false
  if (fresh.value && !c.active) return false
  for (const h of hints) {
    if (!h.on) continue
    if (h.id === 'kafka' && !c.kafka) return false
    if (h.id === 'fintech' && !c.fintech) return false
    if (h.id === 'active' && !c.active) return false
  }
  return true
}))
const applied = computed(() => hints.filter(h => h.on))
const total = computed(() => (applied.value.length ? Math.max(4, Math.min(...applied.value.map(h => h.to)) - (applied.value.length - 1) * 3) : 24))
const tabs = computed(() => [
  { value: 'pool', label: 'Подборка', count: total.value },
  { value: 'bank', label: 'Весь банк', count: 1248 },
  { value: 'saved', label: 'Избранные', count: cands.value.filter(c => c.saved).length }
])
const refines = computed(() => {
  const r: { label: string; off: () => void }[] = []
  if (onlyFsp.value) r.push({ label: 'Есть ФСП', off: () => { onlyFsp.value = false } })
  if (Number(minScore.value)) r.push({ label: `Тест от ${minScore.value}`, off: () => { minScore.value = '' } })
  if (remote.value) r.push({ label: 'Удалённо', off: () => { remote.value = false } })
  if (nsk.value) r.push({ label: 'Новосибирск', off: () => { nsk.value = false } })
  if (fresh.value) r.push({ label: 'Актуальный профиль', off: () => { fresh.value = false } })
  for (const h of applied.value) r.push({ label: h.title.split(' — ')[0]!, off: () => { h.on = false } })
  return r
})
function invite(c: Cand) {
  if (c.id === 1) { navigateTo('/employer/candidate'); return }
  c.status = 'sent'
  show(`Приглашение отправлено: ${c.name}`)
}
function toggleSave(c: Cand) {
  c.saved = !c.saved
  show(c.saved ? `${c.name} — в избранном` : `${c.name} убран(а) из избранного`)
}
const catStyle = (on: boolean) => on
  ? '--cut: var(--cut-m); padding: 16px 20px; text-align: left; cursor: pointer; font: inherit; min-width: 220px; border: 0;'
  : '--cut: var(--cut-m); --fill: var(--surface); --edge: var(--line-strong); --bw: 1px; color: var(--text); padding: 16px 20px; text-align: left; cursor: pointer; font: inherit; min-width: 220px; border: 0; background: none;'
const barColor = (n: number) => (n >= 80 ? 'var(--success)' : n >= 50 ? 'var(--warning)' : 'var(--danger)')
</script>

<template>
  <div style="background: var(--bg); color: var(--text); font-family: var(--font-sans); min-height: 100vh;">
    <FspHeader product="Для компаний" user="Код Сибири" :links="links" />

    <main style="max-width: 1240px; margin: 0 auto; padding: 40px 32px 64px;">
      <div style="display: flex; flex-wrap: wrap; justify-content: space-between; gap: 16px; align-items: flex-end; margin-bottom: 24px;">
        <div>
          <div style="font-size: 12px; font-weight: 600; letter-spacing: .06em; text-transform: uppercase; color: var(--text-muted); margin-bottom: 8px;">Подборка по описанию от 10.10</div>
          <h1 class="fsp-display" style="font-size: 36px; line-height: 40px;">Backend в процессинг платежей</h1>
        </div>
        <FspButton variant="outline" size="sm" href="/employer/need">Изменить описание</FspButton>
      </div>

      <FspTabs v-model="tab" :items="tabs" />

      <section v-if="tab === 'pool'" style="display: flex; flex-wrap: wrap; gap: 12px; margin: 24px 0;">
        <button v-for="c in cats" :key="c.id" type="button" :class="['fsp-cut', cat === c.id && 'fsp-active']" :style="catStyle(cat === c.id)" :aria-pressed="cat === c.id" @click="cat = c.id">
          <span style="display: block; font-weight: 600;">{{ c.title }}</span>
          <span :style="{ display: 'block', fontSize: '13px', marginTop: '4px', color: cat === c.id ? undefined : 'var(--text-muted)' }">{{ c.sub }}</span>
        </button>
      </section>
      <div v-else style="height: 24px" />

      <div style="display: flex; flex-wrap: wrap; gap: 32px; align-items: flex-start;">
        <aside style="flex: 1 1 260px; min-width: 0; padding: 0 24px 0 0; box-shadow: inset -1px 0 0 var(--line); display: flex; flex-direction: column; gap: 22px;">
          <div class="fsp-display" style="font-size: 18px; line-height: 22px;">Уточнить</div>
          <div style="display: flex; flex-direction: column; gap: 2px;">
            <div style="font-size: 12px; font-weight: 600; letter-spacing: .06em; text-transform: uppercase; color: var(--text-muted); margin-bottom: 6px;">Достижения ФСП</div>
            <FspCheckbox v-model="onlyFsp" label="Только с достижениями" :count="62" />
            <FspCheckbox v-model="discs.algo" label="Алгоритмическое" swatch="algo" />
            <FspCheckbox v-model="discs.product" label="Продуктовое" swatch="product" />
            <FspCheckbox v-model="discs.infosec" label="Инфобезопасность" swatch="infosec" />
          </div>
          <FspInput v-model="minScore" label="Тест не ниже" suffix="баллов" inputmode="numeric" />
          <FspInput v-model="stackQ" label="Стек" icon="search" placeholder="Kafka, gRPC…" />
          <div>
            <div style="font-size: 12px; font-weight: 600; letter-spacing: .06em; text-transform: uppercase; color: var(--text-muted); margin-bottom: 8px;">Формат</div>
            <div style="display: flex; flex-wrap: wrap; gap: 8px;"><FspChip v-model:selected="remote">Удалённо</FspChip><FspChip v-model:selected="nsk">Новосибирск</FspChip></div>
          </div>
          <FspCheckbox v-model="fresh" label="Актуальный профиль (задания за 30 дней)" />
        </aside>

        <section style="flex: 999 1 640px; min-width: 0; display: flex; flex-direction: column; gap: 16px;">
          <section v-if="tab === 'pool'" aria-label="Подсказки, как сузить подборку" class="fsp-cut" style="--cut: var(--cut-l); --fill: var(--surface); --edge: var(--accent-mark); --bw: var(--border-card); padding: 24px;">
            <div style="display: flex; flex-wrap: wrap; justify-content: space-between; gap: 8px 16px; align-items: baseline; margin-bottom: 16px;">
              <div style="display: flex; gap: 10px; align-items: center;"><span style="color: var(--accent-mark);"><FspIcon name="filter" /></span><h2 class="fsp-display" style="font-size: 18px; line-height: 22px;">Как сузить подборку · топ-3</h2></div>
              <span style="font-size: 13px; color: var(--text-muted);">Сейчас {{ total }} кандидатов · рассчитано по вашему описанию</span>
            </div>
            <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 200px), 1fr)); gap: 12px;">
              <div v-for="(h, i) in hints" :key="h.id" class="fsp-cut" style="--cut: var(--cut-m); --fill: var(--surface-hover); padding: 18px; display: flex; flex-direction: column; gap: 8px;">
                <span class="fsp-display" style="font-size: 13px; color: #ffffff; background: var(--accent-mark); width: 34px; height: 24px; display: inline-grid; place-items: center;">0{{ i + 1 }}</span>
                <b style="font-size: 15px; line-height: 20px;">{{ h.title }}</b>
                <span class="fsp-display" style="font-size: 24px; line-height: 28px;">24 → {{ h.to }}</span>
                <span style="font-size: 13px; line-height: 18px; color: var(--text-muted);">{{ h.note }}</span>
                <FspButton size="sm" :variant="h.on ? 'primary' : 'outline'" :icon="h.on ? 'check' : undefined" style="margin-top: auto;" @click="toggleHint(h)">{{ h.on ? 'Применено' : 'Применить' }}</FspButton>
              </div>
            </div>
          </section>

          <div style="display: flex; flex-wrap: wrap; gap: 8px; align-items: center; font-size: 14px;">
            <span style="color: var(--text-muted);">Уточнения:</span>
            <span v-if="!refines.length" style="color: var(--text-muted);">нет</span>
            <button v-for="r in refines" :key="r.label" type="button" style="all: unset; cursor: pointer;" :aria-label="'Снять ' + r.label" @click="r.off()"><FspTag>{{ r.label }} ×</FspTag></button>
            <span style="margin-left: auto; color: var(--text-muted);">{{ tab === 'pool' ? `${total} из 340 · исходная подборка сохранена` : tab === 'bank' ? 'Весь банк · 1 248 кандидатов' : 'Ваши избранные' }}</span>
          </div>

          <p v-if="!list.length" style="margin: 0; padding: 32px 0; box-shadow: inset 0 1px 0 var(--line); color: var(--text-muted); font-size: 15px;">Под эти условия никто не подходит — снимите часть уточнений.</p>

          <article v-for="(c, i) in list" :key="c.id" style="padding: 24px 0; box-shadow: inset 0 1px 0 var(--line); display: flex; flex-wrap: wrap; gap: 24px;">
            <div class="fsp-display" style="font-size: 28px; line-height: 32px; width: 48px; color: var(--text-muted);">{{ String(i + 1).padStart(2, '0') }}</div>
            <div style="flex: 999 1 380px; min-width: 0; display: flex; flex-direction: column; gap: 14px;">
              <div style="display: flex; flex-wrap: wrap; gap: 12px; align-items: center;">
                <FspCompanyLogo :name="c.full" :size="48" />
                <div><div style="font-size: 18px; font-weight: 600;">{{ c.name }}</div><div style="font-size: 14px; color: var(--text-muted);">{{ c.meta }}</div></div>
                <FspDisciplineBadge v-if="c.badge" :discipline="c.badge.disc">{{ c.badge.text }}</FspDisciplineBadge>
                <FspTag v-else>Нет истории ФСП</FspTag>
              </div>
              <div style="display: grid; grid-template-columns: 140px 1fr 44px; gap: 12px; align-items: center; font-size: 14px;"><span style="color: var(--text-muted);">Соответствие</span><div style="height: 8px; background: var(--surface-hover);"><div :style="{ width: c.match + '%', height: '8px', background: barColor(c.match) }" /></div><b>{{ c.match }}%</b></div>
              <div style="font-size: 14px; line-height: 20px;">
                <div style="font-size: 12px; font-weight: 600; letter-spacing: .06em; text-transform: uppercase; color: var(--text-muted); margin-bottom: 6px;">Почему в подборке</div>
                <ul style="margin: 0; padding: 0 0 0 18px; display: flex; flex-direction: column; gap: 4px;">
                  <li v-for="w in c.why" :key="w">{{ w }}</li>
                </ul>
              </div>
            </div>
            <div style="flex: 1 1 200px; display: flex; flex-direction: column; gap: 8px; justify-content: space-between;">
              <div style="display: flex; justify-content: space-between; align-items: center; gap: 8px;">
                <FspStatusBadge v-if="c.status === 'viewed'" status="review">Приглашение просмотрено</FspStatusBadge>
                <FspStatusBadge v-else-if="c.status === 'sent'" status="new">Приглашение отправлено</FspStatusBadge>
                <span v-else style="display: flex; gap: 8px; align-items: center; font-size: 13px; color: var(--text-muted);"><FspIcon name="user" />Контакты — после принятия</span>
                <FspButton variant="ghost" size="sm" :icon="c.saved ? 'bookmark-fill' : 'bookmark'" :aria-label="c.saved ? 'Убрать из избранного' : 'В избранное'" :aria-pressed="c.saved" @click="toggleSave(c)" />
              </div>
              <div style="display: flex; flex-direction: column; gap: 8px;">
                <template v-if="c.status === 'none'">
                  <FspButton :block="true" @click="invite(c)">Пригласить</FspButton>
                  <FspButton :block="true" variant="ghost" size="sm" href="/employer/candidate">Открыть профиль</FspButton>
                </template>
                <FspButton v-else :block="true" variant="ghost" size="sm" href="/employer/invites">К приглашению</FspButton>
              </div>
            </div>
          </article>
        </section>
      </div>
    </main>
  </div>
</template>
