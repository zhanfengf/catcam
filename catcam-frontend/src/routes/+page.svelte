<script>
  import { onMount, onDestroy } from 'svelte';
  import '../app.css';
  import { getStatus, feed, adminFeed } from '$lib/api.js';
  import { VideoRTC } from '$lib/video-rtc.js';

  const ADMIN_TOKEN_KEY = 'catcam_admin_token';

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
  let loading = true;
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

  async function refresh() {
    try {
      status = await getStatus();
      localSecs = status.seconds_until_next ?? 0;
      loading = false;
    } catch (e) {
      loading = false;
      showToast('err', '連唔到伺服器，遲啲再試');
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
      showToast('ok', data.message || '餵咗喇！🐱');
    } else {
      showToast(data.reason === 'outside_hours' ? 'warn' : 'warn',
        data.message || '而家餵唔到');
    }
    await refresh();
  }

  function fmt(secs) {
    if (secs <= 0) return '即刻可以餵';
    const h = Math.floor(secs / 3600);
    const m = Math.floor((secs % 3600) / 60);
    const s = secs % 60;
    if (h > 0) return `${h} 小時 ${m} 分鐘後`;
    if (m > 0) return `${m} 分 ${String(s).padStart(2, '0')} 秒後`;
    return `${s} 秒後`;
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
    showToast('ok', '已解鎖秘密通道 🔓');
  }

  function lockAdmin() {
    adminToken = null;
    localStorage.removeItem(ADMIN_TOKEN_KEY);
    showToast('ok', '已鎖返');
  }

  async function onAdminFeed() {
    if (adminFeeding || !adminToken) return;
    adminFeeding = true;
    const { httpOk, data } = await adminFeed(adminToken);
    adminFeeding = false;
    if (httpOk && data.ok) {
      showToast('ok', data.message || '強制餵咗喇！🔓🐱');
    } else {
      showToast('err', data.message || '密碼唔啱或者已過期');
      if (data.reason === 'unauthorized') {
        lockAdmin();
      }
    }
    await refresh();
  }

  $: canFeed = status?.can_feed;
  $: reason = status?.reason;
  $: btnLabel = feeding
    ? '餵緊…'
    : canFeed
      ? '🍚 餵貓'
      : reason === 'outside_hours'
        ? '😴 休息時間'
        : '⏳ 未到下次';

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

  onMount(() => {
    adminToken = localStorage.getItem(ADMIN_TOKEN_KEY);
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
  <title>貓貓直播 · 餵貓</title>
</svelte:head>

<main>
  <header>
    <div class="brand">
      <!-- svelte-ignore a11y-click-events-have-key-events -->
      <!-- svelte-ignore a11y-no-static-element-interactions -->
      <span class="logo" on:click={onLogoClick}>🐱</span>
      <div>
        <h1>貓貓直播</h1>
        <p class="tag">睇住佢，順手餵餐飯</p>
      </div>
    </div>
    {#if status}
      <span class="live-badge" class:on={status.window.is_open_now}>
        {status.window.is_open_now ? '● 開放中' : '● 休息中'}
      </span>
    {/if}
  </header>

  <section class="stage">
    <video-rtc class="stage-cam" bind:this={videoRtcEl}></video-rtc>
  </section>

  <section class="statusbar">
    {#if loading}
      <p class="dim">載入緊…</p>
    {:else if status}
      <div class="stat">
        <span class="k">下次可餵</span>
        <span class="v">{fmt(localSecs)}</span>
      </div>
      <div class="stat">
        <span class="k">今日餵咗</span>
        <span class="v">{status.fed_today ?? 0} 次</span>
      </div>
      <div class="stat">
        <span class="k">餵食時段</span>
        <span class="v">{status.window.open}–{status.window.close}</span>
      </div>
    {/if}
  </section>

  <section class="action">
    <button
      class="feed-btn"
      class:ready={canFeed}
      disabled={!canFeed || feeding}
      on:click={onFeed}
    >
      {btnLabel}
    </button>
    <p class="hint">
      每 {status?.cooldown_minutes ?? 120} 分鐘可以餵一次（{status?.amount ?? 10}g）<br />
      夜晚 {status?.window?.close ?? '23:59'} 之後貓貓要瞓覺喇 🌙
    </p>
  </section>

  {#if adminToken}
    <section class="admin-panel">
      <button class="admin-btn" disabled={adminFeeding} on:click={onAdminFeed}>
        {adminFeeding ? '強制餵緊…' : '🔓 強制餵貓（繞過規則）'}
      </button>
      <button class="admin-lock" on:click={lockAdmin}>🔒 鎖返</button>
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
      <h2>秘密通道</h2>
      <p class="modal-sub">輸入密碼解鎖管理工具</p>
      <input
        type="password"
        class="modal-input"
        placeholder="輸入密碼"
        bind:value={adminPassword}
        on:keydown={(e) => e.key === 'Enter' && unlockAdmin()}
      />
      <button class="modal-unlock" on:click={unlockAdmin}>解鎖</button>
    </div>
  </div>
{/if}

<style>
  main {
    max-width: 560px;
    margin: 0 auto;
    padding: 20px 16px 48px;
    display: flex;
    flex-direction: column;
    gap: 18px;
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
    font-size: 40px;
    line-height: 1;
  }
  h1 {
    margin: 0;
    font-size: 22px;
    letter-spacing: 0.5px;
  }
  .tag {
    margin: 2px 0 0;
    font-size: 13px;
    color: var(--text-dim);
  }

  .live-badge {
    font-size: 12px;
    padding: 6px 10px;
    border-radius: 999px;
    background: #3a2c20;
    color: var(--text-dim);
    white-space: nowrap;
  }
  .live-badge.on {
    background: #14361b;
    color: var(--ok);
  }

  .stage {
    position: relative;
    aspect-ratio: 16 / 9;
    background: #0d0906;
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
  .statusbar {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 10px;
  }
  .stat {
    background: var(--card-solid);
    border: 1px solid var(--line);
    border-radius: 14px;
    padding: 12px 10px;
    text-align: center;
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

  .action {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 10px;
    margin-top: 4px;
  }
  .feed-btn {
    width: 100%;
    padding: 20px;
    font-size: 22px;
    font-weight: 800;
    color: #3a1c05;
    background: #4a3a2c;
    border: none;
    border-radius: var(--radius);
    cursor: not-allowed;
    transition: transform 0.08s ease, filter 0.15s ease;
    box-shadow: var(--shadow);
  }
  .feed-btn.ready {
    color: #3a1c05;
    background: linear-gradient(180deg, var(--accent) 0%, var(--accent-strong) 100%);
    cursor: pointer;
  }
  .feed-btn.ready:active {
    transform: translateY(2px);
  }
  .feed-btn:disabled {
    opacity: 0.85;
  }
  .feed-btn.ready:disabled {
    opacity: 0.7;
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
    background: #14361b;
    color: var(--ok);
    border: 1px solid #1f5a2c;
  }
  .toast.warn {
    background: #3a2f12;
    color: var(--warn);
    border: 1px solid #6b551d;
  }
  .toast.err {
    background: #3a1616;
    color: var(--err);
    border: 1px solid #6b1d1d;
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
  .admin-btn {
    width: 100%;
    padding: 12px;
    font-size: 14px;
    font-weight: 700;
    color: #fff;
    background: linear-gradient(135deg, #3a6b8a 0%, #c9772e 100%);
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
    background: linear-gradient(135deg, #3a6b8a 0%, #c9772e 100%);
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
    background: var(--bg, #15110c);
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
    background: linear-gradient(135deg, #3a6b8a 0%, #c9772e 100%);
    cursor: pointer;
  }
</style>
