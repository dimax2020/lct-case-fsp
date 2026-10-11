<script setup lang="ts">
withDefaults(defineProps<{ status?: 'new' | 'review' | 'invite' | 'offer' | 'reject' | 'archived' }>(), { status: 'review' })
const STATUS: Record<string, string> = { new: 'Новый отклик', review: 'На рассмотрении', invite: 'Приглашение', offer: 'Оффер', reject: 'Отказ', archived: 'В архиве' }
</script>

<template>
  <span :class="['fsp-status', 'fsp-status-' + status]"><span class="fsp-status-dot" aria-hidden="true" /><slot>{{ STATUS[status] }}</slot></span>
</template>
