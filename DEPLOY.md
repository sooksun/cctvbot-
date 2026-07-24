# Deploy — cctvbot บน cctvbot.cnppai.com

Runbook สำหรับ deploy full stack (api + web + event-worker + mosquitto + frigate)
บน CasaOS host `payaprai-MS-7E41` หลัง Nginx Proxy Manager (NPM) โดยใช้ **external MariaDB**.

- **Path บน server:** `/DATA/AppData/www/cctvbot`
- **Domain:** `https://cctvbot.cnppai.com`
- **Ports (host LAN):** web `9930`, api `9931`, frigate UI `5000` (LAN only)

> รันคำสั่งทั้งหมด **บน server** (SSH เข้า host) ไม่ใช่บนเครื่อง dev.

---

## 0) ก่อนเริ่ม (prerequisites บน host)

- Docker + Docker Compose plugin ติดตั้งแล้ว
- External MariaDB container (`mariadb`) รันอยู่ที่ `0.0.0.0:3306`
- NPM (`nginxproxymanager`) รันอยู่ (bind 80/81/443)
- DNS: `cctvbot.cnppai.com` → IP ของ host/router (พร้อม port-forward 80/443 → NPM เท่านั้น)
- ถ้าจะรัน Frigate แบบ GPU: NVIDIA driver + `nvidia-container-toolkit` ติดตั้งแล้ว (ดู §7)

---

## 1) นำโค้ดขึ้น server

```bash
sudo mkdir -p /DATA/AppData/www
cd /DATA/AppData/www
git clone https://github.com/sooksun/cctvbot-.git cctvbot
cd cctvbot
git checkout master   # หรือ feat/school-cctv-mvp ถ้ายังไม่ merge
```

อัปเดตครั้งถัดไป: `cd /DATA/AppData/www/cctvbot && git pull`

---

## 2) สร้าง database + user บน external MariaDB

```bash
docker exec -it mariadb mariadb -uroot -p
```
```sql
CREATE DATABASE IF NOT EXISTS cctvbot
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;   -- utf8mb4 = รองรับข้อความไทย
CREATE USER IF NOT EXISTS 'cctvbot'@'%' IDENTIFIED BY 'STRONG_DB_PASSWORD';
GRANT ALL PRIVILEGES ON cctvbot.* TO 'cctvbot'@'%';
FLUSH PRIVILEGES;
```
> ตาราง (users/cameras/events/audit_logs) ถูกสร้างอัตโนมัติตอน API boot ครั้งแรก (`Base.metadata.create_all`) — ไม่ต้อง migrate มือ

---

## 3) ตั้งค่า `.env.production`

```bash
cp .env.production.example .env.production
# สร้าง secret จริง:
echo "API_SECRET_KEY=$(openssl rand -base64 48)"
echo "SYSTEM_API_TOKEN=$(openssl rand -hex 32)"
nano .env.production
```

ต้องตั้งค่าจริง (ห้ามเหลือ `CHANGE_ME_*`):
- `DATABASE_URL` → ใส่ DB password จาก §2 (host = `host.docker.internal`)
- `API_SECRET_KEY`, `SYSTEM_API_TOKEN`, `ADMIN_PASSWORD`
- `FRIGATE_RTSP_PASSWORD` → รหัส RTSP ของกล้อง/DVR
- (ถ้าใช้ LINE) `LINE_CHANNEL_ACCESS_TOKEN`, `LINE_USER_ID`

> `ENVIRONMENT=production` ทำให้ API **ไม่ยอม boot** ถ้ายังมี secret เป็นค่า default — เป็น guard โดยตั้งใจ

---

## 4) ตั้งค่า Frigate + rules

```bash
nano frigate/config.yml       # ใส่ RTSP host/path จริงของกล้อง (ดู README §RTSP)
# data/config/schedule.yml, rules.yml มี default อยู่แล้ว — แก้ตามโรงเรียน
```
- `camera_id` ใน `frigate/config.yml` ต้องตรงกับ `data/config/rules.yml` (`restricted_zones`)
- redraw zones `restricted` / `litter_watch` ใน Frigate UI ให้ตรงพื้นที่จริง
- **Rules 7 + 9 (motion/crowd/fight) เปิดแล้ว** ผ่าน in-worker person-motion enrichment (`person_motion_enrichment: true`). จูน `run_speed_threshold` / `crowd_threshold` / `fight_*` ตามหน้างานเพื่อลด false positive
- **Rule 8 littering พร้อมแล้ว แต่ opt-in** (`enrichment_available: false` เป็น default) — object-drop layer wired แล้ว (LitteringTracker + camera-level person presence); เปิดต่อกล้องเมื่อพร้อม (FP สูงสุด)
- ⚠️ ก่อน production: ตรวจว่า Frigate MQTT `box` เป็น normalized `[x1,y1,x2,y2]` ตามที่ enricher สมมติ (capture payload จริงมาดู) — ถ้าเป็น pixel ต้อง normalize ด้วย detect width/height

---

## 5) Build + start

