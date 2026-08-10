# =============================================================================
# MurasFood Web image — Nuxt 4 storefront + admin dashboard.
# `development` runs the Nuxt dev server with HMR; `production` runs the
# prebuilt Nitro server output as a non-root user.
# =============================================================================

FROM node:22-alpine AS base
WORKDIR /app

# Native modules (sass-embedded) need a toolchain to install on Alpine.
RUN apk add --no-cache libc6-compat

ENV NODE_ENV=development
COPY apps/web/package.json apps/web/package-lock.json* ./

# `--legacy-peer-deps` matches how the lockfile was resolved. Several Nuxt
# modules still declare peer ranges for Nuxt 3 while working correctly on
# Nuxt 4; npm's strict resolver refuses the tree outright without this flag.
# `npm ci` is preferred for reproducibility and falls back to `npm install`
# when the lockfile is absent.
RUN npm ci --legacy-peer-deps --no-audit --no-fund \
    || npm install --legacy-peer-deps --no-audit --no-fund


# --- development -------------------------------------------------------------
FROM base AS development
COPY apps/web /app
EXPOSE 3000
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]


# --- build -------------------------------------------------------------------
FROM base AS build
COPY apps/web /app
ENV NODE_ENV=production
RUN npm run build


# --- production --------------------------------------------------------------
FROM node:22-alpine AS production
WORKDIR /app
ENV NODE_ENV=production \
    NITRO_PORT=3000 \
    NITRO_HOST=0.0.0.0

# Nitro output is fully self-contained: no node_modules needed at runtime.
COPY --from=build --chown=node:node /app/.output /app/.output

USER node
EXPOSE 3000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD node -e "fetch('http://127.0.0.1:3000/').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"

CMD ["node", ".output/server/index.mjs"]
