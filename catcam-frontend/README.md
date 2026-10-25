# CatCam Frontend (SvelteKit, static)

純前端 SPA(繁中/EN 雙語切換):直播畫面 + 狀態 + 一個「餵貓」大掣,加一個
藏起嚟嘅管理通道(連按 logo 5 次)俾自己繞過冷卻時間。build 出嚟係靜態檔,
唔需要 Node runtime,靠 Caddy 一齊 serve 靜態檔、反向代理後端 API,同代理
go2rtc 嘅直播串流。

```
觀眾 → cat.kelvinp.work → Caddy(:80, CT 114)
        ├─ /                       → 靜態 SvelteKit build
        ├─ /status /feed /admin/feed → reverse_proxy 127.0.0.1:8080（FastAPI 後端）
        └─ /camera/*               → reverse_proxy 127.0.0.1:1984（go2rtc，rewrite 做 /api/*）
```

## 直播畫面

唔係靠 env 變數設定串流網址。流程係:go2rtc 用 WHEP 去 pull Home
Assistant 嘅 PetKit camera（經一個內部 Caddy proxy 注入 HA Bearer
token，因為 go2rtc 嘅 WHEP client 唔會自己帶 auth header），再用
WebSocket + MSE 經 `/camera/ws?src=petkit_h264` 重新 serve 出嚟。前端
用 `src/lib/video-rtc.js`（go2rtc 官方版本，原封不動 vendor 咗入嚟）
揸呢條 WS 連線，再喺 `+page.svelte` 用一個細 subclass `CatCamVideo`
蓋咗 `visibilityCheck`（iOS Safari 背景分頁會提早斷線嘅 bug，詳見
`my-homelab` skill 嘅 catcam 章節）。

## 秘密管理通道

連續撳 logo 5 次會彈一個密碼 modal。密碼就係後端嘅 `ADMIN_TOKEN`。解鎖
之後,前端用 Web Crypto（`crypto.subtle`）對請求做 HMAC-SHA256 簽名,
call `POST /admin/feed` 嚟繞過冷卻時間同開放時段直接餵。Token 存喺
`localStorage`,唔會傳明文密碼。

## 雙語

`translations.zh` / `translations.en` 兩個字典,`lang` 存喺
`localStorage`,全站文字（包括提示句、按鈕、toast）都跟住切換,唔係中英
對照同時顯示。

## Build(可以喺 macOS 或 CT 內做)

```bash
cd catcam-frontend
cp .env.example .env      # 通常留空即可（同源）
npm install
npm run build              # 產出 build/ 資料夾
```

改完 `.env` 要**重新 `npm run build`**(Vite 喺 build 時 inline 呢啲值)。

## 部署到 CT 114(catcam)

```bash
# macOS build 完，打包送上 Proxmox host，再經 pct push/exec 入 CT
COPYFILE_DISABLE=1 tar -czf /tmp/catcam-frontend-build.tar.gz -C build .
scp /tmp/catcam-frontend-build.tar.gz root@upsn150-pve:/tmp/

ssh root@upsn150-pve "
  pct push 114 /tmp/catcam-frontend-build.tar.gz /tmp/catcam-frontend-build.tar.gz
  pct exec 114 -- bash -lc '
    mkdir -p /opt/catcam-frontend/build.new &&
    tar -xzf /tmp/catcam-frontend-build.tar.gz -C /opt/catcam-frontend/build.new &&
    mv /opt/catcam-frontend/build /opt/catcam-frontend/build.old 2>/dev/null;
    mv /opt/catcam-frontend/build.new /opt/catcam-frontend/build &&
    systemctl reload caddy
  '
"
```

`Caddyfile`（repo 根同 `deploy/` 都有一份,內容要保持一致）已經設定好
`/` serve 靜態 build、`/status /feed /health /admin/feed` 代理去後端、
`/camera/*` 代理去 go2rtc。CT 入面要裝 Caddy(見官方 apt repo 說明)同
go2rtc,並喺 Cloudflare Tunnel 加一條 route:`cat.kelvinp.work` →
`http://<CT IP>:80`。

## 本機預覽(開發用)

```bash
npm run dev        # http://localhost:5173，會打你 VITE_API_BASE 設定嘅後端
```

開發時把 `VITE_API_BASE` 設成後端可達位址(例如 `http://ip:8080`),
並記得後端 `.env` 的 `CORS_ORIGINS` 要允許 `http://localhost:5173`。
本機冇 go2rtc 嘅話,直播畫面會顯示連線中/連唔到,唔影響餵貓功能測試。

## 設計風格

色票同 CSS 變數（`src/app.css`）係跟個人 design-system 參考文件
（Lattice，light variant）對出嚟嘅 token,唔係隨便揀顏色。改色前先睇
嗰份參考文件有冇現成 token 可以用,唔好自己加新色碼。
