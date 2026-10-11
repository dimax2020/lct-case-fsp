<script setup lang="ts">
import { safeReturnPath } from '~/utils/epa'

useHead({ title: 'Тестовые задания — Карьера ФСП' })
const cabinetUser = useCabinetUser('Компания')
const route = useRoute()
const back = computed(() => safeReturnPath(route.query.return))
</script>

<template>
  <div class="fsp-shell">
    <FspHeader product="Для компаний" :user="cabinetUser" :links="employerLinks" />
    <main class="fsp-page">
      <h1 class="fsp-display fsp-title">Тестовые задания</h1>
      <p style="margin: 0 0 16px; color: var(--text-muted);">Создайте задание здесь, затем откройте кандидата и прикрепите его к приглашению. Кандидат увидит задание только после принятия.</p>
      <p v-if="back" class="u-note" style="margin: 0 0 20px;">После создания вернитесь к приглашению и выберите это задание в шаге 2.</p>
      <div v-if="back" style="margin-bottom: 24px;"><FspButton :href="back">Вернуться к приглашению</FspButton></div>
      <ProcessDesk role="employer" />
    </main>
  </div>
</template>
