# CatCam 餵食機 API

這是一個 Python + FastAPI 後端，讓公眾透過用途單一、設有速率限制的 endpoint
「餵貓」。SvelteKit 前端只會與**這個服務**通訊；Home Assistant token 只留在
後端，永遠不會送到瀏覽器。

```
觀眾瀏覽器 → SvelteKit → 呢個後端 → HA REST API → text.zhi_ma_guan_jia_manual_feed
```

## 內置規則

- 憑連結使用，毋須登入。
- 全站共用 cooldown：兩次餵食相隔 **120 分鐘**。
- 開放時間：香港時間 **07:00–23:59**。
- 固定份量：**10**。
- 每個 IP 防洗版；這只阻止重複轟炸 endpoint，不是餵食配額。
- `last_fed_at` 保存在 **SQLite**，重啟後仍會保留限制。公開 `/feed`、主人強制
  餵食 `/admin/feed` 及排程自動餵食都會更新這個時間。`/admin/feed` 可繞過
  進行中的 cooldown，但成功出糧後會重新開始 120 分鐘 cooldown；只有
  `/admin/feed-test` 不會改動倒數。
- `fed_today`（顯示為「訪客餵食咗」／`Fed by visitors`）**只計公開訪客餵食**；
  所有 Admin 通道餵食均刻意排除。

## API 路徑

| 方法 | 路徑 | 用途 |
| ------ | ---------------- | ------------------------------------------------------- |
| GET | `/status` | 回傳現在能否餵食、下次餵食時間、開放時段、今日訪客餵食次數、`ha_online`、`stream_online`、`announcement` 及 `auto_feed_windows`。 |
| POST | `/feed` | 嘗試餵食；後端先檢查開放時間及 cooldown，再呼叫 HA。 |
| POST | `/admin/feed` | HMAC 簽署的強制餵食，可繞過 cooldown 及開放時間；成功後重新開始公開 cooldown。 |
| POST | `/admin/feed-test` | HMAC 簽署的模擬餵食。真正出糧以測試完整 pipeline，但不影響公開 cooldown 或「訪客餵食咗」次數。 |
| POST | `/admin/wet-food` | HMAC 簽署的餵罐罐紀錄。重新開始公開 cooldown，但不呼叫 HA、不出乾糧、不錄影。 |
| POST | `/admin/announcement` | HMAC 簽署。設定公告文字；傳入 `""` 可清除公告。 |
| POST | `/admin/auto-feed` | HMAC 簽署。設定同日、結束最遲 `22:59` 的 `HH:MM-HH:MM` 自動餵食安全網時段清單。 |
| POST | `/admin/fasting` | HMAC 簽署。開啟禁食模式及暫停自動餵食安全網。 |
| POST | `/admin/fasting/clear` | HMAC 簽署。解除禁食模式。 |
| GET | `/admin/history` | HMAC 簽署。直接讀取 PetKit 今日出糧紀錄，不是本網站自己的 log。 |
| GET | `/recordings` | 公開。列出本星期的 60 秒餵食影片，包括檔名及時間。 |
| GET | `/activity` | 公開。回傳今日兩階段餵食動態（`fed_at`、`clip`、`clip_ready_at`）。 |
| GET | `/health` | 服務存活檢查。 |

`POST /feed` 成功時回傳 `200`；不在開放時間回傳 `403`；cooldown 或洗版回傳
`429`；HA 無法連線則回傳 `502`。

`POST /admin/feed`、`/admin/feed-test`、`/admin/wet-food`、
`/admin/announcement`、`/admin/auto-feed`、`/admin/fasting`、
`/admin/fasting/clear` 及 `GET /admin/history` 都是秘密通道解鎖後使用的
endpoints。用戶需要連按 logo 5 次並輸入 `ADMIN_TOKEN`。每個請求都必須以
`ADMIN_TOKEN` 對 `{METHOD}:{PATH}:{timestamp}` 產生 HMAC-SHA256 簽署，timestamp
亦必須在 `ADMIN_SIG_WINDOW_SECONDS` 範圍內；詳見 `app/main.py` 的
`verify_admin_signature()`。明文密碼不會經網絡傳送。

