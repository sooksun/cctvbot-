# Web Dockerfile Standalone — Design Spec

**Date:** 2026-07-26
**Project:** `cctvbot`
**Status:** Approved for implementation planning
**Mode:** Deployment/build optimization (apps/web).

---

## 1. Purpose

The web image copies the full `node_modules` + `.next` into the runner and runs
`npm start`, producing a large image. Switch to Next's `output: "standalone"` so the
runner ships only the traced minimal server, shrinking the image and speeding cold start.

## 2. Scope

### In scope
- `output: "standalone"` in `next.config.ts`.
- Rewrite the Dockerfile runner stage to copy `.next/standalone` + `.next/static` +
  `public` and run `node server.js`.

### Out of scope
- docker-compose changes; multi-arch builds; the container image build cannot be
  verified here (Docker Desktop is not running).

## 3. Approach

`apps/web/next.config.ts`:
```ts
const nextConfig: NextConfig = {
  output: "standalone",
};
```

`apps/web/Dockerfile` runner stage — replace the full-copy + `npm start` with:
```dockerfile
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public
EXPOSE 3000
CMD ["node", "server.js"]
```
`.next/standalone` contains `server.js` + its own traced `node_modules` + `package.json`;
static assets live in `.next/static`, and `public/` serves static files. No full
`node_modules`/`next.config.ts` copy needed. `apps/web` is an independent npm project (not
a workspace), so the traced output is self-contained (no `outputFileTracingRoot` needed).

`NEXT_PUBLIC_API_URL` is still baked at build time (unchanged); the runner ENV line is
harmless and kept for parity.

## 4. Verification

- `npm run build` → assert `.next/standalone/server.js` and `.next/static/` exist (proves
  Next emits the standalone artifact correctly).
- `npm run lint`, `npx tsc --noEmit` stay green (`output` doesn't affect dev/lint/types).
- ⚠️ The Docker image build + asset-serving inside the container **cannot be verified
  here** (Docker not running) — standard Next standalone pattern; flagged for the first
  real build.

## 5. Risks & mitigations

| Risk | Mitigation |
|------|------------|
| Static/public asset paths wrong in the container → 404s | Follows the official Next standalone Dockerfile layout (`.next/static`, `public`); verify on first real build. |
| Standalone misses a runtime dep (tracing gap) | `apps/web` is a self-contained project; verify container boot on first build. |
| Build doesn't emit standalone | Verified locally via the presence check of `.next/standalone/server.js`. |
