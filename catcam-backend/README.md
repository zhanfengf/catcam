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
- `last_fed_at` persisted in **SQLite**, so restarts keep the limit. Public
  `/feed`, owner force-feed `/admin/feed`, and scheduled auto-feed calls all
  advance this timestamp. `/admin/feed` may bypass a cooldown already in
  progress, but its successful dispense starts a fresh 120-minute cooldown.
  Only `/admin/feed-test` leaves the countdown untouched.
- `fed_today` (shown as "訪客食咗"/"Fed by visitors") counts **public feeds
  only** — admin-channel feeds are excluded, by design.

## Endpoints

| Method | Path             | Purpose                                                |
| ------ | ---------------- | ------------------------------------------------------- |
| GET    | `/status`             | Can we feed now? next feed time, window, visitor fed-today count, `ha_online`, `stream_online`, `announcement`, `auto_feed_windows`. |
| POST   | `/feed`               | Try to feed. Enforces all rules, then calls HA.          |
| POST   | `/admin/feed`         | HMAC-signed bypass (cooldown + open hours); a successful force-feed starts a fresh public cooldown. |
| POST   | `/admin/feed-test`    | HMAC-signed. Dispenses for real (tests the pipeline end to end) but excluded from the public cooldown and the "訪客餵食咗" count. |
| POST   | `/admin/wet-food`     | HMAC-signed. Records an owner-served wet-food meal, restarts public cooldown, but does not call HA, dispense kibble, or record a clip. |
| POST   | `/admin/announcement` | HMAC-signed. Sets (or clears, with `""`) the announcement banner text. |
| POST   | `/admin/auto-feed`    | HMAC-signed. Sets the list of `HH:MM-HH:MM` auto-feed safety-net windows. |
| GET    | `/admin/history`      | HMAC-signed. Today's feed events, straight from PetKit (not our own log). |
| GET    | `/recordings`         | Public. List of this week's 60s feed clips (filename + timestamp). |
| GET    | `/activity`           | Public. Today's feed events for the two-phase activity feed (`fed_at` + `clip` + `clip_ready_at`). |
| GET    | `/health`             | Liveness check.                                          |

`POST /feed` returns `200` on success, `403` outside hours, `429` cooldown or
spam, `502` if HA is unreachable.

`POST /admin/feed`, `/admin/feed-test`, `/admin/wet-food`,
`/admin/announcement`, and `GET /admin/history` are the secret-channel
endpoints the frontend calls after
unlocking (tap the logo 5×, enter `ADMIN_TOKEN`). Every request must be
HMAC-SHA256 signed with `ADMIN_TOKEN` over `{METHOD}:{PATH}:{timestamp}` and
include a timestamp within `ADMIN_SIG_WINDOW_SECONDS` — see
`verify_admin_signature()` in `app/main.py`. No plaintext password crosses
the wire. Both `/admin/feed` and `/admin/feed-test` skip cooldown/open-hours
checks and log to `feed_log`. A real `/admin/feed` updates public
`last_fed_at`, while `/admin/feed-test` deliberately leaves it alone. Neither
is included in `fed_today`; they're told apart by the `ip` column's prefix:

- `admin:<ip>` — `/admin/feed`, the owner's real "feed now regardless"
  bypass; after dispensing, the public countdown restarts in full.
- `admin_test:<ip>` — `/admin/feed-test`, for exercising the real dispense
  pipeline (HA call, recording trigger) on demand without it looking like
  either a real forced feed or a real visitor.
- `admin_wet_food:<ip>` — `/admin/wet-food`, a real owner-served meal with
  `amount=NULL` because no dry food leaves the feeder. It restarts the public
  cooldown but is excluded from the visitor count.
- no prefix — a real `/feed` call from a visitor.

`count_feeds_today()` (the "訪客餵食咗" stat) excludes all admin prefixes.

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
6. **Precise trim.** The concatenated stream (from step 5) starts at the
   beginning of whichever segment happened to overlap the window first —
   not necessarily exactly `pre_roll_seconds` before `T`. A second pass
   (`ffmpeg -ss <offset> -i concat.mp4 -t <pre_roll_seconds +
   post_roll_seconds> -c copy final.mp4`) trims it to the exact requested
   window. Still `-c copy`, so it can only cut on a keyframe, not an
   arbitrary frame — at this encode's GOP size (`-g 50` @ ~27.5fps) that's
   roughly **±1.8s accuracy**, far tighter than the 5s segment grid, with
   no re-encode cost.
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

## HA connectivity check

`app/ha.py` runs a background poll (every 15s, independent of any feed
attempt) hitting `{HA_URL}/api/` and caching the result in `is_online()`.
`GET /status` includes this as `ha_online`, and overrides `can_feed`/`reason`
to `false`/`"ha_offline"` when it's down — so the frontend can disable the
feed button and show "餵食機離線" within ~15s of HA actually going
unreachable, instead of a visitor hitting the button and only then getting a
`502`. A real HA outage also takes down the camera feed (go2rtc's upstream
WHEP pull goes through HA too), so both go dark together — see the
`feed-ha-offline.png` screenshot in the root README.