`/admin/feed` 及 `/admin/feed-test` 都會跳過 cooldown／開放時間檢查，並寫入
`feed_log`。真正的 `/admin/feed` 會更新公開 `last_fed_at`；`/admin/feed-test`
則刻意保持不變。兩者都不會計入 `fed_today`，並以 `ip` 欄位前綴區分：

- `admin:<ip>`：`/admin/feed`，主人真正的「無視當刻限制立即餵食」；出糧後
  重新開始完整公開倒數。
- `admin_test:<ip>`：`/admin/feed-test`，按需要測試真實出糧 pipeline（呼叫 HA
  及觸發錄影），但不會被當成真正強制餵食或訪客餵食。
- `admin_wet_food:<ip>`：`/admin/wet-food`，主人親手提供的真實一餐。由於沒有
  乾糧離開餵食機，所以 `amount=NULL`；它會重新開始公開 cooldown，但不計入
  訪客次數。
- 沒有前綴：訪客真正呼叫 `/feed`。

`count_feeds_today()`（「訪客餵食咗」統計）會排除所有 Admin 前綴。

`/admin/history` 完全不讀取本網站的 `feed_log`。它會查詢 Home Assistant
history API 內 PetKit 裝置的 `times_dispensed` counter。無論出糧由網站、
PetKit App、機身按鈕或自動排程觸發，每次真實出糧都會令 counter 增加；本地
午夜則重設為 0。history 中每次數值增加代表一次餵食事件，時間使用該次狀態改變
的 HA `last_changed`。本網站 log 只知道經網站觸發的餵食，所以 PetKit counter
才是裝置實際出糧的資料來源。詳見 `app/ha.py` 的 `get_feed_history()`，當中有兩個
不明顯的細節：

- HA history endpoint 每次只會回傳由請求時段起點計起的少量 rows，因此程式會
  以小段時間向後查詢，而不是一次查詢整個大範圍。
- PetKit integration 亦提供 `image.*_last_feed_event`，其 state 的確是事件
  timestamp，看似可直接使用；但它要等待裝置上傳 snapshot，可能延遲數分鐘至
  數小時。`times_dispensed` 只是沒有附圖的數字，真實出糧後數秒便會更新。實測
  手動餵食約 6 秒後 counter 已增加，但 `last_feed_event` 仍落後超過 1 小時。

## 餵食影片錄影

`app/recorder.py` 每 10 秒在背景查詢一次，使用與 `/admin/history` 相同的
`times_dispensed` 信號。每次真實出糧，它都會從下述 pre-roll buffer 拼接一段
影片。這項功能**不只綁定 `/feed` 或 `/admin/feed`**；它直接監察 HA 出糧
counter，因此任何真實出糧都會觸發，包括訪客按網站按鈕、主人 Admin 強制餵食、
PetKit App、餵食機機身按鈕及 PetKit 自己的排程。如果 `/feed` 在 HA 真正出糧前
已失敗（例如回傳 `502`），counter 不會改變，亦不會錄影。

影片保存在 `recordings_dir`（預設 `./recordings`），以 7 日滾動方式保留；每次
新增影片時會刪除最舊檔案。影片毋須驗證即可公開存取：`GET /recordings` 提供 JSON
清單，實際靜態檔案由 Caddy 透過 `/clips/*.mp4` 提供，不經這個後端。

**不明顯的細節：** go2rtc 的限時匯出（`/api/stream.mp4?...`，供下述 fallback
使用）是 fragmented MP4，亦即 WebSocket／MSE 串流所用格式。直接放入
`<video src>` 可能無聲地永遠載入失敗：`readyState` 停在 `0`，沒有 error event，
看起來像網絡緩慢而非格式問題。解決方法是在下載後立即 remux：
`ffmpeg -i raw -c copy -movflags +faststart final.mp4`。這是無損處理，60 秒影片
約需 0.4 秒。下載時先使用 `.part` 副檔名而非 `.mp4`，即使下載或 remux 中途
崩潰，公開清單亦不會出現未完成檔案。

## 預錄緩衝（pre-roll buffer）

