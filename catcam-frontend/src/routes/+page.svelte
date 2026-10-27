<script>
  import { onMount, onDestroy, afterUpdate } from 'svelte';
  import '../app.css';
  import { getStatus, feed, adminFeed, adminFeedTest, adminSetAnnouncement, adminSetAutoFeed, adminHistory, getRecordings, getActivity } from '$lib/api.js';
  import { VideoRTC } from '$lib/video-rtc.js';

  const ADMIN_TOKEN_KEY = 'catcam_admin_token';
  const LANG_KEY = 'catcam_lang';

  const ROLL_ROLL_NAME = 'Roll Roll';
  const INSTAGRAM_URL = 'https://www.instagram.com/familieskhm';
  const INSTAGRAM_HANDLE = '@familieskhm';
  // fill in once a real Roll Roll highlight video is ready — the
  // "今集精華" section stays hidden until this is set
  const HIGHLIGHT_VIDEO_URL = '';
  const PHOTOS = [
    '/photos/rollroll-1.jpg',
    '/photos/rollroll-2.jpg',
    '/photos/rollroll-3.jpg',
    '/photos/rollroll-4.jpg',
    '/photos/rollroll-5.jpg'
  ];

  const translations = {
    zh: {
      title: 'Roll Roll直播',
      live: '直播中',
      liveOffline: '離線',
      feedBtnFeeding: '餵緊…',
      feedBtnReady: '🍚 餵貓',
      fedToday: '訪客餵食咗',
      times: '次',
      hintLine1: (min, g) => `每 ${min} 分鐘可以餵一次（${g}g），`,
      hintLine2: (close) => `夜晚 ${close} 之後 Roll Roll 要瞓覺喇 🌙`,
      hintLine3: (open, close) => `每日 ${open} - ${close} 開放`,
      connErr: '連唔到伺服器，遲啲再試',
      fedFallback: '餵咗喇！🐱',
      cantFeedFallback: '而家餵唔到',
      feederOffline: '🔌 餵食機離線',
      streamOffline: '📷 直播中斷，暫時餵唔到',
      secretTitle: '秘密通道',
      secretSub: '輸入密碼解鎖管理工具',
      pwPlaceholder: '輸入密碼',
      unlockBtn: '解鎖',
      unlockedToast: '已解鎖秘密通道 🔓',
      lockedToast: '已鎖返',
      adminFeedReady: '🔓 強制餵貓（繞過規則）',
      adminFeedFeeding: '強制餵緊…',
      adminFedFallback: '強制餵咗喇！🔓🐱',
      adminTestReady: '🧪 模擬訪客出糧（唔計統計）',
      adminTestFeeding: '模擬出糧緊…',
      adminTestFallback: '模擬出糧完成，冇影響真實統計！🧪🐱',
      announcementSectionTitle: '📢 公告欄',
      announcementPlaceholder: '輸入公告內容，留空即係唔顯示',
      announcementSaveBtn: '儲存公告',
      announcementSaving: '儲存緊…',
      announcementSaved: '公告已更新！📢',
      announcementSaveFail: '儲存失敗',
      announcementBtnLabel: '睇公告',
      autoFeedSectionTitle: '🤖 自動餵食時段',
      autoFeedHint: '每行一個時段 HH:MM-HH:MM。時段完結時如果冇人餵過，就自動餵一份。',
      autoFeedPlaceholder: '例如：\n07:00-07:30\n18:00-18:30',
      autoFeedSaveBtn: '儲存時段',
      autoFeedSaving: '儲存緊…',
      autoFeedSaved: '自動餵食時段已更新！🤖',
      autoFeedSaveFail: '儲存失敗',
      activityAutoMsg: (w, min) => `🤖 冇人喺 ${w} 餵 Roll Roll，自動餵咗一份乾糧。下次可以餵：${min} 分鐘後`,
      wrongPwFallback: '密碼唔啱或者已過期',
      adminLockBtn: '🔒 鎖返',
      refreshLabel: '重新整理鏡頭',
      durH: (h, m) => `${h} 小時 ${m} 分鐘`,
      durM: (m, s) => `${m} 分 ${s} 秒`,
      durS: (s) => `${s} 秒`,
      historyTitle: '今日餵食紀錄（PetKit）',
      historyNote: '裝置本身偵測到嘅每次出糧，包括網站、App、機身按鈕、排程自動餵。PetKit 雲端同步有延遲，啱啱出糧可能要等幾分鐘先顯示',
      historyLoading: '載入緊…',
      historyEmpty: '暫時冇紀錄',
      historyError: '攞唔到紀錄',
      historyRefresh: '重新整理紀錄',
      infoLabel: 'Roll Roll 資料',
      infoSubtitle: '2025年8月生・香港🇭🇰',
      infoBio: '哈囉～我係Roll Roll，2025年8月喺香港出世嘅捲耳貓BB 一隻，在2026年4月見到媽媽，收編了媽媽。最鍾意瞓覺、食嘢同俾人摸頭。你而家睇緊嘅就係我屋企，鏡頭直接對住我嘅食盆，等緊你嚟探我！',
      infoFeedTitle: '🍚 餵我',
      infoFeedText: '撳「餵貓」掣就會自動餵我食一份乾糧。但係唔好餵太多啊：每 120 分鐘先可以餵一次，每日 07:00 - 23:59（香港時間）開放，夜晚我要瞓覺㗎～',
      infoPhotosTitle: '📷 影過嘅相',
      infoHighlightTitle: '📺 今集精華',
      recordingsRowTitle: '餵食錄影',
      recordingsRowSub: '睇返每次餵 Roll Roll 嘅 60 秒短片',
      recordingsTitle: '餵食錄影',
      recordingsSub: '最近 7 日嘅 60 秒短片',
      recordingsLoading: '載入緊…',
      recordingsEmpty: '暫時冇錄影',
      recordingsError: '攞唔到錄影',
      recordingsColTime: '時間',
      activityTitle: '餵食動態',
      activitySystem: '系統 / system',
      activityFedMsg: '🍚 啱啱餵咗 Roll Roll',
      activityFedPending: '錄影整緊…',
      activityClipMsg: '📹 錄影好咗',
      activityWatch: '睇返錄影',
      activityLoading: '載入緊…',
      activityEmpty: '暫時仲未有餵食紀錄',
      activityError: '攞唔到動態'
    },
    en: {
      title: 'Roll Roll Live',
      live: 'LIVE',
      liveOffline: 'Offline',
      feedBtnFeeding: 'Feeding…',
      feedBtnReady: '🍚 Feed Cat',
      fedToday: 'Fed by visitors',
      times: 'times',
      hintLine1: (min, g) => `Feed once every ${min} min (${g}g),`,
      hintLine2: (close) => `Roll Roll sleeps after ${close} 🌙`,
      hintLine3: (open, close) => `Available ${open} - ${close} HK time`,
      connErr: "Can't connect, try again later",
      fedFallback: 'Fed! 🐱',
      cantFeedFallback: "Can't feed right now",
      feederOffline: '🔌 Feeder Offline',
      streamOffline: '📷 Stream down — can’t feed now',
      secretTitle: 'Secret Channel',
      secretSub: 'Enter password to unlock admin tools',
      pwPlaceholder: 'Password',
      unlockBtn: 'Unlock',
      unlockedToast: 'Secret channel unlocked 🔓',
      lockedToast: 'Locked',
      adminFeedReady: '🔓 Force Feed (bypass rules)',
      adminFeedFeeding: 'Force feeding…',
      adminFedFallback: 'Force fed! 🔓🐱',
      adminTestReady: '🧪 Simulate Visitor Feed (not counted)',
      adminTestFeeding: 'Simulating feed…',
      adminTestFallback: 'Simulated feed done, no effect on real stats! 🧪🐱',
      announcementSectionTitle: '📢 Announcement',
      announcementPlaceholder: 'Announcement text, leave empty to hide it',
      announcementSaveBtn: 'Save announcement',
      announcementSaving: 'Saving…',
      announcementSaved: 'Announcement updated! 📢',
      announcementSaveFail: 'Save failed',
      announcementBtnLabel: 'View announcement',
      autoFeedSectionTitle: '🤖 Auto-feed windows',
      autoFeedHint: 'One window per line, HH:MM-HH:MM. If no one feeds during a window, the cat is auto-fed when it ends.',
      autoFeedPlaceholder: 'e.g.\n07:00-07:30\n18:00-18:30',
      autoFeedSaveBtn: 'Save windows',
      autoFeedSaving: 'Saving…',
      autoFeedSaved: 'Auto-feed windows updated! 🤖',
      autoFeedSaveFail: 'Save failed',
      activityAutoMsg: (w, min) => `🤖 No one fed Roll Roll during ${w}, auto-fed a portion. Next feed in ${min} min`,
      wrongPwFallback: 'Wrong password or expired',
      adminLockBtn: '🔒 Lock',
      refreshLabel: 'Refresh camera',
      durH: (h, m) => `${h}h ${m}m`,
      durM: (m, s) => `${m}m ${s}s`,
      durS: (s) => `${s}s`,
      historyTitle: "Today's Feed History (PetKit)",
      historyNote: "Every dispense the device itself detected — site, app, physical button, or scheduled auto-feed. PetKit's cloud sync lags a few minutes, so a fresh feed may not show immediately",
      historyLoading: 'Loading…',
      historyEmpty: 'No records yet',
      historyError: "Couldn't load history",
      historyRefresh: 'Refresh history',
      infoLabel: 'About Roll Roll',
      infoSubtitle: 'Born Aug 2025 · Hong Kong 🇭🇰',
      infoBio: "Hi, I'm Roll Roll — a curly-eared kitten born in Hong Kong in August 2025. In April 2026 I met my mom and decided to adopt her. I love sleeping, eating, and getting head pats. What you're watching right now is my home — the camera points straight at my food bowl, so come visit me!",
      infoFeedTitle: '🍚 Feed Me',
      infoFeedText: "Press the \"Feed Cat\" button and I'll get one portion of kibble. But don't overfeed me: only once every 120 minutes, open 07:00 - 23:59 (HK time) daily — I need my sleep at night~",
      infoPhotosTitle: '📷 Photos',
      infoHighlightTitle: "📺 This Episode",
      recordingsRowTitle: 'Feeding Clips',
      recordingsRowSub: "Watch back each time Roll Roll's been fed — 60s clips",
      recordingsTitle: 'Feeding Clips',
      recordingsSub: '60-second clips from the last 7 days',
      recordingsLoading: 'Loading…',
      recordingsEmpty: 'No clips yet',
      recordingsError: "Couldn't load clips",
      recordingsColTime: 'Time',
      activityTitle: 'Feeding Activity',
      activitySystem: 'system',
      activityFedMsg: '🍚 Just fed Roll Roll',
      activityFedPending: 'clip rendering…',
      activityClipMsg: '📹 Clip ready',
      activityWatch: 'Watch clip',
      activityLoading: 'Loading…',
      activityEmpty: 'No feeds yet',
      activityError: "Couldn't load activity"
    }
  };

  let lang = 'zh';
  $: t = translations[lang];

  function setLang(l) {
    lang = l;
    localStorage.setItem(LANG_KEY, l);
  }

  let videoRtcEl;

  class CatCamVideo extends VideoRTC {
    constructor() {
      super();
      // Must be set before oninit() ever runs (i.e. before the element
      // upgrades), since oninit() only reads this once to decide whether to
      // register the visibilitychange listener at all — setting it later as
      // a property has no effect, the listener is already attached. Without
      // this, iOS backgrounding the tab (screenshot, lock, app switch) trips
      // the listener and the component closes its own WebSocket 5s later.
      this.visibilityCheck = false;
    }

    oninit() {
      super.oninit();
      // keep the native controls (play/pause, mute, fullscreen, PiP via ⋮) —
      // just tag the video so app.css can hide the one bad part, the timeline
      // scrubber: a live MSE stream has no real timeline, so that bar flickers
      // and resets on hover, looking like the stream keeps reloading. oninit
      // fires once on connectedCallback, so the class survives ws reconnects.
      this.video.classList.add('live-cam');
    }
  }

  let status = null;
  let feeding = false;
  let localSecs = 0;
  let toast = null;
  let toastTimer;
  let pollTimer;
  let tickTimer;
  let offlineRefreshTick = 0;
  let cameraConnected = false;
  let cameraCheckTimer;
  let showInfoModal = false;
  let lightboxSrc = null;
  let showRecordingsModal = false;
  let recordings = null;
  let recordingsLoading = false;
  let recordingsError = false;
  let playingClip = null;

  let activity = null;
  let activityLoading = false;
  let activityError = false;
  let activityTimer;
  let activityFeedEl;
  let lastActivityCount = 0;

  // chat-style feed: keep the newest line in view at the bottom. only scroll
  // when the number of lines actually changes (a new feed/clip), not on every
  // 15s status re-render — otherwise it'd fight a user scrolling up to read back
  afterUpdate(() => {
    if (activityFeedEl && activityLines.length !== lastActivityCount) {
      activityFeedEl.scrollTop = activityFeedEl.scrollHeight;
      lastActivityCount = activityLines.length;
    }
  });

  let secretTapCount = 0;
  let secretTapTimer;
  let showAdminModal = false;
  let adminPassword = '';
  let adminToken = null;
  let adminFeeding = false;
  let adminTesting = false;
  let history = null;
  let historyLoading = false;
  let historyError = false;

  const ANNOUNCEMENT_DISMISSED_KEY = 'catcam_announcement_dismissed';
  let showAnnouncement = false;
  let announcementDraft = null;
  let savingAnnouncement = false;
  let autoFeedDraft = null;
  let savingAutoFeed = false;

  async function refresh() {
    try {
      status = await getStatus();
      localSecs = status.seconds_until_next ?? 0;
    } catch (e) {
      showToast('err', t.connErr);
    }
  }

  function showToast(type, text) {
    toast = { type, text };
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => (toast = null), 4000);
  }

  async function onFeed() {
    if (feeding || !status?.can_feed) return;
    feeding = true;
    const { httpOk, data } = await feed();
    feeding = false;
    if (httpOk && data.ok) {
      showToast('ok', data.message || t.fedFallback);
    } else {
      showToast(data.reason === 'outside_hours' ? 'warn' : 'warn',
        data.message || t.cantFeedFallback);
    }
    await refresh();
  }

  // tr is passed explicitly (not read from the closed-over `t`) so Svelte's
  // template dependency tracking — which only sees the literal arguments at
  // the call site, not what the function reads internally — re-runs this
  // when the language toggles, not just when localSecs ticks.
  function fmt(secs, tr) {
    if (secs <= 0) return '';
    const h = Math.floor(secs / 3600);
    const m = Math.floor((secs % 3600) / 60);
    const s = secs % 60;
    if (h > 0) return tr.durH(h, m);
    if (m > 0) return tr.durM(m, String(s).padStart(2, '0'));
    return tr.durS(s);
  }

  function onLogoClick() {
    secretTapCount += 1;
    clearTimeout(secretTapTimer);
    secretTapTimer = setTimeout(() => (secretTapCount = 0), 1500);
    if (secretTapCount >= 5) {
      secretTapCount = 0;
      adminPassword = '';
      showAdminModal = true;
    }
  }

  function openInfoModal() {
    showInfoModal = true;
  }

  function closeInfoModal() {
    showInfoModal = false;
  }

  function openRecordingsModal() {
    showRecordingsModal = true;
    loadRecordings();
  }

  function closeRecordingsModal() {
    showRecordingsModal = false;
  }

  async function loadRecordings() {
    recordingsLoading = true;
    recordingsError = false;
    try {
      const data = await getRecordings();
      recordings = data.recordings || [];
    } catch (e) {
      recordingsError = true;
    }
    recordingsLoading = false;
  }

  // every real dispense (site/app/physical/auto) lands one feed_event, with
  // its clip filled in ~1 min later once the recording renders. activityLoading
  // only gates the very first load; later polls refresh in place without
  // flashing the loading state over an already-populated feed
  async function loadActivity() {
    if (activity === null) activityLoading = true;
    try {
      const data = await getActivity();
      activity = data.events || [];
      activityError = false;
    } catch (e) {
      activityError = true;
    }
    activityLoading = false;
  }

  // two-phase: each event becomes a "fed" line at fed_at, plus — once its clip
  // exists — a separate "clip ready" line at clip_ready_at. flattened and
  // sorted oldest-first (chat style) so each "餵咗 → 錄影好咗" pair reads top
  // to bottom; the feed auto-scrolls to the newest at the bottom
  $: activityLines = (activity || [])
    .flatMap((e) => {
      // "錄影整緊…" only while the clip hasn't landed — once it has, the
      // separate "clip ready" line carries the link and the fed line is plain
      const lines = [{ kind: 'fed', at: e.fed_at, pending: !e.clip, source: e.source, note: e.note }];
      if (e.clip) {
        lines.push({ kind: 'clip', at: e.clip_ready_at || e.fed_at, clip: e.clip });
      }
      return lines;
    })
    .sort((a, b) => (a.at < b.at ? -1 : a.at > b.at ? 1 : 0));

  function formatRecordingTime(iso) {
    const d = new Date(iso);
    const parts = Object.fromEntries(
      new Intl.DateTimeFormat('en-GB', {
        timeZone: 'Asia/Hong_Kong',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        hour12: false
      })
        .formatToParts(d)
        .map((p) => [p.type, p.value])
    );
    return `${parts.month}-${parts.day} ${parts.hour}:${parts.minute}`;
  }

  function closeAdminModal() {
    showAdminModal = false;
    adminPassword = '';
  }

  function unlockAdmin() {
    const token = adminPassword.trim();
    if (!token) return;
    adminToken = token;
    localStorage.setItem(ADMIN_TOKEN_KEY, token);
    closeAdminModal();
    showToast('ok', t.unlockedToast);
    loadHistory();
  }

  function lockAdmin() {
    adminToken = null;
    localStorage.removeItem(ADMIN_TOKEN_KEY);
    showToast('ok', t.lockedToast);
    history = null;
    announcementDraft = null;
    autoFeedDraft = null;
  }

  function formatPetkitTime(ts) {
    // PetKit's history API returns naive HK-local timestamps (no offset);
    // only today's events are shown, so just the time is enough
    if (!ts) return '';
    const d = new Date(ts + '+08:00');
    return d.toLocaleString('zh-HK', {
      timeZone: 'Asia/Hong_Kong',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false
    });
  }

  async function loadHistory() {
    if (!adminToken) return;
    historyLoading = true;
    historyError = false;
    const { httpOk, data } = await adminHistory(adminToken);
    historyLoading = false;
    if (httpOk && data.ok) {
      history = data.petkit_log || [];
    } else {
      historyError = true;
      if (data.reason === 'unauthorized') lockAdmin();
    }
  }

  async function onAdminFeed() {
    if (adminFeeding || !adminToken) return;
    adminFeeding = true;
    const { httpOk, data } = await adminFeed(adminToken);
    adminFeeding = false;
    if (httpOk && data.ok) {
      showToast('ok', data.message || t.adminFedFallback);
    } else {
      showToast('err', data.message || t.wrongPwFallback);
      if (data.reason === 'unauthorized') {
        lockAdmin();
      }
    }
    await refresh();
    if (adminToken) loadHistory();
  }

  async function onAdminFeedTest() {
    if (adminTesting || !adminToken) return;
    adminTesting = true;
    const { httpOk, data } = await adminFeedTest(adminToken);
    adminTesting = false;
    if (httpOk && data.ok) {
      showToast('ok', data.message || t.adminTestFallback);
    } else {
      showToast('err', data.message || t.wrongPwFallback);
      if (data.reason === 'unauthorized') {
        lockAdmin();
      }
    }
    await refresh();
    if (adminToken) loadHistory();
  }

  // pops up once per distinct announcement text — dismissing stores that
  // exact text, so only a genuinely new/changed announcement re-opens it
  $: if (status?.announcement && status.announcement !== localStorage.getItem(ANNOUNCEMENT_DISMISSED_KEY)) {
    showAnnouncement = true;
  }

  function dismissAnnouncement() {
    localStorage.setItem(ANNOUNCEMENT_DISMISSED_KEY, status.announcement);
    showAnnouncement = false;
  }

  function openAnnouncement() {
    if (status?.announcement) showAnnouncement = true;
  }

  // one-time prefill when the admin panel first has both a token and a
  // loaded status — not a plain assignment on every status poll, which
  // would wipe out whatever the admin is mid-typing every 15s
  $: if (adminToken && status && announcementDraft === null) {
    announcementDraft = status.announcement ?? '';
  }

  // one-time prefill of the auto-feed windows textarea (same guard as above)
  $: if (adminToken && status && autoFeedDraft === null) {
    autoFeedDraft = (status.auto_feed_windows ?? []).join('\n');
  }

  async function onSaveAnnouncement() {
    if (savingAnnouncement || !adminToken) return;
    savingAnnouncement = true;
    const { httpOk, data } = await adminSetAnnouncement(adminToken, announcementDraft ?? '');
    savingAnnouncement = false;
    if (httpOk && data.ok) {
      showToast('ok', t.announcementSaved);
    } else {
      showToast('err', data.message || t.announcementSaveFail);
      if (data.reason === 'unauthorized') {
        lockAdmin();
      }
    }
    await refresh();
  }

  async function onSaveAutoFeed() {
    if (savingAutoFeed || !adminToken) return;
    savingAutoFeed = true;
    const windows = (autoFeedDraft ?? '')
      .split('\n')
      .map((l) => l.trim())
      .filter(Boolean);
    const { httpOk, data } = await adminSetAutoFeed(adminToken, windows);
    savingAutoFeed = false;
    if (httpOk && data.ok) {
      // reflect the server's validated/normalised list back into the textarea
      autoFeedDraft = (data.auto_feed_windows ?? []).join('\n');
      showToast('ok', t.autoFeedSaved);
    } else {
      showToast('err', data.message || t.autoFeedSaveFail);
      if (data.reason === 'unauthorized') {
        lockAdmin();
      }
    }
    await refresh();
  }

  $: canFeed = status?.can_feed;
  $: btnLabel = feeding
    ? t.feedBtnFeeding
    : canFeed
      ? t.feedBtnReady
      : status?.reason === 'ha_offline'
        ? t.feederOffline
        : status?.reason === 'stream_offline'
          ? t.streamOffline
          : `${t.feedBtnReady} ${fmt(localSecs, t)}`.trim();

  function initCamera() {
    if (!videoRtcEl) return;
    if (!customElements.get('video-rtc')) {
      customElements.define('video-rtc', CatCamVideo);
    }
    // webrtc/mjpeg dropped: webrtc media can't cross the Cloudflare Tunnel
    // (HTTP-only), and go2rtc's HLS here is a fixed 2-segment window that
    // can't absorb tunnel latency. mse (WebSocket) is what actually works.
    videoRtcEl.mode = 'mse,hls';
    // iOS Safari's ManagedMediaSource stays suspended (black frame, no error)
    // unless the video element has autoplay+muted — go2rtc's component doesn't
    // set these itself. Apple's own MMS reference code sets both explicitly.
    if (videoRtcEl.video) {
      videoRtcEl.video.autoplay = true;
      videoRtcEl.video.muted = true;
    }
    // petkit_h264, not petkit: go2rtc's raw WHEP pull declares a codec that
    // doesn't match the real bitstream (SDP says Baseline L3.1, actual is
    // High L5.1) — desktop ignores the mismatch, iOS Safari's MSE doesn't.
    // petkit_h264 is a clean ffmpeg re-encode, self-consistent, iOS-safe.
    videoRtcEl.src = '/camera/ws?src=petkit_h264';
  }

  function refreshCamera() {
    videoRtcEl?.ondisconnect?.();
    initCamera();
  }

  function checkCameraConnection() {
    cameraConnected = videoRtcEl?.wsState === WebSocket.OPEN;
  }

  onMount(() => {
    lang = localStorage.getItem(LANG_KEY) || 'zh';
    adminToken = localStorage.getItem(ADMIN_TOKEN_KEY);
    if (adminToken) loadHistory();
    refresh();
    loadActivity();
    pollTimer = setInterval(refresh, 15000);
    // a fresh clip only lands ~1 min after a feed (post-roll + ffmpeg), so a
    // slower 30s cadence is plenty and keeps /recordings cheap
    activityTimer = setInterval(loadActivity, 30000);
    tickTimer = setInterval(() => {
      if (localSecs > 0) localSecs -= 1;
      else if (status && !status.can_feed) refresh();
      // while the feeder/stream is offline, poll faster than the 15s main
      // cycle so the button snaps back the moment it recovers (e.g. right
      // after stream auto-recovery) instead of lingering on "直播中斷"
      if (status && (status.reason === 'stream_offline' || status.reason === 'ha_offline')) {
        if (++offlineRefreshTick >= 4) { offlineRefreshTick = 0; refresh(); }
      } else {
        offlineRefreshTick = 0;
      }
    }, 1000);
    initCamera();
    cameraCheckTimer = setInterval(checkCameraConnection, 3000);
  });

  onDestroy(() => {
    clearInterval(pollTimer);
    clearInterval(tickTimer);
    clearInterval(cameraCheckTimer);
    clearInterval(activityTimer);
    clearTimeout(toastTimer);
    clearTimeout(secretTapTimer);
    videoRtcEl?.disconnectedCallback?.();
  });
