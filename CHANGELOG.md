# Changelog

版本記錄,新嘅喺上面。每項列返對應嘅 git commit hash,想睇完整 diff 用 `git show <hash>`。

純 Proxmox host/CT 層面嘅設定(例如 CT 114 嘅 `dev0` GPU passthrough、記憶體分配、`/etc/apt/sources.list.d/pve-enterprise.sources`)**唔屬於呢個 repo 嘅範圍**,呢類改動只會記喺 `my-homelab` skill 同每日工作日誌,呢度唔會列。`go2rtc.yaml`/`go2rtc.service` 本身由 `v0.8.0` 開始已經帶入 `catcam-backend/deploy/go2rtc/`,有埋正常 commit history。

## v0.11.0 — 公告欄 + 歷史紀錄,補齊 README 文檔(2026-10-26)

- `cd538b2` Document the announcement banner, admin_test tagging, and HA offline check——兩份 README 之前已經同 `app/main.py` 脫節——Endpoints 表完全冇列 `/admin/feed-test`、`/admin/announcement`,冇提過 `ha_online`、`feed_log` 嘅 `admin_test:` 標記、公告彈窗嘅 dismiss 邏輯。另外明文記低今次踩咗兩次嘅 Caddyfile 伏:新加任何 `/admin/*` route,CT 本機嘅 `@api path` 清單(唔淨係 repo 複本)都要同步更新,否則請求靜默跌落 SPA fallback,攞住 HTML 當 JSON 解析
- `ceea45a` Add announcement banner with an append-only history log——秘密通道可以推一句自由文字俾所有訪客(`POST /admin/announcement`),`GET /status` 帶返呢個文字,前端一入站就彈出(重用現有 `.modal` 樣式),撳 ✕ 關閉會記住**實際文字**落 `localStorage`,所以改咗公告內容會令所有人(包括之前已經撳過關閉嘅)再見到一次。`state.announcement` 淨係存現時生效緊嗰個值(同 `last_fed_at` 一樣嘅 upsert 寫法),獨立開多一張 `announcement_log` table 每次儲存都 append 一行——故意唔用同一行解決兩個唔同問題(「而家生效緊嘅係乜」vs「過去出過咩、幾時出」)

## v0.10.0 — HA 離線偵測、模擬訪客測試出糧、README 截圖(2026-10-26)

- `7784459` Add screenshot gallery to README——截咗餵貓制四種狀態(ready/cooldown/outside-hours/ha-offline)同已解鎖嘅 admin 面板,放入 `docs/screenshots/`;ha-offline 嗰張特登喺 Playwright 層面擋晒 camera 嘅 WebSocket(連 constructor 都 mock 咗)同 HLS fallback 先截,因為真實 HA 斷晒嗰陣連鏡頭都會一齊斷,唔淨係餵貓制
- `3d23b1f` Add HA offline detection and an admin-only simulated-visitor test feed——背景 task 每 15 秒獨立 ping 一次 HA,`/status` 帶多個 `ha_online` 欄位,一旦 HA 連唔到就覆蓋返 `can_feed`/`reason`,前端餵貓制會喺 ~15 秒內自動 disable、顯示「🔌 餵食機離線」,唔使等訪客撳落先見到 502。同時喺秘密通道加咗一粒「🧪 模擬訪客出糧」制(`/admin/feed-test`),出真糧測試成條 dispense pipeline,用 `admin_test:` 標記喺 `feed_log` 排除喺公開「訪客餵食咗」統計同公眾冷卻時間之外(同原有嘅 `admin:` 強制餵分開嚟)
- `654c8af` Add logging for recorder's silent live-export fallback failures——`recorder.py` 之前 buffer 空咗、或者 live export 嗰個 HTTP call 失敗,會完全靜默咁跳過,而家加返 warning log,下次有「冇生成錄影」嘅報告可以直接喺 log 查到實際卡喺邊一步

今次三個 commit 全部由一次真實嘅 PetKit/Agora WebRTC 斷流事件(2026-10-26,前後斷咗成 45 分鐘)直接驅動——斷流本身發生喺 go2rtc↔Home Assistant 呢一層,同呢個 repo 嘅程式碼完全無關,純屬上游雲端服務嘅瞬斷;但事件暴露咗兩個缺口:冇辦法喺 HA 斷咗嗰刻主動通知訪客(只能等佢撳落先見到錯誤),同埋出糧流程冇一個安全嘅測試手段(每次測試都要用返會污染公開統計嘅強制餵)。呢次改動就係填返呢兩個缺口。

## v0.9.0 — 24/7 pre-roll 緩衝,餵食片終於見到 Roll Roll 跑過去(2026-10-26)

