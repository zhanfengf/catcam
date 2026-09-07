# CatCam Feeder API

Python + FastAPI backend that lets the public "feed the cat" through a narrow,
rate-limited endpoint. The frontend (SvelteKit) only ever talks to **this**
service — the Home Assistant token stays here, never in the browser.

```
觀眾瀏覽器 → SvelteKit → 呢個後端 → HA REST API → text.zhi_ma_guan_jia_manual_feed
```

## Rules baked in

- Link-only, no login.
- Whole-site shared cooldown: **120 minutes** between feeds.
- Open window: **07:00–23:59 (Asia/Hong_Kong)**.
- Fixed portion: **10**.
- Per-IP anti-spam (stops hammering; not the feeding quota).
- `last_fed_at` persisted in **SQLite**, so restarts keep the limit.

## Endpoints

| Method | Path      | Purpose                                             |
| ------ | --------- | --------------------------------------------------- |
| GET    | `/status` | Can we feed now? next feed time, window, fed today. |
| POST   | `/feed`   | Try to feed. Enforces all rules, then calls HA.     |
| GET    | `/health` | Liveness check.                                     |

`POST /feed` returns `200` on success, `403` outside hours, `429` cooldown or
spam, `502` if HA is unreachable.

## Deploy in the LXC (Debian 12, no Docker)

```bash
# as root in the CT
apt update && apt install -y python3 python3-venv python3-pip
useradd -r -m -d /opt/catcam-backend catcam || true

# copy this folder to /opt/catcam-backend, then:
cd /opt/catcam-backend
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

cp .env.example .env
#  >>> edit .env: set HA_TOKEN (and check HA_URL / entity) <<<
chown -R catcam:catcam /opt/catcam-backend

# install the service
cp deploy/catcam.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now catcam
systemctl status catcam --no-pager
```

Test locally inside the CT:

```bash
curl localhost:8080/status
curl -X POST localhost:8080/feed -H 'cf-connecting-ip: 1.2.3.4'
```

## Get the HA token

Home Assistant → click your user (bottom-left) → **Security** tab →
**Long-lived access tokens** → **Create**. Paste it into `.env` as `HA_TOKEN`.
Keep `.env` out of git.

## Exposing it

The service listens on `127.0.0.1:8080`. Put the SvelteKit app in front (same
CT or another), and add a Cloudflare Tunnel route (e.g. `cat.kelvinp.work`)
pointing at the CT. Set `CORS_ORIGINS` in `.env` to your site's origin once the
domain is known (leave `*` only for local testing).

## Notes

- Run with a **single worker** (the systemd unit already does). The anti-spam
  limiter and feed lock live in memory.
- To change portion size, cooldown, or hours, edit `.env` and restart — no code
  changes needed.
