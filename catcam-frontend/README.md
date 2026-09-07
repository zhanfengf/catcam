# CatCam Frontend (SvelteKit, static)

純前端 SPA（廣東話介面）：直播畫面 + 狀態 + 一個「餵貓」大掣。build 出嚟係靜態
檔，唔需要 Node runtime，靠 Caddy 一齊 serve 靜態檔同反向代理後端 API。

```
觀眾 → cat.kelvinp.work → Caddy(:80, CT 114)
        ├─ /            → 靜態 SvelteKit build
        └─ /status /feed → reverse_proxy 127.0.0.1:8080（FastAPI 後端）
```

## Build（可以喺 macOS 或 CT 內做）

```bash
cd catcam-frontend
cp .env.example .env      # 通常留空即可（同源）
npm install
npm run build             # 產出 build/ 資料夾
```

`.env` 兩個掣：
- `VITE_API_BASE` — 留空 = 同源（Caddy 代理）。前後端唔同網域先填。
- `VITE_STREAM_URL` — 直播串流網址。留空顯示 placeholder；等 go2rtc 好咗先填。

改完 `.env` 要**重新 `npm run build`**（Vite 喺 build 時 inline 呢啲值）。

## 部署到 CT 114（catcam）

1. 將 `build/` 內容放到 CT 的 `/opt/catcam-frontend/`：
   ```bash
   # macOS build 完，送上 host 再入 CT（同後端一樣經 pct）
   tar -czf catcam-build.tgz -C build .
   scp catcam-build.tgz root@ip:/root/
   ssh root@ip
   pct push 114 /root/catcam-build.tgz /root/catcam-build.tgz
   pct exec 114 -- mkdir -p /opt/catcam-frontend
   pct exec 114 -- tar -xzf /root/catcam-build.tgz -C /opt/catcam-frontend
   ```

2. 喺 CT 裝 Caddy 並套用設定：
   ```bash
   pct enter 114
   apt install -y debian-keyring debian-archive-keyring apt-transport-https curl
   curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
     | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
   curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
     > /etc/apt/sources.list.d/caddy-stable.list
   apt update && apt install -y caddy

   # 套用 Caddyfile（已喺 deploy/ 內）
   cp /opt/catcam-frontend/Caddyfile /etc/caddy/Caddyfile   # 或手動貼
   systemctl restart caddy
   ```

3. Cloudflare Tunnel 加一條 route：`cat.kelvinp.work` → `http://ip:80`

## 本機預覽（開發用）

```bash
npm run dev        # http://localhost:5173，會打你 VITE_API_BASE 設定嘅後端
```

開發時把 `VITE_API_BASE` 設成後端可達位址（例如 `http://ip:8080`），
並記得後端 `.env` 的 `CORS_ORIGINS` 要允許 `http://localhost:5173`。

## 之後接直播

拿到 RTSP cam + go2rtc 後，把 `VITE_STREAM_URL` 設成串流網址（HLS `.m3u8`
或 go2rtc 的 stream URL），重新 build，placeholder 會換成真直播。HLS 可能要加
`hls.js`；到時再補。
