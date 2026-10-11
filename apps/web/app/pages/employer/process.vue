<script setup lang="ts">
useHead({ title: 'Тестовые задания — Карьера ФСП' })
const cabinetUser = useCabinetUser('Компания')
</script>

<template>
  <div style="background: var(--bg); color: var(--text); font-family: var(--font-sans); min-height: 100vh;">
    <FspHeader product="Для компаний" :user="cabinetUser" :links="employerLinks" />
    <main style="max-width: 1240px; margin: 0 auto; padding: 40px 32px 64px;">
      <h1 class="fsp-display" style="font-size: 40px; line-height: 44px; margin-bottom: 8px;">Тестовые задания</h1>
      <p style="margin: 0 0 28px; color: var(--text-muted);">Загрузите проект или ТЗ, либо сгенерируйте описание и ТЗ. Затем выберите вакансию и смотрите, кто что выполнил.</p>
      <ProcessDesk role="employer" />
    </main>
  </div>
</template>
