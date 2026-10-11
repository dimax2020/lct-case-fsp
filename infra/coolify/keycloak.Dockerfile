# Keycloak для Coolify: реалм запечён в образ и импортируется при первом старте.
# Домен стенда добавляется в разрешённые redirect URI через плейсхолдер ${PUBLIC_URL},
# который Keycloak подставляет из окружения при импорте. Контекст сборки — корень репозитория.
FROM alpine:3.20 AS realm
COPY infra/keycloak/realm-export.json /realm-export.json
RUN sed -i 's#"https://career-demo.example.ru/\*"#"${PUBLIC_URL:https://career-demo.example.ru}/*"#' /realm-export.json \
 && grep -q 'PUBLIC_URL' /realm-export.json

FROM quay.io/keycloak/keycloak:26.0
COPY --from=realm /realm-export.json /opt/keycloak/data/import/realm-export.json
