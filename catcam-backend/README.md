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
| GET    | `/recordings`    | Public. List of this week's 60s feed clips (filename + timestamp). |
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
Assistant's history API for the PetKit device's `times_dispensed` counter,
which increments on *every* real dispense regardless of trigger (this site,
the PetKit app, the physical button, or a scheduled auto-feed), and resets to
0 at local midnight. Each increase in its history is one feed event; the
event's time is HA's own `last_changed` for that state change. Our own log
only knows about feeds triggered through this site, so this is the ground
truth. See `get_feed_history()` in `app/ha.py` — two non-obvious things
there:
- HA's history endpoint caps each response at a handful of rows counted from
  the *start* of the requested window, so it's queried in small
  backward-walking chunks rather than one wide request.
- The PetKit integration also exposes `image.*_last_feed_event`, whose state
  *is* a literal event timestamp — tempting to use directly, but it lags
  minutes-to-hours behind (it waits on a snapshot image upload from the
  device). `times_dispensed` is a plain number with no image attached and
  updates within seconds of a real dispense — confirmed by watching it tick
  up ~6s after a manual feed, while `last_feed_event` was still an hour+
  stale.

## Feed clip recording

`app/recorder.py` runs a background poller (every 10s, same
`times_dispensed` signal as `/admin/history`) and on every real dispense
splices a clip from the pre-roll buffer (see below). **Not tied to `/feed`
or `/admin/feed` specifically** — it watches the HA dispense counter itself,
so it fires on *any* real dispense: a visitor pressing the site's button,
the owner's admin bypass, the PetKit app, the physical button on the
feeder, or PetKit's own schedule. If `/feed` fails before HA actually
dispenses (e.g. `502`), no clip is recorded, since the counter never moved.
Saved to `recordings_dir` (default `./recordings`), 7-day rolling retention
(oldest deleted whenever a new clip lands), served publicly — no auth — via
`GET /recordings` (this JSON list) and static `/clips/*.mp4` (Caddy, not
this backend).

**Non-obvious:** go2rtc's duration-limited export (`/api/stream.mp4?...`,
used by the fallback path below) is fragmented MP4 (the same format it
streams over WebSocket/MSE) — a plain `<video src>` tag can silently fail to
ever load it (`readyState` stuck at `0`, no error event, looks like a slow
network rather than a format problem). Fixed by remuxing immediately after
download: `ffmpeg -i raw -c copy -movflags +faststart final.mp4`
(lossless, ~0.4s for a 60s clip). Downloads go to a `.part` suffix (not
`.mp4`) first so a crash mid-download/remux can never leave a half-written
file visible in the public listing.

## Pre-roll buffer

A fixed-length export starting *after* the dispense signal arrives can
never show the cat running over to eat — by the time the backend even
learns a dispense happened (HA/PetKit cloud sync alone can take seconds to
tens of seconds, confirmed via HA's history API: ~6s for a manual app feed,
~27s for a scheduled auto-feed), the cat may already be at the bowl. There's
no way to retroactively capture footage that was never recorded, so
`app/buffer.py` records continuously instead of waiting for a trigger: a
long-running `ffmpeg -c copy` process pulls `petkit_h264` from go2rtc's own
RTSP server (`rtsp://127.0.0.1:8554/petkit_h264` — go2rtc serves every
configured stream name over RTSP, not just the internal exec-mode sink
paths) and writes it as rolling 5-second segments (`-f segment
-segment_time 5 -strftime 1`) into `buffer_dir` (default `./buffer`),
deleting anything older than `buffer_window_seconds` (default 180s). Being
`-c copy` (no re-encode) this costs almost no extra CPU on top of the VAAPI
encode `petkit_h264` already does — see the `my-homelab` skill's catcam
section for why that encode is VAAPI hardware and not libx264 software.

**Non-obvious:** ffmpeg's `-strftime 1` filenames use the *spawned
process's* wall clock, not Python's `datetime.now(tz())`. `go2rtc.service`
sets `Environment=TZ=Asia/Hong_Kong`, but `catcam.service` doesn't (the CT's
system clock is UTC) — the buffer's ffmpeg subprocess has to be launched
with `TZ=Asia/Hong_Kong` explicitly (`env={**os.environ, "TZ": ...}` in
`asyncio.create_subprocess_exec`), or its filenames end up ~8h "behind" by
the time `segments_covering()`/`_cleanup_old()` parse them as HK time —
every segment looks instantly older than `buffer_window_seconds` and gets
deleted within one cleanup cycle (5s), so the buffer silently never holds
more than one near-empty file no matter how long it runs.

When `recorder.py`'s poller detects a dispense at time `T`, it waits
`post_roll_seconds` (default 45s) for the buffer to actually have footage
past `T`, then pulls every segment overlapping
`[T - pre_roll_seconds, T + post_roll_seconds]` (default 3s pre-roll) and
losslessly concatenates them (`ffmpeg -f concat -c copy`, same technique as
the weekly highlight reel) into the final clip — so the published clip now
starts *before* the dispense, not after it. Selection is whole-segment, not
frame-exact, so the actual pre-roll included is rounded up to the nearest
`buffer_segment_seconds` boundary (e.g. a 3s `pre_roll_seconds` against 5s
segments typically pulls in one full preceding segment, closer to ~5s of
real pre-roll than exactly 3). If the buffer has nothing
covering that window (just restarted, `petkit_h264` briefly down), it falls
back to the old duration-limited go2rtc export — a plain post-trigger clip
with no pre-roll, rather than no clip at all.

## Weekly highlight reel

`app/highlights.py` is a separate background task: sleeps until the next
Sunday 00:00 (Asia/Hong_Kong), then takes the **earliest clip of each of the
past 7 days** from `recordings/` and concatenates them
(`ffmpeg -f concat -c copy`, lossless) into
`highlights_dir/highlight_<start>_to_<end>.mp4` (default `./highlights`).
This folder has **no route and no frontend UI** — it's a private staging
area to review before manually deciding whether to upload anywhere (e.g.
YouTube); fetch it with `pct pull`/`scp` (see the `catcam-ct114-transfer`
skill). The scheduling loop wraps the compile call in `try`/`except` —
letting an exception escape would silently kill the `asyncio.Task` forever,
cancelling every future week until the next service restart.

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

## go2rtc config (live-stream pipeline)

`deploy/go2rtc/go2rtc.yaml` and `deploy/go2rtc/go2rtc.service` are a
checked-in mirror of the actual files running on CT 114
(`/opt/go2rtc/go2rtc.yaml`, `/etc/systemd/system/go2rtc.service`) — go2rtc
itself isn't installed from this repo (separate binary + systemd unit), but
its config carries the project's hardest-won, least-obvious fixes: the WHEP
auth-proxy workaround, the iOS Safari codec-mismatch fix, the burned-in
clock, and the VAAPI hardware-encode `exec:` command (see `my-homelab`
skill's catcam section for the full history of each). **After editing
either file on the CT, copy the change back into this folder and commit —
these files have no other version history.** Deploy with the
`catcam-ct114-transfer` skill's sync pattern:
`cat deploy/go2rtc/go2rtc.yaml | ssh root@upsn150-pve "pct exec 114 -- tee /opt/go2rtc/go2rtc.yaml > /dev/null" && ssh root@upsn150-pve "pct exec 114 -- systemctl restart go2rtc"`.

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
