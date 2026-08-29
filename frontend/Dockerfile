# syntax=docker/dockerfile:1
#
# Production image only (Phase 6). Local dev still runs the frontend via `npm run dev`
# on the host, not containerized — see README.md.

FROM node:20-slim AS deps
WORKDIR /srv
COPY package.json package-lock.json ./
RUN npm ci

FROM node:20-slim AS build
WORKDIR /srv
COPY --from=deps /srv/node_modules ./node_modules
COPY . .
# Baked in at build time (Next.js inlines NEXT_PUBLIC_* vars into the client bundle —
# there's no reading this from the environment at runtime). `/api` is always correct in
# this deployment: Caddy reverse-proxies `/api/*` to the backend on the same origin as
# the frontend (infra/Caddyfile), so the browser never needs a cross-origin request and
# the backend's CORS config never has to change for prod.
ARG NEXT_PUBLIC_API_BASE_URL=/api
ENV NEXT_PUBLIC_API_BASE_URL=$NEXT_PUBLIC_API_BASE_URL
RUN npm run build

# `output: "standalone"` (next.config.ts) traces the minimal server + dependency set into
# .next/standalone — public/ and .next/static/ are copied in separately per Next's docs.
FROM node:20-slim AS run
WORKDIR /srv
ENV NODE_ENV=production PORT=3000 HOSTNAME=0.0.0.0
COPY --from=build /srv/public ./public
COPY --from=build /srv/.next/standalone ./
COPY --from=build /srv/.next/static ./.next/static

RUN useradd --create-home --uid 10001 appuser && chown -R appuser /srv
USER appuser

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD node -e "require('http').get('http://localhost:3000/login', r => process.exit(r.statusCode < 500 ? 0 : 1)).on('error', () => process.exit(1))"

CMD ["node", "server.js"]
