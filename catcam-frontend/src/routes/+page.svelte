<script>
  import { onMount, onDestroy } from 'svelte';
  import '../app.css';
  import { getStatus, feed, STREAM_URL } from '$lib/api.js';

  let status = null;
  let loading = true;
  let feeding = false;
  let localSecs = 0;
  let toast = null;
  let toastTimer;
  let pollTimer;
  let tickTimer;

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

  $: canFeed = status?.can_feed;
  $: reason = status?.reason;
  $: btnLabel = feeding
    ? '餵緊…'
    : canFeed
      ? '🍚 餵貓'
      : reason === 'outside_hours'
        ? '😴 休息時間'
        : '⏳ 未到下次';

  onMount(() => {
    refresh();
    pollTimer = setInterval(refresh, 15000);
    tickTimer = setInterval(() => {
      if (localSecs > 0) localSecs -= 1;
      else if (status && !status.can_feed) refresh();
    }, 1000);
  });

  onDestroy(() => {
    clearInterval(pollTimer);
    clearInterval(tickTimer);
    clearTimeout(toastTimer);
  });
</script>

<svelte:head>
  <title>貓貓直播 · 餵貓</title>
</svelte:head>

<main>
  <header>
    <div class="brand">
      <span class="logo">🐱</span>
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
    {#if STREAM_URL}
      <video src={STREAM_URL} autoplay muted playsinline controls></video>
    {:else}
      <div class="stage-placeholder">
        <span class="big">🎥</span>
        <p>直播畫面準備緊</p>
        <small>裝好 RTSP cam + go2rtc 後就會喺呢度出現</small>
      </div>
    {/if}
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
      每 {status?.cooldown_minutes ?? 120} 分鐘可以餵一次，每次一份（{status?.amount ?? 10}）。
      夜晚 {status?.window?.close ?? '23:59'} 之後貓貓要瞓覺喇 🌙
    </p>
  </section>

  {#if toast}
    <div class="toast {toast.type}">{toast.text}</div>
  {/if}

  <footer>由 🐾 Home Assistant 驅動</footer>
</main>

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
  .stage video {
    width: 100%;
    height: 100%;
    object-fit: cover;
  }
  .stage-placeholder {
    position: absolute;
    inset: 0;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 6px;
    color: var(--text-dim);
    text-align: center;
    padding: 12px;
  }
  .stage-placeholder .big {
    font-size: 48px;
    opacity: 0.7;
  }
  .stage-placeholder p {
    margin: 4px 0 0;
    font-size: 15px;
  }
  .stage-placeholder small {
    font-size: 12px;
    opacity: 0.7;
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

  footer {
    text-align: center;
    font-size: 12px;
    color: var(--text-dim);
    opacity: 0.6;
    margin-top: 8px;
  }
</style>