**「Pre-roll」與「24/7 buffering」不是兩個替代方案：pre-roll 是目的，持續
buffering 是唯一能達成它的方法。** Pre-roll 代表最終影片包含觸發前的畫面，
例如 Roll Roll 跑向食碗，而不只是已經在吃。觸發發生後才開始錄影，已經無法回到
過去；如果那段時間沒有預先被記錄，不論觸發邏輯有多快，畫面都已消失。要在收到
觸發時取得「過去」，只能在觸發出現前已持續把畫面錄入滾動窗口，之後再向前拼接，
沒有方法可以避開 24/7 buffering。

| 項目 | 舊方案：觸發後匯出 | 新方案：pre-roll buffer |
|---|---|---|
| 開始錄影時間 | 收到出糧信號後才開始 | 任何觸發出現前已 24/7 持續運行 |
| 能否看到貓咪跑過來 | 不能；開始錄影時通常已經在吃 | 可以；拼入 `T` 之前的畫面 |
| 影片內容 | 只有 `[T, T + recording_seconds]` | `[T - pre_roll_seconds, T + post_roll_seconds]` |
| 額外恆常負載 | 沒有；未觸發時閒置 | 一個長期運行的 `ffmpeg -c copy` process（約 0% CPU，毋須重新編碼） |
| 磁碟 | `recordings/` 內只有完成影片 | 完成影片加小型滾動 `buffer/`（約 3 分鐘片段、數百 MB） |
| 尚未準備好時 | 不適用 | fallback 至舊有觸發後匯出，確保餵食事件不會完全沒有影片 |

### 時間軸

```
buffer.py — 持續錄影、-c copy、5 秒片段、長期運行
════════════════════════════════════════════════════════════════════▶ 時間
                              │
                 ┌────────────┴────────────┐
                 │  真實按下按鈕             │
                 │  （HA/PetKit 延遲：約 6–27 秒）│
                 └────────────┬────────────┘
                              │
                              ▼
                 T  ← recorder.py poller 在此偵測到出糧
                              │
        ┌─────────────────────┼─────────────────────────────────────┐
        │                     │                                     │
   T - pre_roll_seconds       │                       T + post_roll_seconds
   （影片由此開始；          │                       （影片在此結束；recorder.py
    畫面已在 buffer 中，     │                         以 asyncio.sleep() 等待
    毋須等待）               │                         這個時間真正到達）
        │                     │                                     │
        └─────────────────────┴─────────────────────────────────────┘
                   最終影片 = concat(segments) → trim →
                   「Roll Roll 跑過來」→「Roll Roll 食緊」
```

最終影片左半段（`T - pre_roll_seconds` 至 `T`）直接取自觸發前已寫入 buffer 的
片段，毋須等待。右半段（`T` 至 `T + post_roll_seconds`）在偵測當刻尚未發生，
因此 `recorder.py` 必須等待這段時間完結，才能開始組合影片。

### 處理流程逐步說明

1. **持續錄影（`buffer.py`，長期運行）。** 一個長期存在的 `ffmpeg -c copy`
   process 拉取 `petkit_h264` 直播，把它寫成滾動的 5 秒片段放入 `buffer_dir`，
   並刪除早於 `buffer_window_seconds` 的內容（預設 180 秒，即 3 分鐘）。這一步
   令系統有機會取得「過去」。
2. **偵測觸發（`recorder.py` poller）。** 每 10 秒檢查 HA 出糧 counter；數值
   增加時記錄偵測時間 `T`。由於 HA／PetKit 來回同步，這通常已比真正按掣遲數秒。
3. **等待 post-roll 時段真正發生。** 影片需要包含直到 `T + post_roll_seconds`
   的畫面，但這段內容在偵測時尚不存在。背景 task 會先執行
   `asyncio.sleep(post_roll_seconds)` 再繼續；這是非阻塞等待，不影響其他請求。
4. **選取覆蓋 `[T - pre_roll_seconds, T + post_roll_seconds]` 的片段。**
   `buffer.segments_covering()` 會選取所有與該時段重疊的 5 秒片段。
5. **無損拼接。** `ffmpeg -f concat -c copy` 把選取片段接成連續串流，使用與每週
   精華相同的方法，毋須重新編碼。
