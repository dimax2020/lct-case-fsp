FROM node:20-bookworm-slim

WORKDIR /srv

RUN apt-get update \
 && apt-get install -y --no-install-recommends git ca-certificates \
 && rm -rf /var/lib/apt/lists/*

COPY package.json package-lock.json tsconfig.json vitest.config.ts ./
COPY apps ./apps
COPY packages ./packages
COPY services ./services
COPY extensions ./extensions

RUN npm ci \
 && npm run extension:package

ENV HOST=0.0.0.0 \
    EPA_RDE_DRIVER=local \
    EPA_SANDBOX_DRIVER=local \
    EPA_DATA_DIR=/data \
    PORT=8080

EXPOSE 8080

CMD ["npx", "tsx", "apps/api/src/main.ts"]
