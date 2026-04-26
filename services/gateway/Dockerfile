# Stage 1: builder
FROM node:22-slim AS builder
WORKDIR /app
# Copy the shared-types package so the file: dependency resolves during npm ci
COPY packages/shared-types/typescript ./packages/shared-types/typescript
COPY services/gateway/package*.json ./
RUN npm ci
COPY services/gateway/tsconfig.json ./
COPY services/gateway/src ./src
RUN npm run build

# Stage 2: runtime
FROM node:22-slim
WORKDIR /app
COPY --from=builder /app/dist ./dist
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/package.json ./
USER node
EXPOSE 3000
CMD ["node", "dist/index.js"]
