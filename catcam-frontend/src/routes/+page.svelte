<script>
  import { onMount, onDestroy } from 'svelte';
  import '../app.css';
  import { getStatus, feed, adminFeed, adminHistory } from '$lib/api.js';
  import { VideoRTC } from '$lib/video-rtc.js';

  const ADMIN_TOKEN_KEY = 'catcam_admin_token';
  const LANG_KEY = 'catcam_lang';

  const translations = {
    zh: {
      title: 'Roll Roll直播',
      live: '直播中',
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
      secretTitle: '秘密通道',
      secretSub: '輸入密碼解鎖管理工具',
      pwPlaceholder: '輸入密碼',
      unlockBtn: '解鎖',
      unlockedToast: '已解鎖秘密通道 🔓',
      lockedToast: '已鎖返',
      adminFeedReady: '🔓 強制餵貓（繞過規則）',
      adminFeedFeeding: '強制餵緊…',
      adminFedFallback: '強制餵咗喇！🔓🐱',
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
      historyRefresh: '重新整理紀錄'
    },
    en: {
      title: 'Roll Roll Live',
      live: 'LIVE',
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
      secretTitle: 'Secret Channel',
      secretSub: 'Enter password to unlock admin tools',
      pwPlaceholder: 'Password',
      unlockBtn: 'Unlock',
      unlockedToast: 'Secret channel unlocked 🔓',
      lockedToast: 'Locked',
      adminFeedReady: '🔓 Force Feed (bypass rules)',
      adminFeedFeeding: 'Force feeding…',
      adminFedFallback: 'Force fed! 🔓🐱',
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
      historyRefresh: 'Refresh history'
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
  }

  let status = null;
  let feeding = false;
  let localSecs = 0;
  let toast = null;
  let toastTimer;
  let pollTimer;
  let tickTimer;

  let secretTapCount = 0;
  let secretTapTimer;
  let showAdminModal = false;
  let adminPassword = '';
  let adminToken = null;
  let adminFeeding = false;
  let history = null;
  let historyLoading = false;
  let historyError = false;

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

  $: canFeed = status?.can_feed;
  $: btnLabel = feeding
    ? t.feedBtnFeeding
    : canFeed
      ? t.feedBtnReady
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

  onMount(() => {
    lang = localStorage.getItem(LANG_KEY) || 'zh';
    adminToken = localStorage.getItem(ADMIN_TOKEN_KEY);
    if (adminToken) loadHistory();
    refresh();
    pollTimer = setInterval(refresh, 15000);
    tickTimer = setInterval(() => {
      if (localSecs > 0) localSecs -= 1;
      else if (status && !status.can_feed) refresh();
    }, 1000);
    initCamera();
  });

  onDestroy(() => {
    clearInterval(pollTimer);
    clearInterval(tickTimer);
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
      <div>
        <h1>{t.title}</h1>
      </div>
    </div>
    <div class="header-right">
      <div class="lang-toggle">
        <button class:active={lang === 'zh'} on:click={() => setLang('zh')}>繁中</button>
        <button class:active={lang === 'en'} on:click={() => setLang('en')}>EN</button>
      </div>
      <span class="live-badge">
        <span class="live-dot"></span>
        {t.live}
      </span>
    </div>
  </header>

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
      max-width: 1300px;
    }
  }
  @media (min-width: 1600px) {
    main {
      /* camera's native resolution is 1728x1080 — capping here avoids
         upscaling the video past its real pixel density on bigger screens.
         Kept below that cap so the hint line still fits under the video
         without scrolling on common desktop viewport heights. */
      max-width: 1550px;
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
  h1 {
    margin: 0;
    font-size: 16px;
    letter-spacing: 0.5px;
  }

  .header-right {
    display: flex;
    align-items: center;
    gap: 8px;
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
    cursor: pointer;
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
    cursor: pointer;
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
    cursor: pointer;
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
    cursor: pointer;
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
    cursor: pointer;
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
    cursor: pointer;
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
    cursor: pointer;
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
    cursor: pointer;
  }
</style>
