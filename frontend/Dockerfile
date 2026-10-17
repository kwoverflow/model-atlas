FROM node:22-slim AS deps
WORKDIR /app
COPY package*.json ./
COPY .npmrc ./
COPY tooling ./tooling
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
ENV NEXT_TELEMETRY_DISABLED=1
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public
EXPOSE 3000
CMD ["node", "server.js"]