6. **精準裁剪。** 第 5 步的拼接串流由第一個重疊片段的起點開始，不一定剛好是
   `T` 前 `pre_roll_seconds`。第二次處理以
   `ffmpeg -ss <offset> -i concat.mp4 -t <pre_roll_seconds + post_roll_seconds> -c copy final.mp4`
   裁至指定範圍。由於仍是 `-c copy`，只能在 keyframe 而非任意 frame 切割；目前
   GOP 設定（`-g 50`、約 27.5 fps）的準確度約為 **±1.8 秒**，遠比 5 秒片段網格
   精準，而且沒有重新編碼成本。
7. **保存及發布。** 結果寫入 `recordings_dir`；超過 `recording_retention_days`
   的舊影片會被清理。影片隨即出現在 `GET /recordings`，並可從
   `/clips/<filename>.mp4` 播放。
8. **Fallback。** 若 buffer 沒有覆蓋所需時段的內容，例如服務剛重啟、buffer
   尚未填滿，第 4 步會回傳空結果。程式會跳過整個拼接流程，改用原本的 go2rtc
   限時匯出，產生沒有 pre-roll 的普通觸發後影片，而不是完全沒有影片。

透過 HA history API 實測，真正出糧至後端知道事件之間確有 HA／PetKit 雲端
同步延遲：App 手動餵食約 6 秒，自動排程約 27 秒。因此第 2 步不能只靠「更快
觸發」解決；信號到達前，貓咪可能已經走到食碗。

**不明顯的細節：** ffmpeg 的 `-strftime 1` 檔名使用*被啟動 process 的系統
時間*，不是 Python 的 `datetime.now(tz())`。`go2rtc.service` 有設定
`Environment=TZ=Asia/Hong_Kong`，但 `catcam.service` 沒有，而 CT 系統時間是
UTC。因此啟動 buffer ffmpeg subprocess 時，必須明確傳入 `TZ=Asia/Hong_Kong`
（`asyncio.create_subprocess_exec` 中的 `env={**os.environ, "TZ": ...}`）。否則
`segments_covering()`／`_cleanup_old()` 以香港時間解析檔名時，會把檔案看成落後約
8 小時；所有片段立即被判定早於 `buffer_window_seconds`，在 5 秒內被刪除，令
buffer 無論運行多久都只剩一個近乎空白的檔案。

## 每週精華影片

`app/highlights.py` 是獨立背景 task。它會等待至下一個香港時間星期日 00:00，
再從 `recordings/` 選取**過去 7 日每天最早的一段影片**，以
`ffmpeg -f concat -c copy` 無損拼接成
`highlights_dir/highlight_<start>_to_<end>.mp4`（預設 `./highlights`）。
這個資料夾**沒有 route 亦沒有前端 UI**；它是私人暫存區，供主人檢查後再決定
是否手動上載到 YouTube 等平台。請用 `pct pull`／`scp` 取回檔案，詳見
`catcam-ct114-transfer` skill。排程 loop 以 `try`／`except` 包住編譯呼叫；若
exception 逃出，`asyncio.Task` 會無聲地永久停止，之後每星期都不會再執行，直至
服務重啟。

## HA 連線檢查

`app/ha.py` 每 15 秒在背景查詢 `{HA_URL}/api/`，與餵食請求互相獨立，並把結果
cache 在 `is_online()`。`GET /status` 會以 `ha_online` 回傳結果；HA 斷線時，
`can_feed`／`reason` 會覆寫成 `false`／`"ha_offline"`。因此 HA 真正無法連線後
約 15 秒，前端便會停用餵食按鈕及顯示「餵食機離線」，而不是等訪客按下才收到
`502`。真正 HA 故障亦會同時中斷相機，因為 go2rtc 上游 WHEP 同樣經過 HA；
詳見根目錄 README 的 `feed-ha-offline.png` 截圖。

## 串流看門狗（`stream_offline` 及自動修復）

`ha_online` 只能回答「HA 能否連線」，但最常見的故障剛好相反：HA 保持在線，
亦繼續把相機狀態報成 `streaming`，但 **PetKit 雲端 WHEP session 已無聲中斷**，
再沒有畫面流入。`app/streamwatch.py` 以獨立存活信號補上這個缺口。

