# CatCam Project

公開貓貓直播站，觀眾可以撳掣餵貓。

## 架構
- 後端：Python + FastAPI（呢個 repo），部署喺 Proxmox LXC `catcam`（Debian 12）
- 前端：SvelteKit（未起）
- 對外：Cloudflare Tunnel，route `cat.kelvinp.work`
- 出糧：call Home Assistant REST API → text.zhi_ma_guan_jia_manual_feed（HA @ ）

## 規則（已實作喺 app/scheduling.py）
- 全站共用 120 分鐘冷卻
- 開放時段 07:00–23:59 Asia/Hong_Kong
- 固定出糧份量 10
- 每 IP 防洗版

## 下一步
- 起 SvelteKit 前端：餵貓大掣（POST /feed）、倒數（GET /status）、之後嵌直播