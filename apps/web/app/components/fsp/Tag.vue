<script setup lang="ts">
defineProps<{ match?: boolean }>()
</script>

<template>
  <span :class="['fsp-tag', match && 'fsp-tag-match']" :title="match ? 'Есть в вашем профиле' : undefined"><slot /></span>
</template>