它透過 **24/7 pre-roll buffer**（`app/buffer.py`）判斷直播是否正常。有畫面時，
ffmpeg 會持續寫出包含數據的約 5 秒片段；`stream_online()` 只需檢查最新片段是否
高於最低 bytes，而且 mtime 是否夠新（小於 `stream_stale_seconds`，預設 30 秒）。
最低 bytes 很重要：go2rtc 仍在線但沒有上游畫面時，ffmpeg 會重連並不斷製造 mtime
很新但近乎空白的片段；若把它們計算在內，系統會錯誤判定為在線。因此少於
`buffer_min_segment_bytes`（20 KB）的片段不算有效。

`GET /status` 會回傳 `stream_online`。餵食機正常但串流停滯時，`can_feed`／
`reason` 會在 `ha_offline` 檢查後覆寫為 `false`／`"stream_offline"`，停用公開
餵食按鈕；看不到貓咪時便不開放餵食。

背景 loop 每 15 秒亦會執行**自動修復**。中斷持續超過
`stream_recover_after_seconds`（預設 75 秒）後，它會執行與 `my-homelab` skill
內 `scripts/fix-catcam-stream.sh` 相同的流程：重新載入 PetKit integration
（`ha.reload_petkit()`）、等待，再重啟 go2rtc。之後會等待
`stream_recover_cooldown_seconds`（預設 300 秒）才可再次嘗試，避免真正雲端
故障時不斷轟炸。設定 `stream_auto_recover=false` 可只保留偵測，不自動修復。

**毋須 sudo 重啟 go2rtc：** CT 沒有 `sudo`。後端以非特權 `catcam` user 運行，
只會 `touch` 一個自己擁有的 trigger file；由 root 運行的 systemd **path unit**
（`deploy/go2rtc-restart.path` → `deploy/go2rtc-restart.service`）監察該檔案並執行
`systemctl restart go2rtc`。因此 `catcam` 只獲得「重啟 go2rtc」一項能力，沒有
一般 root 權限。安裝步驟寫在 `go2rtc-restart.path` 檔頭。

### 中斷提示（Telegram）

`app/notify.py` 提供選用 push 通知。中斷持續超過
`stream_recover_after_seconds` 後，streamwatch 只發送**一則**「🔴 直播斷咗」；
短暫抖動不會通知。恢復時再發送附中斷時長的「🟢 復原咗」。通知採用
fire-and-forget，Telegram 不會阻塞監察 loop；未設定憑證時則完全 no-op，
看門狗仍會靜默偵測及自動修復。

設定方法：

1. 在 Telegram 向 **@BotFather** 發送 `/newbot`，再複製 bot **token**。
2. 開啟新 bot 並向它發送任何訊息；用戶未先聯絡 bot 前，bot 無法主動傳訊。
3. 執行 `curl https://api.telegram.org/bot<TOKEN>/getUpdates`，讀取
   `result[].message.chat.id`，這就是 **chat id**。
4. 把兩者寫入 `.env`：`TELEGRAM_BOT_TOKEN=…`、`TELEGRAM_CHAT_ID=…`，然後重啟。

> **注意——強制使用 IPv4：** CT 114 會把 `api.telegram.org` 解析成 IPv6，
> 但 CT 沒有 IPv6 route，因此預設 client 及普通 `curl` 都會一直等到 timeout。
> `notify.py` 會把 socket 綁定至 IPv4 wildcard（`local_address="0.0.0.0"`）；
> shell 內請使用 `curl -4`。

### 訪客餵食提示（Telegram）

使用相同 Telegram 憑證後，每次**真正網站訪客餵食**的影片準備好時，亦會發送
提示。通知約在餵食 1 分鐘後送出，屆時影片連結已可使用：

```
🍚 有訪客餵咗 Roll Roll
🕐 2026-10-27 08:41
🌐 203.0.113.45 · HK
📹 https://cat.kelvinp.work/clips/2026-10-27_084100.mp4
```

接線方式如下：`/feed` 會把訪客 IP 及國家暫存在短期
`visitor_feed_pending` marker；recorder 偵測到相符的出糧後會取出 marker，影片
完成時再由 `recorder._notify_visitor_feed` 發送提示。**只有網站 `/feed` 會設定
這個 marker**；PetKit App、機身按鈕及 Admin 餵食都沒有 marker 或 IP，因此不會
發送訪客通知。排程自動餵食另有專屬通知，詳見下一節。國家資料來自 Cloudflare
的 `cf-ipcountry` header，
只有國家級別，沒有外部 geo-IP，所以沒有城市或地區資料。影片連結以
`public_base_url` 組成；設定 `notify_visitor_feeds=false` 可關閉功能。

