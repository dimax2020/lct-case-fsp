// https://nuxt.com/docs/api/configuration/nuxt-config
export default defineNuxtConfig({
  compatibilityDate: '2025-07-15',
  devtools: { enabled: false },
  css: ['~/assets/css/tokens.css', '~/assets/css/fsp.css', '~/assets/css/app.css'],
  app: {
    head: {
      htmlAttrs: { lang: 'ru', 'data-theme': 'dark' },
      title: 'Карьера ФСП — покажи, что ты лучший',
      meta: [
        { name: 'viewport', content: 'width=device-width, initial-scale=1' },
        { name: 'description', content: 'Платформа подбора ИТ-специалистов Федерации спортивного программирования: работодатель приходит к лучшим.' }
      ],
      link: [
        { rel: 'icon', type: 'image/svg+xml', href: '/brand/fsp-star-dark.svg' },
        { rel: 'preload', as: 'font', type: 'font/woff2', href: '/fonts/Inter-Regular.woff2', crossorigin: '' },
        { rel: 'preload', as: 'font', type: 'font/woff2', href: '/fonts/Wadik-Bold.woff2', crossorigin: '' }
      ]
    }
  }
})