- `42b426f` Add precise keyframe-accurate trim to the pre-roll splice, tune the window——幫 pre-roll 拼接加多一步精準裁剪(`-ss`/`-t` 喺 concat 完嘅片度再裁一次,`-c copy` 唔轉碼),將原本「成個 5 秒 segment 粗粒度」嘅精度,提升到受限於 keyframe 間距(~1.8 秒)嘅水平。同時將 `pre_roll_seconds`/`post_roll_seconds` 由最初嘅 3/57 調校到 15/45(覆蓋返實測 ~15 秒嘅觸發偵測延遲),總長維持 60 秒
- `0ada9ec` Document pre-roll vs 24/7 buffering distinction and the full splice pipeline——喺 README 補充「pre-roll 係目標、24/7 緩衝係唯一做得到嘅手段」嘅概念解釋,加埋對比表同線性時間軸圖,方便之後參考
- `1b2b391` Add 24/7 pre-roll buffer so feed clips show the cat running over——新增 `app/buffer.py`,24/7 用 `-c copy` 由 go2rtc 嘅 RTSP 攞 `petkit_h264`,切做 5 秒一段嘅 rolling buffer;`recorder.py` 出糧觸發時由 buffer 拼返「觸發前 + 觸發後」嘅畫面,唔再淨係靠觸發後先開始錄(之前嘅做法無論幾快都影唔到貓跑過去,因為根本冧咗做咗嘅畫面冇得補錄)

端對端驗證咗兩次:觸發出糧,片頭第一幀嘅燒入時間戳同「觸發時間 - pre_roll_seconds」計算出嚟嘅數值完全脗合(其中一次仲啱啱好對正咗真實撳制嗰一刻)。

## v0.8.0 — go2rtc VAAPI 硬件編碼 + 設定帶入版本控制(2026-10-26)

- `de8cec7` Bring go2rtc.yaml/service under version control, starting with the VAAPI switch——`petkit_h264` stream 由 `ffmpeg:...#video=h264` 簡寫(內部用 `libx264` 軟件編碼)改做手寫 `exec:` 命令,用 `h264_vaapi` 經 CT 114 嘅 `/dev/dri/renderD128` 做硬件編碼,CPU 由 ~40% 跌到 ~15%(單核)。同時將 `go2rtc.yaml`/`go2rtc.service` 由「只喺 CT 114 度留 `.bak`、零 git history」帶入呢個 repo(`catcam-backend/deploy/go2rtc/`),之後改動都有真正 diff 可以睇

## v0.7.0 — Gallery 互動 + LIVE 狀態反映真實連線(2026-10-25 – 2026-10-26)

- `b96a112` Clarify that feed clip recording triggers on any real dispense
- `a12223b` Tie the LIVE badge to the actual camera WS connection state
- `669c990` Add hover glow to gallery photos; fix clipping on all four sides

## v0.6.0 — 餵食錄影 + 每週精華(2026-10-25)

- `173896d` Document feed-clip recording, weekly highlights, and info-modal docs
- `1f99ba1` Add per-feed clip recording, weekly highlight reel, and info-modal polish

## v0.5.0 — Roll Roll 資料卡(2026-10-25)

- `4b4c7fa` Polish Roll Roll info modal: lightbox, layout, Lattice styling
- `29eb17a` Add Roll Roll info modal with bio, Instagram link, and photo gallery

## v0.4.0 — PetKit 餵食紀錄 + 冷卻時間分離(2026-10-25)

- `641cc36` Update docs for the times_dispensed history fix and label rename
- `9facff6` Fix feed-history lag; auto-refresh after admin feed
- `13206cb` Rename visitor-feed stat label to 訪客餵食咗
- `2dcb642` Add PetKit feed-history view to the admin channel; tighten visitor-feed stat
- `07ba756` Isolate admin feed cooldown from public, burn timestamp into stream, polish stage controls

## v0.3.0 — UI 重做,Lattice design system(2026-10-25)

- `aa9394f` Update docs to match current architecture
- `534d269` Shrink desktop video width so the hint line fits without scrolling
- `a641daa` Replace admin accent color with Design.md teal-to-orange gradient; tidy hint punctuation
- `604eebb` Polish layout: bigger video, tighter header, admin-only stat
- `01e6a8a` Redesign UI: overlay controls on video, LIVE badge, zh/en toggle
- `64206b9` Switch to Lattice light theme and brighten primary green
- `09ab6d5` Rebrand UI to Roll Roll with Lattice Dark color system

## v0.2.0 — 直播 + 秘密管理通道(2026-10-25)

- `5a9d515` Add secret admin channel and live camera streaming

## v0.1.0 — 初始架構(2026-09-07)

- `69f31e7` add README on top-level
- `71a876a` add backend and frontend
- `0367bfe` first commit
