<script setup lang="ts">
const { items } = useToast()
</script>

<template>
  <div class="fsp-toaster" aria-live="polite">
    <TransitionGroup name="fsp-toast">
      <div v-for="t in items" :key="t.id" class="fsp-toast fsp-cut">
        <FspIcon name="check" /><span>{{ t.text }}</span>
      </div>
    </TransitionGroup>
  </div>
</template>

<style>
.fsp-toaster { position: fixed; right: 24px; bottom: 24px; z-index: 100; display: flex; flex-direction: column; gap: 8px; pointer-events: none; }
.fsp-toast { --cut: var(--cut-m); --fill: var(--plate); color: var(--on-plate); display: flex; gap: 10px; align-items: center; padding: 14px 20px; font: 500 15px/20px var(--font-sans); max-width: 380px; }
.fsp-toast .fsp-icon { color: var(--active-success); font-size: 20px; flex: none; }
.fsp-toast-enter-active, .fsp-toast-leave-active { transition: opacity .2s, transform .2s; }
.fsp-toast-enter-from, .fsp-toast-leave-to { opacity: 0; transform: translateY(8px); }
</style>
