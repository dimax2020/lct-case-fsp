<script setup lang="ts">
useHead({ title: 'Тестовые задания — Карьера ФСП' })
const cabinetUser = useCabinetUser('Кандидат')
</script>

<template>
  <div style="background: var(--bg); color: var(--text); font-family: var(--font-sans); min-height: 100vh;">
    <FspHeader product="Карьера" :user="cabinetUser" :links="candidateLinks" />
    <main style="max-width: 1240px; margin: 0 auto; padding: 40px 32px 64px;">
      <h1 class="fsp-display" style="font-size: 40px; line-height: 44px; margin-bottom: 8px;">Тестовые задания</h1>
      <p style="margin: 0 0 28px; color: var(--text-muted);">После отклика на вакансию здесь открывается задание: его нужно выполнить и ответить на вопросы.</p>
      <ProcessDesk role="candidate" />
    </main>
  </div>
</template>
