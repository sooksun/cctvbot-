# cctvbot — School CCTV Security

On-premise school security assistance: Frigate camera ingest, rule-based events, dual API + evidence files, internal dashboard review, and LINE text alerts only after human confirmation.

## Local-first (important)

This system is **local-first / on-premise**:

- Video, clips, and snapshots stay on the school server.
- Do **not** publicly port-forward cameras, Frigate, or evidence storage.
- Dashboard and API are intended for school LAN use.
- LINE (optional) sends **text only** after a human confirms an event — no media.

## Docs

- Design spec: [docs/superpowers/specs/2026-07-23-school-cctv-security-design.md](docs/superpowers/specs/2026-07-23-school-cctv-security-design.md)
- Implementation plan: [docs/superpowers/plans/2026-07-23-school-cctv-security.md](docs/superpowers/plans/2026-07-23-school-cctv-security.md)

## Quick start (scaffold)

1. Copy the env template and set real secrets:

   ```bash
   cp .env.example .env
   ```

2. Edit `.env` — replace all `change_me_*` values. Never commit `.env`.

3. `docker-compose.yml` is a **stub** (networks/volumes only). Full services are added in later tasks. Do not treat empty compose as a production stack yet.

## Layout

```
cctvbot/
├── .env.example          # env var template (committed)
├── .env                  # secrets (gitignored)
├── docker-compose.yml    # stub; services filled in later tasks
├── data/
│   ├── events/           # evidence root (bind mount target)
│   ├── frigate/
│   └── config/
└── docs/superpowers/     # design spec + plan
```

## Stack (planned)

Docker Compose · Frigate · Python event-worker · FastAPI · MySQL 8 · Next.js · MQTT (Mosquitto) · LINE Messaging API