### 自動餵食提示（Telegram）

CatCam 自動餵食安全網成功出糧後，recorder 會照常製作餵食影片，並在影片完成時
發送 Telegram 通知。由於這次出糧由系統排程觸發，通知不會顯示 IP 或國家：

```
🤖 自動餵食咗 Roll Roll
🕐 2026-10-30 07:30
📹 錄影片段：https://cat.kelvinp.work/clips/2026-10-30_073000.mp4
```

通知共用 `TELEGRAM_BOT_TOKEN`、`TELEGRAM_CHAT_ID` 及 `PUBLIC_BASE_URL`；設定
`notify_auto_feeds=false` 可單獨關閉自動餵食通知，而不影響訪客餵食或直播中斷通知。

### 連續 5 小時沒有餵食提示（Telegram）

`app/feedwatch.py` 每 60 秒讀取最新一筆 `feed_event`。事件來源不受公開餵食時間
限制：網站訪客、Admin、餵罐罐、CatCam 自動餵食、PetKit App、機身按鈕及 PetKit
排程都會重設 5 小時計時。因此即使 06:00 的自動餵食發生在公開時間外，只要之後
沒有新事件，提示時間便是 11:00，而不是由 07:00 重新起計。

Telegram 只會在公開餵食時間內發送；如果 5 小時門檻在凌晨達到，會延至下一次
公開時間開始才通知。同一筆最後餵食只提醒一次，成功發送後以
`state.feed_inactivity_alert_key` 保存對應 `feed_event.id`；有新事件後才會啟動下一輪。
如果 Telegram 拒絕或連線失敗，系統不會寫入去重 key，下一次檢查仍會重試。

```
⚠️ Roll Roll 已經連續 5 小時冇餵食紀錄
🕐 最後餵食：2026-10-30 06:00
🍚 請檢查糧兜、餵食機同 Roll Roll
```

設定 `feed_inactivity_alert_enabled=false` 可停用；門檻可用
`feed_inactivity_alert_hours` 調整。監察器只讀取 `feed_event`，不會自行出糧、改動
`last_fed_at`、cooldown 或自動餵食時段。

## 公告欄

主人可以向所有訪客發送自由文字公告。每段不同訊息會在頁面載入時顯示一次。
`POST /admin/announcement` 傳入 `{"text": "..."}` 即可設定；後端最多保留 500
個字元，空字串則隱藏公告。`GET /status` 會以 `announcement` 回傳目前文字，毋須
另設讀取 endpoint，因為前端本身每 15 秒查詢 `/status`。前端會把目前文字與
用戶上次關閉的內容（保存在 `localStorage`）比較，判斷是否再次顯示。因此修改
公告後，即使訪客曾關閉舊訊息，亦會再次看到新 popup。

每次保存都會分別執行兩件事，刻意不合併在同一個 table：

- `state`：key 為 `announcement`，與 `last_fed_at` 使用相同 key-value table。
  它**只保存目前值**，`set_announcement()` 會原地 upsert 這一 row；`/status`
  讀取的就是這裡。
- `announcement_log`：獨立 table，欄位為 `id, text, created_at`。每次保存都會
  無條件**新增一 row**，作為公告內容及時間的 audit trail。目前沒有 endpoint／UI
  讀取它，但日後仍可回答「上星期二公告寫過甚麼」，毋須當時預先截圖。

## 餵食動態（兩階段）

這是直播旁邊公開、唯讀的餵食動態欄。每次餵食機真實出糧，約相隔 1 分鐘產生
**兩則**聊天式訊息：偵測到出糧時顯示「🍚 餵咗 Roll Roll」；影片完成後顯示
附重播連結的「📹 錄影好咗」。

資料由獨立 `feed_event` table（`id, fed_at, clip, clip_ready_at`）提供。
`recorder.py` 使用與影片錄影**相同的 `times_dispensed` 信號**寫入資料，因此涵蓋
網站、PetKit App、機身按鈕及自動排程等*所有*真實出糧，不只網站觸發：

