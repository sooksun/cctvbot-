# Task 9 Report: Frigate config for 2–4 pilot cameras

## Done
- Added `frigate/config.yml` — MQTT→mosquitto, 4 pilot cams (`gate_front`, `yard_1`, `building_a`, `hall_1` disabled), zones `restricted` + `litter_watch`, objects person+COCO litter proxies, record retain 30d, NVIDIA hwaccel + onnx (CPU notes inline).
- Added `frigate` service to `docker-compose.yml` — `/config` + media volume, tmpfs cache, port 5000 LAN optional, GPU deploy commented.
- Added `data/config/cameras.example.yml` (IP vs DVR inventory); `.gitignore` allows the example file.
- README: RTSP IP vs DVR channel, ports, GPU vs CPU detector notes.

## Commit
`feat(frigate): pilot camera config template and compose service`

## Fix notes (Task 9 review — Critical/Important)

Applied 2026-07-23 after review of Frigate 0.14+ schema and Laragon boot safety.

1. **record schema (Critical)** — Replaced legacy `record.retain` + `record.events` with Frigate 0.14+ keys:
   - `continuous.days: 0`, `motion.days: 30`
   - `alerts.retain` / `detections.retain` (days 30, `mode: active_objects`)
   - Per-camera: only `record.enabled: true` (dropped obsolete per-cam `retain.days`)

2. **detect.enabled (Important)** — Set `detect.enabled: true` on all cameras including `hall_1` (camera may stay `enabled: false` until pilot expands; detect block is ready).

3. **CPU-safe defaults for Laragon (Recommended)** — Default detector is `cpu` (`num_threads: 2`). Top-level `ffmpeg.hwaccel_args` commented out. GPU path documented in header + inline comments (RTX 5070 Ti / `stable-tensorrt` / `onnx` / `preset-nvidia-h264`).

### Re-verify (`frigate/config.yml`)

| Check | Status |
|-------|--------|
| No `record.events` / legacy global `record.retain` | OK |
| Global record: continuous/motion/alerts/detections | OK |
| All 4 cams: `detect.enabled: true` + 1280x720@5 | OK |
| Per-cam record: `enabled: true` only | OK |
| Default detector: `cpu` | OK |
| `hwaccel_args` commented (GPU notes present) | OK |

### Follow-up commit
`fix(frigate): align config with Frigate 0.14 record schema and enable detect`
