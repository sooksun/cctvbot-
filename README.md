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

## Quick start

1. Copy the env template and set real secrets:

   ```bash
   cp .env.example .env
   ```

2. Edit `.env` — replace all `change_me_*` values. Never commit `.env`.
   Set `FRIGATE_RTSP_PASSWORD` to the shared camera/DVR RTSP password used in `frigate/config.yml`.

3. Edit `frigate/config.yml` — set RTSP hosts/paths for pilot cameras (see **RTSP** below).
   Copy `data/config/cameras.example.yml` → `data/config/cameras.yml` for inventory notes.

4. Start core services (Frigate needs working RTSP or will restart/retry):

   ```bash
   docker compose up -d db api mosquitto event-worker frigate
   ```

5. Frigate UI (LAN only, unauthenticated on :5000): `http://localhost:5000`  
   API: `http://localhost:8000/health`

## Ports (LAN)

| Port | Service | Notes |
|------|---------|--------|
| 3000 | web (later) | Dashboard |
| 8000 | api | FastAPI |
| 3307 | mysql | Host → container 3306 |
| 5000 | frigate | Optional LAN admin; **do not** public port-forward |
| 1883 | mosquitto | MQTT (Frigate + event-worker) |

## RTSP: IP camera vs DVR channel

Frigate is camera-agnostic: both IP and analog (via DVR) appear as RTSP URLs.

**Direct IP camera** (common ONVIF / vendor paths):

```text
rtsp://USER:PASS@192.168.1.21:554/stream1
rtsp://USER:PASS@192.168.1.21:554/Streaming/Channels/101
```

**Analog camera via DVR/NVR** — RTSP is served by the recorder, not the camera. Channel numbers are vendor-specific:

| Vendor family | Example (channel 1 main stream) |
|---------------|----------------------------------|
| Hikvision-style | `rtsp://USER:PASS@DVR_IP:554/Streaming/Channels/101` (ch2 → `201`) |
| Dahua-style | `rtsp://USER:PASS@DVR_IP:554/cam/realmonitor?channel=1&subtype=0` |
| Generic | Check DVR web UI / “RTSP URL” helper; often port `554` |

Tips:

- Prefer **substream** for `detect` if main is 4K and GPU is limited; main stream for `record` (two inputs).
- Keep cameras and DVR on school LAN only — no public RTSP port-forward.
- Placeholder zones `restricted` and `litter_watch` in `frigate/config.yml` must be redrawn in the Frigate UI to match real floors.
- `camera_id` in Frigate must match IDs used by the API / worker rules.

## Frigate detectors (GPU vs CPU)

| Environment | Image | Config |
|-------------|-------|--------|
| School NVIDIA GPU | `ghcr.io/blakeblackshear/frigate:stable-tensorrt` | `ffmpeg.hwaccel_args: preset-nvidia-h264`, `detectors.onnx` |
| Windows/Laragon, no GPU | `ghcr.io/blakeblackshear/frigate:stable` | Comment `hwaccel_args`; enable `detectors.cpu` (slow; smoke-test only) |

Uncomment `deploy.resources` / `runtime: nvidia` in `docker-compose.yml` on the GPU host. CPU detector is for local dev only — not for production pilot.

## Layout

```
cctvbot/
├── .env.example          # env var template (committed)
├── .env                  # secrets (gitignored)
├── docker-compose.yml    # db, api, mosquitto, event-worker, frigate
├── frigate/
│   └── config.yml        # pilot camera template (2–4 cams)
├── data/
│   ├── events/           # evidence root (bind mount target)
│   ├── frigate/          # Frigate media (recordings/clips)
│   └── config/           # cameras.example.yml + local schedule/rules
└── docs/superpowers/     # design spec + plan
```

## Stack

Docker Compose · Frigate · Python event-worker · FastAPI · MySQL 8 · Next.js · MQTT (Mosquitto) · LINE Messaging API
