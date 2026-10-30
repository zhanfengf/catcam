# CatCam 前端（SvelteKit 靜態網站）

純前端 SPA（繁中／英文雙語切換）：直播畫面、狀態、一個「餵貓」大掣，以及一個
隱藏管理通道（連按 logo 5 次），讓主人繞過冷卻時間。建置結果是靜態檔案，
毋須 Node runtime；Caddy 會同時提供靜態檔案、反向代理後端 API，以及代理
go2rtc 嘅直播串流。

```
觀眾 → cat.kelvinp.work → Caddy(:80, CT 114)
        ├─ /                                                      → 靜態 SvelteKit build
        ├─ /status /feed /admin/feed /admin/feed-test /admin/wet-food
        │  /admin/announcement /admin/auto-feed /admin/fasting
        │  /admin/fasting/clear /admin/history /recordings /activity → reverse_proxy 127.0.0.1:8080（FastAPI 後端）
        ├─ /clips/*                                                → 靜態檔（FastAPI 寫落去嘅 60 秒餵食片，唔經後端）
        └─ /camera/*                                                → reverse_proxy 127.0.0.1:1984（go2rtc，rewrite 做 /api/*）
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

左上角個時間唔係前端畫嘅——係 go2rtc 嗰邊用 ffmpeg 嘅 `drawtext` filter
直接燒錄入條串流度（設定喺 `catcam-backend/deploy/go2rtc/go2rtc.yaml`，
部署到 CT 114 嘅 `/opt/go2rtc/go2rtc.yaml`）。前端呢邊淨係有個
`.stage-refresh` 掣同 `.stage-watermark`，冇 clock 相關嘅 state。

## 秘密管理通道

連續撳 logo 5 次會彈一個密碼 modal。密碼就係後端嘅 `ADMIN_TOKEN`。解鎖
之後,前端用 Web Crypto（`crypto.subtle`）對請求做 HMAC-SHA256 簽名,解鎖
之後有幾個功能：

開發版部署在 `cat-preview.kelvinp.work`，使用獨立 Backend／DB。當 `/status`
回傳 `preview_mode: true`，頁頂會固定顯示「模擬環境」警告；所有餵食按鈕只建立
測試紀錄，不會接觸真正餵食機。Preview 可共用唯讀直播畫面，方便用真實版面測試。

- `POST /admin/feed`：繞過當刻嘅冷卻時間同開放時段直接餵；成功出糧後會由
  嗰一刻重新開始目前公開 cooldown，但唔計落「訪客餵食咗」次數。如果強制餵
  發生喺一個自動餵食時段內，該時段會即時標記為已完成，結束時唔會重複出糧。
  強制餵完會自動 reload 返個紀錄清單。
- `POST /admin/feed-test`（🧪 模擬訪客出糧）：同樣繞過規則,一樣真係出糧、
  一樣會觸發餵食錄影,但用嚟測試成條 pipeline 行唔行得通,唔係代訪客餵——
  `feed_log` 入面用 `admin_test:` 標記,同 `/admin/feed` 嘅 `admin:` 分開,
  唔計落「訪客餵食咗」，亦唔會改動公開冷卻倒數。
- `POST /admin/wet-food`（🥫🐟 餵罐罐）：記錄主人親手餵罐頭，唔 call Home
  Assistant、唔會令 PetKit 出乾糧、唔會錄影。成功後即時新增
  `feed_event.source="admin_wet_food"`、由當刻重新計目前公開 cooldown；如果
  位於自動餵食時段，該時段會即時標記完成。按下後前端立即 reload
  `/activity`，所以所有開住頁面嘅訪客最遲亦會喺原本 30 秒 poll 內見到。
- `POST /admin/announcement`（📢 公告欄）：一個 textarea + 儲存掣,設定/清空
  訪客一入站就見到嘅公告彈窗文字（留空即隱藏）。
- `POST /admin/cooldown`（⏱️ 公開餵食間隔）：百位、十位、個位三個原生選擇器
  合成 `120–240` 分鐘。儲存後現有倒數立即按原本 `last_fed_at` 重新計算；Frontend
  會限制有效組合，Backend 亦會拒絕範圍外或非整數請求。
- `POST /admin/auto-feed`（🤖 自動餵食時段）：以手機原生 `time` picker 增刪最多
  10 個安全網時段。每段開始必須早過結束、唔可以跨午夜，結束最遲 `22:59`；前端
  即時提示，後端亦會二次驗證，無效 API 請求回傳 `422`。每個時段完結時，如果
  冇人餵過就自動餵一份，並喺餵食動態出一條 🤖 系統訊息；自動餵會開始目前
  公眾冷卻，但唔計落「訪客餵食咗」。新加入但今日已完結嘅時段由聽日生效，避免
  儲存後突然追補；儲存亦會清走 `auto_feed_handled` 已取消時段嘅舊 key。
- `GET /admin/history`：顯示今日 PetKit 裝置本身偵測到嘅每次出糧時間
  （唔係呢個網站自己嘅紀錄——網站觸發嘅餵食最終都會出現喺呢度，所以冇需要
  分開顯示兩份清單）。紀錄標題有個手動重新整理掣，因為 PetKit 雲端同步仍然
  可能有幾秒至幾分鐘延遲。

Token 存喺 `localStorage`，唔會傳明文密碼。

## 餵貓掣狀態 + 公告彈窗

`GET /status` 嘅 `can_feed` + `reason` 決定餵貓掣顯示乜(`ok` / `cooldown` /
`outside_hours` / `ha_offline` / `stream_offline`)——`ha_offline` 係後端獨立
背景 poll 緊 HA 嘅結果,同鏡頭個 LIVE/離線 badge(`cameraConnected`,睇
WebSocket 連線狀態)係兩件完全唔同嘅嘢,唔好搞混。狀態截圖喺根目錄 README。

`stream_offline` 係後端「串流看門狗」嘅判斷:PetKit 雲端 WHEP 斷流時,HA 仍然
報 `streaming`,所以淨靠 `ha_offline` 捉唔到——後端改為睇 24/7 buffer 有冇
新鮮片段嚟判斷真係有冇畫面,冇畫面時 `can_feed` 變 `false`、`reason` 做
`stream_offline`,餵貓掣 disable 兼顯示「📷 直播中斷,暫時餵唔到」(睇唔到隻貓
就唔好餵）。詳見 `catcam-backend/README.md` 嘅「串流看門狗」一節。

公告彈窗(`status.announcement`)一入站有內容就自動彈出,用返同秘密通道
登入 modal 一樣嘅 `.modal`/`.modal-backdrop` 樣式。撳右上角 ✕ 關閉會將
**嗰句實際文字**(唔係單純一個 boolean)存入 `localStorage`
(`catcam_announcement_dismissed`),所以如果之後公告內容改咗,訪客會再見到
新彈窗——唔會因為之前撳過「關閉」就永遠見唔返。

## 餵食動態欄（兩段式）

直播畫面右邊一欄「餵食動態」（闊芒 ≥1100px 並排，窄芒疊喺畫面下面），唯讀，
資料來自 `GET /activity`。每一次餵食機真實出糧會出**兩條**訊息：先喺偵測到嗰刻出
「🍚 餵咗 Roll Roll 錄影整緊…」，約一分鐘後錄影整好再出「📹 錄影好咗，睇返
錄影 ›」（撳得，用返同資料卡一樣嘅 `/clips/<filename>.mp4` lightbox 播放器）。

前端攞到 `events`（每個係 `{fed_at, clip, clip_ready_at}`）之後，用
`activityLines` 把每個事件展開成兩行——`fed_at` 出「餵咗」行、有 `clip` 先
多出一行「錄影好咗」——再按時間**舊到新**排（聊天式，最舊喺頂、最新喺底），
所以一對「餵咗 → 錄影好咗」由上往下順住讀；個欄亦會喺有新提示時**自動捲到底**
（`afterUpdate` 裡只喺行數真係變咗先捲，唔會同捲返上去睇舊紀錄嘅用戶打交）。
提示多過個欄高度就出 scrollbar，只顯示當日嘅事件（每日 reset）。未有 `clip`
嗰陣先顯示「錄影整緊…」同唔畀撳；一有 `clip` 就淨低
可撳嗰條帶 link。每 30 秒 poll 一次（錄影本身都要成分鐘先 render 好，唔使更
密）。因為係行 `times_dispensed` 信號，連 PetKit app、機身掣、自動餵都影得到，
唔止網站觸發嘅餵食。如果某個事件係排程**自動餵食**（後端標 `source: "auto"`、
`note` 係對應時段），個「餵咗」行就會換成 🤖「冇人喺 07:00-07:30 餵 Roll Roll，
自動餵咗一份乾糧。下次可以餵：180 分鐘後」（數字按目前設定），之後一樣有
「📹 錄影好咗」嗰條。
`feed_event` 由後端重啟嗰刻先開始記，之前嘅餵食唔會追溯。

`source="admin_wet_food"` 係例外：佢代表主人喺廚房親手餵罐頭，冇 PetKit
dispense、冇錄影。前端只顯示一條「🥫🐟 啱啱餵咗 Roll Roll 食罐罐」，唔會
顯示「錄影整緊…」；亦唔會出現喺只讀 PetKit `times_dispensed` 嘅「今日餵食紀錄」。

## 資料卡（ⓘ）

標題旁邊個 ⓘ 掣彈一個公開嘅資料 modal:名、出生資訊、Instagram 連結(inline
SVG 畫嘅相機圖示，`hover` 會連埋外框一齊變返 `--accent-strong` 綠色)、簡介、
相片 gallery(5 張，`static/photos/` 入面，撳相可以放大做 lightbox，再撳一下
返去資料卡)。相片原圖(iPhone 拍嘅)上載前要用 `magick -auto-orient -resize
-strip` 處理過，**一定要去晒 EXIF/GPS**先至放得（公開網站，原圖會洩露屋企
位置）。

資料卡入面仲有一行「餵食錄影」，撳開會攞 `GET /recordings`（公開，唔使
token），個清單用 Lattice `ex-data-table-cell` 樣式（canvas 底、
surface-soft 表頭、hairline 行線），撳某一行會播返條 `/clips/<filename>.mp4`
（lightbox 入面用 `<video controls autoplay>`，撳背景關閉）。呢個同
「今日餵食紀錄」（`/admin/history`，收埋喺秘密通道）係兩樣嘢 —— 一個係公開
嘅 60 秒片，一個係管理員先睇到嘅時間清單。

## 雙語

`translations.zh` / `translations.en` 兩個字典,全站文字（包括提示句、按鈕、
toast）都跟住切換,唔係中英對照同時顯示。

首次訪客嘅語言用 `detectLang()` 睇 `navigator.languages`——任何 `zh*`
（zh-HK/zh-TW/zh-CN…）→ 繁中,其餘 → 英文,即係跟訪客自己部機嘅語言設定,
唔再一律硬繁中。優先次序：**`localStorage` 手動揀過 > 瀏覽器語言 > fallback
繁中**，所以自動偵測只決定「第一次」睇邊種,訪客撳過切換之後永遠用返佢揀嘅
（存喺 `localStorage`）。呢個係睇瀏覽器語言偏好,唔係 Geo-IP 地理位置——一個
香港人部機設咗英文,佢會見英文（反映佢想睇乜,而唔係人喺邊）。

## 建置（可以喺 macOS 或 CT 內做）

```bash
cd catcam-frontend
cp .env.example .env      # 通常留空即可（同源）
npm install
npm run build              # 產出 build/ 資料夾
```

改完 `.env` 要**重新 `npm run build`**(Vite 喺 build 時 inline 呢啲值)。

## 部署到 CT 114（catcam）

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

`Caddyfile`（repo 根同 `deploy/` 都有一份，內容要保持一致，**改完兩份都要
部署去 CT 114 先生效**）——之前試過淨係改本地 repo 冇部署，新 endpoint
response 靜默跌去 SPA fallback，攞住 HTML 當 JSON parse，前端顯示完全
唔相關嘅錯誤）已經設定好 `/` serve 靜態 build、`/status /feed /health
/admin/feed /admin/feed-test /admin/wet-food /admin/announcement /admin/auto-feed
/admin/fasting /admin/fasting/clear /admin/history /recordings /activity` 代理去後端、
`/clips/*` 直接 serve 後端寫落 CT 本機嘅餵食片、
`/camera/*` 代理去 go2rtc。CT 入面要裝 Caddy(見官方 apt repo 說明)同
go2rtc,並喺 Cloudflare Tunnel 加一條 route:`cat.kelvinp.work` →
`http://<CT IP>:80`。新增任何一個 `/admin/*` endpoint,呢度嘅路由清單都要
同步加返,唔係得 `app/main.py` 加個 route 就夠。

## 本機預覽（開發用）

```bash
npm run dev        # http://localhost:5173，會打你 VITE_API_BASE 設定嘅後端
```

開發時把 `VITE_API_BASE` 設成後端可達位址(例如 `http://ip:8080`),
並記得後端 `.env` 的 `CORS_ORIGINS` 要允許 `http://localhost:5173`。
本機冇 go2rtc 嘅話,直播畫面會顯示連線中/連唔到,唔影響餵貓功能測試。

## 設計風格

色票同 CSS 變數（`src/app.css`）係跟個人設計系統參考文件
（Lattice light variant）對出嚟嘅 token，唔係隨便揀顏色。改色前先睇
嗰份參考文件有冇現成 token 可以用，唔好自己加新色碼。
