import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import db, ha
from .config import get_settings
from .ratelimit import check_ip
from .scheduling import build_status, day_start, now


_feed_lock = asyncio.Lock()


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = get_settings()
    db.init_db(s.db_path)
    yield


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


@app.get("/status")
async def status():
    last = db.get_last_fed_at()
    body = build_status(last)
    body["fed_today"] = db.count_feeds_today(day_start(now()))
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


@app.get("/health")
async def health():
    return {"ok": True}