- 偵測時（`_poll_loop`）立即新增一 row，`clip` 為 NULL。影片尚未存在前約 1
  分鐘，「餵咗」訊息便讀取這一 row。
- 影片寫入後，`set_feed_event_clip()` 會按 `fed_at` 找到同一 row，再填入 `clip`
  及 `clip_ready_at`，產生「錄影好咗」訊息。若影片最終製作失敗，該 row 會保持
  沒有 clip，只顯示「餵咗」，忠實反映結果。

主人親手餵罐罐是刻意設計的例外。`/admin/wet-food` 不會操作 Home Assistant 或
PetKit，而是同步新增自己的 `feed_event.source="admin_wet_food"` row。前端立即
顯示專屬「🥫🐟 啱啱餵咗 Roll Roll 食罐罐」，並知道這個來源不會有影片，所以
不顯示「錄影整緊…」。它亦不會出現在 `/admin/history`；後者只以 PetKit 真實
出糧 counter 作資料來源。

`GET /activity` 會按新至舊回傳今日 rows；前端把每個事件展開成兩行，再按時間
排序。舊 rows 會與影片一同由 `_cleanup_old()` 按 `recording_retention_days`
清理。這套資料刻意與 `feed_log` **分開**：`feed_log` 支援「訪客餵食咗」統計，
只處理網站餵食且沒有影片資料；`feed_event` 支援公開餵食動態，涵蓋所有出糧及
影片。兩個 tables 各有不同用途，不應把一 row 強行兼任兩者。

## 自動餵食時段（安全網）

`app/autofeed.py` 是每 60 秒檢查一次的背景 scheduler，確保沒有訪客時 Roll Roll
亦不會捱餓。主人透過 `POST /admin/auto-feed` 設定 `HH:MM-HH:MM` 時段清單；資料
保存於 `state` 的 `auto_feed_windows` key，並由 `/status` 回傳，讓 Admin 面板
預先填入。每個時段內**如果無人餵過**，結束時便自動出一份。

時段必須在同一曆日內開始及完結，開始早於結束，結束時間最遲為 `22:59`，最多
10 段。`normalise_windows()` 會正規化為 `HH:MM-HH:MM`；任何無效值都令整個 API
請求回傳 `422 invalid_auto_feed_window`，而不是靜默丟棄，避免直接 POST 繞過前端。
`22:59` 加上 60 分鐘寬限期最遲為同日 `23:59`，因此不會把補餵判斷帶到翌日。

主人在設定時段內強制餵食或餵罐罐，會立即把該時段標記為已處理，即使時段長過
120 分鐘亦一樣。主人操作與 scheduler 共用同一把 lock，因此在時段邊界按掣，
不會與 scheduler race 而重複出糧。

每個時段在今日結束、且尚未處理時：

- 若 `last_fed_at` 距離時段結束少於一個公開 cooldown，便標記為已處理而不出糧。
  時段內的主人強制餵食早已透過上述即時流程標記完成。
- 否則，在結束後 `_GRACE_MINUTES`（60 分鐘）寬限期內，系統會設定
  `state.auto_feed_pending` marker、呼叫 `ha.dispense()`，並以
  `record_feed(..., "auto:system", source="auto")` 記錄。這可避免服務停機跨過
  時段後，數小時才突然補餵；超過寬限期只會標記完成，不會出糧。

`auto_feed_handled` 是保存在 `state` 的 `{window: "YYYY-MM-DD"}` map，確保重啟
不會再次觸發今日已處理時段。自動餵食**會**推進公開 cooldown：除 `admin_test`
外，所有來源的 `record_feed` 都會更新 `last_fed_at`，與「下次可以餵：120 分鐘後」
訊息一致。它在 `feed_log` 以 `auto:` 標記，因此不計入「訪客餵食咗」。

`replace_windows()` 在 Admin 儲存時只保留仍存在於新 `auto_feed_windows` 清單的
handled keys，已取消時段的舊 key 會移除；同一時段目前的處理日期則保留，避免普通
儲存動作解除今日的防重複保護。毋須午夜清空，因為翌日日期不相同時 scheduler
自然會重新處理。若一個**新加入**的時段在儲存一刻已經完結，系統先把它標記為今日
已處理，並在 response 的 `starts_tomorrow` 列出，令它由明日生效而不會立即追補。

