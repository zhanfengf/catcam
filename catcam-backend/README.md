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

**"Pre-roll" and "24/7 buffering" aren't two alternatives — pre-roll is the
goal, continuous buffering is the only mechanism that can deliver it.**
Pre-roll means the final clip contains footage from *before* the trigger
moment (e.g. the cat approaching the bowl, not just already eating). But
once a trigger fires, it's too late to go back and capture what already
happened — if that time window wasn't already being recorded somewhere,
it's gone, no matter how fast the triggered capture logic runs. The only
way to have "the past" available when a trigger arrives is to already be
recording continuously into a rolling window *before* you know a trigger is
coming, then splice backwards into it once one does. There's no shortcut
that avoids the 24/7 part.

| | Old: trigger-after export | New: pre-roll buffer |
|---|---|---|
| When recording starts | Only after the dispense signal arrives | Always — 24/7, before any trigger exists |
| Can show the cat running over? | No — by the time it starts, the cat is often already eating | Yes — splices in footage from before `T` |
| What the clip contains | `[T, T + recording_seconds]` only | `[T - pre_roll_seconds, T + post_roll_seconds]` |
| Extra steady-state cost | None (idle until triggered) | One `-c copy` ffmpeg process running continuously (~0% CPU, no re-encode) |
| Disk | Only finished clips in `recordings/` | Finished clips + a small rolling `buffer/` (~3 min of segments, a few hundred MB) |
| If something's not ready | N/A | Falls back to the old trigger-after export, so a feed event never produces *nothing* |

### Timeline

```
buffer.py — continuous recording, -c copy, 5s segments, always running
════════════════════════════════════════════════════════════════════▶ time
                              │
                 ┌────────────┴────────────┐
                 │  real button press       │
                 │  (HA/PetKit lag: ~6-27s) │
                 └────────────┬────────────┘
                              │
                              ▼
                 T  ← recorder.py's poller detects the dispense here
                              │
        ┌─────────────────────┼─────────────────────────────────────┐
        │                     │                                     │
   T - pre_roll_seconds       │                       T + post_roll_seconds
   (clip starts here —        │                       (clip ends here — recorder.py
    already in the buffer,    │                        asyncio.sleep()s until this
    no waiting needed)        │                        moment actually arrives)
        │                     │                                     │
        └─────────────────────┴─────────────────────────────────────┘
                   final clip = concat(segments) → trim →
                   "Roll Roll running over"  →  "Roll Roll eating"
```

The left half of the final clip (`T - pre_roll_seconds` to `T`) is pulled
straight from segments the buffer already wrote *before* the trigger ever
happened — nothing to wait for. The right half (`T` to `T +
post_roll_seconds`) doesn't exist yet at detection time, so that's the part
`recorder.py` has to sleep through before it can assemble anything.

### Pipeline, step by step

1. **Continuous recording (`buffer.py`, always running).** A long-lived
   `ffmpeg -c copy` process pulls the live `petkit_h264` stream and writes
   it as rolling 5-second segment files into `buffer_dir`, deleting
   anything older than `buffer_window_seconds` (default 180s = 3 min). This
   is what makes "the past" available at all.
2. **Detecting the trigger (`recorder.py`'s poller).** Every 10s it checks
   HA's dispense counter. When it increases, it records the detection time
   `T` — already a few seconds after the real button press, due to the
   HA/PetKit round trip.
3. **Waiting for the post-roll window to actually happen.** The clip also
   needs footage up to `T + post_roll_seconds`, which doesn't exist yet at
   detection time — the task `asyncio.sleep(post_roll_seconds)`s in the
   background before continuing (non-blocking; other requests aren't
   affected).
4. **Selecting the segments covering `[T - pre_roll_seconds, T +
   post_roll_seconds]`.** `buffer.segments_covering()` picks every 5s
   segment file that overlaps that window.
5. **Lossless concat.** `ffmpeg -f concat -c copy` stitches the selected
   segments into one continuous stream — same technique as the weekly
   highlight reel, still no re-encode.
6. **Precise trim** *(design target — not yet implemented as of this
   writing; current code stops at step 5, so the actual pre-roll included
   is rounded up to the 5s segment grid rather than exact)*. The
   concatenated stream starts at the beginning of whichever segment
   happened to overlap the window first — not necessarily exactly
   `pre_roll_seconds` before `T`. A second pass (`ffmpeg -ss <offset> -i
   concat.mp4 -t <pre_roll_seconds + post_roll_seconds> -c copy
   final.mp4`) would trim to the exact requested window. Still `-c copy`,
   so it can only cut on a keyframe, not an arbitrary frame — at this
   encode's GOP size (`-g 50` @ ~27.5fps) that's roughly **±1.8s
   accuracy**, far tighter than the 5s segment grid, with no re-encode
   cost.
7. **Save + publish.** The result is written to `recordings_dir`, old clips
   past `recording_retention_days` get cleaned up, and it becomes visible
   via `GET /recordings` and playable at `/clips/<filename>.mp4`.
8. **Fallback.** If the buffer has nothing covering the window (service
   just restarted, buffer hasn't filled yet), step 4 comes back empty and
   the whole splice path is skipped in favor of the original
   duration-limited go2rtc export — a plain post-trigger clip with no
   pre-roll, rather than no clip at all.

Confirmed via HA's history API how much HA/PetKit cloud sync lag there
really is between a real dispense and the backend even learning about it —
~6s for a manual app feed, ~27s for a scheduled auto-feed — which is why
step 2 above can't just be "trigger fast enough," the cat can already be at
the bowl before the signal even arrives.

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
