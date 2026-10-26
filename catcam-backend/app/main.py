import asyncio
import hashlib
import hmac
import time as time_module
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import buffer, db, ha, highlights, recorder
from .config import get_settings
from .ratelimit import check_ip
from .scheduling import build_status, day_start, now


_feed_lock = asyncio.Lock()


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = get_settings()
    db.init_db(s.db_path)
    buffer.start()
    recorder.start()
    highlights.start()
    ha.start()
    yield
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
    body["announcement"] = db.get_announcement()
    if not body["ha_online"]:
        # HA unreachable overrides the time/cooldown-based reason — no point
        # telling a visitor "try again in 5 min" when the feeder itself is
        # down right now
        body["can_feed"] = False
        body["reason"] = "ha_offline"
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

    new_status = build_status(db.get_last_fed_at())
    return {"ok": True, "message": "強制餵咗喇！🔓🐱", **new_status}


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
        # source="admin" keeps this out of the public cooldown (last_fed_at)
        # just like /admin/feed — this button is for testing the dispense
        # pipeline itself, not for actually feeding on the visitor's behalf.
        # "admin_test:" (not "admin:") so it's excluded from the public
        # "訪客餵食咗" count the same way, while staying distinguishable in
        # feed_log from a real forced feed via /admin/feed
        db.record_feed(fed_at, f"admin_test:{ip}", s.feed_amount, source="admin")

    new_status = build_status(db.get_last_fed_at())
    return {"ok": True, "message": "模擬出糧完成，冇影響真實統計！🧪🐱", **new_status}


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
