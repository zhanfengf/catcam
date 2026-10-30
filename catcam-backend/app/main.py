import asyncio
import hashlib
import hmac
import logging
import time as time_module
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import autofeed, buffer, db, feedwatch, ha, highlights, recorder, streamwatch
from .config import get_settings
from .ratelimit import check_ip
from .scheduling import build_status, day_start, now

# Without this, every module's `log.info(...)` (streamwatch's auto-recovery
# trail, in particular) is silently dropped — Python's root logger defaults
# to WARNING with no handler attached, so journalctl only ever shows uvicorn's
# own access/error lines, never the app's own INFO breadcrumbs.
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

_feed_lock = asyncio.Lock()


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = get_settings()
    db.init_db(s.db_path)
    buffer.start()
    recorder.start()
    highlights.start()
    ha.start()
    autofeed.start()
    feedwatch.start()
    streamwatch.start()
    yield
    streamwatch.stop()
    feedwatch.stop()
    autofeed.stop()
    ha.stop()
    recorder.stop()
    highlights.stop()
    buffer.stop()


app = FastAPI(title="CatCam Feeder API", lifespan=lifespan)

_settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=_settings.cors_list,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


def client_ip(request: Request) -> str:
    header = get_settings().client_ip_header
    return (
        request.headers.get(header)
        or (request.client.host if request.client else "unknown")
    )