```bash
docker compose -f docker-compose.prod.yml --env-file .env.production up -d --build
docker compose -f docker-compose.prod.yml --env-file .env.production ps
```
> ใส่ `--env-file .env.production` กับ **ทุก** คำสั่ง compose (logs/ps/exec) ไม่งั้น compose เตือน `variable is not set`

---

## 6) Health check (บน host, ผ่าน LAN)

```bash
curl -s http://localhost:9931/health           # {"status":"ok"}
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:9930/login   # 200
docker compose -f docker-compose.prod.yml --env-file .env.production logs -f api
```
Frigate UI (LAN เท่านั้น): `http://<HOST_LAN_IP>:5000`

---

## 7) Frigate & GPU ⚠️

Frigate detect ต้องการ **NVIDIA GPU** เพื่อประสิทธิภาพจริง

| กรณี | image | การตั้งค่า |
|---|---|---|
| **มี NVIDIA GPU** | `frigate:stable-tensorrt` (default ใน compose) | เปิด `ffmpeg.hwaccel_args: preset-nvidia-h264` + `detectors.onnx` ใน `frigate/config.yml`; ต้องมี `nvidia-container-toolkit` |
| **ไม่มี GPU (CPU)** | เปลี่ยนเป็น `frigate:stable` | **comment บล็อก `deploy:`/`runtime: nvidia`** ใน `docker-compose.prod.yml`; ใช้ `detectors.cpu` |

> **CPU detect ช้ามากและไม่เหมาะกับ production** (README ระบุชัด) — ถ้า host นี้ไม่มี GPU แนะนำ: (ก) ย้าย Frigate+worker ไปเครื่อง GPU ที่ LAN โรงเรียน แล้ว deploy แค่ web+api บน cloud นี้ หรือ (ข) ลด fps/จำนวนกล้องลงมากสำหรับ pilot เท่านั้น

---

## 8) ตั้ง NPM Proxy Host

NPM dashboard (`http://<HOST_IP>:81`) → **Add Proxy Host**

| Tab | Field | Value |
|---|---|---|
| Details | Domain Names | `cctvbot.cnppai.com` |
| Details | Forward Hostname/IP | `<HOST_LAN_IP>` (จาก `hostname -I`) |
| Details | Forward Port | `9930` (web) |
| Details | Cache Assets / Block Common Exploits / Websockets | ✓ |
| Custom locations | location | `/api/` → Forward to `<HOST_LAN_IP>:9931` |
| Custom locations | Custom Nginx Config | `client_max_body_size 25M; proxy_read_timeout 300s;` |
| SSL | Certificate | Request new (Let's Encrypt) · Force SSL · HTTP/2 ✓ · HSTS **OFF** จนกว่าจะเสถียร 24h |

> Dashboard เรียก `https://cctvbot.cnppai.com/api/...` → NPM route `/api/` → api container (same-origin). **ห้าม** เพิ่ม Frigate :5000 เข้า NPM หรือ public-forward

---

## 9) Smoke test (หลัง deploy)

```bash
# บน host — สร้าง event สังเคราะห์ผ่าน API (ไม่ต้องรอกล้อง)
SYSTEM_API_TOKEN=$(grep ^SYSTEM_API_TOKEN .env.production | cut -d= -f2) \
API_BASE_URL=http://localhost:9931 \
EVIDENCE_ROOT=/DATA/AppData/www/cctvbot/data/events \
python3 scripts/smoke_create_event.py
```
แล้วเปิด `https://cctvbot.cnppai.com` → login admin → เปิด event → กด confirm / false_positive
(confirm จะส่ง LINE text ถ้าตั้ง token ไว้)

---

## 10) Security checklist

- [ ] `9930/9931/5000/1883` **ไม่** public port-forward ที่ router — เปิดแค่ 80/443 ให้ NPM
- [ ] `git check-ignore .env.production` → ต้องคืน path (ไม่หลุด git)
- [ ] เปลี่ยน `ADMIN_PASSWORD` ทันทีหลัง login ครั้งแรก
- [ ] `SYSTEM_API_TOKEN` ใน worker = ใน API (ค่าเดียวกัน)
- [ ] MariaDB user `cctvbot` มีสิทธิ์เฉพาะ db `cctvbot` (ไม่ใช่ root)
- [ ] evidence (`data/events`) + recordings (`data/frigate`) อยู่บน host เท่านั้น ไม่เผยแพร่
- [ ] Off-host backup ของ DB (`mariadb-dump`) + `data/events`

---

## 11) Operations

```bash
CO="docker compose -f docker-compose.prod.yml --env-file .env.production"

$CO logs -f --tail=100 api event-worker           # ดู log
$CO up -d --force-recreate --no-deps api           # recreate service เดียว
$CO build web && $CO up -d --force-recreate web     # rebuild หลังแก้ web
git pull && $CO up -d --build                        # deploy โค้ดใหม่
$CO down                                             # stop ทั้ง stack (คง volume/DB)
```

Backup DB (ตัวอย่าง cron รายวัน):
```bash
docker exec mariadb mariadb-dump -uroot -p'ROOT_PW' cctvbot | gzip > /DATA/backup/cctvbot-$(date +%F).sql.gz
```
