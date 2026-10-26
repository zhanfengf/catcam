# Changelog

版本記錄,新嘅喺上面。每項列返對應嘅 git commit hash,想睇完整 diff 用 `git show <hash>`。

純 Proxmox host/CT 層面嘅設定(例如 CT 114 嘅 `dev0` GPU passthrough、記憶體分配、`/etc/apt/sources.list.d/pve-enterprise.sources`)**唔屬於呢個 repo 嘅範圍**,呢類改動只會記喺 `my-homelab` skill 同每日工作日誌,呢度唔會列。`go2rtc.yaml`/`go2rtc.service` 本身由 `v0.8.0` 開始已經帶入 `catcam-backend/deploy/go2rtc/`,有埋正常 commit history。

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
