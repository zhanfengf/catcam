# 🐱 CatCam

A public **"feed my cat"** web app. Viewers open a link, watch a live stream of
the cat, and press a button to dispense a portion of food — subject to sensible
rules (shared cooldown, open hours, anti-spam). The button ultimately triggers a
real smart feeder through Home Assistant.

```
Viewer's browser
      │
      ▼
SvelteKit frontend  ──►  FastAPI backend  ──►  Home Assistant REST API  ──►  🍚 feeder
   (static SPA)          (rules + state)        (text.*_manual_feed)
```

## Why I built it

I wanted a small but complete full-stack project on real hardware: a camera and
a smart pet feeder at home, exposed safely to the public internet. It turned
into a nice exercise in API design, concurrency, rate limiting, and keeping
secrets on the server side — never in the browser.

## Repository layout

| Folder             | What it is                                                        |
| ------------------ | ----------------------------------------------------------------- |
| [`catcam-backend`](./catcam-backend)   | Python + FastAPI service. Enforces feeding rules and calls Home Assistant. Keeps the HA token server-side. |
| [`catcam-frontend`](./catcam-frontend) | SvelteKit static SPA (Cantonese UI). Live stream, status, countdown, and the feed button. |

Each folder has its own README with setup and deployment details.

## Feeding rules

- **Link-only** — no login required.
- **Shared cooldown** — 120 minutes between feeds, across all visitors.
- **Open hours** — 07:00–23:59 (Asia/Hong_Kong).
- **Fixed portion** — one standard amount per feed.
- **Per-IP anti-spam** — stops a single client hammering the endpoint (separate from the feeding quota).
- State (`last_fed_at`) is persisted in **SQLite**, so restarts keep the limits.

## Tech stack

- **Backend:** Python, FastAPI, Uvicorn, httpx, SQLite
- **Frontend:** SvelteKit (static adapter), Vite
- **Infra:** Caddy (static serving + reverse proxy), Cloudflare Tunnel, Home Assistant

## Quick start

Run the two parts separately during development:

```bash
# Backend — see catcam-backend/README.md
cd catcam-backend
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env        # then set HA_TOKEN
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8080

# Frontend — see catcam-frontend/README.md
cd catcam-frontend
cp .env.example .env
npm install
npm run dev                 # http://localhost:5173
```

## Configuration & secrets

Both parts are configured via `.env` files. A `.env.example` template is
provided in each folder — copy it to `.env` and fill in your own values. The
real `.env` files are **git-ignored and never committed**; in particular the
Home Assistant long-lived access token lives only in the backend's `.env`.

## Roadmap

- Embed the live RTSP camera stream (via go2rtc / HLS) in place of the current placeholder.
