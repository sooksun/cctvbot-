# Web Dockerfile Standalone Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Ship the web app as a Next standalone image (smaller, faster cold start).

**Architecture:** `output: "standalone"` + a slim runner stage copying only the traced output.

**Tech Stack:** Next 16, Docker (node:22-alpine).

## Global Constraints

- Only `apps/web/next.config.ts` + `apps/web/Dockerfile` change.
- Verify locally: build emits `.next/standalone/server.js` + `.next/static`; lint + tsc green.
- Container build is NOT verifiable here (Docker down) — flagged, not blocking.

---

### Task 1: Standalone output + Dockerfile

**Files:**
- Modify: `apps/web/next.config.ts`
- Modify: `apps/web/Dockerfile`

- [ ] **Step 1: Enable standalone output** — `apps/web/next.config.ts`:

Replace the config object:
```ts
const nextConfig: NextConfig = {
  // Browser calls API via NEXT_PUBLIC_API_URL (default http://localhost:8000).
  // CORS is configured on the FastAPI side for http://localhost:3000.
};
```
with:
```ts
const nextConfig: NextConfig = {
  // Emit a self-contained server (.next/standalone) for a slim Docker runner.
  output: "standalone",
  // Browser calls API via NEXT_PUBLIC_API_URL (default http://localhost:8000).
  // CORS is configured on the FastAPI side for http://localhost:3000.
};
```

- [ ] **Step 2: Slim the runner stage** — `apps/web/Dockerfile`:

Replace the runner stage body:
```dockerfile
FROM node:22-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1
ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
COPY --from=builder /app/package*.json ./
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/.next ./.next
COPY --from=builder /app/public ./public
COPY --from=builder /app/next.config.ts ./next.config.ts
EXPOSE 3000
CMD ["npm", "start"]
```
with:
```dockerfile
FROM node:22-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1
ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
# Next standalone: minimal traced server + static assets only.
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public
EXPOSE 3000
CMD ["node", "server.js"]
```

- [ ] **Step 3: Build + verify the standalone artifact**

```bash
cd apps/web
npm run build
ls .next/standalone/server.js && ls -d .next/static && echo "standalone OK"
```
Expected: `.next/standalone/server.js` and `.next/static/` exist, build "Compiled successfully".

- [ ] **Step 4: Lint + typecheck**

Run: `cd apps/web && npm run lint` → exit 0 (existing warnings ok)
Run: `cd apps/web && npx tsc --noEmit` → rc 0

- [ ] **Step 5: DEPLOY.md note (optional clarity)**

Add a short note under the web deploy section that the image now uses Next standalone
(`node server.js`), so no `npm start` / full node_modules in the runner.

- [ ] **Step 6: Commit**

```bash
git add apps/web/next.config.ts apps/web/Dockerfile DEPLOY.md
git commit -m "build(web): Next standalone output for a slim runner image"
```

---

## Self-Review

**Spec coverage:** §3 config + Dockerfile → Steps 1–2; §4 verification → Steps 3–4. ✓

**Placeholder scan:** full code in each step. ✓

**Consistency:** runner copies match the standalone layout (`.next/standalone`→`/app`,
`.next/static`, `public`); `CMD node server.js`; `apps/web` self-contained (no tracing
root). Container build flagged unverifiable (Docker down). ✓