自動餵食的 `feed_event` row 由唯一寫入者 **recorder** 建立，而不是 scheduler。
recorder poller 偵測到出糧後，會呼叫 `pop_auto_feed_pending()`；marker 新鮮（少於
90 秒）時，事件便標記為 `source="auto"`，並把時段寫入 `note`。前端會顯示 🤖
「冇人喺……餵……自動餵咗」專屬訊息，仍然保留兩階段，稍後再顯示影片完成。這可
確保每次真實出糧只有一個事件，沒有重複，同時保留專屬訊息及影片。

主人強制餵食使用相同的非同步偵測路徑。`POST /admin/feed` 成功後會保存短期
`state.admin_feed_pending` marker；recorder 看到相符的 PetKit counter 增加時，
會消耗 marker 並寫入 `feed_event.source="admin"`。這樣動態及影片會連接到真實出糧，
亦不會再把主人觸發事件錯誤 fallback 成一般 `visitor`。

## 部署至 LXC（Debian 13，毋須 Docker）

```bash
# 在 CT 內以 root 執行
apt update && apt install -y python3 python3-venv python3-pip
useradd -r -m -d /opt/catcam-backend catcam || true

# 把這個資料夾複製至 /opt/catcam-backend，然後：
cd /opt/catcam-backend
python3 -m venv catvenv   # 名稱需要配合 deploy/catcam.service 的 ExecStart
catvenv/bin/pip install -r requirements.txt

cp .env.example .env
#  >>> 編輯 .env：設定 HA_TOKEN，並檢查 HA_URL／entity <<<
chown -R catcam:catcam /opt/catcam-backend

# 安裝服務
cp deploy/catcam.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now catcam
systemctl status catcam --no-pager
```

## go2rtc 設定（直播處理流程）

`deploy/go2rtc/go2rtc.yaml` 及 `deploy/go2rtc/go2rtc.service` 是 CT 114 實際
運行檔案（`/opt/go2rtc/go2rtc.yaml`、`/etc/systemd/system/go2rtc.service`）的
repository 副本。go2rtc 本身不是由這個 repo 安裝，而是獨立 binary 及 systemd
unit；但設定包含專案中最難發現的重要修正：WHEP auth-proxy workaround、iOS
Safari codec mismatch 修正、燒錄時間，以及 VAAPI 硬件編碼 `exec:` command。
每項完整歷史記錄在 `my-homelab` skill 的 CatCam 章節。

**在 CT 修改任何一個檔案後，都要把改動複製回這個資料夾並 commit；這些檔案沒有
其他版本歷史。** 請依 `catcam-ct114-transfer` skill 的同步方式部署：
`cat deploy/go2rtc/go2rtc.yaml | ssh root@upsn150-pve "pct exec 114 -- tee /opt/go2rtc/go2rtc.yaml > /dev/null" && ssh root@upsn150-pve "pct exec 114 -- systemctl restart go2rtc"`.

在 CT 內測試：

```bash
curl localhost:8080/status
curl -X POST localhost:8080/feed -H 'cf-connecting-ip: 1.2.3.4'
```

## 取得 HA token

在 Home Assistant 左下角按自己的用戶 → **Security** →
**Long-lived access tokens** → **Create**。把 token 以 `HA_TOKEN` 名稱貼入 `.env`，
並確保 `.env` 不會加入 Git。

## 對外開放服務

服務監聽 `127.0.0.1:8080`。把 SvelteKit app 放在前方，可以在同一個或另一個 CT，
再新增指向 CT 的 Cloudflare Tunnel route，例如 `cat.kelvinp.work`。知道 domain 後，
在 `.env` 把 `CORS_ORIGINS` 設成網站 origin；`*` 只應用於本機測試。

## 注意事項

- 只使用**單一 worker**，現有 systemd unit 已按此設定。防洗版 limiter 及 feed lock
  都只存在記憶體。
- 如要修改每份份量、cooldown 或開放時間，只需編輯 `.env` 並重啟，毋須修改程式碼。
