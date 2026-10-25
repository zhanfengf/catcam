# CatCam Project

公開貓貓直播站（cat.kelvinp.work），觀眾可以撳掣餵貓、睇直播；自己可以用
藏起嚟嘅管理通道繞過冷卻時間。

## 架構
- 後端：Python + FastAPI（呢個 repo，`catcam-backend/`），管規則、call HA
- 前端：SvelteKit 靜態 SPA（`catcam-frontend/`），繁中/EN 雙語
- 兩者都部署喺 Proxmox LXC 114「catcam」（Debian 12），Caddy 同一個 CT 入面
  做反向代理，唔係分開兩個 CT
- 直播：go2rtc（同一個 CT）用 WHEP pull HA 嘅 PetKit camera，再經
  WebSocket+MSE 重新 serve 俾前端；Caddy `/camera/*` 直接代理去 go2rtc，
  唔經呢個 FastAPI 後端。架構同埋 iOS Safari 嘅兩個坑（visibilityCheck
  timing、go2rtc codec 聲明同實際 bitstream 唔同）記喺 `my-homelab` skill
  嘅 catcam 章節
- 對外：Cloudflare Tunnel，route `cat.kelvinp.work`
- 出糧：call Home Assistant REST API → text.zhi_ma_guan_jia_manual_feed

## 規則（已實作喺 app/scheduling.py）
- 全站共用 120 分鐘冷卻
- 開放時段 07:00–23:59 Asia/Hong_Kong
- 固定出糧份量 10
- 每 IP 防洗版
- `POST /admin/feed`：HMAC 簽名請求可以繞過冷卻同開放時段（自己用，唔係公開
  規則嘅一部份）