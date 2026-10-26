# Changelog

版本記錄,新嘅喺上面。每項列返對應嘅 git commit hash,想睇完整 diff 用 `git show <hash>`。

純 Proxmox host/CT 層面嘅設定(例如 CT 114 嘅 `dev0` GPU passthrough、記憶體分配、`/etc/apt/sources.list.d/pve-enterprise.sources`)**唔屬於呢個 repo 嘅範圍**,呢類改動只會記喺 `my-homelab` skill 同每日工作日誌,呢度唔會列。`go2rtc.yaml`/`go2rtc.service` 本身由 `v0.8.0` 開始已經帶入 `catcam-backend/deploy/go2rtc/`,有埋正常 commit history。

## v0.13.6 — ⓘ hover 改做淨係變綠字(2026-10-27)

- `37ca01a` Simplify the info (ⓘ) hover to just a green glyph——按更正,標題嘅 ⓘ 掣 hover 只變綠色字體(`--accent-strong`),唔要 v0.13.5 加嘅正方形外框同 10% 透明綠底。✕ 同 Instagram chip 維持完整 `button-ghost`(框 + 字 + 底),ⓘ 就淨係變色。純前端。

## v0.13.5 — 標題 ⓘ 掣都套用 button-ghost hover(2026-10-27)

- `fef907a` Apply the button-ghost hover to the title info (ⓘ) button——「Roll Roll 直播」標題隔籬嗰個 ⓘ 掣,hover 都換成同公告 ✕、Instagram chip 一致嘅 Lattice `button-ghost` pattern(綠色正方形框 + 綠色圖示 + 10% 透明綠底)。bare icon 掣預留 2px 透明框防跳位。純前端。

## v0.13.4 — 公告 ✕ hover 補 10% 透明綠底(Lattice button-ghost pattern)(2026-10-27)

- `d02325c` Add the 10% emerald wash to the announcement close-button hover——承接 v0.13.3,公告彈窗 ✕ 嘅 hover 補返 `rgba(6, 201, 136, 0.1)` 10% 透明綠底,令佢同 Instagram handle chip 完全一致。呢個「綠框 + 綠字/圖示 + 10% 透明綠底」嘅 hover 已經正式記入個人 Lattice design-system(`200_Reference/design-systems/lattice/DESIGN.md`)做 `button-ghost` component + `primary-wash` 色票,係該系統唯一有記錄嘅 hover pattern。純前端。

## v0.13.3 — 公告彈窗 ✕ hover 加綠色正方形外框(2026-10-27)

- `1039259` Add a green square hover frame to the announcement close button——公告彈窗嘅 ✕ 關閉掣,滑鼠移上去時外面加一個綠色正方形外框、✕ 本身都變綠(`--accent-strong`)。只針對 `.announcement-modal .modal-close`,唔影響其他 modal 共用嘅關閉掣;預設留咗一層透明 2px border,所以 hover 出框時唔會推移到個 ✕。純前端。

## v0.13.2 — 公告彈窗加大 2 倍 + 文字加大(2026-10-26)

- `4230247` Enlarge the announcement popup ~2x with bigger text——公告彈窗同秘密通道嘅密碼 modal 共用 `.modal` 樣式,所以加咗一個 `.announcement-modal` 修飾 class,淨係放大公告呢個(`max-width` 340→640px、文字 14→23px、icon 同 ✕ 都放大),唔影響密碼 modal。純前端。

## v0.13.1 — 電腦版直播佈滿畫面,刪走動態欄副標題(2026-10-26)

- `8022900` Make the live view fill the desktop viewport, drop the activity subtitle——電腦版(≥1100px)直播畫面由原本置中封頂 1550px 改做佈滿成個視窗闊度(`main` 嘅 `max-width` 由 1550px 改做 `none`),同時俾 `.stage` 加咗 `max-height: calc(100vh - 160px)`,確保闊畫面喺矮視窗都唔會 overflow(video 本身 `object-fit:cover`,係裁切而唔係變形)。手機版維持動態欄疊喺直播下面。順手刪走「餵食動態」標題下面嗰句「每次餵 Roll Roll 都會自動留低一條 60 秒錄影」副標題。純前端 CSS/markup,冇郁後端同 Caddy。

## v0.13.0 — 直播側邊「餵食動態」欄,兩段式餵咗 + 錄影好咗(2026-10-26)

- `45ca110` Add a two-phase public feeding activity feed——直播畫面右邊加咗一欄「餵食動態」(闊芒並排、窄芒疊落畫面下面),唯讀,畀所有訪客睇。每一次真實出糧出**兩條**聊天式訊息:偵測到嗰刻即出「🍚 餵咗 Roll Roll 錄影整緊…」,約一分鐘後錄影 render 好再出「📹 錄影好咗,睇返錄影 ›」(撳得,用返現有 `/clips/<file>` lightbox 播放器)。後端新開一張 `feed_event` 表(`fed_at` + `clip` + `clip_ready_at`):`recorder.py` 喺偵測到出糧嗰刻(`_poll_loop`)即刻 insert 一行(`clip` 做 NULL),錄影整好先 `set_feed_event_clip()` 補返 clip——即係同觸發錄影同一個 `times_dispensed` 信號,所以**連 PetKit app、機身掣、自動餵都影到**,唔止網站觸發嘅餵食。新加嘅 `GET /activity` 回傳今日嘅事件,前端用 `activityLines` 展開成兩行再按時間排。故意同 `feed_log`(「訪客餵食咗」統計,淨係網站餵食、冇錄影資訊)分開兩張表做兩件事,完全冇改動現有嘅餵食/統計邏輯。Caddy `@api` 清單同步加咗 `/activity` route(兩份 Caddyfile 都改,避開之前中過兩次嘅 SPA fallback 伏)。`feed_event` 由後端重啟嗰刻先開始記,之前嘅餵食唔會追溯顯示。

## v0.12.0 — 大聲公重開公告制 + 全站自訂 cursor(2026-10-26)

- `b5cfd9a` Add a megaphone re-open button and site-wide custom cursors——語言切換掣左面加咗一粒大聲公 icon(淨係喺有公告時先顯示),撳落去會強制重新彈出公告 card,唔理 `localStorage` 記住嘅關閉狀態。同時幫成個網站換咗自訂 cursor:general cursor 係實心黑色三角箭嘴(加咗白邊,確保喺鏡頭直播深色畫面都唔會隱形);可以撳嘅元素(掣、連結)就用深藍色粗線手指(Lucide `pointer`,白色圓角方塊做底,避免透明背景喺任何地方都睇唔清)。全部用一個 `--cursor-pointer` CSS variable 集中管理——Svelte scoped style 嘅 class 選擇器優先權永遠高過單純 `button` 選擇器,所以逐個元件散落嘅 `cursor: pointer;` 改用返呢個變數,一次維護、處處生效

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