## Stream watchdog (stream_offline + auto-recovery)

`ha_online` only answers "is HA reachable" — but the common failure here is
the opposite: HA stays up and keeps reporting the camera as `streaming` while
the **PetKit cloud WHEP session silently drops** and no frames flow. `app/
streamwatch.py` closes that gap with a separate liveness signal.

It judges liveness off the **24/7 pre-roll buffer** (`app/buffer.py`): that
ffmpeg writes a data-bearing `~5s` segment continuously while frames flow, so
`stream_online()` is just "is the newest segment above a byte floor *and* its
mtime fresh (`< stream_stale_seconds`, default 30s)". The byte floor matters —
when go2rtc is up but starved, its ffmpeg reconnects and churns near-empty
segments with fresh mtimes; counting those would falsely read "online", so
anything under `buffer_min_segment_bytes` (20KB) doesn't count.

`GET /status` returns `stream_online`; when the feeder is fine but the stream
is stalled, `can_feed`/`reason` are overridden to `false`/`"stream_offline"`
(layered *after* the `ha_offline` check), so the public feed button disables —
no point feeding a cat nobody can see.

A background loop (every 15s) also **auto-recovers**: after an outage lasts
`stream_recover_after_seconds` (default 75s) it runs the same sequence as
`scripts/fix-catcam-stream.sh` in the my-homelab skill — reload the PetKit
integration (`ha.reload_petkit()`), wait, restart go2rtc — then waits
`stream_recover_cooldown_seconds` (default 300s) before trying again so a
genuine cloud outage isn't hammered. Set `stream_auto_recover=false` to leave
it detect-only.

**go2rtc restart without sudo:** this CT has no `sudo`. Instead the backend
(running as the unprivileged `catcam` user) `touch`es a trigger file it owns;
a root-run systemd **path unit** (`deploy/go2rtc-restart.path` →
`deploy/go2rtc-restart.service`) watches that file and runs `systemctl restart
go2rtc`. So `catcam` gains exactly one capability — restart go2rtc — and no
general root. Install steps are in the header of `go2rtc-restart.path`.

### Outage alerts (Telegram)

Optional push notifications (`app/notify.py`): streamwatch fires **one**
`🔴 直播斷咗` message once an outage is sustained (after
`stream_recover_after_seconds`, so a brief hiccup never pings) and a
`🟢 復原咗` message with the outage duration when it returns. Fire-and-forget
so the watch loop never blocks on Telegram, and a complete no-op when the
credentials aren't set — the watchdog still detects + auto-recovers silently.

Set up:

1. In Telegram, message **@BotFather** → `/newbot` → copy the bot **token**.
2. Open your new bot and send it any message (a bot can't message a user who
   hasn't talked to it first).
3. `curl https://api.telegram.org/bot<TOKEN>/getUpdates` and read
   `result[].message.chat.id` — that's your **chat id**.
4. Put both in `.env`: `TELEGRAM_BOT_TOKEN=…`, `TELEGRAM_CHAT_ID=…`, restart.

> **Gotcha — force IPv4:** CT 114 resolves `api.telegram.org` to an IPv6
> address but has no IPv6 route, so a default client (and plain `curl`) hangs
> until timeout. `notify.py` binds the socket to the IPv4 wildcard
> (`local_address="0.0.0.0"`); from the shell use `curl -4`.

### Visitor-feed alerts (Telegram)

With the same Telegram credentials, each **genuine web-visitor feed** also
pushes an alert once its clip is ready (~1 min later, so the link is live):

```
🍚 有訪客餵咗 Roll Roll
🕐 2026-10-27 08:41
🌐 203.0.113.45 · HK
📹 https://cat.kelvinp.work/clips/2026-10-27_084100.mp4
```

How it's wired: `/feed` stashes the visitor's IP + country in a short-lived
`visitor_feed_pending` marker; when the recorder sees the matching dispense it
pops the marker and, once the clip finishes, `recorder._notify_visitor_feed`
sends the alert. **Only site `/feed` sets that marker** — PetKit-app, physical
button, scheduled auto-feed and admin feeds leave no marker (and have no IP),
so none of them are pushed. Country is Cloudflare's own `cf-ipcountry` header
(country-level only — no external geo-IP, so no city/district); the clip link
is built off `public_base_url`. Turn off with `notify_visitor_feeds=false`.

## Announcement banner

A free-text banner the owner can push to every visitor, shown once per
distinct message as soon as the page loads. `POST /admin/announcement` with
`{"text": "..."}` sets it (truncated to 500 chars server-side); an empty
string hides the banner. `GET /status` returns the current text as
`announcement` — no separate endpoint to fetch it, since the frontend
already polls `/status` every 15s. The frontend decides whether to (re-)show
the popup by comparing this text against what it last dismissed
(`localStorage`), so editing the announcement makes it pop up again for
everyone, even visitors who already dismissed a previous message.

Two separate things happen on every save, deliberately not conflated into
one table:
- `state` (key `announcement`, the same key-value table `last_fed_at` lives
  in) holds **only the current value** — `set_announcement()` upserts this
  one row in place. This is what `/status` reads.
- `announcement_log` (its own table, `id, text, created_at`) gets a **new
  row appended** on every save, unconditionally — an audit trail of what was
  pushed and when. Nothing reads it yet (no endpoint/UI), but it means "what
  did the banner say last Tuesday" has a real answer later without having
  to have thought to screenshot it at the time.

## Activity feed (two-phase)

A public, read-only feed shown beside the live video (the frontend's 餵食動態
column). Each real feeder dispense produces **two** chat-style messages about a minute
apart: "🍚 餵咗 Roll Roll" the moment the feed is detected, then "📹 錄影好咗"
with a watch-back link once the clip finishes rendering.

Backed by its own `feed_event` table (`id, fed_at, clip, clip_ready_at`),
written by `recorder.py` off the **same `times_dispensed` signal** as the clip
recorder — so it covers *every* real dispense (site, PetKit app, physical
button, scheduled auto-feed), not just site-triggered ones:

- On detection (`_poll_loop`), a row is inserted immediately with `clip` NULL
  — this is what the "餵咗" line reads, ~1 min before any clip exists.
- Once the clip is written, `set_feed_event_clip()` fills in `clip` +
  `clip_ready_at` on that same row (matched by `fed_at`) — the "錄影好咗" line.
  If the clip ultimately fails to render, the row just stays clip-less and only
  the "餵咗" line ever shows, which is the honest outcome.

An owner-served wet-food meal is the intentional exception: `/admin/wet-food`
does not touch Home Assistant or PetKit, so it inserts its own
`feed_event.source="admin_wet_food"` row synchronously. The frontend shows the
same "🍚 啱啱餵咗 Roll Roll" line immediately, but knows this source never
expects a clip and therefore does not show "錄影整緊…". It does not appear in
`/admin/history`, whose source of truth remains PetKit's physical dispense
counter.

`GET /activity` returns today's rows (newest-first); the frontend expands each
into the two lines and sorts them by time. Old rows are pruned alongside the
clips in `_cleanup_old()` (`recording_retention_days`). This is deliberately
**separate from `feed_log`**: `feed_log` backs the "訪客餵食咗" visitor stat
(site feeds only, no clip info), `feed_event` backs the public activity feed
(all dispenses, with clips) — two tables, two jobs, not one row stretched over
both.

## Auto-feed windows (safety net)

`app/autofeed.py` is a background scheduler (checks every 60s) that makes sure
Roll Roll doesn't go unfed if no visitor shows up. The owner configures a list
of `HH:MM-HH:MM` windows via `POST /admin/auto-feed` (stored in `state` key
`auto_feed_windows`, also returned in `/status` so the admin panel can prefill);
each window, **if nobody fed the cat during it**, triggers one auto-feed when it
closes.

An owner force-feed or wet-food meal inside a configured window immediately
marks that exact window handled, even when the window is longer than 120
minutes. The owner action and scheduler share one lock, so a click right at the
window boundary cannot race the scheduler into a duplicate dispense.

Per window, once its end time has passed today and it hasn't been handled yet:
- If `last_fed_at` is within one public cooldown of the window close, it's
  marked handled with no feed. Owner force-feeds inside the window have already
  marked it handled through the immediate path above.
- Otherwise, within a `_GRACE_MINUTES` (60) grace after the end (so a service that
  was down through the window doesn't feed hours late), it dispenses: sets a
  `state.auto_feed_pending` marker, calls `ha.dispense()`, and records the feed
  via `record_feed(..., "auto:system", source="auto")`. Past the grace it's just
  marked handled without feeding.

`auto_feed_handled` (`state`, a `{window: "YYYY-MM-DD"}` map) is persisted so a
restart never re-fires a window already handled today. The auto-feed **does**
advance the public cooldown (`record_feed` advances `last_fed_at` for every
source except `admin_test`), matching the "下次可以餵：120 分鐘後" message, and is
tagged `auto:` in `feed_log` so it's excluded from the "訪客餵食咗" count.

The `feed_event` row for an auto-feed is created by the **recorder** (the sole
feed_event writer), not the scheduler: when the recorder's poller detects the
dispense, it calls `pop_auto_feed_pending()` and, if the marker is fresh (<90s),
tags that event `source="auto"` with the window in `note`. The frontend renders
those as the 🤖 "冇人喺 …餵…自動餵咗" line (still two-phase — the clip-ready line
follows). This keeps one event per real dispense (no duplicate) while still
giving the auto-feed both its special message and a clip.

Owner force-feeds use the same asynchronous detection path. A successful
`POST /admin/feed` stores a short-lived `state.admin_feed_pending` marker; when
the recorder sees the matching PetKit counter increase, it consumes that
marker and writes `feed_event.source="admin"`. This keeps the activity event
and its clip attached to the real dispense while avoiding the old generic
`visitor` fallback for owner-triggered feeds.

## Deploy in the LXC (Debian 13, no Docker)

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
