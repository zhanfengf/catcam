# Changelog

版本記錄,新嘅喺上面。每項列返對應嘅 git commit hash,想睇完整 diff 用 `git show <hash>`。

有部分基建層面嘅改動(CT 114 上嘅 `go2rtc.yaml`/`go2rtc.service`、Proxmox 設定)**冇喺呢個 repo 嘅 git history 入面**——呢兩個檔案本身就冇受 git 追蹤(淨係喺 CT 114 度留 `.bak` 備份),所以呢類改動會喺呢份 changelog 入面獨立列出,但唔會有對應嘅 commit hash。

## Unreleased(基建,唔喺呢個 repo 嘅 git history 入面)

- **go2rtc 直播編碼由軟件轉做 VAAPI 硬件編碼**(2026-10-26):`petkit_h264` stream 由 `ffmpeg:...#video=h264` 簡寫(內部用 `libx264` 軟件編碼)改做手寫 `exec:` 命令,用 `h264_vaapi` 經 CT 114 嘅 `/dev/dri/renderD128` 做硬件編碼。CPU 由 ~40% 跌到 ~15%(單核)。隨附改動:CT 114 加 `/dev/dri` passthrough(`dev0`)、RAM 由 512MB 加到 4096MB、go2rtc.yaml 改用 plain YAML scalar 避開 `\:` escape 問題、`-vf` 值要完整用雙引號包住先唔會俾 go2rtc 嘅 `exec:` 解析器因為內部空格拆散。改動位置:CT 114 嘅 `/opt/go2rtc/go2rtc.yaml`(備份喺同一目錄 `.bak-pre-vaapi`)。

## v0.7 — Gallery 互動 + LIVE 狀態反映真實連線(2026-10-25 – 2026-10-26)

- `b96a112` Clarify that feed clip recording triggers on any real dispense
- `a12223b` Tie the LIVE badge to the actual camera WS connection state
- `669c990` Add hover glow to gallery photos; fix clipping on all four sides

## v0.6 — 餵食錄影 + 每週精華(2026-10-25)

- `173896d` Document feed-clip recording, weekly highlights, and info-modal docs
- `1f99ba1` Add per-feed clip recording, weekly highlight reel, and info-modal polish

## v0.5 — Roll Roll 資料卡(2026-10-25)

- `4b4c7fa` Polish Roll Roll info modal: lightbox, layout, Lattice styling
- `29eb17a` Add Roll Roll info modal with bio, Instagram link, and photo gallery

## v0.4 — PetKit 餵食紀錄 + 冷卻時間分離(2026-10-25)

- `641cc36` Update docs for the times_dispensed history fix and label rename
- `9facff6` Fix feed-history lag; auto-refresh after admin feed
- `13206cb` Rename visitor-feed stat label to 訪客餵食咗
- `2dcb642` Add PetKit feed-history view to the admin channel; tighten visitor-feed stat
- `07ba756` Isolate admin feed cooldown from public, burn timestamp into stream, polish stage controls

## v0.3 — UI 重做,Lattice design system(2026-10-25)

- `aa9394f` Update docs to match current architecture
- `534d269` Shrink desktop video width so the hint line fits without scrolling
- `a641daa` Replace admin accent color with Design.md teal-to-orange gradient; tidy hint punctuation
- `604eebb` Polish layout: bigger video, tighter header, admin-only stat
- `01e6a8a` Redesign UI: overlay controls on video, LIVE badge, zh/en toggle
- `64206b9` Switch to Lattice light theme and brighten primary green
- `09ab6d5` Rebrand UI to Roll Roll with Lattice Dark color system

## v0.2 — 直播 + 秘密管理通道(2026-10-25)

- `5a9d515` Add secret admin channel and live camera streaming

## v0.1 — 初始架構(2026-09-07)

- `69f31e7` add README on top-level
- `71a876a` add backend and frontend
- `0367bfe` first commit
