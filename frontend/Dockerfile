FROM node:22-alpine AS builder
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
# Next.js rewrite 목적지는 빌드 시점에 고정되므로 build arg로 주입한다
# (브라우저는 항상 같은 오리진의 /api/v1을 호출하고, 이 서버가 백엔드로 프록시한다)
ARG API_ORIGIN=http://localhost:8000
ENV API_ORIGIN=$API_ORIGIN
RUN npm run build

FROM node:22-alpine
WORKDIR /app
ENV NODE_ENV=production
COPY --from=builder /app/package.json ./
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/.next ./.next
EXPOSE 3000
CMD ["npm", "start"]
