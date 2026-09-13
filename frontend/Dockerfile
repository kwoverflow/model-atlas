FROM node:22-slim AS deps
WORKDIR /app
COPY package*.json ./
RUN if [ -f package-lock.json ]; then npm ci; else npm install; fi

FROM node:22-slim AS builder
WORKDIR /app
ARG NEXT_PUBLIC_API_URL=http://localhost:18000/api/v1
ARG NEXT_PUBLIC_CSRF_COOKIE_NAME=model_atlas_csrf
ARG NEXT_PUBLIC_CSRF_HEADER_NAME=x-model-atlas-csrf
ENV NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL}
ENV NEXT_PUBLIC_CSRF_COOKIE_NAME=${NEXT_PUBLIC_CSRF_COOKIE_NAME}
ENV NEXT_PUBLIC_CSRF_HEADER_NAME=${NEXT_PUBLIC_CSRF_HEADER_NAME}
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm test
RUN npm run build

FROM node:22-slim AS runner
WORKDIR /app
ENV NODE_ENV=production
COPY --from=builder /app/package.json ./package.json
COPY --from=builder /app/package-lock.json ./package-lock.json
COPY --from=builder /app/eslint.config.mjs ./eslint.config.mjs
COPY --from=builder /app/next.config.mjs ./next.config.mjs
COPY --from=builder /app/next-env.d.ts ./next-env.d.ts
COPY --from=builder /app/postcss.config.js ./postcss.config.js
COPY --from=builder /app/tailwind.config.ts ./tailwind.config.ts
COPY --from=builder /app/tsconfig.json ./tsconfig.json
COPY --from=builder /app/app ./app
COPY --from=builder /app/components ./components
COPY --from=builder /app/lib ./lib
COPY --from=builder /app/types ./types
COPY --from=builder /app/.next ./.next
COPY --from=builder /app/.next/standalone ./.next/standalone
COPY --from=builder /app/.next/static ./.next/standalone/.next/static
COPY --from=builder /app/public ./.next/standalone/public
COPY --from=builder /app/public ./public
COPY --from=builder /app/node_modules ./node_modules
EXPOSE 3000
CMD ["node", ".next/standalone/server.js"]
