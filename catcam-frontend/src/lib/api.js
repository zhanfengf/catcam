const API_BASE = import.meta.env.VITE_API_BASE ?? '';

export async function getStatus() {
  const r = await fetch(`${API_BASE}/status`, { cache: 'no-store' });
  if (!r.ok) throw new Error(`status ${r.status}`);
  return r.json();
}

export async function getRecordings() {
  const r = await fetch(`${API_BASE}/recordings`, { cache: 'no-store' });
  if (!r.ok) throw new Error(`recordings ${r.status}`);
  return r.json();
}

export async function getActivity() {
  const r = await fetch(`${API_BASE}/activity`, { cache: 'no-store' });
  if (!r.ok) throw new Error(`activity ${r.status}`);
  return r.json();
}

export async function feed() {
  const r = await fetch(`${API_BASE}/feed`, { method: 'POST' });
  let data = {};
  try {
    data = await r.json();
  } catch (e) {

  }
  return { httpOk: r.ok, status: r.status, data };
}

async function signAdminRequest(token, method, path) {
  const timestamp = Math.floor(Date.now() / 1000).toString();
  const message = `${method}:${path}:${timestamp}`;
  const key = await crypto.subtle.importKey(
    'raw',
    new TextEncoder().encode(token),
    { name: 'HMAC', hash: 'SHA-256' },
    false,
    ['sign']
  );
  const sigBuf = await crypto.subtle.sign('HMAC', key, new TextEncoder().encode(message));
  const signature = Array.from(new Uint8Array(sigBuf))
    .map((b) => b.toString(16).padStart(2, '0'))
    .join('');
  return { timestamp, signature };
}

export async function adminFeed(token) {
  const { timestamp, signature } = await signAdminRequest(token, 'POST', '/admin/feed');
  const r = await fetch(`${API_BASE}/admin/feed`, {
    method: 'POST',
    headers: {
      'X-Admin-Timestamp': timestamp,
      'X-Admin-Signature': signature
    }
  });
  let data = {};
  try {
    data = await r.json();
  } catch (e) {

  }
  return { httpOk: r.ok, status: r.status, data };
}

export async function adminFeedTest(token) {
  const { timestamp, signature } = await signAdminRequest(token, 'POST', '/admin/feed-test');
  const r = await fetch(`${API_BASE}/admin/feed-test`, {
    method: 'POST',
    headers: {
      'X-Admin-Timestamp': timestamp,
      'X-Admin-Signature': signature
    }
  });
  let data = {};
  try {
    data = await r.json();
  } catch (e) {

  }
  return { httpOk: r.ok, status: r.status, data };
}

export async function adminSetAnnouncement(token, text) {
  const { timestamp, signature } = await signAdminRequest(token, 'POST', '/admin/announcement');
  const r = await fetch(`${API_BASE}/admin/announcement`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-Admin-Timestamp': timestamp,
      'X-Admin-Signature': signature
    },
    body: JSON.stringify({ text })
  });
  let data = {};
  try {
    data = await r.json();
  } catch (e) {

  }
  return { httpOk: r.ok, status: r.status, data };
}

export async function adminSetAutoFeed(token, windows) {
  const { timestamp, signature } = await signAdminRequest(token, 'POST', '/admin/auto-feed');
  const r = await fetch(`${API_BASE}/admin/auto-feed`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-Admin-Timestamp': timestamp,
      'X-Admin-Signature': signature
    },
    body: JSON.stringify({ windows })
  });
  let data = {};
  try {
    data = await r.json();
  } catch (e) {

  }
  return { httpOk: r.ok, status: r.status, data };
}

export async function adminSetFasting(token, reason) {
  const { timestamp, signature } = await signAdminRequest(token, 'POST', '/admin/fasting');
  const r = await fetch(`${API_BASE}/admin/fasting`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-Admin-Timestamp': timestamp,
      'X-Admin-Signature': signature
    },
    body: JSON.stringify({ reason })
  });
  let data = {};
  try {
    data = await r.json();
  } catch (e) {

  }
  return { httpOk: r.ok, status: r.status, data };
}

export async function adminClearFasting(token) {
  const { timestamp, signature } = await signAdminRequest(token, 'POST', '/admin/fasting/clear');
  const r = await fetch(`${API_BASE}/admin/fasting/clear`, {
    method: 'POST',
    headers: {
      'X-Admin-Timestamp': timestamp,
      'X-Admin-Signature': signature
    }
  });
  let data = {};
  try {
    data = await r.json();
  } catch (e) {

  }
  return { httpOk: r.ok, status: r.status, data };
}

export async function adminHistory(token) {
  const { timestamp, signature } = await signAdminRequest(token, 'GET', '/admin/history');
  const r = await fetch(`${API_BASE}/admin/history`, {
    method: 'GET',
    headers: {
      'X-Admin-Timestamp': timestamp,
      'X-Admin-Signature': signature
    }
  });
  let data = {};
  try {
    data = await r.json();
  } catch (e) {

  }
  return { httpOk: r.ok, status: r.status, data };
}
