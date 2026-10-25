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
- `last_fed_at` persisted in **SQLite**, so restarts keep the limit. Only
  **public** (`/feed`) calls advance this timestamp — the owner's
  `/admin/feed` bypass never pushes out or resets the public cooldown, so
  using the secret channel doesn't block or confuse visitors.
- `fed_today` (shown as "訪客食咗"/"Fed by visitors") counts **public feeds
  only** — admin-channel feeds are excluded, by design.

## Endpoints

| Method | Path             | Purpose                                                |
| ------ | ---------------- | ------------------------------------------------------- |
| GET    | `/status`        | Can we feed now? next feed time, window, visitor fed-today count. |
| POST   | `/feed`          | Try to feed. Enforces all rules, then calls HA.          |
| POST   | `/admin/feed`    | HMAC-signed bypass (cooldown + open hours) for the owner only. |
| GET    | `/admin/history` | HMAC-signed. Today's feed events, straight from PetKit (not our own log). |
| GET    | `/health`        | Liveness check.                                          |

`POST /feed` returns `200` on success, `403` outside hours, `429` cooldown or
spam, `502` if HA is unreachable.

`POST /admin/feed` and `GET /admin/history` are the secret-channel endpoints
the frontend calls after unlocking (tap the logo 5×, enter `ADMIN_TOKEN`).
Every request must be HMAC-SHA256 signed with `ADMIN_TOKEN` over
`{METHOD}:{PATH}:{timestamp}` and include a timestamp within
`ADMIN_SIG_WINDOW_SECONDS` — see `verify_admin_signature()` in `app/main.py`.
No plaintext password crosses the wire. `/admin/feed` still logs the feed
(`feed_log`) but — unlike `/feed` — skips cooldown/open-hours checks and
does **not** touch the public `last_fed_at` or `fed_today`.

`/admin/history` doesn't read our own `feed_log` at all — it queries Home
Assistant's history API for the PetKit device's own `last_feed_event` sensor,
which updates on *every* real dispense regardless of trigger (this site, the
PetKit app, the physical button, or a scheduled auto-feed). That sensor's
timestamp is the ground truth; our own log only knows about feeds triggered
through this site. See `get_feed_history()` in `app/ha.py` — note HA's
history endpoint caps each response at a handful of rows counted from the
*start* of the requested window, so it's queried in small backward-walking
chunks rather than one wide request.

## Deploy in the LXC (Debian 12, no Docker)

```bash
# as root in the CT
apt update && apt install -y python3 python3-venv python3-pip
useradd -r -m -d /opt/catcam-backend catcam || true

# copy this folder to /opt/catcam-backend, then:
cd /opt/catcam-backend
python3 -m venv catvenv   # name matches deploy/catcam.service's ExecStart
catvenv/bin/pip install -r requirements.txt

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