</script>

<svelte:head>
  <title>{t.title}</title>
</svelte:head>

<main>
  <header>
    <div class="brand">
      <!-- svelte-ignore a11y-click-events-have-key-events -->
      <!-- svelte-ignore a11y-no-static-element-interactions -->
      <span class="logo" on:click={onLogoClick}>🐱</span>
      <div class="brand-title">
        <h1>{t.title}</h1>
        <button class="info-btn" on:click={openInfoModal} aria-label={t.infoLabel}>ⓘ</button>
      </div>
    </div>
    <div class="header-right">
      {#if status?.announcement}
        <button class="announcement-btn" on:click={openAnnouncement} aria-label={t.announcementBtnLabel}>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M11 6a13 13 0 0 0 8.4-2.8A1 1 0 0 1 21 4v12a1 1 0 0 1-1.6.8A13 13 0 0 0 11 14H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2z" />
            <path d="M6 14a12 12 0 0 0 2.4 7.2 2 2 0 0 0 3.2-2.4A8 8 0 0 1 10 14" />
            <path d="M8 6v8" />
          </svg>
        </button>
      {/if}
      <div class="lang-toggle">
        <button class:active={lang === 'zh'} on:click={() => setLang('zh')}>繁中</button>
        <button class:active={lang === 'en'} on:click={() => setLang('en')}>EN</button>
      </div>
      <span class="live-badge" class:offline={!cameraConnected}>
        <span class="live-dot"></span>
        {cameraConnected ? t.live : t.liveOffline}
      </span>
    </div>
  </header>

  <div class="live-layout">
    <div class="live-main">
      <section class="stage">
        <video-rtc class="stage-cam" bind:this={videoRtcEl}></video-rtc>
        <button class="stage-refresh" on:click={refreshCamera} aria-label={t.refreshLabel}>↻</button>
        <div class="stage-watermark">cat.kelvinp.work</div>
        <button
          class="stage-feed-btn"
          class:ready={canFeed}
          disabled={!canFeed || feeding}
          on:click={onFeed}
        >
          {btnLabel}
        </button>
      </section>

      <section class="action">
        <p class="hint">
          {t.hintLine1(status?.cooldown_minutes ?? 120, status?.amount ?? 10)}
          {t.hintLine2(status?.window?.close ?? '23:59')}
          {t.hintLine3(status?.window?.open ?? '07:00', status?.window?.close ?? '23:59')}
        </p>
      </section>
    </div>

    <aside class="activity">
      <div class="activity-head">
        <div class="activity-title">{t.activityTitle}</div>
      </div>
      <div class="activity-feed" bind:this={activityFeedEl}>
        {#if activityLoading && !activity}
          <p class="activity-state">{t.activityLoading}</p>
        {:else if activityError}
          <p class="activity-state">{t.activityError}</p>
        {:else if activity && activity.length === 0}
          <p class="activity-state">{t.activityEmpty}</p>
        {:else}
          {#each activityLines as line (line.kind + line.at)}
            {#if line.kind === 'clip'}
              <button class="activity-item" on:click={() => (playingClip = line.clip)}>
                <div class="activity-item-head">
                  <span class="activity-time">{formatRecordingTime(line.at)}</span>
                  <span class="activity-who">{t.activitySystem}</span>
                </div>
                <div class="activity-item-body">
                  {t.activityClipMsg}，<span class="activity-link">{t.activityWatch} ›</span>
                </div>
              </button>
            {:else}
              <div class="activity-item is-fed">
                <div class="activity-item-head">
                  <span class="activity-time">{formatRecordingTime(line.at)}</span>
                  <span class="activity-who">{t.activitySystem}</span>
                </div>
                <div class="activity-item-body">
                  {#if line.source === 'auto' && line.note}
                    {t.activityAutoMsg(line.note, status?.cooldown_minutes ?? 120)}
                  {:else}
                    {t.activityFedMsg}
                  {/if}
                  {#if line.pending}<span class="activity-pending">{t.activityFedPending}</span>{/if}
                </div>
              </div>
            {/if}
          {/each}
        {/if}
      </div>
    </aside>
  </div>

  {#if adminToken}
    <section class="admin-panel">
      {#if status}
        <div class="stat">
          <span class="k">{t.fedToday}</span>
          <span class="v">{status.fed_today ?? 0} {t.times}</span>
        </div>
      {/if}
      <button class="admin-btn" disabled={adminFeeding} on:click={onAdminFeed}>
        {adminFeeding ? t.adminFeedFeeding : t.adminFeedReady}
      </button>
      <button class="admin-btn" disabled={adminTesting} on:click={onAdminFeedTest}>
        {adminTesting ? t.adminTestFeeding : t.adminTestReady}
      </button>

      <div class="history">
        <div class="history-head">
          <div class="history-title">{t.announcementSectionTitle}</div>
        </div>
        <textarea
          class="announcement-input"
          placeholder={t.announcementPlaceholder}
          bind:value={announcementDraft}
          maxlength="500"
        ></textarea>
        <button class="admin-btn" disabled={savingAnnouncement} on:click={onSaveAnnouncement}>
          {savingAnnouncement ? t.announcementSaving : t.announcementSaveBtn}
        </button>
      </div>

      <div class="history">
        <div class="history-head">
          <div class="history-title">{t.autoFeedSectionTitle}</div>
        </div>
        <p class="history-note">{t.autoFeedHint}</p>
        <textarea
          class="announcement-input"
          placeholder={t.autoFeedPlaceholder}
          bind:value={autoFeedDraft}
          rows="3"
        ></textarea>
        <button class="admin-btn" disabled={savingAutoFeed} on:click={onSaveAutoFeed}>
          {savingAutoFeed ? t.autoFeedSaving : t.autoFeedSaveBtn}
        </button>
      </div>

      <div class="history">
        <div class="history-head">
          <div class="history-title">{t.historyTitle}</div>
          <button class="history-refresh" on:click={loadHistory} disabled={historyLoading} aria-label={t.historyRefresh}>↻</button>
        </div>
        <p class="history-note">{t.historyNote}</p>
        {#if historyLoading}
          <p class="history-state">{t.historyLoading}</p>
        {:else if historyError}
          <p class="history-state">{t.historyError}</p>
        {:else if history && history.length === 0}
          <p class="history-state">{t.historyEmpty}</p>
        {:else if history}
          <ul class="history-list">
            {#each history as ts}
              <li>{formatPetkitTime(ts)}</li>
            {/each}
          </ul>
        {/if}
      </div>

      <button class="admin-lock" on:click={lockAdmin}>{t.adminLockBtn}</button>
    </section>
  {/if}

  {#if toast}
    <div class="toast {toast.type}">{toast.text}</div>
  {/if}
</main>

{#if showAnnouncement}
  <!-- svelte-ignore a11y-click-events-have-key-events -->
  <!-- svelte-ignore a11y-no-static-element-interactions -->
  <div class="modal-backdrop" role="presentation" on:click={dismissAnnouncement}>
    <!-- svelte-ignore a11y-click-events-have-key-events -->
    <!-- svelte-ignore a11y-no-static-element-interactions -->
    <div class="modal announcement-modal" role="presentation" on:click|stopPropagation>
      <button class="modal-close" on:click={dismissAnnouncement}>✕</button>
      <div class="modal-icon">📢</div>
      <p class="announcement-text">{status.announcement}</p>
    </div>
  </div>
{/if}

{#if showAdminModal}
  <!-- svelte-ignore a11y-click-events-have-key-events -->
  <!-- svelte-ignore a11y-no-static-element-interactions -->
  <div class="modal-backdrop" role="presentation" on:click={closeAdminModal}>
    <!-- svelte-ignore a11y-click-events-have-key-events -->
    <!-- svelte-ignore a11y-no-static-element-interactions -->
    <div class="modal" role="presentation" on:click|stopPropagation>
      <button class="modal-close" on:click={closeAdminModal}>✕</button>
      <div class="modal-icon">🔒</div>
      <h2>{t.secretTitle}</h2>
      <p class="modal-sub">{t.secretSub}</p>
      <input
        type="password"
        class="modal-input"
        placeholder={t.pwPlaceholder}
        bind:value={adminPassword}
        on:keydown={(e) => e.key === 'Enter' && unlockAdmin()}
      />
      <button class="modal-unlock" on:click={unlockAdmin}>{t.unlockBtn}</button>
    </div>
  </div>
{/if}

{#if showInfoModal}
  <!-- svelte-ignore a11y-click-events-have-key-events -->
  <!-- svelte-ignore a11y-no-static-element-interactions -->
  <div class="modal-backdrop" role="presentation" on:click={closeInfoModal}>
    <!-- svelte-ignore a11y-click-events-have-key-events -->
    <!-- svelte-ignore a11y-no-static-element-interactions -->
    <div class="info-modal" role="presentation" on:click|stopPropagation>
      <button class="modal-close" on:click={closeInfoModal}>✕</button>
      <div class="info-head">
        <span class="info-avatar">🐱</span>
        <div class="info-head-text">
          <h2>{ROLL_ROLL_NAME}</h2>
          <p class="info-subtitle">{t.infoSubtitle}</p>
        </div>
        <a class="info-ig" href={INSTAGRAM_URL} target="_blank" rel="noopener noreferrer">
          <svg class="info-ig-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <rect x="2" y="2" width="20" height="20" rx="5" ry="5" />
            <path d="M16 11.37A4 4 0 1 1 12.63 8 4 4 0 0 1 16 11.37z" />
            <line x1="17.5" x2="17.51" y1="6.5" y2="6.5" />
          </svg>
          {INSTAGRAM_HANDLE}
        </a>
      </div>

      <p class="info-bio">{t.infoBio}</p>

      <div class="info-feed-box">
        <div class="info-section-title">{t.infoFeedTitle}</div>
        <p class="info-feed-text">{t.infoFeedText}</p>
      </div>

      <!-- svelte-ignore a11y-click-events-have-key-events -->
      <!-- svelte-ignore a11y-no-static-element-interactions -->
      <div class="info-row" role="button" tabindex="0" on:click={openRecordingsModal}>
        <span class="info-row-icon">📹</span>
        <div class="info-row-text">
          <div class="info-row-title">{t.recordingsRowTitle}</div>
          <div class="info-row-sub">{t.recordingsRowSub}</div>
        </div>
        <span class="info-row-chevron">›</span>
      </div>

      <div class="info-section-title">{t.infoPhotosTitle}</div>
      <div class="info-gallery">
        {#each PHOTOS as src}
          <!-- svelte-ignore a11y-click-events-have-key-events -->
          <!-- svelte-ignore a11y-no-static-element-interactions -->
          <img src={src} alt={ROLL_ROLL_NAME} loading="lazy" on:click={() => (lightboxSrc = src)} />
        {/each}
      </div>

      {#if HIGHLIGHT_VIDEO_URL}
        <div class="info-section-title">{t.infoHighlightTitle}</div>
        <a class="info-highlight" href={HIGHLIGHT_VIDEO_URL} target="_blank" rel="noopener noreferrer">
          ▶ {t.infoHighlightTitle}
        </a>
      {/if}
    </div>
  </div>
{/if}

{#if lightboxSrc}
  <!-- svelte-ignore a11y-click-events-have-key-events -->
  <!-- svelte-ignore a11y-no-static-element-interactions -->
  <div class="lightbox" role="presentation" on:click={() => (lightboxSrc = null)}>
    <img src={lightboxSrc} alt={ROLL_ROLL_NAME} />
  </div>
{/if}

{#if showRecordingsModal}
  <!-- svelte-ignore a11y-click-events-have-key-events -->
  <!-- svelte-ignore a11y-no-static-element-interactions -->
  <div class="modal-backdrop" role="presentation" on:click={closeRecordingsModal}>
    <!-- svelte-ignore a11y-click-events-have-key-events -->
    <!-- svelte-ignore a11y-no-static-element-interactions -->
    <div class="info-modal" role="presentation" on:click|stopPropagation>
      <button class="modal-close" on:click={closeRecordingsModal}>✕</button>
      <div class="info-head">
        <span class="info-avatar">📹</span>
        <div class="info-head-text">
          <h2>{t.recordingsTitle}</h2>
          <p class="info-subtitle">{t.recordingsSub}</p>
        </div>
      </div>

      {#if recordingsLoading}
        <p class="history-state">{t.recordingsLoading}</p>
      {:else if recordingsError}
        <p class="history-state">{t.recordingsError}</p>
      {:else if recordings && recordings.length === 0}
        <p class="history-state">{t.recordingsEmpty}</p>
      {:else if recordings}
        <div class="recordings-table-wrap">
          <table class="recordings-table">
            <thead>
              <tr>
                <th class="recordings-col-play"></th>
                <th>{t.recordingsColTime}</th>
              </tr>
            </thead>
            <tbody>
              {#each recordings as r}
                <!-- svelte-ignore a11y-click-events-have-key-events -->
                <!-- svelte-ignore a11y-no-static-element-interactions -->
                <tr on:click={() => (playingClip = r.filename)}>
                  <td class="recordings-col-play">▶</td>
                  <td>{formatRecordingTime(r.recorded_at)}</td>
                </tr>
              {/each}
            </tbody>
          </table>
        </div>
      {/if}
    </div>
  </div>
{/if}

{#if playingClip}
  <!-- svelte-ignore a11y-click-events-have-key-events -->
  <!-- svelte-ignore a11y-no-static-element-interactions -->
  <div class="lightbox" role="presentation" on:click={() => (playingClip = null)}>
    <!-- svelte-ignore a11y-click-events-have-key-events -->
    <video src={`/clips/${playingClip}`} controls autoplay playsinline on:click|stopPropagation>
      <track kind="captions" />
    </video>
  </div>
{/if}

<style>
  main {
    max-width: 560px;
    margin: 0 auto;
    padding: 12px 16px 48px;
    display: flex;
    flex-direction: column;
    gap: 12px;
  }
  @media (min-width: 700px) {
    main {
      max-width: 900px;
      padding: 12px 24px 56px;
    }
  }
  @media (min-width: 1100px) {
    main {
      /* desktop: fill the viewport edge-to-edge instead of a centered column —
         the live view is the point, let it take the whole screen. This upscales
         past the camera's native 1728px on very wide monitors, the explicit
         trade for 佈滿畫面. */
      max-width: none;
    }
    .stage {
      /* but don't let a wide video overflow a short window — cap by viewport
         height; the video's object-fit:cover crops rather than distorts when
         the box ends up wider than 16/9 */
      max-height: calc(100vh - 160px);
    }
  }

  header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
  }
  .brand {
    display: flex;
    align-items: center;
    gap: 12px;
  }
  .logo {
    font-size: 26px;
    line-height: 1;
  }
  .brand-title {
    display: flex;
    align-items: center;
    gap: 6px;
  }
  h1 {
    margin: 0;
    font-size: 16px;
    letter-spacing: 0.5px;
  }
  .info-btn {
    border: none;
    background: none;
    color: var(--text-dim);
    font-size: 15px;
    line-height: 1;
    cursor: var(--cursor-pointer);
    padding: 2px;
    transition: color 0.12s ease;
  }
  .info-btn:hover {
    color: var(--accent-strong);
  }

  .header-right {
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .announcement-btn {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 30px;
    height: 30px;
    padding: 0;
    border-radius: 50%;
    border: 1px solid var(--line);
    background: var(--bg-soft);
    color: var(--text-dim);
    cursor: var(--cursor-pointer);
  }
  .announcement-btn svg {
    width: 16px;
    height: 16px;
  }
  .lang-toggle {
    display: flex;
    border: 1px solid var(--line);
    border-radius: 999px;
    overflow: hidden;
  }
  .lang-toggle button {
    border: none;
    background: var(--card-solid);
    color: var(--text-dim);
    font-size: 12px;
    font-weight: 600;
    padding: 6px 10px;
    cursor: var(--cursor-pointer);
  }
  .lang-toggle button.active {
    background: var(--mint);
    color: var(--pill-green);
  }

  .live-badge {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    font-size: 12px;
    font-weight: 600;
    padding: 6px 10px;
    border-radius: 999px;
    background: var(--bg-soft);
    border: 1px solid var(--line);
    color: var(--text-dim);
    white-space: nowrap;
  }
  .live-dot {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: var(--err);
    animation: live-pulse 1.4s ease-in-out infinite;
  }
  .live-badge.offline .live-dot {
    background: var(--text-dim);
    animation: none;
  }
  @keyframes live-pulse {
    0%, 100% {
      opacity: 1;
    }
    50% {
      opacity: 0.25;
    }
  }

  .stage {
    position: relative;
    aspect-ratio: 16 / 9;
    background: #001f1f;
    border: 1px solid var(--line);
    border-radius: var(--radius);
    overflow: hidden;
    box-shadow: var(--shadow);
  }
  .stage-cam {
    display: block;
    width: 100%;
    height: 100%;
  }
  .stage-cam :global(video) {
    width: 100%;
    height: 100%;
    object-fit: cover;
  }
  .stage-refresh {
    position: absolute;
    top: 10px;
    right: 10px;
    width: 44px;
    height: 44px;
    border-radius: 50%;
    border: none;
    background: rgba(0, 0, 0, 0.45);
    color: #fff;
    font-size: 22px;
    line-height: 1;
    cursor: var(--cursor-pointer);
    display: flex;
    align-items: center;
    justify-content: center;
  }
  .stage-watermark {
    position: absolute;
    bottom: 10px;
    right: 10px;
    font-size: 11px;
    font-family: ui-monospace, "SF Mono", Menlo, monospace;
    color: rgba(255, 255, 255, 0.8);
    background: rgba(0, 0, 0, 0.4);
    padding: 2px 7px;
    border-radius: 4px;
    pointer-events: none;
  }
  .stage-feed-btn {
    position: absolute;
    bottom: 14px;
    left: 14px;
    max-width: calc(100% - 28px);
    padding: 12px 20px;
    font-size: 16px;
    font-weight: 700;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    color: rgba(255, 255, 255, 0.85);
    background: linear-gradient(180deg, rgba(56, 212, 160, 0.5) 0%, rgba(6, 201, 136, 0.5) 100%);
    backdrop-filter: blur(4px);
    border: 1px solid rgba(255, 255, 255, 0.15);
    border-radius: 999px;
    cursor: not-allowed;
    transition: transform 0.08s ease, filter 0.15s ease;
  }
  .stage-feed-btn.ready {
    color: var(--mint);
    background: linear-gradient(180deg, var(--accent) 0%, var(--accent-strong) 100%);
    border: none;
    cursor: var(--cursor-pointer);
  }
  .stage-feed-btn.ready:active {
    transform: translateY(2px);
  }
  .stage-feed-btn:disabled {
    opacity: 0.85;
  }
  .stage-feed-btn.ready:disabled {
    opacity: 0.7;
  }

  .action {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 10px;
    margin-top: -6px;
  }
  .hint {
    font-size: 12.5px;
    color: var(--text-dim);
    text-align: center;
    margin: 0;
    line-height: 1.6;
  }

  /* mobile: video block stacked above the activity feed. desktop (>=1100px):
     video on the left, activity as a fixed-width right rail matching the
     video block's height, feed scrolling inside it */
  .live-layout {
    display: flex;
    flex-direction: column;
    gap: 12px;
  }
  .live-main {
    display: flex;
    flex-direction: column;
    gap: 12px;
    min-width: 0;
  }
  @media (min-width: 1100px) {
    .live-layout {
      flex-direction: row;
      align-items: stretch;
    }
    .live-main {
      flex: 1;
    }
    .activity {
      width: 320px;
      flex-shrink: 0;
    }
  }

  .activity {
    display: flex;
    flex-direction: column;
    background: var(--card-solid);
    border: 1px solid var(--line);
    border-radius: var(--radius);
    padding: 14px 16px;
    box-shadow: var(--shadow);
    min-height: 0;
  }
  .activity-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
    margin-bottom: 10px;
  }
  .activity-title {
    font-size: 13px;
    font-weight: 700;
  }
  .activity-feed {
    flex: 1;
    min-height: 0;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
    gap: 8px;
  }
  @media (max-width: 1099px) {
    .activity-feed {
      max-height: 300px;
    }
  }
  .activity-state {
    margin: 0;
    font-size: 13px;
    color: var(--text-dim);
  }
  .activity-item {
    display: block;
    width: 100%;
    text-align: left;
    background: var(--bg-soft);
    border: 1px solid var(--line);
    border-radius: 12px;
    padding: 10px 12px;
    cursor: var(--cursor-pointer);
    transition: border-color 0.15s ease, background-color 0.15s ease;
  }
  .activity-item:hover {
    border-color: var(--accent-strong);
    background: rgba(6, 201, 136, 0.08);
  }
  .activity-item-head {
    display: flex;
    align-items: baseline;
    gap: 8px;
    margin-bottom: 3px;
  }
  .activity-time {
    font-family: ui-monospace, "SF Mono", Menlo, monospace;
    font-size: 12px;
    font-weight: 600;
    color: var(--text-dim);
  }
  .activity-who {
    font-size: 11px;
    color: var(--accent-strong);
    font-weight: 600;
  }
  .activity-item-body {
    font-size: 13px;
    line-height: 1.5;
    color: var(--text);
  }
  .activity-link {
    color: var(--accent-strong);
    font-weight: 600;
    white-space: nowrap;
  }
  /* the "fed" line has no clip to open yet — flat, non-interactive, no accent
     hover, so only the "clip ready" line looks clickable */
  .activity-item.is-fed {
    cursor: default;
  }
  .activity-item.is-fed:hover {
    border-color: var(--line);
    background: var(--bg-soft);
  }
  .activity-pending {
    font-size: 11px;
    color: var(--text-dim);
    white-space: nowrap;
  }

  .toast {
    position: fixed;
    left: 50%;
    bottom: 26px;
    transform: translateX(-50%);
    padding: 12px 20px;
    border-radius: 999px;
    font-size: 15px;
    font-weight: 600;
    box-shadow: var(--shadow);
    animation: pop 0.2s ease;
  }
  .toast.ok {
    background: var(--ok-tint);
    color: var(--ok);
    border: 1px solid var(--line);
  }
  .toast.warn {
    background: var(--warn-tint);
    color: var(--warn);
    border: 1px solid var(--line);
  }
  .toast.err {
    background: var(--err-tint);
    color: var(--err);
    border: 1px solid var(--line);
  }
  @keyframes pop {
    from {
      opacity: 0;
      transform: translate(-50%, 8px);
    }
    to {
      opacity: 1;
      transform: translate(-50%, 0);
    }
  }

  .admin-panel {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 6px;
    margin-top: -4px;
  }
  .stat {
    background: var(--card-solid);
    border: 1px solid var(--line);
    border-radius: 14px;
    padding: 12px 24px;
    text-align: center;
    min-width: 160px;
    margin-bottom: 4px;
  }
  .stat .k {
    display: block;
    font-size: 12px;
    color: var(--text-dim);
    margin-bottom: 4px;
  }
  .stat .v {
    font-size: 15px;
    font-weight: 600;
  }
  .admin-btn {
    width: 100%;
    padding: 12px;
    font-size: 14px;
    font-weight: 700;
    color: #fff;
    background: var(--gradient-teal-orange);
    border: none;
    border-radius: 12px;
    cursor: var(--cursor-pointer);
  }
  .admin-btn:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }
  .admin-lock {
    background: none;
    border: none;
    color: var(--text-dim);
    font-size: 12px;
    cursor: var(--cursor-pointer);
    padding: 4px;
  }
  .history {
    width: 100%;
    background: var(--card-solid);
    border: 1px solid var(--line);
    border-radius: 14px;
    padding: 14px 16px;
  }
  .history-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
  }
  .history-title {
    font-size: 13px;
    font-weight: 700;
  }
  .history-refresh {
    border: none;
    background: none;
    color: var(--text-dim);
    font-size: 15px;
    line-height: 1;
    cursor: var(--cursor-pointer);
    padding: 2px 4px;
  }
  .history-refresh:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }
  .history-note {
    margin: 2px 0 8px;
    font-size: 11px;
    color: var(--text-dim);
  }
  .history-state {
    margin: 0;
    font-size: 13px;
    color: var(--text-dim);
  }
  .history-list {
    list-style: none;
    margin: 0;
    padding: 0;
    max-height: 200px;
    overflow-y: auto;
    font-family: ui-monospace, "SF Mono", Menlo, monospace;
    font-size: 13px;
  }
  .history-list li {
    padding: 4px 0;
    border-bottom: 1px solid var(--line);
  }
  .history-list li:last-child {
    border-bottom: none;
  }

  .modal-backdrop {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.6);
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 16px;
    z-index: 100;
  }
  .modal {
    position: relative;
    width: 100%;
    max-width: 340px;
    background: var(--card-solid);
    border: 1px solid var(--line);
    border-radius: 18px;
    padding: 32px 24px 24px;
    display: flex;
    flex-direction: column;
    align-items: center;
    text-align: center;
    gap: 6px;
    box-shadow: var(--shadow);
  }
  .modal-close {
    position: absolute;
    top: 12px;
    right: 14px;
    background: none;
    border: none;
    color: var(--text-dim);
    font-size: 16px;
    cursor: var(--cursor-pointer);
  }
  .modal-icon {
    width: 56px;
    height: 56px;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 24px;
    background: var(--gradient-teal-orange);
    margin-bottom: 6px;
  }
  .modal h2 {
    margin: 0;
    font-size: 18px;
  }
  .modal-sub {
    margin: 0 0 14px;
    font-size: 13px;
    color: var(--text-dim);
  }
  .modal-input {
    width: 100%;
    padding: 12px 14px;
    border-radius: 999px;
    border: 1px solid var(--line);
    background: var(--bg, #ffffff);
    color: inherit;
    font-size: 14px;
    margin-bottom: 14px;
    text-align: center;
  }
  .modal-unlock {
    width: 100%;
    padding: 12px;
    border: none;
    border-radius: 999px;
    font-size: 15px;
    font-weight: 700;
    color: #fff;
    background: var(--gradient-teal-orange);
    cursor: var(--cursor-pointer);
  }
  .announcement-text {
    margin: 0;
    font-size: 14px;
    line-height: 1.5;
    white-space: pre-line;
  }
  /* the announcement popup shares .modal with the admin unlock dialog, so
     blow up just this one (~2x) via a modifier rather than touching .modal */
  .announcement-modal {
    max-width: 640px;
    padding: 44px 40px 40px;
    gap: 10px;
  }
  .announcement-modal .modal-icon {
    width: 84px;
    height: 84px;
    font-size: 38px;
    margin-bottom: 10px;
  }
  .announcement-modal .modal-close {
    font-size: 22px;
    top: 16px;
    right: 18px;
    /* square box sized for the ✕; a transparent border is reserved up front so
       the green hover frame doesn't shift anything */
    display: flex;
    align-items: center;
    justify-content: center;
    width: 34px;
    height: 34px;
    line-height: 1;
    border: 2px solid transparent;
    border-radius: 6px;
    transition: color 0.12s ease, border-color 0.12s ease, background-color 0.12s ease;
  }
  .announcement-modal .modal-close:hover {
    color: var(--accent-strong);
    border-color: var(--accent-strong);
    /* Lattice `button-ghost` hover — emerald at 10% (primary-wash), same as
       the Instagram handle chip */
    background: rgba(6, 201, 136, 0.1);
  }
  /* same button-ghost hover on the Roll Roll info card's ✕ (and the recordings
     card, which shares .info-modal chrome) */
  .info-modal .modal-close {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 30px;
    height: 30px;
    line-height: 1;
    border: 2px solid transparent;
    border-radius: 6px;
    transition: color 0.12s ease, border-color 0.12s ease, background-color 0.12s ease;
  }
  .info-modal .modal-close:hover {
    color: var(--accent-strong);
    border-color: var(--accent-strong);
    background: rgba(6, 201, 136, 0.1);
  }
  .announcement-modal .announcement-text {
    font-size: 23px;
    line-height: 1.65;
  }
  .announcement-input {
    width: 100%;
    min-height: 72px;
    padding: 10px 12px;
    border-radius: 12px;
    border: 1px solid var(--line);
    background: var(--bg, #ffffff);
    color: inherit;
    font-size: 13px;
    font-family: inherit;
    resize: vertical;
    margin-bottom: 8px;
    box-sizing: border-box;
  }

  .info-modal {
    /* ex-product-selector (Lattice Design): canvas bg, rounded.xl, spacing.xxl padding */
    position: relative;
    width: 100%;
    max-width: 660px;
    max-height: 85vh;
    overflow-y: auto;
    background: var(--bg);
    border: 1px solid var(--line);
    border-radius: 24px;
    padding: 24px;
    box-shadow: var(--shadow);
  }
  .info-head {
    display: flex;
    align-items: flex-start;
    gap: 12px;
    margin-bottom: 10px;
    padding-right: 32px;
  }
  .info-avatar {
    font-size: 32px;
    line-height: 1;
  }
  .info-head-text {
    flex: 1;
  }
  .info-head-text h2 {
    margin: 0;
    font-size: 18px;
  }
  .info-subtitle {
    margin: 2px 0 0;
    font-size: 12px;
    color: var(--text-dim);
  }
  .info-ig {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 6px 12px;
    border-radius: 999px;
    background: var(--bg-soft);
    border: 1px solid var(--line);
    color: var(--text);
    font-size: 12px;
    font-weight: 600;
    text-decoration: none;
    white-space: nowrap;
    transition: color 0.15s ease, border-color 0.15s ease, background-color 0.15s ease;
  }
  .info-ig:hover {
    color: var(--accent-strong);
    border-color: var(--accent-strong);
    background: rgba(6, 201, 136, 0.1);
  }
  .info-ig-icon {
    width: 20px;
    height: 20px;
    flex-shrink: 0;
  }
  .info-bio {
    margin: 0 0 16px;
    font-size: 14px;
    line-height: 1.6;
  }
  .info-feed-box {
    margin-bottom: 16px;
  }
  .info-feed-box .info-section-title {
    margin-bottom: 4px;
  }
  .info-feed-text {
    margin: 0;
    font-size: 14px;
    line-height: 1.6;
  }
  .info-section-title {
    font-size: 13px;
    font-weight: 700;
    margin-bottom: 8px;
  }
  .info-gallery {
    display: flex;
    gap: 8px;
    overflow-x: auto;
    /* padding on all sides so the hover glow isn't clipped by
       overflow-x:auto (which forces overflow-y to clip too — a container
       can't scroll one axis while leaving the other visible), including
       for the first/last photo where there's no neighbour to absorb it */
    padding: 20px;
    margin: -20px -20px 0;
  }
  .info-gallery img {
    width: 110px;
    height: 110px;
    object-fit: cover;
    border-radius: 12px;
    flex-shrink: 0;
    cursor: zoom-in;
    position: relative;
    z-index: 0;
    transition: transform 0.2s ease, box-shadow 0.2s ease;
  }
  .info-gallery img:hover {
    transform: scale(1.08);
    box-shadow: 0 0 18px 4px rgba(6, 201, 136, 0.55);
    z-index: 1;
  }
  .lightbox {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.92);
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 24px;
    z-index: 200;
    cursor: zoom-out;
  }
  .lightbox img {
    max-width: 100%;
    max-height: 100%;
    object-fit: contain;
    border-radius: 8px;
  }
  .info-highlight {
    display: block;
    padding: 14px 16px;
    border-radius: 14px;
    background: var(--gradient-teal-orange);
    color: #fff;
    font-size: 14px;
    font-weight: 700;
    text-decoration: none;
    text-align: center;
  }
  .info-row {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 10px 12px;
    margin-bottom: 16px;
    border: 1px solid var(--line);
    border-radius: 14px;
    background: var(--bg);
    cursor: var(--cursor-pointer);
    transition: border-color 0.15s ease, background-color 0.15s ease;
  }
  .info-row:hover {
    border-color: var(--accent-strong);
    background: rgba(6, 201, 136, 0.1);
  }
  .info-row-icon {
    font-size: 22px;
  }
  .info-row-text {
    flex: 1;
  }
  .info-row-title {
    font-size: 13px;
    font-weight: 700;
  }
  .info-row-sub {
    font-size: 11px;
    color: var(--text-dim);
  }
  .info-row-chevron {
    font-size: 20px;
    color: var(--text-dim);
  }
  /* ex-data-table-cell (Lattice Design): canvas header, mono-caps eyebrow
     header type, body-sm cells, spacing.sm/lg padding, hairline row border */
  .recordings-table-wrap {
    max-height: 320px;
    overflow-y: auto;
    border: 1px solid var(--line);
    border-radius: 12px;
  }
  .recordings-table {
    width: 100%;
    border-collapse: collapse;
  }
  .recordings-table thead th {
    position: sticky;
    top: 0;
    background: var(--bg-soft);
    text-align: left;
    font-size: 13px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    color: var(--text-dim);
    padding: 9px 16px;
    border-bottom: 1px solid var(--line);
  }
  .recordings-table tbody td {
    font-size: 15px;
    padding: 9px 16px;
    border-bottom: 1px solid var(--line);
  }
  .recordings-table tbody tr {
    cursor: var(--cursor-pointer);
  }
  .recordings-table tbody tr:last-child td {
    border-bottom: none;
  }
  .recordings-table tbody tr:hover td {
    background: var(--bg-soft);
  }
  .recordings-col-play {
    width: 36px;
    color: var(--accent-strong);
  }
  .lightbox video {
    max-width: 100%;
    max-height: 100%;
    border-radius: 8px;
  }
</style>