def verify_admin_signature(method: str, path: str, timestamp: str, signature: str) -> bool:
    s = get_settings()
    if not s.admin_token or not timestamp or not signature:
        return False
    try:
        ts = int(timestamp)
    except ValueError:
        return False
    if abs(time_module.time() - ts) > s.admin_sig_window_seconds:
        return False
    expected = hmac.new(
        s.admin_token.encode(),
        f"{method}:{path}:{timestamp}".encode(),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


@app.get("/status")
async def status():
    last = db.get_last_fed_at()
    body = build_status(last)
    body["fed_today"] = db.count_feeds_today(day_start(now()))
    body["ha_online"] = ha.is_online()
    body["stream_online"] = streamwatch.is_online()
    body["announcement"] = db.get_announcement()
    body["auto_feed_windows"] = db.get_auto_feed_windows()
    fasting = db.get_fasting()
    body["fasting"] = fasting["active"]
    body["fasting_reason"] = fasting["reason"]
    if fasting["active"]:
        # admin-initiated fast overrides every other reason — it's a
        # deliberate decision, not an outage, so a visitor should see "Roll
        # Roll is on a diet" rather than an unrelated ha_offline/stream_offline
        # message that happens to also be true at the same moment
        body["can_feed"] = False
        body["reason"] = "fasting"
    elif not body["ha_online"]:
        # HA unreachable overrides the time/cooldown-based reason — no point
        # telling a visitor "try again in 5 min" when the feeder itself is
        # down right now
        body["can_feed"] = False
        body["reason"] = "ha_offline"
    elif not body["stream_online"]:
        # feeder itself is fine, but the camera stream has stalled (PetKit
        # cloud WHEP drop). No point letting a public viewer feed when they
        # can't actually see Roll Roll — mirror the ha_offline treatment.
        body["can_feed"] = False
        body["reason"] = "stream_offline"
    return body


@app.post("/feed")
async def feed(request: Request):
    ip = client_ip(request)

    if not check_ip(ip):
        return JSONResponse(
            status_code=429,
            content={"ok": False, "reason": "too_many_requests",
                     "message": "撳得太密啦，唞一唞先"},
        )

    async with _feed_lock:
        last = db.get_last_fed_at()
        st = build_status(last)
        if not st["can_feed"]:
            code = 403 if st["reason"] == "outside_hours" else 429
            msg = ("而家係休息時間，餵食時段 "
                   f"{st['window']['open']}–{st['window']['close']}"
                   if st["reason"] == "outside_hours"
                   else "啱啱先餵咗，要等下次先得")
            return JSONResponse(
                status_code=code,
                content={"ok": False, **st, "message": msg},
            )


        try:
            await ha.dispense(st["amount"])
        except ha.HAError as exc:
            return JSONResponse(
                status_code=502,
                content={"ok": False, "reason": "ha_error",
                         "message": "餵食機而家連唔到，遲啲再試",
                         "detail": str(exc)},
            )

        fed_at = now()
        db.record_feed(fed_at, ip, st["amount"])
        # mark this as a genuine web-visitor feed so the recorder can push a
        # Telegram alert with IP + country once the clip is ready. Country is
        # Cloudflare's own geolocation header (no external geo-IP lookup).
        country = request.headers.get("cf-ipcountry")
        db.set_visitor_feed_pending(ip, country, fed_at)

    new_status = build_status(db.get_last_fed_at())
    return {"ok": True, "message": "餵咗喇！🐱", **new_status}


@app.post("/admin/feed")
async def admin_feed(request: Request):
    ip = client_ip(request)

    if not check_ip(ip):
        return JSONResponse(
            status_code=429,
            content={"ok": False, "reason": "too_many_requests",
                     "message": "撳得太密啦，唞一唞先"},
        )

    timestamp = request.headers.get("x-admin-timestamp", "")
    signature = request.headers.get("x-admin-signature", "")
    if not verify_admin_signature("POST", "/admin/feed", timestamp, signature):
        return JSONResponse(
            status_code=403,
            content={"ok": False, "reason": "unauthorized",
                     "message": "密碼唔啱或者已過期"},
        )

    async with _feed_lock:
        # Serialize this dispense with the auto-feed boundary check. Without
        # the shared lock, a force-feed at exactly the window end could race
        # the scheduler and both calls could reach Home Assistant.
        async with autofeed.scheduler_lock():
            s = get_settings()
            try:
                await ha.dispense(s.feed_amount)
            except ha.HAError as exc:
                return JSONResponse(
                    status_code=502,
                    content={"ok": False, "reason": "ha_error",
                             "message": "餵食機而家連唔到，遲啲再試",
                             "detail": str(exc)},
                )

            fed_at = now()
            db.record_feed(fed_at, f"admin:{ip}", s.feed_amount, source="admin")
            # The recorder sees the PetKit counter increase asynchronously.
            # Leave it a short-lived marker so the corresponding feed_event
            # is tagged as admin instead of the generic visitor fallback.
            db.set_admin_feed_pending(fed_at)
            # Force-feed bypasses the cooldown that was already running, but
            # the successful dispense becomes the new public cooldown anchor.
            # Mark any containing auto-feed window covered before releasing
            # the scheduler lock.
            autofeed.mark_windows_covered(fed_at)

    new_status = build_status(db.get_last_fed_at())
    return {
        "ok": True,
        "message": f"強制餵咗喇！公開餵食 {s.cooldown_minutes} 分鐘後再開 🔓🐱",
        **new_status,
    }


@app.post("/admin/feed-test")
async def admin_feed_test(request: Request):
    ip = client_ip(request)

    if not check_ip(ip):
        return JSONResponse(
            status_code=429,
            content={"ok": False, "reason": "too_many_requests",
                     "message": "撳得太密啦，唞一唞先"},
        )

    timestamp = request.headers.get("x-admin-timestamp", "")
    signature = request.headers.get("x-admin-signature", "")
    if not verify_admin_signature("POST", "/admin/feed-test", timestamp, signature):
        return JSONResponse(
            status_code=403,
            content={"ok": False, "reason": "unauthorized",
                     "message": "密碼唔啱或者已過期"},
        )

    async with _feed_lock:
        s = get_settings()
        try:
            await ha.dispense(s.feed_amount)
        except ha.HAError as exc:
            return JSONResponse(
                status_code=502,
                content={"ok": False, "reason": "ha_error",
                         "message": "餵食機而家連唔到，遲啲再試",
                         "detail": str(exc)},
            )

        fed_at = now()
        # source="admin_test" keeps this out of the public cooldown
        # (last_fed_at). This button is for testing the dispense pipeline
        # itself, not for actually feeding on the visitor's behalf.
        # "admin_test:" (not "admin:") so it's excluded from the public
        # "訪客餵食咗" count the same way, while staying distinguishable in
        # feed_log from a real forced feed via /admin/feed
        db.record_feed(fed_at, f"admin_test:{ip}", s.feed_amount, source="admin_test")

    new_status = build_status(db.get_last_fed_at())
    return {"ok": True, "message": "模擬出糧完成，冇影響真實統計！🧪🐱", **new_status}


@app.post("/admin/wet-food")
async def admin_wet_food(request: Request):
    ip = client_ip(request)

    if not check_ip(ip):
        return JSONResponse(
            status_code=429,
            content={"ok": False, "reason": "too_many_requests",
                     "message": "撳得太密啦，唞一唞先"},
        )

    timestamp = request.headers.get("x-admin-timestamp", "")
    signature = request.headers.get("x-admin-signature", "")
    if not verify_admin_signature("POST", "/admin/wet-food", timestamp, signature):
        return JSONResponse(
            status_code=403,
            content={"ok": False, "reason": "unauthorized",
                     "message": "密碼唔啱或者已過期"},
        )

    async with _feed_lock:
        # Wet food is a real owner-provided meal, so it shares the public
        # cooldown and covers an active auto-feed window. It deliberately does
        # not call Home Assistant: no kibble is dispensed and the recorder's
        # PetKit counter never changes.
        async with autofeed.scheduler_lock():
            fed_at = now()
            db.record_feed(
                fed_at,
                f"admin_wet_food:{ip}",
                None,
                source="admin_wet_food",
            )
            db.add_feed_event(fed_at, source="admin_wet_food")
            autofeed.mark_windows_covered(fed_at)

    new_status = build_status(db.get_last_fed_at())
    return {
        "ok": True,
        "message": "記低咗今餐罐罐！🥫🐱",
        "fed_at": fed_at.isoformat(),
        **new_status,
    }


@app.post("/admin/announcement")
async def admin_set_announcement(request: Request):
    ip = client_ip(request)

    if not check_ip(ip):
        return JSONResponse(
            status_code=429,
            content={"ok": False, "reason": "too_many_requests",
                     "message": "撳得太密啦，唞一唞先"},
        )

    timestamp = request.headers.get("x-admin-timestamp", "")
    signature = request.headers.get("x-admin-signature", "")
    if not verify_admin_signature("POST", "/admin/announcement", timestamp, signature):
        return JSONResponse(
            status_code=403,
            content={"ok": False, "reason": "unauthorized",
                     "message": "密碼唔啱或者已過期"},
        )

    try:
        body = await request.json()
    except ValueError:
        body = {}
    text = str(body.get("text") or "").strip()[:500]
    db.set_announcement(text, now())

    return {"ok": True, "announcement": text}


@app.post("/admin/fasting")
async def admin_set_fasting(request: Request):
    ip = client_ip(request)

    if not check_ip(ip):
        return JSONResponse(
            status_code=429,
            content={"ok": False, "reason": "too_many_requests",
                     "message": "撳得太密啦，唞一唞先"},
        )

    timestamp = request.headers.get("x-admin-timestamp", "")
    signature = request.headers.get("x-admin-signature", "")
    if not verify_admin_signature("POST", "/admin/fasting", timestamp, signature):
        return JSONResponse(
            status_code=403,
            content={"ok": False, "reason": "unauthorized",
                     "message": "密碼唔啱或者已過期"},
        )

    try:
        body = await request.json()
    except ValueError:
        body = {}
    reason = str(body.get("reason") or "").strip()[:200]
    db.set_fasting(True, reason)

    return {"ok": True, "fasting": True, "fasting_reason": reason}


@app.post("/admin/fasting/clear")
async def admin_clear_fasting(request: Request):
    ip = client_ip(request)

    if not check_ip(ip):
        return JSONResponse(
            status_code=429,
            content={"ok": False, "reason": "too_many_requests",
                     "message": "撳得太密啦，唞一唞先"},
        )

    timestamp = request.headers.get("x-admin-timestamp", "")
    signature = request.headers.get("x-admin-signature", "")
    if not verify_admin_signature("POST", "/admin/fasting/clear", timestamp, signature):
        return JSONResponse(
            status_code=403,
            content={"ok": False, "reason": "unauthorized",
                     "message": "密碼唔啱或者已過期"},
        )

    db.set_fasting(False, "")

    return {"ok": True, "fasting": False}


@app.post("/admin/auto-feed")
async def admin_set_auto_feed(request: Request):
    ip = client_ip(request)

    if not check_ip(ip):
        return JSONResponse(
            status_code=429,
            content={"ok": False, "reason": "too_many_requests",
                     "message": "撳得太密啦，唞一唞先"},
        )

    timestamp = request.headers.get("x-admin-timestamp", "")
    signature = request.headers.get("x-admin-signature", "")
    if not verify_admin_signature("POST", "/admin/auto-feed", timestamp, signature):
        return JSONResponse(
            status_code=403,
            content={"ok": False, "reason": "unauthorized",
                     "message": "密碼唔啱或者已過期"},
        )

    try:
        body = await request.json()
    except ValueError:
        body = {}
    windows, invalid = autofeed.normalise_windows(body.get("windows"))
    if invalid:
        return JSONResponse(
            status_code=422,
            content={
                "ok": False,
                "reason": "invalid_auto_feed_window",
                "message": "時段必須同日完結、開始早過結束，而且結束時間最遲係 22:59",
                "invalid_windows": invalid,
            },
        )

    async with autofeed.scheduler_lock():
        deferred = autofeed.replace_windows(windows, now())

    return {
        "ok": True,
        "auto_feed_windows": windows,
        "starts_tomorrow": deferred,
    }


@app.get("/admin/history")
async def admin_history(request: Request):
    timestamp = request.headers.get("x-admin-timestamp", "")
    signature = request.headers.get("x-admin-signature", "")
    if not verify_admin_signature("GET", "/admin/history", timestamp, signature):
        return JSONResponse(
            status_code=403,
            content={"ok": False, "reason": "unauthorized",
                     "message": "密碼唔啱或者已過期"},
        )

    today_start = day_start(now())
    hours = max(0.1, (now() - today_start).total_seconds() / 3600)
    try:
        petkit_log = await ha.get_feed_history(hours=hours)
    except ha.HAError as exc:
        return JSONResponse(
            status_code=502,
            content={"ok": False, "reason": "ha_error",
                      "message": "攞唔到紀錄", "detail": str(exc)},
        )

    # chunked lookback can overshoot into yesterday — keep only today's HK events
    cutoff = today_start.strftime("%Y-%m-%dT%H:%M:%S")
    petkit_log = [t for t in petkit_log if t >= cutoff]

    return {"ok": True, "petkit_log": petkit_log}


@app.get("/activity")
async def activity():
    # today's feed events for the public two-phase activity feed: each row is
    # a real dispense with `clip` NULL until its recording finishes ~1 min
    # later. the frontend expands each into a "fed" line (at fed_at) and, once
    # present, a "clip ready" line (at clip_ready_at)
    return {"ok": True, "events": db.get_feed_events(day_start(now()))}


@app.get("/recordings")
async def recordings():
    return {"ok": True, "recordings": recorder.list_recordings()}


@app.get("/health")
async def health():
    return {"ok": True}
