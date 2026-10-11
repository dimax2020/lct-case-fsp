<script setup lang="ts">
export type MapNode = {
  id: string
  label: string
  title: string
  status: 'held' | 'review' | 'current' | 'ahead' | 'aside'
  order: number | null
}
export type MapGap = { label: string; title: string; items: string[] }

const props = withDefaults(defineProps<{
  nodes: MapNode[]
  review?: MapGap[]
  specialization?: string
  showReview?: boolean
}>(), { review: () => [], showReview: false, specialization: 'backend' })

const statusLabel: Record<MapNode['status'], string> = {
  held: 'Держится',
  review: 'Повторить',
  current: 'Сейчас',
  ahead: 'Ещё в этой попытке',
  aside: 'Не выпало',
}
const source = computed(() => props.specialization === 'frontend'
  ? { href: 'https://roadmap.sh/frontend', name: 'frontend' }
  : { href: 'https://roadmap.sh/backend', name: 'backend' })
const legend = computed(() => (Object.keys(statusLabel) as MapNode['status'][]).filter(status => props.nodes.some(node => node.status === status)))
</script>

<template>
  <div class="rmap-layout" :class="{ 'rmap-layout-review': showReview }">
    <section class="rmap-map" aria-label="Карта тем">
      <div class="rmap-head">
        <div class="rmap-kicker">Карта {{ source.name }}</div>
        <a class="fsp-link" :href="source.href" target="_blank" rel="noopener">roadmap.sh</a>
      </div>
      <ol class="rmap">
        <li v-for="node in nodes" :key="node.id" class="rmap-node" :data-status="node.status">
          <span class="rmap-mark" aria-hidden="true" />
          <div class="fsp-cut rmap-card">
            <div class="rmap-row">
              <span class="rmap-status">{{ statusLabel[node.status] }}</span>
              <span v-if="node.order" class="rmap-order">{{ node.order }}</span>
            </div>
            <div class="rmap-label">{{ node.label }}</div>
            <p class="rmap-title">{{ node.title }}</p>
          </div>
        </li>
      </ol>
      <ul class="rmap-legend">
        <li v-for="status in legend" :key="status"><i :data-status="status" /> {{ statusLabel[status].toLowerCase() }}</li>
      </ul>
    </section>

    <section v-if="showReview" class="rmap-review" aria-label="Что повторить">
      <div class="rmap-kicker">К следующей попытке</div>
      <h2 class="rmap-review-title">Что повторить</h2>
      <p v-if="!review.length" class="rmap-empty">По темам этой попытки дыр нет. Серые узлы на карте не выпали — в следующий раз вопросы могут прийти оттуда.</p>
      <article v-for="gap in review" :key="gap.label" class="fsp-cut rmap-gap">
        <div class="rmap-status">{{ gap.label }}</div>
        <p class="rmap-gap-title">{{ gap.title }}</p>
        <ul>
          <li v-for="item in gap.items" :key="item">{{ item }}</li>
        </ul>
      </article>
    </section>
  </div>
</template>

<style scoped>
.rmap-layout { display: flex; flex-direction: column; gap: 28px; }
.rmap-layout-review { display: grid; grid-template-columns: minmax(0, 1.1fr) minmax(280px, .9fr); gap: 28px; align-items: start; }
.rmap-head, .rmap-row { display: flex; justify-content: space-between; align-items: baseline; gap: 12px; }
.rmap-kicker, .rmap-status {
  font-size: 12px; font-weight: 600; letter-spacing: .06em; text-transform: uppercase; color: var(--text-muted);
}
.rmap-map { min-width: 0; }
.rmap {
  list-style: none; margin: 18px 0 0; padding: 0;
  display: flex; flex-direction: column; gap: 14px; position: relative;
}
.rmap::before {
  content: ""; position: absolute; left: 11px; top: 28px; bottom: 28px; width: 2px; background: var(--line-strong);
}
.rmap-node { display: grid; grid-template-columns: 24px minmax(0, 1fr); gap: 16px; align-items: start; }
.rmap-mark {
  width: 12px; height: 12px; margin: 22px auto 0; background: var(--line-strong); transform: rotate(45deg); position: relative; z-index: 1;
}
.rmap-card { --cut: var(--cut-s); --bw: 1px; --edge: var(--line-strong); --fill: var(--surface); padding: 14px 16px 16px; min-width: 0; }
.rmap-label { font-family: var(--font-display); font-weight: 700; font-size: 22px; line-height: 26px; margin-top: 4px; }
.rmap-title { margin: 6px 0 0; font-size: 14px; line-height: 20px; color: var(--text-muted); }
.rmap-order { font-size: 12px; font-weight: 700; color: var(--text-muted); }
.rmap-node[data-status="current"] .rmap-mark { background: var(--primary); }
.rmap-node[data-status="current"] .rmap-card { --fill: var(--primary); --edge: var(--primary); color: var(--on-primary); }
.rmap-node[data-status="current"] .rmap-status,
.rmap-node[data-status="current"] .rmap-title,
.rmap-node[data-status="current"] .rmap-order { color: var(--on-primary); opacity: .82; }
.rmap-node[data-status="held"] .rmap-mark { background: var(--success); }
.rmap-node[data-status="held"] .rmap-card { --edge: var(--success); --bw: 1.5px; }
.rmap-node[data-status="review"] .rmap-mark { background: var(--warning); }
.rmap-node[data-status="review"] .rmap-card { --edge: var(--warning); --bw: 1.5px; }
.rmap-node[data-status="review"] .rmap-status { color: var(--warning); }
.rmap-node[data-status="aside"] .rmap-card { opacity: .62; }
.rmap-node[data-status="ahead"] .rmap-mark { background: transparent; box-shadow: inset 0 0 0 1.5px var(--line-strong); }
.rmap-legend { display: flex; flex-wrap: wrap; gap: 14px 18px; margin: 16px 0 0; padding: 0; list-style: none; font-size: 13px; color: var(--text-muted); }
.rmap-legend li { display: inline-flex; align-items: center; gap: 8px; }
.rmap-legend i { width: 8px; height: 8px; transform: rotate(45deg); background: var(--line-strong); }
.rmap-legend i[data-status="current"] { background: var(--primary); }
.rmap-legend i[data-status="held"] { background: var(--success); }
.rmap-legend i[data-status="review"] { background: var(--warning); }
.rmap-legend i[data-status="aside"] { background: transparent; box-shadow: inset 0 0 0 1.5px var(--line-strong); }
.rmap-review-title { font-family: var(--font-display); font-size: 32px; line-height: 36px; margin: 8px 0 16px; }
.rmap-empty { margin: 0; color: var(--text-muted); line-height: 24px; }
.rmap-gap { --cut: var(--cut-m); --bw: 1px; --edge: var(--warning); --fill: var(--surface); padding: 16px 18px 18px; margin-top: 12px; }
.rmap-gap-title { margin: 6px 0 10px; font-weight: 600; line-height: 22px; }
.rmap-gap ul { margin: 0; padding: 0; list-style: none; display: flex; flex-direction: column; gap: 8px; }
.rmap-gap li { padding-left: 14px; position: relative; font-size: 14px; line-height: 20px; color: var(--text-muted); }
.rmap-gap li::before { content: ""; position: absolute; left: 0; top: 7px; width: 6px; height: 6px; background: var(--warning); transform: rotate(45deg); }
@media (max-width: 860px) {
  .rmap-layout-review { grid-template-columns: 1fr; }
}
</style>
