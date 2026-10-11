// https://nuxt.com/docs/api/configuration/nuxt-config
const publicBase = process.env.KEYCLOAK_PUBLIC_BASE || 'http://localhost/auth'
const internalBase = (process.env.KEYCLOAK_INTERNAL_BASE || publicBase).replace(/\/$/, '')
const browserOrigin = process.env.NUXT_PUBLIC_SITE_ORIGIN || 'http://localhost'

export default defineNuxtConfig({
  compatibilityDate: '2025-07-15',
  devtools: { enabled: false },
  modules: ['nuxt-oidc-auth'],
  css: ['~/assets/css/tokens.css', '~/assets/css/fsp.css', '~/assets/css/ui.css', '~/assets/css/landing.css', '~/assets/css/app.css'],
  app: {
    head: {
      htmlAttrs: { lang: 'ru' },
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
  },
  runtimeConfig: {
    apiProxyTarget: process.env.API_PROXY_TARGET || 'http://127.0.0.1:8000',
    epaProxyTarget: process.env.EPA_INTERNAL_URL || 'http://127.0.0.1:8080',
    keycloakInternalBase: internalBase,
    keycloakClientId: process.env.KEYCLOAK_CLIENT_ID || 'career-web',
    keycloakClientSecret: process.env.KEYCLOAK_CLIENT_SECRET || 'change-me',
    keycloakRealm: 'fsp'
  },
  oidc: {
    defaultProvider: 'keycloak',
    providers: {
      keycloak: {
        clientId: process.env.KEYCLOAK_CLIENT_ID || 'career-web',
        clientSecret: process.env.KEYCLOAK_CLIENT_SECRET || 'change-me',
        audience: 'career-web',
        baseUrl: `${publicBase.replace(/\/$/, '')}/realms/fsp`,
        redirectUri: process.env.NUXT_OIDC_PROVIDERS_KEYCLOAK_REDIRECT_URI || `${browserOrigin}/auth/keycloak/callback`,
        logoutRedirectUri: process.env.NUXT_OIDC_PROVIDERS_KEYCLOAK_LOGOUT_REDIRECT_URI || `${browserOrigin}/`,
        authorizationUrl: `${publicBase.replace(/\/$/, '')}/realms/fsp/protocol/openid-connect/auth`,
        tokenUrl: `${internalBase}/realms/fsp/protocol/openid-connect/token`,
        userInfoUrl: `${internalBase}/realms/fsp/protocol/openid-connect/userinfo`,
        logoutUrl: `${publicBase.replace(/\/$/, '')}/realms/fsp/protocol/openid-connect/logout`,
        openIdConfiguration: `${internalBase}/realms/fsp/.well-known/openid-configuration`,
        pkce: true,
        // Демо-вход: /auth/keycloak/login?login_hint=… подставляет почту на странице ФСП ID.
        allowedClientAuthParameters: ['login_hint'],
        scope: ['openid', 'profile', 'email'],
        tokenValidationMode: 'strict',
        validateAccessToken: true,
        validateIdToken: false,
        exposeAccessToken: false,
        exposeIdToken: false,
        optionalClaims: ['sub', 'email', 'realm_access'],
        userNameClaim: 'preferred_username'
      }
    },
    session: {
      automaticRefresh: true,
      expirationCheck: true,
      cookie: {
        sameSite: 'lax',
        secure: publicBase.startsWith('https')
      }
    },
    middleware: {
      globalMiddlewareEnabled: false
    }
  },
  nitro: {
    storage: {
      oidc: {
        driver: 'redis',
        base: 'oidc',
        url: process.env.REDIS_URL || 'redis://127.0.0.1:6379/0'
      }
    }
  }
})
