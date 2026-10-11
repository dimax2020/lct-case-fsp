# Production-сборка Nuxt для Coolify. Контекст сборки — корень репозитория.
# Публичный адрес стенда нужен уже на этапе сборки: от него зависят secure-cookie сессии
# и адреса ФСП ID, поэтому PUBLIC_URL передаётся как build-arg.
FROM node:22-alpine AS build
WORKDIR /app

COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm ci

COPY apps/web/ ./

ARG PUBLIC_URL=http://localhost
ENV NUXT_PUBLIC_API_MOCKS=0 \
    NUXT_PUBLIC_SITE_ORIGIN=${PUBLIC_URL} \
    KEYCLOAK_PUBLIC_BASE=${PUBLIC_URL}/auth \
    KEYCLOAK_INTERNAL_BASE=http://keycloak:8080/auth \
    NUXT_OIDC_PROVIDERS_KEYCLOAK_REDIRECT_URI=${PUBLIC_URL}/auth/keycloak/callback \
    NUXT_OIDC_PROVIDERS_KEYCLOAK_LOGOUT_REDIRECT_URI=${PUBLIC_URL}/ \
    API_PROXY_TARGET=http://api:8000 \
    EPA_INTERNAL_URL=http://epa:8080 \
    REDIS_URL=redis://redis:6379/0 \
    NODE_OPTIONS=--max-old-space-size=3072
RUN npm run build

FROM node:22-alpine
WORKDIR /app
COPY --from=build /app/.output ./.output
ENV NODE_ENV=production \
    HOST=0.0.0.0 \
    PORT=3000
EXPOSE 3000
CMD ["node", ".output/server/index.mjs"]
