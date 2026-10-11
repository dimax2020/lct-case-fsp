<script setup lang="ts">
useHead({ title: 'Тестовые задания — Карьера ФСП' })
const cabinetUser = useCabinetUser('Кандидат')
</script>

<template>
  <div class="fsp-shell">
    <FspHeader product="Карьера" :user="cabinetUser" :links="candidateLinks" />
    <main class="fsp-page">
      <h1 class="fsp-display fsp-title">Тестовые задания</h1>
      <p style="margin: 0 0 28px; color: var(--text-muted);">Задание появляется здесь, когда вы приняли приглашение, к которому работодатель приложил тест.</p>
      <ProcessDesk role="candidate" />
    </main>
  </div>
</template>
